"""
健康检查接口 —— 验证所有依赖是否可用。

为什么需要健康检查：
1. 部署时确认服务就绪
2. 监控系统定期探测（K8s liveness/readiness probe）
3. 开发时快速排查"数据库连不上"等问题

接口设计：
- GET /health → 快速检查（不连数据库，只检查服务自身）
- GET /health/detail → 详细检查（连接所有数据库，返回详细状态）
- GET /health/warmup → task39 GWT③ 冷启动预热状态（逐组件耗时/成败）
"""
from fastapi import APIRouter

from app.common.logging import logger
from app.config import settings

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("/warmup")
async def health_warmup(wait: float = 0.0):
    """冷启动预热状态（task39 GWT③）。

    预热在 lifespan 后台任务中执行，不阻塞启动。本端点用于：
    - 压测前断言「模型已就绪」（status=ready 才允许开始计时，否则首请求会把
      模型加载时间算进 P95，压测数据失真）
    - 容灾演练后确认预热链路是否仍可用（如 sidecar 被 kill 后是否落到本地回退）

    Query:
        wait: 最多等待预热完成的秒数（0 = 立即返回当前状态）
    """
    from app.core import warmup

    if wait and wait > 0:
        await warmup.wait_ready(timeout=min(float(wait), 120.0))
    snap = warmup.snapshot()
    failed = [n for n, c in snap["components"].items() if not c["ok"]]
    return {
        "status": snap["status"],
        "elapsed_ms": snap["elapsed_ms"],
        "started_at": snap["started_at"],
        "finished_at": snap["finished_at"],
        "failed": failed,
        "components": snap["components"],
    }


@router.get("")
async def health_check():
    """
    快速健康检查（不依赖外部服务）。

    用于：
    - 负载均衡器探测
    - 确认服务是否在跑
    """
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@router.get("/detail")
async def health_detail():
    """
    详细健康检查（检查所有数据库连接）。

    Returns:
        各组件状态，任一失败则 status 为 "degraded"
    """
    results = {}
    all_ok = True

    # 检查 MySQL
    try:
        from app.database import fetch_one
        # 走统一并发闸（_pool_acquire/_pool_release），避免直连绕过信号量计数
        await fetch_one("SELECT 1")
        results["mysql"] = "ok"
    except Exception as e:
        logger.error(f"MySQL 健康检查失败: {e}")
        results["mysql"] = f"error: {str(e)[:100]}"
        all_ok = False

    # 检查 Milvus
    try:
        from app.database import get_milvus_client
        from app.knowledge.importer.loader import get_collection_health
        client = get_milvus_client()
        client.list_collections()
        # Phase 2: 获取 Milvus 详细健康信息（collection 加载状态/行数/分区/索引）
        milvus_health = get_collection_health()
        results["milvus"] = {
            "status": "ok",
            "collection": milvus_health.get("collection"),
            "loaded": milvus_health.get("loaded"),
            "row_count": milvus_health.get("row_count"),
            "partitions": milvus_health.get("partitions"),
        }
    except Exception as e:
        logger.error(f"Milvus 健康检查失败: {e}")
        results["milvus"] = f"error: {str(e)[:100]}"
        all_ok = False

    # 检查 MongoDB
    try:
        from app.database import get_mongo_db
        db = get_mongo_db()
        await db.command("ping")
        results["mongodb"] = "ok"
    except Exception as e:
        logger.error(f"MongoDB 健康检查失败: {e}")
        results["mongodb"] = f"error: {str(e)[:100]}"
        all_ok = False

    # 检查 MinIO
    try:
        from app.database import get_minio_client
        client = get_minio_client()
        client.bucket_exists("edu-course")  # 任一 bucket 可达即视为服务在线
        results["minio"] = "ok"
    except Exception as e:
        logger.error(f"MinIO 健康检查失败: {e}")
        results["minio"] = f"error: {str(e)[:100]}"
        all_ok = False

    # 检查 Neo4j
    try:
        from app.database import get_neo4j_driver
        driver = get_neo4j_driver()
        driver.verify_connectivity()
        results["neo4j"] = "ok"
    except Exception as e:
        logger.error(f"Neo4j 健康检查失败: {e}")
        results["neo4j"] = f"error: {str(e)[:100]}"
        all_ok = False

    # 检查 Redis（Phase 1）
    try:
        from app.database import get_redis
        r = get_redis()
        await r.ping()
        # 获取 Redis 内存使用信息
        info = await r.info("memory")
        results["redis"] = {
            "status": "ok",
            "used_memory_human": info.get("used_memory_human", "N/A"),
        }
    except Exception as e:
        logger.warning(f"Redis 健康检查失败（缓存/限流降级）: {e}")
        results["redis"] = f"degraded: {str(e)[:100]}"
        # Redis 降级属「功能可用、性能下降」（§6.4），不置 all_ok=False

    # 冷启动预热状态（task39 GWT③）：压测前用它断言模型已就绪
    try:
        from app.core import warmup
        results["warmup"] = warmup.snapshot()
    except Exception as e:  # noqa: BLE001 — 健康检查自身绝不 500
        results["warmup"] = f"error: {str(e)[:100]}"

    return {
        "status": "ok" if all_ok else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "components": results,
    }
