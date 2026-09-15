# blind-t8-hitl-e2e — R11 HITL 端到端盲测报告

| 项 | 值 |
|---|---|
| executionSessionId | `20260915_185301_t8hitl` |
| 执行时间窗 | 2026-09-15 18:53–19:02 (GMT+8) |
| 被测版本 | 分支 `feature/opt-waves`，HEAD `dfde11210eb3f0244db06ccc98cdc6dfc2c8446b` |
| 被测实例 | **独立后端** `127.0.0.1:8078`（`MYSQL_HOST=127.0.0.1`，`.venv` uvicorn），未触碰在跑的 8000/3000，验后已关闭 |
| 数据纪律 | 自建会话 2 个（`s_350fb9ea0385` / `s_89cc18ff2edb` 及另一次同类）验后 `DELETE` 清理；Redis 自建键验后清理；**无任何 DB 直写** |
| 遵守的禁令 | 未读任何历史报告/验收文档（仅读 README/AGENTS/被测代码 + 测试代码）；未用 Playwright；未 DB 直写 |
| 证据来源 | 全部为本次新跑的 HTTP/进程内实测；脚本落在 `%TEMP%\blind_t8\`（`probe_t8.py` / `probe_t8b.py` / `probe_t8c.py`），非仓库文件 |

标注口径：`[实测]` 本次真实跑出；`[代码佐证]` 源码/grep 出处；`[推演]` 由事实推导、未直接观测；`[未验证]` 受环境或禁令限制无法验证；`[文档原文]` 引用文档字符串。

---

## 1. 结论摘要（先给判定）

| 被测路径 | 判定 | 一句话依据 |
|---|---|---|
| ① 中断触发（`event: pending_confirm` + 五字段） | **FAIL（链路不可达）** | 6/6 写类/危险级诱导 query 走 `/api/chat/stream`，事件序列恒为 `start→retrieval→token×N→done`，**0 次** `pending_confirm`；诱导的写工具**一次都没被调用**（`mcp_tool_calls: []`） |
| ② 中断时工具零执行（安全不变量） | **PASS（但原因是"没走到"，非"拦住了"）** | 工具未执行是因为请求根本没触发工具路径，而不是被 HITL 拦截；不变量当前**未被真实考验** |
| ③ 确认卡渲染（工具名+参数+风险级+确认/拒绝） | **PASS-仅静态** `[代码佐证]` / **渲染与交互 [未验证]** | `chat.html` 中卡片 DOM/CSS/事件齐全，但无 pending_confirm 可触发，且禁 Playwright → 无法截图 |
| ④ 超时自动 reject | `[代码佐证]` / **[未验证]** | `chat.html:905-918` 有 1s 倒计时，归零调 `resumeHitl("reject","确认超时")`；无法真实跑到 |
| ⑤ confirm 路径（resume→同 thread_id 续流→工具真实执行） | **FAIL（不可达）** | 无 pending 可确认；用**人工合成预置** pending 可让端点回 200，但续流时因图中本就无 interrupt，决策被静默吞掉 |
| ⑥ reject 路径（零执行 + 拒绝上下文） | **FAIL（不可达）** | 同上；拒绝上下文分支（`langgraph_agent.py:337-346`）从未在线路上出现 |
| ⑦ 40450（伪造/过期 thread_id） | **PASS** | 4/4 例返回 **HTTP 404 + `{"code":"40450","message":"确认请求已超时或不存在…","data":null}`**；非法 `action` → 422/42200 |

> **一句话总纲**：R11 HITL 的**端点层（resume/40450）是真的、可用的**；但**中断层（pending_confirm）在真实生产链路里不可达** —— 唯一发射它的图节点没有被接进任何生产图，唯一会 `interrupt()` 的聊天节点是无人调用的死代码。因此「用户被弹卡 → 确认/拒绝」这条端到端链**无法由真实用户触发**。

---

## 2. 逐路径实测明细

### 2.1 ① 中断触发 — 6 组诱导 query，0 命中

请求：`POST /api/chat/stream`，body `{"query": …, "stream": true, "use_mcp_tools": true, "model": "fast"}`，学生 token（`user000001`）。全部 HTTP 200。

| # | 诱导目标 | 工具语义 | HTTP | 耗时 | SSE 事件序列 | `pending_confirm` | `mcp_tool_calls` |
|---|---|---|---|---|---|---|---|
| Q1 | 课程写类 | `course_create` | 200 | 36.4s | start×1, retrieval×1, **token×730**, done×1 | **无** | `[]` |
| Q2 | 积分变更 | `points_change` | 200 | 16.1s | start×1, retrieval×1, **token×204**, done×1 | **无** | `[]` |
| Q3 | 命令执行 | `exec_command_demo` | 200 | 13.6s | start×1, retrieval×1, **token×494**, done×1 | **无** | 无调用 |
| Q4 | 退款 | `refund_order` | 200 | 21.9s | start×1, retrieval×1, **token×463**, done×1 | **无** | `[]` |
| Q5 | 知识库导入 | `knowledge_import` | 200 | 19.2s | start×1, retrieval×1, **token×238**, done×1 | **无** | `[]` |
| Q6 | **对照：已注册只读工具** | `ping` | 200 | 29.2s | start×1, retrieval×1, **token×698**, done×1 | **无** | `[{"call_id":"mcp-1789469875261-3a12bffc","tool_name":"ping","args_summary":"{}","status":"success","latency_ms":1285,"result_summary":"{\"pong\": true}"}]` |

**SSE 原文节选（Q1，首帧与 retrieval 帧）**：
```
event: start
data: {"session_id": null, "query": "请帮我创建一门新课程，课程名「HITL 盲测课程」，请调用 course_create 工具写入数据库。"}

event: retrieval
data: {"docs": [...], "graph_entities": [], "retrieved_count": 150, "final_count": 5,
       "rewrite_query": "...", "degraded_reason": "rerank_sidecar_unavailable", "mcp_tool_calls": []}
```

**SSE 原文节选（Q6 对照，工具真的执行了、且全程无确认）**：
```
event: retrieval
data: { ..., "mcp_tool_calls": [{"tool_name": "ping", "status": "success",
        "latency_ms": 1285, "result_summary": "{\"pong\": true}"}] }
event: done
data: {"code": 0, "message": "ok", "data": {"degraded_reason": null, ...}}
```

**工具是否执行**：Q1–Q5 的写类工具**零执行**（`mcp_tool_calls` 为空，且无 `pending_confirm`）；Q6 的 `ping` **真实执行成功**——**且没有任何确认帧、没有任何权限门拦截**。这正是盲测要抓的「200 也绿」的反面：这里不是"绿"，是**中断从未发生**。

### 2.2 ③ 确认卡 — 现场无法产生卡片（见 2.1），只能代码核对

`[代码佐证] edu-frontend/public/chat.html`
- `:1004-1009` SSE 分支 `else if (evt === "pending_confirm")` → `setStreaming(false)` + `JSON.parse(payload)`，缺 `thread_id` 则 `failStream("确认事件缺少 thread_id")`
- `:1007` 渲染函数 `renderHitlCard(pc)`
- `:888-895` 卡片 DOM：标题 + `工具：<code>{tool_name}</code>` + 风险徽章 `hitl-risk-{risk_level}` + `<div class="hitl-args">{args}</div>`（`JSON.stringify(args)`）+ `拒绝` / `确认执行` 两按钮
- `:899-900` 按钮绑定：`resumeHitl("confirm","")` / `resumeHitl("reject","")`
- `:902-918` 超时：`ttl = Number(pc.timeout_s) > 0 ? … : 300`，1s 递减，文案 `（{left}s 内未处理将自动拒绝）`，归零 → 卡片置 `hitl-busy` + 文案 `⏰ 确认超时，已按拒绝处理` → `resumeHitl("reject","确认超时")`
- `:921-937` 决策：`EAPI.post("/api/chat/resume", {thread_id, action, reason})`，成功后 `continueStream(q, pc.thread_id)` → `openStream(query, threadId, {resume:true})`
- `:1019-1021` done 帧保护：`degraded_reason === "awaiting_human_confirm"` 时**保留确认卡不覆盖**
- `:113-129` 卡片样式：3px 黑描边圆角卡、`--candy-orange-soft` 底、风险徽章高=红/中=黄/低=绿、参数区虚线框等宽滚动

**「截图描述」说明（诚实声明）**：本次**没有截到确认卡**——真实链路产生不出 `pending_confirm`（见 2.1），而截图工具（Playwright）被本任务明令禁用。故上节仅为**静态代码推导的形态描述**，标记 `[未验证·视觉渲染]`。**任何声称"确认卡截图已过"的结论，在本链路不可达的前提下都不成立。**

### 2.3 ⑤ / ⑥ confirm 与 reject 路径 — 端点可用、链路不可达

为区分「端点是坏的」与「上游从不产生 pending」，额做一组**人工合成预置**探针（明确标注：pending 标记由探针直接写 Redis 模拟，**非**真实聊天中断产物）：

| 步骤 | 操作 | 实测结果 |
|---|---|---|
| 4 | 自建会话 `s_89cc18ff2edb`，向 Redis 写 `hitl:pending:{sid}` = `{"thread_id":sid,"tool_name":"points_change","args":{"uid":1,"points":999999},"risk_level":"high","timeout_s":300}`（ex=300），再 `POST /api/chat/resume {thread_id:sid, action:"confirm"}` | **HTTP 200** `{"code":0,"message":"ok","data":{"status":"resumed"}}` |
| 5 | 查 Redis 键面 | `hitl:pending:{sid}` **已删除**；`hitl:decision:{sid}` = `{"action":"confirm","reason":"","created_at":1789470043.64}` **已写入** |
| 6 | 同 thread_id 再 resume（应已失效） | **HTTP 404 + code 40450** |
| 7 | 以同 `session_id` 重开 `POST /api/chat/stream` 续流 | **HTTP 200**；事件 `start→retrieval→token×203→done`；`error` 帧 **0**；`done.data.degraded_reason = null`；决策键被消费（步骤 8 查为空） |
| 8 | 查 Redis | `hitl:pending` / `hitl:decision` 双双为 `null` |
| 9/10 | 清理 | 会话 `DELETE` → 200；Redis 删除返回 0（键已不存在） |

**结论**：resume 端点**功能属实**（校验存在性 → 写决策 → 删 pending；一次性消费；二次调用 40450）。但步骤 7 暴露一个**静默行为**：当 thread_id 对应的图**根本没有挂起 interrupt** 时，决策被消费后图**照常当新会话跑完并回 200**（无 error 帧、`degraded_reason=null`）——**决策被静默丢弃，用户侧看不到任何"这次确认没有生效"的提示**。

### 2.4 ⑦ 40450 — PASS（4/4）

学生 token，`POST /api/chat/resume`：

| # | `thread_id` | HTTP | code | message | data |
|---|---|---|---|---|---|
| R1 | `blind-t8-forged-20260915-0001`（随机伪造） | **404** | `40450` | 确认请求已超时或不存在，无法继续执行，请重新提问。 | `null` |
| R2 | `anon-00000000-0000-0000-0000-000000000000`（仿匿名线程） | **404** | `40450` | 同上 | `null` |
| R3 | `盲测-不存在-线程`（中文） | **404** | `40450` | 同上 | `null` |
| R4 | `s_350fb9ea0385`（**真实存在但未挂起的会话 id**） | **404** | `40450` | 同上 | `null` |

补充：
- `action: "approve"`（非法枚举）→ **HTTP 422**，`{"code":"42200","message":"Input should be 'confirm' or 'reject'"}` `[实测]`
- **不带 token** 调 resume → 仍 **404/40450**（非 401）。原因是 `.env` `DEBUG=true` 下无 `Authorization` 头会注入虚拟管理员 `[实测]` + `[推演]`；生产 `DEBUG=false` 应回 401（未在本窗口验证）
- Redis 不可达时契约设计为 503/`50301`（`router.py:368-369`）`[代码佐证]`；本窗口 Redis 正常，**该降级分支未触发** `[未验证]`

### 2.5 五字段校验（`thread_id/tool_name/args/risk_level/timeout_s`）

`[代码佐证]` `langgraph_agent.py:326-332` 构造 payload 恰好这 5 个键，`timeout_s` 硬编码 `300`；`graph_stream.py:313` 以 `sse_line("pending_confirm", value)` 原样下发。
`[实测]` **线上 0 次观测到**（6 组诱导全无该帧）。
`[代码佐证]` 既有测试 `tests/test_r11_hitl.py::test_g1` 断言 `set(v.keys()) == {5 个键}`——但断言对象是**测试内复刻图**在内存里产生的 `__interrupt__`，不是线路上的字节。

---

## 3. 根因（为什么中断不可达）— 全部代码佐证

1. **唯一发射点**：`grep -rn pending_confirm` → 全仓仅 `app/chat/flows/graph_stream.py:313` 一处 `yield sse_line("pending_confirm", value)`，其前置条件是该节点出现 `node == "__interrupt__"`（`:306`）。
2. **生产图里没有会 interrupt 的节点**：`/api/chat/stream` → `graph_stream_sse` → `_ensure_agent_graph()`（`app/ai/graph.py`）。该图节点集被启动自检钉死为 9 个：`app/ai/graph.py:625-628 EXPECTED_SIXNODE_NODES = ("answer","compact","context_edit","fan_out","merge","plan","reflect","route","skill")`；`:724-734` 的 `add_node` 列表与之一致，**无 `tool` 节点**。
3. **唯一会话侧 `interrupt()` 是死代码**：`grep -rn "interrupt(" app/` → 会话侧只有 `app/chat/flows/langgraph_agent.py:334`（`tool_node` 内）。而 `grep -rn "langgraph_agent\|agent_graph" app/ tests/` 显示：**生产代码零引用**，只有 `tests/test_permission_gate.py:41`、`tests/test_r11_hitl.py:70` 引用它。`app/chat/service.py:22` 引的是 `app.ai.graph.run_agent`（同一个 9 节点图），不是它。
4. **双重不可达（就算把 tool_node 接回去也仍然拦不住/拦错了）** `[实测]`：

   | 工具名 | `_hitl_risk_level()`（chat 图分类器） | `_classify_hitl_action()`（executor 分类器） | `can_use_tool("admin", …)` |
   |---|---|---|---|
   | calculator / search_knowledge / add / echo / list_alphabet / ping / sse_health（**全部 7 个真实注册工具**） | `None` | `None` | `True` |
   | course_create/update/delete、question_create/update/delete（6 个） | `medium` | `None` | **`False`** |
   | favorite_add、points_change、knowledge_import、order_create（4 个） | `high` | `None` | **`False`** |

   - 真实注册的 7 个工具**全部 `risk=None`** → 即便接图也**永不中断**；
   - 10 个"写类"名字是契约挂起项、**注册面零命中**，权限门对**含 admin** 一律 deny（`permission_gate.py:197-213` fail-closed）→ 就算接图也是**先被 deny、走不到 interrupt**；
   - 而 `tool_node` 里的顺序就是权限门在前（`:304-315`）、interrupt 在后（`:317-334`）→ 写类工具永远在权限门那一关就返回 `denied`。
5. **真实工具调用路径完全绕过 HITL 与权限门**：会话里真正执行工具的是 `app/chat/tool_calling.py::run_chat_tool_calls`（`:283` 直接 `_mcp_executor.call_tool(...)`），以及非流式路径 `app/chat/flows/agent.py::execute_tool_plan`（`:184` 同样直调）。`grep -rn can_use_tool app/` → **除 `langgraph_agent.py` 外无任何生产消费点**。Q6 实测 `ping` 成功执行、无任何确认，即此路径的现场证据。
6. **executor 自己有一层 HITL gate（但与 resume 不连通）**：`app/mcp/executor.py:490-501` 在 `settings.HITL_ENABLED` 为真且 `_classify_hitl_action(tool) != None` 时走 `_run_hitl_seam` → `run_hitl_gate(human_decision=hitl_decision)`；`human_decision` 缺省 `None` → `pending` → 映射为 `SKIPPED` + 文案「【HITL 待审批】高风险动作已挂起，等待人工/AI 审批。」（`:425-441`）。`grep -rn hitl_decision app/` → **没有任何生产调用方传过 `hitl_decision=True`**，即该 gate 只会一直"挂起"，且**与 `/api/chat/resume` 的 Redis 决策键毫无连接**（后者只被 `graph_stream._pop_hitl_decision` 消费）。
   - `[实测·进程内]` 直接用生产 `run_hitl_gate` + `MemHitlStore`（无 DB 写）复现三态：`human_decision=None → status=pending, executor_calls=0`；`False → rejected, 0`；`True → executed, 1`。即**门逻辑本身正确，缺的是接线与决策传值**。

---

## 4. 与既有测试覆盖的对照（解释"为什么旧绿灯不能证明本链路"）

`[代码佐证] tests/test_r11_hitl.py`（本次实跑 `10 passed in 6.62s`，仅作为机制佐证，不作为链路验收）

| 用例 | 断言对象 | 为什么不足以证明本链路 |
|---|---|---|
| `test_g1_risk_level_classification` | 分类函数纯逻辑 | 不涉及图接线 |
| `test_g1_interrupt_payload_and_no_exec` / `test_g2_resume_confirm_executes` / `test_g2_resume_reject_skips_exec` | **测试内自建复刻图** `_interrupt_graph()` + `InMemorySaver` | 复刻的是语义，不是生产图；生产图根本不含该节点 |
| `test_g3_pending_confirm_sse_frame_bytes` | `sse_line("pending_confirm", …)` 的**字符串拼接字节** | 只证明格式函数能拼串，不证明会被调用 |
| `test_g4_resume_unknown_thread_40450` / `test_g4_resume_confirm_writes_decision` / `test_g5_resume_after_ttl_expiry_40450` | 真实 HTTP（`httpx.ASGITransport(app=app)`） | **但 pending 状态由 `r.set("hitl:pending:{tid}", …)` 直接预置**（`:209`、`:228`）——上游触发从未被验证 |
| `test_g6_error_code_registered` | 常量值 | — |
| `test_g7_frontend_pending_confirm_static` | 对 `chat.html` 做**字符串存在性 grep**（`'evt === "pending_confirm"'`、`"renderHitlCard"`、`"hitl-confirm"` …） | 无 DOM、无渲染、无点击、无网络 → 属 T3「死壳 200 也绿」同类弱断言 |

**旁证（共享 Redis 观测）** `[实测]`：19:00 前后查 Redis 键面，见 `hitl:decision:g4-ok`（`ttl=168s`，`created_at≈18:57`，值 `{"action":"confirm",...}`），键名与 `test_g4_resume_confirm_writes_decision` 的自建键**完全同名** → 说明本窗口内有并行进程正以「直接预置 pending」的方式验证该用例，而非通过真实聊天中断。该键非本次生成，**未删除**（避免干扰并行工作）。同时 `hitl:pending:*` 计数为 **0** —— 全窗口**没有任何一次真实中断发生过**。

---

## 5. 复现步骤（供下一位同事一手复现）

```bash
# 1) 起独立后端（勿动在跑的 8000）
cd "E:/stu/project/stu/EduAgent实施手册/edu-agent"
MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8078

# 2) 跑盲测探针（脚本在 %TEMP%\blind_t8\，需 requests 等价物 urllib，已内置代理绕过）
E:/…/edu-agent/.venv/Scripts/python.exe %TEMP%/blind_t8/probe_t8.py    # SSE 6 组 + 40450 4 例
E:/…/edu-agent/.venv/Scripts/python.exe %TEMP%/blind_t8/probe_t8b.py   # Redis 键面 + gate 三态（须 cwd=edu-agent）
E:/…/edu-agent/.venv/Scripts/python.exe %TEMP%/blind_t8/probe_t8c.py   # 合成 pending → resume 200 → 续流

# 3) 收尾
powershell -c "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8078 -State Listen).OwningProcess -Force"
```
关键预期：步骤 2 第 1 个脚本应看到 **6 组 query 全部无 `pending_confirm`**；第 3 个脚本应看到 resume 200 后**再 resume 变 40450**。

---

## 6. 断言清单（可逐条复核）

| # | 断言 | 标注 |
|---|---|---|
| A1 | 写类/危险级诱导 query 走 `/api/chat/stream`，6/6 无 `pending_confirm` | `[实测]` |
| A2 | 上述 6 组中被诱导的写工具零执行（`mcp_tool_calls` 空） | `[实测]` |
| A3 | `ping` 工具在会话中真实执行成功且无任何确认/权限拦截 | `[实测]` |
| A4 | 伪造/未挂起 thread_id resume → HTTP 404 + `code=40450` + `data=null`（4/4） | `[实测]` |
| A5 | 非法 `action` → HTTP 422 + `42200` | `[实测]` |
| A6 | 无 token 调 resume 未回 401 而是 40450（DEBUG=true 虚拟管理员） | `[实测]` + `[推演]` |
| A7 | 合成预置 pending 下 resume(confirm) → 200 `{"status":"resumed"}`，pending 删、decision 写 | `[实测]`（合成预置，非 e2e） |
| A8 | 合成预置下二次 resume → 40450（一次性消费） | `[实测]`（合成） |
| A9 | 无挂起图时决策被消费后按普通新会话续跑（无 error 帧、无提示）→ **静默** | `[实测]`（合成） |
| A10 | `/api/chat/stream` 所用图的节点集为 9 个、**不含 `tool`** | `[代码佐证]` |
| A11 | `langgraph_agent.tool_node`（唯一会话侧 `interrupt()`）在生产代码零引用 | `[代码佐证]`（grep） |
| A12 | 7 个真实注册工具 `_hitl_risk_level()==None` 且权限门允许 → 永不断点 | `[实测]`（函数级） |
| A13 | 10 个契约挂起写类工具权限门对 admin 亦 deny，且先于 interrupt 判定 | `[实测]` + `[代码佐证]` |
| A14 | 生产工具执行路径（`tool_calling.run_chat_tool_calls` / `agent.execute_tool_plan`）直调 executor，无权限门无 HITL | `[代码佐证]` |
| A15 | executor 层 HITL gate 三态逻辑正确（pending/rejected 零执行、executed 执行 1 次） | `[实测·进程内 MemHitlStore]` |
| A16 | 生产无任何调用方传 `hitl_decision=True` → executor gate 只会长期 pending | `[代码佐证]`（grep） |
| A17 | confirm/reject 端到端链路（弹卡→点按钮→工具真实执行/零执行）**未被验证** | `[未验证]` |
| A18 | 确认卡视觉渲染与交互 | `[未验证]`（禁 Playwright + 无 pending 可触发） |
| A19 | 超时自动 reject 的真实触发 | `[未验证]`（同上；仅 `[代码佐证]` 定时器） |
| A20 | Redis 不可达时 resume 回 503/50301 | `[未验证]`（本窗口 Redis 正常） |

---

## 7. 下一位同事最该知道的 3 件事

1. **`event: pending_confirm` 在真实链路里不可能发生——这不是"没测到"，是代码结构决定的。** 它的唯一发射点在 `graph_stream.py:313`，依赖 `__interrupt__`；而 `/api/chat/stream` 用的 9 节点图（`graph.py:625-628`）里没有任何会 `interrupt()` 的节点，唯一会 interrupt 的 `langgraph_agent.tool_node` 生产零引用。**任何用"注入 Redis pending"来验证 HITL 的测试，验证的都是端点而不是链路**（`tests/test_r11_hitl.py` G4/G5 即如此，G7 更是对 HTML 做字符串 grep）。要验收这条链路，必须先回答一个前置问题：**R11 HITL 到底该挂在哪条编排路径上** —— 是接进 9 节点图（需给图加 tool 节点，会动冻结拓扑 `EXPECTED_SIXNODE_*`），还是把 gate 收敛到 executor 层（`executor.py:490-501` 已在，但缺 `hitl_decision` 的生产传值与 resume 的连接）。

2. **HITL 有两套互不连通的实现，且两套的风险分类器互相打架。** 会话侧 `_hitl_risk_level()` 把 10 个写类名字判 `medium/high`，executor 侧 `_classify_hitl_action()` 对**同 10 个名字统统返回 `None`**（前缀/子串匹配，"course_create" 不 `startswith("create_")`）→ 即使工具真上线，executor gate 也不会拦它们。同时 7 个真实注册工具被两套分类器一致判为"免中断"，但它们被工具路径**直调执行、绕过权限门**（`tool_calling.py:283`）。所以"中断时工具零执行"这个安全不变量**今天没有被真实考验过**——它成立只是因为没走到工具，而不是因为被拦住了。

3. **reject / 超时不点 的真实兜底状态是未知的，别当成"已实现"。** 前端有 1s 倒计时归零自动 `reject`（`chat.html:905-918`），后端有 `pending_ttl_s` 与 `sweep_expired_pending`（`hitl_gate.py:416-430`，由 `app/ai/memory/service.py:246-257` 调用），但：① 二者 TTL 不是同一个口径（前端用 `pc.timeout_s=300`，后端 sweep 用 `HITL_PENDING_TTL_S=600`）；② 断点从不发生 → 两条兜底都从未在真实链路上跑过；③ resume 的 pending 键 TTL 取 `settings.HITL_RESUME_TTL`（默认 300，**`.env` 中未设置**）。复核时请把「TTL 三口径不一致 + 兜底未实测」当作**未收敛项**处理，而不是当作已验收。

---

## 8. 遗留与风险（非本任务判定范围，但影响下轮验收）

- `[实测]` `/api/chat/resume` 在 `DEBUG=true` 且**无 token** 时仍走通业务逻辑（返回 40450 而非 401）。这是 DEBUG 虚拟管理员通道的既有语义，但意味着**本窗口的 40450 结论是在"未鉴权也放行"的姿态下取得的**；生产 `DEBUG=false` 的 401 行为需另窗验证。
- `[实测]` 诱导 query 的 SSE `done.data.degraded_reason = null`（Q6）而 retrieval 帧带 `rerank_sidecar_unavailable` —— 本任务未追此差异。
- `[实测]` 每次 SSE 请求耗时 13–36s（推理模型 reasoning 下限，与既有环境结论一致），本节未做性能解读。
- 本次为验证起的**后端 8078 已关闭**；在跑的 8000/3000 全程未被触碰；自建会话与 Redis 键已清理（`hitl:pending:*` 计数保持 0，非本次的 `hitl:decision:g4-ok` 保留未动）。
