# -*- coding: utf-8 -*-
"""P5 单词闯关 engine + service：分级词库 + SM-2 + daily 计划 + recall + progress 统计。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.common.exceptions import AppException as BizError
from app.database import execute_write, fetch_all, fetch_one
from app.interactive.vocab.schemas import (
    DailyPlan, ProgressStat, RecallIn, RecallOut, VocabCard,
)

QUIZ_TYPES = ["PICK", "LISTEN", "SPELL", "CLOZE"]


# ============= 0. 辅助：根据 user_profile 选主推 Lx 等级 =============

async def _guess_user_target_level(user_id: int) -> str:
    try:
        from app.recommender.engine import _load_profile
        profile = await _load_profile(user_id)
        for a in profile.get("level_assessments") or []:
            if isinstance(a, dict) and (a.get("subject_code") or "").lower() == "english":
                if a.get("level_code"):
                    return a["level_code"]
        grade = (profile.get("grade_code") or "").lower()
        if grade.startswith("p") or "小学" in grade:
            return "L1"
        if grade.startswith("j") or "初中" in grade:
            return "L2"
        if grade.startswith("s") or "高中" in grade:
            return "L3"
    except Exception:
        pass
    return "L2"


# ============= 1. SM-2 核心算法（简化版 Anki）=============

def sm2_update(ease_factor: float, interval_days: int, repetition: int, quality: int
               ) -> tuple[float, int, int, str, timedelta]:
    """
    返回 (new_ease, new_interval, new_repetition, new_status, due_delta_timedelta)。

    SM-2 规则参考（简化）：
      - quality < 3：repetition=0，interval_days=1（第2天重看），ease 不低于 1.3
        (ef = ef - 0.2 - 0.1*(2-q) when q<3 → 更严格下调）
      - quality = 3：repetition 递增；if rep==1 then 1；rep==2 then 6；else round(I*EF)
                    ef = ef - 0.15
      - quality = 4：同上默认公式；ef 不变
      - quality = 5：ef = ef + 0.15；interval 同上
      - 最低 EF = 1.3；repetition 稳定超过 8 次 且 ef > 2.3 就 MASTERED
    """
    q = int(quality)
    ef = max(1.300, float(ease_factor))
    rep = int(repetition)
    interval = int(interval_days)

    if q < 3:
        # 遗忘：回到第一天重新来过，EF 下调（最多扣到 1.3）
        ef = max(1.3, ef - 0.2 - 0.1 * (2 - q))
        rep = 0
        interval = 1
        status = "LEARNING"
        delta = timedelta(days=1)
    else:
        rep += 1
        if q == 3:
            ef = max(1.3, ef - 0.15)
        elif q == 5:
            ef = ef + 0.15
        if rep == 1:
            interval = 1
        elif rep == 2:
            interval = 6
        else:
            interval = max(1, round(float(interval) * ef))
        if rep >= 8 and ef >= 2.30 and interval >= 21 and q >= 4:
            status = "MASTERED"
            delta = timedelta(days=max(interval, 180))
        elif rep >= 3:
            status = "REVIEW"
            delta = timedelta(days=interval)
        else:
            status = "LEARNING"
            delta = timedelta(days=interval)
    return round(ef, 3), int(interval), int(rep), status, delta


# ============= 2. 保证词卡存在（新词 upsert 到 user_vocab_card 并返回 ids）=============

async def _ensure_cards_for_level(user_id: int, level_code: str, limit: int) -> list[dict]:
    """选 level_code 下该用户还没建立的 Lx 词汇，INSERT user_vocab_card，返回 {id,entry,card_info}。"""
    # 找出 limit 条未建卡词
    rows = await fetch_all(
        "SELECT V.id, V.word, V.level_code, V.phonetic_us, V.phonetic_uk, V.meaning_cn,"
        " V.example_en, V.example_cn, V.topic_tag, V.image_hint, V.audio_us, V.subject_code "
        "FROM vocab_entry V "
        "WHERE V.yn=1 AND V.level_code=%s "
        " AND V.id NOT IN (SELECT vocab_entry_id FROM user_vocab_card WHERE user_id=%s) "
        "ORDER BY V.id LIMIT %s",
        (level_code, user_id, int(limit)),
    )
    inserted_ids: list[int] = []
    for r in rows:
        ins = await execute_write(
            "INSERT IGNORE INTO user_vocab_card "
            "(user_id, vocab_entry_id, ease_factor, interval_days, repetition, due_at, created_at, updated_at) "
            "VALUES (%s,%s,2.5,0,0,NOW(),NOW(),NOW())",
            (user_id, int(r["id"])),
        )
        if ins is None:
            row = await fetch_one(
                "SELECT id FROM user_vocab_card WHERE user_id=%s AND vocab_entry_id=%s LIMIT 1",
                (user_id, int(r["id"])),
            )
            if row:
                inserted_ids.append(int(row["id"]))
        else:
            inserted_ids.append(int(ins))
    # 再合并已有 due 到期卡
    return rows


# ============= 3. Daily plan =============

async def daily_plan(user_id: int, *, level_code: str | None = None,
                     new_quota: int = 20, review_quota: int = 60) -> DailyPlan:
    target_level = level_code or await _guess_user_target_level(user_id)

    # 复习卡：due_at <= NOW() AND mastery in NEW/LEARNING/REVIEW
    due_rows = await fetch_all(
        "SELECT C.id AS card_id, C.mastery_status, C.ease_factor, C.interval_days, C.repetition, C.due_at, "
        " V.id AS entry_id, V.word, V.level_code, V.phonetic_us, V.meaning_cn, V.example_en, V.example_cn,"
        " V.topic_tag, V.image_hint, V.audio_us, V.subject_code"
        " FROM user_vocab_card C JOIN vocab_entry V ON V.id = C.vocab_entry_id "
        " WHERE C.user_id=%s AND C.due_at <= NOW() AND C.mastery_status IN ('NEW','LEARNING','REVIEW') "
        " AND V.yn=1 "
        " ORDER BY (CASE C.mastery_status WHEN 'LEARNING' THEN 1 WHEN 'REVIEW' THEN 2 ELSE 3 END), C.due_at ASC "
        " LIMIT %s",
        (user_id, int(review_quota)),
    )

    # 如果该 level 还没卡，先塞一些新卡
    if not due_rows:
        await _ensure_cards_for_level(user_id, target_level, limit=max(10, int(new_quota * 1.5)))
        due_rows = await fetch_all(
            "SELECT C.id AS card_id, C.mastery_status, C.ease_factor, C.interval_days, C.repetition, C.due_at, "
            " V.id AS entry_id, V.word, V.level_code, V.phonetic_us, V.meaning_cn, V.example_en, V.example_cn,"
            " V.topic_tag, V.image_hint, V.audio_us, V.subject_code"
            " FROM user_vocab_card C JOIN vocab_entry V ON V.id = C.vocab_entry_id "
            " WHERE C.user_id=%s AND C.due_at <= NOW() AND C.mastery_status IN ('NEW','LEARNING','REVIEW')"
            " AND V.yn=1 AND V.level_code=%s "
            " ORDER BY (CASE C.mastery_status WHEN 'NEW' THEN 0 WHEN 'LEARNING' THEN 1 ELSE 2 END), C.due_at "
            " LIMIT %s",
            (user_id, target_level, int(review_quota)),
        )

    # 新词（今日 quota 内）：优先 level_code；若无则 fallback
    new_rows = await fetch_all(
        "SELECT C.id AS card_id, C.mastery_status, C.due_at, "
        " V.id AS entry_id, V.word, V.level_code, V.phonetic_us, V.meaning_cn, V.example_en, V.example_cn,"
        " V.topic_tag, V.image_hint, V.audio_us, V.subject_code"
        " FROM user_vocab_card C JOIN vocab_entry V ON V.id = C.vocab_entry_id "
        " WHERE C.user_id=%s AND C.mastery_status='NEW' AND V.yn=1 AND V.level_code=%s"
        " ORDER BY V.id LIMIT %s",
        (user_id, target_level, int(new_quota)),
    )
    if len(new_rows) < new_quota:
        # 再补一批新词进该用户卡库
        await _ensure_cards_for_level(user_id, target_level, limit=int(new_quota))
        new_rows = await fetch_all(
            "SELECT C.id AS card_id, C.mastery_status, C.due_at, "
            " V.id AS entry_id, V.word, V.level_code, V.phonetic_us, V.meaning_cn, V.example_en, V.example_cn,"
            " V.topic_tag, V.image_hint, V.audio_us, V.subject_code"
            " FROM user_vocab_card C JOIN vocab_entry V ON V.id = C.vocab_entry_id "
            " WHERE C.user_id=%s AND C.mastery_status='NEW' AND V.yn=1 AND V.level_code=%s"
            " ORDER BY V.id LIMIT %s",
            (user_id, target_level, int(new_quota)),
        )

    now = datetime.now()
    def to_card(r: dict, idx: int) -> VocabCard:
        due = r.get("due_at") or now
        if isinstance(due, datetime):
            due_min = max(0, int((due - now).total_seconds() / 60))
        else:
            due_min = 0
        return VocabCard(
            card_id=int(r["card_id"]), entry_id=int(r["entry_id"]), word=r["word"],
            level_code=r["level_code"], phonetic_us=r.get("phonetic_us"),
            meaning_cn=r["meaning_cn"], example_en=r.get("example_en"), example_cn=r.get("example_cn"),
            topic_tag=r.get("topic_tag"), image_hint=r.get("image_hint"), audio_us=r.get("audio_us"),
            mastery_status=r["mastery_status"] or "NEW",
            due_in_minutes=due_min,
            suggested_quiz_type=QUIZ_TYPES[(idx + int(r["entry_id"])) % len(QUIZ_TYPES)],
        )

    due_cards = [to_card(r, i) for i, r in enumerate(due_rows)]
    new_cards = [to_card(r, i) for i, r in enumerate(new_rows)]

    # 统计 summary
    summary_rows = await fetch_all(
        "SELECT C.mastery_status AS s, COUNT(*) AS c FROM user_vocab_card C "
        "WHERE C.user_id=%s GROUP BY C.mastery_status",
        (user_id,),
    )
    summary: dict[str, int] = {r["s"]: int(r["c"]) for r in summary_rows}
    return DailyPlan(
        user_id=int(user_id),
        date_label=date.today().isoformat(),
        target_level_code=target_level,
        due_cards=due_cards,
        new_cards=new_cards,
        total_new_quota=int(new_quota),
        total_review_quota=int(review_quota),
        summary={
            "NEW": summary.get("NEW", 0),
            "LEARNING": summary.get("LEARNING", 0),
            "REVIEW": summary.get("REVIEW", 0),
            "MASTERED": summary.get("MASTERED", 0),
        },
    )


# ============= 4. 提交 recall（SM-2 更新）=============

async def recall(user_id: int, payload: RecallIn) -> RecallOut:
    row = await fetch_one(
        "SELECT C.id, C.ease_factor, C.interval_days, C.repetition, C.mastery_status, C.total_reviews, C.total_correct "
        " FROM user_vocab_card C WHERE C.id=%s AND C.user_id=%s LIMIT 1",
        (payload.card_id, user_id),
    )
    if row is None:
        raise BizError(404021, f"未找到 card_id={payload.card_id}（不属于你或不存在）")
    ef = float(row["ease_factor"] or 2.5)
    interval = int(row["interval_days"] or 0)
    repetition = int(row["repetition"] or 0)
    new_ef, new_interval, new_rep, new_status, delta = sm2_update(ef, interval, repetition, payload.quality)
    due_at = datetime.now() + delta
    streak_inc = 1 if payload.quality >= 3 else 0
    total_reviews = int(row["total_reviews"] or 0) + 1
    total_correct = int(row["total_correct"] or 0) + (1 if payload.quality >= 3 else 0)

    await execute_write(
        "UPDATE user_vocab_card SET ease_factor=%s, interval_days=%s, repetition=%s, due_at=%s,"
        " last_quality=%s, last_review_at=NOW(), total_reviews=%s, total_correct=%s, mastery_status=%s, updated_at=NOW()"
        " WHERE id=%s AND user_id=%s",
        (
            float(new_ef), int(new_interval), int(new_rep), due_at,
            int(payload.quality), int(total_reviews), int(total_correct), new_status,
            int(payload.card_id), int(user_id),
        ),
    )
    return RecallOut(
        card_id=payload.card_id,
        quality=int(payload.quality),
        mastery_status=new_status,
        new_ease_factor=float(new_ef),
        new_interval_days=int(new_interval),
        new_due_at=due_at,
        total_reviews=int(total_reviews),
        streak_increment=int(streak_inc),
    )


# ============= 5. Progress 统计（多等级）=============

async def progress(user_id: int, level_code: str | None = None) -> ProgressStat:
    level_code = level_code or await _guess_user_target_level(user_id)
    # 该等级词库总数
    total_words = int((await fetch_one(
        "SELECT COUNT(*) c FROM vocab_entry WHERE yn=1 AND level_code=%s", (level_code,),
    ))["c"])
    # 掌握/学习中
    agg = await fetch_all(
        "SELECT C.mastery_status AS s, COUNT(*) c FROM user_vocab_card C "
        "JOIN vocab_entry V ON V.id=C.vocab_entry_id "
        "WHERE C.user_id=%s AND V.level_code=%s GROUP BY C.mastery_status",
        (user_id, level_code),
    )
    mp = {r["s"]: int(r["c"]) for r in agg}
    mastered = mp.get("MASTERED", 0)
    learning = mp.get("LEARNING", 0) + mp.get("REVIEW", 0)

    # 今日学习量
    today_start = datetime.combine(date.today(), datetime.min.time())
    today = await fetch_all(
        "SELECT C.mastery_status AS s, COUNT(*) c FROM user_vocab_card C "
        "WHERE C.user_id=%s AND C.last_review_at >= %s GROUP BY C.mastery_status",
        (user_id, today_start),
    )
    today_mp = {r["s"]: int(r["c"]) for r in today}
    reviewed_today = sum(today_mp.values())
    new_today = today_mp.get("LEARNING", 0)  # 近似：今天首次变成 LEARNING 的次数（粗略用 any today last_rv）

    # 连续打卡天数：统计 last_review_at 连续天数
    streak = await _calc_streak_days(user_id)
    # 30 天正确率
    acc_rows = await fetch_one(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN last_quality>=3 THEN 1 ELSE 0 END) AS good "
        "FROM user_vocab_card C WHERE C.user_id=%s AND C.last_review_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)",
        (user_id,),
    )
    total = int(acc_rows["total"] or 0)
    accuracy = (float(acc_rows["good"] or 0) / total) if total > 0 else 0.0

    # 估计升级天数：按今日速率
    remaining = max(0, int(total_words * 0.9) - mastered - learning)
    if remaining <= 0:
        expected_days = 0
    else:
        per_day = max(1, reviewed_today or max(1, total // 30))
        expected_days = remaining // per_day
    return ProgressStat(
        user_id=int(user_id),
        level_code=level_code,
        total_words=int(total_words),
        mastered=int(mastered),
        learning=int(learning),
        new_today=int(new_today),
        reviewed_today=int(reviewed_today),
        streak_days=int(streak),
        total_reviews=total,
        accuracy_30d=round(float(accuracy), 4),
        expected_days_to_level_up=int(expected_days),
    )


async def _calc_streak_days(user_id: int) -> int:
    """以 date 为准，统计「昨天/前天/... 只要有 >=1 次 last_review_at 就连续；缺一天则停」。"""
    rows = await fetch_all(
        "SELECT DISTINCT DATE(last_review_at) AS d FROM user_vocab_card C "
        "WHERE C.user_id=%s AND C.last_review_at IS NOT NULL "
        "ORDER BY d DESC LIMIT 366",
        (user_id,),
    )
    if not rows:
        return 0
    days = {r["d"] for r in rows if r["d"] is not None}
    today = date.today()
    streak = 0
    d = today
    # 如果今天还没打卡，但昨天打了，那按行业习惯「连续打卡 = 含昨天起连续」，但今天打了就+1
    while d in days:
        streak += 1
        d = d - timedelta(days=1)
    if streak == 0:
        # 今天没学过但昨天学了：从昨天开算
        d = today - timedelta(days=1)
        while d in days:
            streak += 1
            d = d - timedelta(days=1)
    return streak
