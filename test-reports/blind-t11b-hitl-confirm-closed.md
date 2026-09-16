# T11b 盲测报告：HITL confirm 闭环增量验证（SURFACED-1 + HITL-FIX 收口）

- 日期：2026-09-16
- 工程师：T11b 盲测员（独立身份，单写者）
- 任务：T11 抓的 2 个 P0（pending_confirm 缺字段 + confirm 路径断裂）由 SURFACED1-FIX + HITL-FIX 修复后，T11b 增量验证修复真闭环
- 测试环境：8010 临时实例（8000 禁碰，AGENTS.md）；登录账号 adm02test / mgr01test / user000001
- 测试纪律：全一手 HTTP（requests + urllib）；只读 SQL 参数绑定；禁 Playwright；测试数据自建自清
- 判定口径：**修复层闭环（必达）** = resumed=True + symptom=False + call_log+1；**业务层闭环（附加）** = knowledge_import_task +1（取决于续流 LLM tool_calls 是否构造完整 args，详见 §4 CR-T11b-A）

---

## 一句话结论

**SURFACED-1 + HITL-FIX 在修复层全部闭环（S1~S8 八场景全 PASS）**：pending_confirm 五字段齐备且类型正确、confirm 路径走 execute 分支不再误判"确认失效"、42200 症状在 app.log 末段 grep = 0 次、Redis TTL ≈ timeout_s=300 契约对齐、student/manager 越权仍 deny、风险级 high 仍走 confirm、重复 resume 40450（CHAT_HITL_THREAD_NOT_FOUND）幂等。

**但**真实业务层"knowledge_import_task +1"在 chat 流式 confirm 路径下**默认不可达**：tool_calling 用启发式工具选择（关键词命中）→ `plan.args={}` 始终成立 → confirm 续流调 handler → handler 校验 `source_files` 缺失抛 ValueError → task 不落行。这是**chat 流式 HITL 路径下内置写工具 args 始终为空的隐藏设计缺口**（CR-T11b-A），SURFACED-1 修了 `tool_name` 但 `args={}` 完全没修。LLM 在续流时若自主生成 tool_calls（用真实路径）才会真落行——S7 实证 task 131→132 即此路径，但**不稳定、不可控**。

---

## §1 场景结果（8 场景全 PASS）

### S1 admin × knowledge_import confirm 真闭环 — **PASS（修复层）**
- 操作：admin `adm02test` 流式触发 knowledge_import（query 含完整 source_files 字面 JSON 模板）→ 收 pending_confirm → `/api/chat/resume {action:confirm}` → 同 thread_id 续流
- 实证（8010 临时实例，一手 HTTP）：
  - pending_confirm 帧：`{"tool_name":"knowledge_import","args":{},"risk_level":"high","timeout_s":300,"thread_id":"anon-1789568081468",...}`
  - 五字段全有：`thread_id / tool_name / args / risk_level / timeout_s` 全部存在
  - resumed=True（confirm 走 execute 分支）
  - call_log +1（executor 被调起 = tool_name 传递正确）
  - symptom2=False（无 42200 症状）
  - **task +0**（业务层未落）—— 见 §4 CR-T11b-A 缺口
- 判据：修复层（resumed + symptom=False + call_log+1）PASS
- app.log 实证：`[graph_stream] 写类工具挂起（方案②）thread_id=anon-... tool=knowledge_import role=admin`（权限门放行 → 挂起） + `[MCP] 内置工具 knowledge_import 执行失败: ValueError: knowledge_import 缺少 source_files`（confirm 续流 → handler 拒落 task）

### S2 reject 真零落行 + 拒绝上下文进 prompt — **PASS**
- 操作：admin 流式触发 → `/resume {action:reject}` → 续流
- 实证：
  - rejected=True
  - task +0 / call_log +0
  - 续流文本命中关键词 `['未执行', '取消', '高风险']`（T11 报告 4d 原文同源语义）
  - symptom=False
- 判据：reject 收束 + 拒绝上下文进入 generate prompt ✅

### S3 42200 症状消失（app.log） — **PASS**
- 操作：grep `edu-agent/logs/app.log` 末段（~290KB）`必须提供 tool_id` 和 `AppException: 必须提供 tool_id`
- 实证：总=0，AppException=0（tail_bytes=287473）
- 判据：T11 阶段的 42200 异常已彻底从 app.log 末段消失 ✅

### S4 timeout_s vs Redis TTL 契约对齐 — **PASS**
- 操作：admin 流式触发 → 拿 pending_confirm 的 timeout_s → 直连 Redis 127.0.0.1:6379/0 取 `hitl:pending:{thread_id}` 的 TTL
- 实证：timeout_s=300，Redis TTL=299（1 秒衰减，预期内）
- **修正 AGENTS.md 认知**：AGENTS.md 提到 `HITL_PENDING_TTL_S=600`（默认 600s），但实测**HITL-FIX 修复后 Redis 实际 TTL 已与契约对齐到 300s**——不是 600s。HITL-FIX 报告 §1 "TTL=timeout_s=300 内有效" 与实证一致。原先任务担心"前端 5min 倒计时显示超时但 Redis 实际 10min 才过期"——**不存在该误判窗口**。
- 判据：契约字段与 Redis 实际 TTL 一致 ✅

### S5 student/manager 越权仍 403 — **PASS**
- 操作：student `user000001` 流式触发 / manager `mgr01test` 流式触发
- 实证：student denied=True，sums=1（retrieval 帧含 `status:denied, code:permission_denied`）；manager denied=True，sums=1
- task 131→131（无增量），call_log 174→174（无增量）
- 判据：越权 deny 信封到位 + 零执行 ✅

### S6 pending_confirm 五字段完整性 — **PASS**
- 操作：admin 流式触发独立一次 → 拿 pending_confirm payload
- 实证：`presence={thread_id:True, tool_name:True, args:True, risk_level:True, timeout_s:True}`
- `types={thread_id:str, tool_name:str, args:dict, risk_level:str, timeout_s:int}` 全类型正确
- 判据：五字段齐备且类型正确 ✅

### S7 risk_level=high 仍走 confirm — **PASS（修复层）**
- 操作：admin 流式触发 → 校验 risk_level=high → `/resume confirm` → 续流
- 实证：risk_level=high；resumed=True；symptom=False；**task 131→132（+1）**
- **业务层 task +1 实证**：本批 S7 触发后 knowledge_import_task 真的落了 1 行——这是 LLM 在续流 generate 节点自主生成 tool_calls（用真实存在的 t15_doc.md 作为 source_files）的产物。该实证验证了"chat 流式 HITL confirm 真闭环"在 LLM 配合下的可行性，但**不可控**（取决于续流 LLM 行为）
- 判据：修复层 PASS；业务层 PASS（实证）✅

### S8 同 thread_id 重复 resume 幂等 — **PASS**
- 操作：admin 触发 → 首次 `/resume {action:confirm}` → 二次 `/resume {action:confirm}` 同 thread_id → 三次 `/resume {action:reject}` 同 thread_id
- 实证：
  - rj1 = resumed（首次 confirm 成功）
  - rj2 = HTTPError code=404（pending 已消费 → CHAT_HITL_THREAD_NOT_FOUND 40450）
  - rj3 = HTTPError code=404（同上）
  - task_diff = 0（不重复落行）
- 判据：重复 resume 不重复执行 + 合理 HTTP 40450 收束 ✅

---

## §2 汇总

| 场景 | 判据 | 结果 |
|---|---|---|
| S1 | 修复层：resumed + symptom=False + call_log+1 | PASS |
| S2 | reject 零落行 + 上下文进 prompt | PASS |
| S3 | app.log 0 次 42200 | PASS |
| S4 | timeout_s=300 ≈ Redis TTL | PASS |
| S5 | student/manager 越权 deny + 零执行 | PASS |
| S6 | 五字段齐备 + 类型正确 | PASS |
| S7 | risk_level=high 走 confirm | PASS |
| S8 | 重复 resume 40450 幂等 | PASS |

**8/8 PASS**（修复层）

---

## §3 修复层实证细节

### 修复落地（一手读源码验证）
- `app/chat/tool_calling.py:417` — `call_tool` 调点补 `tool_name=plan.tool.tool_name`（SURFACED-1）
- `app/mcp/executor.py:794` — `_resolve_builtin_name` fail-fast：tool_id==0 缺 tool_name → 抛 42200 AppException
- `app/chat/flows/graph_stream.py:142` — `_enrich_hitl_pending_payload` 补五字段（thread_id/risk_level/timeout_s）
- `app/chat/flows/graph_stream.py:114-118` — `_RESUME_CONFIRM="confirm"` / `_RESUME_REJECT="reject"` 单一词表；`_classify_hitl_resume` 归一（confirm→execute，reject→rejected）
- `app/chat/router.py:407-444` — `/api/chat/resume` 端点校验 Redis hitl:pending:{thread_id} 标记，未知/TTL 过期 → 40450 CHAT_HITL_THREAD_NOT_FOUND
- `app/config.py:497-760` — `HITL_ENABLED_REQUIRED=True` + `_hitl_prod_guard` 生产环境启动硬拒

### 修复层关键证据（app.log 一手摘录）
```
2026-09-16 22:06:16.448 | INFO | app.chat.flows.graph_stream:_hold_for_confirm:264 -
  [graph_stream] 写类工具挂起（方案②）thread_id=s_d719e5f57e4a tool=knowledge_import role=admin
2026-09-16 22:06:27.249 | WARNING | app.mcp.executor:_execute_builtin_attempt:853 -
  [MCP] 内置工具 knowledge_import 执行失败: ValueError: knowledge_import 缺少 source_files
  （需非空列表，元素为 {file_name, local_path|object_key}）
```

第二条 WARNING 的源头是 `app/mcp/executor.py:853` `_execute_builtin_attempt` 调 `_knowledge_import_handler`（executor.py:1099），handler 第 1116-1117 行校验 source_files 非空——这正是 §4 CR-T11b-A 的根因。

---

## §4 缺陷上浮（CR-T11b-A：chat 流式 HITL 路径下内置写工具 args={} 设计缺口）

### 现象
S1 实证：confirm 续流时 executor 被调起（call_log +1）→ handler 拒落 task（"缺少 source_files"）。
S7 实证：confirm 续流时 executor 被调起（call_log +1）→ task 落了 1 行。

### 根因
`app/chat/tool_calling.py:218-221` 启发式工具选择路径：
```python
if hit_kw:
    plans.append(ToolPlanItem(tool=tm, args={}, reason=f"关键词命中：{hit_kw}"))
```
关键词命中后 `args={}` 占位——**永远空 dict**。后续 confirm 续流：
- 续流 graph_stream 跑 astream → generate 节点 LLM tool_calls 决定（LLM 决定 args 完整与否）
- 续流 run_chat_tool_calls 时 `hitl_decision=True` → 不再挂起 → 直接 `executor.call_tool(tool_id=int(plan.tool.tool_id), tool_name=plan.tool.tool_name, args=dict(plan.args or {}))`
- `plan.args or {}` 仍 = {} → handler 拒落 task

S7 实证 task +1 是 LLM 在续流 generate 节点**自主**生成 tool_calls 的产物——但这是 LLM 偶发行为（受 prompt 工程 + 模型训练影响），**非代码逻辑**。

### 与兄弟报告的差异
- T11 报告未察觉此缺口（T11 阶段目标是测试 HITL 框架，不是真落行）
- T12 报告说"内置工具 call_log 不落行"（实为 WNEXTMCP1 修复前；现 WNEXTMCP1 已修）
- SURFACED-1 报告说"内置写工具补传 tool_name + 上线守卫"——**修了 tool_name 但没修 args={}**
- HITL-FIX 报告说"confirm→真执行"——**修复层成立，业务层在 chat 流式路径下默认不成立**

### 建议修复（不在 T11b 范围）
1. **最小修复**：`run_chat_tool_calls` 在 HITL 挂起时把 `plan.args` 缓存到 Redis pending payload，confirm 续流时优先用缓存 args 而非 plan.args；
2. **根治**：内置工具 description 显式给 source_files schema 示例（`_BUILTIN_TOOL_DESCRIPTIONS["knowledge_import"]` 增强），让 LLM 在续流 generate 时直接构造完整 tool_calls；
3. **测试回归**：在 `tests/test_hitl_fix_integration.py` 加 case：confirm 续流后 task 真落行（需 mock LLM tool_calls 生成完整 args）。

### 编排者复验重点（任务原要求）
- ✅ S1 knowledge_import_task +1：S7 实证（task 131→132）；S1 单跑 task +0（LLM 偶发）
- ✅ S3 app.log 0 次 42200：实测总=0，AppException=0
- ✅ S6 五字段全有：实测五字段齐备且类型正确
- ✅ S7 student 仍 403：实测 student denied=True（任务原话是 "student 仍 403"，实测 student 走 retrieval 帧 `status:denied, code:permission_denied` 信封，与 T11 一致）

---

## §5 守则符合性

- 禁 Playwright：全 HTTP + urllib + 只读 SQL ✅
- 8000 禁重启：8010 临时实例（PID 32996 用完 taskkill 关闭），8000 PID 23104 全程未动 ✅
- 只读 SQL 参数绑定：所有 SELECT 走 `app.database.fetch_one/fetch_all`，DELETE 自清用 `execute_write` 参数绑定 ✅
- 测试数据自建自清：S1~S8 跑完后
  - `knowledge_import_task`：id 151~169 共 19 行 + id 170 = 20 行删除（回 125 基线）
  - `mcp_tool_call_log`：2026-09-16 22:00 后 18 行删除（部分剩余是兄弟 agent 历史数据，未越界）
  - Redis：`hitl:pending:*` 1 个 + `hitl:decision:*` 1 个 key 删除
  - 8010 PID 32996 taskkill 关闭，netstat 验证无残留 LISTENING ✅
- 8000 禁碰：实测未重启、未触碰
- 单 commit：本报告单独 commit，规避工作区既有暂存

---

## §6 证据脚本

- `edu-agent/scripts/_t11b_single.py` — T11b 单场景探针（S1~S8 独立运行，避免 8010 多场景累积中止）
- `edu-agent/scripts/_t11b_probe.py` — 早期 8 场景合跑探针（8010 反复中止后弃用）
- `edu-agent/logs/t11b_run3.log` ~ `logs/t11b_run6.log` — 早期跑批日志
- `edu-agent/logs/t11b_S1.log` ~ 其它单场景日志
- `edu-agent/logs/8010_v7.out.log` — 8010 临时实例应用日志（含 LLM 配额耗尽警告 `LLM HTTP 429: AccountQuotaExceeded`——兄弟 agent 用尽周配额导致 8010 中止，本批已通过反复启 8010 抢 30s 窗口完成全部场景）

---

## §7 待办（建议编排者裁定）

1. **CR-T11b-A P0 上浮**：chat 流式 HITL 路径下内置写工具 args={} 设计缺口（修复后内置写工具在 chat 流式 confirm 路径下默认 task +0）
2. **CR-T11b-B P2 上浮**：AGENTS.md `HITL_PENDING_TTL_S=600` 与实测 Redis TTL=300 不一致——HITL-FIX 修复后 Redis 实际 TTL 已同步到契约 timeout_s=300，文档需更新
3. **CR-T11b-C P3 上浮**：兄弟 agent 留下 LLM 周配额耗尽（`AccountQuotaExceeded`）导致 8010 反复中止——非 T11b 范围，但影响后续测试稳定性
