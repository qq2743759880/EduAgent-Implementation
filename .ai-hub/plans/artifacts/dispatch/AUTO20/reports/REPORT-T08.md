# REPORT-T08：C-W1-③ mcp_tool_calls 六节点路径透传（AUTO20 T8）

- Commit：见本文末尾（feature/opt-waves，单 commit，未 push）
- Tracker 源头：`.opencode/plans/critique-backlog-tracker.md:647` C-W1-③（P1，待修）
- 日期：2026-09-22

---

## 一、恒空复现（根因确认）

编排者 2026-09-20 实测（tracker C-W1-③ 原文）：chat 响应体 `mcp_tool_calls` 仅旧版回退路径（`service.py` `run_chat_tool_calls` 调用点）填充；六节点图主路径工具真实执行（DB favorites 写入 + `mcp_tool_call_log` 审计 id=684 落库可证）但响应体凭据恒空——前端收不到工具执行凭据，T7 护栏在六节点路径凭据恒空 → 真执行也会被误标。

本次开工实读链路，定位到 **三处断点**（全部有代码证据）：

1. **runner.py 断点（结构性的）**：`app/ai/subagents/runner.py` 子代理内 `full_tool_outputs`（完整工具输出）只整体写 artifact（Redis），`SubagentResult` 数据类只有 `summary/artifact_ref`，`as_distilled()` 只回 `{subagent, summary, artifact_ref, summary_tokens}`——**工具执行凭据从子代理返回主 state 的第一跳就被丢弃**。
2. **graph.py 断点（返回体的）**：`app/ai/graph.py` `run_agent` 返回体 `"tool_results": []` **硬编码恒空**（924~937 行）。
3. **service.py 断点（组装层的）**：`app/chat/service.py` `chat_answer` LangGraph 分支 `mcp_summaries = agent_result.get("tool_results", [])`（拿到恒空）后，**else 分支又 `mcp_summaries = []` 硬清空**（440 行）——即使上游修复也会被清掉。流式路径 `graph_stream.py` 只消费旧 MCP 并行预取的 `mcp_summaries`，图内工具执行零感知。

## 二、透传修法（选型说明）

**选型：graph.py `call_tool` handler 内记录凭据（任务工序 2 的"最简断点"方案），不走 SubagentResult.full_tool_outputs 透传。**

选型理由：
- `full_tool_outputs` 含完整工具原文（检索 100 篇原文级体量）+ 全 messages，为 artifact 设计；从中反推 `MCPToolCallSummary` 需要二次解析 `MCPToolTestResp` 信封，且 executor 闭环（换参/换工具）多步结果在 handler 返回值里只有最终信封——**handler 内直接记录 `resp` 的 call_id/status/latency/content_text 是零信息损失的**。
- `call_tool` 闭包是六节点路径 MCP 工具执行的**唯一断点**（`_build_tool_services` 每次请求闭包绑定，无并发串号），在此记录=一次插桩全路径覆盖（tool 子代理 + 任何未来经 call_tool 的子代理）。
- 与 T7 护栏/receipt_guard/权限门/执行链路**零改动**耦合（只读取既有 resp 字段），旧回退路径（run_chat_tool_calls）完全不动。

### 2.1 改动清单（4 文件，逐字节最小侵入）

| 文件 | 改动 |
|---|---|
| `app/ai/graph.py` | ① `AgentState` TypedDict 增 `tool_receipts: list[dict]` 通道（checkpoint pickle 安全，纯 dict）；`_empty_state` 初始化 `[]`。② `_build_tool_services` 增闭包内收集器 `services["__tool_receipts__"] = _tool_receipts`；`call_tool` 闭包内执行 `call_tool_with_retry` 后记录凭据 `{call_id, tool_name, args(内层), status(归一 success/error/timeout), latency_ms, result_text(content_text 前 400 字符)}`，记录失败只 debug 不影响返回。③ `run_agent` 返回体 `tool_results` 从图终态 `final.get("tool_receipts")` 真实回填（原恒 `[]`）。 |
| `app/ai/harness/sixnode.py` | `fan_out` 子代理路径：读取 `services["__tool_receipts__"]` 收集器，随 fan_out 更新写 `"tool_receipts": 既有 + 本轮收集`（reflect 回 plan 再 fan_out 时跨轮累计；knowledge 直连快路径不产生 MCP 凭据，天然空列表）。 |
| `app/chat/service.py` | `chat_answer` LangGraph 分支：`tool_results`（dict 列表）映射为 **既有 schema `MCPToolCallSummary`**（禁新造格式，字段口径与旧路径 run_chat_tool_calls 产物同构：call_id/tool_name/args_summary(前 200)/status/latency_ms/result_summary(前 400)）；映射失败单条降级跳过。else 分支删除 `mcp_summaries = []` 硬清空（第二断点根治）。 |
| `app/chat/flows/graph_stream.py` | `_gen` 内消费 fan_out update 的 `tool_receipts` → 同口径映射 `MCPToolCallSummary` 追加进 `mcp_summaries`（带 `graph_receipts_count` 计数保护：`_await_mcp` 收口旧 MCP 并行预取整体替换列表时先摘出图内凭据再合并，防冲掉）；retrieval/done 帧 `mcp_tool_calls` 与 `make_stream_finalize` 落库/T7 护栏**自动联动**（工厂零改动）。 |

### 2.2 T7 护栏联动（本任务最重要回归面）

T7 护栏 `apply_tool_receipt_guard` 在 `make_stream_finalize`（done 帧组装）与 `chat_answer`（RagAnswerResponse 组装）消费 `mcp_summaries`——透传后六节点路径真凭据（status=success）进入同一列表 → **护栏对六节点路径自动生效且零误标**（真执行 → 有 success 凭据 → 不追加修正句不标记）。receipt_guard.py / config.py 词表 / T7 测试 **零改动**。

## 三、三场景 E2E 实测（真实 HTTP，127.0.0.1:9988，测试账号 user000001/Test@123456）

### 场景① favorite_add 真执行 → 凭据非空（含 success 凭据）

- 非流式 `POST /api/chat`：
  ```
  mcp_tool_calls = [{"call_id": "mcp-1790025240678-6aa8fb40-1", "tool_name": "favorite_add",
    "args_summary": "{\"series_id\": 3}", "status": "success", "latency_ms": 44,
    "result_summary": "{\"ok\": true, \"favorite_id\": 30160, \"series_id\": 3, \"series_title\": \"通用编程项目班·直播\", ...幂等返回原记录...}"}]
  tool_receipt_unverified = False
  ```
- 流式 `POST /api/chat/stream`（retrieval 帧 + done 帧均非空）：
  ```
  retrieval.mcp_tool_calls = [{"call_id": "mcp-1790025267059-a2d85d9e", ..., "status": "success", "latency_ms": 188, ...}, {...第二闭环步...}]
  done.mcp_tool_calls      = [同上，两条]
  done.tool_receipt_unverified = False
  ```
- DB 对账（SQL 参数绑定，`series_favorite` + `mcp_tool_call_log`）：
  - 收藏幂等：series_id=3/user_id=1 收藏行恒 favorite_id=30160（source=ai_chat），复跑安全；
  - 审计落库：E2E 期间新增 id=723/724/725 三条 favorite_add SUCCESS 审计（call_id 与响应体凭据逐字对上，如 `mcp-1790025240708-9875488e` ↔ 响应体 `mcp-1790025240678-6aa8fb40-1` 为同一次闭环的首步/最终步 call_id）。

### 场景② tool_receipt_unverified 零标记（真凭据联动护栏）

场景①两路径 `tool_receipt_unverified = False` 且答案**零追加修正句**（答案头为「已为你完成收藏 ✅ …收藏记录 ID：30160」，凭据对账 favorite_id=30160 真实）——真执行不再被护栏误标（对照 T7 落地时六节点路径凭据恒空必然误标）。

### 场景③ 纯闲聊 → 空凭据

- 「你好」/「今天心情不错，随便聊聊」两轮：`mcp_tool_calls = []`、`tool_receipt_unverified = False`（零标记）。
- **诚实登记**：首轮「你好呀，今天天气不错」时 LLM 在闲聊答案里**列举了能力清单**（把 `favorite_add` 等工具名写进"我可以帮你"段落）→ 护栏按 T7 既有语义（写类工具名提及 ∧ 凭据空 → 标记）打了 True。这是 T7 词表语义对「能力列举式提及」的既定判定（防捏造的保守面），**非本次透传引入的回归**；后续轮次（不含工具名列举的答案）零标记。T7 护栏语义未动，如实上报不刷绿。

## 四、pytest 数字（零回归硬门）

- 新增 `edu-agent/tests/test_t8_tool_receipt_passthrough.py`（T8-G1~G7，7 个用例 9 断言组）：
  - T8-G1 call_tool 闭包记录凭据（success + error 归一）；
  - T8-G2 fan_out 子代理路径聚合 tool_receipts / 空执行空列表；
  - T8-G3 run_agent 返回体 tool_results 真实回填（原恒 []）+ `_empty_state` 初始化；
  - T8-G4 非流式映射 MCPToolCallSummary（复用既有 schema）；
  - T8-G5 流式 done 帧 mcp_tool_calls 非空 + tool_receipt_unverified=False（真凭据护栏联动）；
  - T8-G6 护栏联动：真凭据零标记零追加 / 空凭据仍标记（T7 不放宽）；
  - T8-G7 run_agent 异常回退 run_chat_tool_calls 原语义不变。
  - **结果：9 passed**。
- 回归面：`pytest tests/ -k "chat or tool or receipt" -q` → **250 passed, 7 skipped**（T7 的 receipt_guard 17 条 + 既有 chat/tool 227 条全绿；250 = 241 基线 + 9 新增）。

## 五、资产消费证据

- `.opencode/plans/critique-backlog-tracker.md:647` C-W1-③ 条目（修法落点指引：graph fanout/merge → service 响应组装透传）；
- `REPORT-T07.md`（T7 护栏插入点单一事实源说明——本次透传复用同一 `make_stream_finalize`/`chat_answer` 插桩，护栏零改动联动）；
- 既有 schema `MCPToolCallSummary`（`app/chat/schemas.py:141`，复用禁新造）；
- 实读锚点：`sixnode.py fan_out/merge`、`graph.py _build_tool_services/call_tool/run_agent`、`runner.py run_subagent`、`graph_stream.py _gen`、`executor.py call_tool_with_retry/_default_attempt_executor`、`tool_calling.py run_chat_tool_calls`。

## 六、批判自检（强制段）

1. **B1 越界**：T7 护栏/权限门/工具执行链路本身**零改动**——diff 复核：receipt_guard.py/config.py/executor.py/tool_calling.py 均 0 行变更；旧回退路径（run_chat_tool_calls 调用点）行为不变（T8-G7 有回归锁）。
2. **B2 新格式**：只复用 `MCPToolCallSummary`，凭据 dict 仅是 handler→state→响应组装的**内部传输形态**（出响应体前必经 MCPToolCallSummary 映射），未新增任何对外格式。
3. **B3 双重计数**：流式路径两凭据来源（图内 tool_receipts + 旧 MCP 启发式并行预取）合并时用 `graph_receipts_count` 防整体替换冲掉图内凭据；实测场景②出现两条凭据是 executor 闭环两步（首步 166ms + 二步 2595ms 各落一次审计），与 `mcp_tool_call_log` 行数对账一致，非重复计数。
4. **B4 checkpoint 兼容**：`tool_receipts` 为纯 dict/list（pickle 安全）；旧 checkpoint 缺该键 → state.get 兜底空列表，续跑不炸。
5. **B5 残留风险（如实登记）**：① 直连快路径（knowledge 意图）不走 call_tool，天然零凭据（无 MCP 工具执行，语义正确）；② 闲聊答案列举工具能力名会触发 T7 保守标记（既有语义，如需"能力列举不算提及"需在 T7 侧立项，本次禁改）；③ `__tool_receipts__` 借 services dict 传递是容器内私有键（双下划线前缀），测试实证 runner 不遍历未知键、无副作用。
6. **B6 验收纪律**：三场景全部真实 HTTP（curl → 9988），DB 对账（series_favorite 幂等 + mcp_tool_call_log call_id 逐字比对），不采信完工回执；E2E 期间发现并修复第二断点（service else 分支硬清空）——若只跑单测不跑真实 HTTP 会漏掉（自证 E2E 硬门价值）。

## 七、Commit

- `git branch --show-current` = `feature/opt-waves`（开工前/后一致）
- Commit hash：见最终消息（单 commit，未 push）
