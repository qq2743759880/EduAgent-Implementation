调研完成。我已通读 `app/main.py`（中间件链）、`app/database.py`（fetch_one/execute_write/transaction/RO 池/6 存储）、`app/common/*`（限流/鉴权/安全头）、`app/chat/*`（LangGraph 1.2 agent、三通道检索、生成器、MCP 启发式调用）、`app/knowledge/*`（embedder/chunker/loader/retriever）、`app/mcp/*`（registry/executor）、以及 `E:\stu\project\stu\edu-data\sql\edu.sql`（66 张表全量 schema）和 full 档数据生成配置（10 万用户/8 万订单）。以下是重构技术架构设计报告。

---

# EduAgent 后端重构技术架构设计报告

> 调研对象：`E:\stu\project\stu\EduAgent实施手册\edu-agent`（Python 3.11 + FastAPI + LangGraph 1.2 + Milvus + Neo4j + Redis + MySQL(asyncmy) + MongoDB + MinIO）
> 权威数据源：`E:\stu\project\stu\edu-data\sql\edu.sql`（66 张业务表），full 档：10 万用户 / 8 万订单 / 8 万曝光日志
> 对标体系：字节 CloudWeGo（Kitex/Hertz/Sonic/Eino）分层与性能工程、腾讯 Polaris 服务治理、Anthropic 多智能体研究体系与 Contextual Retrieval、LangGraph durable execution
> 性质：只读调研报告，不修改任何文件；交付形态为 Markdown 纯文本

---

## 0. 现状诊断摘要（重构的"为什么"）

### 0.1 现状盘点

| 维度 | 现状（代码实证） | 结论 |
|---|---|---|
| 分层 | 全部业务模块均为 `router.py → service.py（内联 SQL）→ schemas.py`，无 repository 层；SQL 与业务逻辑混合（如 `app/users/service.py` 直接拼 SQL） | 需补 repository 层 |
| 数据库 | `app/database.py` 已有：asyncmy 主池 + **只读池**（`_get_read_pool` 降级）、信号量并发闸、`fetch_one/fetch_all`（走 RO 池）、`execute_write`（走主池）、`transaction()` CM；慢查询阈值 SELECT 200ms / 写 500ms | 读写分离底座已具备，可直接对齐 |
| 响应壳 | **不一致**：异常 handler 返回 `{code,message,detail}`（`app/main.py:206-304`），成功响应返回裸 Pydantic 模型或 `{"ok":...}`（`app/users/router.py`） | 统一 `{code,message,data}` 是必做项 |
| Redis | 仅用于限流（`rate_limit.py`）+ 健康检查；**无业务缓存层**；无幂等/熔断/缓存防护 | 缓存层从 0 建 |
| 中间件 | SecurityHeaders → CORS → Auth（trace_id 8 位 uuid + 白名单 + 指标）→ RateLimit（滑动窗口：auth 10/min、chat 20/min、admin 200/min、default 100/min）→ RequestLogging | 缺：链路追踪贯穿、熔断、幂等、缓存防护 |
| AI Agent | `app/chat/flows/langgraph_agent.py`：单 agent 循环（decision→retrieve/tool→generate，≤3 轮）；`agent_graph.compile()` **无 checkpointer**（thread_id 传了但不持久化）；`retrieve_node`/`tool_node` 内 `user_id=1` **硬编码 TODO**；无子代理、无记忆、无压缩 | 需 orchestrator-worker 重构 |
| RAG | 三通道（Milvus dense+sparse RRF + Neo4j 图谱）+ `_rule_rerank` 规则重排 + 断崖截断；**`RERANKER_PATH=bge-reranker-v2-m3` 已配置但未接入检索链路**（`chat/retriever.py:308-309` 注释明示"统一走规则兜底"）；chunker 纯文本切分，**无 contextual prefix**；HyDE 是静态同义词表（非 LLM） | 需补 rerank 接入 + Contextual Retrieval |
| MCP | registry（DB CRUD + tools/list discover upsert）+ executor（stdio 帧协议/SSE，含超时）+ 启发式工具选择（`chat/tool_calling.py`）；**无工具描述质量审查** | 需描述自动审查重写 |
| 业务域 | 交易（coupon/order/payment/refund）、报名（student_cohort_rel）、学习（attendance/video_play/submission）、售后（service_ticket/risk）**均无业务代码**，但 edu.sql 66 表已全部定义 | 按域新建，直接映射 edu.sql |

### 0.2 核心架构决策：模块化单体（Modular Monolith），不拆微服务

**选型理由（对标字节/腾讯，但不盲从）**：
- 字节 5 万+ 微服务（Kitex RPC + Hertz + Polaris 治理）的成立前提是**海量团队并行开发与独立扩容**；本项目是单体 FastAPI 教育平台，团队规模、流量（full 档 8 万订单）均不支持微服务化的运维成本（注册中心、RPC 序列化、分布式事务、链路治理 ×N）。
- 采纳其**分层思想与治理思想**（Kitex 的 handler→service→repo 分层、Polaris 的熔断/限流模式），落地为**单进程内强分层 + 领域模块边界 + Redis 作服务治理载体**，未来某域（如交易）需要独立扩容时可按域切开。
- 全异步栈继续保留：asyncmy + motor + redis.asyncio + asyncio 事件循环，与 FastAPI 天然匹配；Sonic（字节 JSON JIT+SIMD）的启示是"序列化开销要抠"，本项目对应选型是 pydantic v2（rust core）+ `model_dump(mode="json")` 而非引入新依赖。

### 0.3 重构总目标与验收指标

| 目标 | 指标 | 验证方式 |
|---|---|---|
| 响应壳统一 | 100% HTTP 响应为 `{code,message,data}`（SSE 事件除外） | 契约测试遍历全部 router |
| 交易一致性 | 订单/支付/退款零重复入账（幂等）；状态机非法迁移率 = 0 | 并发压测 + 状态机单测 |
| AI 助手升级 | 意图路由准确率 ≥ 现有基线；P95 延迟 ≤ 8s（流式首包 ≤ 3s）；compaction 后上下文 ≤ 6k token | LLM-as-judge 评估集 + 延迟分位监控 |
| RAG 召回 | 接入 bge-reranker-v2-m3 后 top-20 命中率较规则重排提升（目标 ≥ +15%） | rag_evaluator 离线评估集 |
| 容灾 | 任一外部存储（Milvus/Mongo/Redis/Neo4j/MinIO/LLM）宕机时核心链路不 500 | 故障注入演练 |

---

## 1. 分层架构设计

### 1.1 分层模型（对齐 Kitex 分层 + 现有 fetch_one/execute_write 底座）

```
┌────────────────────────────────────────────────────────────┐
│ Router 层  （HTTP 适配：参数校验、鉴权 Depends、响应壳包装）    │
│   router.py  ──只做──►  request → service → RespModel        │
├────────────────────────────────────────────────────────────┤
│ Service 层 （业务编排：事务边界、领域规则、跨 repository 组合）  │
│   service.py ──持有──► transaction() 边界                    │
├────────────────────────────────────────────────────────────┤
│ Repository 层（数据访问：SQL 组装 + 缓存旁路，逐表一个类）      │
│   repository.py ──调用──► fetch_one/fetch_all/execute_write  │
├────────────────────────────────────────────────────────────┤
│ Infra 层  （app/database.py 现有底座：连接池/事务/慢查询监控）  │
│   + cache.py（Redis 缓存层）/ lock.py（分布式锁）/ idempotency │
└────────────────────────────────────────────────────────────┘
```

**为什么是"router→service→repository→infra"四层而不是五层（含 dao）**：现有 `fetch_one/execute_write` 已经是参数化 SQL 直连底座，其定位就是 DAO 基础设施；再加一层纯转发的 dao 层只会增加 66 张表的样板代码。Kitex 的多层（handler→service→usecase→repo→dao）对应的是"RPC 协议适配 + 多业务组合"场景，本项目 service 层承担 usecase 职责即可。

### 1.2 事务边界策略（对齐现有 transaction() 体系，红线保留）

沿用 `app/database.py` 的硬约束并制度化：
1. **单语句**：`execute_write()` / `fetch_one()` / `fetch_all()`（各自独立连接自动提交）。
2. **多语句原子**：`async with transaction() as (conn, cur):`，事务内**只允许**用共享 `cur` 执行，禁止嵌套 `execute_write()`（task04 #1 已踩过的坑，写进 lint 规则与 CR 清单）。
3. **事务只包最小范围**：LLM 调用、Redis、Milvus、MinIO、Neo4j 一律在事务外；事务内只做 MySQL 行操作，超时预算 1s 内。
4. **领域事件后置**：事务提交成功后才发事件（写 Redis Stream / 任务队列），避免"事务回滚但消息已发"。
5. **跨域一致性**：订单→报名→优惠券核销属"写多表单库"，用**单事务 + 状态机 + 唯一键幂等**，不引入分布式事务（选型理由：单 MySQL 实例，Saga/Outbox 的复杂度收益为负；对账任务兜底）。

### 1.3 app/ 目录重构结构树（设计到目录级，开发可直接照做）

```
app/
├── main.py                     # 入口：中间件注册顺序、路由聚合（瘦身，只做装配）
├── config.py                   # 现有 pydantic-settings，增补新域配置
├── database.py                 # 【保留】infra 底座：6 存储连接池 + fetch_*/execute_write/transaction
│
├── core/                       # 【新增】框架层（替代散落的 common 基建）
│   ├── resp.py                 # RespModel {code,message,data} + ok()/fail() 工具
│   ├── cache.py                # Redis 缓存分层封装（穿透/击穿/雪崩防护，见 §6.1）
│   ├── lock.py                 # Redis 分布式锁（SETNX + Lua 释放）
│   ├── idempotency.py          # 幂等键存取（中间件用）
│   ├── breaker.py              # Polaris 式熔断器（见 §2.3）
│   ├── trace.py                # trace_id/span ContextVar 贯穿（见 §2.2）
│   ├── queue.py                # Redis 任务队列（削峰，见 §3.6/§6.4）
│   └── crud_mixin.py           # Repository 基类（表名/软删 yn=1 过滤/分页 keyset）
│
├── common/                     # 【保留】安全头/CORS 相关 + 异常体系
│   ├── security_headers.py
│   ├── request_logging.py
│   ├── exceptions.py           # 保留，AppException 与 {code,message} 对齐
│   └── error_codes.py          # 扩充分域段码（见 §1.5）
│
├── middleware/                 # 【新增】集中管理（从 main.py 抽离）
│   ├── auth_middleware.py      # 现 app/common/auth.py 迁入
│   ├── rate_limit.py           # 现 app/common/rate_limit.py 迁入 + 双维度
│   ├── trace_middleware.py     # 【新增】trace 贯穿（§2.2）
│   ├── circuit_breaker.py      # 【新增】依赖熔断（§2.3）
│   └── idempotency.py          # 【新增】幂等中间件（§2.5）
│
├── domains/                    # 【新增】业务域根（按 DDD 聚合，对齐 edu.sql）
│   ├── auth/                   # 现有 app/auth 迁入（JWT/双 token/角色）
│   ├── user/                   # 现有 app/users 迁入 + sys_user/student_profile repository
│   ├── course/                 # 【重构】课程域：series/cohort/cohort_course/session/asset/video
│   │   ├── router.py / schemas.py
│   │   ├── service.py          # 上下架状态机、班次容量校验
│   │   └── repository.py       # series_repo / cohort_repo / session_repo / video_repo
│   ├── question/               # 【重构】题库域：question_bank/question/组卷关系
│   ├── trade/                  # 【新建】交易域（§1.4）
│   │   ├── coupon/             # coupon 核销状态机、领券限流
│   │   ├── order/              # 下单/取消/状态机
│   │   ├── payment/            # 支付回调幂等、对账
│   │   └── refund/             # 退款申请→审批(HITL)→退款
│   ├── enrollment/             # 【新建】报名域：student_cohort_rel（满班并发控制）
│   ├── learning/               # 【新建】学习域：attendance/video_play(_event)/homework_exam_submission
│   ├── after_sales/            # 【新建】售后域：service_ticket/follow/satisfaction + 人工申诉
│   ├── risk/                   # 【新建】风控域：risk_alert_event/disposal + ugc_moderation
│   └── settlement/             # 【新建】结算域：teacher_compensation/channel_commission（二期）
│
├── ai/                         # 【重构】AI 助手（现 app/chat 升级，§3）
│   ├── agents/                 # lead/检索/工具/学习规划/闲聊 子代理定义
│   ├── graph.py                # LangGraph 编排图（plan→fanout→merge→reflect→answer）
│   ├── memory/                 # 三层记忆（§3.4）
│   ├── compaction.py           # 上下文压缩（§3.5）
│   ├── router.py / service.py / schemas.py   # 会话/消息持久化（现有逻辑保留）
│   └── tool_specs.py           # 工具清单 + 描述规范（§3.7）
│
├── rag/                        # 【重构】RAG（现 app/knowledge，§4）
│   ├── retriever/              # 三通道 + rerank 接入 + 断崖
│   ├── reranker.py             # 【新增】bge-reranker-v2-m3 接入（懒加载+降级）
│   ├── contextualize.py        # 【新增】写入时 contextual prefix 生成
│   └── importer/               # 现有 pipeline/chunker/embedder/loader/graph_builder 保留
│
├── mcp/                        # 【保留+增强】registry/executor + description_reviewer（§5）
├── admin/                      # 现有管理端四模块保留（rag/course/question/user）
├── interactive/                # 现有 quiz/vocab/coding/math 保留
├── community/ gamification/ recommender/ mindmap/ progress/ curriculum/
│                               # 现有模块保留（二期迁入 domains/ 或按域拆分）
├── monitoring/                 # 现有 Prometheus 指标 + 新增 trace/熔断指标
├── routers/                    # 现有 health 保留
└── services/                   # 现有 minio_uploader 保留；预留 embedding/reranker 独立服务位
```

**迁移策略（不破坏现有功能）**：先 `core/` + `middleware/` 底座落地 → 交易/报名/学习/售后四个新域**直接按新结构新建**（零迁移成本）→ 存量模块（chat/knowledge/users）在各自重构任务中逐步迁入（router 路径不变，对外 API 兼容）。

### 1.4 交易域/课程域/题库域模块划分（对齐 edu.sql 66 表）

**交易域（trade）**——表映射与状态机：

| 子模块 | edu.sql 表 | 核心状态机 | 并发/一致性要点 |
|---|---|---|---|
| coupon | `coupon`、`coupon_category_rel`、`coupon_series_rel`、`coupon_receive_record` | receive_status: unused→used/expired | 领券防超发：`UPDATE coupon SET receive_count=receive_count+1 WHERE id=? AND receive_count < total_count`（条件更新，受影响行数=0 则失败）；receive_no 唯一键幂等 |
| order | `` `order` ``、`order_item`、`shopping_cart_item` | order_status: pending→paid→completed / cancelled / partial_refunded→refunded | 下单 = order+order_item 单事务；order_no 唯一键（institution_id,order_no）幂等；金额 DECIMAL(12,2) 服务端重算，**不信任前端传入价格** |
| payment | `payment_record` | payment_status: pending→paid/failed/closed→partial_refunded/refunded | 回调幂等：payment_no 唯一键 + 状态机条件更新（`WHERE payment_status='pending'`）；支付成功→订单 paid→报名 active→优惠券 used 单事务落库 |
| refund | `refund_request` | refund_status: pending→approved/rejected→refunded | 审批 HITL（LangGraph interrupt，§3.9）；退款金额 ≤ 订单已付金额校验；refund_no 唯一键 |

**课程域（course）**：`series`（sale_status: draft/on_sale/off_sale 状态机）、`series_cohort`（满班条件更新 `current_student_count < max_student_count`）、`series_cohort_course`、`series_cohort_session`（teaching_status: scheduled/in_progress/completed/cancelled）、`session_asset/session_video/session_video_chapter`（MinIO 对象 URL + transcode_status 状态机）。**查询侧**：课程详情走 Redis 热点缓存（§6.1），列表走 RO 池。

**题库域（question）**：`question_bank`、`question`（options_json/answer_text/analysis_text）、`session_homework_question_rel`、`session_exam_question_rel`。要点：题目编辑版本化（软删 + 新行，不物理改）、组卷快照（考试发布时复制题目快照，防止考试中题目被改）。

### 1.5 响应壳统一 `{code, message, data}`

**选型理由**：教育平台前端是同一团队，可一次性统一；字节/腾讯内部网关均为统一包裹（{code,message,data} 是字节 API 网关标准壳），避免前端两套解析逻辑（现状已造成 `{"ok":true}` 与 `{code,message}` 混用）。

```python
# app/core/resp.py（伪代码）
class RespModel(BaseModel):
    code: int = 0          # 0=成功；错误码分段见 error_codes
    message: str = "ok"
    data: Any = None

def ok(data=None, message="ok") -> dict:
    return {"code": 0, "message": message, "data": data}

# router 写法统一：
@router.get("/{series_id}")
async def get_series(...) -> dict:
    return ok(await course_service.get_series(series_id))
```

- 错误码分段（沿用现有 `_http_status_for_code` 约定并扩展）：`400xx` 参数/业务规则、`401xx` 未认证、`403xx` 越权、`404xx` 不存在、`409xx` 冲突、`422xx` 校验、`429xx` 限流、`5xxxx` 服务端。新增域段码：交易 `4xx2x`（如 40920 订单已支付）、售后 `4xx3x`、学习 `4xx4x`。
- **兼容策略**：`app/main.py` 全局 handler 已产出 `{code,message,detail}`，保留 `detail` 字段仅在 DEBUG 下返回（现有逻辑不动）；成功侧通过一个 `RespWrapMiddleware`（或在 router 层逐点改造）包成 `{code:0,message:"ok",data:<原对象>}`。**推荐逐点改造**（router 层改 `return ok(...)`，工作量可控且类型安全），中间件包裹作为过渡兜底（对未改造端点自动包装，白名单跳过 SSE/文件流端点）。
- SSE 流式端点（`/api/chat/stream`）例外：事件流保持 `event:` 结构，但 `done` 事件与 `error` 事件内嵌 `{code,message,data}` 壳。

### 1.6 技术选型表（每项带理由）

| 选型 | 选择 | 理由（为什么用它、不用什么） |
|---|---|---|
| 架构形态 | 模块化单体 + 领域模块 | 团队规模/流量不支持微服务运维成本（字节 5 万微服务需注册中心+RPC+全链路治理）；单 MySQL 实例下分布式事务是负收益；但按域切目录为未来拆分留缝 |
| 数据库访问 | asyncmy 原生 SQL + repository 层 | 现有 fetch_one/execute_write 体系已成熟（含 RO 池/并发闸/慢查询），66 表 CRUD 用 ORM（SQLAlchemy）收益低且迁移风险大；repository 只做 SQL 归口，不引入新引擎 |
| 读写分离 | 保留 RO 池 + `_get_read_pool` 降级 | 现状已实现（`database.py:146-183`），full 档 8 万订单下报表/列表查询可显著减压主库；RO 账号 `GRANT SELECT` 双保险 |
| 缓存 | Redis 单机/主从（现状 redis.asyncio 池） | 规模不需要 Cluster；LangGraph Redis checkpointer 同实例共用，运维面小 |
| 响应壳 | `{code,message,data}` | 团队统一 + 对齐大厂网关惯例；消除现状双格式 |
| Agent 框架 | LangGraph 1.2（保留）+ Redis checkpointer + 手写子代理编排 | Eino（字节）生态在 Go；LangGraph 已有资产（图/节点）与 Python 栈契合；checkpointer 补齐 durable execution（现状缺失） |
| 模型服务 | 本地 BGE-M3 + bge-reranker-v2-m3（已下载），LLM 走 OpenAI 兼容 API | 不重复造轮子；多 worker 下 GPU 模型共享问题见薄弱点 W3 |
| 任务队列 | Redis List（BLPOP）+ 状态表 | full 档批量任务规模（导入/报表/日志落库）用 Redis 足够；不引入 Celery/RabbitMQ 避免运维负担 |
| JSON 序列化 | pydantic v2（rust core） | 对标 Sonic 的"序列化开销抠到极致"理念，不新增依赖 |
| 链路追踪 | 自研 trace_id + span ContextVar（不引入 OpenTelemetry 全套） | 单体场景 OTel 采集器/Agent 运维成本 > 收益；预留 W3C traceparent 格式便于未来接入 |

---

## 2. 中间件规划

### 2.1 现状中间件盘点（`app/main.py:181-202`）

| 中间件 | 现状职责 | 重构动作 |
|---|---|---|
| SecurityHeaders | 安全响应头（CSP/HSTS 等） | 保留不动 |
| CORS | 开发 `*`/生产白名单 | 保留 |
| AuthMiddleware | trace_id（8 位）+ 公开路径白名单 + 指标 + 访问日志 | 升级为 TraceMiddleware 承载，鉴权过滤职责保留 |
| RateLimitMiddleware | Redis 滑动窗口按 IP | 保留 + 双维度（IP+user_id）+ 新域档位 |
| RequestLogging | 非 2xx 请求体脱敏 | 保留 |

### 2.2 TraceMiddleware：trace_id 全链路贯穿

**现状问题**：8 位 uuid 只在 HTTP 层存在，LLM 调用（`generator.py`）、MCP 调用（`tool_calling.py` 传的是 `mcp-chat-{ts}` 自制 id）、SQL 慢查询日志（`database.py` 的 `_log_slow_query`）都不带同一 trace_id，排障靠猜。

**设计**（对标腾讯北极星/字节链路追踪的"贯穿"思想，单体落地版）：

```python
# app/core/trace.py（伪代码）
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
span_id_var:  ContextVar[str] = ContextVar("span_id", default="")

def start_span(name: str):        # 子 span：LLM/MCP/Milvus/Redis/MySQL 调用点
    # 进入时 push 栈 + 生成子 span_id，退出时 pop；span 元数据（耗时）随日志输出
    ...

class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 1) 透传优先：上游 Nginx/前端传 X-Trace-Id 则沿用（W3C traceparent 兼容），否则生成
        tid = request.headers.get("X-Trace-Id") or f"{uuid4().hex[:16]}"
        trace_id_var.set(tid)
        # 2) 响应头回传 X-Trace-Id（现状已有，保留）
        # 3) 结构化日志统一带 trace_id（现有 loguru 绑定字段，保留）
```

**落地点**（改 3 处即可贯穿）：
- `database.py::_log_slow_query` 增加 `trace_id=get_trace_id()` 入日志；
- `generator.py::_ChatClient.call_chat(_stream)` 已在记录 trace_id，保持；MCP executor 的 `call_tool(trace_id=...)` 改为从 contextvars 自动取；
- Prometheus 增加 `edu_trace_spans_total{name,status}`。

### 2.3 CircuitBreaker：Polaris 式熔断器

**选型理由**：北极星熔断器模型（closed→open→half-open + 错误率/慢调用率阈值）是最成熟的国内工程实现；本项目按"每个外部依赖一个熔断器"落地，复用现有 `degraded_reason` 降级通道，无需新建降级框架。

**熔断对象**：`milvus` / `neo4j` / `mongodb` / `redis` / `llm` / `minio` / 每个 `mcp_server`（per-server，粒度最细）。

```python
# app/core/breaker.py（伪代码，Polaris 三态模型）
@dataclass
class BreakerConfig:
    min_requests: int = 20          # 统计窗口最小样本量
    error_rate_threshold: float = 0.5   # 错误率阈值（北极星默认 50%）
    open_duration: float = 30.0     # open 持续时间
    half_open_probes: int = 3       # 半开探针数

class CircuitBreaker:
    state: Literal["closed", "open", "half_open"]
    async def call(self, name: str, fn, *args, **kw):
        # closed: 直接调用；记录成败（Redis HINCRBY + 窗口），错误率超阈值 → open
        # open:   快速失败，抛 CircuitOpenError（调用方捕获 → degraded_reason="Milvus 熔断中"）
        # half_open: 放行探针请求，成功数≥探针数 → closed；任一失败 → open
```

- 状态共享：Redis Hash（多 worker 共享）`breaker:{name}`，本地内存做一级缓存（100ms 刷新）减少 Redis 压力。
- **与现有降级链路的接缝**：`retriever.py` 的三通道、`generator.py` 的 LLM 兜底已经"捕获异常→degraded_reason"，熔断器在异常之上提供**快速失败**（不再等待 8s Milvus 超时），显著改善最坏延迟。
- 指标：`edu_breaker_state{name}` Gauge → Grafana 告警。

### 2.4 限流分级（现状保留 + 双维度 + 新域档位）

现状分级已对齐行业实践（作业帮/猿辅导/黑马基准，`rate_limit.py:39-47`），补三点：

| 档位 | 现状 | 增补 | 维度升级 |
|---|---|---|---|
| auth | login 10/min、register 5/min、refresh 30/min | 增加验证码/短信发送 3/min | IP + user_id 双 key（登录接口取两者更严） |
| chat | 20/min | 增加 **并发会话数 ≤ 2/用户**（Redis 计数，防单用户占满 LLM 预算）；stream 与非 stream 分计 | 同上 |
| admin | 200/min | 不变 | 增加角色豁免（ADMIN 走独立 key，防被 IP 池误伤） |
| default | 100/min | **新增交易档**：`/api/trade/order/create` 10/min、`/api/trade/payment/*` 30/min、`/api/trade/refund/apply` 5/min（防脚本刷单/滥用退款） | IP 为主 |
| 基础设施 | health/metrics/docs 跳过 | 不变 | — |

实现保留现有滑动窗口（理由：固定窗口有边界双倍突发问题，令牌桶需维护令牌状态，滑动窗口 INCR+EXPIRE 在 Redis 下实现最简且多 worker 安全——现状注释已论证，不改算法）。

### 2.5 IdempotencyMiddleware：订单/支付防重

**设计**：`Idempotency-Key` 请求头（或 body 内 `idempotency_key` 字段）→ Redis SETNX 登记 → 命中重复则返回首次缓存响应。

```python
# app/middleware/idempotency.py（伪代码）
IDEMPOTENT_PREFIXES = ("/api/trade/order", "/api/trade/payment", "/api/trade/refund",
                       "/api/trade/coupon/receive", "/api/after_sales/ticket")

class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not request.url.path.startswith(IDEMPOTENT_PREFIXES):
            return await call_next(request)
        key = request.headers.get("Idempotency-Key")
        if not key:                                   # 无幂等键：放行（写接口文档强制）
            return await call_next(request)
        rkey = f"idem:{request.state.user_id}:{key}"
        # SET NX EX 86400；成功 → 执行业务，响应 JSON 缓存 24h（写 session 内）
        # 失败（已存在）→ 返回缓存的首个响应（含相同 order_no，语义幂等）
```

**三层幂等纵深**（不单靠中间件）：
1. 中间件：拦截重复请求（网络重试场景）；
2. 唯一键：`receive_no/order_no/payment_no/refund_no/ticket_no` 已建唯一索引（edu.sql 权威），重复插入抛 `DuplicateKey` → 转 `409xx` 并**回查返回原记录**（幂等成功而非报错）；
3. 状态机条件更新：`UPDATE ... WHERE status='pending'`，受影响行数 0 说明已被并发处理。

### 2.6 缓存穿透/击穿/雪崩防护（中间件 + 装饰器双层）

| 问题 | 防护 | 实现位置 |
|---|---|---|
| 穿透（查不存在数据直达 DB） | 空结果缓存 30s（`"null"` 哨兵值） | `core/cache.py::get_or_load` |
| 击穿（热点 key 过期瞬间并发重建） | SETNX 互斥重建 + 逻辑过期（旧值兜底续期） | 同上（见 §6.1 伪代码） |
| 雪崩（大量 key 同时过期） | TTL 随机抖动 ±10%：`ttl = base * (1 + random.uniform(-0.1, 0.1))` | 同上 |

不做中间件级泛化（缓存读写是业务语义，装饰器/显式封装比"猜每个请求该不该缓存"可靠——这是对"CacheProtection 中间件"题目的诚实技术回答：**实现为 `core/cache.py` 库 + 领域内显式调用**，中间件仅用于幂等/限流这类无业务语义的横切关注点）。

### 2.7 中间件注册顺序总表（后注册先执行）

```
SecurityHeaders → CORS → Trace(融合 Auth 白名单) → Idempotency →
RateLimit → CircuitGuard(轻量,仅打标不拦截) → RequestLogging → 业务路由
```

---

## 3. AI 助手 Agent 架构改造方案（重点）

### 3.1 现状 → 目标总览

| | 现状（langgraph_agent.py + agent.py） | 目标 |
|---|---|---|
| 拓扑 | 单 agent 循环：decision → retrieve/tool → generate（≤3 轮） | orchestrator-worker：routing → plan → 并行子代理 → merge → reflect → answer |
| 意图 | 4 类（知识检索/工具/学习建议/闲聊）JSON 决策 | 保留 4 类**路由前置**（快模型），复杂任务进入规划 |
| 持久化 | 无 checkpointer（thread_id 空转） | LangGraph Redis checkpointer + Store（durable execution） |
| 记忆 | 无（仅 chat_message 表历史窗口） | 三层记忆（working/short/long）+ 遗忘 |
| 上下文管理 | 历史窗口截断（include_history 轮数） | compaction 压缩 + 结构化笔记 |
| 工具调用 | 启发式正则优先 + LLM 兜底 | 函数调用规范 + 并行 + 熔断（§2.3/§3.7） |
| 硬编码 | user_id=1 TODO ×2 处 | state 注入真实身份 |

### 3.2 LangGraph 图节点设计（plan→search→tool→reflect→answer）

对齐 Anthropic Multi-agent Research System 的 orchestrator-worker 编排 + Building Effective Agents 的 workflow 组合（routing + parallelization + orchestrator-workers）：

```text
                        ┌──────────────────────────────┐
                        │  route_node（fast 模型，四类意图）│
                        └──────────────┬───────────────┘
         ┌──────────────────┬──────────┼───────────┬──────────────────┐
         ▼                  ▼          ▼           ▼                  ▼
   chitchat 子代理    knowledge     tool        learning         (直接 answer)
   （直接回答）         意图         意图         建议意图
                        │            │             │
                        ▼            ▼             ▼
                 ┌─────────────────────────────┐
                 │  plan_node（lead 规划任务清单）  │
                 │  输出: tasks[{agent, goal}]    │
                 └──────────────┬──────────────┘
                                │  fan-out（Send API / asyncio.gather 并行）
        ┌───────────────┬───────┴────────┬────────────────┐
        ▼               ▼                ▼                ▼
   search_agent    tool_agent      learning_agent    memory_agent
   （检索+引用）    （MCP 调用）     （画像+规划）     （记忆召回，可选）
        │ 各返回 1000-2000 token 蒸馏摘要 + artifact 轻引用   │
        └───────────────┬────────────────┴────────────────┘
                        ▼
                 ┌─────────────────────────────┐
                 │  merge_node（汇总/去重/冲突检测）│
                 └──────────────┬──────────────┘
                        ▼
                 ┌─────────────────────────────┐
                 │ reflect_node（LLM-as-judge） │── 信息不足且 iterations<MAX ──► plan_node（补充任务）
                 └──────────────┬──────────────┘
                        ▼
                 ┌─────────────────────────────┐
                 │  answer_node（强模型流式生成）  │ ──► END
                 └─────────────────────────────┘
```

**感知-行动-观察循环规则**：
1. **感知**（plan）：lead 读 route 结果 + 记忆三层摘要 → 输出任务清单（每任务：`agent 类型/目标/输入约束`），存 state.tasks；
2. **行动**（fan-out）：并行执行子代理；**独立任务必须并行**（Anthropic 实测 parallel tool calling 提速 90%）；
3. **观察**（merge）：汇总各子代理蒸馏摘要，做冲突检测（如检索结果与工具结果矛盾 → 标注冲突供 reflect 决策）；
4. **评估**（reflect）：LLM-as-judge 判断"是否足以回答用户"，输出 `sufficient: true/false` + 缺口描述；
5. 循环上限：`MAX_REFLECT_ITERATIONS = 2`（现状 3 轮循环经验值收紧，因子代理单轮完成度更高）；超限强制 answer 并标注 `degraded_reason="reflect_max_iter"`。

**Effort scaling 规则**（对齐 Anthropic "简单 1 agent 3-10 calls / 对比 2-4 agents / 复杂 10+ agents"）：

| 任务等级 | 判定 | 编排 | LLM 调用预算 |
|---|---|---|---|
| L0 easy | 闲聊/问候（route=chitchat） | 0 子代理，answer_node 直出（1 次 fast 调用） | 1 |
| L1 medium | 单知识点问答 | search_agent + graph 并行（2 子代理） | 2-4 |
| L2 hard | 学习规划/方法建议/多工具任务 | search + tool + learning 并行 + 1 轮 reflect | 5-8 |
| L3 complex | 跨学科综合/需要多轮信息补全 | fan-out 两次 + reflect 2 轮 | 10+（限流 20/min 内） |

### 3.3 Orchestrator-Worker 编排实现（伪代码）

```python
# app/ai/graph.py（伪代码骨架）
class AIState(TypedDict):
    messages: Annotated[list, add_messages]   # working memory
    route: str                                # knowledge/tool/learning/chitchat
    tasks: list[TaskSpec]                     # lead 计划
    artifacts: dict[str, str]                 # artifact_id -> 摘要/引用
    summary: str                              # compaction 后的对话摘要
    iterations: int
    final_answer: str

def build_ai_graph():
    g = StateGraph(AIState)
    g.add_node("route", route_node)          # fast 模型，输出 4 类之一
    g.add_node("plan", plan_node)            # lead：tasks 清单
    g.add_node("search", search_agent)       # 子代理
    g.add_node("tool", tool_agent)
    g.add_node("learning", learning_agent)
    g.add_node("merge", merge_node)
    g.add_node("reflect", reflect_node)      # LLM-as-judge
    g.add_node("answer", answer_node)        # 强模型流式
    # 条件边：route 按意图分发；L0 直连 answer
    # reflect: sufficient -> answer; insufficient & iter<2 -> plan
    return g.compile(
        checkpointer=AsyncRedisSaver.from_conn_string(settings.REDIS_URL),  # 补上缺失
        store=RedisStore(...),
    )

# 子代理范式（Anthropic 子代理蒸馏摘要规范）
async def search_agent(state) -> dict:
    docs = await retrieve_three_channel(...)      # §4 升级后的检索
    # 1) 完整 docs 写 artifact（Redis，TTL 1h），返回轻引用
    artifact_id = f"search:{uuid4().hex[:12]}"
    await redis.set(artifact_id, json.dumps([d.model_dump() for d in docs]), ex=3600)
    # 2) 返回 1000-2000 token 蒸馏摘要（关键结论 + 引用编号 + 置信度），不返回原文
    distilled = await llm_fast(SUMMARY_PROMPT, docs_text[:8000])
    return {"artifacts": {artifact_id: "search_result"},
            "report": distilled[:2000]}
```

- **Artifact 文件系统**（Anthropic 模式本地化）：完整检索原文/工具输出放 Redis（TTL 1h）或本地 JSON（`data/artifacts/{session_id}/`），图内只流转 1-2k token 摘要；answer_node 需要原文时按引用 JIT 拉取（just-in-time retrieval + progressive disclosure）。**选型理由**：Redis 版多 worker 共享、免磁盘清理；本地文件版适合工具输出大对象（代码执行结果），两者按大小分流。
- 子代理 LLM 全部用 `fast` 模型（qwen-flash），answer 用 `strong`（qwen-plus）——现状 config 已有双模型，仅需把生成路径从 fast 升级为 strong。

### 3.4 记忆体系三层划分

| 层 | 存储 | 内容 | TTL/容量 | 读写时机 |
|---|---|---|---|---|
| Working | LangGraph state（进程内 + Redis checkpoint 备份） | 本轮消息流、任务、摘要 | 单次运行 | 实时 |
| Short-term | Redis（`session:{sid}:history` + checkpointer）+ Mongo（现有 chat_message 保留） | 最近 N 轮对话（原文或压缩摘要） | 会话生命周期 / 7 天 | 每轮写，读取走 Redis 优先 |
| Long-term | ① MySQL 新表 `user_memory`（user_id, memory_type, content, importance, score, created_at, last_access_at） ② Milvus `user_memory` collection（向量记忆，user_id 分区） | 用户画像、偏好、纠错史、重要决策、知识盲点 | 长期 | 会话结束异步写；检索时双路召回 |

**记忆遗忘机制（LRU + 时间衰减 + 重要性评分）**：

```python
# 综合分：score = importance * exp(-λ * Δt_days) * recency_bonus
# importance: 规则打分（明确偏好+5 / 学习目标+4 / 纠错+3 / 普通事实+1）
#            或 LLM 打分（会话结束时用 fast 模型对候选记忆 1-5 分）
# 淘汰：长期记忆容量上限（如每用户 500 条）→ 综合分最低者淘汰（LRU 语义由 last_access_at 体现）
def decay_and_evict(user_id):
    rows = fetch_all("SELECT id, importance, last_access_at FROM user_memory WHERE user_id=%s", ...)
    for r in rows:
        score = r["importance"] * math.exp(-0.01 * (now - r["last_access_at"]).days)
        if score < 0.1:  soft_delete(memory_id)          # 遗忘
    if count > 500: evict_lowest_score(rows)             # LRU+衰减淘汰
```

- 向量记忆检索：用户 query 编码 → Milvus `user_memory` 分区检索 top-3 → 拼入 lead 的 plan prompt（"该用户上次提到…"）。
- 写入链路走 Redis 队列异步（不阻塞应答），对齐 §6.4 durable execution。

### 3.5 Compaction 上下文压缩（Context Engineering 落地）

**触发规则**（token 估算：中文 ≈ 1 字 1 token，`chunker._estimate_tokens` 已有实现可复用）：

| 触发条件 | 动作 |
|---|---|
| 工作消息流估算 > 6000 token | 触发压缩（在 plan_node 前） |
| 距离上次压缩后新增 > 3000 token | 再次触发 |
| 单条工具输出 > 1500 token | 立即蒸馏（不等待全量压缩） |

**保留规则**（Anthropic 结构化笔记 + 保留决策语义）：用户画像/偏好、未完成任务、已确认的决策、纠错记录 → 沉淀进 `state.summary`（结构化 JSON：`{profile_updates, pending_tasks, decisions, facts}`）。
**丢弃规则**：冗余工具输出（tool result clearing——工具原始 JSON 进 artifact，流内只留 1 行结论）、被更正的旧事实、寒暄、重复内容。

```python
# app/ai/compaction.py（伪代码）
async def maybe_compact(state) -> dict:
    if estimate_tokens(state.messages) < 6000:
        return {}
    summary = await llm_fast(COMPACT_PROMPT.format(
        old_summary=state.summary, recent_messages=tail(state.messages, 4000)))
    # 新消息流 = [SystemMessage(summary)] + 最近 K 条原始消息（K=6 轮）
    return {"messages": reset_messages(summary, tail_messages), "summary": summary}
```

### 3.6 Redis 防过载部署（LangGraph Redis 全家桶 + 削峰 + 限流 + 大 key 治理）

1. **LangGraph Redis checkpointer**：`AsyncRedisSaver`（每 superstep 存状态，thread_id 维度，断点续跑/会话恢复——补现状最大缺口）；
2. **任务队列削峰**：chat 请求先经信号量（全局 LLM 并发上限，如 8）+ 会话并发 ≤2（§2.4），超限请求进入 Redis List 排队（`chat:queue` BLPOP），**排队超时 10s 返回"当前咨询人数较多"** 而非堆积；
3. **会话限流**：`chat:concurrent:{user_id}` INCR/DECR 计数 + 20/min 滑动窗口（现状）双层；
4. **大 key 治理**：
   - 会话历史 `session:{sid}:history` 用 ZSET（按时间戳）分片存储 + 单次读取限 50 条；
   - checkpoint 状态按月清理（TTL 7 天）；
   - 监控 `redis_bigkey` 扫描任务（`MEMORY USAGE` 抽样），单值 >1MB 告警；
   - artifact 固定 TTL 1h（§3.3），杜绝无界增长。

### 3.7 Tool / Function-Calling 调用规则（ACI 原则）

**工具清单设计（ACI：Agent-Computer Interface）**——现状工具清单散在启发式正则（`tool_calling.py`）与决策 prompt 两处，重构后统一 `ai/tool_specs.py`：

```python
@dataclass
class ToolSpec:
    name: str            # snake_case 动词开头
    description: str     # 按 §5.2 规范重写后的描述
    input_schema: dict   # JSON Schema，required 明确
    risk: Literal["read","write"]        # 副作用分级
    parallel_safe: bool  # 无依赖工具可并行（asyncio.gather）
    timeout_s: float
    admin_only: bool
```

**工具描述撰写规范**（写入开发规范）：① 一句话说清"做什么+何时用"（含反面：何时不要用）；② 每个参数：语义 + 取值域 + 示例值；③ 返回结构说明；④ 1 个完整调用示例；⑤ 副作用/幂等性声明。理由：Anthropic 指出差工具描述浪费 40% 时间，且本项目启发式匹配依赖描述关键词（`_suggest_keywords` 从 name/desc 提取），描述质量直接决定命中率。

**并行工具调用规则**：plan 出的 tool 任务中，`parallel_safe=True` 且无参数依赖的一批 `asyncio.gather` 并发执行；有依赖的串行。`MCP_TOOL_MAX_TRIES`（现状默认 1）提升为"每任务重试 1 次 + 总工具调用 ≤ 4 次"。

### 3.8 CoT 与 Token 优化

| 手段 | 现状 | 动作 |
|---|---|---|
| System prompt 精简 | AGENT_SYSTEM_PROMPT ~800 token（`langgraph_agent.py:62-95`），RAG_SYSTEM_PROMPT 另计 | 目标各 ≤300 token：删示例冗余、决策规则表化；CoT 只保留"输出 JSON 前先给一句话理由" |
| Few-shot 精选 | AGENT_DECISION_PROMPT 4 例（`agent.py:76-87`） | 保留 4 例但压缩措辞；评估集驱动（LLM-as-judge 回放，移除低增益样例） |
| Prompt caching | 无 | **静态前缀稳定化**：system + 工具清单（按 name 排序固定）作为缓存前缀——DeepSeek context caching 命中后首 token 延迟与计费均降；路由/规划/反思三层复用同一前缀，命中率最大化 |
| 输出约束 | JSON 决策无 schema 校验 | 决策输出用 Pydantic 校验（`ToolPlan.model_validate_json`），非法输出走重试 1 次 → 保守回退（现状 `_safe_json_extract` 语义保留） |
| 流式 | SSE + queue 桥接（`generator.py:377-447`），首包超时 60s | answer_node 接现有流式管道；首包超时分级：10s 提示排队、60s 降级规则答案（现状逻辑保留） |
| 模型分级 | 决策 fast / 生成 fast | 生成升级 strong（qwen-plus），路由/规划/反思/子代理全部 fast |

### 3.9 Durable Execution（断点续跑 + HITL）

- **对话级**：Redis checkpointer（§3.6）保证任意节点崩溃后可 `ainvoke(config)` 从最近 checkpoint 恢复；
- **任务级**：导入/rebuild/批量报表任务走 Redis 队列 + MySQL `task` 状态表（`status: pending/running/succeeded/failed` + `progress_json`），worker 每批（200 条，§6.3）后落 progress；重入时跳过已完成批次（幂等靠 chunk_id upsert，loader 现状已支持）；
- **HITL**：退款审批用 LangGraph `interrupt()`/`Command(resume=...)`——`refund_request` 状态 `approved/rejected` 由人工在管理端确认后 resume 图，执行退款落库；超时（72h）自动升级工单（`service_ticket` priority=high）。

---

## 4. RAG 重构方案（对齐 Contextual Retrieval）

### 4.1 现状诊断（基于代码实证）

| Contextual Retrieval 要素 | 现状 | 缺口 |
|---|---|---|
| Contextual Embeddings（chunk 前置 50-100 token 上下文） | ❌ chunker 纯文本多策略切分（`chunker.py`），无上下文前缀 | 新增 contextualize 步骤 |
| 双路召回（dense + BM25） | ✅ Milvus dense（BGE-M3）+ sparse（jieba BM25 风格）+ RRF 融合（`loader.hybrid_search`） | 已达标（sparse 即 BM25 近似，Milvus 内融合） |
| Rerank | ⚠️ `RERANKER_PATH=bge-reranker-v2-m3` 已配置（`config.py:139`）但**未接入**，chat 链路统一走 `_rule_rerank` 规则重排（`chat/retriever.py:308-309`） | **接入 reranker** |
| 检索量级 top-150→rerank→top-20 | ❌ 现状 top_k=12/20 直接规则重排 → 5 | 提高召回量 + rerank |
| 标签/分区 | ✅ metadata tags（module_codes/keywords）+ partition 多租户 | 补课程域过滤条件 |

### 4.2 写入链路：chunk 上下文化（contextual prefix）

Anthropic Contextual Retrieval 公式落地（检索失败率降 67% 的关键）：

```python
# app/rag/contextualize.py（伪代码，插入 pipeline：chunker → 【contextualize】 → embedder）
CONTEXT_PROMPT = """<document>
{whole_document}
</document>
Here is the chunk we want to situate within the whole document:
<chunk>
{chunk_content}
</chunk>
Please give a short succinct context (50-100 tokens) to situate this chunk
within the overall document for the purposes of improving search retrieval.
Answer only with the succinct context and nothing else."""

async def contextualize_chunks(chunks, whole_doc) -> list[str]:
    # 1) 仅对"知识型"内容生成前缀（讲义/教材），题库/代码片段可跳过（规则判定）
    # 2) 并发度限制（如 8 并发）+ fast 模型 + 单 chunk 1 次调用（入库一次性成本）
    # 3) 失败降级：无前缀原 chunk 照常入库（与 embedder 的三级降级哲学一致）
    prefixes = await batch_llm([CONTEXT_PROMPT.format(...) for c in chunks])
    return [f"{p}\n{c.content}" for p, c in zip(prefixes, chunks)]
```

**embedder.py 是否需要改？不需要**——`encode_dense_batch`/`build_sparse_vector` 的输入是纯文本，contextual chunk 直接作为 content 传入即可；`chunk.content` 在原文档组装处（pipeline.py）替换为 contextual 版本，保留 `chunk.raw_content` 存原文用于 answer 展示。**入库量翻倍风险**：prefix 只进索引不进展示层，Milvus 存储预算按 +15% 规划。

### 4.3 检索链路：top-150 → rerank → top-20 → 断崖 → 5

```python
# app/rag/reranker.py（伪代码：把 RERANKER_PATH 真正接进链路）
_RERANKER_MODEL = None
def _get_reranker():
    # 懒加载 FlagEmbedding FlagReranker（bge-reranker-v2-m3），失败返回 None
    ...
def rerank(query: str, docs: list[RetrievedDoc], top_n: int = 20) -> list[RetrievedDoc]:
    model = _get_reranker()
    if model is None:
        return _rule_rerank(query, docs)[:top_n]     # 现状规则重排兜底（保留）
    scores = model.compute_score([[query, d.content] for d in docs], normalize=True)
    # 分数回写 → 排序 → top_n

# app/chat/retriever.py 改造点：
# 1) top_k: 12 → 150（Milvus hybrid_search 的 top_k 参数，RRF 融合后取 150）
# 2) _rule_rerank 调用点替换为 rag.reranker.rerank(query, merged, top_n=TOP_K_RERANK=20)
# 3) _cliff_cutoff(final_max_k=5) 保留（断崖是业务语义，rerank 后仍有效）
```

- 延迟预算：Milvus top-150 召回 ~100ms + rerank（GPU，16 条/批，150 条 ≈ 10 批）~300ms，总增量可控；`RERANKER_BATCH_SIZE=16` 现状配置直接复用；
- 评估闭环：`app/chat/rag_evaluator.py` 补 top-20 命中率指标，上线前跑离线评估集对比规则重排基线（目标 +15% 命中）；
- **多 worker 下的 reranker 模型加载**：每个 uvicorn worker 各加载一份 bge-reranker（~2.2GB）→ 见薄弱点 W3 的应对。

### 4.4 双路召回 + Contextual BM25

- dense+sparse RRF 现状保留（sparse 通道即 jieba BM25 风格，写入/查询同构：`_term_to_id` 确定性 hash）；
- Anthropic 的"contextual BM25"对应本项目 = **对 contextual chunk 文本做分词建 sparse**（sparse 向量同样基于 contextual 文本生成，天然获得上下文增益），无需另建 MySQL 倒排（P2 曾规划，评估后放弃：Milvus sparse 已覆盖且免双系统一致性）；
- 标签策略（metadata + 分区，对齐 Contextual Retrieval 的 metadata 用法）：
  - 检索过滤表达式：`series_code / module_codes / content_type / tenant_id`；
  - 分区：现状 `_default` + `user_{id}`（多租户）；新增 `course_public` 分区放**交易域课程知识**（与用户上传知识隔离，防止促销文案/班次信息污染学科问答）；
  - 写入时 `keywords` 标签已由 jieba.analyse 提取（`chunker._extract_keywords`），保留并扩展为"学科/学段/知识点"三级标签树。

---

## 5. MCP 重构方案

### 5.1 现状（P8 已落地，可用）

registry（DB CRUD + `tools/list` discover 批量 upsert，`registry.py:246`）、executor（stdio 帧协议 + SSE，超时/幂等 call_id/调用日志，`executor.py`）、管理端 router、chat 侧启发式选择。**评价：传输层扎实（Windows 子进程坑已填），缺"工具语义治理"层。**

### 5.2 工具描述质量自动审查与重写（对齐 Anthropic"描述质量浪费 40% 时间"教训）

MCP 协议是"USB-C"：接入容易，但**第三方 server 的工具描述质量参差**（现状 `upsert_discovered_tools` 原样存 description）。新增 `app/mcp/description_reviewer.py`：

```python
# 规则打分（0-100）：
#  +20 动词开头一句话说明用途        +15 明确"何时不该用"
#  +20 每个 input_schema 参数有说明   +15 有返回结构描述
#  +10 有示例                        +20 无歧义术语/缩写
def score_description(tool: dict) -> int: ...

async def review_and_rewrite(server_id: int, tools: list[dict]):
    for t in tools:
        score = score_description(t)
        if score < 70:
            # 用 fast 模型重写：输入 = 工具名 + input_schema + 原描述
            # 输出 = 符合 §3.7 五要素规范的描述（≤120 字）
            rewritten = await llm_fast(REWRITE_PROMPT, ...)
            # 存 mcp_tool.description_rewritten 列（新列，软迁移），
            # 工具选择/启发式关键词提取统一读 rewritten 版，原描述仅展示
        audit_log(tool_id, score, rewritten)   # 审计
```

- 触发时机：discover 后自动跑 + 管理端"描述体检"按钮手动跑；
- 效果验证：决策 LLM 选错工具率（`mcp_tool_call_log` 中 error 率 + 人工抽样）作为指标。

### 5.3 其他增强

1. **工具调用熔断**：每个 server 挂 §2.3 的 breaker（连续 5 次失败 → 30s 快速失败），替代现状"每次超时等满 call_timeout_ms"；
2. **结果截断规范**：保留现状 300-500 字截断（`tool_calling.py::_truncate`），大结果落 artifact（§3.3）；
3. **只读工具结果缓存**：`risk=read` 且同参数的工具结果 Redis 缓存 60s；
4. **工具权限分级**：`admin_only` 工具不进普通用户 chat 的决策 prompt（现状 `list_enabled_tool_metas` 无权限过滤，是越权隐患）；
5. **Schema 版本化**：discover 发现 `input_schema` 变更时记录 `schema_version` 并告警（防止上游 server 升级悄悄破坏调用）。

---

## 6. 性能与容灾

### 6.1 Redis 缓存分层（热点/空结果/互斥重建/排行）

```python
# app/core/cache.py（伪代码核心，§2.6 的防护在此落地）
CACHE_TTL = {  # 分层 TTL 表（雪崩防护：写入时统一加 ±10% 抖动）
    "series:detail:{id}": 300,        # 课程详情（热点，击穿防护重点）
    "cohort:seats:{id}": 10,          # 班次余位（短 TTL，接近实时）
    "profile:{user_id}": 600,         # 用户画像
    "coupon:template:{id}": 60,       # 券模板
    "rank:weekly": 600,               # ZSET 排行快照
}

async def get_or_load(key: str, loader, ttl: int | None = None):
    # 1) 命中直接返回
    # 2) 穿透防护：loader 返回 None → SET key "null" EX 30（空结果缓存）
    # 3) 击穿防护：SETNX {key}:mutex EX 10；抢到锁者重建 + SET key value EX ttl
    #             抢不到者：若存在旧值（逻辑过期）先返回旧值兜底，否则短轮询 100ms×3
    # 4) 重建完成 DEL mutex（Lua 脚本校验 token 防误删）

# 排行榜：ZSET（gamification 积分/学习时长），周榜快照 + 实时增量
# 一致性策略：写操作（订单/报名）后主动 DEL 相关 key（旁路缓存，非双写一致性）
```

**缓存开启范围（灰度）**：先开 course detail/cohort seats/profile（读多写少、收益最大），chat/交易域暂缓（一致性要求高），canary 验证后逐步放量。

### 6.2 MySQL 慢查询治理

| 项 | 现状 | 动作 |
|---|---|---|
| 阈值告警 | `_log_slow_query`（200/500ms）已埋点 | 日志接 ELK/grafana 聚合 + 每日 TOP-10 慢 SQL 报表 |
| 索引审计 | edu.sql 权威表已带外键/唯一键，但查询索引不足 | 按访问模式补：`order(user_id, created_at)`、`order_item(order_id)`、`payment_record(order_id)`、`session_video_play(user_id, started_at)`、`service_ticket(user_id, ticket_status)` 等 |
| 深度分页 | `LIMIT %s OFFSET %s`（mcp registry 等） | 大表列表改 keyset 分页（`WHERE id < last_id ORDER BY id DESC LIMIT n`） |
| 写放大 | video_play_event/曝光日志高频单行写 | Redis List 缓冲 → 每 2s/500 条批量 INSERT（`executemany`）；掉电容忍（日志表允许秒级丢失） |
| 连接池水位 | 主 10 / RO 5 | full 档评估后调至 20/10；`_pool_semaphore` 信号量闸保留（现有防挂死机制） |
| 事务 | 已有"事务内禁嵌套独立连接"约定 | 加入 CI lint（grep transaction 块内的 execute_write/fetch_* 调用） |

### 6.3 Milvus 批量与 durable execution

- **批量**：`loader.py:179` 已是 `for i in range(0, total, 200)` 分批 upsert ✅ 达标；embed 侧 `EMBED_BATCH_SIZE=8` → 上调 32（GPU 批吞吐提升，`embedder.py:230`）；contextualize 步骤并发限速 8（§4.2）；
- **durable execution**：任务状态表 `task` + `progress_json`（§3.9）；rebuild 状态机现状（`RAG_REBUILD_TIMEOUT_SECONDS`）扩展为通用任务框架（队列 → worker → 断点续跑 → 死信队列人工介入）；
- **LangGraph 对话恢复**：checkpointer 落 Redis（§3.6），进程重启不丢会话。

### 6.4 优雅降级矩阵（外部依赖不可用时的行为契约）

| 依赖宕机 | 降级行为 | 用户感知 | 现状基础 |
|---|---|---|---|
| Milvus | 熔断快速失败 → 空 docs + degraded_reason → 规则重排路径兜底 → LLM 基于自身知识回答并标注"基于通用知识" | 无检索质量下降 | 已实现（retriever.py 三通道 try/except） |
| Redis | 限流放行（现状）、缓存穿透直达 DB、checkpoint 暂存本地内存（有损）、熔断开 | 功能可用、性能下降 | 限流降级已实现，缓存层新加 |
| MongoDB | 对话状态临时切 MySQL（chat_message 表本就是权威历史）；熔断开 | 会话历史可用 | 需新增适配器（STATE_BACKEND 抽象） |
| Neo4j | 跳图谱扩展（现状） | 无图谱推荐 | 已实现 |
| MinIO | 上传/视频 503（明确报错），课程详情文字部分可用 | 部分功能不可用 | 需补"明确 503"而非 500 |
| LLM | 规则兜底答案（`_local_rule_answer`，现状） | 降级答案 | 已实现 |
| MySQL | **不可降级**：503 + 快速失败（熔断防止连接池耗尽），不允许静默 | 服务不可用但快速明确 | 需补熔断快速失败 |

**降级统一原则**：所有降级点写 `degraded_reason`（现状字段语义保留），前端统一展示"部分功能降级中"；降级指标全部进 Prometheus（`edu_degraded_total{component}`）。

---

## 7. 架构薄弱点（供挑战者攻击验证）

| # | 薄弱点 | 潜在风险 | 影响范围 | 挑战方向建议 |
|---|---|---|---|---|
| 1 | **多子代理编排的 LLM 成本/延迟放大**：fan-out 一轮 = 3-5 次 fast 调用 + 1 次 strong 生成，L3 任务可达 10+ 次调用；即使全 fast 模型，P95 延迟与月成本仍可能超预算（chat 限流 20/min × 全量用户） | 延迟超 8s 目标；LLM 账单失控；限流档位被击穿 | AI 助手链路全部用户 | 压测 L1-L3 各等级端到端延迟/成本；挑战 effort scaling 判定是否会误把 L1 升到 L3；验证 prompt caching 前缀命中率是否真的 ≥80% |
| 2 | **交易域并发一致性（订单→支付回调→报名→券核销跨多表事务 + 回调重试）**：单事务内 4-5 表行锁竞争；支付网关回调重试与用户手动支付并发；退款与报名状态双写不同步（退款成功但 student_cohort_rel 未置 refunded） | 重复入账/少核销券/学员已退款仍可上课；行锁等待拖垮连接池（历史 task04 #2 已发生过池耗尽挂死） | 交易/报名/售后全链路，资金安全红线 | 并发压测支付回调（同 payment_no 100 并发重试）；挑战"条件更新+唯一键"幂等是否有遗漏路径（如 payment_no 相同但 order 不同）；验证事务内行锁持有时间 |
| 3 | **多 worker 下本地模型（BGE-M3 + bge-reranker-v2-m3）重复加载**：uvicorn workers=4 → 每 worker 各加载 BGE-M3（~2GB）+ reranker（~2.2GB）≈ 17GB 显存/内存；`services/embedding_service`、`services/reranker_service` 目录已预留但为空（未实现独立服务） | 显存 OOM 导致 worker 崩溃循环；冷启动 44s（现状注释）在重启时放大 ×N | RAG 检索/导入全链路 | 压测 4 worker 启动后的内存/显存占用；挑战"worker 内单例 + 共享内存"方案是否可行（CUDA 多进程共享模型有 GIL/显存页问题）；评估是否必须提前落地独立 embedding/reranker 微服务 |
| 4 | **Redis 从"限流专用"升级为"缓存+checkpoint+队列+幂等+熔断"多角色单点**：角色耦合后 Redis 故障的爆炸半径扩大（现有降级策略是"Redis 挂了限流放行"，但缓存/幂等/checkpoint 挂了怎么办？）；缓存一致性（旁路缓存与 66 表写操作的 DEL 遗漏）引入数据陈旧 | 交易数据读到旧价格/旧余位；幂等失效致重复下单；对话状态丢失 | 全站（尤其交易一致性） | 故障注入：杀掉 Redis 后逐个验证交易/聊天/缓存链路；挑战缓存 key 的 DEL 覆盖是否穷尽所有写路径（含管理端直接改表）；挑战幂等键与唯一键的优先级关系 |
| 5 | **66 表 edu.sql 权威迁移与现有自建表并存冲突**：现 app 已有自建表（chat_session/chat_message/user_profile/order 系列补丁表 patch_chat_tables.sql 等）与 edu.sql 规范（如 `order` 为保留字表名、`student_profile` 结构不同）可能不一致；迁移期间双 schema 并存，全量数据（10 万用户/8 万订单）导入性能与正确性未验证 | 字段映射错误导致数据错乱；迁移失败回滚困难；现网接口读取新旧表混合导致脏读 | 全部业务域，属数据层基础 | 挑战迁移方案的双写/回切策略；验证 edu.sql 导入 66 表的时长与幂等（重复导入）；检查 `order`/`question` 保留字在 asyncmy 参数化 SQL 中的转义一致性 |

---

**附录 A：本次重构建议的任务拆分顺序**（供规划使用）

1. P0：core/resp 壳统一 + middleware 补齐（trace/breaker/idempotency）——横切底座
2. P1：transaction 域（coupon→order→payment→refund）+ enrollment 域（含 HITL 审批）——新表新代码
3. P2：RAG 重构（rerank 接入 + contextualize + top-150→20）+ rag_evaluator 评估闭环
4. P3：AI orchestrator-worker 重构（图/子代理/记忆/compaction/Redis checkpoint）
5. P4：learning/after_sales/risk 域 + 缓存分层 + 慢查询治理
6. P5：edu.sql 66 表迁移收口 + durable execution 任务框架 + 容灾演练

---

架构设计完成，产出：技术架构设计_EduAgent后端重构_正式版_v1.0.md，共 5 个架构薄弱点
