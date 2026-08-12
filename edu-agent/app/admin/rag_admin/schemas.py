"""
P7 路径 B：管理端 RAG 控制台 —— 数据模型。
所有 API 请求/响应、MySQL 行对象都在这里集中定义，便于 service / router 共享。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# 1. 知识库/Partition 元数据（对应 rag_collection_meta）
# ============================================================
class CollectionMeta(BaseModel):
    id: int
    collection_name: str
    partition_name: str
    tenant_id: str | None = None
    display_name: str
    row_count: int = 0
    source_count: int = 0
    last_rebuild_at: datetime | None = None
    last_snapshot_at: datetime
    status: Literal["ready", "rebuilding", "error"] = "ready"
    status_message: str | None = None
    visibility: Literal["public", "private"] = "public"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionRebuildRequest(BaseModel):
    """重建指定 Partition 的索引。不传=重建 _default 公共库。"""
    collection_name: str = "knowledge_chunk_v1"
    partition_name: str = "_default"
    mode: Literal["incremental", "full"] = Field(
        default="incremental",
        description="incremental=只补缺失的 chunk 索引，full=清空后重建整库（更慢但干净）",
    )


class CollectionRebuildResponse(BaseModel):
    job_id: str = Field(..., description="重建任务 ID（r_xxx 短 uuid），用于前端轮询")
    accepted: bool = True
    message: str
    estimated_rows: int = 0


# ============================================================
# 2. 检索参数预设（对应 rag_param_preset）
# ============================================================
class ParamPreset(BaseModel):
    id: int
    preset_name: str
    is_default: bool = False
    description: str | None = None
    top_k: int = 20
    final_max_k: int = 6
    cutoff_drop_ratio: float = 0.4
    rrf_k: int = 60
    use_hyde: bool = True
    enable_graph: bool = True
    llm_model_pref: str = "fast"
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ParamPresetCreate(BaseModel):
    preset_name: str = Field(..., min_length=2, max_length=64)
    is_default: bool = False
    description: str | None = Field(default=None, max_length=512)
    top_k: int = Field(default=20, ge=1, le=200)
    final_max_k: int = Field(default=6, ge=1, le=30)
    cutoff_drop_ratio: float = Field(default=0.4, ge=0.05, le=0.9)
    rrf_k: int = Field(default=60, ge=5, le=500)
    use_hyde: bool = True
    enable_graph: bool = True
    llm_model_pref: Literal["fast", "quality", "local"] = "fast"


class ParamPresetApplyRequest(BaseModel):
    """把指定预设"应用"到一次管理员检索上（不入库，只是请求时复用参数）"""
    preset_id: int = Field(..., description="要应用的 rag_param_preset.id")


# ============================================================
# 3. 审计日志（对应 rag_audit_log）
# ============================================================
class AuditLogEntry(BaseModel):
    id: int
    audit_id: str
    user_id: int
    session_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    role: str = "student"
    query: str
    rewrite_query: str | None = None
    retrieved_count: int | None = None
    final_count: int | None = None
    llm_model: str | None = None
    latency_ms: int = 0
    degraded_reason: str | None = None
    is_stream: bool = False
    error_message: str | None = None
    param_preset_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    page: int
    page_size: int
    total: int
    items: list[AuditLogEntry]


# ============================================================
# 4. 管理员高级检索（跨租户全库，可选 contentType/tenant 筛选）
# ============================================================
class AdminSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    # 跨租户筛选：None = 全库，列表 = 指定 tenant（user_id 字符串或 "_default"）
    tenant_ids: Optional[list[str]] = Field(default=None, description="None=管理员全库；['_default','user_802']=只搜指定分区")
    content_types: Optional[list[str]] = Field(default=None, description="None=全类型；['document','question','slide']=按内容类型筛选")
    # 可选：应用预设 preset_id（若传则覆盖 top_k/final_max_k/cutoff_drop_ratio 等）
    preset_id: int | None = None
    # 以下参数在没传 preset_id 时生效
    top_k: int = Field(default=20, ge=1, le=200)
    final_max_k: int = Field(default=8, ge=1, le=30)
    cutoff_drop_ratio: float = Field(default=0.4, ge=0.05, le=0.9)
    use_hyde: bool = True
    enable_graph: bool = True
    rrf_k: int = Field(default=60, ge=5, le=500)
    model: Literal["fast", "quality", "local"] = "fast"


class AdminSearchResponse(BaseModel):
    # 直接复用 RetrievedDoc，避免重复定义
    docs: list[dict]
    graph_entities: list[dict]
    retrieved_count: int
    final_count: int
    rewrite_query: str | None = None
    degraded_reason: str | None = None
    applied_preset_name: str | None = Field(default=None, description="若应用了预设，这里显示预设名；None=使用请求显式参数")
