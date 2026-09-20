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
  .venv/Scripts/python.exe -X utf8 scripts/eval/build_eval_set64.py --mode rewritev3   # V3: LLM 改写 64 query
  .venv/Scripts/python.exe scripts/eval/build_eval_set64.py --mode buildv3            # V3: 护栏建集（活体 golden 复核）

产物：
  scripts/eval/data/r22_eval_set64.json        64 条去圆环评估集（independence 溯源+双键 golden）
  scripts/eval/data/r22_runs/<tag>.json        逐次测量 per_query 全量
  scripts/eval/data/r22_position_measure.json  头寸汇总（分布+95% CI+分级指标+结论）
  scripts/eval/data/r64v3_rewrite_records.json V3 LLM 改写记录（护栏回炉/剔除计数留痕）
  scripts/eval/data/r64v3_eval_set64.json      V3 集（golden 不变，query 改写面）
  scripts/eval/data/r64v3_runs/<tag>.json      V3 测量 per_query 全量（--set r64v3 集时）
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
# V2（CO-EVAL64V2-001 golden 形态重铸）：golden 主目标=内容块
# V1 既有行为零改动；V2 全部走 buildv2/measure(--set)/freezev2 新路径
# ============================================================
GOLDEN_TYPES = ("content_block", "module_card")
CONTENT_FORMS = ("verbatim", "production_cited")
CONTENT_BLOCK_RATIO_MIN = 0.60   # 类型分布断言（R22 反哺：建集器缺类型分布检查）
V1_SET_PATH = OUT_SET_PATH
V2_SET_PATH = os.path.join(DATA_DIR, "r64v2_eval_set64.json")
V2_RUNS_DIR = os.path.join(DATA_DIR, "r64v2_runs")
V2_CONTRACT_PATH = os.path.join(os.path.dirname(BASE_DIR), "contracts", "rag-baseline-eval64-v2.json")
V2_CHANGE_ORDER = "contracts/ChangeOrder-eval64v2-golden-form.md"

# ============================================================
# V3（EVAL64V3，承接 EVAL64V2 P0-①）：query 面改写——「同义不同形」
# V2 尺 0.9844 贴天花板根因=golden 取自 query 源块（子串保底乐观）。
# V3 用 LLM 把 64 条 query 改写成同义不同形（golden 不变），创造真实 headroom。
# ============================================================
V3_SET_PATH = os.path.join(DATA_DIR, "r64v3_eval_set64.json")
V3_REWRITE_PATH = os.path.join(DATA_DIR, "r64v3_rewrite_records.json")
V3_RUNS_DIR = os.path.join(DATA_DIR, "r64v3_runs")
V3_OVERLAP_MAX = 0.60     # 护栏②：v3 对 v2 字面重叠上限（真改写非微调）
V3_RELEVANCE_MIN = 4      # 护栏③：LLM 自评语义相关度下限（1-5）
V3_REWRITE_RETRY = 2      # 回炉上限（不含首改）；仍违规则剔除计数，不凑数
V3_LENGTH_RATIO = 0.50    # 长度变化上限（±50%，任务书口径）


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
# V2 纯逻辑层（CO-EVAL64V2-001；全部离线可单测，Milvus/app.* 懒加载在 build_v2）
# ============================================================

def norm_text(text: str) -> str:
    """与 V1 query_key 同口径的归一：lower + 去空白/标点/下划线（子串判定两侧统一）。"""
    return re.sub(r"[\s\W_]+", "", str(text or "").lower())


def find_verbatim_candidates(norm_query: str, question_index: list[dict]) -> list[str]:
    """在 question 全量索引中找逐字含问句的内容块，按 chunk_id 排序保证确定性。"""
    if not norm_query:
        return []
    return sorted(qi["chunk_id"] for qi in question_index
                  if qi.get("norm") and norm_query in qi["norm"])


def resolve_golden_v2(
    v1_case: dict,
    question_index: list[dict],
    qcontent_by_id: dict[str, str],
    content_map: dict[str, str],
) -> tuple[dict | None, str | None]:
    """V1 case → V2 golden 解析（CO-EVAL64V2-001 §2.1/§2.2）。

    优先级：cross=逐字内容块（source 块优先，其余重复块次之）→ V1 路由卡兜底（sha 复核）
           manual=生产投喂块（production_cited，sha 复核）→ 逐字内容块 → unresolved。
    返回 (resolved_row | None, unresolved_reason | None)。query 面冻结复用，禁再提取/再改写。
    """
    indep = v1_case.get("independence")
    q = str(v1_case.get("query") or "")
    golden_v1 = v1_case.get("golden") or {}
    v1_gid = str(golden_v1.get("chunk_id") or "")
    v1_sha = str(golden_v1.get("doc_sha256") or "")
    base = {
        "query": q,
        "query_key": norm_text(q),
        "cap_key": None,
        "session_key": None,   # V1 集建集时已过 session cap；V2 继承面不重采
        "independence": indep,
        "v1_golden_chunk_id": v1_gid,
    }

    def _v1_golden_content_ok() -> str | None:
        cur = content_map.get(v1_gid)
        return cur if (cur is not None and v1_sha and sha256_utf8(cur) == v1_sha) else None

    if indep == "cross":
        src = str(v1_case.get("source_chunk_id") or "")
        cands = find_verbatim_candidates(norm_text(q), question_index)
        if cands:
            pick = src if src in cands else cands[0]
            return {**base, "cap_key": pick, "golden_chunk_id": pick,
                    "golden_content": qcontent_by_id.get(pick, content_map.get(pick, "")),
                    "golden_type": "content_block", "content_match_form": "verbatim",
                    "golden_is_query_source": pick == src, "verbatim_dup_count": len(cands)}, None
        cur = _v1_golden_content_ok()
        if cur is not None:
            return {**base, "cap_key": v1_gid, "golden_chunk_id": v1_gid,
                    "golden_content": cur, "golden_type": "module_card",
                    "content_match_form": None, "golden_is_query_source": None,
                    "verbatim_dup_count": None}, None
        return None, "no_verbatim_block_and_v1_golden_unverifiable"
    if indep == "manual":
        cur = _v1_golden_content_ok()
        if cur is not None:
            return {**base, "cap_key": v1_gid, "golden_chunk_id": v1_gid,
                    "golden_content": cur, "golden_type": "content_block",
                    "content_match_form": "production_cited",
                    "golden_is_query_source": None, "verbatim_dup_count": None}, None
        cands = find_verbatim_candidates(norm_text(q), question_index)
        if cands:
            pick = cands[0]
            return {**base, "cap_key": pick, "golden_chunk_id": pick,
                    "golden_content": qcontent_by_id.get(pick, ""),
                    "golden_type": "content_block", "content_match_form": "verbatim",
                    "golden_is_query_source": False, "verbatim_dup_count": len(cands)}, None
        return None, "manual_golden_drift_and_no_verbatim_block"
    return None, f"unknown_independence:{indep}"


def assemble_v2_case(v1_case: dict, row: dict) -> dict:
    """V1 case（provenance 全量继承）+ V2 解析行 → V2 case dict。顺序=V1 文件序（v1_idx 对齐）。"""
    case = dict(v1_case)   # source_chunk_id/source_bank/series_code/matched_terms/manual 溯源等全继承
    content = str(row["golden_content"] or "")
    case.update({
        "golden": make_golden(row["golden_chunk_id"], content),
        "gt_content": content[:8000],   # 与 V1 同口径（截断后双键校验，>8000 会被 validate 拒绝）
        "golden_type": row["golden_type"],
        "v1_golden_chunk_id": row["v1_golden_chunk_id"],
        "v1_idx": row.get("v1_idx"),
    })
    if row.get("content_match_form") is not None or row["golden_type"] == "content_block":
        case["content_match_form"] = row.get("content_match_form")
        case["golden_is_query_source"] = row.get("golden_is_query_source")
        case["verbatim_dup_count"] = row.get("verbatim_dup_count")
    if row["golden_type"] == "content_block" and row.get("content_match_form") == "verbatim" \
            and case.get("independence") == "cross":
        case["source"] = "question_bank->content_block"
    return case


def validate_case_v2(case: dict, *, source_content: str | None = None) -> list[str]:
    """V2 反圆环 + 结构校验（CO-EVAL64V2-001 §2.2）。返回违规列表（空=通过）。

    W1 golden_type 必填且 ∈ {content_block, module_card}
    W2 content_block 必带合法 content_match_form
    W3 verbatim 声明可验证：norm(query) ⊆ norm(gt_content)
    W4 cross verbatim 必带 golden_is_query_source 显式声明（禁隐藏子串保底）
    W5 production_cited 必带 manual 溯源（source_message_id/cited_rank）
    V2/V5 双键与 query 长度同 V1；module_card 沿用 V1 全部 cross 反圆环规则
    （golden≠source id+sha、query 非子串、matched_terms 必填）。
    """
    errs: list[str] = []
    indep = case.get("independence")
    if indep not in INDEPENDENCE_VALUES:
        errs.append(f"V1 independence 非法: {indep!r}")
    gtype = case.get("golden_type")
    if gtype not in GOLDEN_TYPES:
        errs.append(f"W1 golden_type 非法: {gtype!r}")
    golden = case.get("golden") or {}
    gt = str(case.get("gt_content") or "")
    q = str(case.get("query") or "")
    if not golden.get("chunk_id"):
        errs.append("V2 golden.chunk_id 缺失")
    if not golden.get("doc_sha256"):
        errs.append("V2 golden.doc_sha256 缺失")
    elif golden["doc_sha256"] != sha256_utf8(gt):
        errs.append("V2 doc_sha256 与 gt_content 不一致（双键失配）")
    if not (QUERY_MIN_LEN <= len(q) <= QUERY_MAX_LEN):
        errs.append(f"V5 query 长度越界: {len(q)}")
    if gtype == "content_block":
        form = case.get("content_match_form")
        if form not in CONTENT_FORMS:
            errs.append(f"W2 content_match_form 非法: {form!r}")
        elif form == "verbatim":
            if not gt or not q:
                errs.append("W3 verbatim 缺 query 或 gt_content")
            elif norm_text(q) not in norm_text(gt):
                errs.append("W3 verbatim 声明不成立: norm(query) 非 norm(gt_content) 子串")
            if indep == "cross" and not isinstance(case.get("golden_is_query_source"), bool):
                errs.append("W4 cross verbatim 缺 golden_is_query_source 布尔声明")
        elif form == "production_cited":
            if not case.get("source_message_id"):
                errs.append("W5 production_cited 缺 source_message_id 溯源")
            if case.get("cited_rank") is None:
                errs.append("W5 production_cited 缺 cited_rank 溯源")
    if gtype == "module_card":
        src_id = str(case.get("source_chunk_id") or "")
        if not src_id:
            errs.append("V3 module_card 缺 source_chunk_id")
        elif src_id == golden.get("chunk_id"):
            errs.append("V3 module_card golden 与 source 同 chunk（圆环）")
        if source_content is not None and golden.get("doc_sha256") == sha256_utf8(source_content):
            errs.append("V3 module_card golden 内容与 source 内容相同（圆环）")
        if gt and q and q in gt:
            errs.append("V3 module_card query 是 golden 内容子串（自匹配保底）")
        if not case.get("matched_terms"):
            errs.append("V3 module_card 缺 matched_terms 互证证据")
    return errs


def assert_type_distribution(cases: list[dict],
                             *, min_ratio: float = CONTENT_BLOCK_RATIO_MIN) -> dict:
    """类型分布硬断言（CO-EVAL64V2-001 §2.3，R22 反哺）：content_block 占比 <60% 报错退出。"""
    n = len(cases)
    if n == 0:
        raise SystemExit("[buildv2] 空集：类型分布断言不可能满足（content_block 占比须 ≥60%）→ 拒绝落盘")
    cb = sum(1 for c in cases if c.get("golden_type") == "content_block")
    ratio = cb / n
    if ratio < min_ratio:
        raise SystemExit(
            f"[buildv2] 类型分布断言失败: content_block {cb}/{n}={ratio:.2%} < {min_ratio:.0%}"
            f"（{V2_CHANGE_ORDER} §2.3）→ 拒绝落盘，先上报编排者")
    return {"content_block": cb, "module_card": n - cb,
            "content_block_ratio": round(ratio, 4), "min_ratio": min_ratio}


# ============================================================
# V3 纯逻辑层（EVAL64V3；全部离线可单测，LLM 调用只在 rewritev3，Milvus 只在 buildv3）
# ============================================================

def char_bigrams(text: str) -> set:
    """字面重叠计量单元：去空白后的字符 2-gram 集合（长度<2 退化为单字集）。

    中文 query 无分词歧义，字符 bigram 对「换句式/换同义词」敏感且确定性。"""
    t = re.sub(r"\s+", "", str(text or ""))
    if len(t) < 2:
        return set(t)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def literal_overlap(v2_query: str, v3_query: str) -> float:
    """护栏② 计量：v2 面 bigram 保留率 = |B2∩B3| / |B2|。

    分母取 v2——衡量改写保留了多少原句面形：1.0=逐字抄（假改写），0=完全换形。"""
    b2, b3 = char_bigrams(v2_query), char_bigrams(v3_query)
    if not b2:
        return 1.0 if not b3 else 0.0
    return round(len(b2 & b3) / len(b2), 4)


def check_rewrite_guardrails(v2_case: dict, rec: dict, *,
                             overlap_max: float = V3_OVERLAP_MAX,
                             relevance_min: int = V3_RELEVANCE_MIN,
                             length_ratio: float = V3_LENGTH_RATIO) -> list:
    """EVAL64V3 改写护栏（纯逻辑）。返回违规列表（空=通过）。

    G1 双键 golden 归属不变：rec.golden 与 v2 case golden 逐键相等
       （chunk_id + doc_sha256 全等——query 改写不得改变 golden 归属）。
    G2 真改写非微调：literal_overlap(v2, v3) < overlap_max。
    G3 LLM 自评语义相关度 ≥ relevance_min（1-5）。
    G4 长度 ±length_ratio 内（任务书口径）且 ≥ QUERY_MIN_LEN（V5 同口径）；
       空串/与原句全同亦拒。
    """
    errs: list = []
    v2q = str(v2_case.get("query") or "")
    v3q = str(rec.get("v3_query") or "").strip()
    if (rec.get("golden") or {}) != (v2_case.get("golden") or {}):
        errs.append("G1 golden 双键与 V2 不等（归属被改写）")
    if not v3q or v3q == v2q:
        errs.append("G4 v3_query 为空或与原句全同")
    else:
        ov = literal_overlap(v2q, v3q)
        if ov >= overlap_max:
            errs.append(f"G2 字面重叠 {ov:.2%} >= {overlap_max:.0%}（微调非改写）")
        lo, hi = max(1, round(len(v2q) * (1 - length_ratio))), \
            max(1, round(len(v2q) * (1 + length_ratio)))
        if not (lo <= len(v3q) <= hi) or len(v3q) < QUERY_MIN_LEN:
            errs.append(f"G4 长度 {len(v3q)} 越界 [{max(lo, QUERY_MIN_LEN)},{hi}]（±50%）")
    rel = rec.get("relevance")
    if not isinstance(rel, int) or isinstance(rel, bool) or not (1 <= rel <= 5):
        errs.append(f"G3 relevance 非法: {rel!r}")
    elif rel < relevance_min:
        errs.append(f"G3 自评相关度 {rel} < {relevance_min}")
    return errs


def assemble_v3_case(v2_case: dict, rec: dict) -> dict:
    """V2 case（provenance/golden 全继承，golden 逐位不变）+ 改写记录 → V3 case。

    query 换成 v3_query；v2_query 与改写元数据留痕；golden/gt_content 双键零改动。"""
    case = dict(v2_case)
    case["query"] = str(rec["v3_query"])
    case["v2_query"] = str(v2_case["query"])
    case["rewrite_v3"] = {
        "v3_query": str(rec["v3_query"]),
        "rewrite_rationale": str(rec.get("rewrite_rationale") or ""),
        "relevance_self": rec.get("relevance"),
        "style": rec.get("style"),
        "attempts": rec.get("attempts"),
        "literal_overlap": literal_overlap(str(v2_case["query"]), str(rec["v3_query"])),
        "model": rec.get("model"),
    }
    return case


def validate_case_v3(case: dict, *, source_content: str | None = None) -> list:
    """V3 校验：V2 全规则，唯 W3 子串断言按 V3 语义反转。

    - W3 豁免：改写问句按设计不再是 golden 子串（V3 的目的即脱子串代理）。
    - W3'（反向不变量）：verbatim 形态下 norm(v3_query) 仍 ⊆ norm(gt_content)
      = 假改写（子串代理税未破），拒绝。
    - V3 溯源：必带 v2_query；W1/W2/W4/W5/V1/V2/V5 与 validate_case_v2 同语义。"""
    errs = [e for e in validate_case_v2(case, source_content=source_content)
            if not e.startswith("W3 verbatim 声明不成立")]
    gt = str(case.get("gt_content") or "")
    q = str(case.get("query") or "")
    if gt and q and norm_text(q) in norm_text(gt):
        errs.append("W3' v3 query 仍是 golden 子串（假改写，子串代理税未破）")
    if not case.get("v2_query"):
        errs.append("V3 缺 v2_query（面继承溯源）")
    if not (case.get("rewrite_v3") or {}).get("rewrite_rationale"):
        errs.append("V3 缺 rewrite_rationale（改写理由留痕）")
    return errs


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
# V2 构建（CO-EVAL64V2-001）：V1 冻结集 golden 重解析到内容块
# ============================================================

RESOLVE_RATIO_FLOOR = 0.90   # 主尺质量地板：可解析样本不足 90% 拒绝建尺（不凑数）


async def build_v2(in_set: str = V1_SET_PATH) -> None:
    """eval64-v2 重建：冻结复用 V1 query 面，golden 重解析到内容块（逐字含问句优先）。

    纪律（变更单 §2.2）：query 逐字继承（禁从目标块循环提取/再改写）；independence 溯源
    全继承；golden 双键不变；类型分布断言 content_block ≥60% 否则报错退出（§2.3）。
    """
    t0 = time.perf_counter()
    with open(in_set, encoding="utf-8") as f:
        v1 = json.load(f)
    v1_cases: list[dict] = v1["cases"]

    # ---- Milvus：question 全量（逐字索引）+ V1 golden 当前内容（sha 复核）----
    from app.knowledge.importer.loader import COLLECTION_NAME, get_milvus_client

    client = get_milvus_client()
    assert COLLECTION_NAME in [str(c) for c in client.list_collections()], "Milvus 缺 edu_knowledge"
    questions = client.query(
        COLLECTION_NAME,
        filter='content_type == "question"',
        output_fields=["chunk_id", "question_bank_code", "content"],
        limit=8000,
    )
    question_index = [{"chunk_id": str(q.get("chunk_id") or ""),
                       "bank": str(q.get("question_bank_code") or ""),
                       "content": str(q.get("content") or ""),
                       "norm": norm_text(q.get("content"))} for q in questions]
    qcontent_by_id = {qi["chunk_id"]: qi["content"] for qi in question_index if qi["chunk_id"]}
    v1_golden_ids = [str((c.get("golden") or {}).get("chunk_id") or "") for c in v1_cases]
    content_map = _milvus_content_map(client, COLLECTION_NAME, v1_golden_ids)

    # ---- 逐条重解析（V1 文件顺序，v1_idx 对齐 R24 探针口径）----
    resolved: list[dict] = []
    unresolved: list[dict] = []
    for idx, vc in enumerate(v1_cases):
        row, reason = resolve_golden_v2(vc, question_index, qcontent_by_id, content_map)
        if row is None:
            unresolved.append({"v1_idx": idx, "query": vc.get("query"), "reason": reason})
            continue
        row["v1_idx"] = idx
        resolved.append(row)
    resolve_stats = {
        "content_block_verbatim": sum(1 for r in resolved if r["content_match_form"] == "verbatim"),
        "content_block_production_cited": sum(1 for r in resolved if r["content_match_form"] == "production_cited"),
        "module_card_fallback": sum(1 for r in resolved if r["golden_type"] == "module_card"),
        "unresolved": len(unresolved),
    }
    print(f"[buildv2] 解析: {resolve_stats}（in={len(v1_cases)}）")

    # ---- 去重与配额（纪律同 V1）。V1 集已去重，此处丢弃只可能来自 V2 golden 碰撞——显式拒绝 ----
    picked, dedup_stats = dedup_and_cap(resolved, total=len(v1_cases))
    if len(picked) < len(resolved):
        raise SystemExit(f"[buildv2] 继承面出现去重/配额丢弃 {len(resolved) - len(picked)} 条"
                         f"（V2 golden 碰撞？）→ 拒绝静默，先上报编排者: {dedup_stats}")

    # ---- 组装 + V2 校验（硬门）----
    cases: list[dict] = []
    invalid: list[dict] = []
    for r in picked:
        case = assemble_v2_case(v1_cases[r["v1_idx"]], r)
        errs = validate_case_v2(case)
        if errs:
            invalid.append({"v1_idx": r["v1_idx"], "query": case["query"], "errors": errs})
            continue
        cases.append(case)
    if invalid:
        raise SystemExit(f"[buildv2] validate_case_v2 拒绝 {len(invalid)} 条（硬门）: {invalid[:3]}")
    if len(cases) < math.ceil(RESOLVE_RATIO_FLOOR * len(v1_cases)):
        raise SystemExit(f"[buildv2] 可解析样本 {len(cases)}/{len(v1_cases)} 低于 "
                         f"{RESOLVE_RATIO_FLOOR:.0%} 地板，拒绝建尺（不凑数）；unresolved 已入 meta，先上报编排者")

    # ---- 类型分布断言（R22 反哺，硬门）----
    dist = assert_type_distribution(cases)
    print(f"[buildv2] 类型分布: {dist}")

    git_rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             cwd=BASE_DIR).stdout.strip()
    meta = {
        "builder": "build_eval_set64.py --mode buildv2",
        "change_order": V2_CHANGE_ORDER,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": git_rev,
        "in_set": {"file": os.path.relpath(in_set, BASE_DIR).replace("\\", "/"),
                   "n": len(v1_cases), "seed": v1.get("meta", {}).get("seed"),
                   "v1_builder": v1.get("meta", {}).get("builder")},
        "query_face_policy": ("冻结复用 V1 query 面（逐字继承，禁从目标块循环提取/再改写）；"
                               "case 顺序=V1 文件顺序（v1_idx 对齐 R24 探针 idx）"),
        "golden_form": ("主目标=内容块（逐字含问句或直接回答该问句的 chunk）；"
                        "module_card 仅为内容块不可达时的兜底（沿用 V1 反圆环全规则）；"
                        "V1 golden 保留为 v1_golden_chunk_id 次级指标锚点"),
        "n_cases": len(cases),
        "golden_type_distribution": dist,
        "resolve_stats": resolve_stats,
        "unresolved": unresolved,
        "independence_definitions": {
            "manual": "query=V1 继承（chat 真实问句规则改写）; golden=生产投喂块(production_cited, 当前 Milvus sha 复核) 或逐字内容块",
            "cross": "query=V1 继承（题库题干）; golden=逐字含问句的 question 内容块（source 块优先, golden_is_query_source 显式声明）",
        },
        "golden_double_key": ["chunk_id", "doc_sha256(sha256(gt_content utf-8))"],
        "dedup_rules": {"query_normalized_unique": True, "golden_cap": GOLDEN_CAP,
                         "session_cap": "N/A（继承面不重采）", "dropped": dedup_stats},
        "milvus_collection": COLLECTION_NAME,
        "anti_circle_invariants": [
            "V2 query 面冻结自 V1 集本（不在 V2 build 中从 golden 块提取/改写任何 query）",
            "cross verbatim: golden_is_query_source 显式声明子串保底形态（CO-EVAL64V2-001 §2.2），脱圆环语义由变更单裁定",
            "module_card 兜底: golden≠source(id+sha 双验) 且 query 非 golden 子串（V1 规则全保留）",
        ],
        "wall_seconds": round(time.perf_counter() - t0, 1),
    }
    out = {"meta": meta, "cases": cases}
    with open(V2_SET_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[buildv2] n={len(cases)} dist={dist['content_block']}cb/{dist['module_card']}mc "
          f"unresolved={len(unresolved)} → {V2_SET_PATH}")
    print(f"[buildv2] wall={meta['wall_seconds']}s")


# ============================================================
# 测量：实时端到端检索链（R20-min 范式，0-LLM）
# ============================================================

async def _measure_one(sem, idx: int, case: dict, results: list, top_k: int, final_max_k: int,
                      group_hit: bool = False) -> None:
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

        # CO-IDX31-GROUPHIT-001：组命中放宽（配置化，仅标记 group 的 golden 生效）。
        # 「组」= 建集时 verbatim_candidates（norm(V2 题干) 子串命中的兄弟块族，idx31=33 成员）；
        # 组内任一成员进 final docs 即记 hit，mrr 取组内最好排名（docs 已按相关度降序，首个命中=最好）。
        # 默认 False；开启时仅对 verbatim_dup_count>1 的 case 生效（全库实测仅 idx31 一条），
        # 其余 case 走原 _match_golden 单键路径逐位不变。
        group_applied = False
        group_size = None
        if group_hit and (case.get("verbatim_dup_count") or 0) > 1:
            gstem = case.get("v2_query") or case["query"]
            gnorm = norm_text(gstem)
            ranks = [i + 1 for i, d in enumerate(docs) if gnorm and gnorm in norm_text(d["content"])]
            gt_id = case["golden"]["chunk_id"]   # 留痕用规范 golden id
            gt_via = "group_hit"
            group_applied = True
            group_size = case["verbatim_dup_count"]
        else:
            gt_id, gt_via = _match_golden(case, docs)
            ranks = [i + 1 for i, d in enumerate(docs) if d["chunk_id"] == gt_id]
        # module-level 次级指标（CO-EVAL64V2-001 §2.1：模块卡降为次级）：V1 golden 块是否进 final docs
        module_gt = str(case.get("v1_golden_chunk_id") or "")
        module_rank = next((i + 1 for i, d in enumerate(docs) if d["chunk_id"] == module_gt), None) \
            if module_gt else None
        results.append({
            "idx": idx,
            "query": case["query"],
            "independence": case.get("independence"),
            "golden_type": case.get("golden_type"),
            "golden_chunk_id": case["golden"]["chunk_id"],
            "golden_doc_sha256": case["golden"]["doc_sha256"],
            "gt_resolved_id": gt_id,
            "gt_resolve_via": gt_via,
            "hit@5": bool(ranks and ranks[0] <= 5),
            "hit@3": bool(ranks and ranks[0] <= 3),
            "rr@5": (1.0 / ranks[0]) if (ranks and ranks[0] <= 5) else 0.0,
            "rr@10": (1.0 / ranks[0]) if (ranks and ranks[0] <= top_k) else 0.0,
            "rank_of_gt": ranks[0] if ranks else None,
            "module_hit@5": (bool(module_rank and module_rank <= 5)
                             if case.get("v1_golden_chunk_id") else None),
            "module_rank_of_gt": module_rank,
            "final_docs": len(docs),
            "latency_ms": lat_ms,
            "group_hit_applied": group_applied,
            "group_size": group_size,
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
    # V2：golden_type 分组 + module-level 次级指标（V1 集无这些字段时自动缺省不产出）
    if any(r.get("golden_type") for r in per_query):
        summary["by_golden_type"] = {}
        for gt in GOLDEN_TYPES:
            sub = [r for r in per_query if r.get("golden_type") == gt]
            if sub:
                h5 = sum(1 for r in sub if r["hit@5"])
                summary["by_golden_type"][gt] = {
                    "n": len(sub),
                    "hit_rate@5": round(h5 / len(sub), 4),
                    "mrr@5": round(sum(r["rr@5"] for r in sub) / len(sub), 4),
                    "hit@5_wilson95": wilson_ci(h5 / len(sub), len(sub)),
                }
    mod_rows = [r for r in per_query if r.get("module_hit@5") is not None]
    if mod_rows:
        mh5 = sum(1 for r in mod_rows if r["module_hit@5"])
        summary["module_level_secondary"] = {
            "note": "V1 golden（路由卡）是否进 final docs——模块路由能力次级读数，非门禁主尺",
            "n": len(mod_rows),
            "module_hit@5": round(mh5 / len(mod_rows), 4),
            "module_mrr@5": round(sum((1.0 / r["module_rank_of_gt"])
                                      if r.get("module_rank_of_gt") else 0.0
                                      for r in mod_rows) / len(mod_rows), 4),
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


def measure(tag: str, graded: bool = False, set_path: str | None = None,
            group_hit: bool = False) -> dict:
    from app.config import settings
    from app.knowledge.importer.embedder import encode_dense_batch, ensure_jieba_ready

    # V1 缺省行为不变（OUT_SET_PATH + RUNS_DIR）；--set 指定 V2/V3 集时按前缀路由 runs 目录
    eval_set_path = set_path or OUT_SET_PATH
    runs_dir = RUNS_DIR
    if set_path:
        runs_dir = V3_RUNS_DIR if os.path.basename(set_path).startswith("r64v3") else V2_RUNS_DIR
    with open(eval_set_path, encoding="utf-8") as f:
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
        tasks = [_measure_one(sem, i, c, results, top_k, top_k, group_hit=group_hit)
                 for i, c in enumerate(cases)]
        for t in tasks:  # 逐个 await：提交顺序=完成顺序（确定性）
            await t

    asyncio.run(_run_all())
    wall_s = round(time.perf_counter() - t_start, 1)

    mode_note = ("realtime_e2e_retrieval(retrieve_three_channel 全链, 与冻结契约同参)"
                 if not graded else
                 f"graded_widened_window(top_k=final_max_k={top_k}, 其余同冻结契约; 分级测量专用口径)")
    eff_params = dict(PARAMS)
    eff_params.update({"embed_backend": str(getattr(settings, "EMBED_BACKEND", "unknown")),
                        "top_k": top_k, "final_max_k": top_k, "group_hit": group_hit})
    report = {
        "tag": tag,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                                  cwd=BASE_DIR).stdout.strip(),
        "eval_set": eval_set_path,
        "mode_note": mode_note,
        "group_hit": group_hit,
        "group_hit_note": ("CO-IDX31-GROUPHIT-001：组内任一兄弟块进 top5 记 hit；"
                           "仅 verbatim_dup_count>1 的 golden 生效（实测仅 idx31）" if group_hit else
                           "单键精确命中口径（CO-IDX31-GROUPHIT-001 未启用）"),
        "params": eff_params,
        "seed": SEED,
        "n_cases": len(results),
        "llm_used": False,
        "wall_seconds": wall_s,
        "per_query": results,
    }
    os.makedirs(runs_dir, exist_ok=True)
    out_path = os.path.join(runs_dir, f"{tag}.json")
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
# V2 基线冻结（CO-EVAL64V2-001 任务④）：pre-fix 现产线实况，无目标预设
# ============================================================

def _fingerprint(per_query: list[dict]) -> list:
    """逐位指纹（r23_freeze_eval64 同口径：rank/hit/rr/final_docs 四元组）。"""
    return [(r["rank_of_gt"], r["hit@5"], r["rr@5"], r["final_docs"]) for r in per_query]


def freeze_v2(run_tags: list[str]) -> None:
    """V2 双跑 → contracts/rag-baseline-eval64-v2.json（draft:false，格式承 r23_freeze_eval64）。"""
    from app.config import settings

    if len(run_tags) != 2:
        raise SystemExit(f"freezev2 需要恰好 2 个 run tags（determinism 双跑）: {run_tags}")
    runs = {}
    for t in run_tags:
        with open(os.path.join(V2_RUNS_DIR, f"{t}.json"), encoding="utf-8") as f:
            runs[t] = json.load(f)
    run1, run2 = runs[run_tags[0]], runs[run_tags[1]]
    pq1, pq2 = run1["per_query"], run2["per_query"]
    n = len(pq1)
    hit5 = sum(1 for r in pq1 if r["hit@5"])
    hit3 = sum(1 for r in pq1 if r["hit@3"])
    mrr5 = round(sum(r["rr@5"] for r in pq1) / n, 4)
    fd: dict[int, int] = {}
    for r in pq1:
        fd[r["final_docs"]] = fd.get(r["final_docs"], 0) + 1

    base = _summarize(pq1, run_tags[0], run1["mode_note"], TOP_K_EVAL)
    det = {
        "runs": list(run_tags),
        "hit_rate_equal": base["hit_rate@5"] == _summarize(pq2, run_tags[1], "", TOP_K_EVAL)["hit_rate@5"],
        "mrr_equal": round(sum(r["rr@5"] for r in pq1) / n, 4) == round(sum(r["rr@5"] for r in pq2) / n, 4),
        "per_query_identical": _fingerprint(pq1) == _fingerprint(pq2),
        "note": "新尺无跨代际参照（本冻结即代际起点）；复现性以双跑逐位一致为准",
    }

    with open(run1["eval_set"], "rb") as f:
        set_sha = hashlib.sha256(f.read()).hexdigest()
    with open(run1["eval_set"], encoding="utf-8") as f:
        set_meta = json.load(f)["meta"]
    set_file_rel = os.path.relpath(run1["eval_set"], os.path.dirname(BASE_DIR)).replace("\\", "/")

    params = dict(run1["params"])
    params["rerank_cliff_v2"] = bool(getattr(settings, "RERANK_CLIFF_V2", False))  # 冻结时产线实况

    contract = {
        "plan_id": "reshape-r-eval64-v2",
        "change_order": V2_CHANGE_ORDER,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": run1["git_rev"],
        "draft": False,
        "frozen_by": "W-NEXT-EVAL64V2-001（build_eval_set64.py --mode freezev2）",
        "eval_set": {
            "file": set_file_rel,
            "sha256": set_sha,
            "n": n,
            "seed": set_meta.get("in_set", {}).get("seed"),
            "query_face": "冻结复用 V1（禁从目标块循环提取）；case 顺序=V1 文件顺序（v1_idx 对齐）",
            "golden_form": "content_block primary（逐字含问句或直接回答该问句的 chunk）；module card 降为次级指标",
            "golden_type_distribution": set_meta.get("golden_type_distribution"),
            "golden_double_key": ["chunk_id", "doc_sha256(sha256(gt_content utf-8))"],
            "builder": "build_eval_set64.py --mode buildv2（CO-EVAL64V2-001，V1 模式零改动）",
        },
        "params": params,
        "baseline": {
            "tag": run_tags[0],
            "n": n,
            "top_k": TOP_K_EVAL,
            "hit_rate@5": round(hit5 / n, 4),
            "mrr@5": mrr5,
            "hit@3": round(hit3 / n, 4),
            "by_golden_type": base.get("by_golden_type"),
            "module_level_secondary": base.get("module_level_secondary"),
            "runs_reference": [f"edu-agent/scripts/eval/data/r64v2_runs/{t}.json" for t in run_tags],
            "cliff_behavior": {
                "final_docs_dist": {str(k): v for k, v in sorted(fd.items())},
                "note": "V2 断崖（RERANK_CLIFF_V2=True, quant=0.60）现产线实况",
            },
        },
        "thresholds": {
            "RAG_EVAL_HIT_RATE_MIN": round(hit5 / n - 0.02, 4),
            "RAG_EVAL_MRR_MIN": round(mrr5 - 0.02, 4),
            "rule": ("基线-0.02（持续回归下限）；pre-fix 现产线数字即新尺起点，无目标预设"
                     "（CO-EVAL64V2-001 §3）；门禁适用范围裁定权在编排者"),
        },
        "metric_scope": ("实时端到端检索链(retriever.retrieve_three_channel 全链: 召回150→rerank20→断崖→top5), "
                          "禁止在冻结 candidates 上算指标"),
        "determinism_check": det,
        "attribution_reference": {
            "evidence_base": [
                "edu-agent/scripts/eval/data/r24_runs/r24_worst10_probe64.json",
                "edu-agent/scripts/eval/data/r24_runs/r24_rank_probe_probe64.json",
            ],
            "form_mismatch_evidence": "V1 golden 89%(57/64) 为 course_module 路由卡（2026-09-19 Milvus 复核）",
            "worst10_alignment": "worst-10 的 rerank top1(score=1.0) 逐字原题块 == V1 source_chunk_id == V2 golden，10/10 对齐",
            "v1_ruler_on_v2_cliff": "同产线 V1 尺对照 run 见完成报告（r64v1_ctrl_run1），两尺禁互相换算",
        },
        "ruler_note": ("本契约=内容块主尺（eval64-v2）；旧路由卡尺 contracts/rag-baseline-eval64.json "
                        "零改动保留作对照；两尺并行禁互相换算"),
        "id_map_note": "R03 迁移须输出 old→new chunk_id id_map 落盘; golden 双键中 doc_sha256 为迁移后解析兜底键",
    }
    with open(V2_CONTRACT_PATH, "w", encoding="utf-8") as f:
        json.dump(contract, f, ensure_ascii=False, indent=2)
    b = contract["baseline"]
    print(f"[freezev2] → {V2_CONTRACT_PATH}")
    print(f"[freezev2] baseline hit_rate@5={b['hit_rate@5']} mrr@5={b['mrr@5']} hit@3={b['hit@3']} n={n} "
          f"dist={contract['eval_set']['golden_type_distribution']} "
          f"det={det['per_query_identical']} cliff_v2={params['rerank_cliff_v2']}")
    if base.get("module_level_secondary"):
        print(f"[freezev2] module_level_secondary={base['module_level_secondary']}")


# ============================================================
# V3 改写（EVAL64V3 任务①）：LLM 逐条改写 query（deepseek-flash，非流式 thinking disabled）
# ============================================================

V3_REWRITE_MODEL = "strong"   # LLM_MODEL_STRONG=deepseek-flash（.env），call_chat 非流式路径统一注入 thinking=disabled
V3_REWRITE_TEMPERATURE = 0.3
V3_REWRITE_MAX_TOKENS = 400
V3_REWRITE_TIMEOUT = 90.0


def _v3_rewrite_prompt(v2_query: str, style: str,
                       violations: list | None = None, prev_raw: str | None = None) -> str:
    """改写 prompt：同义不同形；禁新实体；长度 ±50%；风格按索引确定轮换（口语/正式混合）。"""
    p = (
        "你是检索评估集的问句改写器。把下面的问句改写成「同义不同形」的新问句：\n"
        "1. 语义与原问句完全相同：提问意图、限定条件、所问内容都不得增减；\n"
        "2. 严禁引入原句没有的实体、专有名词、数字或选项内容；\n"
        "3. 必须换句式/换同义词/调整语序，与原句的字面重叠越低越好（真改写，不是微调）；\n"
        "4. 长度在原句的 ±50% 以内；\n"
        f"5. 风格要求：{style}。\n"
        "输出只含一个 JSON 对象，不要任何解释或代码块标记：\n"
        '{"v3_query": "改写后的问句", "relevance": <1-5 整数，改写与原问句的语义相关度自评>, '
        '"rationale": "不超过30字的改写理由"}\n\n'
        f"原问句：{v2_query}"
    )
    if violations:
        p += (f"\n\n你上一次的改写未通过自动校验：{';'.join(violations)}。"
              f"上次输出：{str(prev_raw or '')[:300]}\n请修正问题后重新只输出 JSON。")
    return p


def _parse_rewrite_json(raw: str) -> dict | None:
    """解析 LLM 输出（容忍 ```json 围码/前后杂文本）；字段非法返回 None。"""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw or "").strip(), flags=re.S).strip()
    m = re.search(r"\{.*\}", t, flags=re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    q = str(obj.get("v3_query") or "").strip()
    rel = obj.get("relevance")
    if not q or isinstance(rel, bool) or not isinstance(rel, int) or not (1 <= rel <= 5):
        return None
    return {"v3_query": q[:QUERY_MAX_LEN * 2], "relevance": rel,
            "rewrite_rationale": str(obj.get("rationale") or "")[:200]}


def rewrite_v3(in_set: str = V2_SET_PATH, limit: int | None = None) -> dict:
    """任务①：64 条 query 逐条 LLM 改写 → data/r64v3_rewrite_records.json。

    每条 {idx, v2_query, v3_query, relevance, rewrite_rationale, golden(继承自 V2),
    status(pass|violation|failed), violations, attempts, style, model}。
    防退化护栏在落记录前先跑（回炉：violation 反馈进 prompt 重改，≤V3_REWRITE_RETRY 次）；
    仍违规定格 violation（buildv3 剔除计数，不凑数）；LLM 调用异常重试由
    call_chat_with_retry 承担，穷尽后标 failed。断点续跑：已有记录按 idx 跳过。
    脱敏：记录与日志零密钥（key 只在进程内 settings）。"""
    from app.chat.generator import _ChatClient

    t0 = time.perf_counter()
    with open(in_set, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    done: dict = {}
    if os.path.exists(V3_REWRITE_PATH):  # 断点续跑
        with open(V3_REWRITE_PATH, encoding="utf-8") as f:
            done = {r["idx"]: r for r in json.load(f)["records"]}
        print(f"[rewritev3] 续跑：已有 {len(done)} 条记录")
    client = _ChatClient.get()
    n_total = len(cases) if limit is None else min(limit, len(cases))
    records: list = list(done.values())
    for idx in range(n_total):
        if idx in done:
            continue
        vc = cases[idx]
        style = "口语化（像学员随口提问）" if idx % 2 == 0 else "正式（书面提问）"
        violations: list = []
        prev_raw = None
        rec = None
        for attempt in range(1 + V3_REWRITE_RETRY):
            try:
                raw = client.call_chat_with_retry(
                    messages=[{"role": "user",
                               "content": _v3_rewrite_prompt(vc["query"], style, violations, prev_raw)}],
                    model=V3_REWRITE_MODEL, temperature=V3_REWRITE_TEMPERATURE,
                    max_tokens=V3_REWRITE_MAX_TOKENS, timeout=V3_REWRITE_TIMEOUT)
            except Exception as exc:  # noqa: BLE001  LLM 穷尽失败：标 failed 计数（截断脱敏）
                rec = {"idx": idx, "v2_query": vc["query"], "golden": vc["golden"],
                       "status": "failed", "violations": [f"llm_error:{type(exc).__name__}"],
                       "attempts": attempt + 1, "style": style, "model": V3_REWRITE_MODEL}
                print(f"[rewritev3] {idx + 1}/{n_total} FAILED {type(exc).__name__}", flush=True)
                break
            parsed = _parse_rewrite_json(raw)
            if parsed is None:
                violations, prev_raw = ["json_parse_failed"], raw
                continue
            cand = {"idx": idx, "v2_query": vc["query"], "golden": vc["golden"], **parsed,
                    "style": style, "attempts": attempt + 1, "model": V3_REWRITE_MODEL}
            violations = check_rewrite_guardrails(vc, cand)
            if not violations:
                rec = {**cand, "status": "pass"}
                print(f"[rewritev3] {idx + 1}/{n_total} pass ov={literal_overlap(vc['query'], parsed['v3_query']):.0%} "
                      f"rel={parsed['relevance']} att={attempt + 1}", flush=True)
                break
            violations, prev_raw = violations, raw   # 回炉：违规反馈进下一轮 prompt
        if rec is None:
            rec = {"idx": idx, "v2_query": vc["query"], "golden": vc["golden"],
                   "status": "violation", "violations": violations,
                   "attempts": 1 + V3_REWRITE_RETRY, "style": style, "model": V3_REWRITE_MODEL}
            print(f"[rewritev3] {idx + 1}/{n_total} violation: {violations}", flush=True)
        records.append(rec)
        records.sort(key=lambda r: r["idx"])
        if (idx + 1) % 8 == 0 or idx + 1 == n_total:  # 检查点：每 8 条落盘（限速/中断保护）
            _dump_v3_records(records, n_total)
    summary = _dump_v3_records(records, n_total)
    print(f"[rewritev3] DONE {summary} wall={round(time.perf_counter() - t0, 1)}s → {V3_REWRITE_PATH}")
    return summary


def _dump_v3_records(records: list, n_total: int) -> dict:
    summary = {"n_expected": n_total, "n": len(records),
               "pass": sum(1 for r in records if r["status"] == "pass"),
               "violation": sum(1 for r in records if r["status"] == "violation"),
               "failed": sum(1 for r in records if r["status"] == "failed")}
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "in_set": os.path.relpath(V2_SET_PATH, BASE_DIR).replace("\\", "/"),
        "rewrite_mode": ("llm_rewrite_query_face（同义不同形；golden 冻结不变；"
                         "护栏 G1/G2/G3/G4 回炉≤2 后剔除计数不凑数）"),
        "model": V3_REWRITE_MODEL,
        "thinking": "disabled（call_chat 非流式统一注入）",
        "temperature": V3_REWRITE_TEMPERATURE,
        "guardrails": {"overlap_max": V3_OVERLAP_MAX, "relevance_min": V3_RELEVANCE_MIN,
                       "length_ratio": V3_LENGTH_RATIO, "retries": V3_REWRITE_RETRY},
        "summary": summary,
        "records": records,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(V3_REWRITE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return summary


# ============================================================
# V3 建集（EVAL64V3 任务②③）：护栏校验 + golden 活体归属检查 → r64v3 评估集
# ============================================================

async def build_v3(in_set: str = V2_SET_PATH, rewrite_path: str = V3_REWRITE_PATH) -> None:
    """V3 建集：V2 冻结集 + 改写记录 → data/r64v3_eval_set64.json。

    纪律：golden/gt_content/provenance 逐位继承（golden 不变，只换 query 面）；
    case 顺序=V2 文件顺序（剔除条空缺不补位，不凑数）；护栏三条全部复检 +
    Milvus 活体 golden 归属检查（内容 sha 漂移即剔除——防语料再入库漂移带入测量）。
    """
    t0 = time.perf_counter()
    with open(in_set, encoding="utf-8") as f:
        v2 = json.load(f)
    v2_cases: list = v2["cases"]
    with open(rewrite_path, encoding="utf-8") as f:
        recs = {r["idx"]: r for r in json.load(f)["records"]}

    passed = [i for i in range(len(v2_cases)) if recs.get(i, {}).get("status") == "pass"]
    # ---- 活体 golden 归属检查（护栏①的语料侧：双键解析在当前 Milvus 上仍成立）----
    from app.knowledge.importer.loader import COLLECTION_NAME, get_milvus_client

    client = get_milvus_client()
    assert COLLECTION_NAME in [str(c) for c in client.list_collections()], "Milvus 缺 edu_knowledge"
    content_map = _milvus_content_map(client, COLLECTION_NAME,
                                      [v2_cases[i]["golden"]["chunk_id"] for i in passed])
    cases: list = []
    dropped: list = []
    for i in passed:
        vc, rec = v2_cases[i], recs[i]
        gid = vc["golden"]["chunk_id"]
        cur = content_map.get(gid)
        if cur is None:
            dropped.append({"idx": i, "reason": "golden_not_in_milvus", "chunk_id": gid})
            continue
        if sha256_utf8(cur) != vc["golden"]["doc_sha256"]:
            dropped.append({"idx": i, "reason": "golden_content_drift", "chunk_id": gid})
            continue
        if rec["v2_query"] != vc["query"]:
            dropped.append({"idx": i, "reason": "v2_query_mismatch_vs_v2_set"})
            continue
        case = assemble_v3_case(vc, rec)
        errs = validate_case_v3(case)
        if errs:
            dropped.append({"idx": i, "reason": "validate_failed", "errors": errs})
            continue
        cases.append(case)
    n = len(v2_cases)
    dropped_pre = n - len(passed)
    floor = math.ceil(RESOLVE_RATIO_FLOOR * n)
    below_floor = len(cases) < floor

    git_rev = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             cwd=BASE_DIR).stdout.strip()
    meta = {
        "builder": "build_eval_set64.py --mode buildv3",
        "purpose": ("EVAL64V3（承接 EVAL64V2 P0-①）：V2 尺贴天花板根因=golden 取自 query 源块"
                    "（子串保底乐观）。V3 改写 query 面（同义不同形），golden 不变——"
                    "创造真实 headroom，让检索质量差异可测量"),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": git_rev,
        "in_set": {"file": os.path.relpath(in_set, BASE_DIR).replace("\\", "/"),
                   "n": n, "sha256": None, "builder": v2.get("meta", {}).get("builder")},
        "rewrite_records": os.path.relpath(rewrite_path, BASE_DIR).replace("\\", "/"),
        "query_face_policy": ("LLM 改写（deepseek-flash，thinking disabled，温度"
                              f"{V3_REWRITE_TEMPERATURE}，风格口语/正式按 idx 轮换）；"
                              "golden/gt_content/provenance 逐位继承；case 顺序=V2 文件顺序"),
        "n_cases": len(cases),
        "guardrail_stats": {
            "in_v2": n,
            "rewrite_pass": len(passed),
            "dropped_rewrite_violation": sum(1 for r in recs.values() if r["status"] == "violation"),
            "dropped_rewrite_failed": sum(1 for r in recs.values() if r["status"] == "failed"),
            "dropped_build_stage": len(dropped),
            "dropped_detail": dropped,
            "final": len(cases),
            "floor": floor,
            "below_floor": below_floor,
            "no_padding": "剔除条不补位不凑数",
        },
        "golden_double_key": ["chunk_id", "doc_sha256(sha256(gt_content utf-8))"],
        "golden_inheritance": "golden/gt_content 与 V2 集逐位相同（建集时活体 sha 复核）",
        "anti_circle_invariants": [
            "V3 query 面由 LLM 改写，禁与 v2_query 字面重叠 ≥60%（护栏②）",
            "W3' 反向不变量：v3 query 不得仍是 golden 子串（假改写拒绝）",
            "G1：golden 双键与 V2 集逐键相等（query 改写不得改变 golden 归属）",
        ],
        "wall_seconds": round(time.perf_counter() - t0, 1),
    }
    out = {"meta": meta, "cases": cases}
    with open(V3_SET_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[buildv3] in={n} pass={len(passed)} final={len(cases)} dropped_build={len(dropped)} "
          f"(violation={meta['guardrail_stats']['dropped_rewrite_violation']}"
          f" failed={meta['guardrail_stats']['dropped_rewrite_failed']}) → {V3_SET_PATH}")
    if below_floor:
        print(f"[buildv3] ⚠ final {len(cases)} < floor {floor}（90% 地板）——如实落盘并在报告标注，"
              "先上报编排者，不凑数")
    print(f"[buildv3] wall={meta['wall_seconds']}s")


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
    ap = argparse.ArgumentParser(description="R22 去圆环评估集构造 + 头寸测量"
                                             "（+V2 golden 形态重铸 CO-EVAL64V2-001 +V3 query 面改写 EVAL64V3）")
    ap.add_argument("--mode", required=True,
                    choices=["build", "measure", "position", "spotcheck", "recallprobe",
                             "buildv2", "freezev2", "rewritev3", "buildv3"])
    ap.add_argument("--tag", default="run")
    ap.add_argument("--limit", type=int, default=64)
    ap.add_argument("--manual-n", type=int, default=40)
    ap.add_argument("--graded", action="store_true", help="measure 用分级窗口 top_k=final_max_k=10")
    ap.add_argument("--group-hit", action="store_true",
                    help="measure 启用 CO-IDX31-GROUPHIT-001 组命中（仅 verbatim_dup_count>1 的 golden 生效；默认关，V1/V2 单键口径零影响）")
    ap.add_argument("--runs", nargs="*", help="position/freezev2 模式: 参与汇总的 run tags")
    ap.add_argument("--graded-tag", default=None, help="position 模式: 分级窗口 run tag")
    ap.add_argument("--in-set", default=None,
                    help="buildv2: V1 集路径（默认 V1 冻结集）；rewritev3/buildv3: V2 集路径"
                         "（默认 V2 冻结集 r64v2_eval_set64.json）")
    ap.add_argument("--set", dest="set_path", default=None,
                    help="measure: 评估集路径（缺省=V1 集不变；V2 集落 r64v2_runs/；"
                         "r64v3* 前缀集落 r64v3_runs/）")
    args = ap.parse_args()

    if args.mode == "build":
        asyncio.run(build(args.limit, args.manual_n))
        return 0
    if args.mode == "buildv2":
        asyncio.run(build_v2(args.in_set or V1_SET_PATH))
        return 0
    if args.mode == "rewritev3":
        rewrite_v3(args.in_set or V2_SET_PATH, limit=args.limit)
        return 0
    if args.mode == "buildv3":
        asyncio.run(build_v3(args.in_set or V2_SET_PATH))
        return 0
    if args.mode == "measure":
        measure(args.tag, args.graded, args.set_path, group_hit=args.group_hit)
        return 0
    if args.mode == "freezev2":
        freeze_v2(args.runs or [])
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
