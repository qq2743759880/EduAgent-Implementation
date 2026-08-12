"""
健康检查接口 —— 验证所有依赖是否可用。

为什么需要健康检查：
1. 部署时确认服务就绪
2. 监控系统定期探测（K8s liveness/readiness probe）
3. 开发时快速排查"数据库连不上"等问题

接口设计：
- GET /health → 快速检查（不连数据库，只检查服务自身）
- GET /health/detail → 详细检查（连接所有数据库，返回详细状态）
"""
from fastapi import APIRouter

from app.common.logging import logger
from app.config import settings

router = APIRouter(prefix="/health", tags=["健康检查"])


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
        from app.database import get_mysql_pool
        pool = get_mysql_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
        results["mysql"] = "ok"
    except Exception as e:
        logger.error(f"MySQL 健康检查失败: {e}")
        results["mysql"] = f"error: {str(e)[:100]}"
        all_ok = False

    # 检查 Milvus
    try:
        from app.database import get_milvus_client
        client = get_milvus_client()
        client.list_collections()
        results["milvus"] = "ok"
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

    return {
        "status": "ok" if all_ok else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "components": results,
    }
