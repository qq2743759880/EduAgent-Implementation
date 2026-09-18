# -*- coding: utf-8 -*-
"""KG 域 DTO（R-N1，contracts/reshape-r-kg.json draft 的响应体权威定义）。

响应壳沿用契约①：{code:0, message:"ok", data:<本文件 DTO>}；
失败 code=<字符串错误码>（见 app/common/error_codes.py KG 段），data=null。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class KgNodeRef(BaseModel):
    """图谱节点引用（轻量，路径/邻域响应内复用）。"""

    key: str = Field(description="节点唯一键，如 kp:KP-001 / module:xxx_m1 / series:12")
    type: str = Field(description="节点类型：course|chapter|knowledge_point|doc_chunk")
    code: str | None = Field(None, description="业务编码（KP code / module_code / series_code）")
    name: str | None = Field(None, description="展示名")


class KgPathStep(BaseModel):
    """学习路径步骤（step 从 1 开始）。"""

    step: int
    key: str
    code: str | None = None
    name: str | None = None


class KgCoursePathData(BaseModel):
    """GET /api/kg/course/{course_id}/path 响应 data。"""

    course: KgNodeRef
    from_code: str = Field(description="起点知识点 code（入参回显）")
    to_code: str = Field(description="终点知识点 code（入参回显）")
    found: bool = Field(description="先修图上是否可达")
    hops: int = Field(0, description="路径边数；found=false 时为 0")
    path: list[KgPathStep] = Field(default_factory=list, description="路径步骤序列")
    cycle_checked: bool = Field(True, description="是否已做先修环检测（false=跳过检测的异常路径）")


class KgChapterNeighborsData(BaseModel):
    """GET /api/kg/chapter/{chapter_code}/upstream|downstream 响应 data。"""

    chapter: KgNodeRef
    direction: str = Field(description="upstream|downstream（入参回显）")
    mentioned_kps: list[KgNodeRef] = Field(
        default_factory=list, description="本章覆盖（MENTIONS）的知识点"
    )
    neighbor_kps: list[KgNodeRef] = Field(
        default_factory=list, description="方向性邻接知识点：upstream=前置，downstream=后续"
    )
    neighbor_chapters: list[KgNodeRef] = Field(
        default_factory=list,
        description="邻接知识点所属章节（按 MENTIONS 归属；已剔除本章节自身）",
    )
