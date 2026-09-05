# C2-② 批判验收报告 —— TOOL_DEFERRED_MODE 灰度受控实证

- 类别：批判 backlog 项 C2-②「TOOL_DEFERRED_MODE 灰度待真实流量窗口」——受控/离线替代实证
- 独立验证子 agent 验收日期：2026-09-05
- 目录：`edu-agent/test-reports/`
- 判定对象：`app/ai/tool_specs.py`、`app/chat/flows/agent.py:103`、`app/mcp/deferred.py`、`app/ai/prompt_cache.py`、`app/ai/cache_monitor.py`、`app/config.py:347`

## 结论

**✓ 闭环（受控实证）**。C2-② 登记原文为「实现完成，运行验证待真实流量窗口」——本轮在**受控环境离线实证**：证明 TOOL_DEFERRED 决策行为真实可走通、缓存计量可观测、灰度决策面可机验；真实代码路径全部走通（PASS 25/25）。**唯一未覆盖**：真实对话/真实 LLM 决策流量（离线禁 LLM），以及 G3 所需的「approved/overridden/denied 专用决策计数器」在代码中**不存在**，如实登记为灰度可观测性缺口（不影响本圆环判定，因 C2-② 原登记本就不承诺此计数器）。

## G1~G4 逐条（方法 + 真实输出证据 + PASS/FAIL）

### G1 DEFERRED 决策前缀行为真实可走通 —— PASS

方法：沿 agent 决策流实际使用的生产函数真实调用链（非 mock）——
`build_decision_prefix(deferred=settings.TOOL_DEFERRED_MODE)`（agent.py:103 同款传参）→ `expand_schema()` / `build_tool_expansion_message()`（决策后按需展开，即「确认前置决策 + 拦截/延迟阶段」）→ `app/mcp/deferred.DeferredToolIndex`（MCP deferred tool search）。数据源 = 真实 `BUILTIN_TOOL_SPECS`。

真实输出（节选）：
- `settings.TOOL_DEFERRED_MODE = True`
- deferred 前缀不含 `input_schema` / `properties` / `required`（前五条 PASS：前缀包含全部可用工具桩名；不含 schema；full A/B 模式含 schema；deferred != full 即确实剥离）
- 决策后展开：`build_tool_expansion_message("calculator")` 返回 `role=system` 独立消息 + `expand_schema` 返回完整 ToolSpec 含 `required` schema →「确认前置决策 + schema 延迟/拦截于执行前到达」，且**前缀在展开前后字节稳定**（schema 不进前缀）
- `expand_schema("__no_such_tool__") is None`（延迟阶段优雅降级）
- MCP 层：`DeferredToolIndex` 前缀为摘要列表（`contains_full_description(listing)=False`），`load_full` 按需取完整定义，完整描述重写（task33）后 `prefix_key` 稳定 `d59de1c5…`

**PASS（13/13）**。

### G2 缓存计量可观测 —— PASS

方法：真实 `PromptCache.set_stubs("project", …)` 由真实 BUILDIN 工具桩派生（`to_prompt_entry(deferred=True)`）；重复同请求验证第一次 miss / 第二次 hit；计数从 `cache.stats()` 读出；并用 `evaluate_hit_rate()` + `CacheMonitor.record_llm_call_sync()`（generator 热路径 `_report_cache_usage` 同一入口）佐证进入可观测通道。

真实输出（节选）：
- 首次 set_stubs：`added=[calculator, web_search, user_profile_lookup, code_runner, admin_user_impersonate, admin_broadcast_message]`，此后 `hits=0 misses=6 hit_rate=0`（**全 miss**）
- 二次相同请求：`added=[]`，此后 `hits=6 misses=6 hit_rate=0.5 invalidations=0`（**全 hit**，无失效事件）
- `evaluate_hit_rate`：`hit_rate=0.8333, sev.sev=False, level=OK`（高命中不触发 SEV）
- `CacheMonitor.stats().overall_hit_rate=1.0, calls=2`

**PASS（5/5）**。备注：`set_stubs` 计量当前由缓存消费方手动驱动（决策前缀真实计算走 `build_decision_prefix`+`ensure_min_prefix`），预期命中基数据源已被 generator 热路径的 `record_llm_call` 真实接入（O1/命中率当 uptime 通道）。

### G3 决策准确率可观测（灰度用）—— 部分（预言存在，专用计数器缺失）

方法：静态/取证 + 机验前置。
- 真实存在的观测通道（取证）：`agent.py` 决策流 `logger` 输出 `决策结果`（`need_search/query_rewrite/tool_plan/answer_direct`）——已是实决策结构化快照；`agent.py:103` 真传 `deferred=settings.TOOL_DEFERRED_MODE`；`CacheMonitor.stats()` / `evaluate_hit_rate` / OTel `cache_event` 为命中率观测（O1-②③ 已独立实证）。
- 灰度准确率可机验前置（真实执行）：deferred vs full **决策可用工具面一致**（`deferred 暴露工具` = `full 暴露工具` = `[calculator, code_runner, user_profile_lookup, web_search]`，且桩含 summary 供 LLM 决策依据）→ 灰度期间按 deferred 决策 LLM/规则下发的 `tool_plan` 与全量模式同面可比，可据此分析决策准确率。

**部分（4/5 断言）+ 1 缺口登记**：代码中**无** `approved / overridden / denied` 专用决策结果计数器，灰度分析决策准确率目前只能靠「决策结果日志（need_search/tools）+ 命中率统计 + 决策面对比」间接观察。`config.py` 已提供灰度开关本身（`TOOL_DEFERRED_MODE`，默认 True，可一键回退 False，见 backlog 登记）。此缺口不阻断 C2-② 原登记范围。

### G4 真实代码路径 —— PASS

全程无 mock 数据冒充：导入即用生产模块（`app.ai.tool_specs`、`app.ai.prompt_cache`、`app.ai.cache_monitor`、`app.mcp.deferred`、`app.config`），数据源为真实 `BUILTIN_TOOL_SPECS` 与真实 ToolSpec。仅决策 LLM 未真调（离线禁 LLM），已在报告醒目标注；deferred 决策-前缀→schema 展开→缓存计量→可观测全链真实可走通。决策前缀字节稳定断言（前缀在展开/重写前后不变）为逐字节真实比较。

## 关键机验数字

- 受控脚本 **PASS 25 / FAIL 0**
- 既有契约回归：`test_contract_task_c2.py` + `test_contract_task_c2_schema_registry.py` + `test_contract_task95.py` **43 passed**
- G1：deferred 剥离 schema（0 次 `input_schema` 出现）、决策后展开独立消息、前缀 key 稳定 `d59de1c5…`
- G2：首写 `misses=6/hits=0` → 二次 `hits=6/misses=6/hit_rate=0.5`；`evaluate_hit_rate hit_rate=0.8333 sev=False`；`CacheMonitor hit_rate=1.0`
- G3：deferred==full 决策工具面 `4/4` 同集

## 资产消费证据

读过（按 C2-② 必读清单）+ 普通 grep 取证：
- `app/mcp/deferred.py`（deferred tool search 前缀/完整定义 key 机制）
- `app/mcp/description_reviewer.py`（FAST 重写 → deferred 层 + 摘要 key 稳定）
- `app/ai/prompt_cache.py`（三层缓存 / `set_stubs` deferred 桩计量 / `evaluate_hit_rate`）
- `app/chat/flows/agent.py`（`build_decision_prefix(deferred=settings.TOOL_DEFERRED_MODE)`, 决策结果日志）
- `app/config.py`（`TOOL_DEFERRED_MODE: bool = True`）
- `app/mcp/__init__.py`、`app/mcp/schemas.py`
- `app/ai/tool_specs.py`（`to_prompt_entry(deferred)`、`SchemaRegistry.expand_schema`、`build_tool_expansion_message`）
- `app/ai/cache_monitor.py`、`app/chat/generator.py`（`_report_cache_usage` → `record_llm_call_sync` 热路径接线）
- `.opencode/plans/critique-backlog-tracker.md`（C2-② 段，v2 修正后无 C2-② 悬空）
- review skill 内核：`~/.agents/skills/tt/vendor/review/SKILL.md` + `reference/critique.md`

**自检发现与修复**：受控脚本初稿有两处断言笔误（①G2 第二次命中断言残留未定义变量 `si_before`；②G3 `to_prompt_entry` 断言对 dict 做字符串成员测试按 key 迭代返 False），均已在脚本内修正为序列化后比较并复跑 PASS（真实代码零改动，见「批判承接」注）。**代码本体零改动**（无 diff）。

## 自检三视角（review skill 内核）

- **交互态**：deferred 决策链路状态机闭合格——决策前缀建立（`build_decision_prefix`）→ LLM 决策仅见桩 → 工具被选中后 `expand_schema`/`build_tool_expansion_message` 产生「展开（schema 补全）」态 → schema 以独立消息注入后续请求而不触碰前缀；前缀 byte 稳定态贯穿。MCP `DeferredToolIndex` 同理：摘要列表常驻 / `load_full` 按需。G2 体现缓存态：first-miss → second-hit。
- **边界**：`expand_schema`/`build_tool_expansion_message` 未知工具 → `None`（不注入、决策前缀不受污染）；admin_only 工具不进普通用户前缀（`specs_for_access` 过滤有既有 C2 测覆盖）；`set_stubs` 重复注册不产生整层失效事件；前缀超预算裁剪行为离线可测。
- **错误反馈**：deferred 决策 LLM 失败时 `agent.py` 回退 `AgentPlan(need_search=True,…)` 并 `logger.warning`；决策输出非法重试后保守回退检索；expand 未知工具静默降级为不注入（由真实 MCP 兜底）。以上在既有 C2/G1 契约测试与诱因代码中可见，受控实证覆盖未知工具降级分支。

## 批判承接核对（对照 C2-②）

C2-② 三段式对照：
| C2-② 项 | 覆盖 | 证据 |
|---|---|---|
| 修复措施：`TOOL_DEFERRED_MODE=True` 已定义 + `tool_specs.to_prompt_entry(deferred)` 前缀只放 name+summary + schema 选中才展开 | ✅ | G1 全部断言 + 脚本 `TOOL_DEFERRED_MODE 默认开启` PASS |
| 验收指标：`prompt_cache.cache_meter/evaluate_hit_rate` 计量命中率且 SEV | ✅ | G2 `evaluate_hit_rate hit_rate=0.8333 sev=False` + `CacheMonitor hit_rate=1.0` |
| 未覆盖：「灰度观察决策准确率」需真实对话/真实 LLM 流量窗口 | ⚠️ 受控替代 | 决策面无 LLM 无法真调；G3 提供「deferred vs full 决策工具面一致」机验前置 + 决策结果日志通道取证，**approved/overridden/denied 专用计数器不存在**（登记缺口，建议灰度期接一计数器或复用 need_search/tools 决策日志分析） |
| 回退路径：必要时 `TOOL_DEFERRED_MODE=False` | ✅ | `config.py:347` 布尔开关存在，full A/B 前缀模式实测包含 schema（`deferred=False` 路径真实可用） |

> 注：受控脚本为一次性验收临时件，按规则已清理；上述 G1–G4 机验数字均为该脚本一次性真实执行输出，可通过 `cd edu-agent && .\.venv\Scripts\python.exe -m pytest tests/test_contract_task_c2.py tests/test_contract_task_c2_schema_registry.py tests/test_contract_task95.py -q`（43 passed）复现 C2 静态覆盖。

## 诚实标注

- 决策 LLM 未真调（离线）；因此「决策准确率」本身（对真实 query 的选择质量）未能端到端量化，仅验证：真实代码路径可走通 + 决策面不因 deferred 收缩 + 命中率计量可观测。真实流量的准确率对比仍需 C2-② 原窗口（或灰度期持久化决策结果日志后离线分析）。
- `approved / overridden / denied` 专用决策计数器在代码库中不存在（grep 仅命中 PermissionDeniedError 等无关项）——已如实登记为灰度可观测性增强建议，不编造。