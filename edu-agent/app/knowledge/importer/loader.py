"""
Milvus 数据加载器 - 支持多租户 Partition 隔离

核心功能:
1. 使用 MilvusClient API (与项目规范一致)
2. 动态创建 Partition (按 tenant_id)
3. 批量插入向量数据
4. 支持混合检索 (稠密 + 稀疏)

Schema 规范 (与 03_P1 文档一致):
- id (INT64, PK): chunk_id 的 hash
- chunk_id (VARCHAR): 唯一标识
- content (VARCHAR): 文本内容
- content_type (VARCHAR): 类型
- source_file (VARCHAR): 来源
- dense_vec (FLOAT_VECTOR, 1024): 稠密向量
- sparse_vec (SPARSE_FLOAT_VECTOR): 稀疏向量
- 动态字段: series_code/series_name/category 等
"""

import hashlib
import re
import time
import zlib
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pymilvus import MilvusClient, DataType
from loguru import logger

from app.config import settings
from app.knowledge.importer.embedder import is_blank_text  # VEC-LOCK：空文本过滤边界兜底
from app.knowledge.models import KnowledgeChunk


COLLECTION_NAME = settings.MILVUS_COLLECTION


# ============================================================
# WNEXT10 F5-a：内部工程/运维文档（internal）标记 + 检索期角色过滤
# ------------------------------------------------------------
# 背景（`test-reports/critique-blind-t4-t9.md` T4-C4 / F5-a）：`_default` 分区混着
# 业务知识与内部工程/运维文档，student 调 `/api/chat/search` 能命中内部实现细节
# （任务编号 task09~14、脚本名 restore_admin.py、认证表结构 sys_user_auth）。
#
# 修法（最小侵入、不破坏检索契约）：
#   1) 导入期打标：load_chunks 对命中 internal 特征的文档写 dynamic field `internal`（bool）。
#      dynamic field 免 alter、免重嵌（与 R03 created_at 同款做法）。
#   2) 检索期过滤：hybrid_search 接受 `include_internal` / `role`，student 一律
#      `internal != true`；admin/manager 不过滤。
#   3) 存量兜底：存量行**没有** internal 字段（回填需人工确认，未执行）→ 结果侧按
#      同一套特征二次剔除（classify_internal），保证存量内部文档同样对 student 不可见。
#
# 特征来源可配置（settings 覆盖，缺省即下方常量）：
#   RAG_INTERNAL_SOURCE_PATTERNS  —— 来源路径特征（正则，作用于 source_file）
#   RAG_INTERNAL_CONTENT_PATTERNS —— 正文特征（正则，作用于 content）
# ============================================================
INTERNAL_FIELD = "internal"
# Milvus dynamic field 过滤表达式（存量行无该字段时同样命中 → 不会误伤业务文档，已实测）
INTERNAL_FILTER_EXPR = f"{INTERNAL_FIELD} != true"
# 只有这两个角色可见 internal 文档（与 permission_gate 的写类角色口径一致）
ROLES_ALLOWED_INTERNAL = ("admin", "manager")

# 来源路径特征：哈希导出的内部文档（.ai-hub / 报告 / 计划 等 md 导出）+ 工程目录
DEFAULT_INTERNAL_SOURCE_PATTERNS = (
    r"^[0-9a-f]{8,32}\.(md|txt|pdf)$",   # 内部文档库哈希导出（实测 1789 行 doc_chunk 全为此形态）
    r"(^|/)\.ai-hub/",
    r"(^|/)test-reports/",
    r"(^|/)refactor_sql/",
    r"(^|/)plans?/artifacts/",
    r"(^|/)scripts?/",
    r"(^|/)deploy/",
    r"(^|/)\.venv/",
    r"kickoff[-_]",
    r"restore_admin\.py",
)
# 正文强特征（高精：业务课程/题库语料实测误伤 <0.1%）
# 注：不放「内部」这类口语词（业务题会出现「隐藏内部实现 / 内部草稿」等误伤）；
# 工程内部性由「任务编号 + 系统表/脚本名 + 内部工程术语」精准锚定。
DEFAULT_INTERNAL_CONTENT_PATTERNS = (
    r"\btask[-_ ]?\d{1,3}\b",
    r"sys_user_auth",
    r"mcp_tool_call_log",
    r"restore_admin\.py",
    r"refactor_sql",
    r"test-reports",
    r"W-NEXT",
    r"\bGWT\b",
    r"编排者",
    r"强制技术批判",
    r"落点",
    r"kickoff[-_]",
)

_PATTERN_CACHE: dict[str, tuple[re.Pattern[str], ...]] = {}


def _internal_patterns(setting_name: str, default: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """取编译好的 internal 特征正则（settings 可覆盖，缺省用模块常量）。"""
    cached = _PATTERN_CACHE.get(setting_name)
    if cached is not None:
        return cached
    raw = getattr(settings, setting_name, None) or default
    pats = tuple(re.compile(p, re.I) for p in raw)
    _PATTERN_CACHE[setting_name] = pats
    return pats


def classify_internal(
    source_file: str | None = None,
    content: str | None = None,
    *,
    internal_flag: bool | None = None,
) -> bool:
    """判定一个文档/分片是否属于「内部工程/运维文档」。

    - `internal_flag` 显式给值（导入方 metadata / 人工指定）时以其为准；
    - 否则按来源路径特征 + 正文强特征判定。
    """
    if internal_flag is not None:
        return bool(internal_flag)
    sf = str(source_file or "")
    body = str(content or "")
    for p in _internal_patterns("RAG_INTERNAL_SOURCE_PATTERNS", DEFAULT_INTERNAL_SOURCE_PATTERNS):
        if p.search(sf):
            return True
    for p in _internal_patterns("RAG_INTERNAL_CONTENT_PATTERNS", DEFAULT_INTERNAL_CONTENT_PATTERNS):
        if p.search(body):
            return True
    return False


def role_allows_internal(role) -> bool:
    """角色是否可见 internal 文档（admin/manager 可见，其余一律不可见）。"""
    val = getattr(role, "value", role)
    return str(val or "").strip().lower() in ROLES_ALLOWED_INTERNAL


# 请求级上下文：由 app/chat/router.py 按当前用户角色注入（检索链路不改签名即可感知角色）
_INTERNAL_ALLOWED: ContextVar[bool] = ContextVar("rag_internal_allowed", default=True)


def set_internal_visibility(allowed: bool) -> Token:
    """设置当前请求上下文的 internal 可见性，返回 reset 用的 token。"""
    return _INTERNAL_ALLOWED.set(bool(allowed))


def reset_internal_visibility(token: Token) -> None:
    """恢复上一个 internal 可见性（配合 set_internal_visibility 的 finally 使用）。"""
    try:
        _INTERNAL_ALLOWED.reset(token)
    except Exception:  # pragma: no cover - token 跨 context 时的兜底
        pass


def internal_visibility_allowed() -> bool:
    """当前上下文是否允许检索 internal 文档（未注入时 = True，保持历史行为）。"""
    return bool(_INTERNAL_ALLOWED.get())


def _row_is_internal(row: dict) -> bool:
    """结果侧判定：存量行无 internal 字段（None）→ 退回内容/来源特征兜底。"""
    flag = row.get(INTERNAL_FIELD)
    if flag is None:
        return classify_internal(row.get("source_file"), row.get("content"))
    if isinstance(flag, str):
        return flag.strip().lower() in ("1", "true", "yes")
    return bool(flag)


def _and_filter(expr: str | None, clause: str) -> str:
    """把过滤子句 AND 进既有表达式（空表达式直接返回子句）。"""
    expr = (expr or "").strip()
    if not expr:
        return clause
    return f"({expr}) and ({clause})"


# ============================================================
# R03 · chunk_id 唯一化（契约 C-R-CHUNK）
# 新格式: {tenant}:{sha256(canonical_content)[:16]}:{seq}
#   canonical_content = contextualize 之前的原始 chunk 文本 =
#       chunk.raw_content（有值） else chunk.content（题库/代码/未开启 contextualize）
#   tenant          = 导入上下文租户（公共=_default / 用户=user_{id} / course_public）
#   seq             = 同租户同 canonical 内容块的出现序号(1-based)，保证同内容多块可区分
# 唯一权威生成点=load_chunks（同时掌握 tenant + 最终 canonical 内容）：
# parse/chunker 生成的 chunk_id 仅是过渡值，入库前的最终 FK 以本处为准。
# 幂等：同一导入（同内容+同顺序）→ 同 chunk_id → upsert 去重；跨租户同名同内容 → 租户前缀隔离。
# ============================================================
def canonical_content_of(chunk: KnowledgeChunk) -> str:
    """返回契约定义的 canonical_content（contextualize 之前的原文）。"""
    return (chunk.raw_content or chunk.content or "").strip()


def canonical_id(tenant_id: str, canonical_content: str, seq: int) -> str:
    """按契约 C-R-CHUNK 生成 chunk_id：{tenant}:{sha256(canonical)[:16]}:{seq}。"""
    h = hashlib.sha256(canonical_content.encode("utf-8")).hexdigest()[:16]
    return f"{tenant_id}:{h}:{seq}"


def _assign_canonical_ids(chunks: list[KnowledgeChunk], tenant_id: str) -> None:
    """就地改写 chunk.chunk_id 为全局唯一 canonical id（同 batch 内按 (tenant,hash) 计数 seq）。"""
    counts: dict[str, int] = {}
    for c in chunks:
        canonical = canonical_content_of(c)
        h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        key = f"{tenant_id}:{h}"
        counts[key] = counts.get(key, 0) + 1
        c.chunk_id = f"{key}:{counts[key]}"


def get_milvus_client() -> MilvusClient:
    """获取 MilvusClient 实例（优先全局单例，兜底新建带超时实例）。

    修复（task04 修正轮 2）：此前每次调用都新建 MilvusClient 实例且不传 timeout，
    Milvus 不可达时 pymilvus 默认 10s 连接超时 → 调用方（async 路由）同步等待 10s，
    阻塞 asyncio 事件循环等效 DoS。现在：
    1) 优先复用 app.database 全局单例：连接复用 + DEBUG 下已配置 3s 超时；
    2) 单例未初始化（启动时 Milvus 不可达被降级跳过，get_milvus_client 抛
       RuntimeError）→ 新建兜底实例，显式传 timeout=3.0（pymilvus 默认 10s），
       不可达时快速失败，不长时间阻塞调用方。

    注意：本函数仍是同步阻塞调用，P1 导入管道在 anyio 线程池执行没问题；
    async 路由中调用必须自行移出事件循环（anyio.to_thread.run_sync + wait_for）。
    """
    try:
        from app.database import get_milvus_client as _db_get_client
        return _db_get_client()
    except Exception:
        return MilvusClient(
            uri=settings.MILVUS_URI,
            token=settings.MILVUS_TOKEN or None,
            timeout=3.0,
        )


def ensure_collection_exists() -> bool:
    """确保 collection 存在。返回 True=新创建。"""
    client = get_milvus_client()

    if client.has_collection(COLLECTION_NAME):
        stats = client.get_collection_stats(COLLECTION_NAME)
        logger.info(f"Collection '{COLLECTION_NAME}' 已存在，当前 {stats['row_count']} 条记录")
        return False

    logger.info(f"创建 collection: {COLLECTION_NAME}")

    # 创建 Schema (与文档规范一致)
    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)

    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("chunk_id", DataType.VARCHAR, max_length=128)
    schema.add_field("content", DataType.VARCHAR, max_length=8192)
    schema.add_field("content_type", DataType.VARCHAR, max_length=32)
    schema.add_field("source_file", DataType.VARCHAR, max_length=256)
    schema.add_field("dense_vec", DataType.FLOAT_VECTOR, dim=1024)
    schema.add_field("sparse_vec", DataType.SPARSE_FLOAT_VECTOR)

    # 多租户字段
    schema.add_field("tenant_id", DataType.VARCHAR, max_length=100)
    schema.add_field("visibility", DataType.VARCHAR, max_length=20)

    # 创建索引
    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="dense_vec",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        params={"nlist": 128},
    )
    index_params.add_index(
        field_name="sparse_vec",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="IP",
    )

    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params,
    )

    # 关键：创建 collection 后必须显式 load，否则索引不加载到内存，搜索会失败
    # Milvus 2.x 默认不自动 load，需要手动触发
    client.load_collection(COLLECTION_NAME)
    logger.info("Collection 已加载到内存，索引就绪")
    return True


def ensure_partition_exists(tenant_id: str) -> str:
    """确保 Partition 存在，返回 Partition 名称

    Args:
        tenant_id: 租户 ID，如 'user_1001' 或 '_default'

    Returns:
        Partition 名称
    """
    partition_name = _get_partition_name(tenant_id)

    if partition_name == "_default":
        return partition_name

    client = get_milvus_client()

    # 检查 Partition 是否存在
    partitions = client.list_partitions(COLLECTION_NAME)
    if partition_name not in partitions:
        client.create_partition(
            collection_name=COLLECTION_NAME,
            partition_name=partition_name
        )
        logger.info(f"Partition '{partition_name}' 创建成功")

    return partition_name


# task31 course_public 保留分区：课程知识隔离用户上传（GWT③）
COURSE_PUBLIC = getattr(settings, "COURSE_PUBLIC_PARTITION", "course_public")


def _get_partition_name(tenant_id: str) -> str:
    """将 tenant_id 转换为合法的 Partition 名称

    Args:
        tenant_id: 租户 ID

    Returns:
        Partition 名称
    """
    if tenant_id == "_default":
        return "_default"
    # 课程公共知识 → 独立保留分区（不混入用户上传/促销文案）
    if tenant_id == COURSE_PUBLIC:
        return COURSE_PUBLIC

    # 确保以字母开头，符合 Milvus Partition 命名规范
    safe_id = tenant_id.replace("-", "_")
    if not safe_id.startswith("user_"):
        safe_id = f"user_{safe_id}"
    return safe_id


def load_chunks(chunks: list[KnowledgeChunk], tenant_id: str = "_default") -> int:
    """将知识块加载到 Milvus (支持 Partition)

    Args:
        chunks: 知识块列表
        tenant_id: 目标租户 ID，决定数据存入哪个 Partition

    Returns:
        成功插入的条数
    """
    if not chunks:
        return 0

    # R03: 入库前统一改写 chunk_id 为全局唯一 canonical id（tenant + 内容 hash + seq）
    _assign_canonical_ids(chunks, tenant_id)

    # VEC-LOCK：空文本/纯标点 chunk 过滤不入库（禁 '.' 占位污染；embed_node 已过滤，此处边界兜底）
    chunks = [c for c in chunks if not is_blank_text(c.content)]
    if not chunks:
        logger.warning(f"load_chunks：全部 chunk 为空/纯标点，无可入库内容（tenant={tenant_id}）")
        return 0

    # 确保 Collection 和 Partition 存在
    ensure_collection_exists()
    partition_name = ensure_partition_exists(tenant_id)

    client = get_milvus_client()
    total = len(chunks)
    inserted = 0

    for i in range(0, total, 200):  # batch_size = 200
        batch = chunks[i : i + 200]

        data = []
        for chunk in batch:
            # 构建稀疏向量字典
            sparse_dict = {}
            if chunk.sparse_indices and chunk.sparse_values:
                for idx, val in zip(chunk.sparse_indices, chunk.sparse_values):
                    sparse_dict[str(idx)] = float(val)

            row = {
                # 确定性 ID：Python 内置 hash() 每次进程随机（PYTHONHASHSEED），
                # 会导致重跑导入生成不同 PK、旧数据无法去重；改用 crc32 稳定哈希
                "id": zlib.crc32(chunk.chunk_id.encode("utf-8")),
                "chunk_id": chunk.chunk_id,
                "content": chunk.content[:8000],
                "content_type": chunk.content_type.value,
                "source_file": chunk.source_file,
                "dense_vec": chunk.dense_vector,
                "sparse_vec": sparse_dict if sparse_dict else {"0": 0.0},
                "tenant_id": tenant_id,
                "visibility": chunk.visibility.value,
                # R03: created_at 作为 dynamic field 承载（Milvus enable_dynamic_field=True，免 alter 免重嵌）
                "created_at": chunk.created_at.isoformat() if chunk.created_at else datetime.now(timezone.utc).isoformat(),
                # WNEXT10 F5-a：内部工程/运维文档标记（dynamic field，学生检索侧按角色过滤）
                # 每条都写（True/False）——保证过滤表达式对全量行语义一致，不依赖字段缺失时的行为
                INTERNAL_FIELD: bool(classify_internal(
                    chunk.source_file,
                    chunk.raw_content or chunk.content,
                    internal_flag=chunk.extra.get("internal"),
                )),
            }
            # VEC-LOCK：入库元数据四字段（embed_node 写入 chunk.extra，供对账/机验）
            # embedding_model（含 revision）/embed_precision/embed_normalized/embed_fallback
            for _mf in ("embedding_model", "embed_precision", "embed_normalized", "embed_fallback"):
                _mv = chunk.extra.get(_mf)
                if _mv is not None:
                    row[_mf] = _mv

            # 动态字段 (通用元数据)
            if chunk.tags:
                row["tags"] = ",".join(chunk.tags)
            if chunk.difficulty:
                row["difficulty"] = chunk.difficulty
            if chunk.resource_type:
                row["resource_type"] = chunk.resource_type
            if chunk.author:
                row["author"] = chunk.author
            if chunk.prerequisites:
                row["prerequisites"] = ",".join(chunk.prerequisites)
            if chunk.keywords:
                row["keywords"] = ",".join(chunk.keywords)

            # 动态字段 (业务元数据 - 由解析器自动提取)
            if chunk.series_code:
                row["series_code"] = chunk.series_code
            if chunk.series_name:
                row["series_name"] = chunk.series_name
            if chunk.category:
                row["category"] = chunk.category
            if chunk.audience:
                row["audience"] = chunk.audience
            if chunk.goal:
                row["goal"] = chunk.goal
            if chunk.question_bank_code:
                row["question_bank_code"] = chunk.question_bank_code
            if chunk.question_bank_name:
                row["question_bank_name"] = chunk.question_bank_name
            if chunk.question_code:
                row["question_code"] = chunk.question_code
            if chunk.question_type:
                row["question_type"] = chunk.question_type

            # 动态字段 (task30 contextualize：原文 + 前缀 + 降级标注)
            # content 列已存前缀版（提召回）；raw_content 存去前缀原文（answer 展示用）
            if chunk.raw_content:
                row["raw_content"] = chunk.raw_content[:8000]
            if chunk.context_prefix:
                row["context_prefix"] = chunk.context_prefix
            if chunk.extra.get("contextualized"):
                row["contextualized"] = 1
            if chunk.extra.get("contextualize_degraded_reason"):
                row["contextualize_degraded_reason"] = chunk.extra["contextualize_degraded_reason"]

            data.append(row)

        # 插入数据到指定 Partition（upsert：同 chunk_id 重复导入幂等，不产生重复行）
        try:
            client.upsert(
                collection_name=COLLECTION_NAME,
                data=data,
                partition_name=partition_name
            )
            inserted += len(data)
        except Exception as e:
            logger.error(f"Milvus 插入失败 (batch {i//200}): {e}")
            continue

    logger.info(f"成功插入 {inserted} 条数据到 Partition '{partition_name}'")
    return inserted


def hybrid_search(
    dense_vec: list[float],
    sparse_vec: dict,
    tenant_ids: list[str] | None = None,
    top_k: int = 30,
    timeout: float | None = 8.0,
    filter_expr: str | None = None,
    include_internal: bool | None = None,
    role: str | None = None,
) -> list[dict]:
    """混合检索 (稠密 + 稀疏) - 支持跨 Partition 搜索

    Args:
        dense_vec: 查询稠密向量 (1024维)
        sparse_vec: 查询稀疏向量 (dict: {index: weight})
        tenant_ids: 要搜索的租户 ID 列表，None 表示搜索所有
        top_k: 返回结果数量
        filter_expr: Milvus 布尔过滤表达式（task31 course_public 过滤防促销/班次混入），
                    同时作用于 dense / sparse 两个 ann 请求
        include_internal: 是否召回「内部工程/运维文档」（WNEXT10 F5-a）。
                    None（默认）= 按 role / 请求上下文判定；False = 强制过滤（学生视角）
        role: 调用方角色（admin/manager 可见 internal；其余不可见）。None 时读请求级
                    上下文（由 app/chat/router.py 注入），上下文也没注入则沿用历史行为（可见）
    Returns:
        检索结果列表，包含 chunk_id, score, content 等
    """
    client = get_milvus_client()

    # WNEXT10 F5-a：解析 internal 可见性（显式参数 > 角色 > 请求上下文）
    if include_internal is None:
        include_internal = role_allows_internal(role) if role is not None else internal_visibility_allowed()
    include_internal = bool(include_internal)

    # 确定要搜索的 Partitions
    if tenant_ids is None:
        partition_names = None  # None = 搜索所有分区
    else:
        partition_names = [_get_partition_name(tid) for tid in tenant_ids]
        # 只搜索实际存在的 Partition，避免「partition xxx not found」异常
        # （如用户还没有任何私有知识时 user_{id} 分区不存在）
        try:
            existing = set(client.list_partitions(COLLECTION_NAME))
        except Exception:
            existing = set()
        if existing:
            partition_names = [p for p in partition_names if p in existing]
            if not partition_names:
                return []

    # WNEXT10 F5-a：不可见 internal 时，把过滤子句 AND 进既有 expr（dense/sparse 双通道同款）
    if not include_internal:
        filter_expr = _and_filter(filter_expr, INTERNAL_FILTER_EXPR)

    # 构建混合检索请求
    from pymilvus import AnnSearchRequest, RRFRanker

    dense_req = AnnSearchRequest(
        data=[dense_vec],
        anns_field="dense_vec",
        param={"metric_type": "COSINE", "params": {"nprobe": int(getattr(settings, "RAG_DENSE_NPROBE", 32))}},
        limit=top_k,
        expr=filter_expr,
    )

    sparse_req = AnnSearchRequest(
        data=[sparse_vec],
        anns_field="sparse_vec",
        param={"metric_type": "IP"},
        limit=top_k,
        expr=filter_expr,
    )

    # 执行混合检索（timeout 兜底，避免 Milvus 慢时拖死请求链路 —— P1-4）
    results = client.hybrid_search(
        collection_name=COLLECTION_NAME,
        reqs=[dense_req, sparse_req],
        ranker=RRFRanker(k=60),
        limit=top_k,
        timeout=timeout,
        partition_names=partition_names,
        output_fields=[
            "chunk_id", "content", "content_type",
            "source_file", "tenant_id", "visibility",
            "tags", "difficulty", "resource_type", "author",
            "series_code", "series_name", "category",
            "question_bank_code", "question_code", "question_type",
            "raw_content", "context_prefix",
            "contextualized", "contextualize_degraded_reason",
            # WNEXT10 F5-a：回带 internal 标记，供结果侧兜底过滤（存量行无此字段 → 键缺失）
            INTERNAL_FIELD,
        ],
    )

    # 格式化结果
    formatted_results = []
    for hits in results:
        for hit in hits:
            entity = hit["entity"]
            row = {
                "chunk_id": entity.get("chunk_id") or str(hit["id"]),  # task31 修复：真实 chunk_id（原误用 crc32 主键致身份错乱）
                "score": hit["distance"],
                "content": entity.get("content", ""),
                "content_type": entity.get("content_type", ""),
                "tenant_id": entity.get("tenant_id", ""),
                "visibility": entity.get("visibility", ""),
                "source_file": entity.get("source_file", ""),
                "tags": entity.get("tags", ""),
                "difficulty": entity.get("difficulty", ""),
                "resource_type": entity.get("resource_type", ""),
                "author": entity.get("author", ""),
                "series_code": entity.get("series_code", ""),
                "series_name": entity.get("series_name", ""),
                "category": entity.get("category", ""),
                "question_bank_code": entity.get("question_bank_code", ""),
                "question_code": entity.get("question_code", ""),
                "question_type": entity.get("question_type", ""),
                "raw_content": entity.get("raw_content", ""),
                "context_prefix": entity.get("context_prefix", ""),
                "contextualized": entity.get("contextualized", ""),
                "contextualize_degraded_reason": entity.get("contextualize_degraded_reason", ""),
                INTERNAL_FIELD: entity.get(INTERNAL_FIELD),
            }
            # WNEXT10 F5-a：存量行无 internal 字段（回填需人工确认，尚未执行）→ 结果侧按
            # 同一套特征（来源/正文）二次剔除，保证 student 检索不漏内部文档。
            if not include_internal and _row_is_internal(row):
                continue
            formatted_results.append(row)

    return formatted_results


def list_all_partitions() -> list[dict]:
    """列出所有 Partition 及其统计信息

    Returns:
        分区信息列表
    """
    client = get_milvus_client()
    partitions = client.list_partitions(COLLECTION_NAME)

    partition_info = []
    for p_name in partitions:
        try:
            stats = client.get_partition_stats(
                collection_name=COLLECTION_NAME,
                partition_name=p_name
            )
            partition_info.append({
                "name": p_name,
                "row_count": stats.get("row_count", 0)
            })
        except Exception:
            partition_info.append({
                "name": p_name,
                "row_count": 0
            })

    return partition_info


def drop_partition(tenant_id: str) -> bool:
    """删除指定 Partition

    Args:
        tenant_id: 租户 ID

    Returns:
        是否删除成功
    """
    partition_name = _get_partition_name(tenant_id)

    if partition_name == "_default":
        logger.warning("不能删除默认 Partition")
        return False

    client = get_milvus_client()

    partitions = client.list_partitions(COLLECTION_NAME)
    if partition_name not in partitions:
        logger.warning(f"Partition '{partition_name}' 不存在")
        return False

    client.drop_partition(
        collection_name=COLLECTION_NAME,
        partition_name=partition_name
    )
    logger.info(f"Partition '{partition_name}' 已删除")
    return True


# ============================================================
# Phase 2: Milvus 健康检查 & 性能监控
# ============================================================

def get_collection_health() -> dict:
    """
    Milvus 健康检查（供 /health/detail 和 Prometheus 使用）。

    返回：
    - loaded: collection 是否已加载到内存
    - row_count: 总行数
    - partitions: 各分区行数
    - index_types: 索引类型描述
    """
    client = get_milvus_client()
    health = {
        "collection": COLLECTION_NAME,
        "exists": False,
        "loaded": False,
        "row_count": 0,
        "partitions": {},
        "index_types": {},
    }
    try:
        if not client.has_collection(COLLECTION_NAME):
            return health
        health["exists"] = True

        # 加载状态
        load_state = client.get_load_state(COLLECTION_NAME)
        health["loaded"] = True  # get_load_state 不抛异常即已加载

        # 统计信息
        stats = client.get_collection_stats(COLLECTION_NAME)
        health["row_count"] = stats.get("row_count", 0)

        # 各分区行数
        for p_name in client.list_partitions(COLLECTION_NAME):
            try:
                p_stats = client.get_partition_stats(COLLECTION_NAME, p_name)
                health["partitions"][p_name] = p_stats.get("row_count", 0)
            except Exception:
                health["partitions"][p_name] = -1  # -1 = 获取失败

        # 索引信息
        try:
            indexes = client.list_indexes(COLLECTION_NAME)
            for idx_name in indexes:
                desc = client.describe_index(COLLECTION_NAME, idx_name)
                health["index_types"][idx_name] = desc.get("index_type", "unknown")
        except Exception:
            pass
    except Exception as exc:
        health["error"] = str(exc)
    return health


def get_search_latency_ms() -> float | None:
    """
    快速探测搜索延迟（用零向量做一次搜索，返回毫秒）。

    面试考点：为什么用零向量？零向量查询不会产生有意义的结果，
    但能准确测量 Milvus 的索引检索延迟（包括网络 RTT）。
    """
    try:
        client = get_milvus_client()
        t0 = time.perf_counter()
        # 用随机小向量做探测，避免零向量被特殊处理
        import random
        dummy_vec = [random.random() for _ in range(1024)]
        client.search(
            collection_name=COLLECTION_NAME,
            data=[dummy_vec],
            anns_field="dense_vec",
            limit=1,
            param={"metric_type": "COSINE", "params": {"nprobe": 1}},
            timeout=2.0,
        )
        return (time.perf_counter() - t0) * 1000
    except Exception:
        return None
