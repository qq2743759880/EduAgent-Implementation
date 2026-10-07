# -*- coding: utf-8 -*-
"""W3-04 Parser Worker 入口脚本。

用法：.venv\Scripts\python.exe scripts/run_parser_worker.py
前置：uvicorn 9988 在线（web_ready 键）；Redis 可达。
"""
import asyncio

# B0-FIX（Video/Wave 缺陷修复）：Windows 下 asyncmy 0.2.x 在 ProactorEventLoop 读
# 大行（>16KB 多包行，如含 business_metadata 的 task.source_files）会触发
# "Existing exports of data: object cannot be re-sized" BufferError → 连接坏死。
# worker 进程不使用 MCP stdio（Proactor 的唯一依赖），一律切 Selector loop。
import sys as _sys
if _sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import argparse
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.worker_bootstrap import worker_resources
from app.core.worker_runtime import HEARTBEAT_KEY_FMT
from app.knowledge.parser_worker import ParserWorker


async def main() -> int:
    worker = ParserWorker()
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-runtime", action="store_true", help="初始化独立进程资源并验证 web_ready/心跳，不消费任务")
    args = parser.parse_args()
    async with worker_resources(worker.spec):
        if args.check_runtime:
            if not await worker._pre_run_gate(timeout_s=0):
                print("[parser-worker] web_ready missing; runtime check failed")
                return 2
            alive = await worker.heartbeat()
            healthy = await worker.health()
            await worker._rd().delete(HEARTBEAT_KEY_FMT.format(name=worker.spec.name))
            print(f"[parser-worker] runtime ready={alive and healthy}; jobs_consumed=0")
            return 0 if alive and healthy else 1

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, worker.request_shutdown)
            except (NotImplementedError, RuntimeError, ValueError):
                signal.signal(sig, lambda *_: worker.request_shutdown())
        return await worker.run_forever()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
