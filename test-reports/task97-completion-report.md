# task97（R5 缓存监控）完工报告

- **任务**：EduAgent 重构项目后端 —— R5 缓存监控（命中率可验证 + 与 task96 上下文水位联合看板）
- **前置**：task94/95/96 已验收；task97 接入 task95（deferred 延迟加载）、task27（prompt_cache 三层组织）、task96（ContextUsageMonitor）
- **状态**：✅ 全部 GWT 通过，契约测试 `tests/test_contract_task97.py` **19 passed**；task95/task96 契约测试 **34 passed**（无回归）
- **纪律**：基于最新 HEAD 单 commit（**未使用 `git read-tree --empty`**）；测试全 in-process 零真实 LLM（符合测试窗口纪律）

---

## 一、GWT 验收

### GWT① description_reviewer 改写存延迟层 + 摘要列表稳定 + admin_only 过滤 + schema 版本告警 + 只读缓存 60s
| 子项 | 落点 | 验收 |
|---|---|---|
| 改写存延迟层 + 摘要列表稳定 | `app/mcp/description_reviewer.py::apply_rewrite_to_deferred` 锚定 `summary_sentence=原首句` → 重写不改变前缀 key | `test_apply_rewrite_to_deferred_keeps_prefix_key`：prefix_key 重写前后一致 |
| 摘要列表稳定 | `app/mcp/deferred.py::build_summary_listing / stable_listing_key` | `test_summary_listing_stable_after_full_rewrite`：完整描述重写 → key 不变 |
| admin_only 过滤 | `build_summary_listing(include_admin_only=False)` 默认过滤 admin 工具 → 普通用户前缀不受 admin 工具变更影响 | `test_admin_only_filtered_from_prefix_by_default` |
| schema 版本告警 | `deferred.detect_schema_version_change` + `DeferredToolIndex.schema_alerts`（prev=None 不误报新工具） | `test_schema_version_change_alert` / `test_detect_schema_version_change_unit` |
| 只读缓存 60s | `REVIEW_CACHE_TTL=60` + `get_or_load(..., ttl=60)` 指纹失效重算 | `test_review_readonly_cache_ttl_60s_and_fingerprint`（验证 TTL 常量 + 接线） |
| per-server 熔断 + 60s 只读缓存 | task95 `executor.py` 已实现（CircuitBreaker 连续5失败→30s 快败；`_MCP_CACHE_TTL=60`）；task97 验证/集成而非重造 | GWT① 增量已闭环，未重复造轮子 |

### GWT② 多轮对话观察 /metrics：命中率持续上报 >50%
- `app/chat/generator.py::_report_cache_usage` 解析 `usage.prompt_tokens_details.cache_read/creation_input_tokens` + `prompt_tokens`，三值全 0 跳过；非流式 `call_chat` 与流式 `call_chat_stream`（已加 `stream_options.include_usage=True`）末帧均上报。
- `app/ai/cache_monitor.py` 用 **threading.Lock**（非 asyncio，因 generator 在 `run_in_executor` 工作线程调用），`record_llm_call_sync` 同步入口。
- 验收：`test_overall_hit_rate_exceeds_50_percent`（5 轮 cache_read=800/1000 → 命中率 0.8 > 0.5，且同步到 Prometheus `edu_cache_hit_rate` gauge）、`test_per_conversation_hit_rate_tracked`（分会话累计）、`test_generator_reports_cache_usage_to_monitor`（generator 真实上报入口）、`test_generator_skips_when_no_usage`（网关未回 usage 不上报）。

### GWT③ MCP 变更 → 命中率不受影响；模型切换 → 命中率下降且记录失效原因
- MCP 描述重写经 `apply_rewrite_to_deferred`（锚定首句）→ 前缀 key 不变 → 不记 `mcp_change` 失效 → 命中率不受影响（R3 deferred 生效）：`test_mcp_change_no_invalidation_when_deferred`。
- 模型切换（同 tier 内模型名变化）→ 记 `model_switch` 失效（根因可追溯），后续纯未命中使整体命中率下降：`test_model_switch_records_invalidation_and_drops_hit_rate`。
- 显式失效（compaction/context_edit 等）一律 `record_invalidation(reason,...)` 并 inc `edu_cache_invalidations_total{reason}`：`test_explicit_invalidation_recorded`。
- 命中率当 uptime 指标：低于 `HIT_RATE_ALERT_THRESHOLD=0.5` 即 `hit_rate_below_threshold()` 报 SEV。

### GWT④ 衔接 task96 ContextUsageMonitor → 联合看板
- `cache_monitor.joint_dashboard(session_id)` 惰性调 `get_context_monitor().snapshot()` 拼「上下文水位 + 缓存命中」，并把最近 usage_ratio 写入 `edu_context_usage_ratio` Gauge。
- 端点：`app/monitoring/router.py` 新增 `GET /api/metrics/cache-context-dashboard`（main 已 include `monitoring_router`）。
- 验收：`test_joint_dashboard_merges_context_water_level`（cache+context 双段）、`test_metrics_endpoint_exposes_cache_dashboard`（/metrics + 新端点均注册）。

---

## 二、批判承接核对
| 来源 | 批判点 | 闭合落点 | 验证 |
|---|---|---|---|
| task95 批判③ | deferred 接入 tool_specs 端到端 | `tests/test_contract_task97.py::TestCritique95DeferredToolSpecs`：tool_specs 形态输入 → 摘要稳定 + 完整定义按 (server_id,name) 独立缓存 + 前缀 key 重写不变 | passed |
| task96 批判② | context_edit 未接入 graph 决策链（仅观测） | `graph.py::context_edit_node`（compact→context_edit→plan），真正调用 `apply_context_strategy`（轻量保前缀→仍超才 compaction）并 record 到 task96 监控器；`plan_node` 消费编辑后上下文（此前 `state.compaction` 产出从未被下游使用，此处首次真正消费） | `test_graph_wires_compact_context_edit_plan` + `test_context_edit_node_runs_and_plan_consumes`（60→16 消息、删 1927 token、monitor 有样本、plan 消费「历史上下文」） |
| task96 批判③ | prefix 真实多轮观测 | `generator._report_cache_usage` 真实解析并上报 CacheMonitor | `test_generator_reports_cache_usage_to_monitor` |

---

## 三、竞品对标（真实 URL）
- **Claude Code prompt-caching**：
  - 文档：https://docs.claude.com/en/docs/claude-code/prompt-caching
  - 缓存命中/创建指标 + 三层组织（system/project/conversation）+ TTL；"Treat cache hit rate like an uptime metric: if it drops, something is wrong."
  - deferred tools 默认开启：server 连接/断开/改工具列表只追加内容、不打扰已缓存前缀（对齐本任务 R3 deferred）。
- 本任务对标落地：命中率当 uptime 监控（`HIT_RATE_ALERT_THRESHOLD=0.5` 低即 SEV）；每次前缀失效记录 `reason`（model_switch / mcp_change / compaction / context_edit / effort_change / prefix_change）以便定位根因。

---

## 四、实时语料 / 观测入口
- 指标（Prometheus）：`edu_cache_read_tokens_total` / `edu_cache_creation_tokens_total` / `edu_cache_prompt_tokens_total` / `edu_cache_hit_rate`（当 uptime）/ `edu_cache_invalidations_total{reason}` / `edu_context_usage_ratio`（联合水位）。
- 端点：`GET /metrics`、`GET /api/metrics/cache-context-dashboard?session_id=`。
- 单例入口：`app.ai.cache_monitor.get_cache_monitor()` / `record_llm_call(**)` / `record_invalidation(reason, ...)`。

---

## 五、交付文件清单（待 single commit）
- 新增：`edu-agent/app/ai/cache_monitor.py`、`edu-agent/tests/test_contract_task97.py`、`test-reports/task97-completion-report.md`
- 修改：`edu-agent/app/monitoring/metrics.py`、`edu-agent/app/monitoring/router.py`、`edu-agent/app/chat/generator.py`、`edu-agent/app/mcp/deferred.py`、`edu-agent/app/mcp/description_reviewer.py`、`edu-agent/app/ai/graph.py`

## 六、下一步
- 等待验收；验收通过后由编排者更新 `D:\.ai-hub\memory\project-handoff.md` 的 task97 行。
- 可选增强（非阻塞）：把 `edu_cache_hit_rate` 接入告警（低于 0.5 触发 SEV 通知）。
