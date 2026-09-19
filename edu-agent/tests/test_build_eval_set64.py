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


# ==================================================================
# V2（CO-EVAL64V2-001）：golden 形态重铸——纯逻辑层单测（全部离线）
# ==================================================================

def _qchunk(cid: str, content: str, bank: str = "academic_planning_bank") -> dict:
    return {"chunk_id": cid, "bank": bank, "content": content, "norm": m.norm_text(content)}


_QUESTION = ("【单选题】题目：制定学期计划时最应优先考虑什么？\n选项：\nA. 目标\nB. 休息\n"
             "答案：A\n解析：计划以目标为先。")


def _v1_cross_case() -> dict:
    content = "课程模块：学业规划方法与目标管理\n关键词：学业规划、时间管理\n课时：8"
    return {
        "query": "制定学期计划时最应优先考虑什么？",
        "golden": m.make_golden("_default:mod01:1", content),
        "gt_content": content,
        "independence": "cross",
        "source": "question_bank->course_module",
        "source_chunk_id": "_default:qsrc01:1",
        "source_bank": "academic_planning_bank",
        "series_code": "academic_planning",
        "matched_terms": ["学业规划", "时间管理"],
        "match_note": "overlap=2_margin=2",
    }


def _resolved_row(v1_case: dict, **kw) -> dict:
    """走真解析器生成 row（保证单测与实现同源），kw 可覆写解析输入。"""
    qidx = kw.pop("question_index", None) or [_qchunk(v1_case["source_chunk_id"], _QUESTION)]
    qcontent = {qi["chunk_id"]: qi["content"] for qi in qidx}
    cmap = kw.pop("content_map", None)
    if cmap is None:
        cmap = {v1_case["golden"]["chunk_id"]: v1_case["gt_content"]}
        cmap.update(qcontent)
    row, reason = m.resolve_golden_v2(v1_case, qidx, qcontent, cmap)
    assert reason is None and row is not None
    return row


# ---- norm_text / find_verbatim_candidates ----
def test_norm_text_matches_v1_query_key_semantics() -> None:
    import re as _re
    v1_key = _re.sub(r"[\s\W_]+", "", "制定学期计划时，最应优先考虑什么？".lower())
    assert m.norm_text("制定学期计划时，最应优先考虑什么？") == v1_key
    assert m.norm_text("  ABC def! ") == "abcdef"
    assert m.norm_text(None) == ""


def test_find_verbatim_candidates_sorted_and_deterministic() -> None:
    qidx = [
        _qchunk("_default:zzz9:1", "题干：简述该场景下的处理顺序。答案A"),
        _qchunk("_default:aaa1:1", "前文 简述该场景下的处理顺序。 后文"),
        _qchunk("_default:mmm5:1", "完全无关内容"),
    ]
    cands = m.find_verbatim_candidates(m.norm_text("简述该场景下的处理顺序。"), qidx)
    assert cands == ["_default:aaa1:1", "_default:zzz9:1"]  # chunk_id 排序，确定性
    assert m.find_verbatim_candidates("", qidx) == []
    assert m.find_verbatim_candidates("不存在的问句", qidx) == []


# ---- resolve_golden_v2：cross 路径 ----
def test_resolve_v2_cross_source_block_wins_with_declaration() -> None:
    v1 = _v1_cross_case()
    qidx = [_qchunk(v1["source_chunk_id"], _QUESTION)]
    row, reason = m.resolve_golden_v2(
        v1, qidx, {v1["source_chunk_id"]: _QUESTION},
        {v1["golden"]["chunk_id"]: v1["gt_content"]})
    assert reason is None
    assert row["golden_type"] == "content_block"
    assert row["content_match_form"] == "verbatim"
    assert row["golden_is_query_source"] is True
    assert row["golden_chunk_id"] == v1["source_chunk_id"]
    assert row["verbatim_dup_count"] == 1


def test_resolve_v2_cross_duplicate_block_falls_back_deterministic() -> None:
    v1 = _v1_cross_case()
    dup_a, dup_b = "_default:aaa1:1", "_default:bbb2:1"
    qidx = [_qchunk(dup_b, _QUESTION, bank="x_bank"), _qchunk(dup_a, _QUESTION, bank="y_bank")]
    row, reason = m.resolve_golden_v2(
        v1, qidx, {dup_a: _QUESTION, dup_b: _QUESTION}, {})
    assert reason is None
    assert row["golden_type"] == "content_block"
    assert row["golden_is_query_source"] is False       # source 块不在语料（被删场景）
    assert row["golden_chunk_id"] == dup_a              # 排序第一，确定性
    assert row["verbatim_dup_count"] == 2


def test_resolve_v2_cross_module_card_fallback_keeps_v1_golden() -> None:
    v1 = _v1_cross_case()
    row, reason = m.resolve_golden_v2(v1, [], {}, {v1["golden"]["chunk_id"]: v1["gt_content"]})
    assert reason is None
    assert row["golden_type"] == "module_card"
    assert row["golden_chunk_id"] == v1["golden"]["chunk_id"]


def test_resolve_v2_cross_unresolved_when_nothing_verifiable() -> None:
    v1 = _v1_cross_case()
    row, reason = m.resolve_golden_v2(v1, [], {}, {})   # 无逐字块 + V1 golden 无法 sha 复核
    assert row is None
    assert reason == "no_verbatim_block_and_v1_golden_unverifiable"


# ---- resolve_golden_v2：manual 路径 ----
def _v1_manual_case() -> dict:
    doc = "## 4. 实现规划要点\n- knowledge_import_task 字段设计：task_id PK、visibility"
    return {
        "query": "请使用 knowledge_import 工具把示例文档导入知识库",
        "golden": m.make_golden("_default:doc09:2", doc),
        "gt_content": doc,
        "independence": "manual",
        "source": "chat_message",
        "source_message_id": "m_79ad5f8b2738",
        "cited_rank": 1,
    }


def test_resolve_v2_manual_production_cited_primary() -> None:
    v1 = _v1_manual_case()
    row, reason = m.resolve_golden_v2(v1, [], {}, {v1["golden"]["chunk_id"]: v1["gt_content"]})
    assert reason is None
    assert row["golden_type"] == "content_block"
    assert row["content_match_form"] == "production_cited"
    assert row["golden_chunk_id"] == v1["golden"]["chunk_id"]


def test_resolve_v2_manual_drift_falls_back_to_verbatim() -> None:
    v1 = _v1_manual_case()
    qidx = [_qchunk("_default:qqq1:1", f"题目：{v1['query']} 答案：A")]
    row, reason = m.resolve_golden_v2(v1, qidx, {"_default:qqq1:1": qidx[0]["content"]}, {})
    assert reason is None
    assert row["content_match_form"] == "verbatim"
    assert row["golden_is_query_source"] is False


def test_resolve_v2_manual_unresolved_on_drift_and_no_verbatim() -> None:
    v1 = _v1_manual_case()
    row, reason = m.resolve_golden_v2(v1, [], {}, {})
    assert row is None and reason == "manual_golden_drift_and_no_verbatim_block"


# ---- assemble_v2_case：provenance 继承 + 双键 ----
def test_assemble_v2_case_inherits_provenance_and_relabels_source() -> None:
    v1 = _v1_cross_case()
    row = _resolved_row(v1)
    row["v1_idx"] = 7
    case = m.assemble_v2_case(v1, row)
    assert case["query"] == v1["query"]                      # query 面冻结复用
    for k in ("source_chunk_id", "source_bank", "series_code", "matched_terms"):
        assert case[k] == v1[k]                              # provenance 全继承
    assert case["source"] == "question_bank->content_block"  # golden 派生来源如实改标
    assert case["v1_golden_chunk_id"] == v1["golden"]["chunk_id"]
    assert case["v1_idx"] == 7
    assert case["golden"]["doc_sha256"] == m.sha256_utf8(case["gt_content"])  # 双键自洽
    assert m.validate_case_v2(case) == []


def test_assemble_v2_case_module_card_source_label_unchanged() -> None:
    v1 = _v1_cross_case()
    row, _ = m.resolve_golden_v2(v1, [], {}, {v1["golden"]["chunk_id"]: v1["gt_content"]})
    case = m.assemble_v2_case(v1, row)
    assert case["source"] == v1["source"]                    # module_card 兜底不改标
    assert m.validate_case_v2(case) == []


# ---- validate_case_v2：W1~W5 + V1 规则在 module_card 路径全保留 ----
def _v2_content_case() -> dict:
    v1 = _v1_cross_case()
    row = _resolved_row(v1)
    return m.assemble_v2_case(v1, row)


def test_validate_v2_rejects_missing_golden_type() -> None:
    case = _v2_content_case()
    del case["golden_type"]
    assert any(e.startswith("W1") for e in m.validate_case_v2(case))


def test_validate_v2_rejects_bad_content_match_form() -> None:
    case = _v2_content_case()
    case["content_match_form"] = "vibes"
    assert any(e.startswith("W2") for e in m.validate_case_v2(case))


def test_validate_v2_rejects_false_verbatim_claim() -> None:
    case = _v2_content_case()
    case["gt_content"] = "与问句完全无关的内容块"      # norm(query) 不在内容里
    case["golden"] = m.make_golden(case["golden"]["chunk_id"], case["gt_content"])
    errs = m.validate_case_v2(case)
    assert any(e.startswith("W3") for e in errs)


def test_validate_v2_requires_query_source_declaration_on_cross() -> None:
    case = _v2_content_case()
    case["golden_is_query_source"] = "yes"               # 非布尔：声明无效
    assert any(e.startswith("W4") for e in m.validate_case_v2(case))


def test_validate_v2_requires_manual_provenance_on_production_cited() -> None:
    v1 = _v1_manual_case()
    row, _ = m.resolve_golden_v2(v1, [], {}, {v1["golden"]["chunk_id"]: v1["gt_content"]})
    case = m.assemble_v2_case(v1, row)
    del case["source_message_id"]
    del case["cited_rank"]
    assert sum(1 for e in m.validate_case_v2(case) if e.startswith("W5")) == 2


def test_validate_v2_module_card_keeps_v1_anti_circle_rules() -> None:
    v1 = _v1_cross_case()
    row, _ = m.resolve_golden_v2(v1, [], {}, {v1["golden"]["chunk_id"]: v1["gt_content"]})
    case = m.assemble_v2_case(v1, row)
    case["source_chunk_id"] = case["golden"]["chunk_id"]  # golden==source 圆环
    assert any("同 chunk" in e for e in m.validate_case_v2(case))
    case2 = m.assemble_v2_case(v1, row)
    case2["query"] = case2["gt_content"][:40]             # query 为 golden 子串
    assert any("子串" in e for e in m.validate_case_v2(case2))
    case3 = m.assemble_v2_case(v1, row)
    case3["matched_terms"] = []                           # 互证证据缺失
    assert any("matched_terms" in e for e in m.validate_case_v2(case3))


def test_validate_v2_content_block_allows_verbatim_substring() -> None:
    # 与 V1 的关键差异：verbatim 内容块 golden 的定义即「逐字含问句」——
    # query 归一后 ⊆ golden 不再是违规（变更单 §2.2 显式裁定），但必须带 W4 声明
    case = _v2_content_case()
    assert m.norm_text(case["query"]) in m.norm_text(case["gt_content"])
    assert m.validate_case_v2(case) == []


# ---- assert_type_distribution：R22 反哺硬断言 ----
def test_type_distribution_assertion_passes_at_threshold() -> None:
    cases = [{"golden_type": "content_block"}] * 6 + [{"golden_type": "module_card"}] * 4
    dist = m.assert_type_distribution(cases)              # 60% 恰好达标
    assert dist["content_block_ratio"] == 0.6


def test_type_distribution_assertion_blocks_below_60pct() -> None:
    cases = [{"golden_type": "content_block"}] * 59 + [{"golden_type": "module_card"}] * 41
    try:
        m.assert_type_distribution(cases)                 # 59/100 < 60%
        raise AssertionError("占比 59% 未触发 SystemExit")
    except SystemExit as exc:
        assert "类型分布断言失败" in str(exc)


def test_type_distribution_assertion_blocks_empty_set() -> None:
    try:
        m.assert_type_distribution([])
        raise AssertionError("空集未触发 SystemExit")
    except SystemExit as exc:
        assert "空集" in str(exc)


# ---- dedup_and_cap 与 V2 行的配合（golden 碰撞显式拒绝由 build_v2 负责）----
def test_dedup_and_cap_works_on_v2_rows() -> None:
    rows = [
        {"query_key": f"q{i}", "cap_key": f"g{i}", "session_key": None,
         "golden_type": "content_block"} for i in range(5)
    ]
    rows.append(dict(rows[0], query_key="q0"))            # 重复 query
    picked, stats = m.dedup_and_cap(rows, total=64)
    assert len(picked) == 5 and stats["dup_query_dropped"] == 1


# ==================================================================
# V3（EVAL64V3）：query 面改写护栏——纯逻辑层单测（全部离线）
# ==================================================================

_V2Q = "关于回归分析，下列说法正确的是？"
_V3Q = "回归分析相关的问题，哪个选项的说法是对的？"
_REWITTEN_CONTENT = ("【多选题】题目：关于回归分析，下列说法正确的是：\n选项：\nA. 可以用于刻画变量之间的关系\n"
                     "答案：A,C\n解析：回归既可线性也可非线性。")


def _v2_case_for_v3() -> dict:
    """V2 verbatim 内容块 case（golden=含 v2_query 的源块）。"""
    return {
        "query": _V2Q,
        "golden": m.make_golden("_default:6ce44e88:1", _REWITTEN_CONTENT),
        "gt_content": _REWITTEN_CONTENT,
        "independence": "cross",
        "source": "question_bank->content_block",
        "source_chunk_id": "_default:6ce44e88:1",
        "golden_type": "content_block",
        "content_match_form": "verbatim",
        "golden_is_query_source": True,
    }


def _pass_rec(v2_case: dict, v3q: str = _V3Q, relevance: int = 5) -> dict:
    return {"idx": 0, "v2_query": v2_case["query"], "golden": v2_case["golden"],
            "v3_query": v3q, "relevance": relevance,
            "rewrite_rationale": "换句式换同义词", "style": "口语化",
            "attempts": 1, "model": "deepseek-flash"}


# ---- literal_overlap：护栏② 计量单元 ----
def test_literal_overlap_identical_is_one() -> None:
    assert m.literal_overlap(_V2Q, _V2Q) == 1.0


def test_literal_overlap_disjoint_is_zero() -> None:
    assert m.literal_overlap("线性代数矩阵", "英国文学诗歌") == 0.0


def test_literal_overlap_partial_bounded_and_deterministic() -> None:
    ov = m.literal_overlap("制定学期计划的方法", "学期计划制定技巧")
    assert 0.0 < ov < 1.0
    assert ov == m.literal_overlap("制定学期计划的方法", "学期计划制定技巧")
    assert m.char_bigrams("ab") == {"ab"}
    assert m.char_bigrams("a b") == {"ab"}


# ---- 护栏 G1：双键 golden 归属不变 ----
def test_guardrail_g1_rejects_golden_mutation() -> None:
    v2 = _v2_case_for_v3()
    rec = _pass_rec(v2)
    rec["golden"] = m.make_golden("_default:mutated:9", "别的块")
    errs = m.check_rewrite_guardrails(v2, rec)
    assert any(e.startswith("G1") for e in errs)


def test_guardrail_g1_passes_on_inherited_golden() -> None:
    assert not any(e.startswith("G1") for e in
                   m.check_rewrite_guardrails(_v2_case_for_v3(), _pass_rec(_v2_case_for_v3())))


# ---- 护栏 G2：真改写非微调（<60%）----
def test_guardrail_g2_rejects_light_edit() -> None:
    v2 = _v2_case_for_v3()
    rec = _pass_rec(v2, v3q="关于回归分析，下列哪些说法是正确的？")   # 只微调
    errs = m.check_rewrite_guardrails(v2, rec)
    assert any(e.startswith("G2") for e in errs)


def test_guardrail_g2_boundary_just_under_threshold_passes() -> None:
    # 构造 v2 10 个 bigram、保留 5 个（50% < 60% 阈值）的边界样本
    v2q = "abcdefghijk"
    v3q = "abcdefVWXYZ"
    v2 = _v2_case_for_v3()
    v2["query"] = v2q
    rec = _pass_rec(v2, v3q=v3q)
    errs = m.check_rewrite_guardrails(v2, rec)
    assert m.literal_overlap(v2q, v3q) == 0.5
    assert not any(e.startswith("G2") for e in errs)


def test_guardrail_g2_rejects_at_threshold() -> None:
    v2q = "abcdefghijk"
    v3q = "abcdefgVWXY"         # 6/10 = 60% 恰在阈值 → 拒（<60% 才过）
    v2 = _v2_case_for_v3()
    v2["query"] = v2q
    rec = _pass_rec(v2, v3q=v3q)
    errs = m.check_rewrite_guardrails(v2, rec)
    assert m.literal_overlap(v2q, v3q) == 0.6
    assert any(e.startswith("G2") for e in errs)


# ---- 护栏 G3：LLM 自评相关性 ≥4/5 ----
def test_guardrail_g3_rejects_low_relevance() -> None:
    errs = m.check_rewrite_guardrails(_v2_case_for_v3(), _pass_rec(_v2_case_for_v3(), relevance=3))
    assert any(e.startswith("G3") for e in errs)
    errs_bad = m.check_rewrite_guardrails(_v2_case_for_v3(),
                                          _pass_rec(_v2_case_for_v3(), relevance="5"))
    assert any(e.startswith("G3") for e in errs_bad)   # 非整数自评 = 非法


def test_guardrail_g3_passes_at_floor() -> None:
    errs = m.check_rewrite_guardrails(_v2_case_for_v3(), _pass_rec(_v2_case_for_v3(), relevance=4))
    assert not any(e.startswith("G3") for e in errs)


# ---- 护栏 G4：长度 ±50% + 非空非全同 ----
def test_guardrail_g4_rejects_length_drift() -> None:
    v2 = _v2_case_for_v3()
    errs = m.check_rewrite_guardrails(v2, _pass_rec(v2, v3q="回归" + "很长" * 30))   # 超长
    assert any(e.startswith("G4") for e in errs)
    errs2 = m.check_rewrite_guardrails(v2, _pass_rec(v2, v3q="回归对不对"))          # 过短
    assert any(e.startswith("G4") for e in errs2)


def test_guardrail_g4_rejects_empty_or_identical() -> None:
    v2 = _v2_case_for_v3()
    assert any(e.startswith("G4") for e in m.check_rewrite_guardrails(v2, _pass_rec(v2, v3q="  ")))
    assert any("全同" in e for e in m.check_rewrite_guardrails(v2, _pass_rec(v2, v3q=v2["query"])))


def test_guardrails_all_pass_for_good_rewrite() -> None:
    assert m.check_rewrite_guardrails(_v2_case_for_v3(), _pass_rec(_v2_case_for_v3())) == []


# ---- assemble_v3_case + validate_case_v3 ----
def test_assemble_v3_case_swaps_query_keeps_golden_bitwise() -> None:
    v2 = _v2_case_for_v3()
    rec = _pass_rec(v2)
    case = m.assemble_v3_case(v2, rec)
    assert case["query"] == _V3Q
    assert case["v2_query"] == v2["query"]
    assert case["golden"] == v2["golden"]                    # golden 逐位不变
    assert case["gt_content"] == v2["gt_content"]
    assert case["rewrite_v3"]["literal_overlap"] == m.literal_overlap(v2["query"], _V3Q)
    assert m.validate_case_v3(case) == []


def test_validate_v3_relaxes_w3_substring_claim() -> None:
    # V3 的核心差异：改写 query 不再是 golden 子串——V2 的 W3 断言必须豁免（按设计反转）
    case = m.assemble_v3_case(_v2_case_for_v3(), _pass_rec(_v2_case_for_v3()))
    assert not m.norm_text(case["query"]) in m.norm_text(case["gt_content"])
    assert m.validate_case_v2(case)      # V2 规则下必挂 W3（对照）
    assert [e for e in m.validate_case_v3(case) if e.startswith("W3")] == []


def test_validate_v3_rejects_fake_rewrite_still_substring() -> None:
    # W3' 反向不变量：改写后仍逐字落在 golden 里 = 假改写
    v2 = _v2_case_for_v3()
    rec = _pass_rec(v2, v3q="回归分析")            # 恰为 golden 内容子串
    case = m.assemble_v3_case(v2, rec)
    errs = m.validate_case_v3(case)
    assert any(e.startswith("W3'") for e in errs)


def test_validate_v3_keeps_v2_double_key_and_w_rules() -> None:
    v2 = _v2_case_for_v3()
    case = m.assemble_v3_case(v2, _pass_rec(v2))
    case["golden"]["doc_sha256"] = "0" * 64        # 双键失配仍拒
    assert any(e.startswith("V2") for e in m.validate_case_v3(case))
    case2 = m.assemble_v3_case(v2, _pass_rec(v2))
    case2["content_match_form"] = "vibes"          # W2 仍拒
    assert any(e.startswith("W2") for e in m.validate_case_v3(case2))
    case3 = m.assemble_v3_case(v2, _pass_rec(v2))
    del case3["v2_query"]                          # V3 溯源缺失拒
    assert any("v2_query" in e for e in m.validate_case_v3(case3))


def test_validate_v3_requires_rewrite_rationale() -> None:
    v2 = _v2_case_for_v3()
    case = m.assemble_v3_case(v2, _pass_rec(v2))
    case["rewrite_v3"]["rewrite_rationale"] = ""
    assert any("rewrite_rationale" in e for e in m.validate_case_v3(case))


# ---- _parse_rewrite_json：LLM 输出解析（容错围码/杂文本）----
def test_parse_rewrite_json_tolerates_code_fence() -> None:
    raw = '```json\n{"v3_query": "回归分析里哪个说法对？", "relevance": 5, "rationale": "换问式"}\n```'
    obj = m._parse_rewrite_json(raw)
    assert obj is not None and obj["relevance"] == 5 and obj["v3_query"].startswith("回归")
    obj2 = m._parse_rewrite_json('前言 {"v3_query": "q 句", "relevance": 4, "rationale": "r"} 后记')
    assert obj2 is not None and obj2["v3_query"] == "q 句"


def test_parse_rewrite_json_rejects_bad_fields() -> None:
    assert m._parse_rewrite_json("没有 JSON") is None
    assert m._parse_rewrite_json('{"v3_query": "", "relevance": 5}') is None
    assert m._parse_rewrite_json('{"v3_query": "q", "relevance": 9}') is None
    assert m._parse_rewrite_json('{"v3_query": "q", "relevance": "5"}') is None


# ---- rewrite prompt：禁新实体/风格轮换由 prompt 承载（此处验证回炉反馈注入）----
def test_rewrite_prompt_includes_violation_feedback() -> None:
    p1 = m._v3_rewrite_prompt("原句", "口语化")
    assert "原问句：原句" in p1 and "口语化" in p1 and "严禁引入原句没有的实体" in p1
    p2 = m._v3_rewrite_prompt("原句", "正式", ["G2 字面重叠 90% >= 60%"], '{"v3_query": "抄写"}')
    assert "G2" in p2 and "抄写" in p2       # 回炉反馈进 prompt
