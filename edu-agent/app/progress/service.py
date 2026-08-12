# -*- coding: utf-8 -*-
"""P3 学习进度追踪 —— service 层。"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from app.common.exceptions import AppException as BizError
from app.database import fetch_all, fetch_one, execute_write
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

    # --- 批量 INSERT ---
    rows_inserted = 0
    for t in deduped:
        payload_str = json.dumps(t.event_payload, ensure_ascii=False) if t.event_payload else None
        sql = (
            "INSERT INTO session_video_play_event "
            "(user_id, session_id, play_session_id, event_type, position_seconds, playback_rate,"
            " network_type, event_payload, event_time, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())"
        )
        await execute_write(
            sql,
            (
                user_id, payload.session_id, payload.play_session_id, t.event_type[:32],
                t.position_seconds, float(t.playback_rate), t.network_type[:32] or "UNKNOWN",
                payload_str, t.event_time,
            ),
        )
        rows_inserted += 1

    # --- 按日期聚合后 UPSERT learning_daily_summary ---
    by_date: dict[date, dict[str, int]] = {}
    for t in deduped:
        d = t.event_time.date() if isinstance(t.event_time, datetime) else t.event_time
        bucket = by_date.setdefault(d, {"study_seconds": 0, "video_ticks": 0})
        bucket["video_ticks"] += 1
    # 把全部 study_seconds_delta 累加到本批次最大日期（最后一条打点的日期）
    if deduped:
        last_date = (deduped[-1].event_time.date()
                     if isinstance(deduped[-1].event_time, datetime) else deduped[-1].event_time)
        by_date[last_date]["study_seconds"] += study_seconds_delta

    for d, vals in by_date.items():
        upsert_sql = (
            "INSERT INTO learning_daily_summary "
            "(user_id, stat_date, study_seconds, video_ticks, yn, created_at, updated_at) "
            "VALUES (%s,%s,%s,%s,1,NOW(),NOW()) "
            "ON DUPLICATE KEY UPDATE "
            "  study_seconds = study_seconds + VALUES(study_seconds),"
            "  video_ticks = video_ticks + VALUES(video_ticks),"
            "  updated_at = NOW()"
        )
        await execute_write(upsert_sql, (user_id, d, vals["study_seconds"], vals["video_ticks"]))

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
    """返回：graded_list, correct_count, total_count, sum_score（按题库 default_score 计）。"""
    if not answers:
        return [], 0, 0, 0.0
    qids = [a.question_id for a in answers]
    qrows = await fetch_all(
        "SELECT id, question_type, correct_answer, default_score FROM admin_question_bank "
        f"WHERE id IN ({','.join(['%s']*len(qids))}) AND yn=1",
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
        score = float(q["default_score"] or 0) if ok else 0.0
        if ok:
            correct += 1
            sum_score += score
        graded.append({
            "question_id": a.question_id,
            "answer": a.answer,
            "score": score,
            "is_correct": ok,
        })
    rate = (correct / total) if total > 0 else 0.0
    return graded, correct, total, sum_score


# ============================================================
# 3. 作业提交
# ============================================================

async def submit_homework(user_id: int, req: HomeworkSubmitIn) -> SubmitOut:
    """提交一次课次作业（一课次一次作业，homework_id = session_id）。"""
    sess = await fetch_one(
        "SELECT id, session_title, module_id FROM curriculum_session WHERE id=%s",
        (req.session_id,),
    )
    if not sess:
        raise BizError(404003, "提交失败：课次不存在")

    graded, correct_count, total_count, total_score = await _grade_answers(req.answers)
    auto_graded = all(g.get("is_correct") is not None for g in graded)
    correction_status = "AUTO_GRADED" if auto_graded else "PARTIAL_GRADED"
    submit_no = f"SH-{req.session_id}-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    correct_rate = (correct_count / total_count) if total_count > 0 else None

    sql = (
        "INSERT INTO session_homework_submission "
        "(institution_id, homework_id, user_id, student_id, session_id, submit_no, submit_status,"
        " total_score, correction_status, corrected_by, feedback_text, answers_json,"
        " submitted_at, corrected_at, created_at, updated_at) "
        "VALUES (1,%s,%s,%s,%s,%s,'SUBMITTED',%s,%s,NULL,NULL,%s,NOW(),NOW(),NOW(),NOW())"
    )
    sub_id = int(await execute_write(
        sql,
        (
            req.session_id, user_id, user_id, req.session_id, submit_no,
            total_score, correction_status, json.dumps(graded, ensure_ascii=False),
        ),
    ))

    # 今日 daily_summary upsert：作业计数+答题累积（正确率下一条语句重算 JSON 聚合）
    today = date.today()
    await execute_write(
        "INSERT INTO learning_daily_summary "
        "(user_id, stat_date, study_seconds, video_ticks, homework_submitted, homework_correct_rate,"
        " questions_attempted, questions_correct, yn, created_at, updated_at) "
        "VALUES (%s,%s,0,0,1,%s,%s,%s,1,NOW(),NOW()) "
        "ON DUPLICATE KEY UPDATE "
        "  homework_submitted = homework_submitted + 1,"
        "  questions_attempted = questions_attempted + VALUES(questions_attempted),"
        "  questions_correct = questions_correct + VALUES(questions_correct),"
        "  updated_at = NOW()",
        (user_id, today, correct_rate, total_count, correct_count),
    )
    # 重算今日作业平均正确率（取 answers_json.is_correct=true 占比的均值）
    await execute_write(
        "UPDATE learning_daily_summary d "
        "SET d.homework_correct_rate = ("
        "  SELECT AVG(s.score_rate) FROM ("
        "    SELECT"
        "      JSON_LENGTH(JSON_SEARCH(answers_json,'one',true,NULL,'$[*].is_correct')) /"
        "      NULLIF(JSON_LENGTH(answers_json),0) AS score_rate "
        "    FROM session_homework_submission "
        "    WHERE user_id=%s AND DATE(submitted_at)=%s AND answers_json IS NOT NULL"
        "  ) s WHERE s.score_rate IS NOT NULL"
        ") "
        "WHERE d.user_id=%s AND d.stat_date=%s",
        (user_id, today, user_id, today),
    )

    return SubmitOut(
        submission_id=int(sub_id),
        submit_no=submit_no,
        total_score=total_score,
        correct_count=correct_count,
        total_count=total_count,
        correct_rate=correct_rate,
        status=correction_status,
    )


# ============================================================
# 4. 考试提交
# ============================================================

async def submit_exam(user_id: int, req: ExamSubmitIn) -> SubmitOut:
    """提交一份试卷（exam_id = admin_exam_paper.id），按试卷条目计分。"""
    paper = await fetch_one(
        "SELECT id, paper_title, total_score, pass_score, subject_code FROM admin_exam_paper WHERE id=%s AND yn=1",
        (req.paper_id,),
    )
    if not paper:
        raise BizError(404004, "提交失败：试卷不存在")

    # 按试卷条目实际分数（score）× 该题正误 计分
    qids = [a.question_id for a in req.answers]
    placeholders = ",".join(["%s"] * len(qids)) if qids else "NULL"
    item_rows = await fetch_all(
        f"SELECT question_id, score FROM admin_exam_paper_item WHERE paper_id=%s AND question_id IN ({placeholders})",
        (req.paper_id, *qids) if qids else (req.paper_id,),
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

    attempt_no = f"EX-{req.paper_id}-{user_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    sql = (
        "INSERT INTO session_exam_submission "
        "(institution_id, exam_id, user_id, student_id, attempt_no, attempt_status,"
        " duration_seconds, score_value, start_at, submit_at, answers_json, created_at, updated_at) "
        "VALUES (1,%s,%s,%s,%s,'SUBMITTED',%s,%s,%s,NOW(),%s,NOW(),NOW())"
    )
    sub_id = int(await execute_write(
        sql,
        (
            req.paper_id, user_id, user_id, attempt_no,
            int(req.duration_seconds), total_score, req.start_at,
            json.dumps(graded, ensure_ascii=False),
        ),
    ))

    today = date.today()
    # UPSERT 今日聚合（exam_submitted, questions_attempted/correct）
    await execute_write(
        "INSERT INTO learning_daily_summary "
        "(user_id, stat_date, study_seconds, video_ticks, homework_submitted, exam_submitted,"
        " exam_avg_score, questions_attempted, questions_correct, yn, created_at, updated_at) "
        "VALUES (%s,%s,0,0,0,1,%s,%s,%s,1,NOW(),NOW()) "
        "ON DUPLICATE KEY UPDATE "
        "  exam_submitted = exam_submitted + 1,"
        "  questions_attempted = questions_attempted + VALUES(questions_attempted),"
        "  questions_correct = questions_correct + VALUES(questions_correct),"
        "  updated_at = NOW()",
        (user_id, today, total_score, total_count, correct_count),
    )
    # 重算 exam_avg_score
    await execute_write(
        "UPDATE learning_daily_summary d "
        "SET d.exam_avg_score = ("
        "  SELECT AVG(score_value) FROM session_exam_submission "
        "  WHERE user_id=%s AND DATE(submit_at)=%s AND attempt_status IN ('SUBMITTED','GRADED')"
        ") "
        "WHERE d.user_id=%s AND d.stat_date=%s",
        (user_id, today, user_id, today),
    )

    status = "AUTO_GRADED" if all(g.get("is_correct") is not None for g in graded) else "PARTIAL_GRADED"
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
    days = max(1, min(days, 365))
    # 取最近 days 天明细（含空补 0，保证折线连续）
    start_date = date.today() - timedelta(days=days - 1)
    rows = await fetch_all(
        "SELECT stat_date, study_seconds, video_ticks, homework_submitted, homework_correct_rate,"
        " exam_submitted, exam_avg_score, questions_attempted, questions_correct "
        "FROM learning_daily_summary "
        "WHERE user_id=%s AND stat_date>=%s ORDER BY stat_date ASC",
        (user_id, start_date),
    )
    row_map: dict[date, dict] = {r["stat_date"]: r for r in rows}
    recent: list[DailyStatItem] = []
    i = 0
    while i < days:
        d = start_date + timedelta(days=i)
        r = row_map.get(d)
        if r:
            recent.append(DailyStatItem(
                stat_date=d,
                study_seconds=int(r["study_seconds"] or 0),
                video_ticks=int(r["video_ticks"] or 0),
                homework_submitted=int(r["homework_submitted"] or 0),
                homework_correct_rate=(float(r["homework_correct_rate"]) if r.get("homework_correct_rate") is not None else None),
                exam_submitted=int(r["exam_submitted"] or 0),
                exam_avg_score=(float(r["exam_avg_score"]) if r.get("exam_avg_score") is not None else None),
                questions_attempted=int(r["questions_attempted"] or 0),
                questions_correct=int(r["questions_correct"] or 0),
            ))
        else:
            recent.append(DailyStatItem(stat_date=d, study_seconds=0))
        i += 1

    # 累计
    tot = await fetch_one(
        "SELECT COUNT(*) AS total_days,"
        " SUM(study_seconds) AS total_study_seconds,"
        " SUM(questions_attempted) AS total_questions_attempted,"
        " SUM(questions_correct) AS total_questions_correct "
        "FROM learning_daily_summary WHERE user_id=%s",
        (user_id,),
    ) or {}
    total_days = int(tot.get("total_days") or 0)
    total_study_seconds = int(tot.get("total_study_seconds") or 0)
    total_q_a = int(tot.get("total_questions_attempted") or 0)
    total_q_c = int(tot.get("total_questions_correct") or 0)
    overall_rate = (total_q_c / total_q_a) if total_q_a > 0 else None

    # 最近连续学习天数：从今天往前数 daily_summary 存在 study_seconds>0 或 video_ticks>0 的日期
    streak = 0
    cursor = date.today()
    all_rows = await fetch_all(
        "SELECT stat_date FROM learning_daily_summary "
        "WHERE user_id=%s AND (study_seconds>0 OR video_ticks>0 OR homework_submitted>0 OR exam_submitted>0) "
        "ORDER BY stat_date DESC",
        (user_id,),
    )
    active_dates = {r["stat_date"] for r in all_rows}
    # 如果今天还没开始学习，从昨天开始算连续
    if cursor not in active_dates:
        cursor -= timedelta(days=1)
    while cursor in active_dates:
        streak += 1
        cursor -= timedelta(days=1)

    return DashboardOut(
        total_days=total_days,
        total_study_seconds=total_study_seconds,
        total_questions_attempted=total_q_a,
        total_questions_correct=total_q_c,
        overall_correct_rate=overall_rate,
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
    """返回用户在指定系列（或全部 yn=1 的系列）中的进度。"""
    where_sql = " WHERE 1=1 "
    args: list[Any] = []
    if series_id is not None and series_id > 0:
        where_sql += " AND id=%s "
        args.append(series_id)
    where_sql += " ORDER BY id LIMIT 5 "
    series_list = await fetch_all(
        f"SELECT id, series_name AS series_title FROM curriculum_series {where_sql}",
        tuple(args) if args else (),
    )
    if not series_list:
        return []

    sids = [int(s["id"]) for s in series_list]
    # 取所有模块 + 课次 tree（真实列：module_name、stage_no）
    modules = await fetch_all(
        f"SELECT id, series_id, module_name AS module_title, stage_no AS module_no FROM curriculum_module "
        f"WHERE series_id IN ({','.join(['%s']*len(sids))}) ORDER BY series_id, stage_no",
        tuple(sids),
    )
    modules_by_series: dict[int, list[dict]] = {}
    for m in modules:
        modules_by_series.setdefault(int(m["series_id"]), []).append(dict(m))
    all_mids = [int(m["id"]) for m in modules]
    if not all_mids:
        sessions_by_module: dict[int, list[dict]] = {}
    else:
        sessions = await fetch_all(
            f"SELECT id, module_id, session_title, session_no, teaching_date, duration_minutes "
            f"FROM curriculum_session "
            f"WHERE module_id IN ({','.join(['%s']*len(all_mids))}) ORDER BY module_id, session_no",
            tuple(all_mids),
        )
        sessions_by_module = {}
        for s in sessions:
            sessions_by_module.setdefault(int(s["module_id"]), []).append(dict(s))

    # 取用户所有视频 event 聚合（max pos per session_id）
    session_ids = list({sess["id"] for sess_list in sessions_by_module.values() for sess in sess_list})
    vp_max: dict[int, int] = {}
    if session_ids:
        vp_rows = await fetch_all(
            f"SELECT session_id, MAX(position_seconds) AS maxpos FROM session_video_play_event "
            f"WHERE user_id=%s AND session_id IN ({','.join(['%s']*len(session_ids))}) GROUP BY session_id",
            (user_id, *session_ids),
        )
        vp_max = {int(r["session_id"]): int(r["maxpos"] or 0) for r in vp_rows}

    # 取用户作业完成情况（session_id → 是否提交 + 分数）
    hw_map: dict[int, dict] = {}
    if session_ids:
        hw_rows = await fetch_all(
            f"SELECT session_id, total_score, submit_status FROM session_homework_submission "
            f"WHERE user_id=%s AND session_id IN ({','.join(['%s']*len(session_ids))}) "
            f"ORDER BY submitted_at DESC",
            (user_id, *session_ids),
        )
        # 同一 session 多次提交取最近一次
        for r in hw_rows:
            sid = int(r["session_id"])
            if sid not in hw_map:
                hw_map[sid] = dict(r)

    out: list[CourseProgressOut] = []
    for s in series_list:
        sid_series = int(s["id"])
        mods_out: list[ModuleProgressItem] = []
        total_sess = 0
        completed_sess = 0
        series_ration_sum = 0.0
        series_ration_cnt = 0
        for m in modules_by_series.get(sid_series, []):
            mid = int(m["id"])
            sessions = sessions_by_module.get(mid, [])
            sess_out_list: list[SessionProgressItem] = []
            mod_sum = 0.0
            for sess in sessions:
                sess_id = int(sess["id"])
                total_sess += 1
                series_ration_cnt += 1
                duration = int(sess.get("duration_minutes") or 45)
                maxpos = vp_max.get(sess_id, 0)
                ratio = (maxpos / (duration * 60)) if duration > 0 else 0.0
                ratio = max(0.0, min(ratio, 1.0))
                hw = hw_map.get(sess_id) or {}
                hw_done = hw.get("submit_status") in {"SUBMITTED", "PARTIAL_GRADED", "AUTO_GRADED", "GRADED"}
                score = float(hw.get("total_score") or 0) if hw_done else None
                score_out = float(score) if hw_done and score > 0 else None
                sess_item_score = _session_score(ratio, bool(hw_done))
                mod_sum += sess_item_score
                series_ration_sum += sess_item_score
                if ratio >= 0.8 and hw_done:
                    completed_sess += 1
                sess_out_list.append(SessionProgressItem(
                    session_id=sess_id,
                    session_title=sess.get("session_title") or f"Session {sess_id}",
                    teaching_date=sess.get("teaching_date"),
                    video_watch_ratio=ratio,
                    homework_done=bool(hw_done),
                    homework_score=score_out,
                ))
            mod_ratio = (mod_sum / len(sessions)) if sessions else 0.0
            mods_out.append(ModuleProgressItem(
                module_id=mid,
                module_title=m.get("module_title") or f"Module {mid}",
                module_no=int(m.get("module_no") or 0),
                overall_ratio=mod_ratio,
                sessions=sess_out_list,
            ))
        series_ratio = (series_ration_sum / series_ration_cnt) if series_ration_cnt > 0 else 0.0
        out.append(CourseProgressOut(
            series_id=sid_series,
            series_title=s.get("series_title") or f"Series {sid_series}",
            overall_ratio=series_ratio,
            total_sessions=total_sess,
            completed_sessions=completed_sess,
            modules=mods_out,
        ))
    return out
