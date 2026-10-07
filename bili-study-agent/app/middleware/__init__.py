"""
app/middleware/ — 中间件层（Phase 重构：task10）

注册顺序（main.py 中按 add_middleware 顺序）：
  SecurityHeaders → CORS → Trace → Idempotency → RateLimit → CircuitGuard → RequestLogging → RespWrap

模块：
- auth_middleware.py：TraceMiddleware（trace_id 生成 + X-Trace-Id 透传 + 慢查询日志带 trace_id）
- rate_limit.py：RateLimitMiddleware（IP+user_id 双维度滑动窗口，交易档限流）
- trace_middleware.py：TraceMiddleware 别名（复用于 auth_middleware）
- circuit_breaker.py：CircuitGuardMiddleware（轻量打标，熔断状态注入 request.state）
- idempotency.py：IdempotencyMiddleware（/api/trade/ 前缀幂等拦截）
- resp_wrap.py：RespWrapMiddleware（响应壳兜底，白名单跳过 SSE/文件流）
"""

from app.middleware.auth_middleware import AdminAuthMiddleware, TraceMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.circuit_breaker import CircuitGuardMiddleware
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.resp_wrap import RespWrapMiddleware

__all__ = [
    "TraceMiddleware",
    "AdminAuthMiddleware",
    "RateLimitMiddleware",
    "CircuitGuardMiddleware",
    "IdempotencyMiddleware",
    "RespWrapMiddleware",
]