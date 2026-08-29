# -*- coding: utf-8 -*-
"""task39 验证脚本的公共工具：依赖预检（preflight）+ 结果归档（archive）。

为什么要有这个模块（task39 复盘结论）：
    首轮交付时，报告里引用的 P95=56ms / escalation 幂等数字**都没有落盘产物**，
    只能从终端回显里抄，复跑一次还得手工重定向 —— 数据不可复现、不可被验收者核对。
    同时共享 VM 掉线时，脚本会以极具误导性的方式失败（一堆锁超时/连接错误，
    看起来像产品缺陷，实际是环境没起），排查成本很高。

因此统一两条纪律：
    1. 跑之前先探活：依赖不可达就明确报「环境未就绪」并退出，不产生误导性结果；
    2. 跑之后必归档：明细写入 ``test-reports/<stem>.txt`` / ``.json``，可直接引用。

用法：
    from task39_report import archive, preflight, target_from_settings
    preflight([target_from_settings("redis"), target_from_settings("mysql")], log=_log)
    archive("task39-xxx", REPORT, payload={...}, log=_log)
"""
from __future__ import annotations

import json
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "test-reports"


# ──────────────────────────────────────────────────────────────
# 依赖预检
# ──────────────────────────────────────────────────────────────
def host_port(target: str | tuple[str, int]) -> tuple[str, int] | None:
    """从 DSN / ``host:port`` / ``(host, port)`` 解析出 (host, port)。

    无法解析时返回 ``None``（调用方跳过该项，而不是抛异常中断预检）。
    注意 unix socket（``unix:///tmp/x.sock``）没有端口语义，直接跳过。
    """
    if isinstance(target, tuple):
        return target[0], int(target[1])
    s = (target or "").strip()
    if not s:
        return None
    if "://" in s:
        p = urlparse(s)
        if p.scheme == "unix":
            return None
        if not p.hostname or not p.port:
            return None
        return p.hostname, int(p.port)
    # 裸 host:port（如 MINIO_ENDPOINT）
    if ":" in s:
        h, _, port = s.rpartition(":")
        if h and port.isdigit():
            return h, int(port)
    return None


def probe_tcp(host: str, port: int, timeout: float = 2.0) -> tuple[bool, float]:
    """TCP 探活，返回 (是否可达, 耗时ms)。不可达时耗时仍记录，便于区分「拒绝」和「超时」。"""
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, (time.perf_counter() - t0) * 1000
    except Exception:
        return False, (time.perf_counter() - t0) * 1000


def preflight(
    deps: list[tuple[str, str | tuple[str, int]]],
    log: Callable[[str], None] = print,
    timeout: float = 2.0,
    strict: bool = True,
) -> dict[str, bool]:
    """逐项探活依赖并打印表格。

    :param strict: True 时任一项不可达即抛 ``SystemExit(2)``（带明确提示），
        避免脚本在环境缺失时产出误导性结果；False 时只告警不中断
        （用于「被测系统本就该在依赖缺失下工作」的容灾演练）。
    :return: {依赖名: 是否可达}
    """
    log("=== 依赖预检 ===")
    status: dict[str, bool] = {}
    for name, target in deps:
        hp = host_port(target)
        if hp is None:
            log(f"  [SKIP] {name:8s} 无法解析目标地址：{target!r}")
            status[name] = True  # 解析不了不代表不可达，不阻塞
            continue
        ok, ms = probe_tcp(hp[0], hp[1], timeout=timeout)
        status[name] = ok
        log(f"  [{'OK' if ok else 'DOWN'}] {name:8s} {hp[0]}:{hp[1]}  ({ms:.0f}ms)")
    down = [n for n, ok in status.items() if not ok]
    if down and strict:
        log(f"\n❌ 环境未就绪：{', '.join(down)} 不可达。"
            f"本脚本的压测结论只在依赖在线时成立，已中止（exit 2）。")
        raise SystemExit(2)
    if down:
        log(f"\n⚠️  {', '.join(down)} 不可达（非严格模式，继续：本场景正是要测依赖缺失下的行为）。")
    else:
        log("  全部依赖在线。")
    return status


def target_from_settings(name: str) -> tuple[str, str | tuple[str, int]]:
    """按名字从 settings 取依赖地址，供 :func:`preflight` 直接使用。"""
    from app.config import settings  # 局部导入：脚本可能只想用 archive

    n = name.lower()
    if n == "redis":
        return "redis", settings.REDIS_URL
    if n == "mysql":
        return "mysql", (settings.MYSQL_HOST, settings.MYSQL_PORT)
    if n == "milvus":
        return "milvus", settings.MILVUS_URI
    if n == "neo4j":
        return "neo4j", settings.NEO4J_URI
    if n == "mongo":
        return "mongo", settings.MONGO_URI
    if n == "minio":
        return "minio", settings.MINIO_ENDPOINT
    raise KeyError(f"未知依赖名: {name}")


# ──────────────────────────────────────────────────────────────
# 结果归档
# ──────────────────────────────────────────────────────────────
def archive(
    stem: str,
    report_lines: list[str],
    payload: dict[str, Any] | None = None,
    log: Callable[[str], None] = print,
) -> tuple[Path, Path]:
    """把验证明细落盘到 ``test-reports/<stem>.txt`` 与 ``.json``。

    返回 (txt_path, json_path)。txt 是给人读的完整回显，json 是给机器/报告引用的结构化数据。
    """
    REPORTS.mkdir(parents=True, exist_ok=True)
    txt = REPORTS / f"{stem}.txt"
    js = REPORTS / f"{stem}.json"
    txt.write_text("\n".join(report_lines), encoding="utf-8")
    body = {
        "task": "task39",
        "stem": stem,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report": report_lines,
        **(payload or {}),
    }
    js.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"\n明细已归档: {txt}")
    log(f"            {js}")
    return txt, js
