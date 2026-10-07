"""
幂等性中间件组件（Phase 重构：task09 core/ 框架层）

三层纵深防御之第一层：SET NX EX 86400 + 响应缓存 24h

面试考点：
- 为什么用 Redis 而不是数据库？幂等 key 是临时性的（24h 过期），Redis TTL 天然支持
- 为什么有三层？中间件层防重复提交 → 唯一键层防数据重复 → 状态机条件更新层防并发
- SET NX EX 的原子性：单条 Redis 命令保证"设置+过期"原子，避免死 key

用法：
  from app.core.idempotency import Idempotency
  idem = Idempotency()
  key = "order:create:abc123"
  # 检查是否已处理
  cached = await idem.check(key)
  if cached is not None:
      return cached  # 幂等返回
  # 执行业务逻辑
  result = await do_business()
  await idem.save(key, result)

降级路径：Redis 不可用时跳过幂等检查（放行），由唯一键+状态机兜底
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.monitoring.metrics import record_degraded as _record_degraded


class Idempotency:
    """幂等性组件：SET NX EX 86400 + 响应缓存 24h。"""

    def __init__(self, ttl: int = 86400):
        self.ttl = ttl  # 24h

    async def _get_redis(self):
        """获取 Redis 客户端，不可用时返回 None。"""
        try:
            from app.database import get_redis
            return get_redis()
        except RuntimeError:
            return None

    async def check(self, key: str) -> Any | None:
        """
        检查幂等 key 是否已处理。

        Returns:
            None: 未处理，继续执行
            Any: 已处理，返回缓存的响应（直接返回给调用方）
        """
        r = await self._get_redis()
        if r is None:
            logger.warning("[Idempotency] Redis 不可用，跳过幂等检查（降级放行）")
            # task39 GWT②：§6.4 Redis 行 —— 幂等降级由唯一键+状态机兜底，指标可见
            _record_degraded("redis", "idempotency_check_unavailable")
            return None

        cached = await r.get(f"idem:{key}")
        if cached is None:
            return None

        try:
            return json.loads(cached)
        except Exception:
            return cached

    async def save(self, key: str, response: Any) -> bool:
        """
        保存幂等结果（SET NX EX）。

        Returns:
            True: 保存成功（首次）
            False: 已存在（并发重复，忽略）
        """
        r = await self._get_redis()
        if r is None:
            logger.warning("[Idempotency] Redis 不可用，跳过幂等保存（降级放行）")
            _record_degraded("redis", "idempotency_save_unavailable")
            return True  # 降级放行

        value = json.dumps(response, ensure_ascii=False, default=str)
        return await r.set(f"idem:{key}", value, nx=True, ex=self.ttl) or False

    async def invalidate(self, key: str) -> None:
        """手动清除幂等缓存（用于退款重试等场景）。"""
        r = await self._get_redis()
        if r is None:
            return
        await r.delete(f"idem:{key}")


# 全局默认实例
_idempotency: Idempotency | None = None


def get_idempotency() -> Idempotency:
    """获取全局幂等组件实例。"""
    global _idempotency
    if _idempotency is None:
        _idempotency = Idempotency()
    return _idempotency