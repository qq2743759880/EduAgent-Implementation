"""
OpenAPI 响应壳契约上移（W2 批判 C1）。

背景：运行时 RespWrapMiddleware 已把 2xx 成功 JSON 响应统一包成
{code:0, message:"ok", data:<原体>} 壳（黑盒兜底），但 OpenAPI /docs 仍停留在
裸 DTO 或裸 dict 声明，与运行返回不一致 —— 下游按 /docs 对接会写错解析器。

本模块把"壳形态"上移到契约声明层：
  - 遍历 openapi 的每个响应，对每个 2xx 的 application/json 内容 schema 统一包壳；
  - 幂等：识别已含 code/data 的壳 schema 则跳过，避免二次包装；
  - 豁免：非 application/json（如 SSE 的 text/event-stream），以及 /health、/metrics、
    /docs、/redoc、/openapi.json 自身。

使用：在 app.main 完成所有 include_router 后调用 `install_openapi_shell(app)`。
注意这只是"文档↔运行一致"，不改任何 HTTP 响应实体（运行态仍由 RespWrapMiddleware 负责）。
"""
from __future__ import annotations

from typing import Any

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}

# 豁免路径：不做响应壳包裹（对齐 RespWrapMiddleware._SKIP_PREFIXES，另加 redoc）
_SKIP_PATHS = ("/docs", "/redoc", "/openapi.json", "/favicon.ico", "/health", "/metrics")


def _shell_schema(data_schema: Any) -> dict:
    """把原 schema 包一次壳 {code:const 0, message:const ok, data:<原 schema>}。"""
    return {
        "type": "object",
        "required": ["code", "message", "data"],
        "properties": {
            "code": {"type": "integer", "const": 0, "title": "code"},
            "message": {"type": "string", "const": "ok", "title": "message"},
            "data": data_schema if isinstance(data_schema, dict) else {"type": "object"},
        },
    }


def _ref_target(schema: Any, components: dict) -> Any:
    """解析 `$ref` → 目标组件；非 ref 或指向未知组件返回 None。"""
    ref = schema.get("$ref") if isinstance(schema, dict) else None
    prefix = "#/components/schemas/"
    if not isinstance(ref, str) or not ref.startswith(prefix):
        return None
    return components.get(ref[len(prefix):])


def _is_shell_schema(schema: Any, components: dict | None = None) -> bool:
    """判定 schema 是否已是壳形态（同时含 code 与 data 属性），避免二次包装。

    兼容两类表达：
    - 内联对象：直接看 properties 是否同时含 code/data。
    - `$ref`：解析到组件再判（若组件已含 code/data 即视为壳）——否则
      response_model=Shell[...] 生成的是 `{$ref: Shell_X_}`，会被误判为未壳而二次包裹。
    对齐 RespWrapMiddleware._is_shell 思路：用「同时含 code/data」判定而非仅查 code，
    否则顶层自带 code 字段的业务 DTO 会被误判为已壳而漏包。
    """
    if not isinstance(schema, dict):
        return False
    if "$ref" in schema:
        if components is not None:
            target = _ref_target(schema, components)
            if target is not None:
                return _is_shell_schema(target, components)
        return False
    props = schema.get("properties")
    return isinstance(props, dict) and "data" in props and "code" in props


def _is_success_status(status: str) -> bool:
    """状态码字符串是否表示 2xx（default / 非数字按非 2xx 处理）。"""
    if status == "default":
        return False
    try:
        return 200 <= int(status) < 300
    except (TypeError, ValueError):
        return False


def install_openapi_shell(app, skip_paths: tuple[str, ...] = ()) -> None:
    """覆写 app.openapi：对每个 2xx application/json 响应 schema 统一包壳（幂等）。

    FastAPI 在 /openapi.json 首次被请求时懒调用 app.openapi()（默认实现自带缓存，
    写死后处理器只需包一层，改动仅影响 /docs 展示，不触任何 HTTP 响应实体）。
    :param skip_paths: 额外按路径前缀豁免的端点（如 SSE 的 text/event-stream 端点）。
        FastAPI 对无 response_model 的流式端点在 /docs 会自动生成 application/json 的
        200，无法仅凭 schema 区分真 JSON 与 SSE，需按路径显式豁免。
    """
    original = app.openapi

    skip = _SKIP_PATHS + tuple(skip_paths or ())

    def _patched() -> dict:
        openapi = original()
        schemas = openapi.get("components", {}).get("schemas", {})
        paths = openapi.get("paths", {})
        if not isinstance(paths, dict):
            return openapi
        for path, path_item in paths.items():
            if not isinstance(path_item, dict) or any(path.startswith(p) for p in skip):
                continue
            for method, op in path_item.items():
                if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                    continue
                responses = op.get("responses")
                if not isinstance(responses, dict):
                    continue
                for status, resp in responses.items():
                    if not _is_success_status(str(status)) or not isinstance(resp, dict):
                        continue
                    content = resp.get("content")
                    if not isinstance(content, dict):
                        continue
                    media = content.get("application/json")
                    if not isinstance(media, dict) or "schema" not in media:
                        continue
                    data_schema = media["schema"]
                    if _is_shell_schema(data_schema, schemas):
                        continue
                    media["schema"] = _shell_schema(data_schema)
        return openapi

    app.openapi = _patched