# -*- coding: utf-8 -*-
"""
task-R1 连续批处理（对齐 vLLM continuous batching）。

职责：把「窗口内到达的多个 rerank 请求」合并成一个大 batch 一次前向，吞吐提升。
设计要点：
- 纯逻辑、零 IO：推理函数由调用方注入（infer_fn: 扁平 (query,content) 对 → 分数），
  便于离线单测（注入 fake，无需 CUDA）。
- 攒批窗口 window_ms：窗口内到达的请求合并；超窗未满批立即 flush（延迟上限 max_wait_ms）。
- 单批上限 max_batch_pairs：超过则拆下一批（AC3 保证 5 请求 ≤2 批）。
- 队满 max_queue：超限返回 BatchClosed（调用方走降级，不 500）。
- sync infer_fn 经 run_in_executor 跑（sidecar 进程内 GPU 线程，不阻塞 sidecar HTTP 事件循环）；
  async infer_fn 直接 await（测试用）。

统计：batch_count / request_count / rejected_count 供 /health 与压测。
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Union

# infer_fn: 扁平 [(query, content), ...] -> [score, ...]（长度与 pairs 对齐）
InferFn = Callable[
    [list[tuple[str, str]]],
    Union[list[float], Awaitable[list[float]]],
]


class BatchClosed(Exception):
    """队列已满或推理失败：调用方应走降级（而非重试/500）。"""

    def __init__(self, message: str = "rerank 批量队列已满，请走降级"):
        super().__init__(message)


class ContinuousBatcher:
    """跨请求连续批处理调度器。"""

    def __init__(
        self,
        infer_fn: InferFn,
        *,
        window_ms: int = 20,
        max_batch_pairs: int = 64,
        max_wait_ms: int = 50,
        max_queue: int = 200,
    ) -> None:
        self._infer_fn = infer_fn
        self.window_ms = int(window_ms)
        self.max_batch_pairs = int(max_batch_pairs)
        self.max_wait_ms = int(max_wait_ms)
        self.max_queue = int(max_queue)
        self._queue: "asyncio.Queue[tuple[str, list[str], asyncio.Future]]" = asyncio.Queue(
            maxsize=self.max_queue
        )
        self._task: asyncio.Task | None = None
        self._closing = False
        # 统计
        self.batch_count = 0
        self.request_count = 0
        self.rejected_count = 0

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._closing = False
            self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        self._closing = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    # ------------------------------------------------------------------
    # 提交（调用方入口）
    # ------------------------------------------------------------------
    async def submit(self, query: str, contents: list[str]) -> list[float]:
        """提交一个 rerank 请求，返回与 contents 对齐的分数列表。

        队列满或已关闭 → 抛 BatchClosed（调用方降级）。
        """
        if self._closing:
            raise BatchClosed("batcher 已关闭")
        if self._queue.qsize() >= self.max_queue:
            self.rejected_count += 1
            raise BatchClosed()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put((query, contents, fut))
        # 等待结果（含推理耗时）。上限给足余量，避免正常推理被误杀。
        return await asyncio.wait_for(fut, timeout=(self.max_wait_ms + 5000) / 1000.0)

    # ------------------------------------------------------------------
    # 主循环：攒批 → flush
    # ------------------------------------------------------------------
    async def _run(self) -> None:
        while not self._closing:
            try:
                first = await self._queue.get()
            except asyncio.CancelledError:
                break
            batch = [first]
            t0 = time.monotonic()
            # 在窗口内尽量多收集（受 max_batch_pairs / max_wait_ms 约束）
            while True:
                pairs_so_far = sum(len(c) for _, c, _ in batch)
                if pairs_so_far >= self.max_batch_pairs:
                    break
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                if elapsed_ms >= self.max_wait_ms:
                    break
                wait_ms = min(self.window_ms, self.max_wait_ms - elapsed_ms)
                if wait_ms <= 0:
                    break
                try:
                    nxt = await asyncio.wait_for(
                        self._queue.get(), timeout=wait_ms / 1000.0
                    )
                    batch.append(nxt)
                except asyncio.TimeoutError:
                    break
            await self._flush(batch)

    async def _flush(self, batch: list) -> None:
        # 1) 扁平化所有请求的对，一次前向
        flat: list[tuple[str, str]] = []
        counts: list[int] = []
        for q, cs, _ in batch:
            for c in cs:
                flat.append((q, c))
            counts.append(len(cs))
        # 2) 推理（异常→各 future 置 BatchClosed，由调用方降级，不丢请求）
        try:
            scores = await self._call_infer(flat)
        except Exception as exc:  # noqa: BLE001
            for _, _, fut in batch:
                if not fut.done():
                    fut.set_exception(BatchClosed(f"推理失败：{exc}"))
            return
        if not isinstance(scores, list) or len(scores) != len(flat):
            for _, _, fut in batch:
                if not fut.done():
                    fut.set_exception(
                        BatchClosed(f"推理返回长度不符：{len(scores) if isinstance(scores, list) else scores} != {len(flat)}")
                    )
            return
        # 3) 切分回各请求
        pos = 0
        for (_, cs, fut), n in zip(batch, counts):
            part = scores[pos : pos + n]
            pos += n
            if not fut.done():
                fut.set_result(part)
        self.batch_count += 1
        self.request_count += len(batch)

    async def _call_infer(self, flat: list[tuple[str, str]]) -> list[float]:
        if asyncio.iscoroutinefunction(self._infer_fn):
            return await self._infer_fn(flat)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._infer_fn, flat)
