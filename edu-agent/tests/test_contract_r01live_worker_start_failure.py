# -*- coding: utf-8 -*-
"""W-NEXT-R01LIVE-001 契约测试：记忆 worker 启动失败注入 → lifespan 不炸 + /health 200 + WARN。

背景（R01 记忆 worker 通电验收「登记②」收口）：此前「worker 启动失败注入 → health 200 +
WARN 不阻断」只有口径声明、无专项测试（口径拉伸）。本文件把它钉成真覆盖，
并与 live 实证（scripts/eval/_r01live_inject_uvicorn.py，:8011 独立实例）同一注入点：

- 注入方式与 live 侧一致：monkeypatch ``app.ai.memory.service.start_memory_worker``
  为必抛 RuntimeError 假件。app/main.py lifespan 是**函数级延迟导入**
  （``from app.ai.memory.service import start_memory_worker``），执行期取到的是
  已 patch 的模块属性——测试 A0 先钉死这一导入语义，保证注入点真实有效；
- 半 live 主断言（A1~A5）：真实 app.main lifespan（TestClient 上下文管理器触发全链），
  断言启动完成、/health 200、WARN 落日志、无半启动态、关闭阶段干净；
  预热（GPU embedding 等 41s 重活）与本契约无关，patch 为 no-op（lifespan 中
  本就是后台 best-effort 任务，失败不阻断）；
- 离线旁证（A6）：启动失败后 ``_worker_started=False``，stop_memory_worker 是
  no-op（不得触碰队列）——失败不留烂摊子。

运行：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_r01live_worker_start_failure.py -q
"""
from __future__ import annotations

import io

import pytest
from loguru import logger


# ---------------------------------------------------------------------------
# 工具：注入假件 + 日志捕获
# ---------------------------------------------------------------------------
def _make_boom(monkeypatch: pytest.MonkeyPatch) -> dict:
    """把 start_memory_worker 换成必抛 RuntimeError 假件；返回调用计数 dict。"""
    import app.ai.memory.service as svc

    calls = {"n": 0}

    async def _boom() -> None:
        calls["n"] += 1
        raise RuntimeError("R01LIVE 契约测试注入：start_memory_worker 必然抛错")

    monkeypatch.setattr(svc, "start_memory_worker", _boom)
    return calls


def _capture_warnings() -> tuple[io.StringIO, int]:
    buf = io.StringIO()
    hid = logger.add(buf, level="WARNING")
    return buf, hid


# ---------------------------------------------------------------------------
# A0：注入点语义——main.py 的函数级延迟导入在 patch 后取到假件
# ---------------------------------------------------------------------------
def test_a0_function_level_import_picks_patched_attr(monkeypatch):
    """app/main.py lifespan 用 `from ... import start_memory_worker` 延迟导入；
    patch 模块属性后，该导入形态必须取到假件（否则 live/测试注入均失效）。"""
    import app.ai.memory.service as svc

    boom_calls = _make_boom(monkeypatch)

    # 与 app/main.py:195 完全相同的导入形态（函数内 import-from）
    from app.ai.memory.service import start_memory_worker

    import inspect

    # 关键断言：取到的是 patched 假件（协程函数），不是原实现
    assert inspect.iscoroutinefunction(start_memory_worker)
    assert svc.start_memory_worker is start_memory_worker
    assert boom_calls["n"] == 0


# ---------------------------------------------------------------------------
# A1~A5：真实 app.main lifespan 半 live（与 :8011 live 注入同一注入点）
# ---------------------------------------------------------------------------
def test_a1_a5_worker_start_failure_lifespan_survives_health_200(monkeypatch):
    """注入态主契约（对应 live 实证三断言）：

    A1 lifespan 启动完成（with 不抛 = 不阻断主服务）；
    A2 /health → 200 且 status=ok；
    A3 日志出现「记忆 worker 启动失败」WARN（app/main.py 降级纪律）；
    A4 假件确被调用且 `_worker_started` 保持 False（无半启动态）；
    A5 关闭阶段不炸（with 正常退出；stop 对未启动 worker 是 no-op）。
    """
    from starlette.testclient import TestClient

    import app.ai.memory.service as svc
    from app.main import app

    boom_calls = _make_boom(monkeypatch)

    # 预热是后台 best-effort（GPU embedding ~41s），与本契约无关 → no-op 化提速
    async def _no_warmup() -> None:
        return None

    monkeypatch.setattr("app.core.warmup.run_warmup", _no_warmup)

    monkeypatch.setattr(svc, "_worker_started", False, raising=False)

    buf, hid = _capture_warnings()
    try:
        with TestClient(app) as client:  # A1：lifespan 启动若炸，这里直接抛
            r = client.get("/health")
            assert r.status_code == 200, f"A2 /health 应 200，实得 {r.status_code}"
            assert r.json().get("status") == "ok"
        # A5：with 正常退出 = 关闭阶段 lifespan 未炸（stop_memory_worker no-op 路径）
    finally:
        logger.remove(hid)

    assert boom_calls["n"] == 1, "lifespan 应恰好调用一次 start_memory_worker"
    assert "记忆 worker 启动失败" in buf.getvalue(), (
        f"A3 应有降级 WARN，实得日志：\n{buf.getvalue()[:600]}"
    )
    assert svc._worker_started is False, "A4 启动失败不得留下半启动态"


# ---------------------------------------------------------------------------
# A6：启动失败后 stop 是 no-op（离线，不触碰队列）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a6_stop_after_failed_start_is_noop(monkeypatch):
    """_worker_started=False 时 stop_memory_worker 必须直接返回，
    不得触碰 get_memory_queue（失败不留烂摊子，shutdown 干净）。"""
    import app.ai.memory.service as svc

    monkeypatch.setattr(svc, "_worker_started", False, raising=False)

    async def _must_not_be_called():
        raise AssertionError("stop_memory_worker 不应在未启动态触碰队列")

    monkeypatch.setattr(svc, "get_memory_queue", _must_not_be_called)
    await svc.stop_memory_worker()  # 不抛 = no-op 路径成立
