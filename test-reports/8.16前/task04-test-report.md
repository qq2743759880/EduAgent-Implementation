# 功能测试报告 Task04

## 第 1 次测试

### 判定：PASS

### 验收标准逐项核对

| # | 验收标准（dev-plan.md L29） | 结果 | 证据 |
|---|------------------------------|------|------|
| 1 | RAG 集合列表含 Milvus 快照行数；重建索引返回 202 + job_id | ✅ 通过 | 页面渲染 2 行集合（`knowledge_chunk_v1/_default` 行数快照 **4,969 chunks**、`edu_knowledge/_default`）；重建弹窗（增量/全量模式）→ 提交 → `POST /collections/rebuild` 返回 **job_id=r_0214f6bb4537** 并展示 |
| 2 | 新建 is_default=true 预设 → 旧 default 自动置 0，列表只显示一个默认项 | ✅ 通过 | UI 实测创建 `ui_test_default_538414`（勾选默认）→ toast「预设已创建并设为默认」→ 列表默认徽章仍 **1 个**；后端 `create_preset`（service.py:247-273）事务内先 `UPDATE is_default=0` 再 INSERT，实测无误 |
| 3 | 审计日志按 user_id/role/created_after 过滤 + 表格分页正确 | ✅ 通过 | 表格 8 列 10 行/页；`user_id=882` 过滤精确命中 1 条打靶学生记录（role=student、latency_ms=4845）；点击「下一页」→ `page=2` 请求 200 且首行数据变化（#882→#842）；user_id/role/created_after 三个过滤控件均渲染，参数透传由单测覆盖 |
| 4 | MCP Server 列表带健康灯；discover-live 工具表格展示 name/description | ✅ 通过 | 5 个 server（3 种子 + 挑战残留）渲染 transport/健康灯（**ERR/OK/OK/OK/ERR** + last_error 文本）；stdio-echodemo「发现工具」→ 4 个 DB 工具（add/list_alphabet/ping/echo）；`discover-live` → `GET /servers/1/discover-live` 200 + sourceLabel「Live Discover（直连不落库）」 |
| 5 | 工具测试提交参数 JSON → 展示 status/result/latency_ms | ✅ 通过 | add 工具测试弹窗预填 schema 默认值 JSON（a:0,b:0）→ 编辑 a=1,b=2 → `POST /api/mcp/tools/test` 200 → 展示 **status=成功、延迟 77ms、result={"sum":3,"was_negative":false}** |
| 6 | student 直连任一 /api/admin/rag/* 或 /api/mcp/* → 403 | ✅ 通过 | verify-task04-rbac.mjs **4/4**：守卫拦截重定向（/admin/rag、/admin/mcp → /dashboard）+ 后端 API 403（`X-Force-Role: student` 直连 collections/servers） |

### 测试执行记录

| 项 | 结果 |
|----|------|
| `npx vitest run`（edu-frontend） | ✅ 24 文件 / 185 用例全部通过（含 `rag.test.ts` 14、`mcp.test.ts` 16、SearchTester 3、RebuildDialog 3、ToolTestDialog 6、ServerTable 4） |
| 后端打靶 `rag_admin_hit.py`（10 断言） | ✅ 10/10（RBAC×2 / collections / rebuild / preset-list / preset-create / audit-empty / audit-by-user / search-all / search-preset）；学生 chat 产生真实审计记录，Milvus 不可达时 search 返回 `retrieved=0/final=0/degraded_reason` 不 500 |
| 浏览器验证（Playwright，admin 身份） | ✅ RAG + MCP 全流程逐项实测通过（见上表）；注：MCP 浏览器环境存在 PNA 限制（页面直连 127.0.0.1:8000 失败）且沙箱无 Node fetch，采用「route.continue 移除 Authorization 头 + 前端 baseURL=localhost:8000」方案打通，全部 API 200 |
| verify-task04-ui.mjs（sd-dev 脚本复跑） | ⚠️ RAG 段 7/7 通过；脚本在「高级检索等待 search-doc」处中断——**Milvus 不可达时 docs=0 属环境限制**，脚本未处理 degraded 分支（脚本自身假设 Milvus 可用，非产品缺陷）；MCP 段由我手动 Playwright 完整验证 |
| verify-task04-rbac.mjs | ✅ 4/4 |

### 环境限制（非缺陷）

1. **Milvus/Mongo/Neo4j VM（192.168.85.101）不可达**（本次测试前已存在，后端启动时降级）：高级检索 docs 无法返回（`docs=0 + degraded_reason="Milvus 检索跳过（MilvusException）；Neo4j 未连接"`），前端正确展示降级提示与元信息（召回 0 · 最终 0 + rewrite_query）——符合后端契约「Milvus 缺时返回空 docs + degraded，不 500」；「docs 展示」项待 Milvus 可用环境复验。
2. **历史脏数据**：`rag_param_preset` 曾存在 2 个默认（id=8/9 `low_*`，命名疑似对抗/打靶脚本创建），导致打靶断言 [04] 首次失败。已实测确认 `create_preset` 事务逻辑正确（创建 is_default=true 后唯一默认），并已清理恢复 id=8 为唯一默认、删除测试预设。**非代码缺陷**。

### 观察项（非 task04 缺陷，供后续处理）

1. **后端 422 异常处理器崩溃（既有缺陷）**：`app/main.py:216` `request_validation_exception_handler` 将 `exc.errors()` 中的 ValueError 对象直接序列化 → `TypeError: Object of type ValueError is not JSON serializable` → **整个 uvicorn 进程崩溃**。由 `POST /api/admin/users/None/role`（task03 打靶遗留的路径参数 422）触发，与 task04 代码无关，但建议在 task05 联调前修复（任一 422 校验错误都可能打崩后端）。
2. 测试产生的增量数据：打靶注册的学生账号、`调试自定义预设-*`（非默认，保留）、MCP 调用日志——不影响验收，未清理。

### 架构薄弱点验证结果（design-guide §7）

| # | 薄弱点 | 是否命中 | 说明 |
|---|--------|---------|------|
| 1 | DEBUG 鉴权绕过（X-Force-Role 伪冒任意角色 / 无 Token 即虚拟 ADMIN） | ⚠️ 部分命中 | 实测 `X-Force-Role: student` 直连 admin API 正确返回 403（RBAC 断言本身成立）；但无 Authorization 头时任意请求即虚拟 admin，本测试即利用该机制打通 admin 会话——**属既有后端设计，供 sd-challenger 深挖**（前端 AdminGuard 不受影响：无 token 一律重定向登录） |
| 2 | 前端静默吞错（R-7） | ✅ 未命中 | rag/mcp 全部写操作失败向上抛 ApiError（单测断言 rejects）；页面查询失败渲染 ErrorState（含重试）；工具测试 JSON 解析失败在 mutationFn 抛错走全局 toast；重建/预设/测试弹窗均展示明确错误 |
| 3 | 聊天路径不匹配（R-1） | ➖ 跳过 | task05 范围，本轮无相关调用 |
| 4 | DELETE 会话缺失（R-2） | ➖ 跳过 | task05 范围 |
| 5 | 文档口径漂移（R-9） | ✅ 未命中 | `rag.ts`/`mcp.ts` 头注释明确按后端代码实测对齐（与 design-guide §4.6/4.7 摘要差异逐条标注：collections 返回数组、rebuild body 字段、last_health_at/last_health_ok、`POST /tools/test`、servers body 字段）；逐条核对 rag_admin/router.py、mcp/router.py 路径与 RBAC（require_role([ADMIN])）全部一致 |

### 结论

task04（G4 管理端 RAG + MCP 控制台）验收标准 6 项全部满足，无阻断性缺陷。前端单测、后端打靶、浏览器端到端、RBAC 四层验证通过。遗留项仅为环境依赖（Milvus 不可达时的 docs 展示）与既有后端 422 崩溃缺陷（非本轮改动范围）。

---

## 第 2 次测试（修正轮回归复测，2026-08-13）

### 判定：FAIL

**背景**：对抗 8 项（#1 并发默认唯一 / #2 并发挂死 / #3 rebuild 状态机 / #4 tools/test 空 body / #5 call-log 枚举 / #6 console XSS / #8 rebuild 校验 已修；#7 DEBUG 记录不修）。本次复测逐项验证修复有效性，全部确认有效；但复测中发现**新缺陷（严重）**：`GET /collections` 同步阻塞事件循环 10s、`rebuild` 20s，Milvus 不可达时单请求冻结全后端——详见问题清单。

### 挑战 8 项回归结果

| # | 上次问题 | 当前状态 | 验证证据 |
|---|---------|---------|---------|
| 1 | 并发默认唯一失效 | ✅ 已修复 | 5 并发 `POST /presets {is_default:true}` → 状态码 `[201,409,409,409,409]`，DB 最终仅 **1 行** is_default=1（API list 复核） |
| 2 | 并发写挂死全后端 | ✅ 已修复（写路径） | 10 并发写 preset 全部 0.03s 按时返回；随后 GET /presets、/api/mcp/servers、/api/admin/users 均 0.02s 正常；信号量无泄漏（MySQL Threads_connected 正常） |
| 3 | rebuild 状态机永久 stuck | ✅ 已修复 | ① 存在 partition rebuild → 202 + job_id；② stuck 回置实证：knowledge_chunk_v1 rebuild 后超 120s 被 `list_collections` 自动回置 `error`（status_message 含"重建超时>120s…自动回置"）；手工回拨 last_rebuild_at 300s 的占位行同样回置 error；③ 前端 `rag/page.tsx:33-34` 仅 rebuilding 时 refetchInterval=10s 轮询，流转后自动停止 |
| 4 | tools/test 空 body → 500 | ✅ 已修复 | 空 body → **422** `{code:42200,...}`（非 500） |
| 5 | call-log 非法枚举静默全量 | ✅ 已修复 | `?status=HACKED` → **422**（Literal 枚举）；`?status=SUCCESS` → 200 正常过滤 |
| 6 | console 页 XSS | ✅ 已修复 | `mcp/router.py:689` `esc(props.join(", "))`（esc 定义 L635） |
| 7 | DEBUG 鉴权绕过 | ➖ 确认不修 | challenge.md 已追加处置结论（继承 task02/03：`.env DEBUG=false` 上线硬门槛，非本轮代码缺陷） |
| 8 | rebuild 垃圾占位行 | ✅ 已修复 | 非法命名 `unknown!bad!` → **400** `RAG_PARTITION_INVALID`；合法命名降级环境占位行由 #3 超时回置兜底（不再永久 stuck） |

### 问题清单（本轮新发现）

| # | 严重度 | 位置 | 原因 | 修改建议 |
|---|--------|------|------|----------|
| 1 | 严重 | edu-agent/app/admin/rag_admin/service.py:161-193,199-289 → app/knowledge/importer/loader.py:336-362,33-40 | `list_collections()`/`rebuild_collection()` 在 async 服务中**同步调用** `loader.list_all_partitions()`，而该函数每次 `MilvusClient(uri=...)` 新建实例且**无超时配置**（对比 `app/database.py:149-150` DEBUG 下 3s 超时）；Milvus VM 不可达时 pymilvus `list_partitions` 默认 10s 连接超时 → 实测 `GET /collections` 恒定 10.0s、`rebuild` 20.1s（2 次调用），且**同步阻塞 asyncio 事件循环**：并发测试中 collections 请求进行时，2s 后发出的 `GET /presets` 被冻结排队至 t=10s（耗时 8.0s）才返回。效果等同单请求 DoS 全后端（含学生请求），浏览器端集合表格"加载知识库…"挂起 ~10s。该缺陷与修正轮 #2 目标（消除单点请求挂死）同源，写路径已修但读路径残留。 | ① loader 复用 `app.database.get_milvus_client()` 全局单例（含 DEBUG 3s 超时）或新建时显式 `timeout=3.0`；② `list_all_partitions` 改异步 + `asyncio.wait_for` 包裹；③ 或将 Milvus 补全逻辑整体移出事件循环（`run_in_executor`/后台任务） |

### 复测执行记录

| 项 | 结果 |
|----|------|
| `npx vitest run`（edu-frontend） | ✅ 24 文件 / 185 用例全过 |
| 后端并发验证（5 并发默认 preset + 10 并发写） | ✅ 见回归表 #1/#2（总耗时 0.03-0.07s） |
| rebuild 验证（400 / 202 / stuck 回置） | ✅ 见回归表 #3/#8 |
| MCP 契约（空 body / HACKED / SUCCESS） | ✅ 3/3（422 / 422 / 200） |
| 浏览器抽查（Playwright + X-Force-Role 注入） | ✅ /admin/rag 集合列表（2 行快照 4,969/0 chunks + 就绪状态 + 重建按钮）；/admin/mcp Server 列表（7 server 健康灯/transport/工具数）；发现工具弹窗 4 工具；add 测试弹窗提交 `{"a":3,"b":4}` → 成功 / 100ms / `{"sum":7,"was_negative":false}`；⚠️ 集合表格加载挂起 ~10s（问题 #1 的 UI 表现） |
| 既有打靶 | ✅ rag_admin_hit.py **10/10**；p8_hit.py **22/22**；admin_all_hit.py **19/19**（脚本自带 uvicorn 因 VM 不可达启动超 60s 失败，改为复用 18765 端口后端运行断言，通过） |
| task04-challenge.md 处置结论 | ✅ 已追加（"处置结论（2026-08-12 sd-dev 修正轮）"：已修复 #1-6/#8 表 + 未修复 #7 表 + 回归结果表） |

### 架构薄弱点验证结果（本轮）

| # | 薄弱点 | 是否命中 | 说明 |
|---|--------|---------|------|
| 1 | DEBUG 鉴权绕过 | ⚠️ 命中（继承） | 环境仍 DEBUG=true，无 token/X-Force-Role 虚拟 ADMIN 可复现；challenge #7 已记录不修，上线硬门槛项 |
| 2 | 前端静默吞错（R-7） | ✅ 未命中 | 本轮浏览器抽查中集合列表/Server 列表加载中与错误态均正常展示（无吞错） |
| 5 | 文档口径漂移（R-9） | ✅ 未命中 | 本轮 8 项修复点路径/契约全部与前端调用一致（rebuild 400/422 等状态码前端可正常处理） |

### 环境说明与数据清理

- 复测环境：后端 127.0.0.1:8000（DEBUG=true，MySQL ok，Milvus/Mongo/Neo4j/MinIO 不可达降级，同 challenge 修正轮）；前端 dev server :3000。
- 问题 #1 判定依据为真实 HTTP 实测（多次重复 + 并发交叉验证），非偶发：`GET /collections` 连续 5 次均 10.0s，`rebuild` 20.1s，均为 Milvus VM 不可达环境必现。
- 复测产生的测试数据已清理：`retest_*`/`repro_*` 预设 11 条删除、默认预设恢复 id=1 唯一、`rag_collection_meta` 2 行恢复 ready（含打靶产生的 rebuilding 行）、`user_99999999` 占位行删除；DB 当前态与修正轮基线一致。

### 结论

挑战 8 项修复全部验证有效（#7 按约定不修并已记录）。但复测中实测发现**严重缺陷**：RAG `list_collections`/`rebuild_collection` 对 Milvus 的同步阻塞调用在 Milvus 不可达时冻结整个 asyncio 事件循环 10-20s（单请求 DoS 全后端，必现），与修正轮 #2 的修复目标同源且位于 task04 核心页面加载路径，判定 FAIL 待修复；修复后建议回归本报告问题 #1 项。

---

## 修正轮 2（2026-08-13，复测问题 #1 修复回归）

### 判定：PASS

**修复内容**（对齐测试者建议 + 最小变更面）：

| # | 文件 | 改动 |
|---|------|------|
| 1 | `edu-agent/app/knowledge/importer/loader.py:33-49` | `get_milvus_client()` 优先复用 `app.database.get_milvus_client()` 全局单例（DEBUG 下 3s 超时）；单例未初始化（启动降级）时兜底新建实例并**显式 `timeout=3.0`**（pymilvus 默认 10s） |
| 2 | `edu-agent/app/admin/rag_admin/service.py` | 新增 `_MILVUS_CALL_TIMEOUT_S=5.0` + `_list_all_partitions_limited()`：`anyio.to_thread.run_sync` 移出事件循环 + `asyncio.wait_for` 5s 硬上限，失败/超时返回 `[]` 降级；`list_collections`/`rebuild_collection` 全部 Milvus 调用改走该 helper（**不再同步阻塞事件循环**） |
| 3 | 同上 | `rebuild_collection` 内两次 `list_all_partitions`（存在性校验 + 快照补全）**合并为一次调用复用**——不可达环境下 2×3s 串行叠加会突破 5s 验收线（实测初版 6.41s → 合并后 3.1s） |
| 4 | `edu-agent/app/knowledge/routers/upload.py:360-374` | 同源缺陷顺带修复：`GET /api/knowledge/partitions` async 路由同步调用 `list_all_partitions` → 同样包 `to_thread + wait_for(5s)`，超时返回 503 而非 500 |
| 5 | 前端 `rag/page.tsx` | 无需改动（确认）：refetchInterval 仅 rebuilding 时 10s 轮询，修复后单次请求 ≤3.1s << 10s 间隔，不叠加不阻塞 |

**耗时实测**（真实 HTTP，双环境矩阵）：

| 场景 | 修复前（第 2 次测试记录） | 修复后 | 验收线 |
|------|--------------------------|--------|--------|
| Milvus 不可达 `GET /collections` | 10.0s（恒定） | **3.03-3.06s**（连续 5 次稳定，走满 loader 3s 超时） | < 5s ✅ |
| Milvus 不可达 `POST rebuild` | 20.1s（2 次调用叠加） | **3.08s**（202 + job_id + "Milvus 未连接"降级语义） | < 5s ✅ |
| collections 进行中并发 `GET /presets` | 排队 8.0s | **0.03s**（事件循环零冻结） | < 1s ✅ |
| 期间 `GET /api/mcp/servers`（旁证） | 冻结 | 0.17s | < 1s ✅ |
| Milvus 可达 `GET /collections` | —（当时不可达） | **0.06-0.17s**（200 + 2 行快照，含真实行计数 4,969） | ✅ |

不可达环境用黑洞地址（`MILVUS_URI=http://10.255.255.1:19530`）强制走满超时路径，非网络抖动巧合；可达环境为 VM 网络恢复后的真实连通。

**既有打靶回归**：

| 脚本 | 环境 | 结果 |
|------|------|------|
| `rag_admin_hit.py` | 8000（Milvus 可达） | ✅ **10/10**（检索真实命中 retrieved=15/final=5，正常路径无回归） |
| `p8_hit.py` | 8000（Milvus 可达） | ✅ **22/22** |
| `admin_all_hit.py` | 18765（Milvus 不可达黑洞） | ✅ **19/19**（复用 18765 实例，断言 0.94s 完成） |
| `npx vitest run`（edu-frontend） | — | ✅ **24 文件 / 185 用例全过**（含 rag.test.ts 14、RebuildDialog 3） |

**复测执行记录**：后端语法检查 `compileall` 通过；`GET /collections` 不可达环境连续 5 次 3.0x s 稳定复现（非偶发）；rebuild 后 `status=rebuilding + 120s 超时回置` 状态机不受影响（占位式降级语义保持）；并发隔离验证按测试者建议复刻（collections 进行中 2s 后发 presets，0.03s 返回）。

**环境说明**：修复验证期间 Milvus VM（192.168.85.101:19530）网络状态发生变化——首次实测时不可达（复现 10s/20.1s 基线中 3s 快速失败路径），后续恢复可达（正常路径 0.06s）；不可达最坏路径用黑洞地址实例覆盖验证。测试产生数据：打靶预设/审计记录按既有惯例保留，未清理。

**结论**：问题 #1（async 路由同步阻塞 Milvus → 单请求 DoS）已修复并经双环境实测 + 三份打靶 + 前端单测回归确认。修复后 Milvus 不可达时 `GET /collections` ≤ 3.1s 带快照降级返回（不 500）、`rebuild` ≤ 3.1s 返回 202、并发无关请求零排队；Milvus 可达时正常路径毫秒级返回且行计数真实回写。前端 10s 轮询与快速返回不叠加。lessons-learned.md 已追加 L24（async 路由禁止同步阻塞外部服务 + 客户端显式超时）。
