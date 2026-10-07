# -*- coding: utf-8 -*-
"""管理端基础设施实时面板 router（TO-EXEC-TB3）。

单端点、**只读**：`GET /api/admin/infra/snapshot`
- 鉴权：admin / manager 放行；student → 403（require_role 工厂统一壳）
- 契约：响应壳 `{code:0,message:"ok",data}`；data 结构冻结于
  `.ai-hub/plans/artifacts/dispatch/REPORT-TB3.md` §0.2
- 降级：各分节自降级（available=false + error），整体恒 200
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import CurrentUser, UserRole, require_role
from app.core.resp import ok
from app.admin.infra import service

router = APIRouter(
    prefix="/api/admin/infra",
    tags=["admin-infra"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.MANAGER]))],
)


@router.get("/snapshot", summary="基础设施实时快照（Redis 四件套 + Mongo + learning_event，只读）")
async def infra_snapshot(
    current_user: CurrentUser = Depends(require_role([UserRole.ADMIN, UserRole.MANAGER])),
):
    """管理端基础设施面板数据源：限流计数 / 缓存冷热 / 锁列表 / 队列深度 + Mongo 三集合 + 事件样例。

    全程只读（Redis 仅 PING/INFO/KEYS/TYPE/TTL/GET/LLEN/ZCARD；Mongo 仅 count/find），
    依赖不可达时分节降级为 `available:false`，**不抛 5xx**——面板在基础设施抖动时仍可用。
    """
    data = await service.build_snapshot()
    # 面板自带身份标记，便于前端展示「谁在看」
    data["viewer"] = {"user_id": current_user.user_id, "role": str(current_user.role.value if hasattr(current_user.role, "value") else current_user.role)}
    return ok(data)
