#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task99: 批量补生成 sys_user_auth（100K 用户登录可用）

背景（实证）：sys_user 100015 条，sys_user_auth 仅 212 条 → 99803 个生成用户无认证记录、无法登录。
性质：**数据补漏**——不改 edu-data 生成脚本（避免重灌破坏冻结基线），只对现有冻结数据补 auth。

安全红线：密码**只以 bcrypt 哈希落库，禁止明文**；哈希逻辑与 `scripts/restore_admin.py`
及 `edu-agent/app/auth/service.py`(PASSWORD_HASH_ROUNDS=12) 一致。

性能取舍（本机实测）：bcrypt rounds=12 单次哈希 **410ms**，逐用户哈希 99803 条需 **11.4 小时** → 不可行。
  由于补生成的账号共用同一默认密码，脚本默认**只算一次哈希**并复用到所有行：
  - 仍是标准 bcrypt 哈希（无明文），`bcrypt.checkpw` 验证通过；
  - 共用同一明文口令时，per-user salt 并不增加任何安全性（攻破一个即等于攻破全部）；
  - 需要 per-user 唯一盐时用 `--per-user-salt`（仅建议小批量，如 --limit 200）。

用法（须用 edu-agent/.venv，含 bcrypt + pymysql）：
  python scripts/backfill_auth.py --dry-run                 # 只看计划，不写库
  python scripts/backfill_auth.py --limit 1000              # 先小批量试跑
  python scripts/backfill_auth.py                           # 全量补齐（默认，99803 条）
  python scripts/backfill_auth.py --role teacher --limit 100
  python scripts/backfill_auth.py --per-user-salt --limit 200

幂等：`sys_user_auth.uk_sys_user_auth_user(user_id)` 唯一键 + `INSERT IGNORE`
  → 重复执行不翻倍、不报唯一键冲突。
"""
from __future__ import annotations

import argparse
import os
import random
import time

import bcrypt
import pymysql

DEFAULT_PASSWORD = "Test@123456"
VALID_ROLES = ("student", "teacher", "manager", "admin")
DEFAULT_BATCH = 5000


def get_conn():
    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", "123456"),
        database=os.environ.get("MYSQL_DB", "edu"),
        charset="utf8mb4",
        autocommit=True,
    )


def scalar(cur, sql):
    cur.execute(sql)
    row = cur.fetchone()
    return row[0] if row else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="task99: 批量补生成 sys_user_auth")
    ap.add_argument("--limit", type=int, default=None,
                    help="最多补生成多少条；默认不限（全量补齐缺失用户）")
    ap.add_argument("--role", default="student", choices=VALID_ROLES,
                    help="新生成记录的 role_code（默认 student）。sys_user 表无角色列，"
                         "故 --role 决定**写入的 role_code**，而非按角色筛选用户")
    ap.add_argument("--password", default=DEFAULT_PASSWORD,
                    help=f"统一默认密码（默认 {DEFAULT_PASSWORD}）；只以 bcrypt 哈希落库")
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH, help="每批写入条数（默认 5000）")
    ap.add_argument("--rounds", type=int, default=12, help="bcrypt 轮次（默认 12，对齐 PASSWORD_HASH_ROUNDS）")
    ap.add_argument("--sample", type=int, default=10, help="抽样验证条数（默认 10）")
    ap.add_argument("--per-user-salt", action="store_true",
                    help="每条记录独立盐（rounds=12 约 410ms/条，全量需 11.4h，仅建议小批量）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写库")
    args = ap.parse_args()

    t_start = time.perf_counter()
    print("=" * 62)
    print("task99: 批量补生成 sys_user_auth")
    print("=" * 62)

    conn = get_conn()
    cur = conn.cursor()

    total_user = scalar(cur, "SELECT COUNT(*) FROM sys_user")
    total_auth_before = scalar(cur, "SELECT COUNT(*) FROM sys_user_auth")
    print(f"\n[现状] sys_user={total_user}  sys_user_auth={total_auth_before}")

    # 待补：sys_user 有、sys_user_auth 无（仅活跃用户）
    sql_missing = """
        SELECT u.id
        FROM sys_user u
        LEFT JOIN sys_user_auth a ON a.user_id = u.id
        WHERE a.user_id IS NULL AND u.yn = 1
        ORDER BY u.id
    """
    if args.limit:
        sql_missing += f" LIMIT {int(args.limit)}"
    cur.execute(sql_missing)
    missing_ids = [r[0] for r in cur.fetchall()]

    print(f"[计划] 待补生成 {len(missing_ids)} 条  角色={args.role}  批次={args.batch_size}"
          f"  独立盐={args.per_user_salt}  轮次={args.rounds}")
    print(f"[安全] 默认密码只以 bcrypt 哈希落库，**不存明文**")

    if not missing_ids:
        print("\n无需补生成（无缺失 auth 的用户）。")
        return 0

    if args.dry_run:
        print(f"\n[dry-run] 未写库。样例 user_id: {missing_ids[:5]}")
        return 0

    # ---- 生成哈希 ----
    t_hash = time.perf_counter()
    if args.per_user_salt:
        hashes = [bcrypt.hashpw(args.password.encode("utf-8"), bcrypt.gensalt(rounds=args.rounds)).decode("utf-8")
                  for _ in missing_ids]
    else:
        # 共用同一明文口令 → 只算一次哈希，复用到所有行（见文件头性能取舍说明）
        one = bcrypt.hashpw(args.password.encode("utf-8"), bcrypt.gensalt(rounds=args.rounds)).decode("utf-8")
        hashes = [one] * len(missing_ids)
    hash_secs = time.perf_counter() - t_hash
    print(f"\n[哈希] 生成 {len(hashes)} 条哈希耗时 {hash_secs:.2f}s（bcrypt rounds={args.rounds}）")

    # ---- 批量写入（INSERT IGNORE 幂等）----
    insert_sql = """
        INSERT IGNORE INTO sys_user_auth
            (user_id, password_hash, role_code, yn, created_at, updated_at)
        VALUES (%s, %s, %s, 1, NOW(), NOW())
    """
    t_ins = time.perf_counter()
    written = 0
    for i in range(0, len(missing_ids), args.batch_size):
        chunk_ids = missing_ids[i:i + args.batch_size]
        chunk_hash = hashes[i:i + args.batch_size]
        cur.executemany(insert_sql, [(uid, h, args.role) for uid, h in zip(chunk_ids, chunk_hash)])
        written += len(chunk_ids)
        print(f"  写入 {written}/{len(missing_ids)}")
    conn.commit()
    insert_secs = time.perf_counter() - t_ins
    print(f"[写入] 完成，耗时 {insert_secs:.2f}s")

    total_auth_after = scalar(cur, "SELECT COUNT(*) FROM sys_user_auth")
    print(f"\n[结果] sys_user_auth {total_auth_before} → {total_auth_after} (+{total_auth_after - total_auth_before})")

    # ---- 抽样验证：bcrypt 校验 + 角色 ----
    n_sample = min(args.sample, len(missing_ids))
    sample_ids = random.sample(missing_ids, n_sample)
    print(f"\n[抽样验证] 随机抽取 {n_sample} 条，用 bcrypt.checkpw 校验密码与角色")
    fmt = ",".join(["%s"] * len(sample_ids))
    cur.execute(
        f"SELECT a.user_id, u.account, a.password_hash, a.role_code "
        f"FROM sys_user_auth a JOIN sys_user u ON u.id = a.user_id WHERE a.user_id IN ({fmt})",
        sample_ids,
    )
    rows = cur.fetchall()
    ok_pwd = ok_role = 0
    for uid, account, pwd_hash, role_code in rows:
        pwd_ok = bcrypt.checkpw(args.password.encode("utf-8"), pwd_hash.encode("utf-8"))
        role_ok = (role_code == args.role)
        ok_pwd += int(pwd_ok)
        ok_role += int(role_ok)
        print(f"  {'PASS' if (pwd_ok and role_ok) else 'FAIL'}  id={uid} account={account} "
              f"pwd={'OK' if pwd_ok else 'BAD'} role={role_code}{'' if role_ok else f'(期望 {args.role})'}")
    print(f"  小结: 密码校验 {ok_pwd}/{len(rows)} 通过，角色 {ok_role}/{len(rows)} 为 {args.role}")

    # ---- 覆盖率 ----
    missing_after = scalar(cur, "SELECT COUNT(*) FROM sys_user u LEFT JOIN sys_user_auth a ON a.user_id=u.id WHERE a.user_id IS NULL")
    print(f"\n[覆盖率] 仍缺 auth 的用户: {missing_after} / {total_user}")

    print(f"\n总耗时 {time.perf_counter() - t_start:.2f}s")
    # 真实账号区间（按本批处理到的首尾 id 回查，避免用总行数臆造 account）
    edge_ids = [missing_ids[0]] if len(missing_ids) == 1 else [missing_ids[0], missing_ids[-1]]
    cur.execute(
        "SELECT id, account FROM sys_user WHERE id IN ({})".format(",".join(["%s"] * len(edge_ids))),
        edge_ids,
    )
    acct_map = {r[0]: r[1] for r in cur.fetchall()}
    acct_first = acct_map.get(missing_ids[0], "?")
    acct_last = acct_map.get(missing_ids[-1], acct_first)
    print("=" * 62)
    print("账号可用于 E2E / 压测：")
    print(f"  用户名（account）: {acct_first} ~ {acct_last}（本批补生成区间，取 sys_user.account）")
    print(f"  统一默认密码    : {args.password}")
    print("  （密码仅以 bcrypt 哈希存储，登录走 app.auth.service.verify_password）")
    print("=" * 62)

    conn.close()
    return 0 if (ok_pwd == len(rows) and ok_role == len(rows)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
