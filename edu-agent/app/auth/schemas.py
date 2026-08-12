"""
鉴权模块 —— 数据模型。

所有接口的输入（请求体）和输出（响应体）都在这里明确定义，
用 Pydantic 做类型校验 + 字段级文档，FastAPI 会自动生成 Swagger。
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator


# ============================================================
# 角色枚举（RBAC 四级角色体系）
# ============================================================
class UserRole(str, Enum):
    """
    平台用户角色。

    权限严格递增（层级关系）：
    student  →  teacher  →  manager  →  admin
      学生        老师        运营        超级管理员

    对应管理端路由保护（P7 用到）：
    - admin    ：全部权限
    - manager  ：课程+用户+题库管理（不含系统级配置）
    - teacher  ：题库+自己班级数据
    - student  ：仅学习端功能，禁访问 /api/admin/*
    """
    STUDENT = "student"    # 普通学员 —— 默认角色
    TEACHER = "teacher"    # 教师
    MANAGER = "manager"    # 运营/教务管理
    ADMIN = "admin"        # 超级管理员 —— 平台最高权限


# ============================================================
# 请求体（输入校验）
# ============================================================
class UserRegister(BaseModel):
    """用户注册请求体。"""
    account: str | None = Field(
        None, min_length=4, max_length=64,
        description="登录账号（唯一）。不传时默认用手机号或邮箱兜底。",
    )
    nickname: str = Field(
        ..., min_length=2, max_length=32,
        description="用户昵称，2-32 字符",
    )
    password: str = Field(
        ..., min_length=6, max_length=64,
        description="登录密码，6-64 字符（明文传入，后端 bcrypt 哈希存储）",
    )
    mobile: str | None = Field(
        None, pattern=r"^1[3-9]\d{9}$",
        description="中国大陆手机号（11 位）。手机号 / 邮箱二选一必填。",
    )
    email: EmailStr | None = Field(
        None, max_length=128,
        description="邮箱地址。手机号 / 邮箱二选一必填。",
    )
    # 允许注册时带初始信息
    real_name: str | None = Field(None, max_length=64, description="真实姓名")
    gender: str | None = Field(None, pattern=r"^(male|female|other)$", description="性别")

    @field_validator("mobile", "email")
    @classmethod
    def _require_at_least_one(cls, v, info):
        """手机号和邮箱至少填一个。"""
        # info.data 是已解析的其他字段
        if v is None and info.field_name == "email":
            if info.data.get("mobile") is None:
                raise ValueError("手机号和邮箱不能同时为空")
        return v


class UserLogin(BaseModel):
    """用户登录请求体。"""
    account: str = Field(
        ..., min_length=4, max_length=128,
        description="登录账号（账号/手机号/邮箱三选一）",
    )
    password: str = Field(
        ..., min_length=1, max_length=64,
        description="登录密码（明文传入）",
    )


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求体。"""
    refresh_token: str = Field(..., description="登录时返回的刷新 Token")


# ============================================================
# JWT 内部结构（解析后的数据载体）
# ============================================================
class TokenData(BaseModel):
    """
    JWT Payload 解析结果。

    签发时的 sub=user_id，另外附带 role，
    这样校验完 Token 后就能直接知道「谁+什么角色」，
    不用再查一次数据库。
    """
    user_id: int                   # 对应 sys_user.id
    role: UserRole                 # 角色（RBAC 依据）
    exp: datetime                  # 过期时间（UTC）
    token_type: str = "access"     # access / refresh


# ============================================================
# 响应体（输出结构）
# ============================================================
class UserInfo(BaseModel):
    """当前用户基本信息（返回给前端展示）。"""
    user_id: int
    account: str | None = Field(None, description="登录账号（sys_user.account），前端用于「用账号登录」")
    username: str | None = Field(None, description="用户名显示名（与 account 保持一致，便于前端双向读取）")
    nickname: str
    real_name: str | None
    mobile: str | None
    email: str | None
    gender: str | None
    avatar_url: str | None
    role: UserRole


class LoginResponse(BaseModel):
    """登录成功响应。"""
    access_token: str = Field(..., description="访问令牌（24 小时有效，放 Authorization: Bearer xxx）")
    refresh_token: str = Field(..., description="刷新令牌（7 天有效，用于换新 access_token）")
    token_type: str = Field("Bearer", description="令牌类型，固定 Bearer")
    expires_in: int = Field(..., description="access_token 剩余有效秒数")
    user: UserInfo = Field(..., description="当前用户信息，前端直接用它渲染个人中心")
