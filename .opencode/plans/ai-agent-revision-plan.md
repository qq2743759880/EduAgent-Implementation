# AI 助手架构 8 项修订计划（self-critique → 修订方案）

> 依据：`self-critique-ai-agent-vs-competitors.md`（九维度批判，3 结构性缺陷 + 5 工程差距）
> 目标：将 task24~36 从"能跑的 RAG demo"升级为对标 Claude Code/TraeWork/Cursor 的生产级 agent 平台
> 范围：修订现有 task24/25/26/27/30 + 新增 task92~99（追加编号，避免重排已执行任务）
> 原则：每项修订都给出"设计变更 + 竞品依据 + 验收标准"，实施时按任务文档执行

---

## 修订总览

| # | 修订项 | 对应维度 | 动作 | 涉及任务 |
|---|--------|---------|------|---------|
| R1 | 子代理独立上下文 | 维度3（结构性） | 重构 | task24 改造 + 新增 task92 |
| R2 | skill 机制接入 | 维度4（结构性） | 新增 | 新增 task93（运行时）+ task94（AI-Hub 56 skills 接入） |
| R3 | MCP tool search + 认证 + 重连 + 子代理隔离 | 维度2/9（结构性） | 新增 | task33 改造 + 新增 task95 |
| R4 | context editing + tool result clearing | 维度8（关键） | 新增 | task26 改造 + 新增 task96 |
| R5 | 缓存三层组织 + 监控 + 失效清单 | 维度9（关键） | 新增 | task27 改造 + 新增 task97 |
| R6 | tree-sitter 语法感知切分 | 维度1 | 改造 | task30 改造 |
| R7 | 显式记忆触发 + 索引文件模式 | 维度6 | 改造 | task25 改造 |
| R8 | harness 简化评估（6节点图 vs 循环） | 维度5 | 评估后定 | task29 扩展 |

---

## R1：子代理独立上下文（结构性重构）

### 现状问题
计划的"子代理"是 LangGraph 节点内 asyncio.gather，4 个子代理共享同一 state/context window —— **丢失子代理核心价值（上下文隔离）**。检索结果/工具输出全留在主上下文，蒸馏摘要和 artifact 收益被抵消。

### 竞品依据
Claude Code sub-agents 官方文档："Each subagent runs in its own context window with a custom system prompt, specific tool access, and independent permissions." 25 个 frontmatter 字段（model/tools/disallowedTools/permissionMode/maxTurns/skills/mcpServers/hooks/memory/isolation）。

### 设计变更
```
改造前（共享 state）：plan_node → asyncio.gather(4个函数共享 state) → merge
改造后（独立上下文）：
  plan_node 产出 SubagentTask[]（每项含 agent 类型/目标/工具白名单/model）
  → 并行启动 N 个独立 subagent 会话（独立 messages 数组 + 独立 system prompt + 独立工具集）
  → 每个 subagent 独立循环（≤maxTurns 轮），结果蒸馏为 ≤1000-2000 token 摘要
  → 摘要进主 state，完整输出写 artifact（Redis TTL 1h）
```

### 实现要点
1. 新增 `app/ai/subagents/runner.py`：`run_subagent(spec, task) -> SubagentResult`（独立 LLM 会话循环）
2. 新增 `app/ai/subagents/definitions.yaml`：子代理定义（对齐 Claude Code frontmatter 子集：name/description/tools/model/maxTurns/memory_scope）
3. 内置 4 子代理：search（只读工具+检索）、tool（MCP 工具）、learning（画像+规划）、memory（记忆召回）
4. 主图（graph.py）改造：plan_node 产任务清单 → **并行启动子代理（非共享 state）** → merge_node 汇总摘要 → reflect → answer
5. LangGraph 的 Send API 用于 fan-out（每个子代理独立 state 通道），或用 asyncio.gather 启动独立会话
6. 子代理缓存：独立 5min TTL（对齐 Claude Code）
7. user_id/thread_id 注入子代理

### 验收标准
- Given 2 个并行子代理任务，When 执行，Then 各自独立上下文（总 token = 主上下文 + Σ子代理上下文，非共享叠加）
- Given 子代理检索 100 个文档，When 完成，Then 主 state 仅含蒸馏摘要 ≤2000 token，原文在 artifact
- Given 子代理崩溃，When 主图重试，Then 不污染主上下文（独立会话隔离）
- 对齐：`crawler 抓取的 sub-agents.md` 中子代理定义字段全部支持

### 风险与缓解
- 多会话并发成本 → effort scaling 保守化（已有）+ 并发闸（已有 task26）
- 子代理间共享信息丢失 → artifact 轻引用 + merge 阶段冲突检测（已有）

---

## R2：skill 机制接入（结构性缺失）

### 现状问题
计划完全无 skill 机制。AI-Hub 已有 56 个 skills（agentskills.io 标准 SKILL.md），但 agent 运行时无法使用。三家竞品（Claude Code/TraeWork/Cursor）均支持 skill。

### 竞品依据
Claude Code skills 文档："a skill's body loads only when it's used... description truncated at 1,536 characters in the skill listing to reduce context usage" + dynamic context injection + paths 条件触发 + context:fork + allowed-tools。

### 设计变更
```
新增 app/ai/skills/：
  runtime.py    — SKILL.md 解析器（frontmatter: description/name/paths/context/disable-model-invocation/allowed-tools）
  registry.py   — 扫描 AI-Hub skills 目录（D:\.ai-hub\skills\**\SKILL.md）→ 内存注册表
  loader.py     — 渐进式披露：description 列表常驻上下文（≤1536 字符/条），body 按需加载
  trigger.py    — description 匹配触发 + paths 条件触发（工作文件匹配时自动加载）
  fork_exec.py  — context:fork 时在独立子代理上下文执行 skill
```

### 实现要点
1. registry 启动时扫描 AI-Hub skills + 项目 .claude/skills/，build 索引（name/description/paths）
2. 主上下文只放 description 列表（每 skill ≤1 行），body 不进前缀 → 保护缓存（R5 联动）
3. 决策 LLM 根据 description 判断何时加载 skill；加载后 body 注入当前轮次
4. allowed-tools 字段 → 该轮次工具预授权；disable-model-invocation → 仅手动触发
5. skill 执行可在主上下文或 fork 子代理（context:fork 时走 R1 的 runner）

### 验收标准
- Given AI-Hub 56 个 skills，When 启动 registry，Then 全部索引（name/description/paths 可查）
- Given 用户请求触发某 skill 描述匹配，When 决策，Then skill body 按需注入（不进前缀）
- Given skill 含 allowed-tools，When 执行，Then 该轮工具免授权
- 对齐：`crawler 抓取的 skills.md` 的 frontmatter 字段全部支持

---

## R3：MCP tool search + 认证 + 重连 + 子代理隔离（结构性）

### 现状问题
MCP 工具描述全量进 system prompt → 随 server 数增长，前缀变化导致缓存失效（且 task33 描述审查重写描述会加剧失效）。缺 OAuth/自动重连/子代理级隔离。

### 竞品依据
Claude Code prompt-caching 文档："Tools loaded into the prefix: any change to them invalidates the cache... Deferred tools, the default on supported models: a server connecting, disconnecting, or changing its tool list only appends new content and doesn't disturb anything already cached." + mcp.md 自动重连/动态工具更新。

### 设计变更
```
改造 task33：
  1. MCP 工具延迟加载（tool search）：主上下文只放工具摘要列表（name+一句话），
     完整描述按需加载（决策 LLM 选定工具后拉取）→ 工具变更不破坏前缀缓存
  2. 描述审查改造：rewrite 描述 → 更新延迟加载的完整描述（不进前缀），
     摘要列表保持稳定（只有 name+一句话）
新增 task95（MCP 增强 v2）：
  3. OAuth 认证支持（Authorization Code flow + API key 注入）
  4. 自动重连（stdio 进程退出/HTTP 会话过期 → 按指数退避重连）
  5. 动态工具更新监听（server 推送工具变更 → 更新注册表，不重启会话）
  6. 子代理级 mcpServers 隔离（子代理只挂所需 server，工具不进主上下文）
  7. per-tool 结果大小限制（超限截断+告警）
```

### 验收标准
- Given 某 MCP server 工具列表变更，When 会话中发生，Then 缓存前缀不受影响（deferred tools 语义）
- Given MCP server 进程退出，When 检测，Then 自动重连（指数退避 ≤5 次）
- Given 子代理任务，When 配置 mcpServers 子集，Then 仅该子代理可见，主上下文不含这些工具
- Given OAuth 配置，When 启动，Then 自动走认证流程并注入请求

---

## R4：context editing + tool result clearing（关键差距）

### 现状问题
计划只有全量 compaction（重武器），缺 context editing（精确删消息保留缓存前缀）——官方称"the safest lightest touch form of compaction"。

### 竞品依据
Claude Code context-window/compaction 文档："What survives compaction... project-root CLAUDE.md survives... context editing 精确删除历史消息，保留前缀缓存"。

### 设计变更
```
改造 task26 交付物：
  1. context_edit.py：精确删除指定历史消息（如已完成任务的工具输出、旧的中间推理）
     - 删除范围：工具调用+结果、冗余中间消息
     - 保留范围：用户意图、未完成决策、系统关键消息
     - 删除后前缀稳定（后续消息不变，缓存可命中）
  2. tool_result_clearing：工具结果在 N 轮后自动精简为一行结论（原文进 artifact）
  3. 触发策略：每轮前评估上下文 → 优先 context_edit（轻量）→ 仍超阈值才 compaction（重量）
新增 task96（上下文管理 v2）：
  4. 上下文使用率监控（token 估算+展示）
  5. 自动阈值策略配置化（可调 context_edit/compaction 触发点）
```

### 验收标准
- Given 历史含 3 条已完成工具调用（各 1500 token），When context_edit，Then 删除后上下文减 ~4.5k token，后续消息前缀不变（可缓存）
- Given 工具结果已处理，When 超 N 轮，Then 自动精简为一行结论（原文进 artifact）
- Given 上下文超阈值，When 触发，Then 优先 context_edit，仍超才 compaction

---

## R5：缓存三层组织 + 监控 + 失效清单（关键差距）

### 现状问题
计划"静态前缀稳定化"过于粗放：未定义三层组织、未识别 MCP 变更破坏前缀、缺 cache_read/creation 监控、"命中≥80%"无法验证。

### 竞品依据
Claude Code prompt-caching 文档三层表：System prompt（第一层，rarely changes）/Project context（第二层，session start）/Conversation（第三层，每轮变）。失效清单：模型切换/effort/连接 MCP/工具 deny/compaction/升级。监控：cache_read_input_tokens/cache_creation_input_tokens。

### 设计变更
```
改造 task27 交付物：
  1. 三层缓存组织（对齐 DeepSeek context caching 前缀规则）：
     Layer1 system prompt（角色/工具摘要/输出规范，最稳定）
     Layer2 项目上下文（CLAUDE.md 风格项目记忆/记忆索引）
     Layer3 对话（每轮追加）
  2. 失效清单文档化（写入 design-guide）：
     - 模型切换（fast↔strong）→ 缓存失效
     - 工具集变化（MCP server 连接/断开）→ R3 deferred 后不失效
     - skill 加载（R2 body 按需）→ 追加不失效
     - compaction/context_edit → context_edit 保留前缀，compaction 失效
  3. 前缀稳定性约束：工具摘要列表稳定（只追加新工具，不重排）
新增 task97（缓存监控）：
  4. cache_read/cache_creation token 指标 → Prometheus /metrics（deepseek usage 字段）
  5. 命中率 = read/(read+creation)，暴露 Gauge
  6. 监控告警：命中率 <50% 持续 1h → 告警
  7. TTL 配置（DeepSeek context caching 的 cache 时长）
```

### 验收标准
- Given 正常多轮对话，When 观察 /metrics，Then cache_read/cache_creation 持续上报，命中率 >50%（优化后 >80%）
- Given MCP server 连接/断开，When 变更后，Then Layer1 前缀不变（deferred tools 生效），命中率不受影响
- Given 模型切换 fast→strong，When 发生，Then 命中率短暂下降并记录失效原因
- 对齐：`crawler 抓取的 prompt-caching.md` 失效清单全覆盖

---

## R6：tree-sitter 语法感知切分（部分差距）

### 现状问题
纯文本切分对代码/结构化教材无语法感知（Cursor 用 tree-sitter AST 边界切分）。

### 竞品依据
Cursor 代码索引（行业公开认知）：tree-sitter 语法树 + BM25 + embeddings 混合。

### 设计变更
```
改造 task30 交付物：
  1. chunker 新增 tree_sitter 模式：对代码文件（py/js/ts/java/sql）按 AST 节点边界切分
     - 函数/类/方法为最小 chunk 边界
     - 大文件先按顶层节点切，再按内部小节点细分
     - 保留语法上下文（函数签名+docstring+体）
  2. 结构化文档（md）保留原有纯文本切分 + contextualize 前缀
  3. 混合策略：按文件类型选择切分器（代码→tree-sitter，文档→纯文本）
```

### 验收标准
- Given Python 文件含 3 个函数，When 切分，Then chunk 边界在函数边界，不跨函数
- Given 代码 chunk 检索，When 命中某函数，Then chunk 含函数签名+docstring（可定位）
- Given 非代码文件，When 切分，Then 走原纯文本路径

---

## R7：显式记忆触发 + 索引文件模式（部分差距）

### 现状问题
计划只有会话结束异步写（漏掉用户纠正这类高价值信号）；缺 MEMORY.md 索引模式。

### 竞品依据
Claude Code memory 文档："When Claude writes a memory file... 'Saved 2 memories'... MEMORY.md acts as an index... first 200 lines or 25KB loaded at start... topic files read on demand"。

### 设计变更
```
改造 task25 交付物：
  1. 显式触发（新增）：
     - 用户纠正/明确要求"记住 X" → 立即写（异步）
     - 会话中检测到高价值事实（如用户职业/目标/偏好）→ 即时写
     - 会话结束补充（保留原有）
  2. 索引文件模式（新增）：
     - 用户级 MEMORY.md 索引（常驻上下文，≤200 行/25KB）
     - topic 文件（debugging.md/learning-goals.md 等）按需读取
     - 向量记忆保留（Milvus 召回 top-3）作为补充检索
  3. 子代理独立记忆（R1 联动）：子代理可配置 memory_scope，独立记忆目录
```

### 验收标准
- Given 用户在对话中纠正"我不学 Java，学 Python"，When 检测，Then 立即写记忆（非会话结束）
- Given MEMORY.md 超 200 行，When 写索引，Then 提示精简（对齐 Claude Code 行为）
- Given 子代理配置 memory，When 运行，Then 独立记忆目录读写
- 对齐：`crawler 抓取的 memory.md` 的 MEMORY.md 索引 + topic 模式

---

## R8：harness 简化评估（6节点图 vs 循环）

### 现状问题
6 节点固定图可能是过度设计（Anthropic 官方"don't overengineer"）；探索深度受限（reflect ≤2 轮）。

### 竞品依据
Anthropic《Building Effective Agents》："agents are typically just LLMs using tools based on environmental feedback in a loop... implementation is often straightforward"；workflow vs agent 的取舍（固定路径=workflow，自由=agent）。

### 设计变更
```
改造 task29 交付物：
  1. 评估集增加对比组：6 节点图 vs 简化循环 harness（route→tool loop→answer）
  2. 指标：准确率/延迟 P95/成本（token）/失败恢复率
  3. 决策规则（写入报告）：
     - 若循环 harness 准确率 ≥ 图方案且成本更低 → 采用循环 harness
     - 若图方案更优（如教育流程确定性高）→ 保留图，但 reflect 轮次放宽至 ≤4
  4. 无论选哪种，保留 R1 子代理独立上下文（二者不冲突）
```

### 验收标准
- Given 评估集（四类意图+L1~L3），When 对比两方案，Then 输出准确率/延迟/成本对照表
- Given 选定方案，When 实施，Then 附选择理由（数据驱动）

---

## 任务映射汇总

| 任务 | 动作 | 修订内容 |
|------|------|---------|
| task24 | 改造 | R1 子代理独立上下文（runner + definitions.yaml） |
| task25 | 改造 | R7 显式触发 + MEMORY.md 索引模式 |
| task26 | 改造 | R4 context_edit + tool_result_clearing（compaction 保留为最后手段） |
| task27 | 改造 | R5 三层缓存组织 + 失效清单文档化 |
| task29 | 改造 | R8 harness 对比评估 |
| task30 | 改造 | R6 tree-sitter 切分 |
| task33 | 改造 | R3 部分（工具延迟加载 + 描述审查改为不进前缀） |
| **task92** | 新增 | R1 子代理定义+runner（独立上下文）—— 从 task24 拆出独立任务便于验收 |
| **task93** | 新增 | R2 skill runtime（解析/注册/渐进式披露/触发） |
| **task94** | 新增 | R2 AI-Hub 56 skills 接入验证 |
| **task95** | 新增 | R3 MCP 认证/重连/动态更新/子代理隔离 |
| **task96** | 新增 | R4 上下文监控+阈值策略配置 |
| **task97** | 新增 | R5 缓存监控（/metrics + 告警 + TTL） |

## 实施顺序（依赖）

```
task92 (R1) → task93/94 (R2，依赖 R1 的 fork 能力)
task95 (R3，独立) → 与 task33 改造并行
task96 (R4) → 依赖 task26 改造
task97 (R5) → 依赖 task95（MCP 延迟加载）与 task27 改造
task30 改造 (R6) → 独立
task25 改造 (R7) → 独立，与 R1 联动
task29 改造 (R8) → 最后（需其他落地后对比）
```

## 与现有计划的衔接

- 追加编号 task92~97（task00~91 已推进至 task02，重排代价大）
- 看板新增 6 行
- tech-source-audit.md 增补：tree-sitter/agentskills/context-editing/缓存三层 4 条选型审计
- self-critique 报告 §三 8 项 → 本计划逐项落实

## ⚠️ Checkpoint 复用硬约束（用户 2026-08-17 裁定）

> 依据：`checkpoint-critique.md`（task06 复核：4 缺陷——无原子写🔴/层粒度非批🟠/init 顺序🟠/并发双跑🔴）。
> **裁定**：task06 的 checkpoint 机制本次不改（仅 task07 使用，复用度低）；**但任何未来实现（含 AI 修订 R1~R8 中涉及持久化状态的部分）一旦复用该 checkpoint 模式，必须先按 checkpoint-critique.md 优化再使用**。

**强制优化清单（复用前必做）**：
1. **原子写**：`os.replace(tmp, file)` 替代 `open("w")`（防断电半截 JSON 丢全部进度）
2. **批级粒度**：`mark_batch_progress(layer, batch_index, rows_done)`，中断后从 batch_index 续跑（防批中断全量重跑）
3. **顺序重排**：`init_checkpoint` 先于 `init_db`，或失败时显式提示 checkpoint 现状（防误 SKIP）
4. **并发锁**：文件锁（msvcrt/fcntl）或迁移 SQLite/MySQL 表（防双跑覆盖）
5. 补测：kill -9 中断/双终端并发/批中断续跑/DB 不可用启动

**AI 修订中的落点**：R5（缓存监控）、task92（子代理 runner 的 artifact 状态）、task26（Redis 防过载的队列状态）若引入任何 checkpoint/状态持久化，必须先满足上述 1~4 条。
