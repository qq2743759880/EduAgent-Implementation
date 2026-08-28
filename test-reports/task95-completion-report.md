# task95 完工报告 — MCP 增强 R3：延迟加载 / 认证 / 重连 / 动态更新 / 子代理隔离

> 角色：EduAgent 重构项目【后端 + 数据库开发者】
> 并行组：W3（与 task93 skill runtime 并行，互不冲突）
> 修订来源：`.opencode/plans/self-critique-ai-agent-vs-competitors.md` 维度 2 / 维度 9 + `ai-agent-revision-plan.md` R3
> 完成时间：2026-08-27 ｜ 测试窗口纪律：全程零真实 LLM 调用（测试均为 in-process 假实现）

---

## 〇、批判承接核对（self-critique 维度 2 / 维度 9 → 落地映射）

| 批判要点（维度 2 / 9 结构性缺陷） | 本报告落地实现 | 交付文件 |
|---|---|---|
| 工具加载：全部 MCP 描述进 system prompt → 缓存必失效 | **deferred 延迟加载**：前缀只放「name + 一句话摘要」，完整描述按需拉取（不进前缀） | `app/mcp/deferred.py` |
| 维度 9 失效清单：未识别「MCP 描述变更」会破坏前缀 | 摘要列表 key 只依赖 name + 首句；重写完整描述 → key 不变 → 前缀不失效（已单测验证） | `app/mcp/deferred.py` + 复用 `app/ai/prompt_cache.py`（project 层） |
| 认证：缺 OAuth / API key | API key 注入 + OAuth2 Authorization Code + refresh token grant；认证头自动构造 | `app/mcp/auth.py` |
| 连接可靠性：仅超时 + 熔断，缺自动重连 | 自动重连：stdio 进程退出 / HTTP 会话过期 → 指数退避重连（≤5 次，上限 30s） | `app/mcp/reconnect.py` |
| 动态工具更新：需重启才感知变更 | `DynamicToolRegistry`：diff 计算 added/removed/updated，内存索引更新，不重启会话 | `app/mcp/dynamic_update.py` |
| 隔离：仅 admin_only 过滤，缺子代理级隔离 | `MCPScope` + `resolve_subagent_tools` / `filter_main_context_tools`：子代理独占 server 工具不进主上下文 | `app/mcp/isolation.py` |
| 结果控制：仅 300-500 字截断 | per-tool 结果大小限制（默认 4000 字符，超限截断 + 告警标记） | `app/mcp/isolation.py` |

维度 2 / 9 的 3 个结构性缺陷中，本任务覆盖其中两项根因（MCP tool search 缺失、缓存失效管理缺 deferred 协同），并实现竞品要求的认证/重连/隔离能力。

---

## 一、竞品对标（强制：每条均引用真实竞品文档与数据）

### 1. Claude Code — prompt-caching（deferred tools 保护前缀）
- 文档：`https://docs.claude.com/en/docs/claude-code/prompt-caching`
- 原文引用（self-critique §〇 已真实抓取）：
  > "Tools loaded into the prefix: any change to them invalidates the cache. Deferred tools, the default on supported models: a server connecting, disconnecting, or changing its tool list only appends new content and doesn't disturb anything already cached."
- 落地：`deferred.py` 的 `build_summary_listing()` 只把 `name + 首句摘要`（≤80 字/条）写入前缀，`load_full_spec()` 在决策 LLM 选定工具后才拉取完整描述；`listing_key()` 稳定 key 保证「重写描述不破坏前缀」。契约测试 `test_cache_prefix_not_invalidated_on_rewrite` 用 `app/ai/prompt_cache.py` 的 project 层直接验证：重写描述后 `invalidations_list(layer="project") == []`。

### 2. Claude Code — mcp（OAuth / 自动重连 / 动态更新）
- 文档：`https://docs.claude.com/en/docs/claude-code/mcp`
- 原文引用（self-critique 证据表）：MCP server 支持 **OAuth 认证、API key、受管配置（allowlist/denylist）**；以及**自动重连**（server 退出后自动恢复）、**动态工具更新**。
- 落地：`auth.py`（`AuthConfig` / `OAuthClient` / `build_auth_headers`）+ `reconnect.py`（`with_reconnect` + 指数退避）+ `dynamic_update.py`（`DynamicToolRegistry`）。

### 3. Claude Code — sub-agents（mcpServers 字段隔离）
- 文档：`https://docs.claude.com/en/docs/claude-code/sub-agents`
- 原文引用（self-critique 证据表）：子代理 25 个 frontmatter 字段含 `mcpServers`，工具不进主上下文。
- 落地：`isolation.py` 的 `MCPScope.mcp_servers` + `filter_main_context_tools()`，契约测试 `test_main_context_excludes_subagent_only_servers` 验证子代理独占工具不泄漏进主上下文。

---

## 二、交付物与验收（GWT ①②③④）

### 验收标准对照
| # | Given / When / Then | 实现 / 测试 |
|---|---|---|
| ① | Given MCP 工具列表变更，When 会话中，Then 缓存前缀不受影响（deferred 语义） | `TestDeferredToolLoading`：`test_summary_listing_stable_after_full_rewrite`、`test_cache_prefix_not_invalidated_on_rewrite`、`test_per_tool_full_def_cache_independent_of_listing` |
| ② | Given server 进程退出，When 检测，Then 自动重连（指数退避 ≤5） | `TestAutoReconnect`：`test_recovers_after_transient_failures`（3 次失败→退避 [1,2,4]）、`test_exhausts_after_max_retries`（5 次后抛 `ReconnectExhausted`，上限 30s） |
| ③ | Given 子代理配置 mcpServers 子集，When 解析，Then 仅该子代理可见，主上下文不含这些工具 | `TestSubagentIsolation`：`test_main_context_excludes_subagent_only_servers`、`test_subagent_resolves_its_own_subset`、`test_per_tool_result_truncation` |
| ④ | Given OAuth 配置，When 启动，Then 自动走认证流程并注入请求 | `TestOAuthAndApiKey`：`test_api_key_header_injection`、`test_oauth_bearer_injection`、`test_oauth_refresh_grant`、`test_authorization_url_constructed`、`test_ensure_token_refreshes_when_expired` |

### 测试结果
```
tests/test_contract_task95.py ............  20 passed in 0.18s
```
- 全量 20 个用例通过，覆盖 GWT①②③④ + 动态工具更新监听（R3(5)）。
- **零真实 LLM / 零真实 MCP 连接**：`reconnect` 用注入 `_FakeSleep` + `_FlakyConnect`，`auth` 用注入 `fake_post`，`prompt_cache` 纯内存；符合测试窗口纪律（12:00–14:00 / 18:00–次日 9:00 之外仅用假实现）。

---

## 三、交付文件清单（task95 独占，未触碰 task33 / task27 模块）

新增 / 修改（均位于 MCP 层，与 task93 的 skills 层互不重叠）：
- `edu-agent/app/mcp/deferred.py` — 延迟加载（摘要常驻 / 完整描述按需 / 前缀 key 稳定）
- `edu-agent/app/mcp/auth.py` — OAuth(Authorization Code + refresh) + API key 注入
- `edu-agent/app/mcp/reconnect.py` — 自动重连（指数退避 ≤5，上限 30s）
- `edu-agent/app/mcp/dynamic_update.py` — 动态工具更新监听（不重启会话）
- `edu-agent/app/mcp/isolation.py` — 子代理级 mcpServers 隔离 + per-tool 结果大小限制
- `edu-agent/app/mcp/__init__.py` — 导出新模块（仅追加 imports，未改既有逻辑）
- `edu-agent/tests/test_contract_task95.py` — 契约测试（20 passed）

复用（只读引用，未修改）：`app/ai/prompt_cache.py`（project 层前缀失效检测）。

并行纪律确认：task93（skills 层 `app/ai/skills/*`）已单独提交（335c0e5）并等待验收；本任务文件全部位于 `app/mcp/*`，与 skills 层无共享文件冲突，符合「双后端并行、各自独占文件域」要求。

---

## 四、衔接与后续依赖
- **task97（R5 缓存监控）**：依赖本任务的 deferred 前缀 key。建议 task97 直接在 `prompt_cache` 的 project 层观察 `invalidations_list(layer="project")`，验证 deferred 后「工具描述变更」不再产生失效事件（本报告已验证此不变量）。
- **task33 改造（R3 部分）**：描述体检重写应写入 `load_full_spec` 取用的完整描述字段，保持「摘要列表（name+首句）」稳定——即 R3 设计变更点 2（rewrite 描述 → 更新延迟加载的完整描述，不进前缀）。本任务已为 task33 预留接口，二者通过 `deferred` 模块衔接，互不耦合。
- **子代理运行时（task92 R1）**：`isolation.MCPScope` 可直接被 `app/ai/subagents/runner.py` 的 `SubagentSpec` 复用，将 `mcp_servers` 字段映射到子代理工具可见域，实现竞品 `mcpServers` 隔离语义。

---

## 五、纪律声明
- 测试窗口纪律：本次执行时间落在禁止真实 LLM 时段，全部测试用 in-process 假实现，无任何真实模型 / MCP 远程调用。
- 单任务单提交：本任务提交仅含上述 7 个 task95 独占文件，未纳入 task93（已单独提交）或未完成任务。
- 未调用 Workflow()；手工按 dev-standard.mjs 八阶段推进（explore → design → implement → test → report → commit → sync → 停下等验收）。
- 下一步：**停下，等待编排方验收 task95**。验收通过后，方可进入后续 task（task97 等视编排顺序）。
