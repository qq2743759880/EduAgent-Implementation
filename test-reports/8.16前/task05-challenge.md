# 对抗性测试报告 Task05

## 第 1 次测试

### 判定：FAIL

- 测试时间：2026-08-13
- 环境：edu-agent 8000 端口运行中（`.env` DEBUG=true，单进程 PID 25184，`/openapi.json` 确认 DELETE 路由已生效）
- 测试方式：真实 HTTP 攻击（注册 A/B 学生 → 创建/删除会话 → 数据库直查验证），前端源码静态审计

---

### 问题清单

| # | 维度 | 严重度 | 位置 | 质疑 | 可能后果 | 建议 |
|---|------|--------|------|------|---------|------|
| 1 | 验收标准盲区 | 一般 | `edu-agent/app/auth/dependencies.py:117-127`（DEBUG 虚拟 admin）+ `edu-agent/app/chat/router.py:116-131`（DELETE 端点）；实测：无 Authorization 头 `DELETE /api/chat/sessions/{id}` → **200 `{ok:true}`** 且会话被删 | be-task01 验收标准明确要求「未登录删除 → 401」，但当前交付环境（DEBUG=true）实测未登录删除返回 200，会话真实被软删。根因是薄弱点 #1（DEBUG 鉴权绕过）的既有设计，但 DELETE 是本轮**新增端点**，验收标准未定义 DEBUG 环境下的预期语义 | 开发/演示环境（.env DEBUG=true 为交付基线）任何人无需 Token 即可删除任意已知 session_id 的会话（session_id 可从 XSS/日志/共享链接等渠道获得）；验收标准与实测行为冲突，验收无法闭合 | ① 验收标准补充 DEBUG 环境语义：未登录删除在 DEBUG=true 下预期 200（虚拟 admin）或要求打靶脚本显式断言；② 生产部署（DEBUG=false）回归验证 401 路径 |
| 2 | 架构级（安全） | 一般 | `edu-agent/app/auth/dependencies.py:80-102`（X-Force 头）；实测 `X-Force-Role: student + X-Force-User-Id: 915`（用户 A 真实 user_id）→ DELETE 返回 **200** 成功删除 A 的会话 | X-Force 伪冒头可完全模拟任意用户身份执行 DELETE（薄弱点 #1 放大到本轮新增端点）。user_id 可通过 `/api/auth/me`、社区帖子 `author_id`、积分日志等公开渠道获取，无需知道 Token | 任何攻击者（或误操作的调试脚本）可批量删除任意用户会话，用户数据"删除后消失"且无法恢复（软删不可见） | ① DEBUG 模式下 X-Force 头增加来源限制（仅 localhost 直连可带）或启动参数开关；② 交付环境建议 DEBUG=false 出包 |
| 3 | 非功能性（事务） | 轻微 | `edu-agent/app/chat/service.py:247-274`（`_append_messages_and_bump_session` 在 `transaction()` 内嵌套调用 `execute_write()`——database.py:360-361 明令禁止的模式，task04 #1 根因） | 消息插入与 `message_count`/`last_message_at` 更新非原子（各自独立连接独立提交），任一步失败会出现计数与真实消息数不一致 | 列表 `message_count` 徽章显示错误；与 DELETE 并发时可能产生孤儿消息（chat_message 有行但会话 yn=0，API 不可见，无数据泄漏但留脏数据） | 事务内改用共享 `cur` 执行（对齐 database.py 注释规范）；DELETE 与消息落库竞态可接受但建议注释说明 |
| 4 | 性能/并发（竞态） | 轻微 | `edu-agent/app/chat/service.py:144-156`（delete_session）与 `service.py:242-246`（update_session_sql 带 `AND yn = 1`） | 用户删除会话与 LLM 回答落库并发时：先通过 `_ensure_session_owner`（yn=1）后 UPDATE yn=0，正在流式生成的回答随后落库——`update_session_sql` 因 `yn=1` 不匹配而空更新，消息已写入 chat_message 但计数不更新 | 已删会话残留孤儿消息行（API 层 404 不可见）；列表无泄漏。低概率、无用户可见后果 | 可接受；若需根治可在落库前复查会话 yn 或依赖外键级联（当前无） |

---

### 薄弱点核查清单（design-guide §7）

| # | 薄弱点 | 防御证据 file:line | 攻击实证 | 结论 |
|---|--------|-------------------|---------|------|
| 3 | 聊天路径不匹配（R-1） | `src/lib/api/chat.ts:218`（getChatHistory → `/history`）；grep 全前端无 `/messages` 调用残留（仅注释 chat.ts:217 与测试描述 chat.test.ts:4/35/100）；`chat.test.ts:35-69` 单测覆盖路径+失败兜底 console.error；深链 `?sid=`：`ChatFullScreenClient.tsx:167-173` initialSid → `useChatSessions.ts:94-109` effectiveSelectedId 回退；GlobalChatInjection.tsx:174 历史加载走同一 `/history` | 路径修复完整；深链失效 id 时 404 → console.error + 空态，不崩溃、不回滚 UI 假数据 | **已防御** |
| 4 | DELETE 会话缺失（R-2） | `router.py:116-131`（DELETE + `DeleteSessionResponse(ok=True)` → 200 `{ok:true}`）；`service.py:144-156`（软删 UPDATE yn=0，无物理 DELETE + 复用 `_ensure_session_owner` 归属校验）；`service.py:92-113`（yn=1 过滤 → 已删会话 404）；`list_sessions`/`get_session_history` 均过滤 yn=1（service.py:120/125/95） | 实测：本人 200 `{ok:true}`；重复删除 404（幂等）；删除后历史 404（chat_message 残留不可见）；删除后列表不含；B 删 A 会话 403 + `CHAT_SESSION_FORBIDDEN`；admin 删他人会话 200（角色语义成立）；非 `s_` 前缀 404；SQL 注入不 500；DB 直查确认 yn=0 且无物理 DELETE | **核心防御已就绪**（另见问题 #1/#2：DEBUG 环境验收冲突） |
| 1 | DEBUG 鉴权绕过（放大面） | 非 task05 新增，但 DELETE 端点暴露面叠加：无 Token → 虚拟 admin（dependencies.py:117-127）；X-Force 头任意伪冒（dependencies.py:80-102） | 实测未登录 DELETE 200 删除成功；X-Force 伪冒真实 user_id 删除成功（200） | **未防御**（既有已知设计，但新增端点放大，见问题 #1/#2） |
| 5 | 文档口径漂移（R-9） | 本轮前端调用路径与后端实测一致（`/history`、`/sessions`、DELETE 均实证 200/403/404） | — | 本轮无新增漂移 |

---

### 各挑战方向核查结果

**1. R-2 补丁缺陷（幂等/残留/403/admin/格式）**：全部通过。重复删除 404（service.py:98-99 已删即 NotFoundError）；软删会话 message 残留不可见（get_session_history 先 `_ensure_session_owner` 过滤 yn=1 → 404，service.py:167）；跨用户 403；admin 删他人会话 200（角色语义：admin 全局可见可删，与 `list_sessions` admin 全局列表一致）；非 `s_` 前缀 404；SQL 注入安全（参数化 + 404）。

**2. R-1 修复完整性**：通过。`/messages` 无调用残留；`?sid=` 深链正常（effectiveSelectedId 派生回退 + 历史合并去重，useChatSessions.ts:104-109、ChatFullScreenClient.tsx:221-257）；GlobalChatInjection 浮动窗口走同一 `/history`（GlobalChatInjection.tsx:174）。

**3. 会话隔离**：通过。A 删后本人列表不含（实测）；admin 全局列表仅 yn=1（删除后即消失，语义一致）；message_count 保持原值不归零但 yn=0 行不可见，无泄漏。

**4. 联调链路**：基本通过。p9_step6_e2e_hit.py 幂等（随机账号 `_gen_account` + 409 兜底、admin 种子存在即跳过不覆盖密码、重启后端后 `_openapi_has_delete_route` 探针防旧代码）；后端不可用 → `_port_up` 超时/连接失败 exit 3 + 报告落盘；RAG collections 实测 200（Milvus 快照降级不 500）。**盲区**：脚本 R-2 专项未覆盖「未登录删除」用例（DEBUG 下必然 200，与验收标准 401 冲突，见问题 #1）。

**5. 归一化回归**：通过。normalizeSession 兼容 `session_id`/`message_count` 双字段（chat.ts:171-191）；缺失时 id 回退 `""`、messages_count 回退 null——极端场景（后端两字段均缺失）id="" 会请求 `/api/chat/sessions/` 404，但后端 schema 强制 `session_id` 必填（schemas.py:23），实际不可达；chat.test.ts:100-130 单测覆盖。

**6. DELETE 契约**：通过。200 结构 `{ok:true}`（实测 `{"ok":true}`）；404/403 错误壳 `{code,message,detail}` 结构正确（实测 CHAT_SESSION_NOT_FOUND / CHAT_SESSION_FORBIDDEN，嵌套 detail 形态与 api-client.ts:113-123 兼容）；OPTIONS preflight 200 + allow-methods 含 DELETE + 反射 Origin（Starlette `allow_origins=["*"]` + `allow_credentials=True` 的标准反射行为，浏览器端可用）。

---

### 测试环境说明（可复现性）

- 攻击脚本：临时目录 `task05_attack*.py`（未写入项目源码，符合只读角色约束）
- **误报澄清**：初次攻击曾观测到「DELETE 200 但 DB yn=1」，经排查为 pymysql 同连接 REPEATABLE READ 快照隔离所致（同连接 DELETE 前 SELECT 开启事务快照，删后同连接 SELECT 仍见旧快照）；pymysql 新连接验证 yn=0，后端删除实际生效。非产品缺陷。
- 遗留：测试产生的测试账号（chal_*/p9s6_*）与会话数据保留在库中，与既有打靶脚本行为一致。
