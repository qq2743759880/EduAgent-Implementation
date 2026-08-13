"""
自定义异常类 —— 统一错误码和错误信息格式。

为什么需要自定义异常：
1. 统一错误响应格式（code/message/detail）
2. 在任何地方 raise，全局 handler 自动返回正确的 HTTP 状态码
3. 业务错误（找不到订单）和系统错误（数据库挂了）分开处理

错误码规范：
- 4xx：客户端错误（输入错误、权限不足等）
- 5xx：服务端错误（数据库连接失败等）
- 业务错误码：如 40001（订单不存在）、40002（退款金额超限）等
"""


class AppException(Exception):
    """
    应用基础异常。

    所有业务异常都继承此类，便于全局统一处理。
    """
    def __init__(
        self,
        code: int,
        message: str,
        detail: str | None = None,
        http_status: int | None = None,
    ):
        self.code = code              # 业务错误码
        self.message = message        # 用户可见的错误信息（中文）
        self.detail = detail          # 内部调试信息（可选）
        if http_status is None:
            http_status = _http_status_for_code(code)
        self.http_status = http_status
        super().__init__(message)


def _http_status_for_code(code: int) -> int:
    """
    业务错误码 → HTTP 状态码（按码段前缀映射，REST 语义对齐）。

    约定：业务码前 3 位即 HTTP 语义段——
      400xx → 400（客户端参数/业务规则错误）
      401xx → 401（未认证 / 凭证失效）
      403xx → 403（无权限 / 资源保护）
      404xx → 404（资源不存在）
      409xx → 409（冲突：重复编码等）
      5xxxx → 500（服务端错误，如 500001 反馈写入失败）
    特殊类（NotFoundError/LLMError/DatabaseError/ValidationError 字符串子码）
    会显式传入 http_status，不落入本映射。
    """
    s = str(code)
    if s.startswith("409"):
        return 409
    if s.startswith("404"):
        return 404
    if s.startswith("403"):
        return 403
    if s.startswith("401"):
        return 401
    if s.startswith("400"):
        return 400
    if s.startswith("5"):
        return 500
    return 400


class NotFoundError(AppException):
    """资源不存在（如订单号找不到）"""
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            code=40400,
            message=f"{resource}不存在：{identifier}",
            http_status=404,
        )


_AUTH_CODE_TO_HTTP = {
    # ValidationError 额外业务子码（字符串）→ 数字业务码 + HTTP 状态码（仅用于 detail 记录子码名称，code 仍用 400xx 段）
    "AUTH_TOKEN_INVALID": (40101, 401),
    "AUTH_TOKEN_EXPIRED": (40102, 401),
    "AUTH_TOKEN_MALFORMED": (40103, 401),
    "AUTH_TOKEN_TYPE_MISMATCH": (40104, 401),
    "AUTH_ROLE_INVALID": (40105, 401),
    "AUTH_ACCOUNT_MISSING": (40011, 400),
    "AUTH_ACCOUNT_EXISTS": (40012, 409),
    "AUTH_MOBILE_EXISTS": (40013, 409),
    "AUTH_EMAIL_EXISTS": (40014, 409),
    "AUTH_LOGIN_FAILED": (40111, 401),
    "AUTH_USER_DISABLED": (40112, 403),
    "AUTH_USER_NOT_FOUND": (40113, 404),
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
        biz_code = 40000
        http_status = 400
        extra_detail: str | None = None
        if code is not None:
            if isinstance(code, int):
                biz_code = int(code)
            elif isinstance(code, str):
                mapped = _AUTH_CODE_TO_HTTP.get(code)
                if mapped is not None:
                    biz_code, http_status = mapped
                else:
                    biz_code = 40000
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
            code=50001,
            message=f"AI 服务暂时不可用：{message}",
            detail=detail,
            http_status=503,
        )


class DatabaseError(AppException):
    """数据库操作失败"""
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(
            code=50002,
            message="数据库操作失败，请稍后重试",
            detail=f"{message}: {detail}" if detail else message,
            http_status=500,
        )
