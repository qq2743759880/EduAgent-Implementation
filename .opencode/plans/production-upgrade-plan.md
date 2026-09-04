# EduAgent 生产级改造方案（基于"毒舌面试官"批判 + 真实竞品对照）

> 来源：`C:\Users\Administrator\Desktop\agent优化.docx`（面试官 8 刀批判 + Q&A + ADR + 差距清单）
> 方法：每条批判用**真实网络搜索**验证竞品（Claude Code / OpenAI Codex / DeepSeek）实际做法，对照生成改造方案。
> 原则（2026-08-22 用户最高优先级）：**以真实竞品实证为唯一批判源**，每方案附真实参考来源。
> 搜索日期：2026-08-25/26。

---

## 方案 0：改造总览（差距 → 改造任务映射）

| # | 批判点 | 竞品参照 | 改造方案 | 落点任务 | 工作量 |
|---|--------|---------|---------|---------|--------|
| P1 | 记忆非事件溯源 | CortexDB / ChronoMem / Claude AutoDream | 记忆事件溯源 + 版本链 + 后台巩固 | **新 task-M1** | XL |
| P2 | 内存向量多实例不一致 | Claude 降级 Redis 共享 | Redis 共享向量降级 | **新 task-M2** | M |
| P3 | 无后台巩固(Dream) | Claude AutoDream（5 会话→fork→升维） | Dream Consolidation 子代理 | 并入 task-M1 | L |
| P4 | 上下文压缩固定丢轮 | Codex token 预算分配器 / Claude 锚定策略 | LLM 动态选片段 + 锚定闸门 | **新 task-C1** | L |
| P5 | 并发非 token 级 | DeepSeek token 预算 + 用户分级 | token 级并发预算 + 分级队列 | **新 task-G1** | M |
| P6 | 工具闭环仅重试 1 次 | Codex Orchestrator + auto-review + 熔断 | 换参/换工具/熔断/人工指南闭环 | **新 task-T1** | L |
| P7 | 缓存全量失效 | Claude 前缀稳定 + defer_loading + 填充注释 | 工具延迟展开 + 前缀锚定 + 填充达标 | **新 task-C2** | L |
| P8 | 观测性黑盒 | Codex OTel / Claude 缓存命中 SEV | trace_id + 5 维指标 + OTel 导出 | **新 task-O1** | L |
| P9 | Rerank 同进程阻塞 | vLLM continuous batching / Sidecar | Rerank 独立服务 + 批处理 | **新 task-R1** | L |
| P10 | 评估集标准题 | 影子模式 + 对抗采样 | Shadow Testing + 金丝雀 | **新 task-E1** | M |
| P11 | 硬编码 6 节点图 | Claude Managed Agents(harness/sandbox/session) | 可插拔 harness 抽象 | **新 task-A1** | L |
| P12 | HITL 单点审批 | Codex auto-review / Claude 全流程护栏 | 全流程透明护栏 + AI 审查 AI | **新 task-S1** | M |

---

## P1：记忆事件溯源 + 版本链 + 审计（最高优先级）

### 批判
- `user_memory` 表只有当前快照，无版本链、无操作人、无回滚。用户投诉"AI 瞎说我说过的话"，无法自证。
- 容量阈值 500 条/用户不真实（1000 DAU × 20 条/天 = 60 万条/月）。

### 竞品实证（真实搜索）
| 竞品 | 做法 | 来源 |
|---|---|---|
| **CortexDB**（Cassandra 之父 Prashant Malik 打造） | **事件溯源**：WAL append-only + fsync，原始事件为唯一事实源；embedding/摘要/知识图都是**异步派生的可重建视图**；每条 Fact 带 `supports: [event_id]` 回溯；重播日志可重建任意派生状态 | https://cortexdb.ai/docs/concepts/event-sourcing |
| **ChronoMem**（Google ADK 开源） | 每次写提交整个记忆快照 + 版本历史 + 自然语言回滚；append-only 事件日志 `{v_j}` + HEAD 指针 | https://arxiv.org/html/2607.27773 |
| **Ninad Pathak（合规 Agent）** | **禁止 UPDATE/DELETE**；每行含 `entity_id/memory_content/embedding/timestamp/valid_to/trace_id`；过滤 `valid_to IS NULL` 防召回旧版本；trace_id 链到推理痕迹 | https://ninadpathak.com/blog/memory-versioning-and-audit-trails/ |

### 改造方案
1. **`user_memory` 改事件溯源**：新增 `user_memory_event` append-only 表（`event_id/entity_id/memory_content/embedding/timestamp/valid_to/trace_id/operator`），`INSERT` 不 `UPDATE`；更新 = 新行 + 旧行 `valid_to` 盖章
2. **查询过滤**：检索强制 `WHERE valid_to IS NULL`（向量预过滤），防召回废弃版本
3. **审计/回滚**：`GET /api/memory/history/{entity_id}` 分页事件流；`POST /rewind` 回滚到版本
4. **容量治理**：按实体生命周期淘汰 + 快照压缩器（保留近期高保真，旧事件懒合成摘要，对齐 VikingMem TIME_COMPRESS）
5. **trace_id 溯源**：每条记忆写带 `trace_id` 指向触发它的 LLM 调用/工具调用（自证清白）

### 验收
- 1000 DAU × 20 条/天 压力下事件表无阻塞；回滚到 T 时刻状态正确；检索永不返回 `valid_to IS NOT NULL` 行。

---

## P2：多实例一致性（内存向量降级）

### 批判
- 生产多实例，实例 A/B 各自内存向量，同一用户召回不一致。

### 竞品实证
| 竞品 | 做法 | 来源 |
|---|---|---|
| **Claude** | 降级时用 Redis 做共享内存向量，或直接拒绝向量检索退回关键词 | 面试文档引述 + Claude 架构（Session 层持久化） |
| **rewind**（开源） | append-only Postgres + pgvector HNSW + Redis pub/sub 横向扩展 | https://github.com/adi-suresh01/rewind |

### 改造方案
- Milvus 不可达时降级用 **Redis 共享向量**（`MemoryVectorStore` backend 增加 `redis` 档：向量存 Redis ZSET/HSET，跨实例一致），而非进程内 dict
- Redis 也不可达才降级内存 + 显式 `degraded_reason`

### 落点
- task-M2（改造 `app/ai/memory/vector.py` 增加 redis backend）

---

## P3：后台巩固（Dream Consolidation）

### 批判
- "喜欢 Python"/"喜欢 FastAPI"/"讨厌 Java" 三条独立存储，向量召回可能只中一条，推荐 Java 乌龙。

### 竞品实证（真实搜索）
| 竞品 | 做法 | 来源 |
|---|---|---|
| **Claude AutoDream** | 5 会话 + 24h 后 fork 子代理，4 阶段（orient/gather/consolidate/prune）把三句话升维为"Python 后端开发者，适合 FastAPI 不适合 Java"；mtime 文件锁防多实例并发；回滚靠 mtime 回拨 | https://codewisdom.io/blog/ai-agents-claude-code-memory-system-notes/ 、https://soma.gravicity.ai/blog/the-architecture-of-forgetting |
| **Claude extractMemories** | 每轮后 fork 完美副本子代理跑 Opus，4 类型 taxonommy（fact/preference/skill/relationship）+ Sonnet 筛选 | 同上（soma.gravicity.ai） |
| **VikingMem**（字节） | LLM_MERGE 增量去重/冲突消解 + TIME_COMPRESS 主题时间线渐进巩固 | https://arxiv.org/html/2605.29640v3 |

### 改造方案
1. **Dream 子代理**：每 5 会话 + 24h，fork 子代理读记忆库 → 去重/合并/升维 → 写回，旧记忆标 `consolidated_version`
2. **mtime 分布式锁**（对齐 Claude）：`mtime` 窗口锁防多实例并发巩固
3. **渐进巩固**：近期高保真 + 旧事件 TIME_COMPRESS 懒合成（对齐 VikingMem）
4. **升维示例**："喜欢 Python" + "喜欢 FastAPI" + "讨厌 Java" → "Python 后端开发者" 结构化条目

### 落点
- 并入 task-M1（Dream 子代理是 M1 的一部分）

---

## P4：上下文压缩 LLM 动态选片段

### 批判
- 固定保留最近 6 轮，用户第 7 轮问"第 3 轮数据"，数据已被压掉。

### 竞品实证（真实搜索）
| 竞品 | 做法 | 来源 |
|---|---|---|
| **Codex** | token 预算分配器：系统 10%/用户问题 20%/工具结果 30%/历史 40%，LLM 动态决定保留哪些历史片段 | 面试文档 + Codex 压缩（SQLite 会话持久化 + 压缩） |
| **Claude compaction** | 服务端 compaction 阈值触发（≥50K token），保留架构决策/未决问题/关键事实，丢弃冗余；支持自定义 compaction prompt；min 50K token | https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools |
| **Claude 锚定策略** | System+工具固定前缀永久缓存；只删闸门后的工具调用日志（tool-result clearing） | https://code.claude.com/docs/en/prompt-caching |

### 改造方案
1. **token 预算分配器**：压缩时按内容类型分配预算（系统/用户/工具结果/历史），**LLM 决策保留哪些历史片段**（非按轮截断），A/B 对比现有 4 键 JSON
2. **锚定闸门**：在对话 N 轮焊死闸门，闸门前（System+核心）永不改，闸门后工具日志可压缩——保护前缀缓存
3. **tool-result clearing**：工具结果 N 轮后精简为一行结论，原文进 artifact（已部分实现，补全）

### 落点
- task-C1（改造 `app/ai/compaction.py` 为预算分配器 + 锚定）

---

## P5：token 级并发预算 + 用户分级

### 批判
- 全局 8 并发，8 个闲聊占满闸门，L3 大请求被挡。

### 竞品实证
| 竞品 | 做法 | 来源 |
|---|---|---|
| **DeepSeek-V3** | MoE 架构级成本优化 + 生产 prefill/decode 分离 + 用户分级队列 | https://arxiv.org/abs/2412.19437 |
| **通用云 LLM** | token 速率限制 + 用户配额 + 预估 token 排队 + 优先级队列 + 智能重试退避（按错误类型动态） | 面试文档引述 |

### 改造方案
1. **token 级预算**：并发闸从"请求数"改为"预估 token 速率"（system+history+query+max_tokens 估算），全局速率上限 + 用户配额
2. **分级队列**：L1~L3 优先级队列，L3 大请求优先于 L1 闲聊；排队超时友好提示（已有 10s，优化为分级）
3. **智能重试退避**：按错误类型（限流/超时/模型错）动态退避，非固定重试

### 落点
- task-G1（改造 `app/ai/guard.py`）

---

## P6：工具调用闭环（换参→换工具→熔断→人工指南）

### 批判
- 重试 1 次就回退，工具全挂无 fallback。

### 竞品实证（真实搜索）
| 竞品 | 做法 | 来源 |
|---|---|---|
| **Codex orchestrator.rs** | approval → 选沙箱 → attempt → 沙箱升级重试（denied→无沙箱重试需新审批）→ sandbox_outcome telemetry | https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/orchestrator.rs |
| **Codex auto-review** | 3 连续拒绝/10 拒绝/50 轮 内熔断中断回合；reviewer 代理决策；显式 override 路径 | https://developers.openai.com/codex/concepts/sandboxing/auto-review |
| **Codex retry telemetry** | `codex.retry` 事件带 attempt/delay/retry layer | https://github.com/openai/codex/pull/38452 |

### 改造方案
1. **闭环状态机**：第 1 次正常 → 第 2 次换参数 → 第 3 次换备用工具 → 第 4 次生成"人工操作指南"给用户 + 停止
2. **熔断（已部分实现）**：task33 已有 per-server 熔断，补"拒绝计数熔断"（Codex auto-review 3 连续拒绝中断）
3. **人工指南 fallback**：工具全挂时输出结构化人工操作步骤（非仅 need_search=True）

### 落点
- task-T1（改造 `app/mcp/executor.py` + `app/ai/flows/agent.py`）

---

## P7：缓存前缀稳定 + 填充达标

### 批判
- 工具清单增删一个 → 全量缓存失效；system prompt 300 token < 1024 门槛形同虚设。

### 竞品实证（真实搜索，关键）
| 竞品 | 做法 | 来源 |
|---|---|---|
| **Claude prompt caching** | **最小可缓存前缀 1024 token**（Opus4.8/Sonnet 4.5 等）；`cache_control` 断点；**工具定义在 system 层，变更即全失效**；defer_loading 工具存根（只名+标记，schema 被选中才展开）保前缀稳定；读缓存 ~10% 费率 | https://platform.claude.com/docs/en/build-with-claude/prompt-caching 、https://code.claude.com/docs/en/prompt-caching |
| **DEV（1024 门槛实证）** | 低于门槛静默不缓存（两计数器为 0）；填充注释撑到阈值可白嫖缓存 | https://dev.to/creeta/claudes-prompt-cache-fails-silently-below-1024-tokens-1ch1 |
| **Glean（Anthropic 工程师）** | 静态优先动态最后；不改 system prompt（用 messages 注入动态信息）；不改工具/模型中途；defer tool loading 保桩序稳定；compaction 复用父会话前缀；缓存命中率当 uptime 监控，低即 SEV | https://glean.smartcoder.ai/en/a/lessons-from-building-claude-code-prompt-caching-is-everythi-sean5e |

### 改造方案
1. **填充注释达标**：system+工具前缀用静态填充注释撑到 ≥1024 token（跨过 DeepSeek/Claude 缓存门槛）
2. **工具延迟展开**：prompt 只放工具名+一句话摘要（defer_loading 语义），完整 schema 被调用才展开——保前缀稳定（task95 已有规划，落地细节对齐此）
3. **锚定策略**：闸门前 System+工具永不变，动态信息经新消息注入；工具 schema 变更只失效该工具单条缓存
4. **缓存命中监控**：`cache_creation/cache_read_input_tokens` 计量 + 命中率告警（对齐 Claude SEV）

### 落点
- task-C2（改造 `app/ai/prompt_cache.py` + `tool_specs.py` 前缀层）

---

## P8：观测性（trace_id + 5 维指标 + OTel）

### 批判
- 只有 logger.warning，无法查"为什么用户 X 没召回 3 天前目标"。

### 竞品实证（真实搜索）
| 竞品 | 做法 | 来源 |
|---|---|---|
| **Codex** | OTel log export：user prompt/approval 决策/工具结果/MCP 使用/网络策略事件；sandbox_outcome 遥测（denied/escalated/timed_out）；活动日志进 SIEM | https://openai.com/index/running-codex-safely/ 、https://github.com/openai/codex/pull/25955 |
| **Claude** | 缓存命中率当 uptime 监控，低即 SEV；状态行显示 cache_creation/read 计数 | https://code.claude.com/docs/en/prompt-caching |

### 改造方案
1. **trace_id 贯穿**：每次记忆写/召回/LLM 调用/工具调用/压缩带 trace_id（会话级唯一）
2. **5 维指标**：记忆命中率 / 压缩效率（压缩前后 token、丢轮数）/ 工具调用成功率 / 缓存命中率 / 并发排队超时率
3. **OTel 导出**：`otel/` 模块导出结构化事件（tool_result/retry/sandbox_outcome/memory_event），灌 ClickHouse/Prometheus
4. **审计查询**：`/metrics` 端点 + trace 检索面板

### 落点
- task-O1（新增 `app/otel/` + 埋点 + metrics 端点）

---

## P9：Rerank 独立服务 + 批处理

### 批判
- Reranker 与主应用同进程，GPU 计算阻塞事件循环，QPS=50 崩。

### 竞品实证
| 竞品 | 做法 | 来源 |
|---|---|---|
| **vLLM** | continuous batching 将多请求矩阵合并，吞吐 5-10x；支持 MLA 优化 | https://github.com/deepseek-ai/DeepSeek-V3（vLLM 兼容段）+ 面试文档 |
| **SGLang** | MLA 吞吐优化 + DP Attention + FP8 KV | https://lmsys.org/blog/2024-12-04-sglang-v0-4/ |

### 改造方案
1. **Rerank 独立服务**：拆成 sidecar 进程（FastAPI 微服务），主应用经 HTTP/gRPC 调用，不阻塞事件循环
2. **连续批处理**：请求排队合并批处理（对齐 vLLM continuous batching 思路，用单模型多请求合并）
3. **消息队列削峰**：Redis/RabbitMQ 缓冲峰值

### 落点
- task-R1（`app/rerank_service/` 独立服务 + 批处理）

---

## P10：影子模式 + 对抗采样评估

### 批判
- 离线评估 62.5%，上线崩——评估集与线上脏数据分布不一致。

### 竞品实证
| 竞品 | 做法 | 来源 |
|---|---|---|
| **通用生产实践** | Shadow Testing：新旧系统同时跑线上流量，旧系统返回用户，新系统只比较；金丝雀发布 1%→3 天→全量 | 面试文档引述（canary release + shadow mode） |
| **多智能体评估** | Anthropic：多智能体系统内部评估超单体 90.2% | 面试文档引述 |

### 改造方案
1. **影子模式**：新检索系统并行跑线上流量，记录差异（不改用户结果）
2. **对抗采样**：评估集加入线上脏数据（错别字/短句）+ 对抗样本
3. **金丝雀**：1% 流量观察 3 天，无异常全量
4. **多维度 Judge**：事实正确性/完整性/无害性/连贯性分维度打分（非单一 0-1）

### 落点
- task-E1（改造 `scripts/eval/` + 影子模式开关）

---

## P11：可插拔 Harness 抽象（替代硬编码 6 节点图）

### 批判
- 6 节点图硬编码，模型升级后 reflect 节点成负担。

### 竞品实证
| 竞品 | 做法 | 来源 |
|---|---|---|
| **Claude Managed Agents** | Harness(大脑)/Sandbox(双手)/Session(记忆) 三可独立替换抽象层 | 面试文档引述 |
| **Codex** | codex-core 137 模块 Rust workspace，Session→Turn→Step 三级模型 | 面试文档引述 |

### 改造方案
- 抽象 `Harness` 接口：`route/plan/fan_out/merge/reflect/answer` 各节点实现可插拔，模型升级替换实现不改图结构；保留 DAG 为默认实现（task29 R8 keep_sixnode 已裁定），但开放接口

### 落点
- task-A1（重构 `app/ai/graph.py` 为接口化）

---

## P12：全流程 HITL 护栏（非单点审批）

### 批判
- HITL 只在退款节点，应贯穿风险行动前。

### 竞品实证（真实搜索）
| 竞品 | 做法 | 来源 |
|---|---|---|
| **Codex auto-review** | 文件写入/网络/越权前经 reviewer 代理审查；3 连续拒绝熔断 | https://developers.openai.com/codex/concepts/sandboxing/auto-review |
| **Claude** | 解释→提议→同意→行动透明护栏；permission 规则 | 面试文档引述 |

### 改造方案
- 高风险动作（写文件/执行命令/网络访问/退款）前统一 HITL-Gate：解释→提议→同意→执行；可选 AI 审查 AI（reviewer 子代理决策）

### 落点
- task-S1（`app/ai/hitl_gate.py` 统一护栏）

---

## 参考来源汇总（真实 URL）

1. CortexDB 事件溯源：https://cortexdb.ai/docs/concepts/event-sourcing
2. ChronoMem（Google ADK 记忆版本控制）：https://arxiv.org/html/2607.27773
3. Ninad Pathak 记忆审计：https://ninadpathak.com/blog/memory-versioning-and-audit-trails/
4. Claude Code Memory System（AutoDream/extractMemories/mtime 锁）：https://codewisdom.io/blog/ai-agents-claude-code-memory-system-notes/
5. Claude Forgetting 架构（autoDream 4 阶段）：https://soma.gravicity.ai/blog/the-architecture-of-forgetting
6. Claude Context Engineering（compaction/clearing/memory）：https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools
7. Claude Prompt Caching（1024 门槛/最小前缀）：https://platform.claude.com/docs/en/build-with-claude/prompt-caching
8. Claude Code Prompt Caching：https://code.claude.com/docs/en/prompt-caching
9. DEV 1024 门槛实证：https://dev.to/creeta/claudes-prompt-cache-fails-silently-below-1024-tokens-1ch1
10. Glean（Anthropic 工程师缓存经验）：https://glean.smartcoder.ai/en/a/lessons-from-building-claude-code-prompt-caching-is-everythi-sean5e
11. Codex orchestrator.rs（工具沙箱升级/审批/遥测）：https://github.com/openai/codex/blob/main/codex-rs/core/src/tools/orchestrator.rs
12. Codex auto-review（3 连续拒绝熔断）：https://developers.openai.com/codex/concepts/sandboxing/auto-review
13. Codex retry telemetry：https://github.com/openai/codex/pull/38452
14. Codex sandbox telemetry：https://github.com/openai/codex/pull/25955
15. OpenAI Codex 安全运行（OTel 导出/SIEM）：https://openai.com/index/running-codex-safely/
16. DeepSeek-V3 技术报告（MLA/MoE）：https://arxiv.org/abs/2412.19437
17. DeepSeek-V3 GitHub：https://github.com/deepseek-ai/DeepSeek-V3
18. DeepSeek 硬件洞察（MLA 70KB/token vs LLaMA 516KB）：https://arxiv.org/html/2505.09343
19. SGLang MLA 优化：https://lmsys.org/blog/2024-12-04-sglang-v0-4/
20. VikingMem（字节记忆管理 TIME_COMPRESS/LLM_MERGE）：https://arxiv.org/html/2605.29640v3
21. rewind（事件溯源 agent memory）：https://github.com/adi-suresh01/rewind

---

## 实施优先级（按影响/成本）

| 批次 | 任务 | 理由 |
|---|---|---|
| 第一批（P0 立即） | **task-M1**（事件溯源+Dream）、**task-C2**（缓存达标，直接影响成本） | 审计合规 + 成本大头 |
| 第二批（P1） | **task-C1**（动态压缩）、**task-G1**（token 预算）、**task-O1**（观测性） | 延迟/公平/可查 |
| 第三批（P2） | **task-T1**（工具闭环）、**task-S1**（HITL 护栏）、**task-R1**（rerank 服务） | 健壮性 |
| 第四批（P3） | **task-A1**（harness）、**task-E1**（影子模式）、**task-M2**（Redis 向量） | 架构演进 |

> 注意：task-M2/C1/G1/T1/C2/O1/R1/E1/A1/S1 为新任务，需更新 dev-plan 版本（v3.5）并加入看板。与既有 task93~99（R2~R5）不冲突，M1/Dream 可并入 R2 系列。