# vault②「agent架构」精读报告 3：编码 Agent × 可观测 × 安全 × Skill 生态

> 精读员产出，2026-09-13。覆盖 20 张卡（F-C03×6 / F-C09×3 / F-C10×3 / F-C04 / F-C05 / F-C08 / S×2 / M×2 / P×1），全部逐节精读全文（非标题）。
> 遵守库根 AGENTS.md v1.4：溯源必带、禁编造、读不了的标注 `[未达]`。
> **链接核读状态**：S-001 原文（anthropic.com）WebFetch 成功；S-002 README（raw.githubusercontent.com）成功；github.com 直连 ECONNREFUSED、raw 的 codex AGENTS.md 超时——改用**本地一级事实源补偿核读**：`E:/stu/tools/codex/AGENTS.md`（原文摘录验证）、`corpus/repos/deepseek-harness/repo/SAFETY.md`（原文通读）、`E:/stu/tools/pi/README.md`（安全节 grep 验证）。各 F 卡内 DeepWiki/仓库 URL 均属 github 系未逐一复抓（卡内已记录 2026-09-08/09 各自 HTTP 200 实测）。

---

## 第一部分：F-C03 CLI/编码 Agent 系列（6 卡）

### 1. F-C03-001 claude-code

**核心定位**：CLI 编码 Agent（source-leak 通道，无官方 repo，Tier3 数据源）。查询引擎驱动 + 60+ 工具生态 + LSP 代码智能。TypeScript（claude-js v1.0.2），绑定 Anthropic API。

**机制细节**（带卡内引用）：
- **agent 主循环**：QueryEngine.ts（48KB，1240+ 行）管会话状态/工具权限/成本追踪/错误重试；query.ts（69KB）实现核心循环——用户输入 → `fetchSystemPromptParts` 聚合系统提示 → Claude API → 解析工具调用 → ToolUseContext 执行 → 观察 → 循环；`categorizeRetryableAPIError` 自动重试（卡 §arch-orchestration，溯源 repo:src/QueryEngine.ts / src/query.ts）。
- **系统提示多层聚合**：工具定义（60+ 工具 name/description/schema）+ 环境信息（cwd/OS/Git）+ 记忆（memdir/）+ 技能 + 系统指令（asSystemPrompt）+ slash 命令技能（卡 §arch-prompting）。
- **子 agent**：AgentTool + AgentDefinition，agents/ 目录定义（`loadAgentsDir.ts`）。
- **计划-执行分离**：EnterPlanModeTool（只读）→ 用户确认 → VerifyPlanExecutionTool 验证执行。
- **文件历史快照**：fileHistory + FileStateCache，agent 修改文件前自动快照，可回滚任意版本。
- **上下文压缩**：SyntheticOutputTool 合成输出压缩历史 + CompactBoundaryMessage 会话边界。
- **技能系统**：SkillTool/DiscoverSkillsTool，技能经系统提醒注入。

**安全方法论**（本卡重点）：
- **运行时权限门**：PermissionMode + CanUseToolFn + SDKPermissionDenial（溯源 `src/hooks/useCanUseTool.ts`、`src/entrypoints/agentSdkTypes.ts`）。每个工具调用前检查权限，敏感工具（Bash/FileEdit）弹确认对话框，用户可选 允许/拒绝/始终允许/始终拒绝；权限模式可切换（只读/全自动/按需确认）。
- **隔离层**：Worktree 隔离（EnterWorktree/ExitWorktree，agent 在独立 Git worktree 操作不污染主区）；计划模式=只读模式；environment-runner/ + self-hosted-runner/ 沙箱执行；McpAuthTool MCP 连接认证；upstreamproxy/ 网络代理控制。
- 卡内对比结论：claude-code 是**运行时权限确认**路线（对照 codex 的 OS 级沙箱、letta 的 Git 签名）。

**可观测**：cost-tracker.ts（10KB）+ accumulateUsage token 统计实时费用；getInMemoryErrors 错误日志；headlessProfiler 性能分析；sessionStorage + recordTranscript 完整 transcript 持久化（可恢复/重放）。无独立评估框架（OverflowTestTool 是上下文边界测试工具）。

**卡内链接**：全部为本地 source-leak `repo:file:` 锚点（无 URL 可抓）；corpus 留档 Repomix 1.92M tokens + codemap 242KB。

**对 EDU 的可执行判据**：
1. EduAgent 若做 agent 化批改/答疑执行体，工具调用前必须过统一权限门（对应现有 admin 三段守卫：无 token 跳登录→me 校验→失败仍跳登录），且敏感操作提供"始终允许"白名单以免打断教学流程。
2. 批改/生成类写操作引入"计划模式"等价物：先只读生成批改方案，教师确认后再落库。
3. 学生提交文件类操作前置自动快照（对齐 fileHistory 模式），保证可回滚——呼应 EDU 现有"实证可重跑"纪律。
4. 系统提示按 fetchSystemPromptParts 模式分层聚合（工具定义/角色/记忆/技能），而非单一大 prompt。
5. 每会话成本追踪（token+费用）入 transcript，为按院系计费/限额打基础。

---

### 2. F-C03-002 codex

**核心定位**：OpenAI 官方开源 CLI 编码 Agent（Apache-2.0，star 123,289 复扫实测）。Rust workspace 100+ crate 生产级工程化，跨平台沙箱最完善，MCP 原生，分布式 app-server/exec-server。

**机制细节**：
- **主循环**：codex-core（487 .rs files）经 `codex.submit(Op::UserTurn)` 提交轮次；AGENTS.md 明文"agent changes prefer integration tests over unit tests"，core/suite 用 `TestCodexBuilder::build_with_auto_env()` + ResponseMock 模拟 SSE（ev_response_created/ev_function_call/ev_completed）。
- **上下文六规则**（本次已从本地 `E:/stu/tools/codex/AGENTS.md` 原文验证）："1. No history rewrite…2. Avoid frequent changes to context that cause cache misses. 3. No unbounded items…hard cap. 4. **No items larger than 10K tokens.** 5. Highlight new individual items that can cross >1k tokens as P0…additional manual review. 6. All injected fragments must be defined as structs in core/context and implement ContextualUserFragment trait"。工程约束：变更 ≤800 行（复杂逻辑 ≤500）。
- **分布式**：app-server（JSON-RPC v2，`<resource>/<method>` 命名）+ exec-server 可跨 OS 部署；rollout crate 支持从既有 rollout 恢复会话。

**安全方法论**（本卡重点，最锋利）：
- **OS 级跨平台沙箱 5 后端**：Seatbelt（macOS `/usr/bin/sandbox-exec`）+ linux-sandbox + windows-sandbox-rs(+service) + mxc-sandbox + bwrap（bubblewrap），另有 sandboxing 抽象 crate 统一。
- **网络硬禁用**：沙箱内 shell 工具运行时 `CODEX_SANDBOX_NETWORK_DISABLED=1`。
- **沙箱代码=禁区**：AGENTS.md 原文（本地已验证）："**Never add or modify any code related to `CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR` or `CODEX_SANDBOX_ENV_VAR`**"——把安全边界写进 agent 工程规范本身，防止 agent 自己改掉自己的镣铐（这是对 prompt injection 最硬的工程防御：注入改不到沙箱代码）。
- **配套 crate**：secrets（密钥不进上下文/日志）、user-verification（危险操作前确认）、shell-escalation（提权管理）、process-hardening、guardian-context（安全相关上下文单独 crate）。

**可观测**：otel crate（OpenTelemetry）+ otel-trace-websocket（trace 走 WebSocket 传输）+ analytics crate；core/suite 集成测试 + insta 快照测试。

**卡内链接**：卡内 github.com/raw 链接本次网络未达；已用本地 clone `E:/stu/tools/codex/AGENTS.md` 原文核读六规则/禁区/行数限制——与卡内 claim 完全一致（Tier1 实证）。

**对 EDU 的可执行判据**：
1. **上下文注入三硬约束直接搬**：所有注入项有界+硬上限、单项 ≤10K token、新增 >1K token 的注入片段标 P0 强制人工审查——EDU 的 RAG 检索块注入 chat 上下文应套同一预算表。
2. **No history rewrite**：会话历史只追加不重写（EDU chat history 返回 data 数组已符合，继续保持增量构建以免 prompt cache 失效）。
3. **安全边界写进规范禁区**：EDU 若引入执行体（代码评测/文件操作），沙箱相关配置代码列为"agent 不可修改清单"。
4. agent 逻辑变更强制集成测试（对齐 EDU"接口验收须独立实证 requests/curl"纪律，且 TestCodexBuilder+ResponseMock 模式可复制到 SSE 契约测试）。
5. 变更 ≤800 行强制拆分——可直接写进 EDU 的 PR/commit 规范。

---

### 3. F-C03-003 DeepSeek Harness

**核心定位**：Everything-is-a-Plugin agent 运行时（dsh）。56 packages + Cordis 依赖注入 + 时空可组合（arXiv:2608.25512），4 应用（cli/desktop/desktop-host/web）+ Python SDK。215k★（复扫 219,985，C03 最高），developer preview（README 原文 "THERE WILL BE COMPATIBILITY-BREAKING CHANGES"）。

**机制细节**：
- **编排插件族**：goal（目标驱动）/ plan（计划-执行分离，支持执行中重规划）/ workflow（确定性 DAG）/ subagent（层级+对等编排，不同子 agent 加载不同插件集）/ skill（技能=提示词+工具+工作流，本身也是插件）/ guard（守卫）——多范式可组合。
- **上下文插件族**：context（核心）/ compaction（压缩，算法可插拔）/ spill（溢出换出到外部存储，热冷分层）/ session / session-query（全文+语义+元数据检索，用于回填与审计）。
- **工具插件族**：mcp/acp/lsp/webhook/web/terminal/shell/fs 全部经 Cordis 统一注册，工具集按时空组合（编码场景 lsp+terminal+fs，浏览场景 web+webhook）。
- **执行后端**：code-runtime + sandbox（应用级+容器级）+ subprocess + e2b（云沙箱）多后端可插拔。

**安全方法论**（本卡重点）：
- **插件化多层安全**：guard（关键节点守卫：工具调用前/LLM 调用前/输出前）+ sandbox + credentials（凭证不暴露给 LLM 或日志）+ identity（RBAC/ABAC）+ net-policy（域名/IP/端口准入，卡内标注"推断"）+ exec-policy（推断）+ runtime-diagnostics（决策/调用/守卫检查审计日志）。
- **SAFETY.md 原文声明**（本地 corpus clone 通读，Tier1）："It has not undergone a security audit and must not be treated as secure or production-ready"；"Sandboxing, approval prompts, and permission controls can reduce risk, but they do not guarantee isolation"；"**Do not rely on DeepSeek Harness as the sole security control** for untrusted workloads"；Responsible use 四条：最小权限 / 一次性 VM·容器·专用环境 / 可及文件保持备份 / 运行前审查插件配置与命令。

**可观测**：runtime-diagnostics（决策+工具调用+守卫检查日志）+ hooks + feedback（用户评分收集）+ benchmarks/。无独立评估框架。

**卡内链接**：卡内 github packages/* URL 未达（github 网络拒）；SAFETY.md 以本地一级事实源通读补偿。

**对 EDU 的可执行判据**：
1. **守卫三桩点直接采用**：工具调用前 / LLM 调用前 / 输出前——EDU 的 chat SSE 链路可在 retrieval 后、token 推流前、done 前各设 guard 检查（内容合规/越权数据/敏感词）。
2. SAFETY 声明模式可抄：EDU 上线文档必须声明"未做安全审计不作为唯一安全控制"，倒逼多层防御而非单点。
3. 上下文 spill（冷上下文换出+检索回填）适合 EDU 长会话辅导场景：热窗口保留当前题目，历史章节摘出库按需回填。
4. 凭证永不进 LLM 上下文/日志（credentials 插件原则）——对齐 EDU 已知教训"DEBUG=true 会返回虚拟管理员"这类配置即风险。
5. developer preview 语义（明确破坏性变更声明）适合 EDU 实验性接口的版本沟通。

---

### 4. F-C03-004 pi

**核心定位**：Self-extensible coding agent + unified multi-provider LLM API（earendil-works/pi，star 104,046 复扫）。12 包 monorepo（chord/telemetry/ai/agent/coding-agent/tui/client/server/protocol/session-backends/evals），本地部署已验证（E:/stu/tools/pi，51 files/7.5MiB bundle）。

**机制细节**：
- **四核心工具**：read/bash/edit/write（README 原文 "pi - AI coding assistant with read, bash, edit, write tools"）——对照 claude-code 的 60+ 工具，极简内核+扩展系统。
- **扩展系统**：`pi install/remove/list/config`，扩展增强能力不需改核心（卡内抽验：self-extensible 命中 README L15）。
- **agent-loop.ts** ReAct 循环 + proxy.ts 远程 agent + stream-fn.ts 流式；Chord composition runtime（服务组合/复制状态/RPC/插件）。
- **可插拔会话后端**：session-backends/sqlite-node 官方实现，支持自定义 PostgreSQL/Redis 后端。
- **vendor-neutral telemetry**：契约 + 参考适配器 + 一致性测试（conformance tests）+ 类型化 schema。

**安全方法论**（本卡重点——"显式不假装"路线）：
- README L41 原文（本地已验证）："**Pi does not include a built-in permission system** for restricting filesystem, process, network, or credential access. By default, it runs with the permissions of the user and process that launched it."
- **三种官方推荐外部沙箱**（README L43-47 原文验证）：① **Gondolin extension**——pi 与 provider auth 留宿主机，内置工具和 `!` 命令路由进本地 Linux micro-VM；② **Plain Docker**——整个 pi 进程进容器简单隔离；③ **OpenShell**——整进程进 policy-controlled sandbox。"If you need stronger boundaries, containerize or sandbox Pi."
- 凭证：`pi auth` 只做 readiness 检查，凭证走 env/`--api-key`，不内置存储。

**可观测**：telemetry 包（契约+conformance tests）；evals 包（`npm run eval --workspace=@earendil-works/pi-evals`）。

**卡内链接**：github 链接未达；本地 clone README 安全节已验证（Tier1）。卡内 DeepWiki 404（Tier3，卡内已标注）。

**对 EDU 的可执行判据**：
1. **安全声明必须显式**：EDU 若某模块无权限控制，像 pi 一样明文写出边界与外部补偿方案，禁止"默认安全"的错觉（直接呼应 AGENTS.md 教训 6：DEBUG=true 未登录可读用户数据）。
2. "核心 4 工具+扩展"哲学：EDU agent 内核保持 read（查库）/search（RAG）/write（作答）/grade（评分）四工具，新能力走扩展而非膨胀内核。
3. telemetry 契约+一致性测试模式：EDU 的埋点字段先定契约（types）再写适配器，避免前端 93 条真实 API 引用口径漂移。
4. vendor-neutral LLM 层（--provider 切换）适配 EDU 的 deepseek/备用模型切换需求（对照 task29 非流式 P95 换模型突破的经验）。

---

### 5. F-C03-005 Gemini CLI

**核心定位**：Google 官方开源终端 AI Agent（Apache-2.0，star 106,870）。TypeScript monorepo（packages/core 887 + cli 614 .ts），Gemini 原生单模型路线，MCP/ACP 双协议，Vim 模式终端 UI。

**机制细节**：
- 三层编排：local-executor.ts（1525 行，ReAct 感知→推理→执行→观察）+ geminiChat.ts（1881 行，对话历史/流式）+ client.ts（1299 行）。
- mcp-client.ts 2466 行（多 MCP 服务器并发连接，动态工具列表）；acpSession.ts 1522 行（ACP 会话，断线重连）。
- memoryService.ts 1487 行跨会话记忆（添加/查询/更新/删除/搜索召回）；配置三层：config.ts 4207 行 + settings.ts 1400 + settingsSchema.ts 3617。

**安全方法论**：
- **应用级沙箱**：sandbox.ts 1324 行——命令白名单/黑名单/路径限制/环境变量隔离，危险操作（删除/系统命令/网络访问）需用户确认。
- **工具白名单**：config 支持工具白/黑名单，用户控制哪些工具可自动调用 vs 需人工确认，**MCP 工具同样受白名单管控**（外接工具不豁免——这条最有借鉴价值）。
- **遥测隐私**：Google Clearcut 遥测 opt-out、匿名化、不含用户代码。

**可观测**：telemetry/types.ts 2502 行 + clearcut-logger.ts 2214 + metrics.ts 1801——C03 系列里应用内遥测最重的实现。

**对 EDU 的可执行判据**：
1. **MCP/外接工具纳入与内置工具同一套白名单**（EDU 若接外部 MCP 数据源，权限不因来源外置而放宽）。
2. 记忆服务四操作+召回（memoryService 模式）可做 EDU 学员画像记忆的最小实现。
3. settingsSchema 独立于 settings（schema 3600 行校验 1400 行配置）——EDU 配置层照此分层，配 config validate 子命令。
4. 遥测默认可退出——教育数据合规（未成年人生成数据）的底线设计。

---

### 6. F-C03-006 OpenHands

**核心定位**：平台化自主编码 Agent（原 OpenDevin，MIT，star 87,359 复扫）。多后端适配 + Web UI 平台 + Docker 沙箱执行。TypeScript/React 前端 + Python Agent 后端。

**机制细节**：
- **agent-server-adapter.ts 1638 行**：统一适配多 Agent 后端（OpenHands Agent / Claude Code / Codex），后端可动态切换——平台不锁定单一 agent。
- conversation-websocket-context.tsx 1278 行（WebSocket 实时会话，流式+断线重连）；agent-server-conversation-service 1145 行（会话生命周期+历史持久化）；前端 628 组件+222 hooks；Electron 桌面端。
- Docker 沙箱：agent 在容器内执行代码/命令/测试，文件系统/网络/进程隔离，可配资源限制与网络访问。

**安全方法论**：Docker 容器级隔离（可配置资源限制+网络）+ 后端 API Key 加密存储不暴露给前端 + 遥测 opt-out 匿名化。卡内结论：容器级 vs codex 的 OS 系统调用级。

**对 EDU 的可执行判据**：
1. **适配器模式接多后端**：EDU 若同时支持"AI 批改/教师手改/混合"，用统一 adapter 抽象而非硬编码单一实现。
2. WebSocket 会话断线重连+会话历史服务端持久化——EDU chat SSE 断线恢复可参考其 context/service 分层。
3. API Key 只存后端加密存储、永不下发前端（EDU 现有 JWT+壳协议已符合，扩展到模型 API Key 管理）。
4. 执行类任务（学生代码评测）一律 Docker 沙箱+资源限制，不接受宿主直跑。

---

## 第二部分：F-C09 可观测三件套（用户点名专题）

### 7. F-C09-001 Langfuse

**核心定位**：LLM 可观测性与评估平台，**OTel 原生 + 可观测性优先**。TypeScript/Next.js 全栈（web 3340 files + shared 731 + worker 391），MIT 核心+EE 企业版，star 34,469 复扫。设计哲学卡内概括为 "LLM 应用的 Datadog + GitHub Actions"。

**trace/评估/回放具体能力**（本专题核心）：
- **trace 摄入**：OtelIngestionProcessor.ts 3864 行——OTLP/gRPC/HTTP 摄入，解析 OTel Resource/Scope/Span，自动识别 LLM 语义约定（`gen_ai.system / gen_ai.request.model / gen_ai.usage.tokens`）→ 转内部事件模型 **Trace → Span → Generation → Observation**（Generation 含 Prompt/Completion/Token 用量/模型）。OTel 生成代码 root.ts 达 16411 行（协议完备性代价）。
- **存储与查询**：events.ts 3884 行事件仓库，Postgres（结构化）+ ClickHouse（分析查询），支持过滤/聚合/时间线。
- **评估**：scores.ts 3365 行评分仓库——人工评分/自动评分（规则）/模型评分（LLM-as-judge）三种，**评分直接关联到 Trace/Span/Generation**，支持准确性/相关性/安全性维度+评分历史。
- **数据集与回放闭环**：dataset-router.ts 2623 行——数据集 CRUD/版本/快照，**支持"从生产 trace 导入"把线上案例变评估用例**（这是"回放"的精髓：生产问题→回归用例）；Worker（391 files）异步跑批量评估（数据集×评估器），支持新版本 vs 旧版本回归对比+指标下降告警。
- **Prompt 管理**：版本化（创建/发布/回滚）+ Prompt 与 Generation 关联（可追溯哪个 prompt 版本生成了哪个输出）+ A/B 测试。
- **成本**：Token 计量（自动解析 gen_ai.usage）+ 按模型单价算成本，按模型/项目/用户/时间聚合+预算告警。
- **容错**：摄入队列 Redis/BullMQ + 死信队列 DLQ + 多实例 + Postgres 主从/ClickHouse 副本——摄入数据不丢失。

**对 EDU 的可执行判据**：
1. **生产 trace→评估数据集的闭环是第一优先级**：EDU 的 chat/批改请求抽量落"评估数据集表"，prompt 或模型升级前先跑回归对比（对齐 EDU 现有 perf 脚本复跑文化）。
2. 评分挂 trace：每次批改/答疑落 user_id/session_id/query/检索块/答案/token/耗时，人工复核分直接写回该 trace。
3. 借 OTel `gen_ai.*` 语义约定命名 EDU 的埋点字段，未来接 Langfuse/Phoenix 零改造。
4. 摄入走异步队列+DLQ，观测不阻塞主链路（EDU Redis 已闭环，可直接复用）。
5. Prompt 版本表（版本号+回滚+与生成记录关联）先于任何 prompt 优化工作。

### 8. F-C09-002 Opik

**核心定位**：LLM 评估与可观测平台，**评估优先 + 多语言 SDK**（Python 2236 + TypeScript 2528 files）。Comet ML 背景（ML 实验管理经验迁移），Apache-2.0，star 21,930 复扫。

**trace/评估/回放具体能力**：
- **统一客户端**：opik_client.py 3598 行——追踪/评估/数据集统一 API；SDK 自动埋点（装饰器/中间件/回调）支持 LangChain/LlamaIndex/OpenAI/Anthropic。
- **评估深度是差异点**：opik_optimizer 495 files——**Prompt 自动优化搜索 / 超参数搜索（temperature/max_tokens）/ A-B 多版本对比 / 贝叶斯优化**，结果（最优配置+指标）可视化。三件套里唯一带"优化器"的。
- **内置评估器**：准确性/相关性/安全性/幻觉检测 + 自定义 Python 评估器，批量运行（数据集×评估器）+回归+告警。
- **Guardrails 独立后端**：apps/opik-guardrails-backend/ 38 files——LLM 输出防护（内容安全/合规检查）作为平台内置组件（三件套唯一）。
- **容错重心在 SDK 端**：重试（指数退避）+ **SDK 本地缓存（断网暂存、恢复后批量上报）**+异步上报不阻塞应用——与 Langfuse 的服务端队列路线互补。

**对 EDU 的可执行判据**：
1. SDK 端本地缓存+批量补报模式：EDU 埋点在 Redis/后端不可用时落本地队列，恢复后补传，观测数据不丢。
2. 若 EDU 做 prompt 调优（批改 rubric prompt），评估优化器的"数据集×评估器×多版本对比"是最小可行流程，不必先建平台。
3. 幻觉检测评估器对教学问答（RAG 场景）是必设指标——答案须可归因到检索块。
4. Guardrails 独立后端（与应用解耦）的模式：EDU 内容合规检查独立成服务，chat 与批改共用。

### 9. F-C09-003 Phoenix

**核心定位**：LLM 可观测与评估平台，**Python 优先 + MCP 原生 + Playground 交互**。Arize AI 背景，ELv2 协议（**非纯开源，商业使用有限制**——选型注意），star 11,416 复扫。

**trace/评估/回放具体能力**：
- **Playground 实时调试**：playground_clients.py 4321 行——多模型并行对比/Prompt 编辑/参数调优/实时输出；**Playground 里可直接跑评估器**，评估结果可存为数据集。三件套唯一"部署前验证"能力。
- **评估器**：evaluators.py 3065 行——LLM-as-judge（评判模型可配 GPT-4/Claude，**评判 Prompt 可自定义，结果可解释：评判理由+评分**）/规则评估/自定义 Python 评估器。
- **Agent 管理**：agents.py 3745 行——Agent 注册/配置（Prompt/参数/**工具白名单**）/全链路追踪/评估；Agent 调用上下文**可追踪和回放**。
- **MCP 原生**：server/mcp/sql/parse.py 3333 行——MCP 工具调用追踪 + Text-to-SQL（自然语言查库）。
- **Trace DSL**：trace/dsl/filter.py 3623 行——领域特定语言过滤（布尔/比较/正则+聚合 count/sum/avg/percentile+分组），DSL 编译为 SQL——灵活分析强于前两者。
- 数据导出为 Pandas DataFrame/JSON/CSV（Python 数据科学生态友好）。

**三件套一页对比**（卡内矛盾记录综合）：
| | Langfuse | Opik | Phoenix |
|---|---|---|---|
| 优先级 | 可观测优先 | 评估优先 | 交互调试优先 |
| 协议 | OTel 原生（gen_ai.*） | 自有 REST+SDK 埋点 | MCP 原生 |
| 独门 | 生产 trace→数据集闭环、Prompt 版本管理 | 优化器（Prompt/超参自动搜索）、Guardrails 后端 | Playground 实时多模型对比、Trace DSL、LLM-as-judge 可解释 |
| 语言/许可 | TS 全栈/MIT+EE | Python+TS 双 SDK/Apache-2.0 | Python 优先/ELv2（限制多） |

**对 EDU 的可执行判据**：
1. EDU 选型默认 **Langfuse 路线**（MIT 可自托管+OTel 标准）；只需评估深度加 Opik 式优化器思想；ELv2 的 Phoenix 仅借鉴 Playground/Trace DSL 设计。
2. "Playground 先行"引入 EDU：批改 prompt 改版先在调试台用历史错题集跑 3 模型对比，再灰度上线。
3. LLM-as-judge 评判必须输出"理由+评分"两字段（可解释性是教师采纳的前提）。
4. Trace DSL 思想：EDU 观测查询别写死 API，落成可组合的过滤表达式（按院系/课程/模型/耗时百分位聚合）。

---

## 第三部分：F-C10 协议与技能生态（含 skill 生态专题）

### 10. F-C10-001 Superpowers（skill 生态重点卡）

**核心定位**：多平台 Agent 技能生态枢纽（obra/superpowers，star 282,954，npm superpowers v6.3.0）。14 个标准化开发工作流技能 + 9 个平台适配目录，"技能即文档"哲学。

**skill 组织哲学**（专题核心）：
- **格式**：SKILL.md = YAML frontmatter（`name` kebab-case + `description` 触发描述）+ Markdown 正文，可带辅助文件（.md/.sh/.ts/.dot/.js）。轻量约定，无强制 JSON Schema。
- **触发机制**：agent 处理请求时按 description 匹配决定是否把技能内容加载进上下文，再由 agent 用自身工具解释执行——技能本身零执行能力。例：systematic-debugging 的 description "Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes"。
- **纪律性条款写进技能**：systematic-debugging 的 **"Iron Law: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST"**（卡内溯源 SKILL.md:12），配 root-cause-tracing / defense-in-depth / condition-based-waiting / test-pressure-1/2/3（对抗"测试压力下放弃纪律"的样例）。
- **元技能自举**：writing-skills（26KB SKILL.md + 46KB anthropic-best-practices.md + 12KB testing-skills-with-subagents.md）教 agent 如何写/测技能——生态自我扩张的引擎。
- **隐式技能链**：brainstorming→writing-plans→executing-plans→TDD→systematic-debugging→code-review→verification-before-completion→finishing-branch 按开发阶段组织，顺序由 LLM 决策（无 DAG 引擎）；显式编排技能有 subagent-driven-development / dispatching-parallel-agents / using-superpowers（技能集导航）。
- **分发（2026-09-10 实测更正版）**：**9 个平台适配目录、三种模式**——①plugin.json 静态配置 5 个（.claude/.codex/.cursor/.devin/.kimi，其中 marketplace.json 仅 .claude-plugin 与 .agents 有）；②运行时代码 2 个（.opencode/plugins/superpowers.js——message transform 注入 bootstrap+config hook 注册技能目录；.pi/extensions/superpowers.ts——ExtensionAPI）；③其他格式 2 个（.agents/plugins/marketplace.json；.hermes-plugin/plugin.yaml 含 `provides_hooks: pre_llm_call`）。**.github 是社区配置非适配器**。CREATION-LOG.md 全仓仅 systematic-debugging 1 例（"每技能一份"旧说已纠错）。

**安全方法论**：
- **宿主代理模型**：技能是 Markdown 无执行能力，辅助脚本（如 find-polluter.sh）是否执行由宿主 agent 权限系统决定（Claude Code 的 PermissionMode / Codex 的沙箱）。
- 无技能签名/验证机制，来源可信性完全由分发渠道（npm/GitHub/平台市场）保证；CREATION-LOG 是审计留痕而非运行时防护。
- 卡内结论：与 MCP 的进程隔离相比，**技能无独立安全边界**——技能内容加载进上下文即等于提示词的一部分（这也是注入面：恶意 SKILL.md = 恶意提示词）。

**对 EDU 的可执行判据**：
1. EDU 教学技能（出题/批改/答疑风格/学情分析）照 SKILL.md 格式组织：frontmatter 两字段+正文+辅助文件，先 markdown 后考虑升级。
2. **description 必须写触发时机**（"Use when…"句式），这是技能被发现率的决定因素。
3. 纪律条款明文化：批改技能写死"Iron Law"式规则（如"NO SCORES WITHOUT RUBRIC CITATION FIRST"——无评分依据引用不给分）。
4. 建 writing-skills 式元技能+用子 agent 测技能（testing-skills-with-subagents 思路），保证技能质量可回归。
5. 引入外部技能一律视为不可信提示词：先人工审内容再入库（对齐 AGENTS.md 铁律 7"只取 markdown 资产并留版权声明"）。
6. 多平台分发的真实成本是 N 个适配目录同步——EDU 技能先服务单平台（ZCode/Trae），再谈跨平台。

### 11. F-C10-002 MCP Servers

**核心定位**：Model Context Protocol 官方参考实现集（modelcontextprotocol/servers，star 90,150）。7 个参考服务器（everything 56 files / filesystem / git / memory 知识图谱 / fetch / sequentialthinking / time），"协议即产品"。

**机制细节**：
- **三大原语**：Tools（有副作用操作，inputSchema=JSON Schema）/ Resources（只读数据，URI 寻址+订阅变更）/ Prompts（参数化提示词模板）。
- **协议**：JSON-RPC 2.0；传输 stdio（本地子进程）/SSE/HTTP/Streamable HTTP（v2025-03-26）；方法命名空间 tools/* resources/* prompts/* sampling/* notifications/*；能力协商（initialize 交换 capabilities）+ 协议版本化（2024-11-05→2025-03-26→2025-06-18，向后兼容渐进增强）；采样回调（服务器反向请求客户端 LLM）+ 进度通知。
- 10+ 语言 SDK（TS/Python/Go/Rust/Java/Swift…）；每 server 独立 npm 包 `npx` 直跑。

**安全方法论**（专题核心，8 层）：
①**进程隔离**（stdio 子进程/容器，服务器崩溃或恶意代码不直接影响 agent）；②**权限控制**（filesystem server **目录白名单**、git server 可限只读；客户端配置声明权限范围）；③**传输加密**（远程 HTTPS）；④**OAuth 2.1 + PKCE**（远程服务器认证，令牌刷新/撤销）；⑤**沙箱**（chroot/容器限文件系统、fetch 域名白名单）；⑥**输入验证**（JSON Schema 验参防路径遍历/命令注入）；⑦**日志审计**（log 方法+客户端收集）；⑧**秘密管理**（env/配置文件传入，禁硬编码）。卡内注意：部分协议级 claim 标 INFERRED（规范在 modelcontextprotocol/specification 另仓）。

**对 EDU 的可执行判据**：
1. EDU 对外暴露数据（成绩/学情）若做成 MCP server：只读 Resources 优先于 Tools，工具一律 JSON Schema 严验参。
2. filesystem 类 server 必须目录白名单且默认只读——教育数据最小暴露。
3. 远程 MCP 接入必须 OAuth 2.1+PKCE，禁止裸 URL。
4. 借"everything server"思路给 EDU 做一个全功能契约测试桩，验收任意 MCP 客户端接入正确性。

### 12. F-C10-003 OpenClaw

**核心定位**：多通道 AI 网关（star 389,421，MIT，本地 CLI Tier1 实测 60+ 命令）。20+ 消息渠道（Discord/iMessage/Slack/Teams/Telegram/WhatsApp…）+ 5 平台原生应用 + Gateway 本地控制平面 + 插件/技能生态。独立 501(c)(3) 基金会治理，"无付费层级/托管服务/token，默认不向家发送数据"。

**机制细节**：
- **三层安全理念 = 卡内点名重点**："trusted gateway, untrusted execution, deterministic policy"（README 原文）：
  - **trusted gateway**：Gateway 跑在用户自己硬件，状态/记忆/凭证全本地；除每日版本检查（可禁）默认不外发数据；匿名统计 opt-in。
  - **untrusted execution**：**"Treat inbound messages as untrusted input"**（README 明文）——入站消息一律视为不可信（这是对 prompt injection 的第一性防御立场）；工具执行在 Docker sandbox；DM 渠道未知发送者默认配对（`pairing approve` 审批）。
  - **deterministic policy**：approvals（工具调用执行审批）+ exec-policy（确定性工具访问控制，非 LLM 自由裁量）+ net-policy 包（域名/IP/端口类型化策略）+ secrets（凭证加密）+ `security audit`（本地配置隐患审计）+ audit 命令（**metadata-only 审计日志，不记敏感内容**）。
- **插件**：plugin-sdk + plugin-package-contract（契约驱动：package.json 字段/目录/入口/权限声明，Gateway 按契约加载验证）；模型提供商与 agent harness（Claude/Codex/本地）都是可替换插件。
- **技能**：skills/ 16+（1password/coding-agent/diagram-maker/gh-issues…），技能=可执行单元（工具/提示词/工作流组合，Gateway 加载调度），skills list/inspect 管理；ClawHub 市场。与 Superpowers 纯文档技能、MCP 独立进程工具形成三级谱系。
- **协议聚合**：Gateway WebSocket + MCP（mcp.servers 配置+渠道桥接）+ ACP（acp-core）；`attach` 命令把 Claude Code 附加到 Gateway 会话并给 **scoped MCP 工具**（工具范围收窄）。

**对 EDU 的可执行判据**：
1. **"入站消息=不可信输入"写进 EDU 后端铁律**：学生/家长消息与网页抓取内容、RAG 检索块同级别对待——进 prompt 前过隔离/标注，绝不因"来自自家前端"而豁免。
2. 危险操作走 deterministic policy（确定性白名单/审批），不交给 LLM 现场判断。
3. 审计日志只记元数据（谁/何时/调了什么工具）不记对话内容——兼顾合规与隐私（教育数据）。
4. 外部会话接入用 pairing 配对审批模式（EDU 家校群/IM 机器人接入未知用户时先配对）。
5. scoped MCP 工具（attach 时收窄工具范围）适用于 EDU 管理端给不同角色暴露不同工具子集。

---

## 第四部分：单卡（daytona / dify / browser-use）

### 13. F-C04-001 daytona

**核心定位**：开发环境沙箱平台（MIT，star 71,737）。**已归档**：main 分支 2026-06 起迁移私有代码库（README 归档声明实测），本卡基于最后公开版 v0.190.0 tag（commit 01c502bb）——选型慎用，但架构可借鉴。

**机制细节**：apps/ 12 服务（api 中央编排 REST/gRPC / runner 容器执行引擎 / proxy 反代端口路由 / ssh-gateway / daemon 心跳注册 / **snapshot-manager 环境快照** / otel-collector / dashboard）+ libs/ 27 库（**5 语言 SDK + 5 语言 API client** + computer-use GUI 自动化 + opencode-plugin + pi-extension）。"dev environments as code"（devcontainer/devfile）。

**安全方法论**：API Key/OAuth2/JWT + RBAC + 环境级权限隔离；每环境独立网络命名空间 + NetworkPolicy + Proxy 仅暴露指定端口；容器 CPU/内存/磁盘配额；非 root 运行/只读根/seccomp/AppArmor；API 与 SSH 全量审计日志（追加不可改）。

**可观测**：otel-collector 三支柱（指标/日志/追踪）+ 多导出器（Prometheus/Jaeger/Zipkin/ES）+ 审计日志合规化。

**对 EDU 的可执行判据**：
1. 学生代码评测环境按"环境即代码"定义（devcontainer），评测镜像版本化可回滚。
2. snapshot-manager 模式：评测环境快照（文件系统+进程状态）支持复查争议批改。
3. 已归档项目禁入 EDU 生产依赖；其 runner/api/proxy 分层可作为自建评测沙箱的参考架构。

### 14. F-C05-001 Dify

**核心定位**：低代码可视化 LLM 应用平台（star 155,406 复扫；13,950 files；Linux Foundation/CNCF 沙箱候选）。"LLM 应用的 WordPress"：可视化 DAG + RAG 内置 + 100+ 模型抽象 + 一键发布。CB-03 大仓预案首例（DeepWiki-first，未跑全量 Repomix）。

**机制细节**：
- **可视化 DAG 工作流**：api/core/workflow 引擎 + web React Flow 编排器；节点族 Start/LLM/Code(Python/JS 沙箱)/Knowledge Retrieval/HTTP Request/IF-ELSE/Iteration/Template(Jinja2)/Variable Aggregator/Question Classifier/Tool/End（**卡内标注 INFERRED 待精读确认**）；Workflow（无状态单次）vs Chatflow（有状态多轮）共享引擎。
- **model_runtime 抽象**：100+ 提供商统一调用+负载均衡+故障转移+降级+缓存。
- **dify-agent/** 独立 Agent 运行时（ReAct/Plan-and-Execute），另有 dify-agent-runtime/（重构版，关系待确认）。
- **插件**：api/extensions/ 扩展点（工具/模型/存储/向量库/搜索）+ packages/contracts 前后端契约类型 + 第三方插件市场。
- 变量四类：系统/环境（不暴露前端）/对话（会话级持久）/节点变量，强类型。

**安全方法论**：API Key 认证+速率限制+RBAC（工作空间/角色）+多租户数据隔离+企业版 SSO(SAML/OIDC)/审计+Code 节点沙箱隔离。

**对 EDU 的可执行判据**：
1. EDU 管理端若做"可视化流程编排"（如请假审批+AI 预审），Dify 节点分类学（尤其 Question Classifier 路由 + IF-ELSE + Knowledge Retrieval）直接套用。
2. 环境变量与对话变量严格分离且环境变量不下发前端——EDU 已有此纪律（edu-api.js 壳），扩展到工作流变量层。
3. 平台锁定警告：应用配置存 Dify 库迁移成本高——EDU 若用须坚持 YAML 导出进 git。
4. RAG"内置够用不深"定位与 EDU 自研 RAG（BGE-M3）路线一致：平台化编排可以引，检索内核不自废。

### 15. F-C08-001 browser-use

**核心定位**：浏览器自动化 Agent 框架（MIT，star 114,156 复扫，Python）。"Agent sees the web like a human"：DOM 语义感知（非坐标/非截图），LLM 驱动 ReAct 循环，底层 Playwright。四层分离架构。

**机制细节**：
- agent/service.py 4163 行（ReAct 循环+消息管理+提示词）+ browser/session.py 4153 行（Playwright 控制+watchdogs）+ mcp/server.py 1294 行（浏览器能力 MCP 化，也含 client.py 556 行可反向接外部 MCP）+ tools/registry/service.py 613 行（动态工具注册）。
- **4 Watchdogs**：default_action（3752 行，动作执行与页面响应）/ downloads（1503，下载）/ dom（877，DOM 变化触发重新感知）/ **har_recording（779，HAR 录制 HTTP 用于调试回放）**。
- **DOM 感知省 token**：只保留可交互元素（按钮/链接/输入框），丢弃静态内容；message_manager（600 行）做 token 计数与截断。
- variable_detector.py 276 行：检测提示词/动作中的变量占位符，凭证从环境变量注入不进提示词。

**安全方法论**：浏览器沙箱（sandbox/ 3 文件+Docker 部署）+ Watchdogs 安全监控（意外导航恶意站/恶意文件下载告警）+ 动作约束（提示词层禁止清单：禁敏感站/禁下载可执行文件/禁输入敏感信息）+ judge.py 225 行动作安全性评估 + 凭证环境变量化 + HAR 全量录制审计回放。

**对 EDU 的可执行判据**：
1. EDU 若做网页自动巡检（教务系统/题库监控），用 DOM 语义感知路线（分辨率无关+token 省），弃坐标 RPA。
2. Watchdog 事件监控模式移植：文件下载/DOM 异变/意外跳转三类事件必设监控。
3. 凭证变量化（环境变量注入占位符）是硬纪律——教学平台账号密码永不写进 prompt。
4. HAR 录制=浏览器侧"回放"能力：与 F-C09 的 trace 回放互补，定位"agent 点了什么导致数据错了"类事故。

---

## 第五部分：S 源卡 / M 矩阵 / P 模式卡

### 16. S-001 Building Effective Agents（Anthropic，URL 已抓取核读）

**核心定位**：agent 设计第一原则文。一句话：从最简单方案起步，只在证明收益时加复杂度——大多数场景一次调用+检索即可，不需要自主 agent。

**机制/论点**（本次 WebFetch 原文验证）：
- Workflow（预定义代码路径编排）≠ Agent（LLM 动态指挥过程与工具）；原文三原则："Maintain simplicity / Prioritize transparency by explicitly showing the agent's planning steps / Carefully craft your agent-computer interface (ACI)"。
- 七模式：Augmented LLM（基本构件）→ Prompt chaining（可加 gate 检查点）→ Routing（含隐私分流）→ Parallelization（sectioning/voting）→ Orchestrator-workers → Evaluator-optimizer → Agents。
- agent 本质："gain ground truth from the environment"——编码 agent 单任务 140+ 次工具调用；最适领域=客服与编码（产出可验证、天然反馈回路）。
- 安全相关原文（补强）："We recommend extensive testing in sandboxed environments, along with the appropriate guardrails"；停止条件（如最大迭代数）；guardrail 模型并行筛查。
- 金句："more time is spent on optimizing tools than the overall prompt"；Poka-yoke 实测：相对路径→绝对路径后 20 次调用 0 次失败。

**对 EDU 的可执行判据**：
1. EDU 每个新 AI 功能先问"一次 LLM 调用+RAG 能不能解决"——能就不上 agent（对齐 S-002）。
2. 批改=编码型任务（可验证反馈回路），是 EDU 最适合 agent 化的场景；闲聊答疑不是。
3. 透明原则：agent 批改必须显式展示"规划步骤"（评分维度→逐项证据→结论），不接受黑盒总分。
4. 给 agent 设最大迭代数停止条件+沙箱内充分测试后再放行。

### 17. S-002 12-Factor Agents（HumanLayer，README 已抓取核读）

**核心定位**：生产级 agent 的 12 条可独立采用的小原则。"确定性代码为主体、在正确的位置点缀 LLM 步骤"（"mostly deterministic code, with LLM steps sprinkled in at just the right points"——这是优点不是缺点）。

**12 因子**（标题已原文核读）：1 Natural language to tool calls / 2 Own your prompts / 3 Own your context window / 4 Tools are just structured outputs / 5 Unify execution state and business state / 6 Launch-Pause-Resume with simple APIs / 7 **Contact humans with tool calls**（HITL 走工具调用）/ 8 **Own your control flow** / 9 **Compact errors into context window** / 10 Small, focused agents / 11 Trigger from anywhere / 12 **Make your agent a stateless reducer**（+荣誉提名 13 预取上下文）。
- 框架陷阱：框架快速到 70-80% 质量→客户前不够用→被迫逆向工程框架→推倒重来（100+ SaaS 构建者共同经历）。

**对 EDU 的可执行判据**：
1. EDU 后端保持"确定性代码为主体"：FastAPI 契约/权限/分页全是确定性代码，LLM 只点缀在批改/生成/检索改写三点。
2. HITL 走工具调用：教师复核/驳回实现为一个"工具"，agent 与人用同一套调用协议（因子 7）。
3. 错误压缩再进上下文（因子 9）：批改失败重试时喂"压缩后的可行动错误"而非原始堆栈（联动 P-003）。
4. agent 做无状态归约器（因子 12）：状态外置 DB/Redis，进程随时重启——契合 EDU uvicorn 无状态多实例部署。

### 18. M-002 C10 协议生态矩阵

**核心定位**：superpowers vs mcp-servers vs openclaw 三形态横评。**一页口径**：三者是 C10 谱系"静态技能→协议工具→完整运行时"的生态层级选择，非替代。

**关键格**：分发（SKILL.md 文档 / npm 独立 server 包 / monorepo+原生应用）；插件架构（9 平台适配目录 / MCP 协议原生无需平台适配 / plugin-sdk+contract 契约）；编排（都无独立引擎→客户端 agent 编排，唯 openclaw 有 Gateway 运行时编排）。

**⚠ 精读发现的不一致**：M-002 矩阵仍写"**10 个平台插件目录**（含 .github）"，而 F-C10-001 已于 2026-09-10 事实纠错为 **9 个**（.github 非适配器）——矩阵未同步 F 卡更正，引用时以 F-C10-001 为准。

**对 EDU 的可执行判据**：
1. EDU 技能/工具选型按层级：方法论类→静态技能；跨 agent 共享工具→MCP；带状态多渠道运行时→openclaw 型网关（教育场景对应家校多渠道机器人）。
2. 矩阵式对比表（维度×框架+EXTRACTED 角标+回溯 F 卡）是 EDU 技术选型报告的标准格式。

### 19. M-003 C03 CLI 编码 Agent 矩阵

**核心定位**：claude-code vs codex vs DeepSeek Harness 横评。**一页口径**：查询引擎 vs 分布式 Rust vs 插件化 Cordis——"非替代而是架构哲学选择"。

**关键格**：安全最完善=codex（Seatbelt/linux/windows/mxc/bwrap 5 后端）；上下文管理最严格=codex 六规则；claude-code 标注 source-leak Tier3 数据源降级；DeepSeek Harness 走 CB-11 Update 增补路径。

**对 EDU 的可执行判据**：
1. EDU 自研 agent 执行体的安全基线按 codex 格（沙箱后端≥1+网络禁用开关+禁区清单），按 claude-code 格（权限确认）做交互层。
2. 数据来源分级（官方 repo/source-leak/DeepWiki Tier）应写进 EDU 调研结论——来源等级决定结论可信度。
3. "star 漂移<2% 不重蒸馏"的 CB-11 微漂移机制适用于 EDU 依赖库跟踪（30 天复扫+仅标注）。

### 20. P-003 工具设计 ACI 法则

**核心定位**：S-001 Appendix 2 的落地模式卡。"agent 的能力上限由工具设计决定"——Anthropic 自述优化工具的时间超过优化整体 prompt。

**五法则**：①格式贴近模型自然语料形态（markdown 代码块优于 JSON 转义；**整文件重写优于 diff**——diff 要求精确数行号恰是模型易错点）；②消除格式开销（不让模型数几千行/字符串转义/写进死角，给足思考 token）；③**Poka-yoke 防呆**（改参数让错误难以发生：绝对路径 20 次 0 失败）；④工具文档像给初级工程师写（示例用法/边界情况/与相似工具区别）；⑤像重视 HCI 一样重视 ACI（多组输入实测误用模式并迭代）。

**对 EDU 的可执行判据**：
1. EDU 工具返回错误必须"本身可行动"（错误信息即 prompt）——对照现有 error_codes.py：错误码+修复建议一起返回给 agent。
2. 批改输出用整段重写+结构化包裹（分数+理由+依据），禁止让模型输出行号对齐 diff。
3. 参数防呆：凡 ID 类参数用完整唯一 ID（student_id 而非序号），杜绝模型猜位。
4. 工具成功率低时**先改工具再改 prompt**——写进 EDU prompt 迭代 SOP 的第一检查项。

---

## 第六部分：TOP10 最锋利判据 + 三专题结论

### TOP10 最锋利判据（跨卡提炼，按杀伤力排序）

1. **【安全】"入站消息=不可信输入"是第一性原则**（OpenClaw README 明文）——EDU 的学生消息、RAG 检索块、网页抓取内容进 prompt 前一律按不可信处理；配合 codex 的"沙箱代码禁区"（Never add or modify CODEX_SANDBOX*）把安全边界写到 agent 改不到的地方。
2. **【安全】沙箱路线三级谱系按威胁选**：运行时权限确认（claude-code CanUseToolFn）→ OS 级沙箱 5 后端+网络硬禁用（codex）→ 显式无内置+外部 micro-VM/Docker/policy-sandbox 三模式（pi）。EDU 执行类任务至少达到"容器隔离+网络禁用+审批"级。
3. **【安全】确定性策略优于 LLM 裁量**（OpenClaw deterministic policy / approvals / exec-policy / net-policy）——危险操作白名单+审批流由配置确定，不让模型现场判断"该不该做"；DM 未知发送者默认 pairing 配对。
4. **【可观测】生产 trace→评估数据集→回归对比是闭环核心**（Langfuse dataset-router：从生产 trace 导入数据集+Worker 批量回归+告警）——EDU 任何 prompt/模型变更前先跑历史真实案例回归（直接服务 task29 P95 优化这类工作）。
5. **【可观测】评分挂 trace + LLM-as-judge 必须可解释**（Langfuse scores 关联 Trace/Span/Generation；Phoenix 评判输出理由+评分）——EDU 批改质量评估落到单条 trace，教师复核分数写回。
6. **【可观测】OTel `gen_ai.*` 语义约定是免锁死的埋点标准**（Langfuse 3864 行摄入器原生解析）——EDU 现在按此命名埋点，未来接哪家平台都零改造；摄入走异步队列+DLQ 不阻塞主链路。
7. **【工具/ACI】工具成功率低先改工具再改 prompt + Poka-yoke 防呆**（P-003：绝对路径 20 次 0 失败；错误返回本身可行动）——这是被 Anthropic 实证过的最高杠杆优化点。
8. **【架构】确定性代码为主体、LLM 只点缀在正确位置**（S-002 因子总纲；框架 70-80% 质量陷阱）——EDU 的 FastAPI 契约层保持确定性，agent 能力以"四核心工具+扩展"（pi 模式）渐进生长。
9. **【skill】技能=Markdown 文档（可审计）+description 决定触发+纪律条款明文化（Iron Law）+元技能自举**（Superpowers）——EDU 教学技能照此四件套建库；外部技能入库前人工审（技能即潜在注入面）。
10. **【上下文】注入项有界硬上限、单项≤10K token、>1K 新增标 P0 人工审查、No history rewrite**（codex AGENTS.md 原文六规则，本地已验证）——EDU 的 RAG 检索块注入直接套用此预算表。

### 专题一：prompt injection / 安全方法论结论

- **防御纵深五层**（从 6 张卡归纳）：①数据层——入站即不可信（OpenClaw）、凭证 env 注入不进 prompt（browser-use/pi/DSH credentials）、秘密 crate 隔离（codex secrets）；②模型层——guard 三桩点（DSH：工具前/LLM 前/输出前）、内容 guardrails 独立后端（Opik）；③工具层——权限门按需确认+始终允许白名单（claude-code）、MCP 目录白名单+JSON Schema 验参+OAuth 2.1 PKCE（mcp-servers 8 层）、工具白名单含外接 MCP 工具（gemini-cli）、scoped MCP 工具（OpenClaw attach）；④执行层——OS 沙箱+网络禁用+禁区代码（codex）、Docker 容器+资源限制（OpenHands/daytona/OpenClaw sandbox）、micro-VM 路由（pi Gondolin）；⑤审计层——metadata-only 审计日志（OpenClaw）、HAR 全量录制（browser-use）、runtime-diagnostics（DSH）、pairing 配对（OpenClaw）。
- **对 EDU 的一句话**：教育平台的最大注入面是"学生输入+网络检索内容直接进批改/答疑 prompt"——按上述五层各落一策即可形成纵深，最低配=权限门（已有）+检索块标注隔离+审计元数据日志+评测沙箱化。
- **诚实声明文化**：pi 显式"无内置权限系统"+DSH SAFETY.md"不作为唯一安全控制"——EDU 每个模块的安全边界要么实现、要么明文声明缺省+补偿方案，禁止沉默的伪安全（AGENTS.md 教训 6 的 DEBUG 虚拟管理员即反面案例）。

### 专题二：可观测三件套结论

- **选型一句话**：Langfuse=OTel 标准+生产闭环+MIT 自托管首选；Opik=评估深度+优化器+SDK 端容错（Apache-2.0）；Phoenix=Playground 实时调试+Trace DSL+可解释 judge，但 **ELv2 许可限制商用**需法务过目。三者非竞争而是可组合：OTel 埋点（Langfuse 协议）+ 优化器思想（Opik）+ Playground 灰度（Phoenix 模式）。
- **回放能力三层**：trace 级回放（三家都有：Trace/Span/Generation 时间线）、生产→数据集回放回归（Langfuse/Opik/Phoenix 数据集导入）、浏览器/网络级回放（browser-use HAR）。
- **EDU 行动序列**：先定 gen_ai.* 埋点契约 → chat/批改 trace 落库（评分挂 trace）→ 抽量建评估数据集 → prompt/模型变更回归门禁 →（可选）批改 prompt Playground 多模型对比。全链路可复用 EDU 已闭环的 Redis 队列与 test-reports 实证文化。

### 专题三：skill 生态结论

- **三级形态谱系**（M-002+F 卡交叉确认）：Superpowers 纯文档技能（SKILL.md，宿主解释执行，零独立安全边界，分发成本=9 个适配目录同步）→ MCP 运行时工具（JSON-RPC+JSON Schema，进程隔离，协议级跨平台）→ OpenClaw 可执行技能（Gateway 内注册工具/提示词/工作流，契约插件+三层防御）。选型按"方法论 vs 工具 vs 运行时"分层，不互斥可组合。
- **Superpowers 可直接搬运的四个资产**（对齐 AGENTS.md 铁律 0"不重复造轮子"）：SKILL.md 格式约定（frontmatter name+description）；Iron Law 式纪律条款写法；writing-skills 元技能（含 anthropic-best-practices.md 46KB+用子 agent 测技能 12KB）；按开发阶段组织的隐式技能链目录结构。搬运时留版权声明、只取 markdown 资产。
- **对 EDU 的路线**：教学技能库从 3-5 个 SKILL.md 起步（出题/批改/答疑/学情），description 全部用"Use when…"句式；建 writing-skills 式元技能保证增长质量；工具类需求走 MCP 而非塞进技能文档；外部技能入库前视为不可信提示词人工审。

### 精读发现的卡片级问题（供 vault② 维护参考）

1. **M-002 未同步**：仍写"10 个平台插件目录（含 .github）"，与 F-C10-001 2026-09-10 更正（9 个，.github 非适配器）矛盾。
2. **F-C03-004 pi 卡转写误差**：§arch-context 中写 codex 六规则"≤30K tokens"，与 codex 卡及本地 AGENTS.md 原文（"No items larger than 10K tokens"）不符，应订正为 10K。
3. F-C03-002 卡内 star 前后两写（正文"star 数 API 暂不可用"为旧稿残留 vs frontmatter/更新记录 123,289 已回填）——以更新记录为准。
4. F-C10-003 "5 平台原生应用"中 Windows 实为 npm CLI+守护进程（卡内已自注"原生应用待确认"），apps/ 实测 10 目录含 swabble/mobile 等非平台项。
