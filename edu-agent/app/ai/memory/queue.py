"""三层记忆 - 异步写队列 + 遗忘任务（task25 R7；R01 升级：对话窗 turn 载荷）。

- **异步隔离（GWT①④）**：`enqueue_candidate` / `enqueue_turn_window` 只入队即返回
  （LPUSH→Redis，或 in-memory asyncio.Queue），绝不阻塞/抛错到应答链路；
  后台 worker 用阻塞 BRPOP 取单 → `store.write`（失败按 retries 上限重入队，
  超限则丢弃记日志）→ 写入后触发 `prune_if_over`（容量卫兵）。
- **两种载荷**：
  - candidate（R7 原样）：已抽取好的单条记忆，直接写；
  - turn（R01-b）：对话窗原始载荷，worker 内做「规则抽取 + LLM 抽取（mem0 式）」，
    LLM 失败显式落 degraded 键（不伪装空列表），抽出的候选再入同一队列走 candidate 路径，
    重试/丢弃计数单一事实源。
- **broker 双实现**：Redis list（生产，复用 app.database.get_redis）+ 内存 asyncio.Queue（降级/测试）。
- worker 生命周期 `start_consumer` / `stop_consumer`；由应用 lifespan 启动（service 门面）。
- **自愈（R01）**：消费循环内单条处理异常只计数入日志、不炸 worker；毒消息（JSON 不可解析）
  计数丢弃不空转。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from loguru import logger

from app.ai.memory.ingest import detect_memories_window
from app.ai.memory.schemas import MemoryCandidate


class MemoryWriteQueue:
    """异步记忆写队列。enqueue 恒快速返回，worker 后台消费组成 `store.write` 链路。"""

    def __init__(self, store: Any, *, max_retry: int | None = None, queue_key: str | None = None) -> None:
        from app.config import settings

        self.store = store
        self._max_retry = int(max_retry if max_retry is not None else settings.MEMORY_QUEUE_MAX_RETRY)
        self._queue_key = queue_key or str(settings.MEMORY_QUEUE_KEY)
        # R01：LLM 抽取失败的 turn 落此 degraded 键（可回放/可观测），Redis 不可用时退进程内列表
        self._degraded_key = f"{self._queue_key}:degraded"
        self._memq: asyncio.Queue = asyncio.Queue()
        self._degraded_mem: list[dict[str, Any]] = []
        self._consumer: asyncio.Task | None = None
        self._running = False
        # R01：worker 计数（自愈/验收观测用；仅进程内计数，不保证跨实例聚合）
        self.stats: dict[str, int] = {
            "candidate": 0,      # 成功消费的 candidate 载荷数
            "turn": 0,           # 成功消费的 turn 载荷数
            "retry": 0,          # 写失败重入队次数
            "dropped": 0,        # 超过重试上限丢弃数
            "degraded": 0,       # LLM 抽取失败落 degraded 数
            "poison": 0,         # 毒消息（不可解析）丢弃数
            "loop_error": 0,     # 消费循环自愈捕获的未预期异常数
        }

    # --- 入队（异步隔离核心，绝不向调用方抛错） ---
    async def _push(self, payload: dict[str, Any]) -> bool:
        """统一入队：Redis LPUSH 优先，失败退内存队列；双失败仅告警返回 False。"""
        try:
            from app.database import get_redis

            r = get_redis()
            await r.lpush(self._queue_key, json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as exc:
            # Redis 不可用 → 入内存队列（测试/降级路径成环亦有消费者吞掉）
            try:
                self._memq.put_nowait(payload)
                return True
            except Exception:
                logger.warning(f"[Memory:queue] 入队失败（丢弃一条，不阻塞应答）：{exc}")
                return False

    async def enqueue_candidate(self, user_id: int, candidate: MemoryCandidate) -> bool:
        payload = {
            "user_id": int(user_id),
            "content": (candidate.content or "")[:2000],
            "memory_type": candidate.memory_type[:32],
            "topic": (candidate.topic or "general")[:64],
            "importance": max(1, min(5, int(candidate.importance or 4))),
            "retries": 0,
        }
        return await self._push(payload)

    async def enqueue_turn_window(
        self,
        user_id: int,
        messages: list[dict[str, str]],
        *,
        threshold: int | None = None,
    ) -> bool:
        """R01-b：对话窗整窗入队（抽取在 worker 内做，enqueue 侧零 LLM、毫秒级快返）。"""
        from app.config import settings

        payload = {
            "kind": "turn",
            "user_id": int(user_id),
            "messages": [
                {"role": str(m.get("role"))[:16], "content": str(m.get("content") or "")[:2000]}
                for m in (messages or [])
                if isinstance(m, dict)
            ][:20],
            "threshold": int(threshold if threshold is not None else settings.MEMORY_IMPORTANCE_THRESHOLD),
            "retries": 0,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        if not payload["messages"]:
            return False
        return await self._push(payload)

    # --- degraded（R01：LLM 失败显式留存，不静默丢弃） ---
    async def record_degraded(self, payload: dict[str, Any], *, reason: str) -> None:
        """把 LLM 抽取失败的 turn 落 degraded 键（Redis 优先，不可用退进程内列表）。"""
        self.stats["degraded"] += 1
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "user_id": int(payload.get("user_id") or 0),
            "reason": str(reason)[:300],
            "turn_ts": payload.get("ts"),
            "retries": int(payload.get("retries") or 0),
            # 只留窗口前 2 条预览（≤200 字/条），避免 degraded 键膨胀；回放可凭日志/时间窗定位
            "window_preview": [
                {"role": str(m.get("role"))[:16], "content": str(m.get("content") or "")[:200]}
                for m in (payload.get("messages") or [])[:2] if isinstance(m, dict)
            ],
        }
        logger.warning(
            f"[Memory:queue] LLM 抽取失败，turn 落 degraded（规则候选仍照常入库，不静默丢弃）："
            f"user={record['user_id']} reason={record['reason']} 累计 degraded={self.stats['degraded']}"
        )
        try:
            from app.database import get_redis

            r = get_redis()
            await r.lpush(self._degraded_key, json.dumps(record, ensure_ascii=False))
        except Exception:
            self._degraded_mem.append(record)

    async def degraded_count(self) -> int:
        """degraded 留存总数（Redis 键 + 进程内兜底），只读观测。"""
        total = len(self._degraded_mem)
        try:
            from app.database import get_redis

            r = get_redis()
            total += int(await r.llen(self._degraded_key))
        except Exception:
            pass
        return total

    # --- 消费（阻塞取单 → 写记忆 → 容量卫兵） ---
    async def _write_candidate_payload(self, payload: dict[str, Any]) -> bool:
        """candidate 载荷写库（R7 原逻辑：失败重入队/超限丢弃）。"""
        user_id = int(payload["user_id"])
        try:
            await self.store.write(
                user_id=user_id,
                content=payload["content"],
                memory_type=payload["memory_type"],
                topic=payload["topic"],
                importance=int(payload["importance"]),
            )
            # 写入后触发容量卫兵（遗忘淘汰，GWT③）
            try:
                await self.store.prune_if_over(user_id)
            except Exception:
                pass
            return True
        except Exception as exc:
            retries = int(payload.get("retries", 0)) + 1
            if retries <= self._max_retry:
                payload["retries"] = retries
                # 失败重入队（Redis index 0 队尾 → 稍后重试；内存队列追加）
                store_failed_payload: dict[str, Any] = dict(payload)
                await self._push(store_failed_payload)
                self.stats["retry"] += 1
                logger.warning(f"[Memory:queue] 写记忆失败（将重试 {retries}/{self._max_retry}）: {exc}")
            else:
                self.stats["dropped"] += 1
                logger.error(f"[Memory:queue] 写记忆失败已达上限，丢弃：user={user_id} exc={exc}")
            return False

    async def _process_turn(self, payload: dict[str, Any]) -> bool:
        """turn 载荷：规则抽取 + LLM 抽取（mem0 式对话窗）→ 候选回灌同队列走写库路径。

        - LLM 失败：显式落 degraded（`record_degraded`），规则候选不丢，turn 视为正常消费；
        - 抽取/回灌自身的异常向上抛，由消费循环自愈计数并按 turn 重试语义处理（毒 turn 不炸 worker）。
        """
        from app.config import settings

        user_id = int(payload["user_id"])
        messages = payload.get("messages") or []
        threshold = int(payload.get("threshold") or settings.MEMORY_IMPORTANCE_THRESHOLD)

        # 1) 规则候选（只扫用户发言，确定性高精度；零外部依赖，永不丢）
        candidates = detect_memories_window(messages)

        # 2) LLM 候选（覆盖用户偏好 + 助手事实性陈述）；失败 → degraded，不阻断
        if getattr(settings, "MEMORY_LLM_EXTRACT_ENABLED", True):
            try:
                from app.ai.memory.extract_llm import extract_candidates_llm

                llm_cands, llm_error = await extract_candidates_llm(messages)
                if llm_error is not None:
                    await self.record_degraded(payload, reason=llm_error)
                else:
                    candidates.extend(llm_cands)
            except Exception as exc:  # 抽取器非预期异常同样显式 degraded（防御纵深）
                await self.record_degraded(
                    payload, reason=f"extract_unexpected: {type(exc).__name__}: {str(exc)[:200]}"
                )

        # 3) 阈值过滤 + 跨源内容去重 → 回灌 candidate 载荷（写库重试逻辑单一事实源）
        pushed = 0
        seen: set[str] = set()
        for c in candidates:
            if int(c.importance or 4) < threshold:
                continue
            if c.content in seen:
                continue
            seen.add(c.content)
            if await self.enqueue_candidate(user_id, c):
                pushed += 1
        logger.info(
            f"[Memory:queue] turn 消费完成 user={user_id} 候选回灌={pushed} "
            f"窗口条数={len(messages)} degraded累计={self.stats['degraded']}"
        )
        return True

    async def _process(self, payload: dict[str, Any]) -> bool:
        if payload.get("kind") == "turn":
            ok = await self._process_turn(payload)
            if ok:
                self.stats["turn"] += 1
            return ok
        ok = await self._write_candidate_payload(payload)
        if ok:
            self.stats["candidate"] += 1
        return ok

    async def _fetch_one(self, redis_timeout: int = 2, wait_timeout: float = 3.0) -> dict[str, Any] | None:
        """取单：Redis BRPOP 优先，空/故障退内存队列；返回 None=本轮无单。毒消息抛 ValueError。"""
        item: dict[str, Any] | None = None
        # 1) Redis 优先
        raw = None
        try:
            from app.database import get_redis

            r = get_redis()
            raw = await asyncio.wait_for(
                r.brpop(self._queue_key, timeout=redis_timeout), timeout=wait_timeout
            )
        except asyncio.TimeoutError:
            pass  # 轮询间隔无任务
        except Exception:
            pass  # Redis 故障 → 走内存队列兜底
        if raw is not None:
            try:
                item = json.loads(raw[1])
            except Exception as exc:
                # 毒消息：BRPOP 已将其移出队列，计数丢弃，避免静默吞掉
                self.stats["poison"] += 1
                logger.error(f"[Memory:queue] 毒消息（JSON 不可解析）丢弃：{exc} raw={str(raw[1])[:200]}")
                raise ValueError("poison message")
        # 2) 内存队列兜底（含 Redis 降级时写入的任务）
        if item is None:
            try:
                item = self._memq.get_nowait()
            except Exception:
                item = None
        return item

    async def _consume_loop(self) -> None:
        while self._running:
            try:
                item = await self._fetch_one()
            except ValueError:
                continue  # 毒消息已计数丢弃
            except Exception as exc:
                # 取单本身异常（理论上 _fetch_one 已内吞，此处为防御）：不自愈退出
                self.stats["loop_error"] += 1
                logger.exception(f"[Memory:queue] 取单异常（worker 自愈继续）：{exc}")
                await asyncio.sleep(0.2)
                continue
            if item is None:
                await asyncio.sleep(0.05)  # 空转节流
                continue
            try:
                await self._process(item)
            except Exception as exc:
                # R01 自愈铁律：单条失败（含 turn 抽取未预期异常）绝不炸死 worker
                self.stats["loop_error"] += 1
                logger.exception(f"[Memory:queue] 单条消费异常（worker 自愈继续）：{exc}")
                await asyncio.sleep(0.05)

    def start_consumer(self) -> None:
        if self._running:
            return
        self._running = True
        self._consumer = asyncio.get_running_loop().create_task(self._consume_loop())

    async def stop_consumer(self) -> None:
        self._running = False
        if self._consumer is not None:
            self._consumer.cancel()
            try:
                await self._consumer
            except Exception:
                pass
            self._consumer = None

    # --- 测试便利 ---
    async def pump_once(self) -> bool:
        """单步消费：从任一 broker 取一条并处理（供单测确定性验证，不启长驻循环）。"""
        item = None
        try:
            from app.database import get_redis

            r = get_redis()
            # brpop 的 timeout 必须是整数秒；wait_for 控制快速返回（最短阻塞）
            raw = await asyncio.wait_for(r.brpop(self._queue_key, timeout=1), timeout=0.3)
            if raw is not None:
                item = json.loads(raw[1])
        except Exception:
            item = None
        if item is None:
            try:
                item = self._memq.get_nowait()
            except Exception:
                return False
        return await self._process(item)
