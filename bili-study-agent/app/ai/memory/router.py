"""记忆事件溯源 API（task-M1：契约红线——纯增量端点，不改 /me、/learning 响应结构）。

端点：
- POST /api/memory/rewind              {entity_id, target_event_id}  回滚到某版本（ChronoMem 语义）
- GET  /api/memory/history/{entity_id}  分页事件流（审计/回滚 UI）
- POST /api/admin/memory/dream/run     {user_id} 手动触发 Dream 巩固（管理员）

响应壳对齐契约①：{code, message, data}；非 0 表示失败。
所有权校验：回滚/历史仅实体属主（或管理员）可访问。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import CurrentUser, UserRole, get_current_user, require_role
from app.ai.memory.service import get_memory_store
from app.ai.memory.dream import run_dream

router = APIRouter(prefix="/api/memory", tags=["记忆事件溯源"])


class RewindRequest(BaseModel):
    entity_id: int
    target_event_id: int


class DreamRunRequest(BaseModel):
    user_id: int


def _ok(data: Any = None, message: str = "ok") -> dict:
    return {"code": 0, "message": message, "data": data}


def _err(message: str, code: int = 1) -> dict:
    return {"code": code, "message": message, "data": None}


async def _check_owner(entity_id: int, user: CurrentUser) -> None:
    store = await get_memory_store()
    head = await store._persistence.fetch_entity(int(entity_id))
    if head is None:
        raise HTTPException(status_code=404, detail="记忆实体不存在")
    if int(head.user_id) != int(user.user_id) and user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise HTTPException(status_code=403, detail="无权访问该记忆实体")


@router.post("/rewind")
async def rewind_memory(
    body: RewindRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """回滚某记忆实体到 target_event_id 版本（追加 rewind 事件，HEAD 指向目标内容）。"""
    await _check_owner(body.entity_id, user)
    store = await get_memory_store()
    try:
        new_eid = await store.rewind(
            entity_id=int(body.entity_id), target_event_id=int(body.target_event_id),
            operator=f"user:{user.user_id}",
        )
    except ValueError as exc:
        return _err(str(exc), code=2)
    return _ok({"entity_id": int(body.entity_id), "new_head_entity_id": new_eid})


@router.get("/history/{entity_id}")
async def memory_history(
    entity_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(get_current_user),
):
    """分页事件流（审计溯源：event_type/operator/trace_id/valid_from/valid_to）。"""
    await _check_owner(entity_id, user)
    store = await get_memory_store()
    events = await store.history(entity_id=int(entity_id), limit=int(limit), offset=int(offset))
    return _ok({"entity_id": int(entity_id), "events": events, "count": len(events)})


@router.post("/admin/dream/run")
async def admin_dream_run(
    body: DreamRunRequest,
    user: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """管理员手动触发某用户 Dream 巩固（受分布式锁保护，并发安全）。"""
    result = await run_dream(int(body.user_id))
    return _ok(result)
