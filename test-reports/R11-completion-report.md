# R11 HITL 中断/恢复 完成报告（contracts/reshape-r-hitl.json，2026-09-15 冻结）

- 日期：2026-09-15
- 角色：后端图域 + chat 前端工程师（单写者，r11.lock 已建/已删）
- 契约权威：`contracts/reshape-r-hitl.json`（frozen_hash 前缀 `6df38908`，用户签字）
- 验收方式：pytest 契约测试（10 项）+ 真实 HTTP 实证（8010 临时实例，已关闭）+ 既有 chat 契约回归（39 项）

## 实现清单

| 文件 | 改动 |
|---|---|
| `app/chat/flows/langgraph_agent.py` | 新增 `_hitl_risk_level`（R15 write_class_tools ∪ course_write ∪ executor 高风险类 → 契约 low\|medium\|high；只读/未登记 → None 免中断）；`tool_node` 中 `settings.HITL_ENABLED` 开关下 `interrupt()` 三件套：payload 五字段 `{thread_id, tool_name, args, risk_level, timeout_s:300}`，resume 决策 `action != "confirm"` → 拒绝结果（工具零执行） |
| `app/chat/flows/graph_stream.py` | Redis 挂起/决策键 `hitl:pending:{thread_id}`/`hitl:decision:{thread_id}`（TTL=timeout_s=300）+ `_mark_hitl_pending`/`_pop_hitl_decision`；astream 捕获 `__interrupt__` → `sse_line("pending_confirm", payload)` + 收束 done（`degraded_reason=awaiting_human_confirm`）；续流驱动：同 thread_id 有决策 → `Command(resume=<决策>)` 续跑挂起图；anon- 前缀 thread_id 放行会话校验（新会话首问即中断的续流专线） |
| `app/chat/router.py` | `ChatResumeRequest{thread_id, action: Literal[confirm,reject], reason?}` + `POST /api/chat/resume`：校验 `hitl:pending:` 存在（未知/过期 → 40450「确认已超时」）→ 决策写 `hitl:decision:`（TTL=300）→ 响应壳 `{"status":"resumed"|"rejected"}`；Redis 不可达 → 50301 脱敏 |
| `app/common/error_codes.py` | 登记 `CHAT_HITL_THREAD_NOT_FOUND = "40450"`（HITL 人机协作域 4045x） |
| `edu-frontend/public/chat.html` | CSS `.hitl-card` 确认卡；SSE `pending_confirm` 分支；`renderHitlCard`（工具名+参数+风险级徽标+确认/拒绝按钮+超时倒计时自动 reject）；`resumeHitl`（EAPI.post /api/chat/resume）；`continueStream`（同 thread_id 重开流）；流式主体抽为可复用 `openStream`（首问与续流共用） |
| `tests/test_r11_hitl.py` | 新增 10 项契约测试（G1~G7 逐条） |

## 40450 登记前后 diff（error_codes.py 摘录）

```diff
@@ BANK_IN_USE 段之后 @@
+# ═══════════════════════════════════════════
+# HITL 人机协作域（chat hitl）— 4045x（R11，contracts/reshape-r-hitl.json 冻结 2026-09-15）
+# 语义：POST /api/chat/resume 未找到挂起中的 thread_id（未知 / TTL 过期自动失效）→「确认已超时」。
+# HTTP 404（404xx 码段 → _http_status_for_code 自动映射）。
+# ═══════════════════════════════════════════
+CHAT_HITL_THREAD_NOT_FOUND = "40450"   # HITL 确认超时/线程不存在（resume 未知或过期 thread_id）
```

## GWT 逐条实证

### R11-G1 图级中断 ✓
`pytest tests/test_r11_hitl.py -v` → `10 passed in 6.88s`（以下数字均出自该次运行）
- `test_g1_risk_level_classification` PASSED：ADMIN_WRITE_TOOLS 5 个工具全部映射 `high`、COURSE_WRITE_TOOLS 6 个全部映射 `medium`、executor 高风险（exec_command/write_file/refund_apply）映射 `high`；只读/未登记（search_knowledge/web_search/get_course/calculator/空串）→ `None` 免中断
- `test_g1_interrupt_payload_and_no_exec` PASSED：带 checkpointer `ainvoke` → 返回 `__interrupt__`，payload 键集合恰为五字段 `{thread_id, tool_name, args, risk_level, timeout_s}`，`risk_level ∈ {low, medium, high}`、`timeout_s == 300`，中断点后状态 `executed is False`（**工具未执行**）

### R11-G2 恢复 ✓
- `test_g2_resume_confirm_executes` PASSED：`Command(resume={"action":"confirm"})` 续跑 → 节点完成且 `executed=True`（工具真实执行）
- `test_g2_resume_reject_skips_exec` PASSED：`Command(resume={"action":"reject"})` → 走拒绝上下文（`out="rejected"`）且 `executed=False`（**工具零执行**）

### R11-G3 SSE 帧 ✓
`test_g3_pending_confirm_sse_frame_bytes` PASSED：`sse_line("pending_confirm", payload)` 字节级恒等于
```
event: pending_confirm
data: {"thread_id": "t1", "tool_name": "points_change", "args": {"p": 1}, "risk_level": "high", "timeout_s": 300}

```

### R11-G4 真实 HTTP ✓
- pytest ASGI：`test_g4_resume_unknown_thread_40450` PASSED（404 + `code=40450` + message 含「超时」）；`test_g4_resume_confirm_writes_decision` PASSED（200 + `data.status=resumed` + `hitl:decision:` 键已写 + `hitl:pending:` 键已消费）
- 8010 真实实例 curl 输出摘录：

```
未知 thread_id:
  {"code":"40450","message":"确认请求已超时或不存在，无法继续执行，请重新提问。","data":null}
  HTTP_STATUS:404
合法 confirm（先注入 hitl:pending:real-http-tid）:
  {"code":0,"message":"ok","data":{"status":"resumed"}}
  HTTP_STATUS:200
  DECISION-EXISTS: 1 / PENDING-GONE: True
```

### R11-G5 超时 ✓
`test_g5_resume_after_ttl_expiry_40450` PASSED：注入 `hitl:pending:` 键 `ex=1`，sleep 1.2s 后 resume → HTTP 404 + `code=40450`（TTL 过期即「确认已超时」，与未知 thread_id 同路径）

### R11-G6 零回归 ✓
- 真实 HTTP：student（user000001）普通问答 `POST /api/chat/stream`（query=「什么是积分？」）事件序列 = `start,retrieval,token,done`，**无 pending_confirm**
- 既有 chat 契约回归：`pytest tests/test_sse_envelope_contract.py tests/test_chat_stream_error.py tests/test_contract_task_r02.py tests/test_contract_task_r02tail.py tests/test_chat_delete.py -q` → `39 passed in 12.43s`

### R11-G7 前端 ✓
- `test_g7_frontend_pending_confirm_static` PASSED：chat.html 含 `evt === "pending_confirm"` 分支、`renderHitlCard`、`resumeHitl`、`EAPI.post("/api/chat/resume"`、`hitl-confirm`/`hitl-reject` 按钮、`thread_id` 续流语义
- JS 语法：内联 script 提取后 `node --check` 通过（`JS-SYNTAX-OK`）
- 手测步骤（编排者复现，禁 Playwright，用真实浏览器）：
  1. 打开 `http://localhost:3000` 登录 student，在既有会话内提问可触发写类工具的指令（如「帮我把课程《XXX》积分加 5 分」）
  2. 流发至检索后应出现 🛡️ 确认卡（工具名 + 参数 + 高风险徽标 + 确认/拒绝按钮 + 倒计时）
  3. 点「确认执行」→ 卡片转 busy → 自动以同 thread_id 重开流 → token/done 照常流出，工具真实执行
  4. 再触发一次，点「拒绝」→ 续流后 AI 以「您拒绝了该操作」上下文继续作答，工具零执行
  5. 不操作等待倒计时归零 → 卡片显示「确认超时，已按拒绝处理」并自动按 reject 续流
  6. 会话侧栏应出现该对话（done 帧 session_id 收编）

## 契约接线说明（实现决策，非契约扩展）

- **续流驱动**：resume 端点只落 Redis 决策；客户端收 `resumed` 后以**同 thread_id** 重开 `POST /api/chat/stream`，graph_stream 适配层检测决策 → `Command(resume=<决策>)` 续跑挂起图（checkpoint 已保存 interrupt 状态）
- **anon- 续流专线**：新会话首问即中断时 thread_id=`anon-{uuid}`（无真实会话），续流重开以同 thread_id 传 `session_id`，会话归属校验对 `anon-` 前缀放行（该前缀是 checkpoint 线程 id 而非真实会话）
- **风险级单一事实源**：`_hitl_risk_level` 复用 `permission_gate.ADMIN_WRITE_TOOLS/COURSE_WRITE_TOOLS` + `executor._classify_hitl_action`，禁另造分类器；RiskLevel 枚举 → 契约 low|medium|high

## 交付

- commits：后端 `feat(r)/R11-hitl-interrupt-resume` + 前端 `feat(r)/R11-hitl-chat-pending-confirm` + 报告 `docs(r)/R11-completion-report`（仅 R11 范围文件，工作区其它并行任务改动未混入）
- r11.lock 已删
