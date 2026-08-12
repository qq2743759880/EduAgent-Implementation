# -*- coding: utf-8 -*-
"""P6 成就 & 游戏化 service：积分累计(INSERT..幂等)+ 等级 10 级 + 徽章解锁检测 + 排行榜(快照+实时兜底)。
event_scope 触发：POST / POST_LIKE / COMMENT_LIKE / QUIZ_CORRECT / QUIZ_FULL / VOCAB_MASTERED / HW_SUBMIT / EXAM_PASS / STUDY_MIN_TICK。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.database import execute_write, fetch_all, fetch_one

from .schemas import (
    AwardResponse, BadgeItem, BadgeListResp, LEVEL_TABLE, PointLogItem,
    PointsResp, RankingResp, RankingRow, calc_level,
)

# 业务点类型 → 积分值 / 中文备注
POINT_TYPE_LABEL = {
    "LEARN_MIN": ("学习时长", 1),
    "QUIZ_CORRECT": ("习题正确", 10),
    "QUIZ_FULL_CORRECT": ("习题一套全对", 30),
    "HW_SUBMIT": ("作业提交", 50),
    "EXAM_PASS": ("考试通过", 200),
    "POST_CREATE": ("社区发帖", 5),
    "COMMENT_CREATE": ("社区回帖", 2),
    "LIKE_GAIN": ("内容获赞", 2),
    "BADGE_BONUS": ("徽章奖励", 0),
    "VOCAB_MASTERED": ("单词MASTERED", 15),
}


# ========== 1. 积分写入（幂等 biz_key）==========
async def award_points(user_id: int, biz_key: str, point_type: str, delta: int,
                       note: str | None = None) -> int:
    """幂等写入一条积分流水；返回实际新增积分(重复调用返回 0)。"""
    if not biz_key or delta == 0:
        return 0
    # 1) 幂等检查
    exist = await fetch_one(
        "SELECT id FROM user_point_log WHERE user_id=%s AND biz_key=%s LIMIT 1",
        (user_id, biz_key),
    )
    if exist:
        return 0
    # 2) 获取当前余额（SUM delta 做 balance_after）
    bal_row = await fetch_one(
        "SELECT COALESCE(SUM(delta), 0) AS s FROM user_point_log WHERE user_id=%s",
        (user_id,),
    )
    cur_bal = int(bal_row["s"] or 0) if bal_row else 0
    new_bal = cur_bal + delta
    try:
        await execute_write(
            "INSERT INTO user_point_log (user_id, biz_key, point_type, delta, balance_after, note)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, biz_key, point_type, delta, new_bal, note),
        )
    except Exception:
        return 0
    return delta


async def get_total_points(user_id: int) -> int:
    r = await fetch_one(
        "SELECT COALESCE(SUM(delta),0) s FROM user_point_log WHERE user_id=%s", (user_id,),
    )
    return int(r["s"] or 0) if r else 0


# ========== 2. 个人积分面板 + 等级 ==========
async def my_points(user_id: int, page: int = 1, page_size: int = 20) -> PointsResp:
    total = await get_total_points(user_id)
    lv_no, lv_min, lv_title = calc_level(total)
    # 下一级门槛
    next_min = None
    for nxt_lv, nxt_thr, _ in LEVEL_TABLE:
        if nxt_lv > lv_no:
            next_min = nxt_thr
            break
    if next_min is None:
        next_min = LEVEL_TABLE[-1][1]  # 已满级，门槛不变
    level_progress_pct = 0.0 if next_min == lv_min else min(
        100.0, max(0.0, (total - lv_min) / max(1, (next_min - lv_min)) * 100)
    )

    total_logs_row = await fetch_one(
        "SELECT COUNT(*) c FROM user_point_log WHERE user_id=%s", (user_id,),
    )
    logs_total = int(total_logs_row["c"] or 0) if total_logs_row else 0
    offset = max(0, (page - 1) * page_size)
    logs = await fetch_all(
        "SELECT id, point_type, delta, balance_after, note, created_at "
        "FROM user_point_log WHERE user_id=%s ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (user_id, page_size, offset),
    )
    recent = [
        PointLogItem(
            log_id=int(r["id"]), point_type=r["point_type"], delta=int(r["delta"]),
            balance_after=int(r["balance_after"] or 0), note=r.get("note"),
            created_at=r.get("created_at") or datetime.utcnow(),
        )
        for r in logs
    ]
    return PointsResp(
        user_id=user_id, total_points=total,
        level_no=lv_no, level_title=lv_title,
        level_min=lv_min, next_level_min=next_min,
        level_progress_pct=round(level_progress_pct, 2),
        logs_total=logs_total, recent_logs=recent,
    )


# ========== 3. 徽章：全部徽章 & 个人解锁进度 ==========
async def list_badges_with_progress(user_id: int) -> BadgeListResp:
    badges = await fetch_all("SELECT * FROM gamification_badge WHERE yn=1 ORDER BY id")
    unlocked_rows = await fetch_all(
        "SELECT badge_code, unlocked_at FROM user_badge WHERE user_id=%s",
        (user_id,),
    )
    unlocked_map = {r["badge_code"]: r.get("unlocked_at") for r in unlocked_rows}

    # 拉一次统计量（每徽章一个 rule）
    metrics = await _collect_user_metrics(user_id)

    items: list[BadgeItem] = []
    next_milestone = "继续积累学习时长与答题正确率以解锁更多徽章！"
    for b in badges:
        rule = b.get("trigger_rule") or ""
        req = int(b.get("rule_value") or 0)
        cur = int(metrics.get(rule) or 0)
        pct = 0.0 if req <= 0 else min(100.0, cur / req * 100)
        code = b.get("badge_code") or ""
        unlocked = code in unlocked_map
        item = BadgeItem(
            badge_code=code,
            badge_name=b.get("badge_name") or "",
            badge_desc=b.get("badge_desc") or "",
            category=b.get("category") or "ACHIEVEMENT",
            icon_emoji=b.get("icon_emoji"),
            rarity=b.get("rarity") or "COMMON",
            trigger_rule=rule,
            rule_value=req,
            reward_points=int(b.get("reward_points") or 0),
            unlocked=unlocked,
            unlocked_at=unlocked_map.get(code) if unlocked else None,
            progress_current=cur,
            progress_required=req,
            progress_pct=round(pct, 2),
        )
        items.append(item)

    # next_milestone：第一个未解锁且 progress<100 的徽章
    for it in items:
        if not it.unlocked and it.progress_pct < 100:
            next_milestone = (
                f"下一目标：{it.icon_emoji or ''} {it.badge_name}"
                f"（进度 {it.progress_current}/{it.progress_required}，{it.progress_pct:.0f}%）"
            )
            break

    unlocked_count = sum(1 for i in items if i.unlocked)
    return BadgeListResp(total=len(items), unlocked_count=unlocked_count,
                         next_milestone=next_milestone, items=items)


async def _collect_user_metrics(user_id: int) -> dict[str, int]:
    """各徽章 trigger_rule → 累计进度。"""
    metrics: dict[str, int] = {}

    # 学习时长：learning_daily_summary.study_seconds / 60 + LEARN_MIN 积分的分钟数
    r = await fetch_one(
        "SELECT COALESCE(SUM(study_seconds),0) AS s FROM learning_daily_summary "
        "WHERE yn=1 AND user_id=%s", (user_id,),
    )
    study_sec_from_summary = int(r["s"] if r else 0)
    r2 = await fetch_one(
        "SELECT COALESCE(SUM(CASE WHEN point_type='LEARN_MIN' THEN delta ELSE 0 END),0) min1, "
        "       COALESCE(SUM(CASE WHEN point_type='LEARN_MIN_BONUS' THEN delta ELSE 0 END),0) min2 "
        "FROM user_point_log WHERE user_id=%s",
        (user_id,),
    )
    study_min_from_points = int(r2["min1"] or 0) + int(r2["min2"] or 0) if r2 else 0
    study_min = max(study_sec_from_summary // 60, study_min_from_points)
    metrics["STUDY_MIN_TOTAL"] = study_min

    # QUIZ_FULL_CORRECT：quiz_answer_session 答对次数（is_correct=1 代理满分）或 QUIZ_FULL_CORRECT 积分合计
    r = await fetch_one(
        "SELECT COUNT(*) c FROM quiz_answer_session QAS "
        "WHERE QAS.user_id=%s AND QAS.is_correct=1",
        (user_id,),
    )
    rq = await fetch_one(
        "SELECT COALESCE(SUM(delta),0) s FROM user_point_log "
        "WHERE user_id=%s AND point_type='QUIZ_FULL_CORRECT'",
        (user_id,),
    )
    metrics["QUIZ_FULL_CORRECT"] = max(int(r["c"] or 0) if r else 0,
                                       int(rq["s"] or 0) if rq else 0)

    # COURSE_FINISHED：完成系列课或 point_type=COURSE_FINISHED 积分合计
    rc = await fetch_one(
        "SELECT COALESCE(SUM(delta),0) s FROM user_point_log "
        "WHERE user_id=%s AND point_type='COURSE_FINISHED'",
        (user_id,),
    )
    metrics["COURSE_FINISHED"] = int(rc["s"] or 0) if rc else 0

    # VOCAB_MASTERED：MASTERED 的 user_vocab_card 数量或 VOCAB_MASTERED 积分合计
    r = await fetch_one(
        "SELECT COUNT(*) c FROM user_vocab_card WHERE user_id=%s AND mastery_status='MASTERED'",
        (user_id,),
    )
    rv = await fetch_one(
        "SELECT COALESCE(SUM(delta),0) s FROM user_point_log "
        "WHERE user_id=%s AND point_type='VOCAB_MASTERED'",
        (user_id,),
    )
    metrics["VOCAB_MASTERED"] = max(int(r["c"] or 0) if r else 0,
                                     int(rv["s"] or 0) if rv else 0)

    # POST_LIKES_TOTAL：个人所有帖子累计获赞或 LIKE_GAIN 积分合计
    r = await fetch_one(
        "SELECT COALESCE(SUM(like_count),0) s FROM community_post WHERE yn=1 AND author_id=%s",
        (user_id,),
    )
    rl = await fetch_one(
        "SELECT COALESCE(SUM(delta),0) s FROM user_point_log "
        "WHERE user_id=%s AND point_type='LIKE_GAIN'",
        (user_id,),
    )
    metrics["POST_LIKES_TOTAL"] = max(int(r["s"] or 0) if r else 0,
                                       int(rl["s"] or 0) if rl else 0)

    # COMMENT_LIKES_TOTAL：个人所有评论累计获赞或 COMMENT_LIKE_GAIN 积分合计
    r = await fetch_one(
        "SELECT COALESCE(SUM(like_count),0) s FROM community_comment WHERE yn=1 AND author_id=%s",
        (user_id,),
    )
    rcl = await fetch_one(
        "SELECT COALESCE(SUM(delta),0) s FROM user_point_log "
        "WHERE user_id=%s AND point_type='COMMENT_LIKE_GAIN'",
        (user_id,),
    )
    metrics["COMMENT_LIKES_TOTAL"] = max(int(r["s"] or 0) if r else 0,
                                          int(rcl["s"] or 0) if rcl else 0)

    return metrics


# ========== 4. 徽章解锁检测（事件/手动触发） ==========
async def check_and_unlock_badges(user_id: int, event_scope: str | None = None) -> list[str]:
    """检查所有徽章触发条件，满足则 INSERT IGNORE user_badge + 奖励积分(bonus)。
    返回本次新解锁 badge_code 列表。"""
    metrics = await _collect_user_metrics(user_id)
    badges = await fetch_all("SELECT * FROM gamification_badge WHERE yn=1")
    unlocked_codes: list[str] = []
    for b in badges:
        rule = b.get("trigger_rule") or ""
        req = int(b.get("rule_value") or 1)
        have = int(metrics.get(rule) or 0)
        if have < req:
            continue
        code = b.get("badge_code")
        bonus = int(b.get("reward_points") or 0)
        # 写入 user_badge（幂等），判断是否插入
        row = await fetch_one(
            "SELECT id FROM user_badge WHERE user_id=%s AND badge_code=%s LIMIT 1",
            (user_id, code),
        )
        newly = False
        if row is None:
            try:
                await execute_write(
                    "INSERT INTO user_badge (user_id, badge_code, unlocked_at, source_note)"
                    " VALUES (%s, %s, %s, %s)",
                    (user_id, code, datetime.utcnow(), f"达成 {rule} {have}/{req}"),
                )
                newly = True
            except Exception:
                newly = False
        if newly:
            unlocked_codes.append(code)
            if bonus > 0:
                await award_points(
                    user_id, biz_key=f"badge-bonus-{code}",
                    point_type="BADGE_BONUS", delta=bonus,
                    note=f"解锁徽章 {code} 奖励 {bonus} 分",
                )
    return unlocked_codes


# ========== 5. 排行榜（快照优先，无快照 → 实时 SUM）==========
SCOPE_ORDER = ["DAILY", "WEEKLY", "MONTHLY", "ALL_TIME"]
DIM_ORDER = ["POINTS", "STUDY_MIN", "BADGE_COUNT"]


async def ranking(user_id: int, scope: str = "DAILY", dimension: str = "POINTS",
                  top_n: int = 20) -> RankingResp:
    scope = scope.upper() if scope.upper() in SCOPE_ORDER else "DAILY"
    dimension = dimension.upper() if dimension.upper() in DIM_ORDER else "POINTS"
    today = date.today()
    snapshot_date = today

    # 优先查快照
    snap = await fetch_all(
        "SELECT S.rank_no, S.user_id, S.metric_value, UA.real_name AS name "
        "FROM ranking_snapshot S LEFT JOIN sys_user UA ON UA.id=S.user_id "
        "WHERE S.snapshot_date=%s AND S.rank_scope=%s AND S.rank_dim=%s AND S.yn=1 "
        "ORDER BY S.rank_no ASC LIMIT %s",
        (snapshot_date, scope, dimension, top_n),
    )
    source = "SNAPSHOT"
    if not snap:
        # 实时兜底（小项目）
        snap = await _live_ranking(scope=scope, dimension=dimension, top_n=top_n)
        source = "LIVE_CALC"

    # 徽章数（给每行附带）
    top_uid = [int(r["user_id"]) for r in snap]
    badge_counts: dict[int, int] = {}
    if top_uid:
        ph = ",".join(["%s"] * len(top_uid))
        bc = await fetch_all(
            f"SELECT user_id, COUNT(*) c FROM user_badge WHERE user_id IN ({ph}) GROUP BY user_id",
            tuple(top_uid),
        )
        for x in bc:
            badge_counts[int(x["user_id"])] = int(x["c"] or 0)
    user_levels: dict[int, tuple[int, int, str]] = {}
    for uid in top_uid:
        user_levels[uid] = calc_level(await get_total_points(uid))

    top_list: list[RankingRow] = []
    for r in snap:
        uid = int(r["user_id"])
        lv_no, _, _ = user_levels.get(uid, (1, 0, "萌新"))
        top_list.append(RankingRow(
            rank_no=int(r["rank_no"] or 0),
            user_id=uid,
            user_name=r.get("name") or f"用户{uid}",
            metric_value=int(r["metric_value"] or 0),
            level_no=lv_no,
            is_myself=(uid == user_id),
            badge_count=badge_counts.get(uid, 0),
        ))

    # 我的排名：查快照 or 实时排名
    my_row: RankingRow | None = None
    if source == "SNAPSHOT":
        mine = await fetch_one(
            "SELECT rank_no, metric_value FROM ranking_snapshot "
            "WHERE snapshot_date=%s AND rank_scope=%s AND rank_dim=%s AND user_id=%s AND yn=1 LIMIT 1",
            (snapshot_date, scope, dimension, user_id),
        )
    else:
        mine = None  # 实时模式下 top 里已包含（若在榜）

    # 在 top_list 里已找到我就直接用，否则单独算 metric_value 然后找排名插值
    if any(r.user_id == user_id for r in top_list):
        my_row = next(r for r in top_list if r.user_id == user_id)
    else:
        my_val = await _user_metric_value(user_id, scope, dimension)
        # 插值：找 snap 里比我的大的数量 + 1
        better = 0
        for r in snap:
            if int(r.get("metric_value") or 0) > my_val:
                better += 1
        my_rank_no = better + 1
        my_lv_no, _, _ = calc_level(await get_total_points(user_id))
        my_row = RankingRow(
            rank_no=my_rank_no, user_id=user_id,
            user_name=f"用户{user_id}", metric_value=my_val,
            level_no=my_lv_no, is_myself=True,
            badge_count=badge_counts.get(user_id, 0) if user_id in badge_counts else int(await _badge_count(user_id)),
        )

    return RankingResp(scope=scope, dimension=dimension, snapshot_date=snapshot_date,
                       top=top_list, my_rank=my_row, source=source)


async def _user_metric_value(user_id: int, scope: str, dimension: str) -> int:
    start = _scope_start(scope)
    if dimension == "POINTS":
        r = await fetch_one(
            "SELECT COALESCE(SUM(delta),0) s FROM user_point_log "
            "WHERE user_id=%s AND created_at >= %s",
            (user_id, start),
        )
        return int(r["s"] or 0) if r else 0
    if dimension == "STUDY_MIN":
        r = await fetch_one(
            "SELECT COALESCE(SUM(study_seconds),0) s FROM learning_daily_summary "
            "WHERE yn=1 AND user_id=%s AND stat_date >= %s",
            (user_id, start.date()),
        )
        return int((r["s"] if r else 0) // 60)
    # BADGE_COUNT：不限 scope
    return await _badge_count(user_id)


async def _badge_count(user_id: int) -> int:
    r = await fetch_one("SELECT COUNT(*) c FROM user_badge WHERE user_id=%s", (user_id,))
    return int(r["c"] or 0) if r else 0


def _scope_start(scope: str) -> datetime:
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if scope == "DAILY":
        return today
    if scope == "WEEKLY":
        # 本周周一
        return today - timedelta(days=today.weekday())
    if scope == "MONTHLY":
        return today.replace(day=1)
    # ALL_TIME
    return datetime(2000, 1, 1)


async def _live_ranking(*, scope: str, dimension: str, top_n: int) -> list[dict]:
    start = _scope_start(scope)
    if dimension == "POINTS":
        rows = await fetch_all(
            "SELECT user_id, COALESCE(SUM(delta),0) AS metric_value FROM user_point_log "
            "WHERE created_at >= %s GROUP BY user_id ORDER BY metric_value DESC LIMIT %s",
            (start, top_n),
        )
    elif dimension == "STUDY_MIN":
        rows = await fetch_all(
            "SELECT user_id, COALESCE(FLOOR(SUM(study_seconds)/60),0) AS metric_value "
            "FROM learning_daily_summary WHERE yn=1 AND stat_date >= %s GROUP BY user_id "
            "ORDER BY metric_value DESC LIMIT %s",
            (start.date(), top_n),
        )
    else:  # BADGE_COUNT
        rows = await fetch_all(
            "SELECT user_id, COUNT(*) AS metric_value FROM user_badge "
            "WHERE unlocked_at >= %s GROUP BY user_id ORDER BY metric_value DESC LIMIT %s",
            (start, top_n),
        )
    out: list[dict] = []
    for i, r in enumerate(rows, start=1):
        out.append({"rank_no": i, "user_id": int(r["user_id"] or 0),
                    "metric_value": int(r["metric_value"] or 0)})
    return out


# ========== 手动加积分（打靶用，避免真实 VIDEO_WATCH 数据）==========
async def admin_award(user_id: int, point_type: str, delta: int, biz_key: str,
                      note: str | None = None) -> AwardResponse:
    added = await award_points(user_id, biz_key=biz_key, point_type=point_type,
                               delta=delta, note=note)
    unlocked = await check_and_unlock_badges(user_id, event_scope="ADMIN")
    total = await get_total_points(user_id)
    lv_no, _, lv_title = calc_level(total)
    return AwardResponse(
        points_added=added, new_balance=total, level_no=lv_no,
        level_title=lv_title, newly_unlocked=unlocked,
    )
