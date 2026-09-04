"""
鉴权中间件 —— 两件事：
1. 为每个 HTTP 请求生成 trace_id，并写入 Request 上下文 + Response Header（全链路排错）
2. 根据「公开路径」白名单跳过路由级鉴权（真正的 JWT 校验留给路由 Depends）

设计说明：
- 中间件不做 JWT 解码和角色校验，因为这些是「路由级」的精细化需求。
- 路由层使用 Depends(get_current_user) / Depends(require_role([...])) 时才做真实校验。
- 中间件只负责「过滤公开路径 + 生成 trace_id + 记录结构化访问日志」。
"""
import time
import uuid
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.common.logging import logger

# 指标标签归一化：高基路径（含 id）聚合为 {path}
_METRIC_SKIP_PATHS = {"/metrics", "/health", "/health/detail"}


def _metric_path(path: str) -> str:
    """把高基数路径（/api/chat/123）归一化为低基数模板（/api/chat/{id}）。"""
    if path in _METRIC_SKIP_PATHS:
        return path
    parts = path.strip("/").split("/")
    out = []
    for p in parts:
        # 纯数字段 → {id}（会话 id / 用户 id 等）
        if p.isdigit():
            out.append("{id}")
        else:
            out.append(p)
    return "/" + "/".join(out)


# ============================================================
# 全局上下文变量（每个请求独立一份，coroutine safe）
# ============================================================
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """获取当前请求的 trace_id（供日志/LLM 调用/MCP 调用等使用）。"""
    return trace_id_var.get("")


# ============================================================
# 公开路径白名单（无需 JWT 即可访问）
# ============================================================
SKIP_EXACT_PATHS = {
    "/",                   # 根路径欢迎页
    "/health",             # 存活探测
    "/health/detail",      # 详细健康检查
    "/metrics",            # Prometheus 抓取（P1-2）
    "/docs",               # Swagger UI（DEBUG 模式开启）
    "/redoc",              # ReDoc UI
    "/openapi.json",       # OpenAPI Schema（Swagger 需要）
    "/favicon.ico",        # 浏览器图标
}
SKIP_PATH_PREFIXES = (
    "/api/auth/",          # 鉴权模块（注册/登录/刷新 —— 必须公开，不然根本拿不到 token）
)


def _is_public_path(path: str) -> bool:
    """判断一个请求路径是否属于公开路径（无需鉴权）。"""
    if path in SKIP_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in SKIP_PATH_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    轻量鉴权中间件。

    职责：
    1) 每个请求生成 8 字符短 UUID 作为 trace_id，写入 context + 响应头
    2) 公开路径直接放行
    3) 非公开路径：**不拦截**（把校验留给路由 Depends(get_current_user / require_role)）
    4) 记录结构化访问日志（method/path/status/duration/client_ip，生产 JSON 含 trace_id）
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # ---- 0. 生成 trace_id 并写入上下文 ----
        tid = str(uuid.uuid4())[:8]
        trace_id_var.set(tid)

        path = request.url.path
        mpath = _metric_path(path)
        is_public = _is_public_path(path)

        # ---- 1. 指标：在途 + 开始计时 ----
        try:
            from app.monitoring.metrics import http_request_duration, http_requests_inflight, http_requests_total
            http_requests_inflight.inc()
        except Exception:
            http_requests_total = http_request_duration = None

        start = time.perf_counter()
        try:
            # ---- 2. 打印 DEBUG 级请求日志 ----
            logger.debug(
                f"[{tid}] {request.method} {path}"
                f" (public={is_public})"
            )

            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            if http_requests_total is not None:
                try:
                    http_requests_total.labels(method=request.method, path=mpath, status=500).inc()
                    http_request_duration.labels(method=request.method, path=mpath).observe(duration_ms / 1000)
                    http_requests_inflight.dec()
                except Exception:
                    pass
            logger.error(
                f"[{tid}] {request.method} {path} 异常",
                trace_id=tid, method=request.method, path=path,
                status=500, duration_ms=round(duration_ms, 1),
                client_ip=request.client.host if request.client else None,
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Trace-Id"] = tid

        # ---- 3. 指标：计数 + 耗时 ----
        if http_requests_total is not None:
            try:
                http_requests_total.labels(
                    method=request.method, path=mpath, status=response.status_code
                ).inc()
                http_request_duration.labels(
                    method=request.method, path=mpath
                ).observe(duration_ms / 1000)
                http_requests_inflight.dec()
            except Exception:
                pass

        # ---- 4. 结构化访问日志（生产 JSON 可被收集） ----
        logger.info(
            f"[{tid}] {request.method} {path} → {response.status_code} ({duration_ms:.0f}ms)",
            trace_id=tid, method=request.method, path=path,
            status=response.status_code, duration_ms=round(duration_ms, 1),
            client_ip=request.client.host if request.client else None,
            is_public=is_public,
        )
        return response
