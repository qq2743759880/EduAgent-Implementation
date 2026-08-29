# -*- coding: utf-8 -*-
"""task39 契约回归测试：把压测/容灾演练暴露的修复钉死在契约层。

背景（task39 完工报告 §5.1 / §7.2 / §7.3）：
  本任务改了 6 处生产代码，但当时只做了实时压测取证，**没有补契约测试**。
  共享环境（VM 192.168.85.101）掉线后实时验证无法复跑，故补一批**纯单元测试**
  ——不依赖 MySQL/Redis/Milvus/Neo4j/MinIO 任何实时服务，任何环境都能跑。

覆盖的四处修复：
  1. app/config.py::_normalize_loopback —— Windows IPv6 双栈陷阱（P95 8185ms→56ms 的根因）
  2. app/monitoring/metrics.py::record_degraded/clear_degraded —— §6.4 降级可观测
  3. app/core/warmup.py 后端感知策略 —— §7 薄弱点 3「多 worker 显存重复占用」
  4. app/domains/course/router.py::list_series_cohorts —— 压测发现的 P0 无条件 500
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

import pytest  # noqa: E402

from app.config import Settings, settings  # noqa: E402
from app.core import warmup as warmup_mod  # noqa: E402
from app.domains.course import router as course_router  # noqa: E402
from app.domains.course import service as course_svc  # noqa: E402
from app.domains.course.schemas import CohortListData, PageMeta  # noqa: E402
from app.monitoring import metrics as metrics_mod  # noqa: E402


# ══════════════════════════════════════════════════════════════
# 1. REDIS_URL 回环归一化（task39 GWT④ 根因一）
# ══════════════════════════════════════════════════════════════
class TestLoopbackNormalization:
    """Windows 上 localhost → ::1 而 Redis 只听 IPv4 → 每次新建连接先撞 IPv6 超时。

    实测 20 并发首次 ping：localhost 6058ms vs 127.0.0.1 4ms（1500×）。
    归一化必须只动「host 恰为 localhost」的情形，其它形态保持原样。
    """

    @pytest.mark.parametrize("raw,expected", [
        ("redis://localhost:6379/0", "redis://127.0.0.1:6379/0"),
        # userinfo + 非默认端口 + 非 0 db 必须完整保留（这是最容易改错的地方）
        ("redis://u:p@localhost:6380/2", "redis://u:p@127.0.0.1:6380/2"),
        ("redis://localhost:6379", "redis://127.0.0.1:6379"),
        ("rediss://localhost:6380/0", "rediss://127.0.0.1:6380/0"),
    ])
    def test_localhost_rewritten(self, raw, expected):
        assert Settings(REDIS_URL=raw).REDIS_URL == expected

    @pytest.mark.parametrize("raw", [
        "redis://[::1]:6379/0",            # 显式 IPv6 —— 用户明确要 IPv6，不许动
        "redis://redis.internal:6379/0",   # 内网域名
        "redis://127.0.0.1:6379/0",        # 已经是 IPv4
        "unix:///var/run/redis.sock",      # unix socket
    ])
    def test_non_localhost_untouched(self, raw):
        assert Settings(REDIS_URL=raw).REDIS_URL == raw

    def test_empty_or_broken_never_raises(self):
        """解析异常必须静默保持原值——配置层不该让服务起不来。"""
        assert Settings(REDIS_URL="").REDIS_URL == ""
        assert Settings(REDIS_URL="not a url").REDIS_URL == "not a url"

    def test_default_settings_is_normalized(self):
        """进程实际使用的 settings 单例也必须已归一化（容易漏：只测了构造函数）。"""
        cur = str(getattr(settings, "REDIS_URL", "") or "")
        if "localhost" in cur:
            pytest.fail(f"settings 单例的 REDIS_URL 仍是 localhost：{cur}")


# ══════════════════════════════════════════════════════════════
# 2. 降级指标（§6.4 统一原则）
# ══════════════════════════════════════════════════════════════
def _metric_value(text: str, name: str, label_filter: str) -> float:
    """从 Prometheus 文本里取一条样本值（找不到返回 0.0）。"""
    total = 0.0
    for line in text.splitlines():
        if line.startswith(name + "{") and label_filter in line:
            try:
                total += float(line.rsplit(" ", 1)[-1])
            except ValueError:
                pass
    return total


class TestDegradedMetrics:
    """Counter 回答「发生过多少次」，Gauge 回答「现在是否还在降级」。

    两者缺一不可：只有 Counter 无法判断故障是否持续，只有 Gauge 会丢掉短时抖动。
    """

    def test_record_sets_counter_and_gauge(self):
        comp = "task39a"
        before = _metric_value(metrics_mod.render_metrics().decode(),
                               "edu_degraded_total", f'component="{comp}"')
        metrics_mod.record_degraded(comp, "boom")
        text = metrics_mod.render_metrics().decode()
        after = _metric_value(text, "edu_degraded_total", f'component="{comp}"')
        assert after == before + 1, "每次降级必须让 Counter +1"
        assert _metric_value(text, "edu_degraded_active", f'component="{comp}"') == 1.0

    def test_clear_resets_gauge_but_keeps_counter(self):
        """恢复只清 Gauge；Counter 是单调的，历史降级次数不允许被抹掉。"""
        comp = "task39b"
        metrics_mod.record_degraded(comp, "boom")
        total_after_record = _metric_value(metrics_mod.render_metrics().decode(),
                                           "edu_degraded_total", f'component="{comp}"')
        metrics_mod.clear_degraded(comp)
        text = metrics_mod.render_metrics().decode()
        assert _metric_value(text, "edu_degraded_active", f'component="{comp}"') == 0.0
        assert _metric_value(text, "edu_degraded_total", f'component="{comp}"') == total_after_record

    def test_component_normalized(self):
        """组件名必须收敛到 §6.4 矩阵行，否则 label 基数会炸。"""
        metrics_mod.record_degraded("  MiLvUs  ", "x")
        text = metrics_mod.render_metrics().decode()
        assert 'component="milvus"' in text
        assert 'component="  MiLvUs  "' not in text

    def test_never_raises(self):
        """埋点在任何输入下都不能抛——指标把业务链路搞挂是不可接受的。"""
        for bad in (None, "", 123, object()):
            metrics_mod.record_degraded(bad, bad)  # type: ignore[arg-type]
            metrics_mod.clear_degraded(bad)         # type: ignore[arg-type]


# ══════════════════════════════════════════════════════════════
# 3. 预热后端感知策略（§7 薄弱点 3）
# ══════════════════════════════════════════════════════════════
def _reset_warmup_state():
    warmup_mod._state.update({  # noqa: SLF001 — 测试需复位进程级单例
        "status": "pending", "started_at": None, "finished_at": None,
        "elapsed_ms": None, "components": {},
    })
    warmup_mod._ready = asyncio.Event()  # noqa: SLF001


@pytest.fixture
def warmup_env(monkeypatch):
    """把全部阻塞型预热体替换为假的，只验证**编排策略**（哪个跑、哪个跳过）。"""
    _reset_warmup_state()
    called = []

    def fake(name, ok=True, detail="fake"):
        def _fn():
            called.append(name)
            return ok, detail
        return _fn

    monkeypatch.setattr(warmup_mod, "_warm_jieba", fake("jieba"))
    monkeypatch.setattr(warmup_mod, "_warm_cloud_embed", fake("cloud_embed"))
    monkeypatch.setattr(warmup_mod, "_warm_bge_local", fake("bge_m3"))
    monkeypatch.setattr(warmup_mod, "_warm_reranker_sidecar", fake("reranker_sidecar"))
    monkeypatch.setattr(warmup_mod, "_warm_reranker_local", fake("reranker_local"))
    monkeypatch.setattr(settings, "EMBED_BACKEND", "cloud", raising=False)
    yield called
    _reset_warmup_state()


class TestWarmupBackendPolicy:
    def test_cloud_backend_skips_local_bge(self, warmup_env):
        """EMBED_BACKEND=cloud 时本地 BGE-M3 不在主链路 → 禁止预加载（白占显存）。"""
        snap = asyncio.run(warmup_mod.run_warmup())
        assert "bge_m3" not in warmup_env, "cloud 模式不得预加载本地 BGE-M3"
        assert "skipped" in snap["components"]["bge_m3"]["detail"]
        assert snap["status"] == "ready", "skip 类不影响 ready 判定"

    def test_cuda_backend_does_load_local_bge(self, warmup_env, monkeypatch):
        """反向对照：EMBED_BACKEND=cuda 时本地 BGE 是主链路，必须预加载。

        没有这条，上面那条 `assert "bge_m3" not in ...` 就是**空断言**——
        万一 fixture 把 bge_m3 永久打桩掉了，跳过策略坏了也测不出来。
        """
        monkeypatch.setattr(settings, "EMBED_BACKEND", "cuda", raising=False)
        snap = asyncio.run(warmup_mod.run_warmup())
        assert "bge_m3" in warmup_env, "cuda 模式本地 BGE 是主链路，必须预加载"
        assert "cloud_embed" not in warmup_env, "cuda 模式下两条向量链路不得同时加载"
        assert snap["status"] == "ready"

    def test_sidecar_ok_skips_local_reranker(self, warmup_env):
        """sidecar 可用 → 主进程不再加载 reranker（§7 薄弱点 3 的核心约束）。"""
        snap = asyncio.run(warmup_mod.run_warmup())
        assert "reranker_local" not in warmup_env
        assert "skipped" in snap["components"]["reranker_local"]["detail"]

    def test_sidecar_down_falls_back_to_local(self, warmup_env, monkeypatch):
        """sidecar 不可达 → 必须回落到本地 reranker，否则 RAG 排序能力整体丢失。"""
        monkeypatch.setattr(warmup_mod, "_warm_reranker_sidecar",
                            lambda: (_ for _ in ()).throw(RuntimeError("sidecar down")))
        asyncio.run(warmup_mod.run_warmup())
        assert "reranker_local" in warmup_env, "sidecar 不可达时必须回落本地"

    def test_warmup_is_idempotent(self, warmup_env):
        """重复调用直接返回上次结果——启动时预热一次，压测再查不能再跑一遍。"""
        first = asyncio.run(warmup_mod.run_warmup())
        n_after_first = len(warmup_env)
        second = asyncio.run(warmup_mod.run_warmup())
        assert len(warmup_env) == n_after_first, "第二次调用不得重复执行预热体"
        assert first["status"] == second["status"]


# ══════════════════════════════════════════════════════════════
# 4. cohorts 分页壳 P0 回归（压测发现，契约测试原未覆盖）
# ══════════════════════════════════════════════════════════════
class TestCohortsPagedShell:
    """task39 压测采样发现：/api/series/{id}/cohorts 无条件 500。

    svc.list_cohorts 自 R2 裁定起返回 CohortListData 分页壳（items + page_meta），
    不再是裸列表。旧代码直接迭代 pydantic 模型 → 得到 (字段名, 值) 元组 →
    元组无 .model_dump() → 500。契约测试没覆盖到，是靠真实压测才暴露的。
    """

    @staticmethod
    def _paged():
        return CohortListData.model_construct(
            items=[],
            page_meta=PageMeta(page=1, page_size=10, total=0, total_pages=0, has_more=False),
        )

    def test_root_cause_pinned_iterating_model_yields_tuples(self):
        """把根因钉住：pydantic 模型被迭代时给出 (字段名, 值) 元组。"""
        first = next(iter(self._paged()))
        assert isinstance(first, tuple) and first[0] == "items"
        assert not hasattr(first, "model_dump"), "元组没有 model_dump —— 这正是旧代码 500 的原因"

    def test_endpoint_serializes_paged_shell(self, monkeypatch):
        # 必须是 async fake —— list_cohorts 是被 await 的（同步 lambda 会抛
        # "object CohortListData can't be used in 'await' expression"，与 task37
        # 踩过的 _rerank_docs 同族）。
        async def _fake(series_id):
            return self._paged()

        monkeypatch.setattr(course_svc, "list_cohorts", _fake)
        resp = asyncio.run(course_router.list_series_cohorts(1))
        data = resp["data"] if isinstance(resp, dict) else resp.data
        assert set(data) == {"items", "page_meta"}, f"出口形态与分页壳不一致: {list(data)}"

    def test_consistent_with_sibling_endpoints(self, monkeypatch):
        """出口形态必须与 get_series_detail / get_cohort_detail 对齐（都是 model_dump）。"""
        async def _fake(series_id):
            return self._paged()

        monkeypatch.setattr(course_svc, "list_cohorts", _fake)
        resp = asyncio.run(course_router.list_series_cohorts(1))
        data = resp["data"] if isinstance(resp, dict) else resp.data
        assert data == self._paged().model_dump(mode="json")
