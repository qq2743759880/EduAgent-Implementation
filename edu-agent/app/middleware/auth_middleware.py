"""
TraceMiddleware：trace_id 生成 + X-Trace-Id 透传 + 慢查询日志带 trace_id
AdminAuthMiddleware：/api/admin/* 强制 Bearer 鉴权（task11 批判⑥ 安全补强）

鉴权设计（fail-closed）：
- 管理端点无 token / 格式错 / token 无效过期 / 用户不存在 → 一律 401 壳 {"code":"40101"}
- DEBUG 虚拟管理员与 X-Force-Role 测试后门对 /api/admin/* 一律失效（堵匿名 200 缺陷）
- 角色级 403 仍由路由内 require_role 负责（分层：认证归中间件，授权归路由）
"""
from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.common.logging import logger
# 使用 app.core.trace 中的同一个 trace_id_var 实例
#（TraceMiddleware 在前向路径已设该值，短路响应需从同一 ContextVar 读取）
from app.core.trace import trace_id_var

# 慢查询阈值（毫秒）
SLOW_REQUEST_MS = 500


def get_trace_id() -> str:
    return trace_id_var.get("")


# 公开路径白名单
SKIP_EXACT_PATHS = {
    "/", "/health", "/health/detail", "/metrics",
    "/docs", "/redoc", "/openapi.json", "/favicon.ico",
}
SKIP_PATH_PREFIXES = ("/api/auth/", "/media/")


def _is_public_path(path: str) -> bool:
    if path in SKIP_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in SKIP_PATH_PREFIXES)


class TraceMiddleware(BaseHTTPMiddleware):
    """
    请求追踪中间件。

    职责：
    1. 生成 trace_id → ContextVar + X-Trace-Id 响应头
    2. 公开路径白名单放行
    3. 慢查询日志（>500ms）带 trace_id
    4. 结构化访问日志
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. 生成 trace_id
        tid = request.headers.get("X-Trace-Id") or str(uuid.uuid4())[:8]
        trace_id_var.set(tid)
        # 供下游（chat 会话入口等）覆盖为会话级 trace_id；中间件据此回写响应头。
        # 注：BaseHTTPMiddleware 在隔离 context 中执行端点，端点内对 ContextVar 的修改
        # 不会回传，故用 request.state（同一 request 实例按引用共享）承载最终 trace_id。
        request.state.trace_id = tid

        path = request.url.path
        is_public = _is_public_path(path)
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                f"[{tid}] {request.method} {path} 异常",
                trace_id=tid, method=request.method, path=path,
                status=500, duration_ms=round(duration_ms, 1),
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        # 响应头携带 trace_id：优先取路由内通过 request.state 写入的最终 trace_id
        # （如 chat 会话入口设置的会话级 trace_id），否则回退请求级 tid（task-O1 AC4/AC5）。
        final_tid = getattr(request.state, "trace_id", None) or trace_id_var.get("") or tid
        response.headers["X-Trace-Id"] = final_tid

        # 慢查询日志
        if duration_ms >= SLOW_REQUEST_MS:
            logger.warning(
                f"[{tid}] SLOW {request.method} {path} → {response.status_code} ({duration_ms:.0f}ms)",
                trace_id=tid, method=request.method, path=path,
                status=response.status_code, duration_ms=round(duration_ms, 1),
                slow=True,
            )

        logger.info(
            f"[{tid}] {request.method} {path} → {response.status_code} ({duration_ms:.0f}ms)",
            trace_id=tid, method=request.method, path=path,
            status=response.status_code, duration_ms=round(duration_ms, 1),
        )
        return response


def _unauthorized(message: str = "凭证无效或未登录") -> JSONResponse:
    """401 统一壳（契约①：{code:<字符串>, message, data:null} + Trace 外层注 X-Trace-Id）。

    AdminAuthMiddleware 短路返回的 401 响应会在后向路径经 TraceMiddleware
    （外层，CircuitGuard 之后注册）注入 X-Trace-Id——不再需要自注入。
    但仍从 app.core.trace 导入 trace_id_var 供本中间件内部日志使用。
    """
    return JSONResponse(
        status_code=401,
        content={"code": "40101", "message": message, "data": None},
        headers={"WWW-Authenticate": "Bearer"},
    )


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """
    管理端强制鉴权中间件（task11 批判⑥：堵匿名访问管理端点返回 200 的越权缺口）。

    规则（fail-closed，任何异常一律 401 拒绝）：
    1. 拦截全部管理面前缀：/api/admin/* 与 /api/mcp/*（后者整路由 require_role(ADMIN)，
       属管理端专用，sd-challenger CA-49/50 实证 DEBUG 后门可旁路依赖层鉴权）
    2. 必须携带 Authorization: Bearer <access_token>
    3. token 必须解码有效（decode_token expect_type=access）
    4. 用户必须存在（get_user_info_by_id）
    通过后注入 request.state.user_id 供下游使用；角色授权归路由 require_role。
    """

    # 管理面前缀清单（新增管理路由时必须同步登记）
    # - /api/knowledge/admin/：知识库管理上传（require_role ADMIN/MANAGER）
    # - /api/knowledge/partitions（无尾斜杠）：精确路径 + DELETE /{tenant_id} 子路径都命中
    ADMIN_PREFIXES = (
        "/api/admin/",
        "/api/mcp/",
        "/api/knowledge/admin/",
        "/api/knowledge/partitions",
        "/api/metrics/",
        "/api/memory/admin/",
    )

    # 角色伪造堵截（judge R1 裁定）：管理前缀请求一律剥离 X-Force-Role 头，
    # 使 DEBUG 后门（dependencies.py 规则①）对管理面彻底失效——
    # "有效 token 的普通用户 + 伪造头" 无法再越过 require_role(ADMIN)。
    # 选型说明（三案选一）：①中间件剥离头（本方案，最小侵入、不经环境开关）；
    # ②DEBUG 后门整体加环境开关（影响全部既有测试，风险大）；
    # ③后门按前缀失效（逻辑分散进 dependencies，两处耦合）。
    _FORGED_ROLE_HEADERS = ("x-force-role",)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        # CORS 预检：OPTIONS 不带 Authorization，属安全放行路径，交给 CORS 中间件处理，
        # 否则 /api/admin/* 的预检被本轮短路 401（无 ACAO 头）导致浏览器跨域失败。
        if request.method == "OPTIONS":
            return await call_next(request)
        if not path.startswith(self.ADMIN_PREFIXES):
            return await call_next(request)

        # 剥离角色伪造头（MutableHeaders 改 scope，下游 dependencies/require_role 不再可见）
        if any(h in request.headers for h in self._FORGED_ROLE_HEADERS):
            mutable_headers = MutableHeaders(scope=request.scope)
            for header in self._FORGED_ROLE_HEADERS:
                if header in mutable_headers:
                    del mutable_headers[header]

        # 1. Bearer 格式检查
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            logger.warning(f"[auth] 管理端匿名访问拒绝: {path}")
            return _unauthorized("缺少 Authorization 请求头")
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return _unauthorized("Authorization 格式应为: Bearer <token>")

        # 2~3. token 解码 + 用户存在性（延迟导入避免启动期循环依赖）
        try:
            from app.auth.service import decode_token, get_user_info_by_id
            token_data = decode_token(parts[1], expect_type="access")
            user = await get_user_info_by_id(token_data.user_id)
        except Exception as exc:
            logger.warning(f"[auth] 管理端 token 校验失败: {type(exc).__name__}: {exc}")
            return _unauthorized()
        if user is None:
            return _unauthorized("用户不存在或已被删除")

        # 4. 注入用户上下文，放行（角色检查归路由 require_role）
        request.state.user_id = user.user_id
        return await call_next(request)