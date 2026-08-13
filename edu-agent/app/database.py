"""
数据库 & 存储 连接管理。

一共 5 类存储：
1. MySQL（主库）：业务数据（用户/课程/订单/学习记录），asyncmy 异步（Cython 高性能版）
2. Milvus（向量库）：知识库向量化，部署在虚拟机 Docker
3. MongoDB（文档库）：对话状态持久化，motor 异步驱动
4. MinIO（对象存储）：课程视频/课件/题库附件/用户上传文件
5. Neo4j（图谱库）：知识图谱 / 个性化推荐 / 思维导图（P1+P4+P9）

关键设计：
- 懒加载 + 全局单例 + lifespan 优雅关闭
- 所有查询/写入走统一辅助函数（参数化 SQL、事务 CM）
- 远端存储连不上时，在 DEBUG 模式只告警不阻断启动（保证本地可开发）
"""
from __future__ import annotations

import asyncio
import typing
from contextlib import asynccontextmanager

import asyncmy
from asyncmy.pool import Pool
from asyncmy.connection import Connection
from asyncmy.cursors import Cursor
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymilvus import MilvusClient
from minio import Minio

from app.common.exceptions import DatabaseError
from app.common.logging import logger
from app.config import settings


# ============================================================
# MySQL 连接池（全局单例）
# ============================================================
_mysql_pool: Pool | None = None
# 并发闸：限制同时 acquire 的连接数 ≤ MYSQL_POOL_SIZE（asyncmy 的 Pool.acquire 不支持
# timeout 参数，池满时 acquire 会无限排队 → 单点并发写即可占满连接挂死全后端）。
# 先取信号量（带超时）再取连接，从根上消除无限排队（task04 #2）。
_pool_semaphore: asyncio.Semaphore | None = None


async def _pool_acquire(pool: Pool) -> Connection:
    """
    从连接池取连接：并发闸 + 超时 + 重试（task04 #2 并发写挂死修复）。

    背景：pool maxsize 有限，并发写 + 行锁竞争时 acquire 无超时会无限排队，
    单点并发写即可占满全部连接 → 全后端 MySQL 类 API 挂死。
    方案：信号量把并发 acquire 数限制在 maxsize 内；取信号量与取连接均设
    MYSQL_POOL_ACQUIRE_TIMEOUT 超时，超时短暂退避重试 MYSQL_POOL_ACQUIRE_RETRIES 次，
    仍失败抛 DatabaseError（业务侧 5xx，绝不挂死）。
    """
    timeout = float(getattr(settings, "MYSQL_POOL_ACQUIRE_TIMEOUT", 10.0) or 10.0)
    retries = max(1, int(getattr(settings, "MYSQL_POOL_ACQUIRE_RETRIES", 2) or 2))
    sem = _pool_semaphore
    if sem is None:
        # 兜底：init_mysql 未执行（如单测直连）时退化为无闸直取
        return await pool.acquire()
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            await asyncio.wait_for(sem.acquire(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            last_exc = exc
            logger.warning(
                f"[mysql.pool] 并发闸 acquire 超时（{timeout}s，第 {attempt + 1}/{retries} 次，"
                f"maxsize={settings.MYSQL_POOL_SIZE}），退避后重试..."
            )
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
        try:
            return await asyncio.wait_for(pool.acquire(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            last_exc = exc
            sem.release()
            logger.warning(
                f"[mysql.pool] 连接 acquire 超时（{timeout}s，第 {attempt + 1}/{retries} 次），退避后重试..."
            )
            await asyncio.sleep(0.2 * (attempt + 1))
        except Exception:
            sem.release()
            raise
    raise DatabaseError(
        "MySQL 连接池繁忙",
        detail=f"pool acquire 超时（{timeout}s × {retries} 次），连接数可能已达 maxsize",
    ) from last_exc


def _pool_release(pool: Pool, conn: Connection) -> None:
    """归还连接 + 释放并发闸（与 _pool_acquire 成对使用，缺一不可）。"""
    pool.release(conn)
    if _pool_semaphore is not None:
        _pool_semaphore.release()


async def init_mysql():
    """初始化 MySQL 连接池（asyncmy Cython 高性能版，参数与 aiomysql 兼容）。"""
    global _mysql_pool, _pool_semaphore
    logger.info(f"初始化 MySQL 连接池: {settings.MYSQL_HOST}:{settings.MYSQL_PORT} (asyncmy)")
    _mysql_pool = await asyncmy.create_pool(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DATABASE,
        charset=settings.MYSQL_CHARSET,
        autocommit=False,
        pool_recycle=settings.MYSQL_POOL_RECYCLE,
        minsize=1,
        maxsize=settings.MYSQL_POOL_SIZE,
    )
    _pool_semaphore = asyncio.Semaphore(int(settings.MYSQL_POOL_SIZE))
    logger.info("MySQL 连接池已创建")


async def close_mysql():
    global _mysql_pool, _pool_semaphore
    if _mysql_pool is not None:
        _mysql_pool.close()
        await _mysql_pool.wait_closed()
        _mysql_pool = None
        _pool_semaphore = None
        logger.info("MySQL 连接池已关闭")


def get_mysql_pool() -> Pool:
    if _mysql_pool is None:
        raise RuntimeError("MySQL 连接池未初始化，请先调用 init_mysql()")
    return _mysql_pool


# ============================================================
# 2. Milvus 客户端（全局单例）
# ============================================================
_milvus_client: MilvusClient | None = None


def init_milvus():
    global _milvus_client
    logger.info(f"初始化 Milvus 连接: {settings.MILVUS_URI}")
    # DEBUG 模式下 3 秒快速超时，避免 Milvus 虚拟机没启动时卡很久
    milvus_kwargs = dict(
        uri=settings.MILVUS_URI,
        token=settings.MILVUS_TOKEN if settings.MILVUS_TOKEN else None,
        db_name=settings.MILVUS_DB,
    )
    if settings.DEBUG:
        milvus_kwargs.update(timeout=3.0)
    _milvus_client = MilvusClient(**milvus_kwargs)
    version = _milvus_client.get_server_version()
    logger.info(f"Milvus 连接成功，服务器版本: {version}")


def close_milvus():
    global _milvus_client
    if _milvus_client:
        _milvus_client.close()
        _milvus_client = None
        logger.info("Milvus 客户端已关闭")


def get_milvus_client() -> MilvusClient:
    if _milvus_client is None:
        raise RuntimeError("Milvus 客户端未初始化，请先调用 init_milvus()")
    return _milvus_client


# ============================================================
# 3. MongoDB 连接（全局单例，motor 异步驱动）
# ============================================================
_mongo_client: AsyncIOMotorClient | None = None
_mongo_db: AsyncIOMotorDatabase | None = None


async def init_mongo():
    global _mongo_client, _mongo_db
    logger.info(f"连接 MongoDB: {settings.MONGO_URI}")
    # DEBUG 模式下用 3s 超时，避免远端 MongoDB 挂掉时 lifespan 卡 30 秒
    mongo_timeout_ms = 3000 if settings.DEBUG else None
    mongo_kwargs = {}
    if mongo_timeout_ms is not None:
        mongo_kwargs.update(
            serverSelectionTimeoutMS=mongo_timeout_ms,
            connectTimeoutMS=mongo_timeout_ms,
            socketTimeoutMS=mongo_timeout_ms,
        )
    _mongo_client = AsyncIOMotorClient(settings.MONGO_URI, **mongo_kwargs)
    _mongo_db = _mongo_client[settings.MONGO_DB]
    await _mongo_client.admin.command("ping")
    logger.info(f"MongoDB 连接成功，数据库: {settings.MONGO_DB}")


async def close_mongo():
    global _mongo_client, _mongo_db
    if _mongo_client:
        _mongo_client.close()
        _mongo_db = None
        _mongo_client = None
        logger.info("MongoDB 连接已关闭")


def get_mongo_db() -> AsyncIOMotorDatabase:
    if _mongo_db is None:
        raise RuntimeError("MongoDB 未初始化，请先调用 init_mongo()")
    return _mongo_db


# ============================================================
# 4. MinIO 对象存储（全局单例）
# ============================================================
_minio_client: Minio | None = None


def init_minio() -> None:
    """初始化 MinIO，并自动创建课程/题库/上传三个核心 Bucket。"""
    global _minio_client
    logger.info(f"初始化 MinIO 连接: {settings.MINIO_ENDPOINT} (secure={settings.MINIO_SECURE})")
    # minio 7.2+ 的 Minio.__init__ 不再接受 timeout 参数（需走 http_client），
    # 不再传入；MinIO 不可达时由下方 bucket_exists 的 try/except 兜底
    _minio_client = Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
    required_buckets = [
        settings.MINIO_BUCKET_COURSE,
        settings.MINIO_BUCKET_QUESTION,
        settings.MINIO_BUCKET_UPLOAD,
    ]
    for bucket in required_buckets:
        try:
            exists = _minio_client.bucket_exists(bucket)
            if not exists:
                _minio_client.make_bucket(bucket)
                logger.info(f"MinIO Bucket 已自动创建: {bucket}")
        except Exception as e:
            logger.warning(
                f"MinIO Bucket {bucket} 检查失败（视频/文件上传暂不可用，可忽略）: {e}"
            )
    logger.info("MinIO 初始化完成")


def close_minio() -> None:
    global _minio_client
    if _minio_client:
        _minio_client = None
        logger.info("MinIO 客户端已释放")


def get_minio_client() -> Minio:
    if _minio_client is None:
        raise RuntimeError("MinIO 未初始化，请先调用 init_minio()")
    return _minio_client


# ============================================================
# 5. Neo4j 图谱（全局同步单例）
# ============================================================
# 说明：官方 neo4j 驱动是同步模型（Session/Transaction 阻塞），但 P1 导入管道
# 本身在 anyio.to_thread.run_sync 线程池里执行，所以全局 driver 同步使用即可，
# 不阻塞 FastAPI 事件循环。
_neo4j_driver: typing.Any | None = None
_neo4j_init_failed: bool = False    # 标记：初始化失败过就不再反复尝试，避免持续打日志


def init_neo4j() -> None:
    """
    初始化 Neo4j driver，并做一次 connectivity 探测。

    安全策略：
    - DEBUG / 连不上：只 logger.warning，不抛异常（保证主服务启动）
    - 生产模式（DEBUG=False）且连接失败 -> RuntimeError，避免生产环境静默漏写图谱
    """
    global _neo4j_driver, _neo4j_init_failed

    try:
        from neo4j import GraphDatabase  # 延迟 import，允许不装 neo4j 也能跑其他业务
    except Exception as exc:
        _neo4j_init_failed = True
        logger.warning(f"neo4j 包未安装（跳过图谱能力，可用 pip install neo4j 补齐）：{exc}")
        return

    uri = settings.NEO4J_URI
    user = getattr(settings, "NEO4J_USER", None) or None
    pwd = getattr(settings, "NEO4J_PASSWORD", None) or None
    connect_timeout = float(getattr(settings, "NEO4J_CONNECT_TIMEOUT", 3.0) or 3.0)

    logger.info(f"初始化 Neo4j：{uri}")
    try:
        _neo4j_driver = GraphDatabase.driver(
            uri,
            auth=(user, pwd) if (user and pwd) else None,
            connection_timeout=connect_timeout,
            max_connection_pool_size=20,
        )
        # 同步 ping 一次（DEBUG 下超时短，快速失败）
        database = getattr(settings, "NEO4J_DATABASE", None) or None
        with _neo4j_driver.session(database=database) as session:
            session.execute_read(lambda tx: tx.run("RETURN 1 AS ok").single()[0])
        logger.info("Neo4j 连接成功")
    except Exception as exc:
        _neo4j_init_failed = True
        # 释放坏掉的 driver
        try:
            if _neo4j_driver is not None:
                _neo4j_driver.close()
        except Exception:
            pass
        _neo4j_driver = None
        msg = f"Neo4j 连接失败（知识图谱写入会降级跳过，不影响 Milvus 入库）：{exc}"
        if settings.DEBUG:
            logger.warning(msg)
        else:
            raise RuntimeError(msg) from exc


def close_neo4j() -> None:
    global _neo4j_driver, _neo4j_init_failed
    if _neo4j_driver is not None:
        try:
            _neo4j_driver.close()
        except Exception as exc:
            logger.debug(f"Neo4j driver 关闭异常（忽略）：{exc}")
        _neo4j_driver = None
        _neo4j_init_failed = False
        logger.info("Neo4j driver 已关闭")


def get_neo4j_driver():
    """获取 Neo4j driver；未初始化/失败 -> 返回 None（调用方自行处理 skip）。"""
    global _neo4j_driver, _neo4j_init_failed
    if _neo4j_init_failed:
        return None
    if _neo4j_driver is None:
        # 懒初始化（graph_builder.save_relations_to_neo4j 会在后台线程调用）
        try:
            init_neo4j()
        except Exception:
            return None
    return _neo4j_driver


# ============================================================
# MySQL 事务上下文管理器
# ============================================================
@asynccontextmanager
async def transaction():
    """
    事务上下文管理器。保证多条 SQL 同时成功或同时回滚。

    用法（⚠️ 重要）：
        async with transaction() as (conn, cur):
            await cur.execute("INSERT sys_user ...", args1)
            await cur.execute("INSERT sys_user_auth ...", (user_id, ...))

    注意：事务内**必须**用上下文提供的共享连接 cur 执行 SQL。
    禁止在事务块内调用 execute_write()/fetch_one()/fetch_all() —— 它们会
    从连接池 acquire **独立连接**并自动 commit，导致"事务形同虚设"（task04 #1 根因）。
    """
    pool = get_mysql_pool()
    conn: Connection = await _pool_acquire(pool)
    try:
        async with conn.cursor() as cur:
            try:
                yield conn, cur
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
    finally:
        _pool_release(pool, conn)


# ============================================================
# MySQL 通用查询辅助函数（单语句场景）
# ============================================================
async def fetch_one(sql: str, args: tuple | None = None) -> dict | None:
    """查询单行。返回 dict（列名→值），无数据返回 None。"""
    pool = get_mysql_pool()
    conn = await _pool_acquire(pool)
    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, args or ())
            if cur.description is None:
                return None
            cols = [d[0] for d in cur.description]
            row = await cur.fetchone()
            if row is None:
                return None
            return dict(zip(cols, row))
    finally:
        _pool_release(pool, conn)


async def fetch_all(sql: str, args: tuple | None = None) -> list[dict]:
    """查询多行。返回 list[dict]，无数据返回 []。"""
    pool = get_mysql_pool()
    conn = await _pool_acquire(pool)
    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, args or ())
            if cur.description is None:
                return []
            cols = [d[0] for d in cur.description]
            rows = await cur.fetchall()
            return [dict(zip(cols, r)) for r in rows]
    finally:
        _pool_release(pool, conn)


async def execute_write(
    sql: str,
    args: tuple | None = None,
    *,
    commit: bool = True,
) -> int:
    """
    单条写操作（独立连接 + 自动提交；只用于单语句场景）。
    INSERT 返回 lastrowid；UPDATE/DELETE 返回受影响行数。
    多语句原子事务请用 transaction() CM（事务内用其共享 cur 执行，勿再嵌套本函数）。
    """
    pool = get_mysql_pool()
    conn = await _pool_acquire(pool)
    try:
        async with conn.cursor() as cur:
            await cur.execute(sql, args or ())
            if commit:
                await conn.commit()
            if sql.strip().upper().startswith("INSERT"):
                return typing.cast(int, cur.lastrowid)
            return typing.cast(int, cur.rowcount)
    finally:
        _pool_release(pool, conn)
