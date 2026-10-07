"""
统一响应壳（Phase 重构：task10 响应壳标准化）

设计决策：
- 成功：{code: 0, message: "ok", data: <任意类型>}
- 失败：{code: <字符串错误码>, message: <用户可读>, data: null}
- 对齐 edu-data-refactor-plan.md §3.5 决策③：全模块统一

面试考点：
- 为什么不用 HTTP 状态码区分成功/失败？HTTP 状态码是传输层语义，业务错误码是应用层语义
- 为什么 code 是字符串？字符串错误码更可读（如 "AUTH_EXPIRED" vs 40102），且支持分段编码
- 与现有 {code,message,detail} 的兼容：保留 detail 字段仅在 DEBUG 下返回

用法：
  from app.core.resp import ok, fail
  return ok(data={"user": {...}})
  return fail("AUTH_EXPIRED", "登录已过期")
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class RespModel(BaseModel):
    """统一响应模型。"""
    code: int = 0
    message: str = "ok"
    data: Any = None


class Shell(BaseModel, Generic[T]):
    """统一响应壳（OpenAPI 契约形态，W2 批判 C1）。

    供显式声明 response_model 的端点使用（如 `response_model=Shell[UserProfile]`），
    使 /docs 对成功 2xx 展开为 {code:0, message:"ok", data:T} 而非裸 DTO，与
    运行时 RespWrapMiddleware 包壳后的实体一致。已含 code/data 属性，OpenAPI
    后处理器识别到壳形态会跳过，避免二次包装。
    """
    code: int = 0
    message: str = "ok"
    data: T | None = None


def ok(data: Any = None, message: str = "ok") -> dict:
    """成功响应。"""
    return {"code": 0, "message": message, "data": data}


def fail(code: str | int, message: str, data: Any = None) -> dict:
    """失败响应。code 支持字符串错误码（如 "AUTH_EXPIRED"）或数字码。"""
    return {"code": code, "message": message, "data": data}