#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EduAgent CI 门禁（task98）—— DB 验收体系：schema / counts / quality / all。

复用：
  - `edu-agent/.env` 的 MYSQL_*（settings 配置源）为 DSN 事实源（不新造连接层/不引新依赖）；
  - 既有 `asyncmy`（项目已装 MySQL 驱动）直接连接；
  - 既有 `test-reports/interface_acceptance_final.py` / scripts/verify_task07_*.py 的校验口径
    （引用完整性 / 有效性 / 时序 / 一致性）收敛为轻量 DB 断言，可独立于后端运行。

子命令：
  schema  对比 DB 当前表结构 vs .schema-acceptance.yaml（核心表+关键列存在性），缺失→FAIL
  counts  抽查核心表行数 vs 基线（容差判定），偏差→FAIL
  quality DB 数据质量不变量（孤儿/金额/枚举/时序/一致性），任一违规>0→FAIL
  all     依次跑上面三子命令，任一 FAIL → exit 1（CI 门禁用）

退出码：0=通过，1=失败。
用法：edu-agent/.venv/Scripts/python.exe -X utf8 scripts/verify.py all
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncmy
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EDU_AGENT = PROJECT_ROOT / "edu-agent"
ENV_FILE = EDU_AGENT / ".env"
SCHEMA_YAML = PROJECT_ROOT / ".schema-acceptance.yaml"

BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def _load_dsn() -> dict:
    """DB DSN 来源（优先级）：环境变量(CI 注入) > edu-agent/.env(settings 事实源) > 默认值。

    复用既有配置源，不引新连接层。CI 通过 env 注入 MYSQL_*；本地走 .env。
    """
    dsn = {
        "MYSQL_HOST": "localhost",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "",
        "MYSQL_DATABASE": "edu",
        "MYSQL_CHARSET": "utf8mb4",
    }
    # 1) env 优先（GitHub Actions secrets/workflow env）
    for k in dsn:
        if os.environ.get(k):
            dsn[k] = os.environ[k]
    # 2) .env 兜底（settings 同源）
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k in dsn and not os.environ.get(k):
                dsn[k] = v.strip()
    return dsn


DSN = _load_dsn()


def _load_baseline() -> dict:
    if not SCHEMA_YAML.exists():
        print(f"{RED}✗ 缺基线文件: {SCHEMA_YAML}{RESET}")
        sys.exit(1)
    with open(SCHEMA_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


BASELINE = _load_baseline()


async def _connect():
    return await asyncmy.connect(
        host=DSN["MYSQL_HOST"],
        port=int(DSN["MYSQL_PORT"]),
        user=DSN["MYSQL_USER"],
        password=DSN["MYSQL_PASSWORD"],
        db=DSN["MYSQL_DATABASE"],
        charset=DSN["MYSQL_CHARSET"],
    )


async def _fetchone(cur, sql, args=None):
    await cur.execute(sql, args or ())
    row = await cur.fetchone()
    return row[0] if row else None


# ============================================================
# schema：核心表 + 关键列存在性
# ============================================================
async def run_schema() -> bool:
    tables = BASELINE.get("schema", {}).get("tables", {})
    print(f"{BOLD}=== schema：DB 表结构 vs .schema-acceptance.yaml（{len(tables)} 表）==={RESET}")
    conn = await _connect()
    fails = 0
    try:
        async with conn.cursor() as cur:
            for table, spec in tables.items():
                cols = set(spec.get("required_columns", []))
                # 表存在性
                n = await _fetchone(
                    cur,
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_schema=%s AND table_name=%s AND table_type='BASE TABLE'",
                    (DSN["MYSQL_DATABASE"], table),
                )
                if not n:
                    print(f"  {RED}✗ {table}: 表缺失{RESET}")
                    fails += 1
                    continue
                # 列存在性
                await cur.execute(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE table_schema=%s AND table_name=%s",
                    (DSN["MYSQL_DATABASE"], table),
                )
                db_cols = {r[0] for r in await cur.fetchall()}
                missing = sorted(cols - db_cols)
                if missing:
                    print(f"  {RED}✗ {table}: 缺失列 {missing}{RESET}")
                    fails += 1
                else:
                    print(f"  {GREEN}✓ {table}: 表 + {len(cols)} 关键列就位{RESET}")
    finally:
        conn.close()
    return _summary("schema", fails)


# ============================================================
# counts：核心表行数 vs 基线（容差判定）
# ============================================================
async def run_counts() -> bool:
    tables = BASELINE.get("counts", {}).get("tables", {})
    if not tables:
        print(f"{RED}✗ counts 基线为空{RESET}")
        return False
    print(f"{BOLD}=== counts：核心表行数 vs 基线（{len(tables)} 表）==={RESET}")
    conn = await _connect()
    fails = 0
    try:
        async with conn.cursor() as cur:
            for table, spec in tables.items():
                expected = int(spec.get("expected", 0))
                tol_abs = float(spec.get("tol_abs", 0))
                tol_frac = float(spec.get("tol_frac", 0))
                got = await _fetchone(cur, f"SELECT COUNT(*) FROM `{table}`")
                got = int(got or 0)
                tol = max(tol_abs, abs(expected * tol_frac))
                dev = abs(got - expected)
                if dev <= tol:
                    print(f"  {GREEN}✓ {table}: {got} vs {expected}（容差 {tol:.0f}）PASS{RESET}")
                else:
                    print(f"  {RED}✗ {table}: {got} vs {expected}（偏差 {dev} > {tol:.0f}）FAIL{RESET}")
                    fails += 1
    finally:
        conn.close()
    return _summary("counts", fails)


# ============================================================
# quality：DB 数据质量不变量（接口验收脚本的 DB 侧轻量断言）
# ============================================================
# 每项：(名称, SQL 返回违规计数, 说明)。全部须为 0。
QUALITY_CHECKS = [
    # 引用完整性（孤儿）
    ("referential:series_cohort.series_id→series",
     "SELECT COUNT(*) FROM series_cohort sc LEFT JOIN series s ON s.id=sc.series_id WHERE s.id IS NULL",),
    ("referential:series_cohort_course.cohort_id→series_cohort",
     "SELECT COUNT(*) FROM series_cohort_course sc LEFT JOIN series_cohort c ON c.id=sc.cohort_id WHERE c.id IS NULL",),
    ("referential:series_cohort_session.series_cohort_course_id→series_cohort_course",
     "SELECT COUNT(*) FROM series_cohort_session ss LEFT JOIN series_cohort_course c ON c.id=ss.series_cohort_course_id WHERE c.id IS NULL",),
    ("referential:order_item.order_id→`order`",
     "SELECT COUNT(*) FROM order_item oi LEFT JOIN `order` o ON o.id=oi.order_id WHERE o.id IS NULL",),
    ("referential:payment_record.order_id→`order`",
     "SELECT COUNT(*) FROM payment_record pr LEFT JOIN `order` o ON o.id=pr.order_id WHERE o.id IS NULL",),
    # 有效性（金额域）
    ("validity:order.total_amount>0",
     "SELECT COUNT(*) FROM `order` WHERE total_amount <= 0",),
    ("validity:payment_record.amount>0",
     "SELECT COUNT(*) FROM payment_record WHERE amount <= 0",),
    # 有效性（业务日期窗口 2020~2027）
    ("validity:order.created_at∈[2020,2027]",
     "SELECT COUNT(*) FROM `order` WHERE created_at < '2020-01-01' OR created_at > '2027-12-31'",),
    # 时序（已支付订单：支付时间不得早于下单）
    ("temporal:order.created_at≤payment.paid_at",
     "SELECT COUNT(*) FROM `order` o JOIN payment_record p ON p.order_id=o.id "
     "WHERE o.created_at > p.paid_at",),
    # 时序（班次周期）
    ("temporal:series_cohort.start_date≤end_date",
     "SELECT COUNT(*) FROM series_cohort WHERE start_date IS NOT NULL AND end_date IS NOT NULL AND start_date > end_date",),
    # 时序（审计时间）
    ("temporal:order.created_at≤updated_at",
     "SELECT COUNT(*) FROM `order` WHERE created_at IS NOT NULL AND updated_at IS NOT NULL AND created_at > updated_at",),
    # 一致性（应付守恒：抽样 500 单）
    ("consistency:order.payable_amount==SUM(order_item.payable_amount)",
     "SELECT COUNT(*) FROM (SELECT oi.order_id, o.payable_amount, "
     "SUM(oi.payable_amount) AS s, ABS(o.payable_amount - SUM(oi.payable_amount)) AS d "
     "FROM order_item oi JOIN `order` o ON o.id = oi.order_id "
     "WHERE oi.order_item_status NOT IN ('cancelled','refunded') "
     "GROUP BY oi.order_id, o.payable_amount HAVING d > 0.0001 LIMIT 500) t",),
]


async def run_quality() -> bool:
    print(f"{BOLD}=== quality：DB 数据质量不变量（{len(QUALITY_CHECKS)} 项断言）==={RESET}")
    conn = await _connect()
    fails = 0
    try:
        async with conn.cursor() as cur:
            for name, sql in QUALITY_CHECKS:
                try:
                    cnt = int(await _fetchone(cur, sql) or 0)
                except asyncmy.MySQLError as e:
                    print(f"  {RED}✗ {name}: SQL 执行失败 {e}{RESET}")
                    fails += 1
                    continue
                if cnt == 0:
                    print(f"  {GREEN}✓ {name}: 0 违规{PASS_EXPECTED}{RESET}")
                else:
                    print(f"  {RED}✗ {name}: {cnt} 违规（期望 0）FAIL{RESET}")
                    fails += 1
    finally:
        conn.close()
    return _summary("quality", fails)


PASS_EXPECTED = "（期望 0）"


def _summary(stage: str, fails: int) -> bool:
    if fails == 0:
        print(f"{GREEN}✓ {stage} 校验通过 — 0 差异{PASS_EXPECTED if stage == 'quality' else ''}{RESET}")
    else:
        print(f"{RED}✗ {stage} 校验不通过：{fails} 项 FAIL{RESET}")
    return fails == 0


# ============================================================
# CLI
# ============================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="verify.py",
        description="EduAgent DB 验收门禁（schema/counts/quality/all）",
    )
    parser.add_argument(
        "cmd", nargs="?", default="all",
        choices=["schema", "counts", "quality", "all"],
        help="要运行的子命令（默认 all）",
    )
    args = parser.parse_args()
    cmds = ["schema", "counts", "quality"] if args.cmd == "all" else [args.cmd]
    rc = 0
    for c in cmds:
        print(f"\n{'=' * 60}\n[all] 阶段: {c}\n{'=' * 60}")
        ok = asyncio.run(_ROUTER[c]())
        if not ok:
            rc = 1
    print(f"\n{'-' * 60}")
    if rc == 0:
        print(f"{GREEN}{BOLD}✓ 校验通过 — 可发布/合并（exit 0）{RESET}")
    else:
        print(f"{RED}{BOLD}✗ 校验不通过 — 请修复后重跑，禁合并（exit 1）{RESET}")
    sys.exit(rc)


_ROUTER = {
    "schema": run_schema,
    "counts": run_counts,
    "quality": run_quality,
}


if __name__ == "__main__":
    main()