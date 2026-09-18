# R12 完工报告：tool/learning 子代理工具调用 exact-pin 对齐（C-01）

> 执行 agent：R12（编排者逐断言独立实证验收轮）· 日期 2026-09-19 · 工作区 `E:\stu\project\stu\EduAgent实施手册`
> 对标资产：`.ai-hub/plans/kb-deep-1-orchestration.md` §5 F-C02-002-hermes（工具名/参数逐字段精确绑定、拒绝 LLM 自由发挥的模糊调用）+ TOP10 #9/#10
> ⚠️ 本文件为**新一轮 R12** 报告；上一轮 R12（LLM 工具决策接管）报告原件在 git `509496d:test-reports/R12-completion-report.md` 可溯，未丢失。
> 单写者锁 `edu-agent/scripts/eval/r12.lock` 已随完工删除。

---

## 1. 交付概览

| 项 | 内容 |
|---|---|
| commit | 主体 `90f7391`（feat(r)/R12-exactpin；基线 git tip `3779142`，主循环被测代码 = 3779142 工作树 + 本轮改动） |
| 差距清单 | 7 条（G1~G7，§2），全部收敛于 `app/ai/subagents/` |
| 对齐实现 | 新增 `tool_schemas.py` + runner 三段 exact-pin 校验 + q 精确绑定问题本体 + definitions.yaml schema 提示（§3） |
| 复验 | R20-b 双跑探针全量 100 样本：**残差 18 → 0**，Jaccard mean 0.8533 → **1.0**（100/100 全等），intent 分歧保持 0%（§4） |
| 测试 | 新增 22 例全绿；相关域回归 198 过 2 skip（§5） |

## 2. 现状审计：exact-pin 差距清单（逐条 file:line）

判据基准（kb-deep-1 §5 + TOP10 #9/#10）：工具名白名单精确匹配；参数逐字段精确绑定（类型/必填/域）；模糊调用 fail-closed 返结构化错误；调用可观测。

| # | 位置（审计时行号） | 现状 | exact-pin 差距 |
|---|---|---|---|
| G1 | `runner.py:42`（`_direct_tool_args`） | 正则 `（问题：(.*)）\s*$` 锚定串尾 | plan 节点（sixnode.plan）在 `（问题：X）` 后追加 skill/context_edit 块 → 正则必然失配 → 整段任务串兜底作 q。**R20-b 残差 18 条根因**（实测 new_retrieval_queries=「模板+（问题：X）+[历史上下文…]」拼接串，旧路径用原 query） |
| G2 | `runner.py:241-248`（`_parse_action`） | JSON 解析失败 → 大括号截取片段当 final | fail-open：模糊/畸形输出被静默接受，且回退片段丢失上下文 |
| G3 | `runner.py:361` | `action.get("tool")` 仅 truthy 检查 | 非字符串（dict/list/int）/空白/带前后缀空白的 tool 名直接进白名单比较，无类型精确校验 |
| G4 | `runner.py:368-374` | 白名单违规/服务未注入 → 一句"跳过" + continue | 软拒绝：无结构化错误码、无 allowed_tools 提示、拒绝不记账、无 fail-closed 终止路径；assistant 的 action 不入 messages（转录不一致，LLM 难自纠错） |
| G5 | `runner.py:377` | `handler(action.get("args") or {})` 零校验直派发 | 缺必填 q → 延迟到服务闭包才报错；别名字段（recall_memory 用 `query`）被静默接受；未知字段（search_knowledge 塞 top_k）被静默忽略；recall_profile 拼错字段 → 静默落默认关键词「学习画像 目标 偏好 规划」（检索语义被 LLM 拼写错误劫持） |
| G6 | `definitions.yaml:17-21 等` | system prompt 只说"用 X 工具"，无参数 schema | ACI 当 HCI 缺口：LLM 无逐字段绑定依据，prefetch 关闭时必然产出模糊调用 |
| G7 | `runner.py:396-407`（artifact payload） | 无拒绝事件记录 | 模糊调用不可观测，验收/排查无证据链 |

残差定位（`dualrun_results.before.json`，R02-tail 复验态）：18 条 jaccard<1 全部 `new_subagent_n=3`、intent∈{tool:14, learning:4}（chat_history 16 + edge_tool 2）——与 R02-completion-report.md 的移交结论一致（「子代理 search 的 q 应取用户问题本体而非任务串」）。

## 3. 对齐实现（diff 摘要）

**文件归属备案（报编排者）**：`app/ai/subagents/runner.py`（+125/-20）、`app/ai/subagents/tool_schemas.py`（新增 ~160 行）、`app/ai/subagents/definitions.yaml`（+24/-8）、`tests/test_contract_r12_exactpin.py`（新增 22 例）。**未触碰** retriever.py / langgraph_agent.py / graph.py / app/domains/** / config.py（红线自检通过；`_build_tool_services` 闭包为绑定权威，只读核对未改）。

1. **`tool_schemas.py`（新增，schema 独立成模块——对齐 ChatDev tool_spec 同构判据）**
   - `TOOL_ARG_SCHEMAS`：4 工具精确字段绑定，绑定权威 = `graph._build_tool_services` 各闭包真实消费字段（search_knowledge: `q` 必填；recall_memory: `q` + 可选 `top_k`∈[1,50]；recall_profile: `profile_query` + 可选 `top_k`；call_tool: `tool_name` 必填 + 可选嵌套 `args` 对象——嵌套内 schema 由 mcp.executor.registry 二次兜底，双层防御）。
   - `validate_tool_args`：五类拒绝 `not_an_object / missing_required / unknown_field / wrong_type / out_of_domain`，纯函数可单测。
   - `structured_rejection`：`EXACT_PIN_REJECTED` 结构化错误（reason/detail/claimed_tool/allowed_tools/args_schema/instruction），回灌 LLM 自纠错 + fail-closed 上交主上下文双用。
2. **`runner.py` 三段 exact-pin 校验（主循环）**：① 工具名类型/形态精确（非 str/空白/前后缀空白 → `invalid_tool_name`）② 白名单精确匹配（`unknown_tool` 携 allowed_tools）③ 参数 schema 逐字段（`invalid_args:*` 携 schema）。拒绝 → assistant+user 结构化错误对入 messages（转录一致，可自纠错）+ `rejections` 记账；连续 2 次（`MAX_CONSECUTIVE_VAGUE_REJECTS`）→ **fail-closed 终止：结构化错误作 summary 上交、ok=False、不烧剩余轮次**；成功派发重置 streak。`handler_unavailable`（环境性缺失）单独结构化告知、不计 streak。
3. **q 精确绑定问题本体（G1 承重修复）**：`_direct_tool_args` 改块边界感知贪婪提取 `（问题：(.*)）(?=\n\n\[|\s*$)`（上下文块以 `]` 收尾、其内部 `）` 不可能后随 `\n\n[`，贪婪回溯精确落在问题收尾 `）`；问题含括号/块序变化实测均正确），旧正则保留次选，整段兜底降为最终兜底（行为下限不劣于修复前）+ debug 打点。
4. **预执行参数同过 schema**：确定性 prefetch 的推导参数必须过 `validate_tool_args`（失败=代码缺陷 → error 日志 + 回退 LLM 决策循环，绝不把模糊参数打进检索/记忆服务）。
5. **`_parse_action` 契约收口**：解析失败回传原文（纯文本终答=设计内完成路径，优雅接受；真正的模糊「调用」由主循环三段校验拒绝）——解析与判定分离。
6. **`definitions.yaml`**：四个子代理 system prompt 补「参数恰为 {…}」精确 schema 行 + 头部 exact-pin 契约注释（与 tool_schemas.py 双侧同步声明）；artifact payload 增加 `exact_pin_rejections` 记账（G7）。

## 4. 复验：R20-b 双跑探针（全量 100 样本）

用法核对（r20b_dualrun_probe.py 头注）后执行：`cd edu-agent && .venv/Scripts/python.exe scripts/eval/r20b_dualrun_probe.py`。

**环境偏差（如实登记）**：
- 首跑 BGE-M3 CUDA 加载段**段错误**（EXIT=139，GPU 被并发进程占满 5.7/8.2GB 98%）；改进程级 `EMBED_BACKEND=cpu` 重跑（同一本地 BGE-M3/dim=1024，仅 device 变化；新旧两路径共用同进程 embedder，门槛口径不变；未改 config.py/.env）。
- **LLM 周配额 429（AccountQuotaExceeded，重置 2026-09-21）**：子代理总结轮/HyDE 改写/judge 生成层死亡。门槛指标恰不依赖该层——intent=规则路由 0-LLM、docs=预执行确定性检索（429 不影响工具执行，日志见 docs=150）；语义 30% 抽检 judge_failed 30/30（如实登记：**答案语义面本轮无证据**）。
- 主循环窗口（00:12:49–00:17:11）内 backend=3779142+本轮改动；summary 内 git_rev=d0fc59b 为汇总落盘时刻 HEAD（R-N2 报告 00:36 提交致 tip 前移），非主循环被测代码。R-N2 自证零分歧 + graph_expand 灰度默认关，归因不受污染。

| 指标 | 修复前（R02-tail 复验基线，before 备份于 `test-reports/r12-before-backup/`） | 修复后（2026-09-19 00:50） |
|---|---|---|
| docs Jaccard mean | 0.8533 | **1.0**（p50=p95=min=max=1.0） |
| Jaccard=1 条数 | 82 | **100** |
| Jaccard<0.5 条数 | 18 | **0** |
| **tool/learning 残差（子代理面）** | **18**（tool 14 / learning 4，sub_n=3） | **0** |
| intent 分歧率 | 0% | 0%（0/100） |
| need_search 分歧率 | 0 | 0 |
| error / unstable | 0 / 0 | 0 / 0 |

**机制证据（因果锁定）**：修复前残差样本 new_retrieval_queries=「基于问题给出检索要点（问题：X）\n\n[历史上下文…]」（任务串）；修复后样本 34/35/41/89 实测 new_q0=X（问题本体）且 old_doc_ids==new_doc_ids 全等。产物：`dualrun-summary.json`/`dualrun_results.json`（GridFS 制品 aid=6aad6bd7…，本地同字节副本）/`test-reports/dualrun-baseline.md`；运行日志 `test-reports/r12-r20b-rerun.log`；复跑命令同上。

## 5. 测试

新增 `tests/test_contract_r12_exactpin.py`（in-process + fake LLM/tool，不连真实依赖）：**22/22 绿**，覆盖 kickoff 四验收面——精确 pin 过（3：白名单派发逐字段断言/call_tool 嵌套透传/定义-校验双侧不漂移）、模糊拒（6：缺必填零派发+错误回灌携 schema/未知字段/别名字段/类型与取值域/空 tool 带 final 优雅收口/纯文本 final）、未知工具拒+fail-closed（5：unknown_tool 结构化携 allowed_tools 零派发/非 str tool/连续 2 次 fail-closed ok=False 且不烧轮次/streak 成功重置/拒绝记账入 artifact）、q 精确绑定（8：真实 plan 串/skill 块在前/问题含括号/旧形态/无标记兜底/learning profile_query/预执行参数过 schema/解析三态）。

相关域回归：task92/93/taskP1L/task24/task_a1/task_r01/artifact_store/agent_loop **111 过 1 skip**；task_a1*/task_r02/task_e1/chat_tool_calling/r12_tool_decision **72 过 1 skip**；chat_flow_args_fix **15 过**。合计 **220 过 2 skip，全绿**。

## 6. P0 自批判（≥3）

1. **复验环境非 LLM 活体**：LLM 周配额 429 使 after-run 生成层死亡。门槛指标（intent/docs）与修复面（确定性 q 绑定）恰不依赖该层，且机制证据直接锁定因果；但「LLM 活体下的严格同环境复跑」未完成（配额 2026-09-21 重置后可复跑验证），语义 30% 抽检 30/30 judge 失败，答案语义面本轮零证据。若活体 HyDE 改写与 raw 分叉，Jaccard 未必严格 1.0（before 基线中 old_rewrite==raw 的实测证据削弱此虑但不归零）。
2. **exact-pin 嵌套边界**：call_tool 嵌套 args 内部不校验（透传 executor registry 二次兜底，fail-closed 但会烧一次派发轮 + 一次 executor 解析）；嵌套 schema 机验归 MCP registry 面接管，本轮未做跨层联防测试。
3. **q 提取的模板耦合**：`_direct_tool_args` 兜底仍保留整段 input 作 q（无标记/异常输入），且提取正则与 plan 模板（graph.py，他人领地）强耦合——plan 模板变更可能再度失配；单测 REAL_PLAN_INPUT 是当前模板快照而非契约拉取，无自动漂移检测。schema 模块已注明绑定权威与双侧同步要求，但「同步」靠纪律不靠机验。
4. **fail-closed 上限与 maxTurns 的隐含前提**：`MAX_CONSECUTIVE_VAGUE_REJECTS=2` 需 maxTurns≥2 才可达；当前 4 个子代理定义（3~5）均满足，但未对「未来新增子代理 maxTurns<2」做防御性断言，fail-closed 会被轮次耗尽静默取代。

## 7. 批判承接核对

kickoff 明示「无承接项」。核对 `handoffs/taskR20b-kickoff.md` 与 R02-completion-report.md 移交条目：R02 报告「交由 R02-b 灰度期/W3 继续跟踪」「建议 R12/W3 接管（子代理 search 的 q 应取用户问题本体而非任务串）」——本轮 R12 即该移交项的承接执行（见 §2/§4），无其他未承接项带入。

## 8. 资产消费证据

- `.ai-hub/plans/kb-deep-1-orchestration.md`：§5 F-C02-002-hermes（exact-pin 范式/审批三件套）+ TOP10 #9（工具调用三级权限/供应链硬约束）+ #10（自持控制流/ACI 当 HCI）+ §7 ChatDev 判据 4（tool schema 独立成 spec 文件）——对齐实现三件套的直接设计来源（开工前先读，判据落 §3）。
- 代码定位：`app/ai/subagents/{runner.py,definitions.yaml}`（grep）、`app/ai/harness/sixnode.py`（fan_out 直连/子代理分野、plan 尾缀块格式）、`app/ai/graph.py::_build_tool_services`（schema 绑定权威，只读）、`app/mcp/executor.py::call_tool_with_retry`（嵌套兜底边界，只读）。
- 实证基线：`scripts/eval/r20b_dualrun_probe.py`（用法节）、`dualrun_results.before.json`（18 条残差逐条定位）、`R02-completion-report.md`（根因移交）、`R02-dualrun-reverify.md`/`r02tail-dualrun-baseline.md`（before 数字 0.8533/18）。
- `AGENTS.md`（红线/教训 9-11/测试账号）。
