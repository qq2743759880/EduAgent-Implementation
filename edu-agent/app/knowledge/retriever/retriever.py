"""
知识检索器 - 基于 Milvus Partition 的多租户检索

检索策略:
- 普通用户: 搜索 _default (公共) + user_{id} (私有)
- 管理员: 可搜索所有 Partition
"""

from loguru import logger

from app.knowledge.importer.loader import hybrid_search


class KnowledgeRetriever:
    """知识检索器 - 支持多租户隔离检索"""

    def __init__(self):
        pass

    def retrieve(
        self,
        query_dense_vector: list[float],
        query_sparse_vector: dict,
        user_id: str | None = None,
        is_admin: bool = False,
        top_k: int = 30
    ) -> list[dict]:
        """检索知识

        Args:
            query_dense_vector: 查询的稠密向量 (1024维)
            query_sparse_vector: 查询的稀疏向量 (dict: {index: weight})
            user_id: 当前用户 ID，用于确定 Partition 范围
            is_admin: 是否为管理员，管理员可检索所有分区
            top_k: 返回结果数量

        Returns:
            检索结果列表，包含 chunk_id, score, content 等
        """
        # 确定要搜索的租户 ID 列表
        tenant_ids = self._determine_search_partitions(user_id, is_admin)

        logger.debug(
            f"检索请求: user_id={user_id}, is_admin={is_admin}, "
            f"搜索分区: {tenant_ids}"
        )

        # 调用混合检索 (稠密 + 稀疏 + RRF 融合)
        results = hybrid_search(
            dense_vec=query_dense_vector,
            sparse_vec=query_sparse_vector,
            tenant_ids=tenant_ids,
            top_k=top_k
        )

        # 普通用户：过滤掉其他租户的私有数据
        if not is_admin and user_id:
            results = self._filter_private_data(results, user_id)

        return results

    @staticmethod
    def _determine_search_partitions(
        user_id: str | None,
        is_admin: bool
    ) -> list[str] | None:
        """确定要搜索的分区范围

        Args:
            user_id: 当前用户 ID
            is_admin: 是否为管理员

        Returns:
            租户 ID 列表，None 表示搜索所有
        """
        if is_admin:
            return None  # 管理员搜索所有分区

        if user_id:
            # 普通用户：公共分区 + 自己的私有分区
            return ["_default", f"user_{user_id}"]

        return ["_default"]  # 未登录用户仅搜索公共分区

    @staticmethod
    def _filter_private_data(results: list[dict], current_user_id: str) -> list[dict]:
        """过滤私有数据 - 普通用户只能看到自己的私有数据

        Args:
            results: 检索结果
            current_user_id: 当前用户 ID

        Returns:
            过滤后的结果
        """
        filtered = []
        for result in results:
            tenant_id = result.get("tenant_id", "_default")

            # 公共数据（_default）所有人可见
            if tenant_id == "_default":
                filtered.append(result)
                continue

            # 当前用户的私有数据
            if tenant_id == f"user_{current_user_id}":
                filtered.append(result)
                continue

            # 其他用户的私有数据 - 跳过
            logger.debug(
                f"过滤掉非当前用户的私有数据: "
                f"result_tenant={tenant_id}, current_user={current_user_id}"
            )

        return filtered

    def search_public_only(
        self,
        query_dense_vector: list[float],
        query_sparse_vector: dict,
        top_k: int = 30
    ) -> list[dict]:
        """仅搜索公共知识（不依赖用户登录）

        Args:
            query_dense_vector: 查询的稠密向量
            query_sparse_vector: 查询的稀疏向量
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        return hybrid_search(
            dense_vec=query_dense_vector,
            sparse_vec=query_sparse_vector,
            tenant_ids=["_default"],
            top_k=top_k
        )
