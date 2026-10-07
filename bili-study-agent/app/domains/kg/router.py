# -*- coding: utf-8 -*-
"""KG-2 学习路径端点（R-N1，contracts/reshape-r-kg.json draft：3 端点）。

- GET /api/kg/course/{course_id}/path?from=&to=   课程内最短先修路径（环检测 fail-closed）
- GET /api/kg/chapter/{chapter_code}/upstream     章节前置知识面
- GET /api/kg/chapter/{chapter_code}/downstream   章节后续知识面

范式对齐：
- 匿名只读（与 course C 端一致）；响应壳 {code:0,message:"ok",data}（ok()）；
- 失败 AppException → 全局 handler（40460/40461/40462/40910/50301）；
- Neo4j driver 为同步模型——端点用同步 def，FastAPI 自动投递线程池，不阻塞事件循环。
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.resp import ok
from app.domains.kg import service as svc

router = APIRouter(tags=["kg · 知识图谱（Neo4j 先修图）"])


@router.get("/api/kg/course/{course_id}/path", summary="课程内学习路径（先修图最短路 + 环检测）")
def course_path(
    course_id: int,
    from_: str = Query(..., alias="from", min_length=1, max_length=64, description="起点知识点 code"),
    to: str = Query(..., min_length=1, max_length=64, description="终点知识点 code"),
):
    data = svc.course_path(course_id, from_, to)
    return ok(data=data.model_dump(mode="json"))


@router.get("/api/kg/chapter/{chapter_code}/upstream", summary="章节前置知识面（先修知识点 + 所属章节）")
def chapter_upstream(chapter_code: str):
    data = svc.chapter_neighbors(chapter_code, "upstream")
    return ok(data=data.model_dump(mode="json"))


@router.get("/api/kg/chapter/{chapter_code}/downstream", summary="章节后续知识面（依赖本章的知识点 + 所属章节）")
def chapter_downstream(chapter_code: str):
    data = svc.chapter_neighbors(chapter_code, "downstream")
    return ok(data=data.model_dump(mode="json"))
