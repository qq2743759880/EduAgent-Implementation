# -*- coding: utf-8 -*-
"""W-NEXT-R01LIVE-001 注入态一次性 runner（8011 独立实例，用后即弃）。

目的：实证 R01 记忆 worker 通电验收登记②——「worker 启动失败注入 → health 200 +
WARN 不阻断」的 live 行为，把「口径拉伸」变真覆盖。

最小侵入原则（红线：不碰 app/**、config.py、共享 8000）：
- 故障注入在本 runner 进程内完成：patch `app.ai.memory.service.start_memory_worker`
  为必抛 RuntimeError 的假件。app/main.py lifespan 是函数级
  `from app.ai.memory.service import start_memory_worker`（延迟导入），uvicorn 导入
  app.main 时 lifespan 执行期取到的是**已 patch 的模块属性**，因此注入必然生效；
- 队列键经环境变量 MEMORY_QUEUE_KEY 指到专用键（edu:mem_queue:r01live_inject），
  注入态下 chat 的记忆入队落专用键无人消费（旁路降级停写），**不与共享 8000 的
  worker 竞争 edu:mem_queue**，共享实例零接触。

运行（示例）：
    MEMORY_QUEUE_KEY=edu:mem_queue:r01live_inject .venv/Scripts/python.exe \
        scripts/eval/_r01live_inject_uvicorn.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 以脚本路径直接运行时，把项目根（edu-agent/）加入 sys.path，保证 `import app.*` 可用
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import uvicorn  # noqa: E402


def _inject_fault() -> None:
    """把 start_memory_worker 换成必抛假件（lifespan 应 WARN 不阻断）。"""
    import app.ai.memory.service as svc

    async def _boom() -> None:
        raise RuntimeError("R01LIVE-001 注入故障：start_memory_worker 必然抛错（live 演练）")

    svc.start_memory_worker = _boom
    print("[R01LIVE-001] 已注入：app.ai.memory.service.start_memory_worker -> 必抛 RuntimeError")


def main() -> None:
    _inject_fault()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8011, log_level="info")


if __name__ == "__main__":
    main()
