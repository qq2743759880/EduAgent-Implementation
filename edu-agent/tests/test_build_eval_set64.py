# -*- coding: utf-8 -*-
"""R22 build_eval_set64 单测（W-NEXT-R22-001 任务④）。

覆盖：independence 强制 / 去重与配额 / 双键 golden / 反圆环不变量 / 规则改写 /
bank→series 对齐 / 互证匹配边际 / CI 与退化分布判别。
全部离线纯逻辑：不连 Milvus/MySQL，不加载 GPU 模型，不经 LLM。
"""
from __future__ import annotations

import hashlib

from scripts.eval import build_eval_set64 as m


# ------------------------------------------------------------------
# 双键 golden（V2）
# ------------------------------------------------------------------
def test_make_golden_dual_key() -> None:
    content = "【单选题】题目：制定学期计划时最应优先考虑什么？答案：A"
    g = m.make_golden("chunk_abc", content)
    assert g["chunk_id"] == "chunk_abc"
    assert g["doc_sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_validate_case_detects_sha_mismatch() -> None:
    case = _valid_cross_case()
    case["golden"]["doc_sha256"] = "0" * 64
    errs = m.validate_case(case, source_content="source 原文")
    assert any(e.startswith("V2") for e in errs)


# ------------------------------------------------------------------
# independence 强制（V1）+ 溯源（V4）
# ------------------------------------------------------------------
def test_validate_case_rejects_bad_independence() -> None:
    case = _valid_manual_case()
    case["independence"] = "self"   # 圆环自证值，必须拒绝
    errs = m.validate_case(case)
    assert any(e.startswith("V1") for e in errs)


def test_validate_case_requires_manual_provenance() -> None:
    case = _valid_manual_case()
    del case["source_message_id"]
    del case["cited_rank"]
    errs = m.validate_case(case)
    assert any(e.startswith("V4") for e in errs)


# ------------------------------------------------------------------
# 反圆环不变量（V3，Crit-1 承接核心）
# ------------------------------------------------------------------
def test_validate_case_rejects_same_chunk_cross() -> None:
    case = _valid_cross_case()
    case["source_chunk_id"] = case["golden"]["chunk_id"]  # golden==source 即圆环
    errs = m.validate_case(case, source_content="question 原文")
    assert any("V3" in e and "同 chunk" in e for e in errs)


def test_validate_case_rejects_query_substring_of_golden() -> None:
    case = _valid_cross_case()
    case["query"] = case["gt_content"][:40]  # query 变成 golden 子串 = 自匹配保底
    errs = m.validate_case(case, source_content="question 原文")
    assert any("子串" in e for e in errs)


def test_validate_case_rejects_identical_cross_content() -> None:
    case = _valid_cross_case()
    errs = m.validate_case(case, source_content=case["gt_content"])  # golden 内容与 source 相同
    assert any("内容相同" in e for e in errs)


def test_validate_case_requires_cross_match_evidence() -> None:
    case = _valid_cross_case()
    case["matched_terms"] = []
    errs = m.validate_case(case, source_content="question 原文")
    assert any("matched_terms" in e for e in errs)


def test_validate_case_passes_wellformed_both_modes() -> None:
    assert m.validate_case(_valid_manual_case()) == []
    assert m.validate_case(_valid_cross_case(), source_content="question 原文") == []


# ------------------------------------------------------------------
# query 长度（V5）
# ------------------------------------------------------------------
def test_validate_case_rejects_short_query() -> None:
    case = _valid_manual_case()
    case["query"] = "干嘛?"
    errs = m.validate_case(case)
    assert any(e.startswith("V5") for e in errs)


# ------------------------------------------------------------------
# 去重与配额（dedup_and_cap）
# ------------------------------------------------------------------
def test_dedup_drops_duplicate_normalized_query() -> None:
    # 归一（lower+去空白标点）发生在上游 builder，这里传归一后的 query_key
    rows = [
        {"query_key": "abc", "cap_key": "g1", "session_key": "s1"},
        {"query_key": "abc", "cap_key": "g2", "session_key": "s2"},
    ]
    picked, stats = m.dedup_and_cap(rows, total=10)
    assert len(picked) == 1
    assert stats["dup_query_dropped"] == 1


def test_query_key_normalization() -> None:
    import re as _re

    norm = lambda q: _re.sub(r"[\s\W_]+", "", q.lower())  # 与 builder 同口径
    assert norm("制定学期计划时，最应优先考虑什么？") == norm("制定学期计划时最应优先考虑什么")
    assert norm("ABC def!") == "abcdef"


def test_cap_limits_same_golden_chunk() -> None:
    rows = [{"query_key": f"q{i}", "cap_key": "same_golden", "session_key": f"s{i}"}
            for i in range(5)]
    picked, stats = m.dedup_and_cap(rows, total=10)
    assert len(picked) == m.GOLDEN_CAP
    assert stats["golden_cap_dropped"] == 3


def test_session_cap_limits_same_session() -> None:
    rows = [{"query_key": f"q{i}", "cap_key": f"g{i}", "session_key": "one_session"}
            for i in range(5)]
    picked, stats = m.dedup_and_cap(rows, total=10)
    assert len(picked) == m.SESSION_CAP
    assert stats["session_cap_dropped"] == 2


def test_dedup_respects_total_and_order_is_deterministic() -> None:
    rows = [{"query_key": f"q{i}", "cap_key": f"g{i}", "session_key": f"s{i}"} for i in range(10)]
    p1, _ = m.dedup_and_cap(rows, total=4)
    p2, _ = m.dedup_and_cap(rows, total=4)
    assert p1 == p2 and len(p1) == 4


# ------------------------------------------------------------------
# 规则改写（纯 regex，禁 LLM）
# ------------------------------------------------------------------
def test_rewrite_query_strips_pleasantries() -> None:
    assert m.rewrite_query("老师你好，请问制定学期计划时最应优先考虑什么？谢谢") == \
        "制定学期计划时最应优先考虑什么？"
    assert m.rewrite_query("帮我  问一下  Python 列表和元组有什么区别") == \
        "Python 列表和元组有什么区别"


def test_rewrite_query_is_deterministic_and_never_expands() -> None:
    src = "老师请问数据结构怎么复习？？？"
    outs = {m.rewrite_query(src) for _ in range(5)}
    assert len(outs) == 1
    out = outs.pop()
    assert len(out) <= len(src)


# ------------------------------------------------------------------
# bank→series 归一化对齐
# ------------------------------------------------------------------
def test_bank_to_series_alignment() -> None:
    assert m.bank_to_series("academic_planning_bank") == "academic_planning"
    assert m.norm_series_code("academic_planning_advanced") == "academic_planning"
    assert m.norm_series_code("sales_training_foundation") == "sales_training"
    assert m.bank_to_series("postgraduate_math_bank") == m.norm_series_code("postgraduate_math_practice")


# ------------------------------------------------------------------
# 互证匹配（match_module：词重叠 + 次优边际）
# ------------------------------------------------------------------
def _mod(cid: str, title: str, kw: str) -> dict:
    return {"chunk_id": cid, "_match_text": f"{title} {kw}"}


def test_match_module_picks_best_with_margin() -> None:
    mods = [
        _mod("m1", "学业规划方法与目标管理", "学业规划 时间管理"),
        _mod("m2", "全科串讲与模考演练", "模考 复盘"),
    ]
    best, terms, note = m.match_module(["学业规划", "目标管理", "时间管理"], mods)
    assert best is not None and best["chunk_id"] == "m1"
    assert set(terms) == {"学业规划", "目标管理", "时间管理"}
    assert "margin" in note


def test_match_module_rejects_tied_margin() -> None:
    mods = [
        _mod("m1", "学业规划方法", "学业规划 时间管理"),
        _mod("m2", "学业规划进阶", "学业规划 时间管理"),
    ]
    best, _, note = m.match_module(["学业规划", "时间管理", "复习"], mods)
    assert best is None and note == "tied_margin"


def test_match_module_rejects_insufficient_overlap() -> None:
    best, _, note = m.match_module(["量子力学"], [_mod("m1", "模考演练", "模考")])
    assert best is None and note in ("no_overlap", "insufficient_overlap")


def test_match_module_accepts_single_long_term() -> None:
    mods = [
        _mod("m1", "线性代数核心讲义", "线性代数"),
        _mod("m2", "模考演练", "模考"),
    ]
    best, terms, note = m.match_module(["线性代数"], mods)
    assert best is not None and best["chunk_id"] == "m1"
    assert note.startswith("single_long_term")
    # 短单词（<4字）不足以互证 → 拒绝
    best2, _, note2 = m.match_module(["极限"], [_mod("m1", "高等数学极限", "极限")])
    assert best2 is None and note2 == "insufficient_overlap"


# ------------------------------------------------------------------
# 统计：CI / 分布 / 退化判别（Crit-1/Crit-3 形态学）
# ------------------------------------------------------------------
def test_wilson_ci_sanity() -> None:
    lo, hi = m.wilson_ci(0.9688, 32)
    assert 0.8 < lo < 0.9688 < hi <= 1.0
    assert m.wilson_ci(0.5, 0) == (0.0, 1.0)


def test_bootstrap_ci_deterministic_with_seed() -> None:
    vals = [1.0] * 8 + [0.5] * 2
    assert m.bootstrap_ci(vals, seed=1) == m.bootstrap_ci(vals, seed=1)
    lo, hi = m.bootstrap_ci(vals, seed=1)
    assert 0.0 <= lo <= hi <= 1.0


def test_rank_distribution_and_degeneracy() -> None:
    ranks = [1, 1, 1, 2, None]
    hist = m.rank_distribution(ranks, 5)
    assert hist == {"rank1": 3, "rank2": 1, "rank3": 0, "rank4": 0, "rank5": 0, "miss": 1}
    # 圆环自证形态：全 rank1 → mrr==hit_rate → 退化
    deg = m.degeneracy_check(1.0, 1.0, [1] * 32)
    assert deg["verdict"].startswith("degenerate")
    # 有区分度：存在 rank>1 命中
    inf = m.degeneracy_check(0.8, 0.6, [1, 1, 1, 1, 3, 2, None, None, None, None])
    assert inf["verdict"].startswith("informative")


# ------------------------------------------------------------------
# 夹具
# ------------------------------------------------------------------
def _valid_manual_case() -> dict:
    content = "【单选题】题目：Python 列表和元组的区别是什么？\n选项：\nA. 可变性不同\n答案：A"
    return {
        "query": "Python 列表和元组有什么区别",
        "golden": m.make_golden("_default:aa11bb22:1", content),
        "gt_content": content,
        "independence": "manual",
        "source_message_id": "m_abc123",
        "cited_rank": 1,
    }


def _valid_cross_case() -> dict:
    content = "课程模块：学业规划方法与目标管理\n关键词：学业规划、时间管理、目标拆解\n课时：8"
    return {
        "query": "制定学期计划时最应优先考虑什么？",
        "golden": m.make_golden("_default:cc33dd44:2", content),
        "gt_content": content,
        "independence": "cross",
        "source_chunk_id": "question_academic_planning_bank_q001",
        "source_bank": "academic_planning_bank",
        "series_code": "academic_planning",
        "matched_terms": ["学业规划", "时间管理"],
        "match_note": "overlap=2_margin=2",
    }
