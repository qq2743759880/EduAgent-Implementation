# -*- coding: utf-8 -*-
"""
R22 · W-NEXT-R22-001 去圆环评估集构造 + 阈值头寸测量（承接 R20-min 双环验收 Crit-1/Crit-3）

批判承接（.opencode/plans/critique-backlog-tracker.md §R20-min 验收）：
  - Crit-1 golden 圆环自证：eval_set32 的 query 从 golden chunk 自身提取（_extract_query
    取自同一块），关键词重叠保底 → 命中全 rank1、mrr==hit_rate 退化分布，基线含方法论
    自证成分。本脚本去圆环：golden query **不得**从 golden chunk 自身提取。
  - Crit-3 阈值头寸退化：hit_rate@5=0.9688 贴天花板（阈值 0.9488=基线-0.02），无法区分
    真回归与测量噪声。本脚本在新集上量头寸：分布 + 95% CI；贴 1.0 则出「区分度不足」
    结论 + 分级指标建议（rank2/3 命中 / mrr@10 / distinct-doc 覆盖）。

两种独立 golden 来源（independence 溯源字段，每条必带）：
  manual —— chat_message 真实用户问句（role=user，规则改写去寒暄，禁 LLM），
            golden = 同会话紧随 assistant 回复 rag_docs_json 中生产实际投喂的 chunk
            （RetrievedDoc.doc_id == Milvus chunk_id，retriever.py:266）。
            注意：该 golden 是「生产链自身产出的一致性证据」，衡量链稳定性偏乐观，
            见报告 P0 自批判 S-2。
  cross  —— 跨 chunk 互证：query 从题库 question chunk 提取题干（复用
            build_eval_set32._extract_query，只读复用不改其行为），
            golden = 同域课程 course_module 块（73/73 bank→series 归一化对齐，
            规则=标题+关键词行词重叠+次优边际，纯字符串规则，不经检索链、不经 LLM）。
            golden 与 source 必为不同 chunk（类型亦不同），无子串保底。

头寸测量（--mode measure）：R20-min 测量仪范式（r20min_run.py 同口径，只读复用其
_match_golden 双键解析），实时端到端 retrieve_three_channel 全链（召回150→rerank20→
断崖→top5），0-LLM。另跑分级窗口（top_k=final_max_k=10，参数在产出中单独披露）
供 rank2/3 命中 / mrr@10 / distinct-doc 覆盖分级指标。
不落门：本脚本一切数字只入 data/ 产物与报告，禁改 contracts/rag-baseline-eval32.json
冻结值与 check-demo/veclock 门槛。

GPU 争用降级：EMBED_BACKEND=cpu 进程级环境变量启动本脚本即可（同 BGE-M3 双路径共用，
查询/库内 embedding 仍同模型），检索语义不变仅速度变化。

用法（edu-agent/ 下）：
  .venv/Scripts/python.exe scripts/eval/build_eval_set64.py --mode build
  .venv/Scripts/python.exe scripts/eval/build_eval_set64.py --mode spotcheck
  .venv/Scripts/python.exe scripts/eval/build_eval_set64.py --mode measure --tag r22_base_run1
  .venv/Scripts/python.exe scripts/eval/build_eval_set64.py --mode measure --tag r22_base_run2
  .venv/Scripts/python.exe scripts/eval/build_eval_set64.py --mode measure --tag r22_graded10 --graded

产物：
  scripts/eval/data/r22_eval_set64.json        64 条去圆环评估集（independence 溯源+双键 golden）
  scripts/eval/data/r22_runs/<tag>.json        逐次测量 per_query 全量
  scripts/eval/data/r22_position_measure.json  头寸汇总（分布+95% CI+分级指标+结论）
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_DIR = os.path.join(BASE_DIR, "scripts", "eval")
DATA_DIR = os.path.join(EVAL_DIR, "data")
RUNS_DIR = os.path.join(DATA_DIR, "r22_runs")
OUT_SET_PATH = os.path.join(DATA_DIR, "r22_eval_set64.json")
POSITION_PATH = os.path.join(DATA_DIR, "r22_position_measure.json")
sys.path.insert(0, BASE_DIR)  # app.* 包导入（与 build_eval_set32/r20min_run 同口径）

SEED = 20260918
TOP_K_EVAL = 5
GRADED_K = 10
BOOTSTRAP_B = 10000

# 生产参数：与冻结契约 contracts/rag-baseline-eval32.json params 逐字段一致
#（r20min_run.PARAMS 同源：chat 正产默认 + W0 钉死项）
PARAMS = {
    "recall_topk": 150,
    "rerank_topk": 20,
    "final_max_k": 5,
    "cutoff_drop_ratio": 0.40,
    "use_hyde": False,
    "enable_graph": True,
    "nprobe": 10,
    "rrf_k": 60,
    "embed_backend": "cuda",   # 运行时按 settings.EMBED_BACKEND 实测值覆盖记录
    "rerank_sidecar": "http://127.0.0.1:8601",
    "role": "student",
}

# chat_message 真采 SQL（与 r20b 口径同源：role=user/长度≥10/会话 yn=1），
# 配对在 python 侧按 (session_id, created_at, id) 相对序完成（确定性：SQL 相对序+种子内洗牌）
CHAT_SQL = (
    "SELECT m.session_id, m.role, m.content, m.created_at, m.id, m.message_id, "
    "m.rag_docs_json, m.rag_error, m.rag_final_count "
    "FROM chat_message m JOIN chat_session s ON s.session_id = m.session_id "
    "WHERE s.yn = 1 ORDER BY m.session_id, m.created_at, m.id"
)

INDEPENDENCE_VALUES = ("manual", "cross")
QUERY_MIN_LEN = 6
QUERY_MAX_LEN = 120
GOLDEN_CAP = 2          # 同一 golden chunk 最多出现在 2 条样本（防集中偏置）
SESSION_CAP = 3         # 同一会话最多采 3 条（r20b 同口径）


# ============================================================
# 纯逻辑层（模块级，可离线单测；Milvus/MySQL/app.* 一律懒加载）
# ============================================================

def sha256_utf8(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def norm_series_code(series_code: str) -> str:
    """课程系列编码归一化：去 _advanced/_practice/_foundation 等档位后缀。"""
    s = str(series_code or "")
    for suf in ("_advanced", "_practice", "_foundation", "_improve", "_bootcamp", "_pro"):
        if s.endswith(suf):
            return s[: -len(suf)]
    return s


def bank_to_series(bank_code: str) -> str:
    """题库编码 → 同域课程系列核心名：去 _bank 后缀。实测 73/73 bank 可对齐 series。"""
    b = str(bank_code or "")
    return b[:-5] if b.endswith("_bank") else b


_PLEASANTRY_HEAD = re.compile(
    r"^(老师|您好|你好|hi|hello|嗨|请问|问下|问一下|帮我|麻烦|我想问|我想问下|我想咨询|"
    r"请教|想问|问个问题|我想知道)[，,：:、\s！!？?]*",
    re.IGNORECASE,
)
_PLEASANTRY_TAIL = re.compile(r"(谢谢|感谢|thanks|thank you|辛苦了|了)[!！。.～~\s]*$", re.IGNORECASE)


def rewrite_query(text: str) -> str:
    """规则改写 chat 真实问句：去寒暄头尾 + 空白归一（纯 regex，禁 LLM；确定性）。"""
    q = re.sub(r"\s+", " ", str(text or "")).strip()
    prev = None
    while prev != q:
        prev = q
        q = _PLEASANTRY_HEAD.sub("", q).strip()
        q = _PLEASANTRY_TAIL.sub("", q).strip()
    return q


def extract_key_terms(text: str, topk: int = 8) -> list[str]:
    """jieba 关键词（确定性 topK），长度≥2。纯本地分词，非 LLM。"""
    import jieba.analyse

    return [t for t in jieba.analyse.extract_tags(str(text or ""), topK=topk) if len(t) >= 2]


def make_golden(chunk_id: str, content: str) -> dict:
    """双键 golden：chunk_id + doc_sha256(sha256(content utf-8))，与冻结契约同口径。"""
    return {"chunk_id": str(chunk_id or ""), "doc_sha256": sha256_utf8(content)}


def validate_case(case: dict, *, source_content: str | None = None) -> list[str]:
    """反圆环 + 结构校验。返回违规列表（空=通过）。

    硬性不变量（Crit-1 去圆环）：
      V1 independence 必填且 ∈ {manual, cross}
      V2 golden 双键齐全且 doc_sha256 与 gt_content 一致
      V3 cross：golden chunk ≠ source chunk（id 与内容 sha 均不同），
         query 不是 golden 内容的子串（禁自匹配保底）
      V4 manual：溯源字段齐全（source_message_id/cited_rank）
      V5 query 长度在 [QUERY_MIN_LEN, QUERY_MAX_LEN]
    """
    errs: list[str] = []
    indep = case.get("independence")
    if indep not in INDEPENDENCE_VALUES:
        errs.append(f"V1 independence 非法: {indep!r}")
    golden = case.get("golden") or {}
    gt = str(case.get("gt_content") or "")
    if not golden.get("chunk_id"):
        errs.append("V2 golden.chunk_id 缺失")
    if not golden.get("doc_sha256"):
        errs.append("V2 golden.doc_sha256 缺失")
    elif golden["doc_sha256"] != sha256_utf8(gt):
        errs.append("V2 doc_sha256 与 gt_content 不一致（双键失配）")
    q = str(case.get("query") or "")
    if not (QUERY_MIN_LEN <= len(q) <= QUERY_MAX_LEN):
        errs.append(f"V5 query 长度越界: {len(q)}")
    if indep == "cross":
        src_id = str(case.get("source_chunk_id") or "")
        if not src_id:
            errs.append("V3 cross 缺 source_chunk_id")
        elif src_id == golden.get("chunk_id"):
            errs.append("V3 cross golden 与 source 同 chunk（圆环）")
        if source_content is not None and golden.get("doc_sha256") == sha256_utf8(source_content):
            errs.append("V3 cross golden 内容与 source 内容相同（圆环）")
        if gt and q and q in gt:
            errs.append("V3 cross query 是 golden 内容子串（自匹配保底）")
        if not case.get("matched_terms"):
            errs.append("V3 cross 缺 matched_terms 互证证据")
    if indep == "manual":
        if not case.get("source_message_id"):
            errs.append("V4 manual 缺 source_message_id 溯源")
        if case.get("cited_rank") is None:
            errs.append("V4 manual 缺 cited_rank 溯源")
    return errs


def dedup_and_cap(
    rows: list[dict],
    *,
    total: int,
    query_key=lambda r: r["query_key"],
    cap_key=lambda r: r["cap_key"],
    session_key=lambda r: r.get("session_key"),
) -> tuple[list[dict], dict]:
    """确定性去重（query 归一键）+ golden 配额 + 会话配额。返回 (选中, 统计)。"""
    seen_q: set[str] = set()
    cap_cnt: dict[str, int] = {}
    sess_cnt: dict[str, int] = {}
    picked: list[dict] = []
    stats = {"dup_query_dropped": 0, "golden_cap_dropped": 0, "session_cap_dropped": 0}
    for r in rows:
        if len(picked) >= total:
            break
        qk = query_key(r)
        if qk in seen_q:
            stats["dup_query_dropped"] += 1
            continue
        ck = cap_key(r)
        if cap_cnt.get(ck, 0) >= GOLDEN_CAP:
            stats["golden_cap_dropped"] += 1
            continue
        sk = session_key(r)
        if sk is not None and sess_cnt.get(sk, 0) >= SESSION_CAP:
            stats["session_cap_dropped"] += 1
            continue
        seen_q.add(qk)
        cap_cnt[ck] = cap_cnt.get(ck, 0) + 1
        if sk is not None:
            sess_cnt[sk] = sess_cnt.get(sk, 0) + 1
        picked.append(r)
    return picked, stats


def match_module(
    q_terms: list[str],
    modules: list[dict],
) -> tuple[dict | None, list[str], str]:
    """跨 chunk 互证匹配：题库关键词 ∩ 课程模块(标题+关键词行) 词重叠 + 次优边际。

    返回 (best_module|None, matched_terms, note)。纯字符串规则，不经检索链不经 LLM。
    拒绝条件：重叠不足（<2 词，或 1 词但长度<4）、无严格边际（并列最优）。
    """
    scored: list[tuple[int, str, dict]] = []
    for m in modules:
        text = str(m.get("_match_text") or "")
        hit = sorted({t for t in q_terms if t in text}, key=lambda t: (-len(t), t))
        scored.append((len(hit), "|".join(hit), m))
    scored.sort(key=lambda x: (-x[0], x[1], str(x[2].get("chunk_id"))))
    if not scored or scored[0][0] == 0:
        return None, [], "no_overlap"
    best_n, best_terms_key, best = scored[0]
    best_terms = [t for t in best_terms_key.split("|") if t]
    second_n = scored[1][0] if len(scored) > 1 else 0
    if best_n >= 2 and best_n > second_n:
        return best, best_terms, f"overlap={best_n}_margin={best_n - second_n}"
    if best_n == 1 and len(best_terms) and len(best_terms[0]) >= 4 and best_n > second_n:
        return best, best_terms, f"single_long_term={best_terms[0]}"
    if best_n >= 2 and best_n == second_n:
        return None, best_terms, "tied_margin"
    return None, best_terms, "insufficient_overlap"


# ============================================================
# 统计层：95% CI（Wilson / bootstrap）+ 分布 + 退化判别
# ============================================================

def wilson_ci(p: float, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """二项比例 Wilson 95% 置信区间（n=0 时退化为 [0,1]）。"""
    if n <= 0:
        return (0.0, 1.0)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def bootstrap_ci(values: list[float], seed: int = SEED, b: int = BOOTSTRAP_B) -> tuple[float, float]:
    """bootstrap 百分位 95% CI（固定 seed 确定性）。"""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(b))
    return (round(means[int(0.025 * b)], 4), round(means[min(int(0.975 * b), b - 1)], 4))


def rank_distribution(ranks: list[int | None], k: int) -> dict:
    hist = {f"rank{i}": sum(1 for r in ranks if r == i) for i in range(1, k + 1)}
    hist["miss"] = sum(1 for r in ranks if r is None or r > k)
    return hist


def degeneracy_check(hit_rate: float, mrr: float, ranks: list[int | None]) -> dict:
    """退化分布判别（Crit-1 的形态学指标）：mrr==hit_rate 且命中全 rank1 = 圆环自证形态。"""
    hits = [r for r in ranks if r is not None and r <= TOP_K_EVAL]
    all_rank1 = bool(hits) and all(r == 1 for r in hits)
    return {
        "mrr_equals_hit_rate": abs(mrr - hit_rate) < 1e-9,
        "all_hits_rank1": all_rank1,
        "verdict": ("degenerate(圆环自证形态)" if (abs(mrr - hit_rate) < 1e-9 and all_rank1)
                    else "informative(有区分度)"),
    }


# ============================================================
# 构建：manual（chat 真问句）+ cross（题库↔课程模块互证）
# ============================================================

def _milvus_content_map(client, collection: str, chunk_ids: list[str]) -> dict[str, str]:
    """按 chunk_id 批量取当前内容（小批+引号包裹，避开 client.get 对带冒号 id 的裸 IN 表达式缺陷）。"""
    out: dict[str, str] = {}
    uniq = [cid for cid in dict.fromkeys(chunk_ids) if cid]
    step = 20
    for i in range(0, len(uniq), step):
        batch = uniq[i:i + step]
        quoted = ", ".join(f'"{cid}"' for cid in batch)
        try:
            rows = client.query(collection, filter=f"chunk_id in [{quoted}]",
                                output_fields=["chunk_id", "content"])
        except Exception as exc:  # noqa: BLE001  单批失败不静默：升格硬错，防 golden 内容缺查
            raise SystemExit(f"[build] Milvus content 查询失败 (batch {i // step}): {exc}")
        for r in rows or []:
            out[str(r.get("chunk_id") or "")] = str(r.get("content") or "")
    return out


def _build_manual_rows(pairs: list[dict], content_map: dict[str, str]) -> tuple[list[dict], dict]:
    """chat 配对 → 候选 manual 行（含规则改写 + golden 有效性过滤），附产出统计。"""
    rows: list[dict] = []
    stats = {"pairs_total": len(pairs), "rewrite_empty": 0, "no_cited_docs": 0,
             "golden_not_in_milvus": 0, "golden_content_drift": 0,
             "no_term_overlap_with_golden": 0}
    for p in pairs:
        q = rewrite_query(p["user_content"])
        if not (QUERY_MIN_LEN <= len(q) <= QUERY_MAX_LEN):
            stats["rewrite_empty"] += 1
            continue
        docs = p.get("rag_docs") or []
        if not docs:
            stats["no_cited_docs"] += 1
            continue
        q_terms = set(extract_key_terms(q, topk=10))
        golden = None
        for rank_i, d in enumerate(docs, start=1):
            did = str(d.get("doc_id") or "")
            if not did:
                continue
            cur = content_map.get(did)
            if cur is None:
                stats["golden_not_in_milvus"] += 1
                continue
            if sha256_utf8(cur) != sha256_utf8(str(d.get("content") or "")):
                stats["golden_content_drift"] += 1   # 语料再入库漂移：golden 引用已失效
                continue
            ov = q_terms & set(extract_key_terms(cur, topk=30))
            # 相关性貌似性过滤（防生产退化检索当 golden）。只认 ≥3 字强特征词重叠：
            # 抽检实证 {说明,完成}/{介绍} 等 2 字弱功能词重叠会放进无关 golden（M1/M3 坏例）
            strong = [t for t in ov if len(t) >= 3]
            if q_terms and not strong:
                stats["no_term_overlap_with_golden"] += 1
                continue
            golden = {"doc": d, "rank": rank_i, "content": cur, "overlap_terms": sorted(strong)}
            break
        if golden is None:
            continue
        rows.append({
            "query": q,
            "query_key": re.sub(r"[\s\W_]+", "", q.lower()),
            "cap_key": golden["doc"].get("doc_id"),
            "session_key": p.get("session_id"),
            "independence": "manual",
            "source_message_id": p.get("assistant_message_id"),
            "cited_rank": golden["rank"],
            "golden_chunk_id": golden["doc"].get("doc_id"),
            "golden_content": golden["content"],
            "golden_overlap_terms": golden.get("overlap_terms", []),
            "rag_final_count": p.get("rag_final_count"),
        })
    return rows, stats


def _build_cross_rows(questions: list[dict], modules_by_series: dict[str, list[dict]],
                      content_map: dict[str, str]) -> tuple[list[dict], dict]:
    """题库 question → 同域 course_module 互证候选行。"""
    sys.path.insert(0, EVAL_DIR)
    from build_eval_set32 import _extract_query  # 只读复用既有题干提取规则（不改其行为）

    rows: list[dict] = []
    stats = {"questions_total": len(questions), "bank_no_series_modules": 0,
             "stem_empty": 0, "match_rejected": 0}
    for q_row in questions:
        series = norm_series_code(bank_to_series(str(q_row.get("question_bank_code") or "")))
        modules = modules_by_series.get(series) or []
        if not modules:
            stats["bank_no_series_modules"] += 1
            continue
        content = str(q_row.get("content") or "")
        stem = _extract_query(content)
        if not stem or len(stem) < QUERY_MIN_LEN:
            stats["stem_empty"] += 1
            continue
        # 互证词源：题干 + 解析（答案区不参与，避免把选项词当关键词）
        analysis = content.split("解析：", 1)[1] if "解析：" in content else ""
        q_terms = extract_key_terms(f"{stem} {analysis}", topk=12)
        best, matched, note = match_module(q_terms, modules)
        if best is None:
            stats["match_rejected"] += 1
            continue
        gid = str(best.get("chunk_id") or "")
        gcontent = content_map.get(gid, str(best.get("content") or ""))
        rows.append({
            "query": stem,
            "query_key": re.sub(r"[\s\W_]+", "", stem.lower()),
            "cap_key": gid,
            "session_key": None,
            "independence": "cross",
            "source_chunk_id": str(q_row.get("chunk_id") or ""),
            "source_bank": str(q_row.get("question_bank_code") or ""),
            "series_code": series,
            "golden_chunk_id": gid,
            "golden_content": gcontent,
            "matched_terms": matched,
            "match_note": note,
        })
    return rows, stats


async def _fetch_chat_pairs() -> list[dict]:
    import app.database as db

    await db.init_mysql()
    rows = await db.fetch_all(CHAT_SQL)
    pairs: list[dict] = []
    prev_user = None
    for r in rows:
        d = dict(r)
        if d["role"] == "user":
            prev_user = d
        elif (d["role"] == "assistant" and prev_user is not None
              and prev_user["session_id"] == d["session_id"]):
            if (prev_user.get("content") and len(str(prev_user["content"]).strip()) >= 10
                    and d.get("rag_docs_json") and not d.get("rag_error")):
                try:
                    docs = json.loads(d["rag_docs_json"])
                except (TypeError, ValueError):
                    docs = []
                if docs:
                    pairs.append({
                        "session_id": str(prev_user["session_id"]),
                        "user_content": str(prev_user["content"]),
                        "assistant_message_id": str(d.get("message_id") or d.get("id") or ""),
                        "rag_docs": docs,
                        "rag_final_count": d.get("rag_final_count"),
                    })
            prev_user = None
    return pairs


async def build(limit: int = 64, manual_n: int = 40) -> None:
    from app.config import settings

    os.makedirs(DATA_DIR, exist_ok=True)
    t0 = time.perf_counter()

    # ---- manual 侧数据 ----
    pairs = await _fetch_chat_pairs()
    rng = random.Random(SEED)
    rng.shuffle(pairs)  # 种子内洗牌：新插入会话不改已选集（r20b 同口径）
    cited_ids: list[str] = []
    for p in pairs:
        for d in (p.get("rag_docs") or [])[:3]:
            did = str(d.get("doc_id") or "")
            if did:
                cited_ids.append(did)

    # ---- Milvus 内容现状（golden 双键以当前库内容为准）----
    from app.knowledge.importer.loader import COLLECTION_NAME, get_milvus_client

    client = get_milvus_client()
    assert COLLECTION_NAME in [str(c) for c in client.list_collections()], "Milvus 缺 edu_knowledge"
    content_map = _milvus_content_map(client, COLLECTION_NAME, cited_ids)

    questions = client.query(
        COLLECTION_NAME,
        filter='content_type == "question"',
        output_fields=["chunk_id", "question_bank_code", "content"],
        limit=8000,
    )
    module_rows = client.query(
        COLLECTION_NAME,
        filter='content_type == "course_module"',
        output_fields=["chunk_id", "series_code", "content"],
        limit=8000,
    )
    modules_by_series: dict[str, list[dict]] = {}
    for m in module_rows:
        sc = str(m.get("series_code") or "")
        if not sc:
            continue
        content = str(m.get("content") or "")
        title = content.split("课程模块：", 1)[1].split("\n", 1)[0] if "课程模块：" in content else ""
        kw_line = content.split("关键词：", 1)[1].split("\n", 1)[0] if "关键词：" in content else ""
        m["_match_text"] = f"{title} {kw_line}"
        modules_by_series.setdefault(norm_series_code(sc), []).append(m)
    module_ids = [str(m.get("chunk_id") or "") for m in module_rows if m.get("chunk_id")]
    content_map.update(_milvus_content_map(client, COLLECTION_NAME, module_ids))

    # ---- 两路候选 ----
    manual_rows, manual_stats = _build_manual_rows(pairs, content_map)
    cross_rows, cross_stats = _build_cross_rows(questions, modules_by_series, content_map)
    print(f"[build] manual 候选 {len(manual_rows)} / cross 候选 {len(cross_rows)}")

    picked_manual, m_dedup = dedup_and_cap(manual_rows, total=manual_n)
    # manual 独立 query 池不足时不静默凑数也不虚增重复样本（重复 query 会簇集偏置 CI），
    # 不足额显式回补 cross（同为任务书认可的独立 golden 来源），缺口留痕入 meta。
    manual_shortfall = manual_n - len(picked_manual)
    if manual_shortfall > 0:
        print(f"[build] manual 唯一池不足: {len(picked_manual)}/{manual_n}"
              f"（chat 语料唯一有效问句上限）→ 差额 {manual_shortfall} 由 cross 补足（显式留痕）")
    picked_cross, c_dedup = dedup_and_cap(cross_rows, total=limit - len(picked_manual))
    print(f"[build] manual 选中 {len(picked_manual)} (去重丢弃 {m_dedup})")
    print(f"[build] cross 选中 {len(picked_cross)} (去重丢弃 {c_dedup})")
    if len(picked_manual) + len(picked_cross) < limit:
        raise SystemExit(
            f"两路合计仍不足 {limit}：manual={len(picked_manual)} cross={len(picked_cross)}；"
            "先上报编排者，禁止静默凑数。")

    # ---- 组装 + 校验（不通过即硬错，禁止静默带病落盘）----
    question_content_by_id = {str(q.get("chunk_id") or ""): str(q.get("content") or "") for q in questions}
    cases: list[dict] = []
    invalid: list[dict] = []
    for r, src_content in ([(r, None) for r in picked_manual]
                           + [(r, question_content_by_id.get(r.get("source_chunk_id")))
                              for r in picked_cross]):
        gt = str(r["golden_content"])[:8000]
        case = {
            "query": r["query"],
            "golden": make_golden(r["golden_chunk_id"], r["golden_content"]),
            "gt_content": gt,
            "independence": r["independence"],
            "source": ("chat_message" if r["independence"] == "manual" else "question_bank->course_module"),
        }
        if r["independence"] == "manual":
            case.update({"source_message_id": r["source_message_id"], "cited_rank": r["cited_rank"],
                         "rewrite": "rule_regex(去寒暄+空白归一)", "rag_final_count": r.get("rag_final_count"),
                         "golden_overlap_terms": r.get("golden_overlap_terms")})
        else:
            case.update({"source_chunk_id": r["source_chunk_id"], "source_bank": r["source_bank"],
                         "series_code": r["series_code"], "matched_terms": r["matched_terms"],
                         "match_note": r["match_note"]})
        errs = validate_case(case, source_content=src_content)
        if errs:
            invalid.append({"query": case["query"], "errors": errs})
            continue
        cases.append(case)
    if invalid:
        raise SystemExit(f"validate_case 拒绝 {len(invalid)} 条（反圆环硬门）：{invalid[:3]}")

    # 交错排布（manual/cross 相间）避免前 32 条全是单一来源：按种子洗牌
    rng.shuffle(cases)

    git_rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             cwd=BASE_DIR).stdout.strip()
    meta = {
        "builder": "build_eval_set64.py --mode build",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": git_rev,
        "seed": SEED,
        "n_cases": len(cases),
        "split_requested": {"manual": manual_n, "cross": limit - manual_n},
        "split": {"manual": sum(1 for c in cases if c["independence"] == "manual"),
                   "cross": sum(1 for c in cases if c["independence"] == "cross")},
        "manual_shortfall_note": (
            f"请求 manual={manual_n}，强证据规则下唯一有效池仅 {manual_n - manual_shortfall} 条："
            "chat_message 为测试语料（唯一问句少 + 部分生产检索退化产出无关 golden + jieba 分词粒度"
            "在 query/doc 两侧不一致），抽检实证弱词重叠规则会放进无关 golden（如『一般过去时』问句"
            "配上『复试自我介绍』chunk），故只保留强证据样本、不凑数，差额由 cross 补足"
        ) if manual_shortfall > 0 else "无缺口",
        "independence_definitions": {
            "manual": "query=chat_message 真实用户问句(规则改写禁 LLM); golden=同会话 assistant rag_docs_json 生产投喂 chunk(当前 Milvus 内容 sha 复核)",
            "cross": "query=题库 question 题干(_extract_query 只读复用); golden=同域 course_module(bank→series 归一化对齐+词重叠边际规则), golden≠source chunk",
        },
        "golden_validity_rule": "manual golden 取被引 doc 中首个(当前库内容 sha 一致 且 与 query 词重叠≥2 或含≥3字重叠词)者; cross 需 matched_terms≥2 或单词长≥4 且次优边际严格",
        "dedup_rules": {"query_normalized_unique": True, "golden_cap": GOLDEN_CAP, "session_cap": SESSION_CAP},
        "chat_sql": CHAT_SQL,
        "yield_stats": {"manual": manual_stats, "manual_dedup": m_dedup,
                         "cross": cross_stats, "cross_dedup": c_dedup},
        "milvus_collection": COLLECTION_NAME,
        "golden_double_key": ["chunk_id", "doc_sha256(sha256(gt_content utf-8))"],
        "anti_circle_invariants": ["golden query 非从 golden chunk 自身提取(两路均成立)",
                                     "cross: golden≠source(id+sha 双验) 且 query 非 golden 子串",
                                     "manual: query 出自真实用户消息, 与 golden chunk 无文本派生关系"],
        "embed_backend_effective": str(getattr(settings, "EMBED_BACKEND", "unknown")),
        "wall_seconds": round(time.perf_counter() - t0, 1),
    }
    out = {"meta": meta, "cases": cases}
    with open(OUT_SET_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[build] n={len(cases)} (manual={meta['split']['manual']} cross={meta['split']['cross']}) → {OUT_SET_PATH}")
    print(f"[build] wall={meta['wall_seconds']}s embed_backend={meta['embed_backend_effective']}")


# ============================================================
# 测量：实时端到端检索链（R20-min 范式，0-LLM）
# ============================================================

async def _measure_one(sem, idx: int, case: dict, results: list, top_k: int, final_max_k: int) -> None:
    from app.auth import UserRole
    from app.chat.retriever import retrieve_three_channel

    async with sem:
        t0 = time.perf_counter()
        bundle = await retrieve_three_channel(
            case["query"],
            user_id=1,
            role=UserRole.STUDENT,
            use_hyde=PARAMS["use_hyde"],
            enable_graph=PARAMS["enable_graph"],
            top_k=top_k,
            final_max_k=final_max_k,
            cutoff_drop_ratio=PARAMS["cutoff_drop_ratio"],
        )
        lat_ms = round((time.perf_counter() - t0) * 1000, 1)
        docs = [{"chunk_id": d.doc_id, "content": d.content, "score": d.score} for d in bundle.docs]
        from r20min_run import _match_golden  # 只读复用 W0 双键解析（id_map/doc_sha256 兜底）

        gt_id, gt_via = _match_golden(case, docs)
        ranks = [i + 1 for i, d in enumerate(docs) if d["chunk_id"] == gt_id]
        results.append({
            "idx": idx,
            "query": case["query"],
            "independence": case.get("independence"),
            "golden_chunk_id": case["golden"]["chunk_id"],
            "golden_doc_sha256": case["golden"]["doc_sha256"],
            "gt_resolved_id": gt_id,
            "gt_resolve_via": gt_via,
            "hit@5": bool(ranks and ranks[0] <= 5),
            "hit@3": bool(ranks and ranks[0] <= 3),
            "rr@5": (1.0 / ranks[0]) if (ranks and ranks[0] <= 5) else 0.0,
            "rr@10": (1.0 / ranks[0]) if (ranks and ranks[0] <= top_k) else 0.0,
            "rank_of_gt": ranks[0] if ranks else None,
            "final_docs": len(docs),
            "latency_ms": lat_ms,
            "trace": {
                "recall_layer": int(bundle.raw_retrieved_count),
                "final_layer": len(docs),
                "degraded_reason": bundle.degraded_reason,
            },
        })


def _summarize(per_query: list[dict], tag: str, mode_note: str, top_k: int) -> dict:
    n = len(per_query)
    ranks = [r["rank_of_gt"] for r in per_query]
    hit5 = sum(1 for r in per_query if r["hit@5"])
    hit3 = sum(1 for r in per_query if r["hit@3"])
    mrr5 = round(sum(r["rr@5"] for r in per_query) / n, 4)
    mrrk = round(sum(r["rr@10"] for r in per_query) / n, 4)
    resolved_goldens = {r["gt_resolved_id"] for r in per_query if r["rank_of_gt"]}
    summary = {
        "tag": tag,
        "mode_note": mode_note,
        "n": n,
        "hit_rate@5": round(hit5 / n, 4),
        "mrr@5": mrr5,
        "hit@5_wilson95": wilson_ci(hit5 / n, n),
        "mrr@5_bootstrap95": bootstrap_ci([r["rr@5"] for r in per_query]),
        "rank_hist_top5": rank_distribution(ranks, 5),
        "degeneracy": degeneracy_check(hit5 / n, mrr5, ranks),
        "by_independence": {},
    }
    for indep in INDEPENDENCE_VALUES:
        sub = [r for r in per_query if r.get("independence") == indep]
        if sub:
            h5 = sum(1 for r in sub if r["hit@5"])
            summary["by_independence"][indep] = {
                "n": len(sub),
                "hit_rate@5": round(h5 / len(sub), 4),
                "mrr@5": round(sum(r["rr@5"] for r in sub) / len(sub), 4),
                "hit@5_wilson95": wilson_ci(h5 / len(sub), len(sub)),
            }
    if top_k > TOP_K_EVAL:  # 分级窗口
        h10 = sum(1 for r in per_query if r["rank_of_gt"] and r["rank_of_gt"] <= top_k)
        summary.update({
            "graded": {
                "top_k": top_k,
                "hit@3": round(hit3 / n, 4),
                "hit@5": round(hit5 / n, 4),
                f"hit@{top_k}": round(h10 / n, 4),
                f"mrr@{top_k}": mrrk,
                f"mrr@{top_k}_bootstrap95": bootstrap_ci([r["rr@10"] for r in per_query]),
                "rank_hist": rank_distribution(ranks, top_k),
                "distinct_golden_hit": len(resolved_goldens),
                "distinct_golden_hit_ratio": round(len(resolved_goldens) / n, 4),
            },
        })
    return summary


def measure(tag: str, graded: bool = False) -> dict:
    from app.config import settings
    from app.knowledge.importer.embedder import encode_dense_batch, ensure_jieba_ready

    with open(OUT_SET_PATH, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    ensure_jieba_ready()
    sys.path.insert(0, EVAL_DIR)  # r20min_run 只读复用（_match_golden 双键解析）
    # 预热 BGE-M3（冷加载在 retriever 外层 wait_for 窗口内会误触超时降级，eval 侧显式预热）
    _ = encode_dense_batch(["预热"])

    top_k = GRADED_K if graded else TOP_K_EVAL
    sem = asyncio.Semaphore(1)  # 串行：GPU/Milvus 稳定性优先，顺序固定保证可复现
    results: list[dict] = []
    t_start = time.perf_counter()

    async def _run_all() -> None:
        tasks = [_measure_one(sem, i, c, results, top_k, top_k) for i, c in enumerate(cases)]
        for t in tasks:  # 逐个 await：提交顺序=完成顺序（确定性）
            await t

    asyncio.run(_run_all())
    wall_s = round(time.perf_counter() - t_start, 1)

    mode_note = ("realtime_e2e_retrieval(retrieve_three_channel 全链, 与冻结契约同参)"
                 if not graded else
                 f"graded_widened_window(top_k=final_max_k={top_k}, 其余同冻结契约; 分级测量专用口径)")
    eff_params = dict(PARAMS)
    eff_params.update({"embed_backend": str(getattr(settings, "EMBED_BACKEND", "unknown")),
                        "top_k": top_k, "final_max_k": top_k})
    report = {
        "tag": tag,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                  cwd=BASE_DIR).stdout.strip(),
        "eval_set": OUT_SET_PATH,
        "mode_note": mode_note,
        "params": eff_params,
        "seed": SEED,
        "n_cases": len(results),
        "llm_used": False,
        "wall_seconds": wall_s,
        "per_query": results,
    }
    os.makedirs(RUNS_DIR, exist_ok=True)
    out_path = os.path.join(RUNS_DIR, f"{tag}.json")
    try:
        from app.common.artifact_store import save_artifact

        arch = save_artifact(f"eval/r22_runs/{tag}.json", report,
                             metadata={"kind": "r22_run_report", "tag": tag, "n_cases": len(results)},
                             local_copy=out_path)
        print(f"[artifact] backend={arch['backend']} aid={arch['aid']}")
    except Exception as exc:  # noqa: BLE001  归档失败回退直接落盘，不阻断测量
        print(f"[artifact] 归档失败(忽略, 直接落盘): {type(exc).__name__}: {exc}")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[measure:{tag}] hit@5={_hit5(results)} wall={wall_s}s → {out_path}")
    return report


def _hit5(results: list[dict]) -> str:
    if not results:
        return "n/a"
    return f"{sum(1 for r in results if r['hit@5'])}/{len(results)}"


def build_position_measure(run_tags: list[str], graded_tag: str | None) -> None:
    """头寸汇总：两跑确定性对照 + 95% CI + 分级指标 + 贴天花板判别（不落门，只出数字）。"""
    # 只读冻结契约（对照参照；本任务禁改该文件）
    contract_path = os.path.join(os.path.dirname(BASE_DIR), "contracts", "rag-baseline-eval32.json")
    try:
        with open(contract_path, encoding="utf-8") as f:
            contract = json.load(f)
        frozen_ref = {
            "contract": "contracts/rag-baseline-eval32.json (冻结, 本轮禁改)",
            "hit_rate@5": contract["baseline"]["hit_rate@5"],
            "mrr@5": contract["baseline"]["mrr@5"],
            "threshold_hit_rate_min": contract["thresholds"]["RAG_EVAL_HIT_RATE_MIN"],
            "threshold_mrr_min": contract["thresholds"]["RAG_EVAL_MRR_MIN"],
            "note": "eval_set32 为圆环自证集, 头寸仅对新集解释",
        }
    except (OSError, KeyError) as exc:
        raise SystemExit(f"冻结契约不可读或缺字段（对照参照必需）: {exc}")

    runs = {}
    for t in run_tags:
        with open(os.path.join(RUNS_DIR, f"{t}.json"), encoding="utf-8") as f:
            runs[t] = json.load(f)
    tags = list(runs)
    base = _summarize(runs[tags[0]]["per_query"], tags[0], runs[tags[0]]["mode_note"], TOP_K_EVAL)
    det = {"runs": tags}
    if len(tags) > 1:
        a, b = runs[tags[0]]["per_query"], runs[tags[1]]["per_query"]
        det.update({
            "hit_rate_equal": base["hit_rate@5"] == _summarize(b, tags[1], "", TOP_K_EVAL)["hit_rate@5"],
            "mrr_equal": base["mrr@5"] == _summarize(b, tags[1], "", TOP_K_EVAL)["mrr@5"],
            "per_query_identical": ([ (r["rank_of_gt"], r["hit@5"]) for r in a ]
                                    == [ (r["rank_of_gt"], r["hit@5"]) for r in b ]),
        })

    threshold_min = frozen_ref["threshold_hit_rate_min"]
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_set": OUT_SET_PATH,
        "frozen_baseline_reference": frozen_ref,
        "primary": base,
        "determinism_check": det,
        "graded_run": None,
        "headroom_verdict": None,
    }
    hr = base["hit_rate@5"]
    if hr >= 1.0:
        out["headroom_verdict"] = {
            "verdict": "insufficient_discrimination(区分度不足)",
            "reason": "hit_rate@5 贴 1.0 天花板, 与基线同样无法区分真回归与测量噪声; 阈值(基线-0.02)无头寸",
            "graded_metrics_advice": [
                "rank2/3 命中(hit@3): 把判别线从『进 top5』前移到『进 top3』",
                "mrr@10: 计入 top10 排名质量, 拉开 rank1~rank10 差异",
                "distinct-doc 覆盖: 命中 golden 的去重文档比例, 暴露多 query 挤同一 doc 的退化",
            ],
        }
    else:
        gap_to_ceiling = round(1.0 - hr, 4)
        margin_to_threshold = round(hr - threshold_min, 4)
        out["headroom_verdict"] = {
            "verdict": "headroom_measured(有头寸)",
            "gap_to_ceiling": gap_to_ceiling,
            "note": (f"新集 hit_rate@5={hr}, 距天花板 {gap_to_ceiling}; "
                     f"若沿用基线-0.02 阈值规则, 本集等价阈值为 {round(hr - 0.02, 4)}, "
                     f"与冻结阈值 {threshold_min} 的头寸差异需编排者裁定, 本任务不落门"),
            "threshold_margin_vs_frozen": margin_to_threshold,
        }
    if graded_tag:
        with open(os.path.join(RUNS_DIR, f"{graded_tag}.json"), encoding="utf-8") as f:
            grun = json.load(f)
        out["graded_run"] = _summarize(grun["per_query"], graded_tag, grun["mode_note"], GRADED_K)
    with open(POSITION_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[position] hit@5={base['hit_rate@5']} ci95={base['hit@5_wilson95']} "
          f"mrr@5={base['mrr@5']} ci95={base['mrr@5_bootstrap95']} det={det} → {POSITION_PATH}")
    print(f"[position] verdict={out['headroom_verdict']['verdict']}")


# ============================================================
# 抽检：5 条 golden 人读判定（3 manual + 2 cross，确定性）
# ============================================================

def spotcheck(n_total: int = 5) -> list[dict]:
    """抽检 golden 人读判定（manual 优先，池不足名额让给 cross，保证足额 n_total 条）。"""
    with open(OUT_SET_PATH, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    rng = random.Random(SEED)
    n_manual = min(3, sum(1 for c in cases if c["independence"] == "manual"))
    n_cross = n_total - n_manual
    picked: list[dict] = []
    for indep, n in (("manual", n_manual), ("cross", n_cross)):
        pool = [c for c in cases if c["independence"] == indep]
        rng.shuffle(pool)
        picked.extend(pool[:n])
    out = []
    for i, c in enumerate(picked, 1):
        item = {
            "no": i,
            "independence": c["independence"],
            "query": c["query"],
            "golden_chunk_id": c["golden"]["chunk_id"],
            "golden_content_head": c["gt_content"][:220].replace("\n", " / "),
            "provenance": ({k: c[k] for k in ("source_message_id", "cited_rank") if k in c}
                            if c["independence"] == "manual"
                            else {k: c[k] for k in ("source_chunk_id", "source_bank", "series_code",
                                                     "matched_terms", "match_note") if k in c}),
        }
        out.append(item)
        print(f"[spot#{i}] ({item['independence']}) Q: {item['query']}")
        print(f"         golden={item['golden_chunk_id']}")
        print(f"         content: {item['golden_content_head'][:160]}")
        print(f"         provenance: {json.dumps(item['provenance'], ensure_ascii=False)}")
    return out


def recallprobe() -> None:
    """召回层探针：逐 cross query 直连 hybrid_search(recall_topk=150)，定位 golden 召回排名。

    与 r20min_run._run_sensitivity 同思路的独立直连通道（loader 同参重放），只出召回层
    布尔/排名口径，用于分层归因（召回 vs rerank+断崖），不与主链绝对值混算。
    """
    from app.config import settings
    from app.knowledge.importer.embedder import build_sparse_vector, encode_dense_batch, ensure_jieba_ready
    from app.knowledge.importer.loader import COLLECTION_NAME, COURSE_PUBLIC, get_milvus_client, hybrid_search

    with open(OUT_SET_PATH, encoding="utf-8") as f:
        cases = [c for c in json.load(f)["cases"] if c.get("independence") == "cross"]
    ensure_jieba_ready()
    client = get_milvus_client()
    tenant_ids = ["_default", COURSE_PUBLIC]
    exclude = getattr(settings, "RETRIEVER_EXCLUDE_CONTENT_TYPES", ()) or ()
    filter_expr = None
    if exclude:
        quoted = ", ".join(f'"{ct}"' for ct in exclude)
        filter_expr = f"content_type not in [{quoted}]"

    dense_all = encode_dense_batch([c["query"] for c in cases])
    rows: list[dict] = []
    for c, dv in zip(cases, dense_all):
        recall = hybrid_search(
            dense_vec=[float(x) for x in dv],
            sparse_vec=build_sparse_vector(c["query"]),
            tenant_ids=tenant_ids,
            top_k=PARAMS["recall_topk"],
            filter_expr=filter_expr,
            timeout=float(getattr(settings, "MILVUS_SEARCH_TIMEOUT", 8.0)),
        )
        ids = [str(r.get("chunk_id") or "") for r in recall]
        types = [str(r.get("content_type") or "") for r in recall]
        gt = c["golden"]["chunk_id"]
        rrank = ids.index(gt) + 1 if gt in ids else None
        rows.append({
            "query": c["query"],
            "golden_chunk_id": gt,
            "golden_recall_rank": rrank,
            "golden_in_recall": rrank is not None,
            "recall_top5_types": types[:5],
            "recall150_type_mix": {t: types.count(t) for t in sorted(set(types))},
        })
    n = len(rows)
    hit = sum(1 for r in rows if r["golden_in_recall"])
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channel": "isolated_replay(loader.hybrid_search 同参直连, 召回层口径, 不与主链混算)",
        "recall_topk": PARAMS["recall_topk"],
        "n_cases": n,
        "golden_in_recall": hit,
        "golden_in_recall_ratio": round(hit / n, 4) if n else 0.0,
        "golden_recall_rank_hist": rank_distribution([r["golden_recall_rank"] for r in rows], PARAMS["recall_topk"]),
        "rows": rows,
    }
    path = os.path.join(DATA_DIR, "r22_recall_layer_probe.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[recallprobe] golden_in_recall={hit}/{n} → {path}")
    ranks = sorted(r["golden_recall_rank"] for r in rows if r["golden_recall_rank"])
    if ranks:
        import statistics

        print(f"[recallprobe] golden recall rank: min={ranks[0]} median={statistics.median(ranks)} max={ranks[-1]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="R22 去圆环评估集构造 + 头寸测量")
    ap.add_argument("--mode", required=True, choices=["build", "measure", "position", "spotcheck", "recallprobe"])
    ap.add_argument("--tag", default="run")
    ap.add_argument("--limit", type=int, default=64)
    ap.add_argument("--manual-n", type=int, default=40)
    ap.add_argument("--graded", action="store_true", help="measure 用分级窗口 top_k=final_max_k=10")
    ap.add_argument("--runs", nargs="*", help="position 模式: 参与汇总的主口径 run tags")
    ap.add_argument("--graded-tag", default=None, help="position 模式: 分级窗口 run tag")
    args = ap.parse_args()

    if args.mode == "build":
        asyncio.run(build(args.limit, args.manual_n))
        return 0
    if args.mode == "measure":
        measure(args.tag, args.graded)
        return 0
    if args.mode == "position":
        build_position_measure(args.runs or ["r22_base_run1"], args.graded_tag)
        return 0
    if args.mode == "recallprobe":
        recallprobe()
        return 0
    spotcheck()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
