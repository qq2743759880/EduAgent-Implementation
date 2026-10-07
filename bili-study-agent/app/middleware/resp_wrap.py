"""
RespWrapMiddleware：响应壳兜底中间件（task114 统一重构：非 2xx 兜底 + 2xx 裸 DTO 全站包壳）

职责（sd-challenger CA-52/53 修复 + task114 响应壳全站统一）：
1. 非 2xx：Starlette Router 对未匹配路由的 404 / 方法不允许的 405 等直接返回
   默认 {"detail": "..."}，不经过 app 级 exception handler —— 本中间件在响应出口
   兜底：非 2xx 且非壳的 JSON 响应 → 统一 {code, message, data:null} 壳。
2. 2xx（task114 新增）：裸 response_model / 裸 dict 的成功 JSON 响应 → 统一包壳
   {code:0, message:"ok", data:<原体>}，终结"前端每页双解析"。

规则：
- 白名单前缀/内容类型跳过（SSE/文件流/docs/health/metrics）
- 仅处理 application/json 响应
- 幂等边界（task114 契约 C-A）：body 已是壳（同时含 code/message/data 三键）→ 原样透传，
  绝不二次包裹。用「三键齐备」判定壳，而非仅查 code —— 否则 /api/coding/challenges/{code} 等
  业务 DTO 顶层自带 code 字段会被误判为已壳而漏包。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.common.error_codes import STATUS_TO_CODE

# 白名单：不做响应壳包裹的路径
_SKIP_PREFIXES = (
    "/docs", "/redoc", "/openapi.json", "/favicon.ico",
    "/health", "/metrics",  # 健康检查/Prometheus 指标不需要壳
)

# 白名单：不做响应壳包裹的内容类型
_SKIP_CONTENT_TYPES = (
    "text/event-stream",  # SSE
    "application/octet-stream",  # 文件下载
    "text/plain", "text/html",  # 308 重定向 / 默认文本响应
    "image/", "video/", "audio/",
)

# 重建响应时需要剔除的头（由新 Response 按新 body 重算，避免长度/类型错配）
_HOP_BY_HOP_HEADERS = {"content-length", "content-type"}


class RespWrapMiddleware(BaseHTTPMiddleware):
    """JSON 响应壳兜底：2xx 裸成功体统一包壳 + 非 2xx 裸体壳化（幂等）。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 白名单跳过
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        response = await call_next(request)

        # 跳过特殊内容类型
        content_type = response.headers.get("content-type", "")
        if any(content_type.startswith(ct) for ct in _SKIP_CONTENT_TYPES):
            return response
        if not content_type.startswith("application/json"):
            return response

        # BaseHTTPMiddleware 下 response.body_iterator 可能同步（list）或异步（async gen），
        # 统一消费后以新 Response 重建，避免破坏 / 重复包壳。
        body, payload = await self._consume_json(response)

        # 幂等边界：已是壳（code+message+data 三键齐备）→ 原样透传，绝不二次包裹
        if _is_shell(payload):
            return self._rebuild(response, body)

        # 2xx 裸成功体 → 统一包壳 {code:0, message:"ok", data:<原体>}
        if 200 <= response.status_code < 300:
            return JSONResponse(
                status_code=response.status_code,
                content={"code": 0, "message": "ok", "data": payload},
                headers=self._inherited_headers(response),
            )

        # 非 2xx 裸响应（如 FastAPI 默认 {"detail": "Not Found"}）→ 壳化
        message = str(payload.get("detail", f"HTTP {response.status_code}")) if isinstance(payload, dict) else f"HTTP {response.status_code}"
        code_val = STATUS_TO_CODE.get(response.status_code, "50000")
        return JSONResponse(
            status_code=response.status_code,
            content={"code": code_val, "message": message, "data": None},
            headers=self._inherited_headers(response),
        )

    @staticmethod
    async def _consume_json(response) -> tuple[bytes, dict | Any]:
        """消费响应体为 (原始 bytes, 解析后的 JSON 载荷)。"""
        body = b""
        body_iter = response.body_iterator
        if hasattr(body_iter, "__aiter__"):
            async for chunk in body_iter:
                body += chunk
        else:
            for chunk in body_iter:
                body += chunk
        try:
            payload = json.loads(body) if body else {}
        except (ValueError, TypeError):
            payload = {}
        return body, payload

    @staticmethod
    def _inherited_headers(response):
        """继承原响应语义头（WWW-Authenticate/Retry-After/Allow 等），剔除需重建的 hop-by-hop。"""
        return {
            k: v for k, v in response.headers.items()
            if k.lower() not in _HOP_BY_HOP_HEADERS
        }

    @staticmethod
    def _rebuild(response, body: bytes) -> Response:
        """以消费后的 body 重建响应（保留状态码与继承头）。"""
        return Response(
            content=body,
            status_code=response.status_code,
            headers=RespWrapMiddleware._inherited_headers(response),
            media_type="application/json",
        )


def _is_shell(payload) -> bool:
    """判断是否为统一响应壳（code+message+data 三键齐备）。

    用"三键齐备"而非仅"含 code"，避免业务 DTO（如 coding.Challenge 顶层自带
    `code` 字段）被误判为已壳而漏包（task114 幂等边界）。
    """
    return isinstance(payload, dict) and {"code", "message", "data"} <= payload.keys()
