#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EduAgent CI 门禁（task98）—— DB 验收体系：schema / counts / quality / tests / all。

复用：
  - `edu-agent/.env` 的 MYSQL_*（settings 配置源）为 DSN 事实源（不新造连接层/不引新依赖）；
  - 既有 `asyncmy`（项目已装 MySQL 驱动）直接连接；
  - 既有 `test-reports/interface_acceptance_final.py` / scripts/verify_task07_*.py 的校验口径
    （引用完整性 / 有效性 / 时序 / 一致性）收敛为轻量 DB 断言，可独立于后端运行；
  - task07「6-机构多租户口径」（scripts/verify_task07_counts.py，6 机构切分）落为 counts 机构维段。

子命令：
  schema  对比 DB 当前表结构 vs .schema-acceptance.yaml（核心表+关键列存在性），缺失→FAIL
  counts  抽查核心表行数 vs 基线（容差判定）＋机构维段（task07 6-机构切分+归属无孤儿）
  quality DB 数据质量不变量（孤儿/金额/枚举/时序/一致性），任一违规>0→FAIL
  tests   集成测试结果归一门禁（task37 联动）：全量失败基线白名单比对，白名单外新增失败→FAIL
  all     依次跑 schema/counts/quality，任一 FAIL → exit 1（tests 独立，不进 all，避免 30min 全量拖 CI）

退出码：0=通过，1=失败。
用法：
  edu-agent/.venv/Scripts/python.exe -X utf8 scripts/verify.py all
  edu-agent/.venv/Scripts/python.exe -X utf8 scripts/verify.py counts
  edu-agent/.venv/Scripts/python.exe -X utf8 scripts/verify.py tests [--no-run] [--target "pytest args..."]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
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
            # --- task07「6-机构多租户口径」机构维段 ---
            inst_tables = BASELINE.get("counts", {}).get("institution", {}).get("tenant_tables", [])
            if inst_tables:
                print(f"{BOLD}--- counts 机构维段（task07 6-机构切分 + 归属无孤儿，{len(inst_tables)} 表）---{RESET}")
                org_n = int(await _fetchone(cur, "SELECT COUNT(*) FROM org_institution") or 0)
                if org_n <= 0:
                    print(f"  {RED}✗ org_institution 为空，无法做 6-机构口径{RESET}")
                    fails += 1
                for t in inst_tables:
                    distinct = int(await _fetchone(
                        cur, f"SELECT COUNT(DISTINCT institution_id) FROM `{t}`") or 0)
                    if distinct < org_n:
                        print(f"  {RED}✗ {t}: 机构切分不完整 distinct={distinct} < org={org_n} FAIL{RESET}")
                        fails += 1
                        continue
                    orphan = int(await _fetchone(
                        cur, f"SELECT COUNT(*) FROM `{t}` "
                             "WHERE institution_id IS NULL OR "
                             "institution_id NOT IN (SELECT id FROM org_institution)") or 0)
                    if orphan:
                        print(f"  {RED}✗ {t}: {orphan} 行机构归属孤儿 FAIL{RESET}")
                        fails += 1
                    else:
                        print(f"  {GREEN}✓ {t}: 覆盖 {distinct} 机构，0 归属孤儿 PASS{RESET}")
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


# ============================================================
# tests：集成测试结果归一门禁（task37 联动）
# ============================================================
# expected_test_failures 基线（.schema-acceptance.yaml）＝全量 pytest 已知环境/数据/性能/独立验收失败白名单。
# 门禁逻辑：命中白名单的失败=符合预期；白名单外新增失败 → FAIL。
#   --no-run   只做 collect-only 漂移门（快）：断言白名单 nodeid 仍可收集；CI 用，避免 30min 全量拖超时。
#   --target  透传 pytest 目标参数（默认全量 tests/），全量验收 by orchestrator 一次性跑。
TESTS_TARGET = ["tests/", "-q", "--tb=no", "-p", "no:cacheprovider"]
TESTS_NO_RUN = False


def _parse_nodeids(text: str) -> set:
    """从 pytest --collect-only / FAILED 输出提取 nodeid（`路径::类::函数`）。"""
    return set(re.findall(r"\S+::\S+", text, re.M))


def run_tests() -> bool:
    wl = BASELINE.get("expected_test_failures", [])
    wl_ids = {w.get("nodeid") for w in wl if w.get("nodeid")}
    if not wl_ids:
        print(f"{RED}✗ expected_test_failures 基线为空{RESET}")
        return False
    print(f"{BOLD}=== tests：集成测试失败白名单门禁（expected 基线 {len(wl_ids)} 项，task37 联动）==={RESET}")

    # 1) collect-only 漂移门：白名单 nodeid 是否仍可收集
    #    注：恰好一个 -q 才会输出 `::` nodeid 列表；无 -q=verbose 树、重复 -q=每文件计数，均不可解析。
    base = [a for a in TESTS_TARGET if a != "-q"]
    coll = subprocess.run(
        [sys.executable, "-m", "pytest", *base, "-q", "--collect-only"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    collected = _parse_nodeids(coll.stdout)
    missing = sorted(wl_ids - collected)
    if missing:
        print(f"  {YELLOW}◌ 白名单 {len(missing)} 项已不可收集（基线过期或被修复，建议核对收缩）:{RESET}")
        for nid in missing:
            print(f"    {YELLOW}◌ {nid}{RESET}")
    else:
        print(f"  ✓ 白名单 {len(wl_ids)} 项 nodeid 均可收集（基线无漂移）")

    if TESTS_NO_RUN:
        print(f"{GREEN}✓ tests 收集漂移门通过（--no-run，未实跑；白名单剩余为环境类，CI 不实跑避免超时）{RESET}")
        return True  # 收集漂移不判 FAIL（缺失=改善信号），CI 快速门仅保证基线不漂

    # 2) 实跑 pytest 并比对失败清单
    print(f"{BOLD}--- 实跑 pytest（{ ' '.join(TESTS_TARGET) }）---{RESET}")
    run = subprocess.run(
        [sys.executable, "-m", "pytest", *TESTS_TARGET],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    output = run.stdout + run.stderr
    failed = {line.split()[1] for line in output.splitlines() if line.startswith("FAILED ")}
    if not failed:
        print(f"  {GREEN}✓ 本次 0 失败 —— 白名单 {len(wl_ids)} 项全部未复现（基线可收缩）{RESET}")
        return True

    wl_hits = failed & wl_ids
    new_fail = failed - wl_ids
    reason = {w.get("nodeid"): w.get("reason", "") for w in wl}
    for nid in sorted(wl_hits):
        print(f"  {GREEN}✔ 白名单命中（符合预期）: {nid}{RESET}")
        print(f"      原因: {reason.get(nid)}")
    for nid in sorted(wl_ids - failed):
        print(f"  {YELLOW}◌ 白名单项本次未复现（改善，基线可收缩）: {nid}{RESET}")
    for nid in sorted(new_fail):
        print(f"  {RED}✗ 白名单外新增失败: {nid}{RESET}")
    if new_fail:
        print(f"{RED}✗ tests 校验不通过：{len(new_fail)} 项新增白名单外失败{RESET}")
        return False
    print(f"{GREEN}✓ tests 校验通过：{len(wl_hits)} 项失败全部命中白名单预期，0 新增{RESET}")
    return True


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
        description="EduAgent DB 验收门禁（schema/counts/quality/tests/all）",
    )
    parser.add_argument(
        "cmd", nargs="?", default="all",
        choices=["schema", "counts", "quality", "tests", "all"],
        help="要运行的子命令（默认 all）",
    )
    parser.add_argument(
        "--no-run", action="store_true",
        help="tests 子命令仅做 collect-only 收集漂移门（快），不实跑 pytest",
    )
    parser.add_argument(
        "--target", nargs="+", default=None, metavar="ARGS",
        help="tests 子命令透传给 pytest 的目标参数（默认 'tests/'）",
    )
    args = parser.parse_args()
    global TESTS_TARGET, TESTS_NO_RUN
    TESTS_NO_RUN = args.no_run
    if args.target:
        TESTS_TARGET = args.target
    if args.cmd == "tests":
        cmds = ["tests"]
    else:
        cmds = ["schema", "counts", "quality"] if args.cmd == "all" else [args.cmd]
    rc = 0
    for c in cmds:
        print(f"\n{'=' * 60}\n[all] 阶段: {c}\n{'=' * 60}")
        if c == "tests":  # run_tests 为同步子进程门禁，不走 asyncio.run
            ok = run_tests()
        else:
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
    "tests": run_tests,
}


if __name__ == "__main__":
    main()