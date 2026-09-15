# -*- coding: utf-8 -*-
"""F-2 一次性对账脚本：以 MySQL ``user_point_log`` 账本为真相源，把积分排行榜
POINTS ZSET（g-rank:{scope}:POINTS:{period}）对齐到账本口径。

背景（两源分叉根因）：
  - 面板总分走 MySQL SUM(delta)；排行榜走 Redis ZSET（award_points 写 MySQL 后 ZINCRBY）。
  - 历史数据（SQL 导入/种子，如 LEARN_MIN/QUIZ_CORRECT 等）绕过了 award_points 入口；
    Redis 故障/清空窗口内 fail-open 提交的事件也只落 MySQL——这些增量 ZSET 永远缺失。
  - 读取侧只在 key 完全为空时 SQL 回填，key 一旦有部分数据（如停在 35）永不重算。

安全边界（红线）：
  - 默认 DRY-RUN，只打印差异计划；必须显式 --apply 才写 Redis。
  - 只写 Redis ZSET（ZADD 绝对对齐 / ZREM 清幽灵成员 / EXPIRE 续期），**绝不写 MySQL**，
    不清零任何真实积分；账本净值为 0/负数也如实反映。
  - 只处理「当前周期」4 个 key（DAILY/WEEKLY/MONTHLY/ALL_TIME）；历史周期 key 仅列出不动
    （周期滚动后有 TTL 自然过期）。STUDY_MIN/BADGE_COUNT 维度不在本单范围。

用法（在 edu-agent/ 下）：
  .venv\\Scripts\\python.exe scripts\\reconcile_points_zset.py            # dry-run 预览
  .venv\\Scripts\\python.exe scripts\\reconcile_points_zset.py --apply    # 执行对齐
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

from app.database import close_redis, fetch_all, get_redis, init_mysql, init_redis
from app.gamification.service import (
    SCOPE_ORDER,
    _ZSCOPE_TTL,
    _rank_zset_key,
    _scope_start,
)


async def _truth_by_scope(scope: str, now: datetime) -> dict[int, int]:
    """账本真相：某 scope 起点之后每个用户的积分净值（与 _live_ranking 同口径）。"""
    start = _scope_start(scope, now=now)
    rows = await fetch_all(
        "SELECT user_id, COALESCE(SUM(delta),0) AS s FROM user_point_log "
        "WHERE created_at >= %s GROUP BY user_id",
        (start,),
    )
    return {int(r["user_id"] or 0): int(r["s"] or 0) for r in rows}


async def reconcile(*, apply: bool) -> int:
    now = datetime.utcnow()
    r = get_redis()
    touched = 0
    current_keys: set[str] = set()

    for scope in SCOPE_ORDER:
        key = _rank_zset_key(scope, "POINTS", now)
        current_keys.add(key)
        truth = await _truth_by_scope(scope, now)
        old_rows = await r.zrange(key, 0, -1, withscores=True)
        old = {int(member): int(score) for member, score in old_rows}

        # ZADD 绝对对齐（含新增缺失用户、修正漂移用户；净值 0 也如实写为 0）
        zadd_map = {
            str(uid): score for uid, score in truth.items() if old.get(uid) != score
        }
        # 幽灵成员：ZSET 有、账本无该用户（周期内无任何流水）→ 移除
        zrem_members = [str(uid) for uid in old if uid not in truth]

        print(f"\n[{scope}] key={key} ttl={await r.ttl(key)}")
        print(f"  账本用户数={len(truth)} ZSET 成员数={len(old)} "
              f"待 ZADD/修正={len(zadd_map)} 待 ZREM={len(zrem_members)}")
        for member, score in sorted(zadd_map.items(), key=lambda kv: kv[1], reverse=True)[:20]:
            print(f"    ZADD uid={member}: {old.get(int(member), '<缺失>')} -> {score}")
        for member in zrem_members[:20]:
            print(f"    ZREM uid={member}: 旧值={old[int(member)]}（账本无周期内流水）")

        if apply and (zadd_map or zrem_members):
            if zadd_map:
                await r.zadd(key, zadd_map)
            if zrem_members:
                await r.zrem(key, *zrem_members)
            await r.expire(key, _ZSCOPE_TTL[scope])
            touched += len(zadd_map) + len(zrem_members)

    # 历史周期 POINTS key：只盘点，不改动（等 TTL 自然过期，避免误伤跨周期榜单语义）
    print("\n[历史周期 POINTS key（跳过，TTL 自然过期）]")
    async for k in r.scan_iter("g-rank:*:POINTS:*"):
        if k not in current_keys:
            print(f"  SKIP {k} ttl={await r.ttl(k)}")

    mode = "APPLY（已写 Redis）" if apply else "DRY-RUN（未写入；加 --apply 执行）"
    print(f"\n完成：{mode}，对齐成员变更 {touched} 个；MySQL 账本零写入。")
    return touched


async def amain(apply: bool) -> None:
    await init_mysql()
    await init_redis()
    try:
        await reconcile(apply=apply)
    finally:
        await close_redis()


def main() -> None:
    parser = argparse.ArgumentParser(description="积分排行榜 ZSET 与 MySQL 账本一次性对账（F-2）")
    parser.add_argument("--apply", action="store_true", help="真正写入 Redis（默认仅 dry-run）")
    args = parser.parse_args()
    try:
        asyncio.run(amain(apply=args.apply))
    except Exception as e:  # noqa: BLE001
        logger.exception(f"对账失败：{type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
