# -*- coding: utf-8 -*-
"""W3-05：Ingest Worker 进程入口（启停脚本按 WorkerSpec.entry_script 拉起）。

用法（仓库根 / bili-study-agent/ 下，.venv 解释器）::

    .venv/Scripts/python.exe scripts/run_ingest_worker.py

进程语义（v2.5 §2.2）：
- run_forever：ready 门（runtime:web_ready）→ startup（注册消费组/预热 BGE-M3）→
  循环（心跳 + 消费）→ shutdown（SIGTERM 后停止取新单，当前批 flush 后退出码 0）；
- 退出码：0=干净退出；1=shutdown 超时强退（PEL 留给 reconciler）；2=ready 门未通过。
- Windows 兼容：asyncio 的 add_signal_handler 在 Proactor 循环不支持 → 回退
  signal.signal（主线程注册，asyncio.run 的事件循环运行在主线程，可收到）。
"""
from __future__ import annotations

import asyncio

# B0-FIX（Video/Wave 缺陷修复）：Windows 下 asyncmy 0.2.x 在 ProactorEventLoop 读
# 大行（>16KB 多包行，如含 business_metadata 的 task.source_files）会触发
# "Existing exports of data: object cannot be re-sized" BufferError → 连接坏死。
# worker 进程不使用 MCP stdio（Proactor 的唯一依赖），一律切 Selector loop。
import sys as _sys
if _sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import argparse
import os
import signal
import sys
from pathlib import Path

# 保证 `python scripts/run_ingest_worker.py` 直跑可 import app.*（cwd 无关）
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("PYTHONPATH", str(_REPO_ROOT))


async def _amain() -> int:
    from app.knowledge.ingest_worker import IngestWorker
    from app.core.worker_bootstrap import worker_resources
    from app.core.worker_runtime import HEARTBEAT_KEY_FMT

    worker = IngestWorker()
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-runtime", action="store_true", help="初始化独立进程资源并验证 web_ready/心跳，不消费任务")
    args = parser.parse_args()
    loop = asyncio.get_running_loop()

    def _graceful(*_args) -> None:
        # SIGTERM/SIGINT → 置位 shutdown：停止取新单，当前批处理完（flush）后退出码 0
        worker.request_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _graceful)
        except NotImplementedError:  # Windows Proactor：回退传统信号处理器
            signal.signal(sig, _graceful)
        except (RuntimeError, ValueError):  # 非 main 线程等场景：仅跳过注册
            pass

    async with worker_resources(worker.spec):
        if args.check_runtime:
            if not await worker._pre_run_gate(timeout_s=0):
                print("[ingest-worker] web_ready missing; runtime check failed")
                return 2
            alive = await worker.heartbeat()
            healthy = await worker.health()
            await worker._rd().delete(HEARTBEAT_KEY_FMT.format(name=worker.spec.name))
            print(f"[ingest-worker] runtime ready={alive and healthy}; jobs_consumed=0")
            return 0 if alive and healthy else 1
        return await worker.run_forever()


def main() -> None:
    exit_code = asyncio.run(_amain())
    sys.exit(int(exit_code or 0))


if __name__ == "__main__":
    main()
