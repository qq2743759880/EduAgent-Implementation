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

from typing import Optional
import zlib
from pymilvus import MilvusClient, DataType
from loguru import logger

from app.config import settings
from app.knowledge.models import KnowledgeChunk


COLLECTION_NAME = settings.MILVUS_COLLECTION


def get_milvus_client() -> MilvusClient:
    """获取 MilvusClient 实例

    注意: 实际项目应从 app.database 获取全局单例
    这里为了独立使用，创建新实例（URI 统一走 settings.MILVUS_URI）
    """
    client = MilvusClient(uri=settings.MILVUS_URI, token=settings.MILVUS_TOKEN or None)
    return client


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

    logger.info("Collection 创建成功")
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


def _get_partition_name(tenant_id: str) -> str:
    """将 tenant_id 转换为合法的 Partition 名称

    Args:
        tenant_id: 租户 ID

    Returns:
        Partition 名称
    """
    if tenant_id == "_default":
        return "_default"

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
            }

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
    top_k: int = 30
) -> list[dict]:
    """混合检索 (稠密 + 稀疏) - 支持跨 Partition 搜索

    Args:
        dense_vec: 查询稠密向量 (1024维)
        sparse_vec: 查询稀疏向量 (dict: {index: weight})
        tenant_ids: 要搜索的租户 ID 列表，None 表示搜索所有
        top_k: 返回结果数量

    Returns:
        检索结果列表，包含 chunk_id, score, content 等
    """
    client = get_milvus_client()

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

    # 构建混合检索请求
    from pymilvus import AnnSearchRequest, RRFRanker

    dense_req = AnnSearchRequest(
        data=[dense_vec],
        anns_field="dense_vec",
        param={"metric_type": "COSINE", "params": {"nprobe": 10}},
        limit=top_k,
        expr=None,
    )

    sparse_req = AnnSearchRequest(
        data=[sparse_vec],
        anns_field="sparse_vec",
        param={"metric_type": "IP"},
        limit=top_k,
        expr=None,
    )

    # 执行混合检索
    results = client.hybrid_search(
        collection_name=COLLECTION_NAME,
        reqs=[dense_req, sparse_req],
        ranker=RRFRanker(k=60),
        limit=top_k,
        partition_names=partition_names,
        output_fields=[
            "chunk_id", "content", "content_type",
            "source_file", "tenant_id", "visibility",
            "tags", "difficulty", "resource_type", "author",
            "series_code", "series_name", "category",
            "question_bank_code", "question_code", "question_type"
        ],
    )

    # 格式化结果
    formatted_results = []
    for hits in results:
        for hit in hits:
            entity = hit["entity"]
            formatted_results.append({
                "chunk_id": hit["id"],
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
            })

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
