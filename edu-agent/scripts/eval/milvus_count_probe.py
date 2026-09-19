# -*- coding: utf-8 -*-
"""
W-NEXT-MILVUSFLUSH-001 只读探针：edu_knowledge query 枚举 vs count(*) 行差定量归因。

现象（R-M2 移交，commit 1b13547 登记 + 本批基线复现）：
  - client.query(filter="id >= 0", limit=16384) 枚举 = 3388
  - client.query(output_fields=["count(*)"])    = 3398
  - flush 后不消除，3 次探针稳定；隔日（2026-09-19）复测两口径不变
  - 另发现第三口径：get_collection_stats row_count = 3399（stats 比 count(*) 又多 1）

本探针全程只读（禁 flush/compact/load/release/insert/delete/upsert 任何写路径），做五件事：

  1. 口径阶梯（每轮）：num_entities(stats) / count(*)（空 filter 与 id>=0）/
     enumerate(id>=0, ['id']) / enumerate(['id','chunk_id'])（字段 absent 过滤差异检验）/
     Strong 一致性枚举（Bounded 快照滞后检验）/ 分区级三口径 / 段级阶梯
     （persistent 段按 state 求和 vs loaded 段按 state 求和）。
  2. 行级 diff（第 1 轮）：PK=id 为客户端给定 INT64（crc32，值域 < 2^32），
     以「区间 count(*) vs 已枚举 id 计数」二分下降（divide & conquer）定位
     「count 可见而枚举不可见/不可全见」的差异 id 清单（含 multiplicity），
     并对每个差异 id 记录可见性三元组 (count(*)==id, query==id, get==id)。
  3. 差异 id 跨分区归属（C-01 新增）：对每个差异 id 逐分区 count(id==gid) 并取回
     每个持有副本分区的 {chunk_id, tenant_id, created_at, source_file}——
     定性「跨分区重复 PK（upsert 只 tombstone 本分区）vs 真 ghost（count 可见但全不可读）」，
     并以 created_at 给两副本定序（谁旧谁新、谁被枚举返回）。
  4. created_at 测年：分区级 created_at min/max（枚举侧），供 ⑪⑲ 瞬态归因
     （判断写入窗与 check-demo 红窗是否重叠）。
  5. 稳定窗：默认 3 轮重复口径阶梯，输出各轮枚举 id 集合 sha256 前 12 位证明同一性。

假设打分（v2 修正）：v1 草稿（milvus_rowdiff_probe.py，未入库即被本文件取代）把
  「sum_rows - enumerate >= gap」当 growing 段证据，但对拍段级全 sealed（state 4/3、无
  growing）时仍会误判——v2 改为显式签名判据：
    - true_ghost_unreadable       ：存在 count 可见而 query/get 全不可读的 id（真数据问题，上报变更单）
    - cross_partition_duplicate_pk：差异 id 全部 query 可读且 count_eq>query_eq，
                                    且分区枚举和 > 整表枚举、分区 count 和 == 整表 count
                                    （Milvus reduce 按 PK 去重返回最新副本；upsert 只
                                    tombstone 目标分区 → 跨分区同 PK 双副本共存）
    - deleted_rows_pending_compaction：stats−count 差可完全由分区级 stats−count 差解释
    - growing_unsealed_rows       ：段级出现 Growing/Sealed（state 1/2）非 Flushed 段
    - field_absent_filter / bounded_snapshot_lag / concurrent_write_window：同 v1

输出契约（末尾 [WMF1] 单行 JSON）：
  rounds[]: 每轮口径阶梯 + 分区 + 段级 + 分页一致性 + created_at 测年
  rowdiff:  {diff_ids: [{id, count_eq, query_eq, get_eq, copies:[...]}], anomalies, d&c_probes}
  verdict:  {status, count_enumerate_gap, stats_count_gap, dominant_hypothesis, hypothesis_scores}
  meta:     server_version, collection, partitions, consistency_level, generated_at

退出码：0=口径一致（gap=0）；1=口径不一致（gap>0，本批预期态）；2=Milvus 不可达。
用法：
  cd edu-agent && .venv/Scripts/python.exe scripts/eval/milvus_count_probe.py [--rounds 3] [--no-diff]
产物：data/wnextmilvusflush1_probe.json（每次运行覆盖为最新全量结果）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from bisect import bisect_left
from pathlib import Path
from typing import Any

EDU_ROOT = Path(__file__).resolve().parents[2]

# .env 加载兜底（与 veclock_verify.py 同款：绕过 pydantic-settings env_file 相对 cwd 寻址陷阱，
# check-demo 子进程 cwd=仓库根也可跑）
from dotenv import load_dotenv  # noqa: E402

if (EDU_ROOT / ".env").is_file():
    load_dotenv(EDU_ROOT / ".env", override=False)

sys.path.insert(0, str(EDU_ROOT))

from app.config import settings  # noqa: E402
from pymilvus import MilvusClient  # noqa: E402

COLL = settings.MILVUS_COLLECTION
PAGE = 1000          # 守卫交叉检验用分页大小（⑪ 范式）
BIG_LIMIT = 16384    # r03b_verify 同款单页上限（maxQueryResultWindow 默认 16384）
ID_SPACE = 1 << 32   # PK=id 客户端给定 crc32，值域 < 2^32（实测 max 4294555907）
# pymilvus 段状态码：1=Growing 2=Sealed 3=Flushed(loaded 视角 Loaded) 4=Flushed
GROWING_STATES = {"1", "2", "Growing", "Sealed"}


def _client() -> MilvusClient:
    return MilvusClient(
        uri=settings.MILVUS_URI,
        token=settings.MILVUS_TOKEN or None,
        timeout=60.0,
    )


def _count(client: MilvusClient, flt: str = "", partition_names: list[str] | None = None,
           consistency: str | None = None) -> int:
    kwargs: dict[str, Any] = {}
    if consistency:
        kwargs["consistency_level"] = consistency
    res = client.query(
        COLL, filter=flt, output_fields=["count(*)"],
        partition_names=partition_names, timeout=60, **kwargs,
    )
    return int(res[0]["count(*)"])


def _enumerate(client: MilvusClient, flt: str, output_fields: list[str],
               limit: int = BIG_LIMIT, partition_names: list[str] | None = None,
               consistency: str | None = None) -> list[dict]:
    kwargs: dict[str, Any] = {}
    if consistency:
        kwargs["consistency_level"] = consistency
    return client.query(
        COLL, filter=flt, output_fields=output_fields, limit=limit,
        partition_names=partition_names, timeout=120, **kwargs,
    )


def _seg_sums(client: MilvusClient) -> dict[str, Any]:
    """段级阶梯：persistent（datacoord 视角）与 loaded（querycoord 视角）按 state 求和。"""
    out: dict[str, Any] = {}
    for label, fn in (("persistent", client.list_persistent_segments),
                      ("loaded", client.list_loaded_segments)):
        try:
            segs = fn(COLL) or []
        except Exception as exc:  # 段查询失败不应炸整轮
            out[label] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        rows: list[dict] = []
        for s in segs:
            d = s if isinstance(s, dict) else getattr(s, "__dict__", {})
            rows.append({
                "segment_id": d.get("segment_id") or d.get("ID"),
                "state": str(d.get("state") or d.get("State") or ""),
                "num_rows": int(d.get("num_rows") or d.get("NumRows") or 0),
                "partition_id": d.get("partition_id") or d.get("PartitionID"),
            })
        by_state: dict[str, int] = {}
        cnt_by_state: dict[str, int] = {}
        for r in rows:
            by_state[r["state"]] = by_state.get(r["state"], 0) + r["num_rows"]
            cnt_by_state[r["state"]] = cnt_by_state.get(r["state"], 0) + 1
        out[label] = {
            "segments": len(rows),
            "sum_rows": sum(r["num_rows"] for r in rows),
            "rows_by_state": by_state,
            "segments_by_state": cnt_by_state,
            "all_segments": rows,  # 3398 行级别下段数量有限，全量可承受
        }
    return out


def _partition_ladder(client: MilvusClient, parts: list[str]) -> list[dict]:
    out = []
    for p in parts:
        try:
            st = client.get_partition_stats(COLL, p)
            stats_rows = int(st.get("row_count", -1))
        except Exception as exc:
            stats_rows = -1
            stats_err = f"{type(exc).__name__}: {exc}"
        else:
            stats_err = None
        cnt = _count(client, partition_names=[p])
        rows = _enumerate(client, "id >= 0", ["id", "created_at"], partition_names=[p])
        ts = sorted(str(r.get("created_at") or "") for r in rows if r.get("created_at"))
        out.append({
            "partition": p,
            "stats_row_count": stats_rows,
            "stats_err": stats_err,
            "count_star": cnt,
            "enumerate": len(rows),
            "stats_minus_count": (stats_rows - cnt) if stats_rows >= 0 else None,
            "created_at_min": ts[0] if ts else None,
            "created_at_max": ts[-1] if ts else None,
        })
    return out


def _diff_attribution(client: MilvusClient, diff_ids: list[int], parts: list[str]) -> list[dict]:
    """逐差异 id 逐分区归属：count(id==gid) per partition + 取回每个副本的关键字段。"""
    out: list[dict] = []
    for gid in diff_ids:
        entry: dict[str, Any] = {"id": gid, "per_partition": []}
        for p in parts:
            cnt = _count(client, f"id == {gid}", partition_names=[p])
            rows: list[dict] = []
            if cnt > 0:
                rows = client.query(
                    COLL, filter=f"id == {gid}", partition_names=[p],
                    output_fields=["id", "chunk_id", "tenant_id", "source_file", "created_at"],
                    timeout=60,
                )
            if cnt or rows:
                entry["per_partition"].append({"partition": p, "count": cnt, "rows": rows[:3]})
        entry["copies_total"] = sum(x["count"] for x in entry["per_partition"])
        out.append(entry)
    return out


def _rowdiff_divide_conquer(client: MilvusClient, present_ids: list[int]) -> dict[str, Any]:
    """二分定位「count 可见而枚举不可见/不可全见」的差异 id。

    present_ids: 升序去重后的已枚举 id。搜索空间 [0, ID_SPACE)。
    区间判据：count(*) in [lo,hi) > bisect(present_ids) → 深入；== → 剪枝；< → 记 anomaly。
    叶（hi-lo==1）：expected==0 且 count>0 → 差异 id（multiplicity=count）。
    """
    diffs: list[dict] = []
    anomalies: list[dict] = []
    probes = 0

    def dc(lo: int, hi: int) -> None:
        nonlocal probes
        if hi - lo < 1:
            return
        expected = bisect_left(present_ids, hi) - bisect_left(present_ids, lo)
        probes += 1
        cnt = _count(client, f"id >= {lo} and id < {hi}")
        if cnt == expected:
            return
        if cnt < expected:
            anomalies.append({"range": [lo, hi], "count": cnt, "expected": expected})
            return
        if hi - lo == 1:
            # id=lo 在 count 口径的物理行数 > 枚举可见数（整表 reduce 去重视角）
            diffs.append({"id": lo, "count_in_range": cnt})
            return
        mid = (lo + hi) // 2
        dc(lo, mid)
        dc(mid, hi)

    dc(0, ID_SPACE)

    # 可见性三元组（count / query / get 三口径逐 id）
    for g in diffs:
        gid = g["id"]
        cnt_eq = _count(client, f"id == {gid}")
        rows_eq = client.query(COLL, filter=f"id == {gid}", output_fields=["id", "chunk_id"], timeout=60)
        gets = client.get(COLL, ids=[gid], output_fields=["id", "chunk_id"], timeout=60)
        g["count_eq"] = cnt_eq
        g["query_eq"] = len(rows_eq)
        g["get_eq"] = len(gets)
        g["query_rows"] = rows_eq[:2]
    return {"diff_ids": diffs, "anomalies": anomalies, "dc_probes": probes}


def _one_round(client: MilvusClient, round_no: int, parts: list[str]) -> dict[str, Any]:
    r: dict[str, Any] = {"round": round_no, "epoch": time.time()}
    r["stats_row_count"] = int(client.get_collection_stats(COLL).get("row_count", -1))
    r["count_star_empty"] = _count(client, "")
    r["count_star_id_ge0"] = _count(client, "id >= 0")
    rows = _enumerate(client, "id >= 0", ["id"])
    ids = sorted(int(x["id"]) for x in rows)
    r["enumerate_id_ge0"] = len(ids)
    r["id_min"] = ids[0] if ids else None
    r["id_max"] = ids[-1] if ids else None
    r["ids_sha12"] = hashlib.sha256(json.dumps(ids).encode()).hexdigest()[:12]
    # 字段 absent 过滤差异检验：多要一个 chunk_id 是否仍同数量
    rows2 = _enumerate(client, "id >= 0", ["id", "chunk_id"])
    r["enumerate_with_chunk_id"] = len(rows2)
    # Strong 一致性检验（Bounded 快照滞后排除/证实）
    try:
        rows_strong = _enumerate(client, "id >= 0", ["id"], consistency="Strong")
        r["enumerate_strong"] = len(rows_strong)
        r["strong_ids_sha12"] = hashlib.sha256(
            json.dumps(sorted(int(x["id"]) for x in rows_strong)).encode()).hexdigest()[:12]
    except Exception as exc:
        r["enumerate_strong"] = None
        r["strong_err"] = f"{type(exc).__name__}: {exc}"
    # 守卫 ⑪ offset 分页范式交叉检验（page=1000 多页拼接 vs 单页）
    walked: list[int] = []
    offset = 0
    while True:
        part = client.query(COLL, filter="id >= 0", output_fields=["id"], limit=PAGE,
                            offset=offset, timeout=120)
        if not part:
            break
        walked.extend(int(x["id"]) for x in part)
        offset += len(part)
        if len(part) < PAGE:
            break
    r["paginate_walk_total"] = len(walked)
    r["paginate_same_set"] = sorted(walked) == ids
    # 分区级三口径 + stats−count 落差定位 + created_at 测年
    r["partitions"] = _partition_ladder(client, parts)
    r["partitions_count_sum"] = sum(x["count_star"] for x in r["partitions"])
    r["partitions_enumerate_sum"] = sum(x["enumerate"] for x in r["partitions"])
    r["partitions_stats_minus_count_sum"] = sum(
        x["stats_minus_count"] or 0 for x in r["partitions"])
    # 段级阶梯
    r["segments"] = _seg_sums(client)
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description="W-NEXT-MILVUSFLUSH-001 只读行差探针（禁写 Milvus）")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--no-diff", action="store_true", help="跳过二分 diff 定位（只做口径阶梯）")
    ap.add_argument("--out", default=str(EDU_ROOT / "data" / "wnextmilvusflush1_probe.json"))
    args = ap.parse_args()

    try:
        client = _client()
        server = client.get_server_version()
    except Exception as exc:
        print("[WMF1] " + json.dumps({
            "status": "UNREACHABLE",
            "error": f"{type(exc).__name__}: {exc}",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False))
        return 2

    desc = client.describe_collection(COLL)
    parts = client.list_partitions(COLL)
    rounds: list[dict] = []
    rowdiff: dict[str, Any] | None = None
    attribution: list[dict] | None = None
    for i in range(1, max(1, args.rounds) + 1):
        t0 = time.time()
        rd = _one_round(client, i, parts)
        rd["elapsed_s"] = round(time.time() - t0, 2)
        rounds.append(rd)
        if i == 1 and not args.no_diff:
            # 重取一次轻量枚举，保证与 diff 定位同快照附近
            ids = sorted(int(x["id"]) for x in _enumerate(client, "id >= 0", ["id"]))
            t1 = time.time()
            rowdiff = _rowdiff_divide_conquer(client, ids)
            rowdiff["elapsed_s"] = round(time.time() - t1, 2)
            rowdiff["present_total"] = len(ids)
            if rowdiff["diff_ids"]:
                attribution = _diff_attribution(client, [g["id"] for g in rowdiff["diff_ids"]], parts)
                rowdiff["attribution"] = attribution

    last = rounds[-1]
    gap = last["count_star_id_ge0"] - last["enumerate_id_ge0"]
    stats_gap = last["stats_row_count"] - last["count_star_id_ge0"]

    # ---- 假设打分 v2：显式签名判据（v1 草稿 growing 判据已在段级 sealed 数据上证伪）----
    hs: dict[str, bool] = {}
    ghosts = (rowdiff or {}).get("diff_ids") or []
    segs = last.get("segments", {})
    pers_states = set(((segs.get("persistent") or {}).get("rows_by_state") or {}).keys())
    load_states = set(((segs.get("loaded") or {}).get("rows_by_state") or {}).keys())

    hs["true_ghost_unreadable"] = bool(
        gap > 0 and ghosts
        and any(g["query_eq"] == 0 and g["get_eq"] == 0 for g in ghosts)
    )
    hs["cross_partition_duplicate_pk"] = bool(
        gap > 0 and ghosts
        and all(g["query_eq"] >= 1 and g["count_eq"] > g["query_eq"] for g in ghosts)
        and last["partitions_count_sum"] == last["count_star_id_ge0"]
        and last["partitions_enumerate_sum"] == last["count_star_id_ge0"]
        and last["partitions_enumerate_sum"] > last["enumerate_id_ge0"]
    )
    hs["deleted_rows_pending_compaction"] = bool(
        stats_gap > 0
        and last["partitions_stats_minus_count_sum"] == stats_gap
        and not hs["true_ghost_unreadable"]
    )
    hs["growing_unsealed_rows"] = bool(pers_states & GROWING_STATES or load_states & GROWING_STATES)
    hs["field_absent_filter"] = bool(last["enumerate_with_chunk_id"] != last["enumerate_id_ge0"])
    hs["bounded_snapshot_lag"] = bool(
        last.get("enumerate_strong") is not None
        and last["enumerate_strong"] != last["enumerate_id_ge0"]
    )
    hs["concurrent_write_window"] = bool(
        len({r["count_star_id_ge0"] for r in rounds}) > 1
        or len({r["enumerate_id_ge0"] for r in rounds}) > 1
        or len({r["stats_row_count"] for r in rounds}) > 1
    )

    hypothesis = "unknown"
    if hs["true_ghost_unreadable"]:
        hypothesis = "true_ghost_unreadable（count 可见而 query/get 全不可读——真数据问题，应上报变更单）"
    elif hs["cross_partition_duplicate_pk"]:
        hypothesis = ("cross_partition_duplicate_pk（同 PK 跨分区双副本：整表枚举按 PK reduce 去重返回最新副本，"
                      "count(*) 数物理副本；upsert 只 tombstone 目标分区故旧副本存活；flush 不消除——正常语义差）")
    elif stats_gap > 0 and gap == 0:
        hypothesis = "deleted_rows_pending_compaction（stats num_entities 含已删行，待 compaction 回收）"
    elif hs["growing_unsealed_rows"]:
        hypothesis = "growing_unsealed_rows（存在未 flush 段）"
    elif hs["field_absent_filter"]:
        hypothesis = "field_absent_filter（输出字段 absent 行被枚举过滤）"
    elif hs["bounded_snapshot_lag"]:
        hypothesis = "bounded_snapshot_lag（Bounded 快照滞后，Strong 口径不同）"
    elif hs["concurrent_write_window"]:
        hypothesis = "concurrent_write_window（并发写入窗口，轮间数字漂移）"

    verdict = {
        "status": "CONSISTENT" if gap == 0 and stats_gap == 0 else "INCONSISTENT",
        "count_enumerate_gap": gap,
        "stats_count_gap": stats_gap,
        "hypothesis_scores": hs,
        "dominant_hypothesis": hypothesis,
    }

    payload = {
        "meta": {
            "server_version": server,
            "collection": COLL,
            "partitions": parts,
            "consistency_level": desc.get("consistency_level_name") or str(desc.get("consistency_level")),
            "auto_id": desc.get("auto_id"),
            "enable_dynamic_field": desc.get("enable_dynamic_field"),
            "num_shards": desc.get("num_shards"),
            "milvus_uri": settings.MILVUS_URI,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "readonly_guarantee": "仅 describe/list/stats/query/get，无 flush/compact/load/release/insert/delete/upsert",
        },
        "rounds": rounds,
        "rowdiff": rowdiff,
        "verdict": verdict,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("[WMF1] " + json.dumps({
        "status": verdict["status"],
        "count_star": last["count_star_id_ge0"],
        "enumerate": last["enumerate_id_ge0"],
        "stats_row_count": last["stats_row_count"],
        "gap": gap,
        "stats_gap": stats_gap,
        "rounds": len(rounds),
        "round_numbers_stable": len({(r["count_star_id_ge0"], r["enumerate_id_ge0"], r["stats_row_count"]) for r in rounds}) == 1,
        "diff_total": len(ghosts),
        "diff_ids": [g["id"] for g in ghosts],
        "diff_triples": [(g["id"], g["count_eq"], g["query_eq"], g["get_eq"]) for g in ghosts][:12],
        "attribution_partitions": [
            {"id": a["id"], "copies": {x["partition"]: x["count"] for x in a["per_partition"]}}
            for a in (attribution or [])
        ][:12],
        "paginate_same_set": last["paginate_same_set"],
        "strong": last.get("enumerate_strong"),
        "partition_stats_minus_count_sum": last["partitions_stats_minus_count_sum"],
        "dominant_hypothesis": hypothesis,
        "artifact": str(out_path),
    }, ensure_ascii=False))

    return 0 if verdict["status"] == "CONSISTENT" else 1


if __name__ == "__main__":
    sys.exit(main())
