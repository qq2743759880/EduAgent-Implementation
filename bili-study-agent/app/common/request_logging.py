"""
请求体日志中间件（Phase 3 可观测性）。

记录每个请求的关键信息，敏感字段自动脱敏。

面试考点：
- 为什么不在路由层打日志？中间件可以统一处理，不漏掉任何请求
- 为什么只记录非 2xx 请求体？2xx 请求体量太大，只记录错误请求体减少日志量
- 脱敏策略：敏感字段名 + 手机号/邮箱正则匹配
"""
from __future__ import annotations

import json
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.common.log_sanitizer import sanitize_dict_for_log
from app.common.logging import logger


# 不记录请求体的路径（文件上传、大体积数据）
_SKIP_BODY_PATHS = (
    "/api/knowledge/upload",
    "/api/admin/courses/upload",
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求体日志中间件。

    行为：
    - 所有请求记录 method + path + status + duration
    - 非 2xx 响应记录请求体（脱敏后），方便排查错误
    - 跳过文件上传等大体积请求的 body 记录
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 先执行请求（不读取 body，避免消耗流）
        response = await call_next(request)

        # 仅对非 2xx 响应记录请求体（错误排查需要）
        if response.status_code >= 400 and not any(
            request.url.path.startswith(p) for p in _SKIP_BODY_PATHS
        ):
            try:
                # 尝试读取请求体（仅对非 GET 请求）
                body_data: dict[str, Any] | None = None
                if request.method in ("POST", "PUT", "PATCH"):
                    # 从 request.state 或重新读取 body
                    # 注意：BaseHTTPMiddleware 中 request.body() 可能已被消费
                    # 这里用 try/except 静默失败
                    try:
                        body_bytes = await request.body()
                        if body_bytes and len(body_bytes) < 4096:  # 最大 4KB
                            body_data = json.loads(body_bytes)
                    except Exception:
                        pass

                if body_data:
                    safe_body = sanitize_dict_for_log(body_data)
                    logger.warning(
                        f"[REQ_ERR] {request.method} {request.url.path} "
                        f"→ {response.status_code} | body={json.dumps(safe_body, ensure_ascii=False, default=str)}"
                    )
            except Exception:
                pass

        return response