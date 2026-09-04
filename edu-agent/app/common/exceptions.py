"""
自定义异常类 —— 统一错误码和错误信息格式。

为什么需要自定义异常：
1. 统一错误响应格式（code/message/detail）
2. 在任何地方 raise，全局 handler 自动返回正确的 HTTP 状态码
3. 业务错误（找不到订单）和系统错误（数据库挂了）分开处理

错误码规范：
- 4xx：客户端错误（输入错误、权限不足等）
- 5xx：服务端错误（数据库连接失败等）
- 错误码为字符串（如 "40111"），成功 code=0 (int)
"""
from app.common.error_codes import (
    OK, BAD_REQUEST, NOT_FOUND, FORBIDDEN, CONFLICT, VALIDATION,
    INTERNAL_ERROR, SERVICE_UNAVAILABLE,
)


class AppException(Exception):
    """应用基础异常。"""
    def __init__(
        self,
        code: str | int,
        message: str,
        detail: str | None = None,
        http_status: int | None = None,
    ):
        self.code = code              # 业务错误码（字符串或数字）
        self.message = message        # 用户可见的错误信息
        self.detail = detail          # 内部调试信息
        if http_status is None:
            http_status = _http_status_for_code(str(code) if isinstance(code, int) else code)
        self.http_status = http_status
        super().__init__(message)


def _http_status_for_code(code: str) -> int:
    """业务错误码 → HTTP 状态码（按码段前缀映射）。"""
    s = str(code)
    if s.startswith("409"):
        return 409
    if s.startswith("404"):
        return 404
    if s.startswith("403"):
        return 403
    if s.startswith("401"):
        return 401
    if s.startswith("422"):
        return 422
    if s.startswith("400"):
        return 400
    if s.startswith("5"):
        return 500
    return 400


class NotFoundError(AppException):
    """资源不存在（如订单号找不到）"""
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            code=NOT_FOUND,
            message=f"{resource}不存在：{identifier}",
            http_status=404,
        )


class ResourceNotFoundError(AppException):
    """通用资源不存在（P1-3：带业务码，前端可读 code 分支处理）"""
    def __init__(self, message: str, code: str | int = NOT_FOUND, detail: str | None = None):
        super().__init__(code=code, message=message, detail=detail)


class PermissionDeniedError(AppException):
    """无权限（403）"""
    def __init__(self, message: str, code: str | int = FORBIDDEN, detail: str | None = None):
        super().__init__(code=code, message=message, detail=detail)


class BadRequestError(AppException):
    """客户端参数/业务规则错误（400）"""
    def __init__(self, message: str, code: str | int = BAD_REQUEST, detail: str | None = None):
        super().__init__(code=code, message=message, detail=detail)


class ConflictError(AppException):
    """资源冲突（如唯一约束违反），HTTP 409。"""
    def __init__(self, message: str, code: str | int = CONFLICT, detail: str | None = None):
        super().__init__(code=code, message=message, detail=detail, http_status=409)


_AUTH_CODE_TO_HTTP = {
    "AUTH_TOKEN_INVALID": ("40101", 401),
    "AUTH_TOKEN_EXPIRED": ("40102", 401),
    "AUTH_TOKEN_MALFORMED": ("40103", 401),
    "AUTH_TOKEN_TYPE_MISMATCH": ("40104", 401),
    "AUTH_ROLE_INVALID": ("40105", 401),
    "AUTH_ACCOUNT_MISSING": ("40011", 400),
    "AUTH_ACCOUNT_EXISTS": ("40912", 409),
    "AUTH_MOBILE_EXISTS": ("40913", 409),
    "AUTH_EMAIL_EXISTS": ("40914", 409),
    "AUTH_LOGIN_FAILED": ("40111", 401),
    "AUTH_USER_DISABLED": ("40312", 403),
    "AUTH_USER_NOT_FOUND": ("40413", 404),
}


class ValidationError(AppException):
    """输入校验失败。

    兼容两种用法：
      - ValidationError(message, detail=...) ：默认业务码 40000。
      - ValidationError(message, code="AUTH_...", detail=...) ：
        code 是业务子码字符串（如 AUTH_TOKEN_INVALID），映射后用具体 401xx/400xx 数字业务码，
        并把原始子码字符串写入 detail（若 detail 未填），便于排查。
    """
    def __init__(
        self,
        message: str,
        detail: str | None = None,
        code: str | int | None = None,
        **kwargs: object,
    ):
        biz_code: str | int = "40000"
        http_status = 400
        extra_detail: str | None = None
        if code is not None:
            if isinstance(code, int):
                biz_code = str(code)
            elif isinstance(code, str):
                mapped = _AUTH_CODE_TO_HTTP.get(code)
                if mapped is not None:
                    biz_code, http_status = mapped
                else:
                    biz_code = "40000"
                extra_detail = f"sub_code={code}"
        # detail 合并：优先调用方传入，再补充子码信息
        final_detail = detail
        if extra_detail:
            if final_detail is None:
                final_detail = extra_detail
            else:
                final_detail = f"{detail} | {extra_detail}"
        super().__init__(
            code=biz_code,
            message=message,
            detail=final_detail,
            http_status=http_status,
        )


class LLMError(AppException):
    """大模型调用失败"""
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(
            code="50001",
            message=f"AI 服务暂时不可用：{message}",
            detail=detail,
            http_status=503,
        )


class DatabaseError(AppException):
    """数据库操作失败"""
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(
            code="50002",
            message="数据库操作失败，请稍后重试",
            detail=f"{message}: {detail}" if detail else message,
            http_status=500,
        )
