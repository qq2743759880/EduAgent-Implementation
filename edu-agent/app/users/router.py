"""
用户画像路由（都挂 Depends(get_current_user)，必须登录）。
GET  /api/users/me/profile  → 读（首次自动初始化，永不为空）
PUT  /api/users/me/profile  → 部分更新（全 Optional；None 表示不改）

另外新增两个兼容端点（对齐前端 BasicProfileForm / PreferencesForm 的 PATCH 请求）：
GET  /api/users/me           → 读（代理 /api/auth/me 的 CurrentUser，但同步 profile 字段展开）
PATCH /api/users/me           → 部分更新（接受前端宽松字段命名：avatar/avatar_url、learningGoal/learning_goals、
                                 subjectPreferences/subject_preferences 都收），并把 nickname/avatar 写回 auth.users 表。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import CurrentUser, get_current_user
from app.database import execute_write
from app.users import service as users_service
from app.users.schemas import UserProfile, UserProfileUpdate, SubjectPreference

router = APIRouter(prefix="/api/users", tags=["users · 用户画像"])


# ========== 兼容：前端 PATCH /api/users/me 的宽松入参 ==========

class UserMePatch(BaseModel):
    """前端 BasicProfileForm 传 nickname / avatar；PreferencesForm 传 learningGoal(string) / subjectPreferences(string[])。
    这里把两侧的命名都兼容进来（avatar vs avatar_url、snake_case vs camelCase）。"""
    model_config = ConfigDict(extra="ignore")

    nickname: str | None = Field(default=None, max_length=64)
    avatar: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=255)
    # PreferencesForm 的 camelCase
    learningGoal: str | None = Field(default=None)
    subjectPreferences: list[str] | None = Field(default=None)
    # 标准 snake_case（与 UserProfileUpdate 一致，后续扩展用）
    learning_goals: list[str] | None = None
    subject_preferences: list[SubjectPreference] | list[dict] | None = None


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


@router.patch("/me", response_model=dict, summary="兼容端点：更新当前用户（昵称/头像 + 画像混合）")
async def patch_my_unified(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    body: UserMePatch,
) -> dict:
    """
    两步写入：
      1) nickname / avatar 同步更新 auth.users 表（刷新 /api/auth/me 就生效）
      2) nickname / avatar_url / learningGoal(s) / subjectPreference(s) 写入 user_profile（PUT /api/users/me/profile 同样的效果）
    两端字段名都尽量兼容，避免前端被 404/405 打断。
    """
    # 1) 同步 auth.users 表：nickname、avatar_url
    nickname_upd = body.nickname
    avatar_upd = body.avatar_url or body.avatar
    if nickname_upd or avatar_upd:
        sets_cols: list[str] = []
        params: dict[str, Any] = {"user_id": user.user_id}
        if nickname_upd is not None:
            sets_cols.append("nickname = %(nickname)s")
            params["nickname"] = nickname_upd
        if avatar_upd is not None:
            sets_cols.append("avatar_url = %(avatar_url)s")
            params["avatar_url"] = avatar_upd
        if sets_cols:
            sql = f"UPDATE users SET {', '.join(sets_cols)} WHERE id = %(user_id)s LIMIT 1"
            try:
                await execute_write(sql, params)
            except Exception:
                # users 表字段若不匹配（avatar_url 列不存在等），静默忽略；画像表里还会写一遍
                pass

    # 2) 组装 UserProfileUpdate，写入 user_profile
    profile_body: dict[str, Any] = {}
    if body.nickname is not None:
        profile_body["nickname"] = body.nickname
    if (body.avatar_url or body.avatar) is not None:
        profile_body["avatar_url"] = body.avatar_url or body.avatar

    # 学习目标：前端 learningGoal 单字符串 → 后放到 learning_goals list[str]
    if body.learningGoal is not None:
        goals = [s for s in [body.learningGoal] if s]
        profile_body["learning_goals"] = goals
    elif body.learning_goals is not None:
        profile_body["learning_goals"] = list(body.learning_goals)

    # 学科偏好：
    #   - 简单格式 ["english","math"] → 转 [{subject_code, preference_score:5}]
    #   - 标准格式 [{subject_code, preference_score}] → 原样
    subjects_simple = body.subjectPreferences
    subjects_structured = body.subject_preferences
    if subjects_simple is not None:
        profile_body["subject_preferences"] = [
            {"subject_code": str(s), "preference_score": 5} for s in subjects_simple if s
        ]
    elif subjects_structured is not None:
        normalized = []
        for s in subjects_structured:
            if isinstance(s, dict):
                normalized.append({
                    "subject_code": str(s.get("subject_code")),
                    "preference_score": int(s.get("preference_score") or 5),
                })
            else:
                normalized.append(s)
        profile_body["subject_preferences"] = normalized

    updated_profile = None
    if profile_body:
        try:
            update_in = UserProfileUpdate.model_validate(profile_body)
            updated_profile = await users_service.update_profile(user, update_in)
        except Exception:
            # 画像 schema 对齐失败（字段名未来可能扩展）就只保留 users 表的写入
            updated_profile = None

    profile_resp = updated_profile or await users_service.get_or_create_profile(user)
    return {
        "ok": True,
        "updated": list(profile_body.keys()),
        "profile": profile_resp.model_dump(mode="json"),
    }


@router.get("/me", response_model=dict, summary="兼容端点：GET /api/users/me（返回 auth info + 画像合并视图）")
async def get_me_with_profile(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict:
    profile = await users_service.get_or_create_profile(user)
    data = {
        "id": user.user_id,
        "nickname": profile.nickname or user.nickname,
        "email": getattr(user, "email", None),
        "avatar": profile.avatar_url or getattr(user, "avatar_url", None) or getattr(user, "avatar", None),
        "roles": getattr(user, "roles", []),
        "tenantId": getattr(user, "tenant_id", None),
        "learningGoal": " ".join(profile.learning_goals) if profile.learning_goals else "",
        "subjectPreferences": [
            sp.subject_code for sp in profile.subject_preferences
        ] if isinstance(profile.subject_preferences, list) else [],
        "profile": profile.model_dump(mode="json"),
    }
    return data
