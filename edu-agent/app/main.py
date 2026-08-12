"""
FastAPI 应用主入口。

关键概念：
- lifespan：应用启动/关闭钩子（初始化 5 类存储连接池）
- middleware：CORS + AuthMiddleware（公开路径白名单跳过 JWT）
- routers：health / auth / knowledge / curriculum / users / ... 逐步增加
"""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager

# Windows 下 asyncio 子进程（P8 MCP stdio create_subprocess_exec）需要 ProactorEventLoop；
# 否则 SelectorEventLoop 不支持 subprocess，导致 initialize/tool call 假死无响应。
if os.name == "nt" and sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.common.auth import AuthMiddleware
from app.common.exceptions import AppException
from app.common.logging import logger
from app.config import settings
from app.database import (
    close_milvus, close_minio, close_mongo, close_mysql, close_neo4j,
    init_milvus, init_minio, init_mongo, init_mysql, init_neo4j,
)
from app.routers import health


# ============================================================
# Lifespan：应用启动 / 关闭 钩子
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"=== {settings.APP_NAME} v{settings.APP_VERSION} 正在启动 ===")

    # ── 启动阶段：5 类存储初始化（任一失败仅 DEBUG 模式下继续） ──
    store_status = {}

    # 1. MySQL（本地，主库）
    try:
        await init_mysql()
        store_status["mysql"] = "ok"
    except Exception as e:
        logger.error(f"MySQL 初始化失败: {e}")
        store_status["mysql"] = f"error: {e}"
        if not settings.DEBUG:
            raise

    # 2. Milvus（虚拟机，向量库）
    try:
        init_milvus()
        store_status["milvus"] = "ok"
    except Exception as e:
        logger.warning(f"Milvus 初始化失败（开发模式可忽略，知识库不可用）: {e}")
        store_status["milvus"] = f"error: {e}"
        if not settings.DEBUG:
            raise

    # 3. MongoDB（虚拟机，对话状态）
    try:
        await init_mongo()
        store_status["mongodb"] = "ok"
    except Exception as e:
        logger.warning(f"MongoDB 初始化失败（开发模式可忽略，对话不可用）: {e}")
        store_status["mongodb"] = f"error: {e}"
        if not settings.DEBUG:
            raise

    # 4. MinIO（对象存储，课程视频/课件/题库附件）
    try:
        init_minio()
        store_status["minio"] = "ok"
    except Exception as e:
        logger.warning(f"MinIO 初始化失败（开发模式可忽略，文件上传不可用）: {e}")
        store_status["minio"] = f"error: {e}"
        if not settings.DEBUG:
            raise

    # 5. Neo4j（图谱存储，知识图谱/推荐/思维导图；DEBUG 连不上不阻断）
    try:
        init_neo4j()
        store_status["neo4j"] = "ok"
    except Exception as e:
        logger.warning(f"Neo4j 初始化失败（开发模式可忽略，仅图谱写入会跳过）: {e}")
        store_status["neo4j"] = f"error: {e}"
        if not settings.DEBUG:
            raise

    logger.info(f"=== 存储初始化完成: {store_status} ===")

    # ── 运行阶段 ──
    yield

    # ── 关闭阶段 ──
    logger.info("=== 服务正在关闭 ===")
    for close_fn, name in [
        (close_mysql,   "MySQL"),
        (close_mongo,   "MongoDB"),
        (lambda: (close_milvus(), None)[0], "Milvus"),
        (lambda: (close_minio(), None)[0], "MinIO"),
        (lambda: (close_neo4j(), None)[0], "Neo4j"),
    ]:
        try:
            result = close_fn()
            if hasattr(result, "__await__"):
                await result
        except Exception:
            pass
    logger.info("=== 服务已安全关闭 ===")


# ============================================================
# 创建 FastAPI 应用
# ============================================================
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="多学科在线教育平台 AI Agent",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)


# ── 中间件（顺序：后注册的先执行） ──
# CORS（开发模式开放所有来源；生产限制到前端 3000 端口）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 鉴权中间件（公开路径会在 AuthMiddleware 内部跳过）
app.add_middleware(AuthMiddleware)


# ── 全局异常处理 ──
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """业务层 AppException → 标准 JSON 响应"""
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "detail": exc.detail},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    路由里显式 raise HTTPException → 统一外壳为 {code, message, detail}。

    对 detail 有两种常见形态做兼容：
    1)  dict：auth.router 里的 detail={"code":"AUTH_EMAIL_EXISTS","message":"该邮箱已注册"}
    2)  其他（字符串 / 列表）：如 community.router 里的 detail="帖子不存在" 或数组
    """
    status_code = exc.status_code or 500
    detail = exc.detail
    if isinstance(detail, dict):
        code_val = detail.get("code", status_code * 100 if status_code else 50000)
        message_val = detail.get("message") or (str(detail) if detail else f"HTTP {status_code}")
        detail_val = detail.get("detail", detail)
    else:
        code_val = status_code * 100 if status_code else 50000
        message_val = str(detail) if detail is not None else f"HTTP {status_code}"
        detail_val = detail
    # headers（401 需要 WWW-Authenticate）原样带回
    headers = exc.headers if exc.headers else None
    return JSONResponse(
        status_code=status_code,
        content={"code": code_val, "message": message_val, "detail": detail_val},
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Pydantic 请求体校验失败（422）→ 聚合第一条错误信息为用户可读 message。

    FastAPI 默认返回 {detail:[{loc:[...],msg:"...",type:"..."}]}，前端难展示；
    这里把第一条 msg 提取出来，并保留原 detail 供调试。
    """
    errors = exc.errors()
    first_msg = "参数校验失败"
    if errors:
        first = errors[0]
        raw_msg = first.get("msg") if isinstance(first, dict) else str(first)
        loc = first.get("loc") if isinstance(first, dict) else None
        field_path = ""
        if isinstance(loc, list) and loc:
            # ["body","email"] / ["body","password",0] → 取 body 之后的部分
            tail = [str(x) for x in loc if x != "body"]
            if tail:
                field_path = ".".join(tail) + "："
        first_msg = f"{field_path}{raw_msg}" if raw_msg else first_msg
    return JSONResponse(
        status_code=422,
        content={
            "code": 42200,
            "message": first_msg,
            "detail": errors if settings.DEBUG else None,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """兜底异常：不暴露堆栈信息（生产）"""
    logger.exception(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 50000,
            "message": "服务内部错误，请稍后重试",
            "detail": str(exc) if settings.DEBUG else None,
        },
    )


# ── 注册业务路由（新增模块按依赖顺序追加） ──
app.include_router(health.router)                    # 健康检查
app.include_router(auth_router)                      # 鉴权（注册/登录/刷新/me）—— 新增

from app.knowledge.routers import router as knowledge_router
app.include_router(knowledge_router)                 # 知识库导入/检索（P1）

from app.curriculum.router import router as curriculum_router
app.include_router(curriculum_router)                  # 分级课程（P0-P 步骤3）—— 新增
from app.users.router import router as users_router
app.include_router(users_router)                       # 用户画像（P0-P 步骤4）—— 新增
from app.chat.router import router as chat_router
app.include_router(chat_router)                        # AI 问答（P2 用户端 RAG）
from app.admin.rag_admin.router import router as rag_admin_router
app.include_router(rag_admin_router)                   # 管理端 RAG 控制台（P7 路径 B）

from app.admin.course_admin.router import router as course_admin_router
app.include_router(course_admin_router)                # 管理端 课程管理（P7 路径 B）
from app.admin.question_admin.router import router as question_admin_router
app.include_router(question_admin_router)              # 管理端 题库管理（P7 路径 B）
from app.admin.user_admin.router import router as user_admin_router
app.include_router(user_admin_router)                  # 管理端 用户管理（P7 路径 B）
from app.progress.router import router as progress_router
app.include_router(progress_router)                    # 学习进度追踪（P3）
from app.recommender.router import router as recommender_router
app.include_router(recommender_router, prefix="/api/recommend")   # 推荐引擎（P4 学习路径 / 下一步 / 反馈）
from app.mindmap.router import router as mindmap_router
app.include_router(mindmap_router, prefix="/api/mindmap")         # 思维导图（P4 课程 / 学科 / 我的 / 先修链）
from app.interactive.quiz.router import router as quiz_router
app.include_router(quiz_router, prefix="/api/interactive/quiz")    # 互动习题（P5 quiz 6 API）
from app.interactive.vocab.router import router as vocab_router
app.include_router(vocab_router, prefix="/api/vocab")              # 单词闯关（P5 vocab 3 API：daily/recall/progress）
from app.interactive.coding.router import router as coding_router
app.include_router(coding_router, prefix="/api/coding")            # 编程练习（P5 coding 5 API）
from app.interactive.math.router import router as math_router
app.include_router(math_router, prefix="/api/math")                # 数学互动（P5 math 3 API）
from app.community.router import router as community_router
app.include_router(community_router)                               # 社区论坛（P6 发帖/回帖/反应/排行）
from app.gamification.router import router as gamification_router
app.include_router(gamification_router)                            # 成就激励（P6 徽章/积分/等级/排行榜）
from app.mcp.router import router as mcp_router
app.include_router(mcp_router)                                     # MCP 导入与集成（P8：server 注册/import/工具列表/测试/日志，管理员专用）
# app.include_router(admin_router)                   # 管理端（P7 已在上方分模块引入）
# app.include_router(mcp_router)                     # MCP 导入（P8 已在上方 include）


@app.get("/", tags=["根路径"])
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "message": f"欢迎使用 {settings.APP_NAME} — 多学科在线教育平台 AI Agent",
        "docs": "/docs" if settings.DEBUG else "文档已关闭（生产模式）",
    }
