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
from typing import Any

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
from app.common.error_codes import STATUS_TO_CODE
from app.common.exceptions import AppException
from app.common.logging import logger
from app.common.security_headers import SecurityHeadersMiddleware
from app.config import settings
from app.database import (
    close_milvus, close_minio, close_mongo, close_mysql, close_neo4j, close_redis,
    init_milvus, init_minio, init_mongo, init_mysql, init_mysql_ro, init_neo4j, init_redis,
)
from app.middleware import (
    TraceMiddleware, AdminAuthMiddleware, RateLimitMiddleware,
    CircuitGuardMiddleware, IdempotencyMiddleware, RespWrapMiddleware,
)
from app.routers import health
from app.monitoring.router import router as monitoring_router


def _warmup_local_models() -> None:
    """后台预热（兼容旧调用点）：统一转交 app.core.warmup.run_warmup。

    task39 GWT③：改走后端感知预热（云端优先不预加载本地 BGE、reranker 由 sidecar 预热、
    sidecar 不可达才落本地），避免 §7 薄弱点 3 的多 worker 显存重复占用。
    """
    import asyncio as _asyncio

    from app.core import warmup as _warmup_mod

    _asyncio.run(_warmup_mod.run_warmup())


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
        # 主库初始化成功后，尝试初始化只读连接池（Phase 2 读写分离）
        try:
            await init_mysql_ro()
            store_status["mysql_ro"] = "ok"
        except Exception as e:
            logger.warning(f"MySQL 只读池初始化失败（降级为主库，不影响服务）: {e}")
            store_status["mysql_ro"] = f"degraded: {e}"
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

    # 6. Redis（缓存层，Phase 1：缓存 + 限流；DEBUG 连不上不阻断，降级为无缓存）
    try:
        await init_redis()
        store_status["redis"] = "ok"
    except Exception as e:
        logger.warning(f"Redis 初始化失败（开发模式可忽略，缓存/限流降级为跳过）: {e}")
        store_status["redis"] = f"error: {e}"
        if not settings.DEBUG:
            raise

    logger.info(f"=== 存储初始化完成: {store_status} ===")

    # ── 预热阶段：后端感知预热（不阻塞启动，避免首个用户 10~44s 冷启动） ──
    # task39 GWT③：jieba + embedding（云端连接池 / 本地 BGE 二选一）+ reranker
    # （sidecar 优先，不可达才落本地进程内模型），逐组件记录耗时供 /health/warmup 观测。
    async def _warmup() -> None:
        try:
            from app.core import warmup as warmup_mod
            await warmup_mod.run_warmup()
        except Exception as exc:
            logger.warning(f"[预热] 预热失败（不影响服务，请求时懒加载兜底）：{type(exc).__name__}: {exc}")

    warmup_task = asyncio.create_task(_warmup())

    # ── AI HITL 退款审批：72h 超时升级后台扫描（task28 GWT③） ──
    # settings.HITL_ESCALATION_AUTO=True 时自动拉起；stop_event 置位在关闭阶段退出。
    hitl_stop = asyncio.Event()
    hitl_scan_task = None
    if settings.HITL_REFUND_ENABLED and settings.HITL_ESCALATION_AUTO:
        try:
            from app.domains.trade.refund.hitl_graph import run_escalation_loop
            hitl_scan_task = asyncio.create_task(run_escalation_loop(stop_event=hitl_stop))
        except Exception as e:
            logger.warning(f"AI HITL 超时扫描任务启动失败（跳过，不影响服务）: {e}")

    # ── 运行阶段 ──
    yield

    # ── 关闭阶段 ──
    if hitl_scan_task is not None:
        hitl_stop.set()
        try:
            await asyncio.wait_for(hitl_scan_task, timeout=10)
        except Exception:
            hitl_scan_task.cancel()
    warmup_task.cancel()
    logger.info("=== 服务正在关闭 ===")
    for close_fn, name in [
        (close_mysql,   "MySQL"),
        (close_mongo,   "MongoDB"),
        (lambda: (close_milvus(), None)[0], "Milvus"),
        (lambda: (close_minio(), None)[0], "MinIO"),
        (lambda: (close_neo4j(), None)[0], "Neo4j"),
        (lambda: (close_redis(), None)[0], "Redis"),
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


# ── 中间件（顺序：SecurityHeaders → CORS → RateLimit → AdminAuth → Idempotency → CircuitGuard → Trace → RespWrap） ──
# 注册顺序 = 请求执行顺序的逆序（最后注册=最外层，最先注册=最内层靠路由）
# ┌───────────────────────────────────────────────────────────┐
# │ RespWrap  (8th, 最外层：响应壳兜底)                         │
# │  ├ Trace     (7th: X-Trace-Id 注入 + 慢日志，外层保证       │
# │  │            AAuth 401/RL 429 短路响应仍携带 trace_id)    │
# │  │  ├ CircuitGuard (6th: 轻量熔断打标)                    │
# │  │  │  ├ Idempotency  (5th: 幂等，写方法拦截)             │
# │  │  │  │  ├ AdminAuth    (4th: 管理端 Bearer 鉴权)        │
# │  │  │  │  │  ├ RateLimit    (3rd: IP+user 双维度限流)     │
# │  │  │  │  │  │  ├ CORS        (2nd: 跨域)                 │
# │  │  │  │  │  │  │  ├ SecurityHeaders (1st, 最内层靠路由) │
# │  │  │  │  │  │  │  │  └ Router                           │
# └───────────────────────────────────────────────────────────┘
app.add_middleware(SecurityHeadersMiddleware)

# CORS
def _cors_origins() -> list[str]:
    if settings.DEBUG:
        return ["*"]
    if settings.CORS_ORIGINS.strip():
        return [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    return ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流（IP+user_id 双维度；位于 AdminAuth 外层防 token 喷射打穿鉴权层）
app.add_middleware(RateLimitMiddleware)

# Admin 强制鉴权（task11 批判⑥补强 + judge R1：管理前缀 fail-closed 401 壳 "40101"）
app.add_middleware(AdminAuthMiddleware)

# 幂等（/api/trade/ 前缀拦截；鉴权内层生效，匿名请求不占用幂等缓存）
app.add_middleware(IdempotencyMiddleware)

# 熔断打标（轻量，不拦截）
app.add_middleware(CircuitGuardMiddleware)

# Trace（融合 Auth：trace_id 生成 + X-Trace-Id 透传 + 慢查询日志）
# S1（judge 裁定）：Trace 保持在 RateLimit/AdminAuth 外层——限流 429 与鉴权 401
# 短路响应均携带 X-Trace-Id，跨域前端可读完整壳体（CORS 在更外层注入响应头）。
# 注册于 AdminAuth 之后（更外层），确保 AdminAuth 短路返回时 Trace 能注入 X-Trace-Id。
# Trace（在 AdminAuth 外层确保 401/429 短路响应携带 X-Trace-Id）
app.add_middleware(TraceMiddleware)

# 响应壳兜底（白名单跳过 SSE/文件流）
app.add_middleware(RespWrapMiddleware)


# ── 全局异常处理 ──
def _jsonable(v: Any) -> Any:
    """递归把任意对象转为 JSON 可序列化形态。"""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return str(v)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """业务层 AppException → {code, message, data:null}"""
    detail = exc.detail if settings.DEBUG else None
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "data": detail},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTPException → {code, message, data:null}（R4：默认码查 STATUS_TO_CODE 单一事实源）"""
    status_code = exc.status_code or 500
    detail = exc.detail
    default_code = STATUS_TO_CODE.get(status_code, "50000")
    if isinstance(detail, dict):
        code_val = detail.get("code", default_code)
        message_val = detail.get("message", str(detail))
    else:
        code_val = default_code
        message_val = str(detail) if detail is not None else f"HTTP {status_code}"

    return JSONResponse(
        status_code=status_code,
        content={"code": code_val, "message": message_val, "data": None},
        headers=exc.headers if exc.headers else None,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 校验失败 → {code: 42200, message, data: null}"""
    errors = exc.errors()
    first_msg = "参数校验失败"
    if errors:
        first = errors[0]
        raw_msg = first.get("msg") if isinstance(first, dict) else str(first)
        loc = first.get("loc") if isinstance(first, dict) else None
        field_path = ""
        if isinstance(loc, list) and loc:
            tail = [str(x) for x in loc if x != "body"]
            if tail:
                field_path = ".".join(tail) + "："
        first_msg = f"{field_path}{raw_msg}" if raw_msg else first_msg
    return JSONResponse(
        status_code=422,
        content={
            "code": "42200",
            "message": first_msg,
            "data": _jsonable(errors) if settings.DEBUG else None,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """兜底异常 → {code: 50000, message, data: null}"""
    logger.exception(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": "50000",
            "message": "服务内部错误，请稍后重试",
            "data": str(exc) if settings.DEBUG else None,
        },
    )


# ── 注册业务路由（新增模块按依赖顺序追加） ──
app.include_router(health.router)                    # 健康检查
app.include_router(monitoring_router)                # Prometheus 指标 /metrics（P1-2）
app.include_router(auth_router)                      # 鉴权（注册/登录/刷新/me）—— 新增

from app.knowledge.routers import router as knowledge_router
app.include_router(knowledge_router)                 # 知识库导入/检索（P1）

from app.curriculum.router import router as curriculum_router
app.include_router(curriculum_router)                  # 旧课程路由 → 308 重定向（task11）
from app.domains.course.router import router as course_router
app.include_router(course_router)                      # 课程域 C 端 5 端点（task11 契约冻结②）
from app.users.router import router as users_router
app.include_router(users_router)                       # 用户画像（P0-P 步骤4）—— 新增
from app.chat.router import router as chat_router
app.include_router(chat_router)                        # AI 问答（P2 用户端 RAG）
from app.admin.rag_admin.router import router as rag_admin_router
app.include_router(rag_admin_router)                   # 管理端 RAG 控制台（P7 路径 B）

from app.domains.course_admin.router import router as course_admin_router
app.include_router(course_admin_router)                # 管理端 课程管理 CRUD（task12）
from app.domains.question_admin.router import router as question_admin_router
app.include_router(question_admin_router)              # 管理端 题库管理（task13 重写：edu.sql question_bank/question）
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
from app.domains.market.router import coupon_router as market_coupon_router
from app.domains.market.router import favorite_router as market_favorite_router
app.include_router(market_coupon_router)                           # 优惠券（task16 契约⑦）
app.include_router(market_favorite_router)                         # 课程收藏（task16 契约⑦）
from app.domains.trade.order.router import router as order_router
app.include_router(order_router)                                   # 订单/交易（task17 契约⑧）
from app.domains.trade.payment.router import router as payment_router
app.include_router(payment_router)                                 # 支付/交易（task18 契约⑨）
from app.domains.trade.refund.router import router as refund_router
from app.domains.trade.refund.router import admin_router as refund_admin_router
app.include_router(refund_router)                                  # 退款/交易（task19 契约⑩）
app.include_router(refund_admin_router)                            # 退款审批 stub（task19 HITL 预留）
from app.domains.enrollment.router import router as enrollment_router
app.include_router(enrollment_router)                              # 报名/我的班次（task20 契约⑪前段）
from app.domains.learning.router import router as learning_router
app.include_router(learning_router)                                # 学习/study（task21 契约⑪task21段）
from app.domains.after_sales.router import router as after_sales_router
app.include_router(after_sales_router)                             # 售后工单（task22 契约⑫）
from app.mcp.router import router as mcp_router
from app.ai.memory.router import router as memory_router
app.include_router(mcp_router)                                     # MCP 导入与集成（P8：server 注册/import/工具列表/测试/日志，管理员专用）
app.include_router(memory_router)                  # 记忆事件溯源/回滚/历史/Dream（task-M1，纯增量端点）
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
