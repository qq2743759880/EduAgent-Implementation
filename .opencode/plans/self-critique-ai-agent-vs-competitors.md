# 自我批判报告：task24~36 完成后能否达到竞品水平？

> 批判对象：dev-plan.md task24~36 的 AI 助手/RAG/MCP 设计
> 对标基准：Claude Code（Anthropic 官方文档，已真实抓取 5 篇）、Codex（OpenAI 官方文档）、Cursor（行业公开认知）、云朵课堂（爬取的功能页）
> 结论先行：**不能。** task24~36 按当前设计完成后，与 Claude Code/Codex/Cursor 的工程差距约为"能跑通 demo vs 生产级 agent 平台"的量级，9 个维度中 6 个存在**结构性缺陷**（非参数调优可解决）。

---

## 〇、证据来源（全部真实抓取/搜索，非道听途说）

| 证据 | 来源 | 获取方式 |
|------|------|---------|
| Claude Code memory 机制（CLAUDE.md 分级/auto memory MEMORY.md 索引 200 行上限/topic 按需读取/子代理独立记忆） | code.claude.com/docs/en/memory | webfetch 全文 |
| Claude Code subagents（独立 context window/25 个 frontmatter 字段/mcpServers 隔离/isolation worktree/memory 字段） | code.claude.com/docs/en/sub-agents | webfetch 全文 |
| Claude Code prompt-caching（三层缓存组织/失效清单/cache_read 指标/MCP tool search 保护前缀/TTL 5min-1h） | code.claude.com/docs/en/prompt-caching | webfetch 全文 |
| Claude Code skills（SKILL.md 渐进式披露/description 1536 截断/dynamic context injection/context:fork/agentskills.io 标准） | code.claude.com/docs/en/skills | webfetch 全文 |
| Anthropic 工程博客 4 篇（building-effective-agents/context-engineering/multi-agent-research/contextual-retrieval） | anthropic.com/engineering | 前序会话已抓 |
| Codex 文档结构（AGENTS.md/subagents/sandboxing/MCP/memories/compaction） | developers.openai.com/codex | webfetch 索引 |
| 云朵课堂后台功能（教务/CRM/营销 4 页） | crawler/output_edu/ | crawl4ai 实爬 |

---

## 一、九维度逐项批判

### 维度 1：RAG 向量切分/召回/检索/索引 —— ⚠️ 部分达标，缺语法感知与在线评估

| 对比项 | 计划（task30~32） | 竞品实测 | 判定 |
|--------|------------------|---------|------|
| 切分 | 纯文本多策略切分（chunker.py）+ contextualize 前缀 | Cursor：tree-sitter 语法感知切分（代码 AST 边界）；Claude Code：不用向量库做代码检索，用 grep/glob+语义搜索 | **落后**：纯文本切分对代码/结构化文档无语法感知，Cursor 的 AST 边界切分显著更优 |
| 召回 | dense(BGE-M3)+sparse(jiaba BM25) RRF + top-150→rerank→20→断崖→5 | Anthropic Contextual Retrieval 同款（官方实测 -67% 失败率） | ✅ 达标（本维度亮点） |
| 索引 | Milvus IVF_FLAT+SPARSE_INVERTED | Cursor：代码索引（tree-sitter 语法树+BM25+embeddings 混合）；Claude Code：语义搜索+grep 混合 | ⚠️ 部分达标：对"代码库"场景缺语法索引 |
| 评估 | rag_evaluator 离线 top-20 命中率 | Anthropic 建议：在线评估+持续监控 | ⚠️ 只做离线评估，缺线上检索质量监控 |

**批判**：本维度 RAG 链路（contextualize+rerank）本身对齐了 Anthropic 官方最佳实践（已达标），但**切分没有语法感知**（对代码/教材结构化内容），且**缺在线检索质量监控**（只有离线评估一次）。Cursor 的 tree-sitter 语法索引是明显差距。

### 维度 2：MCP 调用效率 —— ❌ 结构性落后（缺 tool search 延迟加载/认证/自动重连）

| 对比项 | 计划（task33） | Claude Code 实测 | 判定 |
|--------|--------------|-----------------|------|
| 工具加载 | 全部 MCP 工具描述进 system prompt | **Tool search**：数千工具按需延迟加载（默认），工具描述不进前缀，保护 prompt cache | ❌ **关键差距**：MCP 工具描述全量进前缀→随 server 数增长，缓存必失效（Claude Code 明确说"加载进前缀的工具，任何变更使缓存失效"） |
| 认证 | 无 | MCP OAuth 认证、API key、受管配置（allowlist/denylist） | ❌ 缺 |
| 连接可靠性 | 超时+熔断 | 自动重连（stdio 进程退出/HTTP 会话过期后自动恢复）、动态工具更新 | ❌ 缺自动重连 |
| 结果控制 | 结果截断 300-500 字 | per-tool MCP 结果大小覆盖 | ⚠️ 部分达标 |
| 隔离 | admin_only 过滤 | 子代理级 mcpServers 隔离（工具不进主上下文） | ⚠️ 有过滤但缺子代理级隔离 |

**批判**：MCP 领域差距最大。Claude Code 的 tool search（按需延迟加载）是**保护缓存命中率的根本机制**——计划里 MCP 描述审查（task33）甚至会加剧问题：重写描述=前缀变更=缓存失效。缺 OAuth/自动重连/子代理级隔离。

### 维度 3：多 agent/子 agent 工作流 —— ❌ 结构性缺陷（子代理无独立上下文）

| 对比项 | 计划（task24） | Claude Code 实测 | 判定 |
|--------|--------------|-----------------|------|
| 子代理上下文隔离 | **LangGraph 节点 + asyncio.gather（共享同一 state/context）** | 每个子代理**独立 context window**+独立 system prompt+独立工具集+独立权限 | ❌ **最严重缺陷**：计划的"子代理"是同一上下文中并发执行的节点，**丢失了子代理核心价值（上下文隔离）** |
| 子代理返回 | artifact 轻引用+蒸馏摘要 1000-2000 token | 同（蒸馏摘要返回） | ✅ 方向对 |
| 子代理配置 | 固定 4 个（search/tool/learning/memory） | 25 个 frontmatter 字段：model/tools/disallowedTools/permissionMode/maxTurns/skills/mcpServers/hooks/memory/isolation/background/effort | ❌ 缺：子代理模型选择、工具白名单、权限模式、独立记忆、worktree 隔离 |
| 编排 | orchestrator-worker + effort scaling | Agent teams/background agents/dynamic workflows（跨会话消息、后台代理、脚本化编排） | ⚠️ 计划只有基础 orchestrator，无后台/并行会话/跨会话协作 |
| 子代理缓存 | 无 | 子代理独立 5min TTL 缓存；fork 模式继承父缓存 | ❌ 缺 |

**批判（最关键）**：Anthropic《Multi-agent Research System》明确子代理的核心价值是"**独立 context window**（the detailed search context remains isolated within sub-agents）"。计划的 LangGraph 实现（节点共享 state）**恰恰没有实现这一点**——如果 4 个"子代理"在同一个 state 里跑，它们的完整检索结果/工具输出都会留在共享上下文里，等于没有上下文隔离，蒸馏摘要和 artifact 的收益被抵消。这是**结构性设计错误**，不是调参能修的。

### 维度 4：tool/skill 调用 —— ❌ 缺 skill 机制（渐进式披露）

| 对比项 | 计划 | Claude Code 实测 | 判定 |
|--------|------|-----------------|------|
| 能力扩展 | 仅 MCP 工具 + ToolSpec | **Skills**：SKILL.md 渐进式披露（description 1536 字符截断进上下文，body 按需加载）+ agentskills.io 开放标准 | ❌ **结构性缺失**：计划完全无 skill 机制。skills 是 Claude Code/Cursor/Codex 三家的通用能力扩展标准 |
| 技能触发 | 无 | description 自动触发 + paths 条件触发 + 手动 /skill | ❌ |
| 技能执行 | 无 | context: fork（在子代理中执行）、allowed-tools 预授权、dynamic context injection（!command 注入实时数据） | ❌ |
| 工具权限 | admin_only 过滤 | 权限模式（allow/ask/deny/auto）+ 工具格式（Text/JSON/Image） | ⚠️ 部分达标 |

**批判**：skill 是当前 AI 工具生态的**通用标准**（Claude Code/Codex/Cursor 均支持，agentskills.io 是开放标准）。本项目有 AI-Hub 的 56 个 skills（agentskills 格式），但计划中**完全没有把 skill 机制接入 agent 运行时**——这是 AI-Hub 资产的浪费，也是与竞品能力对齐的重大缺失。

### 维度 5：harness 架构 —— ⚠️ 过度设计且缺核心循环

| 对比项 | 计划 | 竞品实测 | 判定 |
|--------|------|---------|------|
| 架构 | 6 节点 LangGraph 图（route→plan→fan-out→merge→reflect→answer） | Claude Code：agentic loop harness（system prompt→工具调用→环境反馈→循环）；Anthropic 官方："agents are typically just LLMs using tools based on environmental feedback in a loop...implementation is often straightforward" | ⚠️ 计划偏重：6 节点图对教育问答场景可能是过度设计；图编排固定开销+难以像循环 harness 那样自由探索 |
| 自适应工具选择 | 预定义 route 分 4 类 → plan → 固定 fan-out | 模型在循环中**自行决定**用哪个工具（无预定义路径） | ⚠️ 计划是 workflow（固定路径），非 agent（自由循环）。Anthropic：workflow 适合"可预测固定路径"——教育问答基本可预测，勉强可接受，但灵活性差 |
| 探索深度 | reflect ≤2 轮强制 answer | 循环 harness 可自由 N 轮直到完成（maxTurns 配置） | ❌ 探索受限 |

**批判**：Anthropic 原话"**Don't overengineer**：start with simple prompts, add multi-step agentic systems only when simpler solutions fall short"。计划的 6 节点图对"教育问答/检索/学习建议"场景可能是过度设计——一个循环 harness（model 自由用检索工具+记忆工具直到回答充分）可能更简单更有效。6 节点图最大的问题是**固定路径无法处理未预料的任务类型**。

### 维度 6：上下文记忆/记忆存储 —— ⚠️ 机制缺显式触发与索引模式

| 对比项 | 计划（task25） | Claude Code 实测 | 判定 |
|--------|--------------|-----------------|------|
| 记忆写入 | 会话结束异步写（队列） | **用户纠正/偏好触发**（"Saved 2 memories"）+ 自动学习 | ⚠️ 缺显式触发：会话结束批量写会漏掉"用户纠正"这类高价值信号 |
| 记忆结构 | user_memory 表（importance 字段） | MEMORY.md 索引（200 行/25KB 上限）+ topic 文件按需读取 + modified 时间戳 | ❌ 缺索引文件模式：计划只有"向量召回 top-3"，没有 Claude Code 的"索引+按需读 topic"模式 |
| 记忆读取 | 检索 top-3 进 plan | MEMORY.md 每次会话加载前 200 行 + topic 按需读 | ⚠️ 方向不同：Claude Code 是"索引常驻+详情按需"，计划是"向量召回"——两者可互补但计划缺前者 |
| 子代理记忆 | 无 | 子代理独立 memory 目录（user/project/local scope） | ❌ 缺 |
| 遗忘 | exp 衰减+500 条淘汰 | 无显式遗忘（靠 MEMORY.md 精简提示），用 modified 时间戳管理时效 | ⚠️ 计划的 exp 衰减是学术模型，Claude Code 用更工程化的"精简索引"方式；两者思路不同 |

**批判**：计划的记忆体系（三层+遗忘）有学术依据（Ebbinghaus），但缺两个 Claude Code 的核心机制：**①显式记忆触发**（用户纠正/明确要求"记住 X"→立即写，而非会话结束批量写）；②**索引文件模式**（MEMORY.md 常驻+topic 按需）。以及子代理独立记忆。

### 维度 7：LangGraph 节点逻辑 —— ⚠️ 可行但缺生产级细节

| 对比项 | 计划 | 竞品 | 判定 |
|--------|------|------|------|
| 图结构 | 6 节点+条件边 | Claude Code 非图（循环）；Codex 也是循环 | ⚠️ 图本身可行（Anthropic workflow 模式认可），但节点内逻辑需加强 |
| 持久化 | Redis checkpointer | 会话持久化+恢复+分叉（--continue/--resume/--from-pr） | ✅ 达标 |
| 恢复 | 崩溃后同 thread_id 恢复 | 会话恢复+checkpointing（rewind 文件变更+对话） | ⚠️ 缺文件级 checkpoint（rewind 文件变更到任意状态） |
| 中断 | HITL interrupt | HITL + approvals + advisor 工具 | ✅ 达标 |

**批判**：LangGraph 图+checkpointer 是合理选型（Anthropic workflow 模式认可），但缺竞品的文件级 checkpoint/rewind 能力。

### 维度 8：优化 token 消耗 —— ❌ 缺 context editing 与 tool result clearing 细节

| 对比项 | 计划（task26/27） | Claude Code 实测 | 判定 |
|--------|------------------|-----------------|------|
| compaction | >6000 token 触发压缩 | 自然断点手动触发+自动触发+压缩后重载 CLAUDE.md | ✅ 达标 |
| **context editing** | 无 | **精确删除历史消息**（不重写、保留前缀缓存） | ❌ **关键差距**：context editing 是最省 token 的手段（保留缓存前缀），计划只有全量压缩 |
| tool result clearing | 仅 compaction 里提"丢弃冗余" | 官方最轻量手段（深层历史工具结果清除） | ⚠️ 计划有概念无独立实现 |
| 前缀稳定 | 静态前缀稳定化 | 三层组织（system/project/conversation）+ MCP tool search 延迟加载 | ⚠️ 计划缺 MCP 延迟加载对前缀的保护 |

**批判**：token 优化是竞品差距最明显的维度之一。Claude Code 的 **context editing**（精确删消息、保留缓存）是比全量 compaction 更优的手段（官方："The safest lightest touch form of compaction is tool result clearing"），计划完全没有。compaction 是重武器，context editing 才是日常省 token 的手段。

### 维度 9：缓存命中率 —— ❌ 缺失效管理与监控

| 对比项 | 计划 | Claude Code 实测 | 判定 |
|--------|------|-----------------|------|
| 缓存组织 | 静态前缀稳定化（简单方案） | 三层组织（system prompt 在前/project context 中间/conversation 最后） | ⚠️ 计划未定义三层组织，只笼统"前缀稳定" |
| **失效清单** | 无 | 明确失效清单：模型切换/effort 切换/MCP 连接变化/工具 deny/compaction/升级 | ❌ **关键差距**：计划未识别"MCP 工具描述变更"（task33 描述审查会改描述！）会导致缓存失效 |
| 监控 | 仅 task29 提"命中≥80%目标" | cache_read/creation_input_tokens 指标（statusline 实时可见）+ OTel 导出 | ❌ 缺监控手段设计 |
| TTL | 未提 | 5min/1h TTL 选择（按认证方式自动）+ env 覆盖 | ❌ 未设计 |
| MCP 与缓存协同 | 无 | tool search 延迟加载=工具不进前缀=缓存不失效 | ❌ 缺（与维度 2 同根） |

**批判**：缓存命中率是 Claude Code 官方强调"**prompt caching is everything**"的核心。计划的"静态前缀稳定化"过于粗放：①未定义三层缓存组织；②未识别 MCP 描述审查会破坏前缀（自相矛盾）；③缺 cache_read/creation 监控手段；④缺 TTL 管理。**没有监控就无法声称"命中率≥80%"**——这是个无法验证的目标。

---

## 二、差距量化总结

| 维度 | 差距等级 | 核心缺陷 | 修复难度 |
|------|---------|---------|---------|
| RAG 切分/检索 | ⚠️ 部分达标 | 缺语法感知切分+在线监控 | 中 |
| MCP 效率 | ❌ 结构性落后 | 缺 tool search 延迟加载/认证/自动重连/子代理隔离 | 大 |
| 多 agent | ❌ **结构性错误** | **子代理无独立上下文（共享 state）** | 大（需重构） |
| tool/skill | ❌ 结构性缺失 | 无 skill 机制（SKILL.md/渐进式披露） | 中（AI-Hub 已有 56 个 skills 待接入） |
| harness | ⚠️ 过度设计 | 6 节点图 vs 循环 harness；探索受限 | 中 |
| 记忆 | ⚠️ 部分达标 | 缺显式触发+索引文件模式+子代理记忆 | 中 |
| LangGraph 节点 | ⚠️ 可行 | 缺文件级 checkpoint/rewind | 小 |
| token 优化 | ❌ 关键差距 | 缺 context editing/tool result clearing | 中 |
| 缓存命中率 | ❌ 关键差距 | 缺三层组织/失效清单/监控/TTL | 中 |

**结构性缺陷 3 个（必须重构而非调参）**：子代理无独立上下文（维度 3）、无 skill 机制（维度 4）、MCP tool search 缺失（维度 2/9 同根）。

---

## 三、修复建议（task24~36 升级为对标方案）

1. **子代理独立上下文（维度 3）**：将 LangGraph 节点内"共享 state 的 gather"改为**真正独立的 LLM 会话**（每个子代理独立 messages 数组+独立 system prompt+独立工具集，返回蒸馏摘要进主 state）。LangGraph 可用 `Send` API + 独立 node state 实现，或用并行 LLM 调用封装。
2. **skill 机制接入（维度 4）**：运行时支持 agentskills.io 标准 SKILL.md 渐进式披露（description 进上下文、body 按需加载、paths 触发、context:fork 子代理执行）——直接消费 AI-Hub 现有 56 个 skills。
3. **MCP tool search（维度 2/9）**：工具描述延迟加载（不进前缀）、按需发现、OAuth 认证、自动重连、子代理级 mcpServers 隔离。
4. **context editing（维度 8）**：实现精确消息删除（保留缓存前缀）作为 compaction 之前的日常手段；tool result clearing 独立实现。
5. **缓存三层组织+监控（维度 9）**：system prompt（含工具描述，稳定在前）/项目上下文（中间）/对话（最后）；cache_read/creation 指标暴露到 /metrics；失效清单文档化（模型/effort/MCP/工具变更/compaction 触发）；TTL 配置。
6. **语法感知切分（维度 1）**：接入 tree-sitter（Python 可用 tree_sitter 包）对代码/结构化教材按 AST 边界切分。
7. **显式记忆触发（维度 6）**：用户在对话中纠正/明确要求记忆→立即写（异步），会话结束只做补充。
8. **harness 简化（维度 5）**：评估集对比 6 节点图 vs 循环 harness，若循环更优则简化（Anthropic 建议）。

## 四、结论

task24~36 按当前设计完成后，是**一个能运行的 RAG+多 agent 教学问答 demo**，但不是**生产级 agent 平台**。与 Claude Code/Codex/Cursor 的真实差距集中在 3 个结构性缺陷（子代理上下文隔离、skill 机制、MCP 工具延迟加载）和 2 个工程化差距（context editing、缓存管理监控）。这些不是 token 预算或调参问题，而是**架构层面的设计差距**，必须在实施前修订设计。
