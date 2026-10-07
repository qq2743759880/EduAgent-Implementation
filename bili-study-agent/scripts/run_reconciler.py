"""Standalone W3 reconciler process entry point.

Usage: .venv/Scripts/python.exe scripts/run_reconciler.py
"""
from __future__ import annotations

import argparse
import asyncio

# B0-FIX（Video/Wave 缺陷修复）：Windows 下 asyncmy 0.2.x 在 ProactorEventLoop 读
# 大行（>16KB 多包行，如含 business_metadata 的 task.source_files）会触发
# "Existing exports of data: object cannot be re-sized" BufferError → 连接坏死。
# worker 进程不使用 MCP stdio（Proactor 的唯一依赖），一律切 Selector loop。
import sys as _sys
if _sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import signal
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.reconciler import ReconcilerWorker
from app.core.worker_bootstrap import worker_resources
from app.core.worker_runtime import HEARTBEAT_KEY_FMT


async def _amain() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-runtime", action="store_true",
                        help="initialize process-local clients and check web_ready without reconciling")
    args = parser.parse_args()
    worker = ReconcilerWorker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.request_shutdown)
        except (NotImplementedError, RuntimeError, ValueError):
            signal.signal(sig, lambda *_: worker.request_shutdown())

    async with worker_resources(worker.spec):
        if args.check_runtime:
            if not await worker._pre_run_gate(timeout_s=0):
                print("[reconciler] web_ready missing; runtime check failed")
                return 2
            alive = await worker.heartbeat()
            healthy = await worker.health()
            await worker._rd().delete(HEARTBEAT_KEY_FMT.format(name=worker.spec.name))
            print(f"[reconciler] runtime ready={alive and healthy}; jobs_reconciled=0")
            return 0 if alive and healthy else 1
        return await worker.run_forever()


if __name__ == "__main__":
    sys.exit(asyncio.run(_amain()))
