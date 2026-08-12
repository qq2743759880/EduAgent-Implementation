"""
知识库数据模型 - 定义知识条目的结构

设计要点:
1. KnowledgeChunk 是 Milvus 中存储的最小单元
2. extra 字段支持动态元数据扩展（Milvus enable_dynamic_field=True）
3. ImportState 是 LangGraph 管道的状态载体
4. GraphRelation 是 Neo4j 图谱关系的载体
5. 元数据分通用字段和业务字段，通用字段适用于所有文件类型

多租户设计:
- tenant_id: 对应 Milvus Partition，实现物理隔离
- visibility: 控制数据访问范围
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    """内容类型（决定解析方式，不再决定切分策略）"""
    COURSE_INTRO = "course_intro"          # 课程介绍（系列级）
    COURSE_MODULE = "course_module"        # 课程模块（模块级）
    QUESTION = "question"                  # 题目
    DOC_CHUNK = "doc_chunk"                # 通用文档片段


class ChunkStrategy(str, Enum):
    """
    分块策略 - 根据文本特征选择，与文件类型无关。

    策略选择路由（纯文本特征判断，不依赖文件名）：
    ┌─────────────────────────────────────────────────────────────┐
    │ 文本特征             │ 切分策略          │ 说明                  │
    ├─────────────────────────────────────────────────────────────┤
    │ 含 #/##/### 标题     │ HEADING_BASED     │ 按 Markdown 标题切分  │
    │ 有双换行短文本        │ PARAGRAPH         │ 按自然段落切分        │
    │ 通用文档 <=5000 字    │ SEMANTIC_WINDOW   │ 语义边界 + 字数滑窗   │
    │ 超长文本 >5000 字     │ WORD_WINDOW       │ 纯字数滑窗（兜底）    │
    └─────────────────────────────────────────────────────────────┘

    特殊规则：如果 chunk 已经 <= MAX_CHUNK_SIZE (800字)，
    则跳过切分直接保留（适用于预解析的课程/题目 chunk）。
    """
    HEADING_BASED = "heading_based"        # 基于 Markdown 标题层级
    PARAGRAPH = "paragraph"                # 按自然段落
    SEMANTIC_WINDOW = "semantic_window"    # 语义感知滑窗
    WORD_WINDOW = "word_window"            # 纯字数滑窗（兜底）


class Visibility(str, Enum):
    """可见性类型 - 用于多租户隔离和权限控制"""
    PRIVATE = "private"      # 仅上传者可见，存入 user_{id} Partition
    PUBLIC = "public"        # 全系统可见，存入 _default Partition


class KnowledgeChunk(BaseModel):
    """
    一条知识库记录（向量化后入库的最小单位）。

    设计原则:
    - chunk_id 全局唯一（用于去重、更新）
    - content 检索和生成的主体
    - 通用元数据适用于所有文件类型（支持过滤检索）
    - 业务元数据由解析器自动提取（课程/题目专用）
    - extra 字段支持动态扩展（Milvus enable_dynamic_field=True）
    """
    chunk_id: str = Field(description="全局唯一 ID，格式如 course_001 / question_bank_q0001")
    content: str = Field(description="文本内容（用于向量化和生成答案）")
    content_type: ContentType = Field(description="内容类型")

    # ========== 通用元数据（适用于所有文件类型） ==========
    tags: list[str] = Field(default_factory=list, description="标签列表，用于关键词检索和过滤")
    difficulty: Optional[str] = Field(None, description="难度等级：入门/中级/高级")
    resource_type: Optional[str] = Field(None, description="资源类型：文档/视频/代码/题库")
    author: Optional[str] = Field(None, description="作者/上传者")
    prerequisites: list[str] = Field(default_factory=list, description="前置知识点 ID 列表")
    keywords: list[str] = Field(default_factory=list, description="关键词列表（用于稀疏向量增强）")

    # ========== 业务元数据（由解析器自动提取） ==========
    # 课程相关
    series_code: Optional[str] = Field(None, description="课程系列编码")
    series_name: Optional[str] = Field(None, description="课程系列名称")
    module_codes: list[str] = Field(default_factory=list, description="模块编码列表")
    category: Optional[str] = Field(None, description="课程分类")
    audience: Optional[str] = Field(None, description="适合人群")
    goal: Optional[str] = Field(None, description="学习目标")

    # 题目相关
    question_bank_code: Optional[str] = Field(None, description="题库编码")
    question_bank_name: Optional[str] = Field(None, description="题库名称")
    question_code: Optional[str] = Field(None, description="题目编码")
    question_type: Optional[str] = Field(None, description="题型：单选/多选/判断")

    # ========== 多租户字段 ==========
    tenant_id: str = Field(default="_default", description="租户 ID，对应 Milvus Partition")
    visibility: Visibility = Field(default=Visibility.PUBLIC, description="可见性：private/public")

    # ========== 向量（由 embedder 填充） ==========
    dense_vector: list[float] = Field(default_factory=list, description="稠密向量 1024 维")
    sparse_indices: list[int] = Field(default_factory=list, description="稀疏向量索引")
    sparse_values: list[float] = Field(default_factory=list, description="稀疏向量值")

    # ========== 元信息 ==========
    source_file: str = Field("", description="来源文件名")
    chunk_strategy: ChunkStrategy = Field(ChunkStrategy.SEMANTIC_WINDOW, description="分块策略")
    created_at: datetime = Field(default_factory=datetime.now)
    extra: dict = Field(default_factory=dict, description="扩展元数据，支持动态字段")


class GraphRelation(BaseModel):
    """
    知识图谱关系（存入 Neo4j）。

    用于构建课程 prerequisite、知识点关联、学习路径等关系。
    """
    source_entity: str = Field(..., description="源实体 ID")
    target_entity: str = Field(..., description="目标实体 ID")
    relation_type: str = Field(..., description="关系类型：contains/prerequisite/related")
    properties: dict = Field(default_factory=dict, description="关系属性")


class ImportTask(BaseModel):
    """导入任务（跟踪进度和结果）。"""
    task_id: str = Field(..., description="导入任务 ID")
    source_files: list[str] = Field(default_factory=list, description="导入文件列表")
    status: str = "pending"                # pending / running / done / failed
    total_chunks: int = 0
    imported_chunks: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class ImportState(BaseModel):
    """
    LangGraph State —— 管道各节点共享的状态。

    执行流程:
    parse → chunks 填充
    chunk → chunks 填充完整（含切分）
    embed → 向量填充
    load → imported_count 累加
    graph_build → relations 填充

    任意节点出错 → error 字段填上，后续节点检查到 error 就跳过

    多租户:
    - tenant_id 用于路由到 Milvus Partition
    - task_type: system_init(管理员) / user_upload(用户)
    """
    task_id: str = Field(..., description="导入任务 ID")
    source_files: list[str] = Field(default_factory=list, description="导入文件列表")
    chunks: list[KnowledgeChunk] = Field(default_factory=list, description="当前导入的 chunk 列表")
    relations: list[GraphRelation] = Field(default_factory=list, description="图谱关系列表")
    imported_count: int = 0
    error: Optional[str] = None
    tenant_id: str = Field(default="_default", description="目标租户 ID")
    task_type: str = Field(default="user_upload", description="任务类型：system_init/user_upload")
