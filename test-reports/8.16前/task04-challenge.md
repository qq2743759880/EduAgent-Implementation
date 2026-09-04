# 对抗性测试报告 Task04

> 任务：task04 · G4 管理端 RAG + MCP 控制台（P9 Step9）
> 被测面：`edu-frontend/src/lib/api/admin/{rag,mcp}.ts`、`src/components/admin/rag/*`、`mcp/*`、`src/app/(admin)/admin/{rag,mcp}/page.tsx`；后端 `app/admin/rag_admin/*`、`app/mcp/*`
> 测试方式：代码静态核对（file:line）+ 真实 HTTP 实测（后端 127.0.0.1:8000，DEBUG=true，Milvus/Mongo/Neo4j 不可用降级环境）

## 第 1 次测试

### 判定：FAIL

### 薄弱点核查清单（design-guide §7）

| design-guide 薄弱点 | 防御证据 file:line | 结论 |
|---|---|---|
| 1. DEBUG 鉴权绕过（`auth/dependencies.py:80-127`） | 无代码级防御。实测：无 token `GET /api/mcp/servers` → **200**（虚拟 ADMIN）；`X-Force-Role: admin` 无 token → 200。`admin-guard.tsx:22-23` 仅注释声明"上线硬门槛 DEBUG=false"，.env 现仍 `DEBUG=true` | **未防御**（问题 #7，继承 task02 对抗 #1，非本轮新增） |
| 2. 前端静默吞错（R-7） | ① `lib/api/admin.ts:21-43` 列表/写操作一律抛 ApiError 不吞错；② `lib/query-client.ts:50-52` 全局 MutationCache onError → toast+console.error；③ 列表三态 `controls.tsx:79-102` ErrorState/EmptyState；④ RAG search 降级提示显式展示 `SearchTester.tsx:122-130`；⑤ MCP 工具测试失败 `error_message` 显式展示 `ToolTestDialog.tsx:165-169`；⑥ discover-live 失败展示 liveError `ToolTable.tsx:72-83`；⑦ call-log 空态 `CallLogTable.tsx:136-137`；⑧ audit-log 空态 `AuditLogTable.tsx:117-118` | **已防御** |
| 5. 文档口径漂移（R-9） | 前端 14 个端点路径与后端 router 逐一核对一致：rag.ts:172/184/204/227/243 ↔ rag_admin/router.py:65/73/81/89/97/115；mcp.ts:190/195/203/208/216/230/235/247/273/278 ↔ mcp/router.py:43/52/75/84/121/202/231/252/338/355。实测 200/201/202/400/404/409/422 全部符合契约（含 `tools/test` body 差异已在 mcp.ts:9-12 注释修正） | **已防御** |

### 问题清单

| # | 维度 | 严重度 | 位置 | 质疑 | 可能后果 | 建议 |
|---|------|--------|------|------|---------|------|
| 1 | 边界攻击（并发唯一性） | 严重 | `app/admin/rag_admin/service.py:247-273` + `app/database.py:344-360` | 2 并发 `POST /presets {is_default:true}` → 两个 201，DB 持久存在 **2 行 is_default=1**（实测 id=11/12，6 秒后与 API 均仍双默认）。根因：`transaction()` 上下文内的 UPDATE/INSERT 均经 `execute_write`（`database.py:348-360` 每次 `pool.acquire()` 独立连接 + `commit=True` 自动提交）执行，事务包装形同虚设——"清旧 default"与"插新 default"之间无原子窗口，并发 B 的 UPDATE 落在 A 的 INSERT 之前即双双成为默认 | 验收标准"旧 default 自动置 0，列表只显示一个默认项"**在并发下失效**；`rag/page.tsx:39` 取第一个默认、`SearchTester` 下拉出现 2 个"（默认）"项；admin search 应用 preset 时取到哪个不确定 | 唯一性下沉 DB（`(yn,is_default)` 部分唯一索引）或 `SELECT ... FOR UPDATE` 串行化；`transaction()` 内禁止嵌套 `execute_write`，改用共享连接 `cur.execute` |
| 2 | 非功能性（并发可用性悬崖） | 严重 | `app/config.py:48`（MYSQL_POOL_SIZE=5）+ `app/database.py:43-54,288-310` | 5 并发 `POST /presets is_default=true` → 5 请求全部挂起 >25s 零提交，随后**整个后端 MySQL 类 API（rag presets/collections、admin users、mcp servers）挂死 ≥8s**，仅 `/health` 存活，重启后恢复（实测复现） | 池 maxsize=5 + `pool.acquire()` 无超时，行锁竞争占满连接 → 单点并发写即 DoS 全后端，管理端控制台整体瘫痪 | acquire 加超时与队列上限；#1 修复后锁竞争消失；适度提高 pool size；写路径加并发闸 |
| 3 | 数据一致（rebuild 状态机） | 一般 | `app/admin/rag_admin/service.py:157-231` + `CollectionTable.tsx:76` | rebuild 202 后 status 永久停在 rebuilding：Milvus 不可用时无异步任务也无回置逻辑（service.py:195-224 注释自认"不做异步任务队列"），`list_collections` 只同步 row_count 不重置状态；前端**无轮询**（全项目 grep 无 refetchInterval），且 `CollectionTable.tsx:76` 在 rebuilding 时禁用重建按钮 → 集合被永久锁死 | 当前降级环境实测 `_default` 集合 stuck rebuilding，重建按钮永远禁用，无任何恢复路径；验收标准只覆盖"202+job_id"未覆盖状态流转 | 后端补 job 状态机（超时回置 ready/failed）；前端 `refetchInterval` 轮询；rebuilding 允许重试（幂等重建） |
| 4 | 边界攻击（错误契约） | 一般 | `app/mcp/schemas.py:187-191` + `app/main.py:195-223` | `POST /api/mcp/tools/test` 空 body → **500** `{code:50000, detail:"Object of type ValueError is not JSON serializable"}`，应 422 | model_validator 抛 ValueError 进入 422 handler 的 `errors` ctx 后 `json.dumps` 崩溃；DEBUG 下泄露内部异常；前端虽不发空 body，但契约健壮性缺失 | validator 改抛 HTTPException(400) 或 422 handler 对 ctx 做可序列化兜底 |
| 5 | 契约/过滤（静默失效） | 一般 | `app/mcp/router.py:271` | `GET /api/mcp/call-log?status=HACKED` → 200 返回**全量**日志（非法枚举被静默跳过而非 422） | 管理员拼错状态值（如 SUCESS）时过滤条件被静默丢弃，审计结果误导 | 非法枚举返回 422，或按字面 LIKE 过滤 |
| 6 | XSS | 轻微 | `app/mcp/router.py:681`（后端 console HTML 页，非 task04 React 面） | 工具表 `props.join(", ")`（input_schema 属性名）未转义直接 innerHTML，恶意/失陷 MCP server 的 schema 属性名可注入 HTML | admin-only 页面存储型 XSS；task04 前端组件（ToolTable.tsx:163-190 等）全部 JSX 转义，实测 `<script>` 预设名存储+返回均安全 | `props.join` 前过 `esc()`（同文件 455-460 已有工具） |
| 7 | 架构级（RBAC/DEBUG） | 轻微 | `app/auth/dependencies.py:80-102` + `.env:DEBUG=true` | 薄弱点 #1 实证：无 token `GET /api/mcp/servers` → 200；`X-Force-Role: admin` 可伪冒任意角色（student force → 403 证实 force 生效） | 前端守卫（admin-guard.tsx:81-85）正确拦截未登录/非 admin，但 API 层在 DEBUG=true 下完全裸奔——上线忘关 DEBUG 则管理端 API 全量可匿名访问 | 继承 task02 对抗 #1 处置：上线硬门槛 `.env DEBUG=false` + 生产禁用 force 头（非本轮新增，仅实证确认） |
| 8 | 边界攻击（垃圾数据） | 轻微 | `app/admin/rag_admin/service.py:168-193` | rebuild 不存在的 partition → 202 + 占位 INSERT 一行永久 rebuilding（实测 `user_99999999` 垃圾行入库） | 误输 partition 名会污染 `rag_collection_meta`，列表出现永不恢复的假集合（叠加 #3 无回置） | 校验 partition 存在性，或占位行加 TTL/失败回置 |

### 已验证防御（PASS 面，附证据）

1. **RBAC（真实 token）**：student 与真实 manager（提权后实测）token 访问 10 个端点全部 403——`/api/admin/rag/{collections,presets,audit-log,search,rebuild}`、`/api/mcp/{servers,call-log,tools/test,health-scan,discover-live,console}`（后端路由级依赖 `rag_admin/router.py:44`、`mcp/router.py:36`）；前端守卫 `admin-guard.tsx:81-85` + 菜单过滤 `layout.tsx:49` 与后端一致。
2. **契约漂移**：全部路径/body/query 参数核对一致；实测空 query → 422、preset_id=999999 → 404 `RAG_PRESET_NOT_FOUND`、page_size=200 → 422、user_id=abc → 422、server_code 重复 → 409、import-url ftp://file:// → 400、tools/test 不存在 tool → 404、discover-live 不存在 server → `{ok:false,reason}` 且前端展示。
3. **静默吞错（R-7）**：写操作全走 useMutation + 全局 MutationCache toast；列表三态齐全；search degraded_reason、工具测试 error_message、健康扫描 last_error 均显式展示；`created_after=2026-08-12T00:00`（datetime-local 无秒）实测 200 正常解析。
4. **XSS（task04 前端面）**：审计 query、预设名、工具 description/name、server 字段全部 React JSX 转义；实测含 `<script>` 的预设名存储/返回后由 React 安全渲染。

### 测试环境与方法

- 后端：`uvicorn app.main:app`（DEBUG=true，MySQL ok，Milvus/Mongo/Neo4j 不可用——与 .env 一致），实测端口 8000。
- 手段：requests 脚本实测 40+ 用例（RBAC 真 token / force 头 / 边界 / 并发 / 降级 / 状态流转）；pymysql 直查 DB 取证（`rag_param_preset`、`rag_collection_meta`）；前端静态核对 file:line。
- 复现保留：并发双默认（preset id=11/12）、stuck rebuilding 集合（`_default`、`user_99999999`）、垃圾占位行均已入库；如需清理可在复测前重置这两张表。

### 判定说明

- 问题 #1/#2 直接违反 task04 验收标准核心不变量（默认项唯一）并导致全后端可用性风险，且为可稳定复现的实证缺陷 → **FAIL**。
- 问题 #3-#8 为验收标准盲区与降级路径缺陷；#7 为 design-guide 薄弱点 #1 实证（继承项，非本轮新增）。

---

## 处置结论（2026-08-12 sd-dev 修正轮）

### 已修复

| # | 严重度 | 修复内容 | 验证方式 |
|---|--------|---------|---------|
| 1 | 严重 | ① DB 层：`rag_param_preset` 加生成列 `default_flag`（`CASE WHEN is_default=1 AND yn=1 THEN 1 ELSE NULL END` STORED）+ 唯一键 `uk_rag_preset_default_flag`（MySQL 8.0.12 不支持函数索引，用生成列方案，5.7/8.0.x 通用）；② `create_preset` 事务内共享连接 cur 执行 + 快照读/FOR UPDATE 锁默认行，锁等待期间默认行身份变化 → 409 `RAG_PRESET_DEFAULT_CONFLICT`；③ `transaction()` 内不再嵌套 `execute_write`（全项目事务块改为共享 cur） | 并发 5 请求 POST /presets {is_default:true} → **状态码 [201, 409, 409, 409, 409]**，DB 最终仅 1 行 is_default=1（API list 核验）；正常切换默认仍 201 |
| 2 | 严重 | ① `MYSQL_POOL_SIZE` 5→10（config.py + .env）；② `database.py` 新增 `_pool_acquire`：`asyncio.Semaphore(maxsize)` 并发闸 + `asyncio.wait_for` 10s 超时（asyncmy 的 `Pool.acquire` 不支持 timeout 参数）+ 2 次退避重试，失败抛 DatabaseError；③ 新增 `_pool_release` 统一归还连接+信号量（acquire/release 成对）；④ `health.py` 直连池改为走统一通道，避免计数不一致 | 并发 10 写 POST /presets + 10 并发 GET 全部按时返回（实测 0.05s，无挂死）；随后多轮并发（含 #1 场景）信号量无泄漏、无超时 |
| 3 | 一般 | 后端 rebuild 状态机：`rebuild_collection` 进入时写 `last_rebuild_at=now`（计时起点），重复重建幂等（重置计时）；新增 `_recover_stuck_collections()`：`list_collections` 入口对 `status='rebuilding'` 且超 `RAG_REBUILD_TIMEOUT_SECONDS=120`（config 可配）回置 `error` 并注明原因；前端 `rag/page.tsx` collectionsQuery 加 `refetchInterval`（仅当存在 rebuilding 时 10s 轮询，状态流转后自动停止），`CollectionTable.tsx` 移除 rebuilding 禁用（允许幂等重试） | 手工置 stuck（last_rebuild_at 回拨 300s）→ GET /collections 回置 `error` 且 message 含"重建超时…自动回置"；rebuild 中重复 rebuild 202 幂等 |
| 4 | 一般 | ① `mcp/schemas.py` 两个 model_validator 改抛 `HTTPException(422)`（ValueError 会进 422 handler 的 errors ctx 导致 json.dumps 崩溃）；② `main.py` 422 handler 对 errors 递归 `_jsonable` 兜底（任何对象 str 化），双重防御 | POST /api/mcp/tools/test 空 body → **422** `{code:42200,...}`（原 500）；stdio 缺 run_command → 422 |
| 5 | 一般 | `mcp/router.py` call-log 的 status 参数改为模块级 `CallLogStatus = Literal["SUCCESS","ERROR","TIMEOUT","SKIPPED"]` 类型别名（future-annotations 下内联 Literal 字面量会 PydanticUserError 500） | GET /api/mcp/call-log?status=HACKED → **422**；status=SUCCESS → 200 正常过滤（打靶 [13]/[17] 回归通过） |
| 6 | 轻微 | `mcp/router.py` console 页面 `props.join(", ")` 前过 `esc()`（复用同文件 455-460 转义工具） | console 页面 JS 静态核验含 `esc(props.join(...))`；页面 200 可访问 |
| 8 | 轻微 | `rebuild_collection`：① partition 命名契约校验（`_default` 或 `user_\d+`，非法 → 400 `RAG_PARTITION_INVALID`）；② Milvus 可用时强校验真实分区存在（不存在 → 404，不插占位垃圾行）；③ Milvus 不可用（降级）时占位行由 #3 超时回置兜底（120s → error），不再永久 stuck | 非法 partition `unknown!bad!` → 400；降级环境 rebuild 202 后 stuck 由 list_collections 自动回置（与 #3 同验） |

### 未修复（记录）

| # | 结论 |
|---|------|
| 7 | 继承 task02/task03 处置：DEBUG 鉴权绕过（`auth/dependencies.py` 虚拟 ADMIN / X-Force-Role）属上线硬门槛范畴（`.env DEBUG=false` 后自动关闭），非本轮代码缺陷；上线检查单应包含"生产环境 DEBUG=false + 禁用 force 头"项 |

### 回归结果（修复后全量打靶）

| 打靶脚本 | 结果 |
|---------|------|
| `rag_admin_hit.py`（10 断言） | ✅ 全过（RBAC×2 / collections / rebuild 202 / presets 列表+新建默认唯一 / audit / admin-search±preset） |
| `p8_hit.py`（20 断言） | ✅ 全过（servers CRUD / import-url / tools / test 4 工具 / 非法 tool 4xx / call-log SUCCESS / RBAC） |
| `p8_admin_debug_hit.py`（14 断言） | ✅ 全过（console 200 / RBAC×2 / discover-live / raw-rpc / health-scan / call-log 过滤） |
| `admin_all_hit.py`（19 断言） | ✅ 全过（课程/题库/用户三模块 + RBAC 403） |
| 前端 `npx vitest run` | ✅ 24 文件 185 用例全过 |
| 前端 `npx tsc --noEmit` / `eslint`（改动文件） | ✅ 无错误 |

### 测试环境说明

- 修正轮验证在后端 127.0.0.1:8000 实测（DEBUG=true，MySQL 本机 ok，Milvus/Mongo/Neo4j/MinIO 不可用降级——进程级环境变量 `MINIO_ENDPOINT=127.0.0.1:1`、`NEO4J_URI=bolt://127.0.0.1:1` 加速 lifespan，未改动 .env 业务配置）。
- 修正前已清理：`rag_param_preset` 双默认（id=11/12 已不存在于库中，恢复种子 id=1 为唯一默认）；`rag_collection_meta` stuck rebuilding（`_default` 两行）回置 ready；`user_99999999` 垃圾行已不存在。
- 修正后数据态：`rag_param_preset` 仅 1 行默认（id=1 平衡-default）；`rag_collection_meta` 2 行 ready（种子 + 打靶 edu_knowledge）。
- 建表脚本 `patch_rag_admin_tables.sql` 已同步生成列 + 唯一键（新环境一键建表即带约束）。
