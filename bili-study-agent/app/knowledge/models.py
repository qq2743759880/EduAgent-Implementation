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
    content: str = Field(description="文本内容（task30 起可为带上下文前缀的版本，用于向量化和编辑答案）")
    content_type: ContentType = Field(description="内容类型")

    # ========== task30 Contextual Retrieval ==========
    raw_content: Optional[str] = Field(None, description="原始内容（去前缀前的原文，answer 展示用；None=未 contextualize）")
    context_prefix: Optional[str] = Field(None, description="上下文前缀（50-100 token），检索召回增强用；None=未生成")

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
    series_codes: list[str] = Field(default_factory=list, description="多系列绑定编码列表（一题多课时逐条保留，§23 不压单值）")
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
    owner_id: Optional[int] = Field(None, description="private 文档所属用户，检索授权用")

    # ========== W2-S4：Document IR provenance（可选；flag OFF 时全 None/空 = 零影响） ==========
    # 契约（PRD v2.2 §6-3）：block_type 用 ir.BlockType 的字符串值（避免 enum 耦合）；
    # security_scope 不落 KnowledgeChunk 正式字段（可见性走既有 visibility 轴，scope 随 extra 透传）。
    block_ids: list[str] = Field(
        default_factory=list,
        description="来源 block_id 列表（ir 命名 {document_id}:b{seq}；仅 DOC_IR_ENABLED 分支有值）",
    )
    block_type: Optional[str] = Field(
        None, description="来源块类型（text/title/table/code...，取 ir.BlockType 字符串值）"
    )
    page_start: Optional[int] = Field(None, ge=1, description="起始页（legacy_str 后端无页码恒 1）")
    page_end: Optional[int] = Field(None, ge=1, description="结束页")
    parser_backend: Optional[str] = Field(
        None, description="解析后端名（legacy 过渡分支写 legacy_str；后续 mineru/pdfplumber 等）"
    )
    parse_fingerprint: Optional[str] = Field(
        None, description="解析指纹 sha256(sha|backend|version|options)[:16]（同输入稳定，重复解析跳过判据）"
    )

    # ========== 向量（由 embedder 填充） ==========
    dense_vector: list[float] = Field(default_factory=list, description="稠密向量 1024 维")
    sparse_indices: list[int] = Field(default_factory=list, description="稀疏向量索引")
    sparse_values: list[float] = Field(default_factory=list, description="稀疏向量值")

    # ========== 元信息 ==========
    source_file: str = Field("", description="来源文件名")
    chunk_strategy: ChunkStrategy = Field(ChunkStrategy.SEMANTIC_WINDOW, description="分块策略")
    created_at: datetime = Field(default_factory=datetime.now)
    extra: dict = Field(default_factory=dict, description="扩展元数据，支持动态字段")


# ============================ W2-S2：导入源资产（import_source_asset） ============================
# stage 冻结词汇（模块级常量冻结，不新建 enum 类——避免污染 ContentType 轴；
# 词汇表来源：PRD v2.2 §2 import_source_asset 设计，W2 只写 queued_parser→ir_ready 两态）。
ASSET_STAGE_QUEUED_PARSER = "queued_parser"   # 已建 asset，待 parser 认领
ASSET_STAGE_PARSING = "parsing"               # parser 已租约认领，解析中
ASSET_STAGE_IR_READY = "ir_ready"             # IR 已产出（W2 终态；S4 真实写入）
ASSET_STAGE_INGESTED = "ingested"             # 已向量入库（W3 接管后出现）
ASSET_STAGE_FAILED = "failed"                 # 解析失败（error 落原因）

# 全量冻结词汇（校验用；顺序即生命周期顺序，failed 例外）
IMPORT_ASSET_STAGES = (
    ASSET_STAGE_QUEUED_PARSER,
    ASSET_STAGE_PARSING,
    ASSET_STAGE_IR_READY,
    ASSET_STAGE_INGESTED,
    ASSET_STAGE_FAILED,
)


class ImportSourceAsset(BaseModel):
    """
    导入源资产（W2-S2）：`import_source_asset` 表的行级模型，task 1:N 细化
    （每个源文件一行）。parser job 的 claim/retry/lease 全部在此表，
    task 级 stage 保留为聚合视图（PRD v2.2 §2）——不建第二套 task 状态机。
    """
    asset_id: str = Field(..., description="资产 ID（创建时生成的 uuid 短 id）")
    task_id: str = Field(..., description="所属导入任务（逻辑关联 knowledge_import_task.task_id）")
    file_index: int = Field(..., description="文件在任务内的序号（0 起）")
    bucket: Optional[str] = Field(None, description="MinIO bucket")
    object_key: Optional[str] = Field(None, description="MinIO object key")
    file_name: Optional[str] = Field(None, description="原始文件名")
    sha256: Optional[str] = Field(None, description="源文件 sha256（64 hex；上传时计算）")
    size_bytes: Optional[int] = Field(None, description="文件大小（字节）")
    mime: Optional[str] = Field(None, description="MIME 类型")
    document_id: str = Field(..., description="文档身份 ID（asset 创建时为每个文件生成 uuid 短 id）")
    stage: str = Field(ASSET_STAGE_QUEUED_PARSER, description=f"阶段（冻结词汇：{'/'.join(IMPORT_ASSET_STAGES)}）")
    retry_count: int = Field(0, description="重试次数")
    execution_epoch: int = Field(0, description="执行纪元（每次 CAS 成功 +1，防并发重复推进）")
    lease_owner: Optional[str] = Field(None, description="当前租约持有者（worker 标识）")
    lease_until: Optional[datetime] = Field(None, description="租约到期时间")
    parse_fingerprint: Optional[str] = Field(None, description="解析指纹（16 hex，同指纹跳过重复解析）")
    artifact_ref: Optional[str] = Field(None, description="解析产物引用（IR/清洗产物）")
    error: Optional[str] = Field(None, description="失败原因")
    created_at: Optional[datetime] = Field(None, description="创建时间（DB DEFAULT）")


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
    extra: dict = Field(default_factory=dict, description="导入元数据（来源资产与解析参数；不作为权限权威源）")

    # ==================== W2-S4：安全元数据 first-class（PRD v2.2 §6-1/2） ====================
    # 正式字段落 ImportState（拔除 upload.py:249 `state.__dict__.setdefault("extra", {})`
    # hack 的契约前置——upload.py 的收敛归 S5 组处理；过渡期 parse_node 双读
    # state.visibility → state.extra["visibility"]，S5 收敛后删 extra 分支）。
    visibility: Optional[str] = Field(
        None, description="可见性 private/public（v2.2 §6 fail-closed：None=未声明，user_upload 下解析直接失败）"
    )
    owner_id: Optional[int] = Field(
        None, description="发起者用户 ID（public 资产可为 None；传播到 chunk extra.provenance）"
    )
    security_scope: str = Field(
        "default", description="安全域 scope（v2.2 §6 first-class；多租户扩展位，随 chunk extra 透传）"
    )
