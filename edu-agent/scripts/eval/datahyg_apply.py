# -*- coding: utf-8 -*-
"""
W-NEXT-DATAHYG-001 执行器：清除 edu_knowledge `_default` 分区 10 条跨分区冗余副本。

承接（MILVUSFLUSH1 处置建议 §六-2，用户已批准立项；归因证据
data/wnextmilvusflush1_probe.json rowdiff.diff_ids + attribution）：
  10 个 PK（crc32 客户端给定 id）在 `_default` 与 `user_1` 各持 1 份活副本
  （写入窗 09-16 15:05~16:06，hex 命名 md 来源；upsert 只 tombstone 目标分区，
  旧 `_default` 副本存活）。整表 query 枚举按 PK reduce 去重 = 3388 不受影响；
  count(*) 数物理副本 = 3398 虚高 10。本批删除 `_default` 冗余副本，
  预期 count(*) 3398→3388、枚举集合 sha 不变（检索零影响）。

三核闸（逐步留痕，产物全落 data/）：
  backup      核1 10 PK 全字段快照（含全部标量 + 向量 + 副本分区），可重插=恢复路径
  precheck    删前基线：口径阶梯 + 逐 PK 分区归属核验 + golden5 检索预跑
  apply       核2 仅删 `_default` 分区这 10 个 PK（partition_name 精确删除），
              前后 count 对比（3398→3388 预期）；对已删行重跑 = 幂等 no-op（核4 同路径）
  verify      核3 ①10 PK `_default` 0 命中 / `user_1` 各 1 命中 ②整表枚举仍 3388
              且 id 集合 sha 与删前逐位一致 ③golden 抽检 5 条（eval64-v2 集）仍命中

红线（违者立即中止）：
  - 只动这 10 个 PK 的 `_default` 副本；禁触 user_1/user_100003/course_public 分区与任何其他行
  - 唯一写原语 = delete(ids, partition_name="_default")；禁 flush/compaction/load/release/
    insert/upsert（恢复路径只写进文档 meta，本脚本自身永不执行 insert）
  - 删前逐 PK 双副本状态机校验（_default=1 且 user_1=1 且标量逐字段同）不满足即中止

用法（cwd=edu-agent）:
  .venv/Scripts/python.exe -X utf8 scripts/eval/datahyg_apply.py backup
  .venv/Scripts/python.exe -X utf8 scripts/eval/datahyg_apply.py precheck
  .venv/Scripts/python.exe -X utf8 scripts/eval/datahyg_apply.py apply
  .venv/Scripts/python.exe -X utf8 scripts/eval/datahyg_apply.py verify
产物：
  data/datahyg_backup_<ts>.json / datahyg_precheck_<ts>.json /
  datahyg_apply_<ts>.json / datahyg_verify_<ts>.json（data/ 在 .gitignore 内，按 rn2 先例 force-add）
退出码：0=该步全部断言通过；1=断言失败/前置不满足；2=Milvus 不可达。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

EDU_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = EDU_ROOT / "data"
EVAL_DIR = EDU_ROOT / "scripts" / "eval"
PROBE_PATH = DATA_DIR / "wnextmilvusflush1_probe.json"
V2_SET_PATH = EVAL_DIR / "data" / "r64v2_eval_set64.json"
V2_BASE_RUN = EVAL_DIR / "data" / "r64v2_runs" / "r64v2_base_run1.json"
GOLDEN_N = 5

from dotenv import load_dotenv  # noqa: E402

if (EDU_ROOT / ".env").is_file():
    load_dotenv(EDU_ROOT / ".env", override=False)

sys.path.insert(0, str(EDU_ROOT))

from app.config import settings  # noqa: E402
from pymilvus import MilvusClient  # noqa: E402

COLL = settings.MILVUS_COLLECTION
DEFAULT_PART = "_default"
EXPECT_DEFAULT_COPIES = 10      # 待删冗余副本数（MILVUSFLUSH1 归因定数）
EXPECT_USER1_COPIES = 10        # 必须存活的 user_1 副本数
EXPECT_ENUM_PRE = 3388          # 整表 reduce 去重枚举（删前后都必须相等）
EXPECT_COUNT_PRE = 3398         # 整表 count(*)（删前）
EXPECT_COUNT_POST = 3388        # 整表 count(*)（删后）
BIG_LIMIT = 16384


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")


def _client() -> MilvusClient:
    return MilvusClient(
        uri=settings.MILVUS_URI,
        token=settings.MILVUS_TOKEN or None,
        timeout=60.0,
    )


def _die(msg: str, code: int = 1) -> None:
    print(f"[DHG1][FATAL] {msg}", file=sys.stderr)
    print(f'[DHG1] {{"ok": false, "step": "{sys.argv[1] if len(sys.argv) > 1 else "?"}", "fatal": {json.dumps(msg, ensure_ascii=False)}}}')
    sys.exit(code)


def wait_visible(client: MilvusClient, expect_count: int, expect_sha: str,
                 timeout_s: int = 90) -> tuple[int, str]:
    """等待 Bounded 一致性窗口收敛到期望口径（禁 flush，轮询只读）。

    MILVUSFLUSH1 语义：count(*) 数物理副本（tombstone 已即时生效于查询侧），
    但 Bounded 快照存在秒级滞后——apply#1 实测删后立即断言会撞陈旧读窗口，
    故删后轮询至 count(*)/枚举 sha 同时收敛（或超时 fail-closed）。"""
    deadline = time.time() + timeout_s
    last = (-1, "")
    while time.time() < deadline:
        last = (count_star(client), sha12(enumerate_ids(client)))
        if last == (expect_count, expect_sha):
            return last
        time.sleep(2)
    return last


def _out(name: str, payload: dict) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = DATA_DIR / f"datahyg_{name}_{_now()}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def _ok(step: str, payload: dict) -> None:
    payload["ok"] = True
    p = _out(step, payload)
    payload["artifact"] = str(p)
    print(f"[DHG1] {json.dumps(payload, ensure_ascii=False)}")
    print(f"[DHG1][artifact] {p}")


def load_pks() -> list[int]:
    """PK 清单唯一定位：MILVUSFLUSH1 探针产物 rowdiff.diff_ids（10 个）。"""
    if not PROBE_PATH.is_file():
        _die(f"探针产物缺失: {PROBE_PATH}")
    probe = json.loads(PROBE_PATH.read_text(encoding="utf-8"))
    pks = sorted(int(d["id"]) for d in probe["rowdiff"]["diff_ids"])
    if len(pks) != EXPECT_DEFAULT_COPIES:
        _die(f"探针 diff_ids 数量 {len(pks)} != 预期 {EXPECT_DEFAULT_COPIES}，清单口径漂移，拒执行")
    return pks


def count_star(client: MilvusClient, partition: str | None = None) -> int:
    flt = "id >= 0" if partition is None else "id >= 0"
    kw = {"partition_names": [partition]} if partition else {}
    rows = client.query(COLL, filter=flt, output_fields=["count(*)"], **kw)
    return int(rows[0]["count(*)"])


def enumerate_ids(client: MilvusClient) -> list[int]:
    rows = client.query(COLL, filter="id >= 0", output_fields=["id"], limit=BIG_LIMIT)
    return sorted(int(r["id"]) for r in rows)


def sha12(ids: list[int]) -> str:
    return hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:12]


def ladder(client: MilvusClient) -> dict:
    """口径阶梯：stats / 整表 count(*) / 整表枚举 / 分区 count(*)。"""
    stats = client.get_collection_stats(COLL)
    parts = {}
    for p in client.list_partitions(COLL):
        parts[p] = count_star(client, p)
    enum_ids = enumerate_ids(client)
    return {
        "stats_row_count": int(stats.get("row_count", -1)),
        "count_star": count_star(client),
        "enumerate": len(enum_ids),
        "enumerate_sha12": sha12(enum_ids),
        "partitions_count_star": parts,
    }


def fetch_copies(client: MilvusClient, pks: list[int], partition: str) -> list[dict]:
    """取某分区内这批 PK 的全字段行（含向量/动态字段）。"""
    idl = ", ".join(str(i) for i in pks)
    return client.query(
        COLL, filter=f"id in [{idl}]", output_fields=["*"],
        partition_names=[partition], timeout=120,
    )


_SCALAR_SKIP = {"id"}  # id 单列，其余全部入快照


def snapshot_rows(client: MilvusClient, pks: list[int]) -> dict:
    """核1 备份：逐分区逐 PK 全字段快照 + 可重插结构自证（字段覆盖/向量维度/PK 对齐）。"""
    desc = client.describe_collection(COLL)
    fields = desc["fields"]
    vec_field = next((f for f in fields if str(f.get("type")) in ("101", "BinaryVector", "FloatVector")
                      or "Vector" in str(f.get("type", ""))), None)
    dim = None
    vec_name = None
    if vec_field:
        vec_name = vec_field["name"]
        dim = int((vec_field.get("params") or {}).get("dim", 0))
    scalar_fields = [f["name"] for f in fields if f["name"] != vec_name]

    per_partition: dict[str, list[dict]] = {}
    for part in client.list_partitions(COLL):
        rows = fetch_copies(client, pks, part)
        if not rows:
            continue
        cleaned = []
        for r in rows:
            item = {"partition": part}
            for k, v in r.items():
                if k in _SCALAR_SKIP and k == "id":
                    item["id"] = int(v)
                elif k == vec_name:
                    item["_vector_field"] = k
                    item["_vector"] = [float(x) for x in v]
                    item["_vector_dim"] = len(v)
                else:
                    item[k] = v
            cleaned.append(item)
        per_partition[part] = cleaned

    # 结构自证：每个 PK 在 _default 与 user_1 各恰好 1 行；标量字段全覆盖；向量维度一致
    problems: list[str] = []
    for pk in pks:
        for part in (DEFAULT_PART, "user_1"):
            rows = [r for r in per_partition.get(part, []) if r["id"] == pk]
            if len(rows) != 1:
                problems.append(f"pk={pk} partition={part} rows={len(rows)}")
    for part, rows in per_partition.items():
        for r in rows:
            missing = [f for f in scalar_fields if f not in r]
            if missing:
                problems.append(f"pk={r['id']} part={part} missing_scalar={missing}")
            if vec_name and r.get("_vector_dim") != dim:
                problems.append(f"pk={r['id']} part={part} dim={r.get('_vector_dim')}!={dim}")

    # 双副本逐标量一致性（副本内容逐字段同 = 删 _default 冗余副本不丢任何信息）
    scalar_diffs: list[dict] = []
    for pk in pks:
        a = next((r for r in per_partition.get(DEFAULT_PART, []) if r["id"] == pk), None)
        b = next((r for r in per_partition.get("user_1", []) if r["id"] == pk), None)
        if a and b:
            diff = {k: [a.get(k), b.get(k)] for k in scalar_fields
                    if k != "id" and a.get(k) != b.get(k)}
            if diff:
                scalar_diffs.append({"id": pk, "diff": diff})

    payload = {
        "meta": {
            "plan": "W-NEXT-DATAHYG-001",
            "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "collection": COLL,
            "milvus_uri": settings.MILVUS_URI,
            "pk_source": str(PROBE_PATH.name) + "#rowdiff.diff_ids",
            "pks": pks,
            "scalar_fields": scalar_fields,
            "vector_field": vec_name,
            "vector_dim": dim,
            "recovery_path": (
                "insert(rows, partition_names=[<backup.partition>]) 原样重插（本脚本永不执行）；"
                "向量/标量均为全精度原值，chunk_id 契约（C-R-CHUNK）不变"
            ),
            "readonly_provenance": "MILVUSFLUSH1 attribution 逐字段对照",
        },
        "structural_problems": problems,
        "default_vs_user1_scalar_diffs": scalar_diffs,
        "rows": [r for part in sorted(per_partition) for r in per_partition[part]],
    }
    if problems:
        _die(f"备份结构自证失败（不满足双副本状态机，中止）: {problems[:8]}")
    if scalar_diffs:
        _die(f"_default 与 user_1 副本标量不一致（删前必须逐字段同）: {scalar_diffs[:3]}")
    return payload


def golden_cases() -> list[dict]:
    """golden 抽检选案：eval64-v2 基线 run 中 hit@5=true 的 per_query 按原 idx 均布取 5。
    只取基线命中案——「删后仍命中」才有判别力。"""
    run = json.loads(V2_BASE_RUN.read_text(encoding="utf-8"))
    hits = [r for r in run["per_query"] if r["hit@5"]]
    if len(hits) < GOLDEN_N:
        _die(f"v2 基线 hit 案不足 {GOLDEN_N}")
    step = len(hits) / GOLDEN_N
    picked = [hits[min(int(i * step), len(hits) - 1)] for i in range(GOLDEN_N)]
    return picked


async def _golden_one(case_run: dict) -> dict:
    from app.auth import UserRole
    from app.chat.retriever import retrieve_three_channel

    bundle = await retrieve_three_channel(
        case_run["query"],
        user_id=1,
        role=UserRole.STUDENT,
        use_hyde=False,          # 契约 params.use_hyde=false
        enable_graph=True,       # 契约 params.enable_graph=true
        top_k=5, final_max_k=5, cutoff_drop_ratio=0.40,
    )
    docs = [{"chunk_id": d.doc_id, "content": d.content, "score": d.score} for d in bundle.docs]
    sys.path.insert(0, str(EVAL_DIR))
    from r20min_run import _match_golden  # 只读复用 W0 双键解析（与 v2 基线同口径）

    fake_case = {"golden": {"chunk_id": case_run["golden_chunk_id"],
                            "doc_sha256": case_run["golden_doc_sha256"]}}
    gt_id, via = _match_golden(fake_case, docs)
    ranks = [i + 1 for i, d in enumerate(docs) if d["chunk_id"] == gt_id]
    return {
        "idx": case_run["idx"],
        "golden_chunk_id": case_run["golden_chunk_id"],
        "gt_resolved_id": gt_id,
        "gt_resolve_via": via,
        "hit@5": bool(ranks and ranks[0] <= 5),
        "rank_of_gt": ranks[0] if ranks else None,
        "final_docs": len(docs),
    }


def golden_check(tag: str) -> list[dict]:
    """golden5 抽检：与 v2 基线同参全链（召回150→rerank20→断崖→top5），串行确定性。"""
    import asyncio

    from app.knowledge.importer.embedder import encode_dense_batch, ensure_jieba_ready

    ensure_jieba_ready()
    _ = encode_dense_batch(["预热"])  # 冷加载移出 retriever wait_for 窗（build_eval_set64 同款）
    cases = golden_cases()
    results = []
    for c in cases:
        results.append(asyncio.run(_golden_one(c)))
    hits = sum(1 for r in results if r["hit@5"])
    if hits != GOLDEN_N:
        _die(f"golden[{tag}] {hits}/{GOLDEN_N} 命中（要求满堂红）: {results}")
    print(f"[DHG1][golden:{tag}] {hits}/{GOLDEN_N} hit")
    return results


# ================================================================
# 子命令
# ================================================================
def cmd_backup() -> None:
    pks = load_pks()
    client = _client()
    if not client.has_collection(COLL):
        _die(f"集合不存在: {COLL}", 2)
    payload = snapshot_rows(client, pks)
    backup_path = DATA_DIR / f"datahyg_backup_{_now()}.json"
    backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    n_rows = len(payload["rows"])
    print(f"[DHG1][backup] rows={n_rows} pks={len(pks)} vec_dim={payload['meta']['vector_dim']} → {backup_path}")
    print(f'[DHG1] {{"ok": true, "step": "backup", "rows": {n_rows}, "artifact": {json.dumps(str(backup_path))}}}')


def latest_artifact(kind: str) -> Path:
    cands = sorted(DATA_DIR.glob(f"datahyg_{kind}_*.json"))
    if not cands:
        _die(f"缺少 datahyg_{kind}_*.json 产物（先跑 backup/precheck）")
    return cands[-1]


def cmd_precheck() -> None:
    """删前基线：口径阶梯 + 逐 PK 归属核验 + golden5 预跑（green 才允许 apply）。"""
    pks = load_pks()
    client = _client()
    lad = ladder(client)
    if lad["enumerate"] != EXPECT_ENUM_PRE or lad["count_star"] != EXPECT_COUNT_PRE:
        _die(f"删前口径漂移: {lad}（期望 count={EXPECT_COUNT_PRE} enum={EXPECT_ENUM_PRE}）——"
             f"环境与 MILVUSFLUSH1 归因基线不一致，拒执行（人工复核）")
    per_pk = []
    idl = ", ".join(str(i) for i in pks)
    for part in client.list_partitions(COLL):
        rows = client.query(COLL, filter=f"id in [{idl}]", output_fields=["id"],
                            partition_names=[part])
        for pk in pks:
            got = sum(1 for r in rows if int(r["id"]) == pk)
            per_pk.append({"id": pk, "partition": part, "copies": got})
    bad = [x for x in per_pk
           if (x["partition"] == DEFAULT_PART and x["copies"] != 1)
           or (x["partition"] == "user_1" and x["copies"] != 1)
           or (x["partition"] not in (DEFAULT_PART, "user_1") and x["copies"] != 0)]
    if bad:
        _die(f"删前逐 PK 归属核验失败: {bad}")
    golden = golden_check("pre")
    _ok("precheck", {"ladder": lad, "per_pk_copies_ok": True, "golden_pre": golden,
                     "golden_n": GOLDEN_N, "pks": pks})


def cmd_apply() -> None:
    """核2+核4：仅删 _default 分区 10 PK；重跑时逐 PK 已删 → no-op 断言 counts 不变。"""
    pks = load_pks()
    client = _client()
    pre = ladder(client)

    # 删前状态机：每个 PK _default=1 / user_1=1（首轮）；重跑（幂等路径）_default=0 / user_1=1
    idl = ", ".join(str(i) for i in pks)
    state = {}
    for part in (DEFAULT_PART, "user_1"):
        rows = client.query(COLL, filter=f"id in [{idl}]", output_fields=["id"],
                            partition_names=[part])
        for pk in pks:
            state.setdefault(pk, {})[part] = sum(1 for r in rows if int(r["id"]) == pk)
    fresh = [pk for pk in pks if state[pk][DEFAULT_PART] == 1]
    already = [pk for pk in pks if state[pk][DEFAULT_PART] == 0]
    invalid = [pk for pk in pks
               if pk not in fresh and pk not in already]
    # 任何 PK user_1 副本缺失 = 红线级异常（删冗余副本不能造成唯一副本消失）
    missing_user1 = [pk for pk in pks if state[pk]["user_1"] != 1]
    if invalid or missing_user1:
        _die(f"删前状态机异常 invalid={invalid} missing_user1={missing_user1}")
    if pre["count_star"] not in (EXPECT_COUNT_PRE, EXPECT_COUNT_POST):
        _die(f"删前 count(*)={pre['count_star']} 不在 {{{EXPECT_COUNT_PRE},{EXPECT_COUNT_POST}}}，环境漂移拒执行")
    if already and pre["count_star"] == EXPECT_COUNT_PRE:
        _die("部分 PK 已删但 count(*) 仍=3398，状态自相矛盾，拒执行")

    mode = "fresh" if not already else "idempotent_noop"
    if fresh:
        # 唯一写原语：partition_name 精确限定 _default；不触其他分区
        res = client.delete(COLL, ids=fresh, partition_name=DEFAULT_PART, timeout=120)
        delete_result = dict(res) if hasattr(res, "items") else {"raw": str(res)}
    else:
        # 幂等证明路径：全 10 PK 已删 → 重发同参 delete（Milvus 对不存在 PK no-op）
        res = client.delete(COLL, ids=pks, partition_name=DEFAULT_PART, timeout=120)
        delete_result = dict(res) if hasattr(res, "items") else {"raw": str(res)}

    post_expect_count = EXPECT_COUNT_POST if mode == "fresh" else pre["count_star"]
    got = wait_visible(client, post_expect_count, pre["enumerate_sha12"])
    post = ladder(client)

    # 删后即时断言
    if mode == "fresh":
        if pre["count_star"] != EXPECT_COUNT_PRE:
            _die(f"fresh 路径删前 count(*)={pre['count_star']} != {EXPECT_COUNT_PRE}")
        if post["count_star"] != EXPECT_COUNT_POST:
            _die(f"删后 count(*)={post['count_star']} != {EXPECT_COUNT_POST}（含 Bounded 收敛等待后）")
        if post["enumerate"] != EXPECT_ENUM_PRE or post["enumerate_sha12"] != pre["enumerate_sha12"]:
            _die(f"删后枚举口径变化: pre_sha={pre['enumerate_sha12']} post={post['enumerate']}/{post['enumerate_sha12']}")
        if post["partitions_count_star"].get(DEFAULT_PART) != \
                pre["partitions_count_star"].get(DEFAULT_PART) - len(fresh):
            _die(f"_default 分区计数变化异常: {pre['partitions_count_star']} → {post['partitions_count_star']}")
        for part in ("user_1", "user_100003", "course_public"):
            if post["partitions_count_star"].get(part) != pre["partitions_count_star"].get(part):
                _die(f"红线：非目标分区 {part} 计数被动 {pre['partitions_count_star']} → {post['partitions_count_star']}")
    else:
        # 幂等 no-op：三次口径全部逐位不变
        for k in ("stats_row_count", "count_star", "enumerate", "enumerate_sha12", "partitions_count_star"):
            if pre[k] != post[k]:
                _die(f"幂等路径 {k} 变化: {pre[k]} → {post[k]}")

    _ok("apply", {
        "mode": mode,
        "deleted_requested": fresh if mode == "fresh" else pks,
        "already_deleted": already,
        "delete_result": delete_result,
        "pre": pre,
        "post": post,
        "visibility_wait": {"got": list(got), "expected": [post_expect_count, pre["enumerate_sha12"]]},
        "expected": {"count_star": EXPECT_COUNT_POST, "enumerate": EXPECT_ENUM_PRE},
    })


def cmd_verify() -> None:
    """核3：①逐 PK 双分区命中 ②整表枚举同集 ③golden5 仍命中。依赖 apply 产物对账。"""
    pks = load_pks()
    client = _client()
    apply_art = json.loads(latest_artifact("apply").read_text(encoding="utf-8"))
    pre_sha = apply_art["pre"]["enumerate_sha12"]

    # ① 10 PK：_default 0 命中 / user_1 恰 1 命中（取回 user_1 行内容证明副本完好）
    idl = ", ".join(str(i) for i in pks)
    per_pk = []
    for part in client.list_partitions(COLL):
        rows = client.query(COLL, filter=f"id in [{idl}]", output_fields=["id", "chunk_id",
                                                                           "tenant_id"],
                            partition_names=[part])
        for pk in pks:
            got = [r for r in rows if int(r["id"]) == pk]
            per_pk.append({"id": pk, "partition": part, "copies": len(got)})
    v_default = [x for x in per_pk if x["partition"] == DEFAULT_PART]
    v_user1 = [x for x in per_pk if x["partition"] == "user_1"]
    others = [x for x in per_pk if x["partition"] not in (DEFAULT_PART, "user_1")]
    ok1 = (all(x["copies"] == 0 for x in v_default)
           and all(x["copies"] == 1 for x in v_user1)
           and all(x["copies"] == 0 for x in others))
    user1_rows = client.query(COLL, filter=f"id in [{idl}]", output_fields=["*"],
                              partition_names=["user_1"], timeout=120)
    intact = len(user1_rows) == EXPECT_USER1_COPIES
    if not (ok1 and intact):
        _die(f"核3-① 失败: _default 清零={ok1} user1={intact} per_pk={per_pk}")

    # ② 整表枚举 3388 + 与删前 sha 逐位一致（reduce 去重集合不变 = 检索零影响）
    lad = ladder(client)
    ok2 = (lad["count_star"] == EXPECT_COUNT_POST and lad["enumerate"] == EXPECT_ENUM_PRE
           and lad["enumerate_sha12"] == pre_sha)
    if not ok2:
        _die(f"核3-② 失败: {lad}（删前 sha={pre_sha}）")

    # ③ golden5 仍命中（eval64-v2 集抽检，与删前 precheck 同案）
    golden = golden_check("post")

    _ok("verify", {
        "check1_default_zero": True,
        "check1_user1_one_each": True,
        "check1_user1_rows_intact": EXPECT_USER1_COPIES,
        "check2_ladder": lad,
        "check2_sha_matches_pre": True,
        "check3_golden": golden,
        "golden_n": GOLDEN_N,
    })


def main() -> int:
    ap = argparse.ArgumentParser(description="W-NEXT-DATAHYG-001 数据卫生执行器")
    ap.add_argument("step", choices=["backup", "precheck", "apply", "verify"])
    args = ap.parse_args()
    t0 = time.time()
    {"backup": cmd_backup, "precheck": cmd_precheck,
     "apply": cmd_apply, "verify": cmd_verify}[args.step]()
    print(f"[DHG1][{args.step}] wall={round(time.time() - t0, 1)}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
