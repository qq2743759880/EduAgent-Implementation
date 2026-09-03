"""
用户画像路由（都挂 Depends(get_current_user)，必须登录）。
GET  /api/users/me/profile                    → 读（首次自动初始化，永不为空）
PUT  /api/users/me/profile                    → 部分更新（全 Optional；None 表示不改）
GET  /api/users/me                            → 读代理 /api/auth/me，同步 profile 展开
GET  /api/users/me/student-profile            → 学员档案
GET  /api/users/me/learning-summary           → 学习汇总（视频时长 / 活跃班次 / 作业 / 考试）
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.resp import ok
from app.database import fetch_one
from app.users import service as users_service
from app.users.schemas import UserProfile, UserProfileUpdate

router = APIRouter(prefix="/api/users", tags=["users · 用户画像"])


@router.get("/me/profile", response_model=UserProfile, summary="获取当前用户的画像")
async def get_my_profile(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> UserProfile:
    return await users_service.get_or_create_profile(user)


@router.put("/me/profile", response_model=UserProfile, summary="部分更新当前用户的画像")
async def update_my_profile(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    body: UserProfileUpdate,
) -> UserProfile:
    return await users_service.update_profile(user, body)


@router.get("/me", response_model=dict, summary="兼容端点：GET /api/users/me（返回 auth info + 画像合并视图，task114 新契约 snake_case）")
async def get_me_with_profile(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """返回当前用户 snake_case 合并视图（task114 冻结 C-A）。

    契约：data = {user_id, account, username, nickname, role, email, mobile, real_name,
                  gender, avatar_url, learning_goal[], subject_preferences[], profile}
    - role 为字符串枚举（student/teacher/manager/admin）
    - learning_goal / subject_preferences 由用户画像展开为 list[str]
    """
    profile = await users_service.get_or_create_profile(user)
    data = {
        "user_id": user.user_id,
        "account": getattr(user, "account", None) or getattr(user, "username", None),
        "username": getattr(user, "username", None) or getattr(user, "account", None),
        "nickname": profile.nickname or user.nickname,
        "role": user.role.value,
        "email": getattr(user, "email", None),
        "mobile": getattr(user, "mobile", None),
        "real_name": getattr(user, "real_name", None),
        "gender": getattr(user, "gender", None),
        "avatar_url": profile.avatar_url or getattr(user, "avatar_url", None),
        "learning_goal": profile.learning_goals if isinstance(profile.learning_goals, list) else [],
        "subject_preferences": [
            sp.subject_code for sp in profile.subject_preferences
        ] if isinstance(profile.subject_preferences, list) else [],
        "profile": profile.model_dump(mode="json"),
    }
    return ok(data=data)


@router.get("/me/student-profile", summary="获取当前用户的学员档案")
async def get_my_student_profile(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """查询 student_profile 表，返回学员档案信息。"""
    row = await fetch_one(
        "SELECT * FROM student_profile WHERE user_id = %(user_id)s LIMIT 1",
        {"user_id": user.user_id},
    )
    return ok(data=row or {})


@router.get("/me/learning-summary", summary="获取当前用户的学习汇总数据")
async def get_my_learning_summary(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    """聚合多表，返回学习汇总：总视频时长、活跃班次、作业提交数、考试提交数及平均分。"""
    user_id = user.user_id

    # 1. 总视频观看时长
    video_row = await fetch_one(
        "SELECT COALESCE(SUM(watched_seconds), 0) AS total_watched_seconds "
        "FROM session_video_play WHERE user_id = %(user_id)s",
        {"user_id": user_id},
    )
    total_watched_seconds = video_row["total_watched_seconds"] if video_row else 0

    # 2. 活跃班次数量
    cohort_row = await fetch_one(
        "SELECT COUNT(*) AS active_cohorts_count "
        "FROM student_cohort_rel WHERE user_id = %(user_id)s AND enroll_status = 'active'",
        {"user_id": user_id},
    )
    active_cohorts_count = cohort_row["active_cohorts_count"] if cohort_row else 0

    # 3. 已提交作业数量
    hw_row = await fetch_one(
        "SELECT COUNT(*) AS homework_submitted "
        "FROM session_homework_submission WHERE user_id = %(user_id)s AND submit_status = 'submitted'",
        {"user_id": user_id},
    )
    homework_submitted = hw_row["homework_submitted"] if hw_row else 0

    # 4. 考试提交数量及平均分
    exam_row = await fetch_one(
        "SELECT COUNT(*) AS exam_submitted, "
        "       COALESCE(AVG(score_value), 0) AS exam_avg_score "
        "FROM session_exam_submission WHERE user_id = %(user_id)s AND attempt_status = 'submitted'",
        {"user_id": user_id},
    )
    exam_submitted = exam_row["exam_submitted"] if exam_row else 0
    exam_avg_score = float(exam_row["exam_avg_score"]) if exam_row else 0.0

    return ok(data={
        "total_watched_seconds": total_watched_seconds,
        "active_cohorts_count": active_cohorts_count,
        "homework_submitted": homework_submitted,
        "exam_submitted": exam_submitted,
        "exam_avg_score": exam_avg_score,
    })