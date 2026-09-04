# -*- coding: utf-8 -*-
"""
task-E1 契约测试：AC1 影子不变性 / AC2 对抗集 / AC3 4 维 Judge / AC4 金丝雀 / AC5 回归。
影子/对抗集构造不依赖真实 LLM 或线上 DB，随时可测；4 维 Judge 的 LLM 调用经 scorer 注入。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.auth import UserRole
from app.chat import retriever as R
from scripts.eval import build_adversarial_set
from scripts.eval import canary
from scripts.eval import llm_judge


# ============================================================
# AC1 影子模式：主路径答案不变 + 影子对比异步落库不阻塞
# ============================================================
class TestAC1Shadow:
    async def test_shadow_records_diff_without_blocking(self, monkeypatch):
        monkeypatch.setattr(R.settings, "SHADOW_MODE_ENABLED", True, raising=False)
        monkeypatch.setattr(R.settings, "SHADOW_MODE_RATIO", 1.0, raising=False)
        sink: list[dict] = []
        R.set_shadow_sink(sink.append)

        primary = R.RetrievalBundle(
            docs=[], raw_retrieved_count=0, graph_entities=[],
            rewrite_query=None, degraded_reason=None,
        )
        R._maybe_shadow("怎么安装python", 1, UserRole.ADMIN, primary)
        await asyncio.sleep(0.05)

        assert sink, "影子对比应至少落一条 diff"
        assert "jaccard" in sink[0] and "variant_latency_ms" in sink[0]
        assert primary.docs == [], "影子不得修改主链路 bundle"

    async def test_main_path_identical_with_shadow_on_off(self, monkeypatch):
        # 隔离重检索内部（避免真实 Milvus/embedder IO），仅验证影子机制不改主路径
        async def _fake_rerank(q, docs):
            return docs, None

        async def _graph_noop(*a, **k):
            return [], None
        monkeypatch.setattr(R, "_milvus_hybrid_search_safe", lambda *a, **k: ([], None))
        monkeypatch.setattr(R, "_graph_expand", _graph_noop)
        monkeypatch.setattr(R, "_rerank_docs", _fake_rerank)

        kw = dict(user_id=1, role=UserRole.ADMIN, use_hyde=False,
                  enable_graph=True, top_k=5, final_max_k=5, cutoff_drop_ratio=0.2)

        monkeypatch.setattr(R.settings, "SHADOW_MODE_ENABLED", False, raising=False)
        b_off = await R.retrieve_three_channel("python列表去重", **kw)

        sink: list[dict] = []
        R.set_shadow_sink(sink.append)
        monkeypatch.setattr(R.settings, "SHADOW_MODE_ENABLED", True, raising=False)
        b_on = await R.retrieve_three_channel("python列表去重", **kw)
        await asyncio.sleep(0.05)

        assert [d.doc_id for d in b_on.docs] == [d.doc_id for d in b_off.docs]
        assert b_on.degraded_reason == b_off.degraded_reason
        assert sink, "开启影子后应有对比落库"

    def test_shadow_sampling_ratio(self):
        assert R._shadow_sampled("x", ratio=1.0) is True
        assert R._shadow_sampled("x", ratio=0.0) is False


# ============================================================
# AC2 对抗采样评估集
# ============================================================
class TestAC2Adversarial:
    def test_counts_and_ground_truth(self):
        dirty = [(i, q, g) for (i, q, g) in build_adversarial_set.DIRTY]
        adv = [(i, q, g) for (i, q, g) in build_adversarial_set.ADVERSARIAL]
        assert len(dirty) >= 20, "脏数据需 ≥20"
        assert len(adv) >= 20, "对抗样本需 ≥20"
        for lst in (dirty, adv):
            for (_id, q, g) in lst:
                assert q.strip() and g.strip(), f"{_id} 缺 query 或 ground_truth"

    def test_build_writes_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr(build_adversarial_set, "_OUT", str(tmp_path / "adv.json"))
        data = build_adversarial_set.build()
        assert data["dirty_count"] >= 20 and data["adversarial_count"] >= 20
        loaded = json.loads((tmp_path / "adv.json").read_text(encoding="utf-8"))
        assert len(loaded["samples"]) == data["total"]
        assert all(s["ground_truth"] for s in loaded["samples"])


# ============================================================
# AC3 4 维 Judge
# ============================================================
class TestAC3Judge4D:
    def _fake_scorer(self, dims):
        raw = json.dumps({**dims, "reason": "ok"})
        return {"text": raw, "usage": {}}

    def test_four_dimensions_returned(self):
        dims = {"fact_correctness": 0.9, "completeness": 0.8,
                "harmlessness": 1.0, "coherence": 0.7}
        res = llm_judge.judge_answer_4d(
            "Python 列表去重", "用 set 去重：list(set(x))", "set 去重",
            scorer=lambda m: self._fake_scorer(dims),
        )
        for d in llm_judge.JUDGE_DIMS:
            assert d in res, f"缺失维度 {d}"
            assert 0.0 <= res[d] <= 1.0

    def test_empty_answer_zero(self):
        res = llm_judge.judge_answer_4d("q", "", "g")
        assert all(res[d] == 0.0 for d in llm_judge.JUDGE_DIMS)

    def test_report_mean_and_quantiles(self):
        recs = [
            {d: v for d, v in zip(llm_judge.JUDGE_DIMS, row)}
            for row in [(0.9, 0.8, 1.0, 0.7), (0.5, 0.6, 0.9, 0.4), (1.0, 1.0, 1.0, 1.0)]
        ]
        rep = llm_judge.judge_report(recs)
        for d in llm_judge.JUDGE_DIMS:
            assert "mean" in rep[d] and "p25" in rep[d] and "p75" in rep[d]
            assert rep[d]["mean"] == pytest.approx(sum(r[d] for r in recs) / 3, abs=1e-3)
            assert 0.0 <= rep[d]["pass_rate"] <= 1.0


# ============================================================
# AC4 金丝雀
# ============================================================
class TestAC4Canary:
    def test_assign_deterministic(self):
        assert canary.canary_assign("u-42", ratio=0.01) == canary.canary_assign("u-42", ratio=0.01)
        assert canary.canary_assign("u-42", ratio=1.0) is True
        assert canary.canary_assign("u-42", ratio=0.0) is False

    def test_rollback_on_bad_metrics(self):
        from datetime import datetime, timedelta
        w = canary.CanaryWindow(started_at=datetime.now() - timedelta(days=5))
        # 延迟超标 → 立即回滚，无视观察期满
        assert w.decide({"latency_p95_ms": 9999, "correctness": 1.0, "tool_success_rate": 1.0}) == "rollback"
        # 正确性不达标 → 回滚
        assert w.decide({"latency_p95_ms": 100, "correctness": 0.5, "tool_success_rate": 1.0}) == "rollback"

    def test_promote_after_window(self):
        from datetime import datetime, timedelta
        w = canary.CanaryWindow(started_at=datetime.now() - timedelta(days=4))
        good = {"latency_p95_ms": 100, "correctness": 0.95, "tool_success_rate": 0.99}
        assert w.decide(good) == "promote"

    def test_hold_during_window(self):
        from datetime import datetime, timedelta
        w = canary.CanaryWindow(started_at=datetime.now() - timedelta(days=1))
        good = {"latency_p95_ms": 100, "correctness": 0.95, "tool_success_rate": 0.99}
        assert w.decide(good) == "hold"


# ============================================================
# AC5 既有评估脚本可复现（task29 judge_answer / task32 eval_dataset / harnesses 导入）
# ============================================================
class TestAC5Regression:
    def test_judge_answer_0_1_still_works(self):
        # 空回答走降级，不触网；验证原 0-1 接口未被破坏
        res = llm_judge.judge_answer("q", "", "g")
        assert "score" in res and res["score"] == 0

    def test_eval_dataset_intact(self):
        from scripts.eval import eval_dataset
        assert len(eval_dataset.ALL) >= 40, "task32 标准题基线不被破坏"

    def test_harnesses_importable(self):
        from scripts.eval import harnesses  # noqa: F401
        assert hasattr(harnesses, "run_sixnode")
