"""
日志系统 —— 基于 loguru 的结构化日志。

特性：
1. 自动按大小轮转（100MB 一个文件）
2. 自动清理旧日志（保留 7 天）
3. 支持 trace_id（追踪一次请求的完整链路）
4. 彩色输出（本地开发友好）
"""
import sys
from pathlib import Path

from loguru import logger

from app.config import settings


def setup_logging():
    """
    配置 loguru 日志系统。

    日志输出：
    - 控制台：彩色格式，INFO 及以上
    - 文件（app.log）：详细格式，DEBUG 及以上
    - 文件（error.log）：只记录 ERROR 及以上
    """
    # 移除默认的 handler
    logger.remove()

    # ============================================================
    # 控制台输出（开发模式彩色，生产模式简洁）
    # ============================================================
    if settings.DEBUG:
        # 开发模式：彩色 + 详细信息
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
            level=settings.LOG_LEVEL,
            colorize=True,
        )
    else:
        # 生产模式：纯文本 JSON（便于日志收集系统解析）
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
            level=settings.LOG_LEVEL,
            colorize=False,
        )

    # ============================================================
    # 文件输出：所有日志
    # ============================================================
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "app.log",
        rotation=settings.LOG_ROTATION,      # 100MB 轮转
        retention=settings.LOG_RETENTION,    # 保留 7 天
        compression="zip",                   # 压缩旧日志
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        encoding="utf-8",
    )

    # ============================================================
    # 文件输出：只记录错误
    # ============================================================
    logger.add(
        log_dir / "error.log",
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        encoding="utf-8",
    )

    logger.info(f"日志系统已初始化，级别: {settings.LOG_LEVEL}，目录: {log_dir}")


# 在模块导入时自动初始化
setup_logging()
