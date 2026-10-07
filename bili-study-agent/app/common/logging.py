"""
日志系统 —— 基于 loguru 的结构化日志。

特性：
1. 自动按大小轮转（100MB 一个文件）
2. 自动清理旧日志（保留 7 天）
3. 支持 trace_id（追踪一次请求的完整链路）
4. 彩色输出（本地开发友好）
5. 生产模式 JSON 结构化输出（日志收集系统如 Loki/ELK 直接解析）
"""
import json
import sys
from pathlib import Path

from loguru import logger

from app.config import settings


def _json_sink(message) -> None:
    """loguru 自定义 sink：把每条日志序列化为 JSON 一行。"""
    record = message.record
    payload = {
        "time": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "level": record["level"].name,
        "logger": f"{record['name']}:{record['function']}:{record['line']}",
        "message": record["message"],
    }
    extra = record.get("extra") or {}
    for k, v in extra.items():
        payload[k] = v
    if record.get("exception") is not None:
        payload["exception"] = str(record["exception"])
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def setup_logging():
    """
    配置 loguru 日志系统。

    日志输出：
    - 控制台：DEBUG 彩色 / 生产 JSON（sink 函数）
    - 文件（app.log）：JSON 结构化
    - 文件（error.log）：只记录 ERROR 及以上（JSON）
    """
    # 移除默认的 handler
    logger.remove()

    # ============================================================
    # 控制台输出（开发彩色，生产 JSON）
    # ============================================================
    if settings.DEBUG:
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>",
            level=settings.LOG_LEVEL,
            colorize=True,
        )
    else:
        logger.add(
            _json_sink,
            level=settings.LOG_LEVEL,
        )

    # ============================================================
    # 文件输出：所有日志（JSON，serialize=True 供收集系统解析）
    # ============================================================
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "app.log",
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        level="DEBUG",
        serialize=True,
        encoding="utf-8",
    )

    # ============================================================
    # 文件输出：只记录错误（JSON）
    # ============================================================
    logger.add(
        log_dir / "error.log",
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        compression="zip",
        level="ERROR",
        serialize=True,
        encoding="utf-8",
    )

    logger.info(f"日志系统已初始化，级别: {settings.LOG_LEVEL}，目录: {log_dir}")


# 在模块导入时自动初始化
setup_logging()
