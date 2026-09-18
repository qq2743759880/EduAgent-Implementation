# -*- coding: utf-8 -*-
"""P3 学习进度追踪 —— service 层。"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from app.common.exceptions import AppException as BizError
from app.database import fetch_all, fetch_one, execute_write
from app.domains.analytics.event_stream import emit_learning_event
from app.progress.schemas import (
    CourseProgressOut, DashboardOut, DailyStatItem, ExamSubmitIn,
    HomeworkSubmitIn, ModuleProgressItem, SessionProgressItem,
    SubmitOut, SubmittedAnswerIn, VideoTickBatchIn, VideoTickBatchOut,
)


# ============================================================
# 1. 视频打点（批量 + 去重 + 时长增量计算 + 每日聚合更新）
# ============================================================

async def record_video_ticks(user_id: int, payload: VideoTickBatchIn) -> VideoTickBatchOut:
    """批量写入视频打点（30 秒上传一次），并更新 daily_summary。"""
    # 按 event_time 排序并在批次内按 (play_session_id,event_time,position_seconds) 去重
    seen: set[tuple[int, datetime, int]] = set()
    deduped = []
    for t in sorted(payload.ticks, key=lambda x: (x.event_time, x.position_seconds)):
        key = (payload.play_session_id, t.event_time.replace(microsecond=0), t.position_seconds)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)

    if not deduped:
        return VideoTickBatchOut(inserted=0, study_seconds_delta=0, message="no new ticks")

    # --- 计算学习时长增量（连续有效播放的 position 差）---
    study_seconds_delta = 0
    prev_pos: int | None = None
    prev_time: datetime | None = None
    for t in deduped:
        if prev_pos is None:
            prev_pos = t.position_seconds
            prev_time = t.event_time
            continue
        dpos = t.position_seconds - prev_pos
        dtime = int((t.event_time - prev_time).total_seconds()) if prev_time else 0
        # 有效增量：前进的位置差 > 0，且和时间差相差在 ±60 秒内（排除暂停/拖动导致的跳变）
        if 0 < dpos <= 3600 and abs(dtime - dpos) <= 60:
            study_seconds_delta += dpos
        prev_pos = t.position_seconds
        prev_time = t.event_time

    # --- 确保 play_session 存在（play_session_id → session_video_play.id）---
    play = await fetch_one(
        "SELECT id, user_id, watched_seconds FROM session_video_play WHERE id=%s",
        (payload.play_session_id,),
    )
    if not play:
        raise BizError(400010, f"play_session not found: {payload.play_session_id}")

    # --- 批量 INSERT（不含 user_id/session_id，通过 play_session_id FK 关联）---
    rows_inserted = 0
    for t in deduped:
        payload_str = json.dumps(t.event_payload, ensure_ascii=False) if t.event_payload else None
        sql = (
            "INSERT INTO session_video_play_event "
            "(play_session_id, event_type, position_seconds, playback_rate,"
            " network_type, event_payload, event_time, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())"
        )
        await execute_write(
            sql,
            (
                payload.play_session_id, t.event_type[:32],
                t.position_seconds, float(t.playback_rate), t.network_type[:32] or "UNKNOWN",
                payload_str, t.event_time,
            ),
        )
        rows_inserted += 1

    # --- 更新 session_video_play.watched_seconds（替代 learning_daily_summary UPSERT）---
    if study_seconds_delta > 0:
        await execute_write(
            "UPDATE session_video_play SET watched_seconds = watched_seconds + %s,"
            " updated_at = NOW() WHERE id=%s",
            (study_seconds_delta, payload.play_session_id),
        )

    # R-M1 旁路异步写（Mongo learning_event，视频心跳事件）：失败 WARN 不阻断主链；
    # 一条 tick-batch 请求 = 一条事件，payload.rows_inserted 供对账（scripts/eval/mevent_reconcile.py）
    emit_learning_event(
        "video_heartbeat",
        user_id=user_id,
        session_id=payload.play_session_id,
        payload={"rows_inserted": rows_inserted, "study_seconds_delta": study_seconds_delta},
    )

    return VideoTickBatchOut(
        inserted=rows_inserted,
        study_seconds_delta=study_seconds_delta,
        message="ok",
    )


# ============================================================
# 2. 自动判题工具（选择题/判断/填空 = 客观题自动批）
# ============================================================

def _normalize_answer(qtype: str, ans: str) -> str:
    if ans is None:
        return ""
    s = ans.strip()
    if qtype in ("MULTIPLE", "MULTI"):
        # 多选：字母排序，忽略大小写/逗号/空格
        chars = [c.upper() for c in s if c.isalpha()]
        return "".join(sorted(chars))
    if qtype in ("TRUE_FALSE", "JUDGE", "TF"):
        if s in {"1", "T", "t", "TRUE", "True", "true", "对", "正确", "是"}:
            return "1"
        if s in {"0", "F", "f", "FALSE", "False", "false", "错", "错误", "否"}:
            return "0"
        return s
    if qtype in ("FILL_BLANK", "FILL"):
        return s.replace(" ", "").lower()
    # SINGLE / UNKNOWN：不区分大小写字母
    return s.upper() if len(s) <= 4 else s


async def _grade_answers(
    answers: list[SubmittedAnswerIn],
) -> tuple[list[dict[str, Any]], int, int, float]:
    """返回：graded_list, correct_count, total_count, sum_score（每题固定 5 分）。"""
    if not answers:
        return [], 0, 0, 0.0
    qids = [a.question_id for a in answers]
    qrows = await fetch_all(
        "SELECT q.id, qt.type_code AS question_type, q.answer_text AS correct_answer "
        "FROM question q "
        "JOIN dim_question_type qt ON qt.id = q.question_type_id "
        f"WHERE q.id IN ({','.join(['%s']*len(qids))}) AND q.yn=1",
        tuple(qids),
    )
    qmap: dict[int, dict] = {q["id"]: dict(q) for q in qrows}
    graded: list[dict[str, Any]] = []
    correct = 0
    total = len(answers)
    sum_score = 0.0
    for a in answers:
        q = qmap.get(a.question_id)
        if not q:
            graded.append({
                "question_id": a.question_id,
                "answer": a.answer,
                "score": 0,
                "is_correct": False,
                "note": "题目不存在",
            })
            continue
        qtype = (q["question_type"] or "SINGLE").upper()
        subjective = qtype.startswith("SUBJECT") or qtype == "WRITING" or qtype == "ESSAY"
        if subjective:
            graded.append({
                "question_id": a.question_id,
                "answer": a.answer,
                "score": 0,
                "is_correct": None,
                "note": "主观题待人工批改",
            })
            continue
        norm_stu = _normalize_answer(qtype, a.answer)
        norm_ref = _normalize_answer(qtype, (q["correct_answer"] or ""))
        ok = bool(norm_stu and norm_ref and norm_stu == norm_ref)
        score = 5.0 if ok else 0.0
        if ok:
            correct += 1
            sum_score += score
        graded.append({
            "question_id": a.question_id,
            "answer": a.answer,
            "score": score,
            "is_correct": ok,
        })
    return graded, correct, total, sum_score


# ============================================================
# 3. 作业提交
# ============================================================

async def _resolve_student_id(user_id: int) -> int:
    """Get real student_profile.id for a user_id; auto-create minimal profile if not exists."""
    row = await fetch_one(
        "SELECT id FROM student_profile WHERE user_id=%s AND yn=1 LIMIT 1",
        (user_id,),
    )
    if row:
        return int(row["id"])
    sub_id = await execute_write(
        "INSERT INTO student_profile (user_id, learner_identity_id, learning_goal_id, yn, created_at, updated_at) "
        "VALUES (%s, 1, 1, 1, NOW(), NOW())",
        (user_id,),
    )
    return int(sub_id)


async def submit_homework(user_id: int, req: HomeworkSubmitIn) -> SubmitOut:
    """提交一次课次作业。"""
    sess = await fetch_one(
        "SELECT id, session_title FROM series_cohort_session WHERE id=%s",
        (req.session_id,),
    )
    if not sess:
        raise BizError(404003, "提交失败：课次不存在")

    student_id = await _resolve_student_id(user_id)

    graded, correct_count, total_count, total_score = await _grade_answers(req.answers)
    auto_graded = all(g.get("is_correct") is not None for g in graded)
    response_status = "AUTO_GRADED" if auto_graded else "PARTIAL_GRADED"
    db_correction_status = "corrected" if auto_graded else "pending"
    submit_no = f"SH-{req.session_id}-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    correct_rate = (correct_count / total_count) if total_count > 0 else None

    sql = (
        "INSERT INTO session_homework_submission "
        "(institution_id, homework_id, user_id, student_id, session_id, submit_no, submit_status,"
        " total_score, correction_status, corrected_by, feedback_text,"
        " submitted_at, corrected_at, created_at, updated_at) "
        "VALUES (1,%s,%s,%s,%s,%s,'submitted',%s,%s,NULL,NULL,NOW(),NOW(),NOW(),NOW())"
    )
    sub_id = int(await execute_write(
        sql,
        (
            req.homework_id, user_id, student_id, req.session_id, submit_no,
            total_score, db_correction_status,
        ),
    ))

    return SubmitOut(
        submission_id=int(sub_id),
        submit_no=submit_no,
        total_score=total_score,
        correct_count=correct_count,
        total_count=total_count,
        correct_rate=correct_rate,
        status=response_status,
    )


# ============================================================
# 4. 考试提交
# ============================================================

async def submit_exam(user_id: int, req: ExamSubmitIn) -> SubmitOut:
    """提交一份考试。"""
    exam = await fetch_one(
        "SELECT id, exam_name, total_score, pass_score FROM session_exam WHERE id=%s",
        (req.exam_id,),
    )
    if not exam:
        raise BizError(404004, "提交失败：考试不存在")

    student_id = await _resolve_student_id(user_id)

    # 按考试题目实际分数计分
    qids = [a.question_id for a in req.answers]
    placeholders = ",".join(["%s"] * len(qids)) if qids else "NULL"
    item_rows = await fetch_all(
        f"SELECT question_id, score FROM session_exam_question_rel WHERE exam_id=%s AND question_id IN ({placeholders})",
        (req.exam_id, *qids) if qids else (req.exam_id,),
    )
    item_score_map: dict[int, float] = {int(r["question_id"]): float(r["score"] or 0) for r in item_rows}

    graded, _correct_raw, total_count, _sum_default = await _grade_answers(req.answers)
    correct_count = 0
    total_score = 0.0
    for g in graded:
        ok = g.get("is_correct") is True
        if ok:
            correct_count += 1
            total_score += float(item_score_map.get(int(g["question_id"]), 0.0))
    correct_rate = (correct_count / total_count) if total_count > 0 else None

    attempt_no = f"EX-{req.exam_id}-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    db_attempt_status = "submitted"
    auto_graded = all(g.get("is_correct") is not None for g in graded)

    sql = (
        "INSERT INTO session_exam_submission "
        "(institution_id, exam_id, user_id, student_id, attempt_no, attempt_status,"
        " duration_seconds, score_value, start_at, submit_at, created_at, updated_at) "
        "VALUES (1,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW(),NOW())"
    )
    sub_id = int(await execute_write(
        sql,
        (
            req.exam_id, user_id, student_id, attempt_no, db_attempt_status,
            int(req.duration_seconds), total_score, req.start_at,
        ),
    ))

    status = "AUTO_GRADED" if auto_graded else "PARTIAL_GRADED"
    return SubmitOut(
        submission_id=int(sub_id),
        submit_no=attempt_no,
        total_score=total_score,
        correct_count=correct_count,
        total_count=total_count,
        correct_rate=correct_rate,
        status=status,
    )


# ============================================================
# 5. 统计看板
# ============================================================

async def get_dashboard(user_id: int, days: int = 7) -> DashboardOut:
    """从 session_video_play / session_homework_submission / session_exam_submission 聚合统计看板。"""
    days = max(1, min(days, 365))
    start_date = date.today() - timedelta(days=days - 1)

    # ---------- 视频 ----------
    video_rows = await fetch_all(
        "SELECT DATE(started_at) AS stat_date,"
        " COALESCE(SUM(watched_seconds),0) AS study_seconds,"
        " COUNT(DISTINCT id) AS play_sessions"
        " FROM session_video_play"
        " WHERE user_id=%s AND DATE(started_at)>=%s"
        " GROUP BY DATE(started_at)",
        (user_id, start_date),
    )
    video_map: dict[date, dict] = {r["stat_date"]: r for r in video_rows}

    # ---------- 作业（edu.sql 无 answers_json 列，仅统计提交数和平均分）----------
    hw_rows = await fetch_all(
        "SELECT DATE(submitted_at) AS stat_date,"
        " COUNT(*) AS cnt,"
        " AVG(COALESCE(total_score,0)) AS avg_score"
        " FROM session_homework_submission"
        " WHERE user_id=%s AND DATE(submitted_at)>=%s"
        " GROUP BY DATE(submitted_at)",
        (user_id, start_date),
    )
    hw_map: dict[date, dict] = {r["stat_date"]: r for r in hw_rows}

    # ---------- 考试（edu.sql 无 answers_json 列，仅统计提交数和平均分）----------
    exam_rows = await fetch_all(
        "SELECT DATE(submit_at) AS stat_date,"
        " COUNT(*) AS cnt,"
        " AVG(COALESCE(score_value,0)) AS avg_score"
        " FROM session_exam_submission"
        " WHERE user_id=%s AND DATE(submit_at)>=%s"
        " GROUP BY DATE(submit_at)",
        (user_id, start_date),
    )
    exam_map: dict[date, dict] = {r["stat_date"]: r for r in exam_rows}

    # ---------- 组装 daily 明细（无数据日期补 0）----------
    recent: list[DailyStatItem] = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        v = video_map.get(d) or {}
        h = hw_map.get(d) or {}
        e = exam_map.get(d) or {}

        study_secs = int(v.get("study_seconds") or 0)
        video_ticks = int(v.get("play_sessions") or 0)

        hw_submitted = int(h.get("cnt") or 0)
        hw_avg_score = float(h.get("avg_score") or 0) if h.get("avg_score") is not None else None

        exam_submitted = int(e.get("cnt") or 0)
        exam_avg_score = float(e.get("avg_score") or 0) if e.get("avg_score") is not None else None

        recent.append(DailyStatItem(
            stat_date=d,
            study_seconds=study_secs,
            video_ticks=video_ticks,
            homework_submitted=hw_submitted,
            homework_correct_rate=None,      # edu.sql 无作答明细载体，正确率不可计算
            exam_submitted=exam_submitted,
            exam_avg_score=exam_avg_score,
            questions_attempted=0,           # edu.sql 无作答明细载体
            questions_correct=0,
        ))

    # ---------- 累计 ----------
    tot_video = await fetch_one(
        "SELECT COUNT(DISTINCT DATE(started_at)) AS total_days,"
        " COALESCE(SUM(watched_seconds),0) AS total_study_seconds"
        " FROM session_video_play WHERE user_id=%s",
        (user_id,),
    ) or {}
    total_days = int(tot_video.get("total_days") or 0)
    total_study_seconds = int(tot_video.get("total_study_seconds") or 0)

    # 累计仅统计提交数
    total_hw_cnt = await fetch_one(
        "SELECT COUNT(*) AS cnt FROM session_homework_submission WHERE user_id=%s",
        (user_id,),
    ) or {}
    total_exam_cnt = await fetch_one(
        "SELECT COUNT(*) AS cnt FROM session_exam_submission WHERE user_id=%s",
        (user_id,),
    ) or {}
    total_submissions = int(total_hw_cnt.get("cnt") or 0) + int(total_exam_cnt.get("cnt") or 0)

    # 答题数与正确数：quiz_answer_session（task114 D4）—— 有真实作答明细载体
    q_row = await fetch_one(
        "SELECT COUNT(*) AS attempts, COALESCE(SUM(is_correct),0) AS correct "
        "FROM quiz_answer_session WHERE user_id=%s",
        (user_id,),
    ) or {}
    total_questions_attempted = int(q_row.get("attempts") or 0)
    total_questions_correct = int(q_row.get("correct") or 0)

    # 进行中的班次（active_courses_count，task114 D4）
    cohort_row = await fetch_one(
        "SELECT COUNT(*) AS cnt FROM student_cohort_rel "
        "WHERE user_id=%s AND enroll_status='active'",
        (user_id,),
    ) or {}
    active_courses_count = int(cohort_row.get("cnt") or 0)

    # ---------- 连续学习天数（从 session_video_play 的活跃日期）----------
    active_rows = await fetch_all(
        "SELECT DISTINCT DATE(started_at) AS active_date"
        " FROM session_video_play"
        " WHERE user_id=%s AND watched_seconds>0"
        " ORDER BY active_date DESC",
        (user_id,),
    )
    active_dates = {r["active_date"] for r in active_rows}
    streak = 0
    cursor = date.today()
    if cursor not in active_dates:
        cursor -= timedelta(days=1)
    while cursor in active_dates:
        streak += 1
        cursor -= timedelta(days=1)

    # 整体正确率由 quiz_answer_session 实证数据折算（task114 D4）
    overall_correct_rate = (total_questions_correct / total_questions_attempted) if total_questions_attempted > 0 else None

    return DashboardOut(
        total_days=total_days,
        total_study_seconds=total_study_seconds,
        total_questions_attempted=total_questions_attempted,
        total_questions_correct=total_questions_correct,
        overall_correct_rate=overall_correct_rate,
        active_courses_count=active_courses_count,
        latest_streak_days=streak,
        recent_days=list(reversed(recent)),  # 最新在前
    )


# ============================================================
# 6. 课程进度（按系列→模块→课次）
# ============================================================

def _session_score(ratio: float, hw_done: bool) -> float:
    """课次完成率：视频*0.5 + 作业*0.5；视频达到 0.8 视作完成观看。"""
    video_score = min(ratio / 0.8, 1.0) if ratio < 0.8 else 1.0
    hw_score = 1.0 if hw_done else 0.0
    return video_score * 0.5 + hw_score * 0.5


async def get_course_progress(user_id: int, series_id: int | None = None) -> list[CourseProgressOut]:
    """返回用户在指定系列（从 series → cohort → course → session 链查询）中的进度。"""
    where_clause = " WHERE 1=1 "
    args: list[Any] = []
    if series_id is not None and series_id > 0:
        where_clause += " AND id=%s "
        args.append(series_id)
    where_clause += " ORDER BY id LIMIT 5 "
    series_list = await fetch_all(
        f"SELECT id, series_name AS series_title FROM series {where_clause}",
        tuple(args) if args else (),
    )
    if not series_list:
        return []

    sids = [int(s["id"]) for s in series_list]
    # 取 cohorts
    cohorts = await fetch_all(
        f"SELECT id, series_id FROM series_cohort WHERE series_id IN ({','.join(['%s']*len(sids))})",
        tuple(sids),
    )
    cids_by_series: dict[int, list[int]] = {}
    all_cids: list[int] = []
    for c in cohorts:
        sid = int(c["series_id"])
        cids_by_series.setdefault(sid, []).append(int(c["id"]))
        all_cids.append(int(c["id"]))

    # 取 courses（相当于旧版 module）
    courses: list[dict] = []
    if all_cids:
        courses = await fetch_all(
            f"SELECT id, cohort_id, module_name, stage_no FROM series_cohort_course "
            f"WHERE cohort_id IN ({','.join(['%s']*len(all_cids))}) ORDER BY cohort_id, stage_no",
            tuple(all_cids),
        )
    courses_by_cohort: dict[int, list[dict]] = {}
    for c in courses:
        cid = int(c["cohort_id"])
        courses_by_cohort.setdefault(cid, []).append(dict(c))

    # 取 sessions
    all_course_ids = [int(c["id"]) for c in courses]
    sessions: list[dict] = []
    if all_course_ids:
        sessions = await fetch_all(
            f"SELECT id, series_cohort_course_id, session_title, session_no, teaching_date "
            f"FROM series_cohort_session "
            f"WHERE series_cohort_course_id IN ({','.join(['%s']*len(all_course_ids))}) "
            f"ORDER BY series_cohort_course_id, session_no",
            tuple(all_course_ids),
        )
    sessions_by_course: dict[int, list[dict]] = {}
    for s in sessions:
        cid = int(s["series_cohort_course_id"])
        sessions_by_course.setdefault(cid, []).append(dict(s))

    # 取所有 session_id
    all_session_ids = [int(s["id"]) for s in sessions]

    # 取视频进度（通过 session_video_play → session_video → session_asset → series_cohort_session 链）
    vp_max: dict[int, int] = {}
    if all_session_ids:
        # 用 session_video_play.last_position_seconds 作为观看最大位置
        vp_rows = await fetch_all(
            "SELECT sa.session_id, MAX(svp.last_position_seconds) AS maxpos "
            "FROM session_video_play svp "
            "JOIN session_video sv ON sv.id = svp.video_id "
            "JOIN session_asset sa ON sa.id = sv.asset_id "
            f"WHERE svp.user_id=%s AND sa.session_id IN ({','.join(['%s']*len(all_session_ids))}) "
            "GROUP BY sa.session_id",
            (user_id, *all_session_ids),
        )
        vp_max = {int(r["session_id"]): int(r["maxpos"] or 0) for r in vp_rows}

    # 取作业完成情况
    hw_map: dict[int, dict] = {}
    if all_session_ids:
        hw_rows = await fetch_all(
            f"SELECT session_id, total_score, submit_status FROM session_homework_submission "
            f"WHERE user_id=%s AND session_id IN ({','.join(['%s']*len(all_session_ids))}) "
            f"ORDER BY submitted_at DESC",
            (user_id, *all_session_ids),
        )
        for r in hw_rows:
            sid = int(r["session_id"])
            if sid not in hw_map:
                hw_map[sid] = dict(r)

    # 拼装返回结构：series → 收集该系列下所有 cohort 的 course（扁平化为模块）
    out: list[CourseProgressOut] = []
    for s in series_list:
        sid_series = int(s["id"])
        mods_out: list[ModuleProgressItem] = []
        total_sess = 0
        completed_sess = 0
        series_ratio_sum = 0.0
        series_ratio_cnt = 0

        # 收集该系列所有 cohort 下的 course，按 (cohort_id, stage_no) 排序
        series_courses: list[dict] = []
        for cid in cids_by_series.get(sid_series, []):
            for c in courses_by_cohort.get(cid, []):
                series_courses.append(dict(c))

        # 使用 module_no = cohort_id*100 + stage_no 保证顺序
        for idx, c in enumerate(series_courses):
            cid = int(c["id"])
            sess_list = sessions_by_course.get(cid, [])
            sess_out_list: list[SessionProgressItem] = []
            mod_sum = 0.0
            for sess in sess_list:
                sess_id = int(sess["id"])
                total_sess += 1
                series_ratio_cnt += 1
                # 默认 45 分钟，series_cohort_session 无 duration_minutes 列
                duration_seconds = 45 * 60
                maxpos = vp_max.get(sess_id, 0)
                ratio = min(maxpos / duration_seconds, 1.0) if duration_seconds > 0 else 0.0
                ratio = max(0.0, ratio)
                hw = hw_map.get(sess_id) or {}
                hw_done = hw.get("submit_status") == "submitted"
                score_val = float(hw.get("total_score") or 0) if hw_done else None
                sess_item_score = _session_score(ratio, bool(hw_done))
                mod_sum += sess_item_score
                series_ratio_sum += sess_item_score
                if ratio >= 0.8 and hw_done:
                    completed_sess += 1
                sess_out_list.append(SessionProgressItem(
                    session_id=sess_id,
                    session_title=sess.get("session_title") or f"Session {sess_id}",
                    teaching_date=sess.get("teaching_date"),
                    video_watch_ratio=ratio,
                    homework_done=bool(hw_done),
                    homework_score=score_val,
                ))
            mod_ratio = (mod_sum / len(sess_list)) if sess_list else 0.0
            mods_out.append(ModuleProgressItem(
                module_id=cid,
                module_title=c.get("module_name") or f"Course {cid}",
                module_no=idx + 1,
                overall_ratio=mod_ratio,
                sessions=sess_out_list,
            ))
        series_ratio = (series_ratio_sum / series_ratio_cnt) if series_ratio_cnt > 0 else 0.0
        out.append(CourseProgressOut(
            series_id=sid_series,
            series_title=s.get("series_title") or f"Series {sid_series}",
            overall_ratio=series_ratio,
            total_sessions=total_sess,
            completed_sessions=completed_sess,
            modules=mods_out,
        ))
    return out
