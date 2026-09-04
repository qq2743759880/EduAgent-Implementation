# 技术选型来源审计（Tech Source Audit）

> 要求：每个技术栈/方案/策略必须注明参考来源（文献/网站/竞品），并自我批判"是否为最优解"及选用原因。
> 维护：本文件随方案变更同步更新；dev-plan 每个任务的"选型依据"引用本文件。

## 一、后端基础栈

| 选型 | 参考来源 | 自我批判（是否为最优解） | 选用原因 |
|------|---------|------------------------|---------|
| Python 3.11 + FastAPI | ① FastAPI 官方文档（fastapi.tiangolo.com）② 字节 CloudWeGo 官网（Kitex/Hertz 为 Go 栈，cloudwego.io）③ 腾讯 tRPC（Go）| **非绝对最优**：字节 Kitex/腾讯 tRPC 在 RPC 吞吐上优于 FastAPI，但均为 Go 生态；本项目团队 Python 成熟度远高于 Go，且现有 edu-agent 全部代码为 Python（迁移成本负收益）。单机 QPS 场景 FastAPI+asyncmy 足够 | 存量资产最大化复用；全异步栈与 LangGraph Python 生态天然一致 |
| 模块化单体（不拆微服务） | ① 字节 CloudWeGo 官网（2021 年 5 万+ 微服务规模）② Martin Fowler "Monolith First" ③ Netflix "Ready for microservices" 反例 | **是当前规模的最优解**：微服务的前提（大团队并行/独立扩容/多语言）本项目均不具备；但已按领域分目录（domains/）留拆分缝。批判点：若未来交易域流量暴涨需独立扩容，需按域切开（方案已预留） | 运维成本/分布式事务复杂度为负收益；单 MySQL 实例下 Saga/Outbox 不必要 |
| 数据库访问：asyncmy 原生 SQL + repository 层 | ① asyncmy 官方 ② 现有 app/database.py 体系（fetch_one/execute_write/读写分离/慢查询）③ SQLAlchemy 官方（被否决） | **最优**：66 表 CRUD 场景 ORM 收益低（无复杂关系导航），且现有底座含 RO 池/事务/慢查询监控，重写风险大。批判点：SQL 拼装易错，用 crud_mixin + 参数化 SQL + 单测缓解 | 存量底座复用；全异步 |
| 响应壳 {code,message,data} | ① 字节 API 网关惯例（头条系接口规范）② edu-data app/response.py ③ 腾讯开放平台网关 | **最优**：消除现状双格式解析混乱；SSE 例外已定义 | 团队统一 + 大厂惯例 |

## 二、AI 助手架构

| 选型 | 参考来源 | 自我批判 | 选用原因 |
|------|---------|---------|---------|
| LangGraph 1.2（保留升级） | ① LangGraph 官方文档（langchain-ai.github.io/langgraph，context7 已验证 checkpointer/HITL API）② LangGraph Redis（Checkpoint Savers + Stores）③ 字节 Eino（Go LLM 编排框架，被否决） | **Python 生态下最优**：Eino 为 Go 栈不匹配；LlamaIndex Agent 不如 LangGraph 的图原语贴近本项目"节点走向规划"需求。批判点：LangGraph 抽象层较多，按 Anthropic 建议"理解底层代码"——已要求先读官方文档 | 存量图资产 + durable execution + HITL 原生支持 |
| orchestrator-worker 多 agent | ① Anthropic《Building Effective Agents》（anthropic.com/engineering/building-effective-agents）② Anthropic《Multi-agent Research System》③ Claude Code subagents 架构 | **不是所有场景最优**：Anthropic 原文明示多 agent 消耗 15× token，仅高价值任务值得；已用 effort scaling（L0 直答/L1 2 代理/L2 3 代理/L3 2 轮 fan-out）对冲。批判点：编码类任务并行度低——本场景（教育问答/检索/规划）并行度高，适用 | 检索/工具/学习规划三类子任务天然可并行 |
| 三层记忆 + 遗忘机制 | ① Anthropic《Effective Context Engineering》（structured note-taking/agentic memory 章节）② Claude Code memory tool 公开资料 ③ Ebbinghaus 遗忘曲线（认知科学，指数衰减）④ Mem0 开源项目 | **工程折中最优**：人类遗忘曲线的 exp(-λ·Δt) 是学界共识模型；importance 打分用规则+LLM 双轨（Mem0 纯 LLM 打分成本高）。批判点：500 条容量上限是经验值，需评估集调参 | 学术依据 + 工程可实现 |
| compaction 上下文压缩 | ① Anthropic《Effective Context Engineering》Compaction 章节（Claude Code 实现描述：保留架构决策/未解决 bug/丢弃冗余工具输出）② Chroma Research "context rot" 研究 | **最优**：6000 token 阈值与保留/丢弃规则直接对齐 Anthropic 官方描述；tool result clearing 为其官方推荐最轻量手段 | 官方一手实践 |
| artifact 轻引用（子代理输出写文件系统） | ① Anthropic《Multi-agent Research System》附录"Subagent output to a filesystem to minimize the game of telephone" | **最优**：避免子代理→lead 的 token 拷贝损耗；Redis TTL 1h + 本地文件按大小分流 | 官方一手实践 |
| effort scaling 四档 | ① Anthropic《Multi-agent Research System》"Scale effort to query complexity"（简单 1 agent 3-10 calls/对比 2-4/复杂 10+） | **最优**：直接对齐官方数字并映射到本项目 L0~L3 | 官方一手实践 |
| LLM-as-judge 评估 | ① Anthropic《Multi-agent Research System》"LLM-as-judge evaluation scales when done well"（单一 judge 0-1 评分 + pass/fail） | **最优**：官方结论"单一 LLM 单 prompt 评分一致性最高"，已采用；人工评估兜底保留 | 官方一手实践 |
| HITL 退款审批（LangGraph interrupt/Command resume） | ① LangGraph 官方文档（interrupt/HumanInterrupt，context7 已验证）② Anthropic 工程博客 agent 循环中 human checkpoint 概念 | **最优**：LangGraph 原生能力，无需自研审批状态机 | 官方 API |
| tree-sitter 语法感知切分（R6 新增） | ① tree-sitter 官方（通用语法解析库，150+ 语言，Anthropic/OpenAI 内部代码工具均基于它）② Anthropic《Effective Context Engineering》context rot 章节（代码按函数/类边界切分保语义）③ 对比否决：正则/缩进启发式切分（破坏 AST 边界，检索噪声大） | **代码场景最优**：AST 边界切分保证 chunk 是完整语法单元，retrieval 精度显著优于启发式；本项目 AI 助手侧源码切分（edu-agent 代码检索）需要它。批判点：需维护 languages 映射 + 解析失败降级纯文本 | self-critique 维度4 工程差距修复（原 task30 纯文本切分），补结构性缺失 |
| agentskills.io skill 标准 + 渐进式披露（R2 新增） | ① agentskills.io（Anthropic 参与的 open skill format，Claude Code/TraeWork 共用）② Claude Code skills.md 官方（frontmatter description/paths/allowed-tools；渐进式披露：列表常驻 + body 按需注入）③ 本项目 AI-Hub 56 个既有 skills（D:\.ai-hub\skills\） | **最优**：skill 是 Claude Code/TraeWork 三家通用标准能力，本项目原 task24 完全缺失（self-critique 维度4 结构性缺失）；直接消费 AI-Hub 存量 56 skills 零成本复用。批判点：SKILL.md 质量参差，触发前需 description 审查 | self-critique 结构性缺陷修复；AI-Hub 资产统一 |
| context editing（最轻量上下文管理，R4 新增） | ① Claude Code context-window 官方文档（context editing 为"最轻量手段"，compaction 为兜底）② Anthropic《Effective Context Engineering》Compaction 章节 | **最优**：精确删历史消息保留缓存前缀（删工具调用+结果/冗余中间消息，保留用户意图/未完成决策），比无差别 compaction 省 token 且命中缓存；tool result clearing 为其官方推荐手段 | self-critique 维度4 工程差距修复（原 task26 仅 compaction，丢失前缀缓存） |
| 缓存三层组织 + 命中率监控（R5 新增） | ① Claude Code prompt-caching 官方文档（system prompt 三层组织：内置/CLI 扩展/项目 MEMORY；cache_read/cache_creation 指标；缓存失效场景清单：模型切换/effort/环境变量/MCP 工具变更/compaction/升级）② Anthropic《Effective Context Engineering》缓存章节 | **最优**：三层组织（system/project/对话）+ 指标监控是官方一手实践；本项目 MCP 工具描述进前缀导致缓存失效（self-critique 维度2 结构性缺陷），R3 延迟加载 + R5 监控联动根治。批判点：命中率目标 50% 为经验值，需实测调 | self-critique 结构性缺陷修复；让 prompt-caching 收益可度量 |

## 三、RAG / MCP

| 选型 | 参考来源 | 自我批判 | 选用原因 |
|------|---------|---------|---------|
| Contextual Retrieval（chunk 上下文前缀 + 双路召回 + rerank） | ① Anthropic《Introducing Contextual Retrieval》（实测：contextual embeddings 降 35% 失败率、+BM25 降 49%、+rerank 降 67%；top-150→rerank→top-20）② 对比否决：HyDE（论文 arXiv:2212.10496）、LlamaIndex summary index | **最优**：Anthropic 用对照实验数据证明；本项目已具备 dense+sparse 双路（Milvus RRF）与 bge-reranker-v2-m3 本地模型，增量成本仅 contextualize 写入步骤 | 实测数据最强 |
| reranker 选型 bge-reranker-v2-m3 | ① BAAI 官方模型卡（HuggingFace）② MTEB 榜单 ③ 对比否决：Cohere rerank（闭源 API 成本+数据出境）、Voyage reranker | **本地部署最优**：中文效果好、已下载到本地（RERANKER_PATH 已配置）、零 API 成本。批判点：多 worker 每进程加载 ~2.2GB 显存——已用懒加载+降级兜底 | MTEB 中文榜单 + 本地化 |
| Milvus（保留） | ① Milvus 官方文档 ② 对比否决：Qdrant/Weaviate（迁移成本）③ pgvector（无 sparse 向量原生支持） | **最优**：现有 2 集合+分区多租户+hybrid search 已上线；sparse 向量（BM25 通道）是 Contextual Retrieval 双路的关键，pgvector 不支持 | 存量 + sparse 支持 |
| MCP 工具描述自动审查重写 | ① Anthropic《Multi-agent Research System》"tool-testing agent…40% decrease in task completion time" ② MCP 官方规范（modelcontextprotocol.io） | **最优**：官方明示差描述浪费 40% 时间，审查重写是直接对策 | 官方一手实践 |

## 四、数据/中间件

| 选型 | 参考来源 | 自我批判 | 选用原因 |
|------|---------|---------|---------|
| Redis 多角色（缓存/限流/checkpoint/队列/锁/排行） | ① LangGraph Redis 官方（redis-developer/langgraph-redis）② 腾讯 CKV 实践 ③ 现有 rate_limit.py 滑动窗口 | **单实例下最优**：规模不需要 Cluster；与 LangGraph Redis checkpointer 同实例减少运维面。批判点：Redis 单点故障爆炸半径大——已要求每个组件显式降级路径 | 官方适配 + 存量 |
| 缓存三防（穿透/击穿/雪崩） | ① 阿里云 Redis 最佳实践文档 ② 腾讯云缓存穿透/击穿/雪崩解决方案 ③ 黑马/极客时间教程 | **业界标准解**：空值 30s/SETNX 互斥/TTL 抖动为全行业共识，无更优解 | 行业共识 |
| 熔断器三态（Polaris 模型） | ① 腾讯 PolarisMesh 官方文档（polarismesh.cn，closed/open/half-open + 错误率阈值）② Netflix Hystrix（对比否决：停止维护）③ Resilience4j | **最优**：Polaris 是腾讯生产验证（微信支付/王者荣耀在用）；参数（min_requests=20/error_rate=0.5/open 30s/探针 3）对齐官方默认 | 生产验证 |
| 幂等三层纵深 | ① 支付行业通用实践（微信/支付宝文档幂等要求）② 唯一键幂等 + 状态机条件更新（WHERE status='pending'）为业界标准 | **最优**：三层（中间件/唯一键/条件更新）逐层兜底是支付系统标准做法 | 资金安全红线 |
| MySQL 读写分离/慢查询 | ① MySQL 官方复制文档 ② 现有 Phase 2 实现 ③ 腾讯 TDSQL 实践 | 最优（已有实现，保留调参） | 存量 |

## 五、前端技术栈

| 选型 | 参考来源 | 自我批判 | 选用原因 |
|------|---------|---------|---------|
| Next.js 16.3 + React 19 + Tailwind v4 + shadcn（保留） | ① Next.js 官方文档 ② 现有 package.json（16.3.0/19.2.8/Tailwind v4/shadcn 4.16.2）③ AGENTS.md Next.js 16 破坏性变更警告 ④ **生态实证（2026-08-18 npm/GitHub api）**：Next.js 月下载 2.17 亿 = Remix 74×/Vue 3.9×/Svelte 9.9×，stars 14.2 万全球框架第一 ⑤ 对比否决：Vite+React18（PromptForge 兄弟栈）、Remix/React Router v7（下载 292 万远小）| **最优（生态+存量+扩展三支柱，详见 frontend-framework-critique.md）**：①生态碾压（组件/文档/人才/问答最多）②存量 package.json 全套最新 stable 锁定，重写负收益 ③React 19 官方优先支持 + 手机端响应式/PWA/Capacitor 路径成熟。批判点：构建慢/SC 学习曲线/Vercel 锁定——均已评估可接受，版本 16.3.0 固定 | 生态数据 + 存量锁定 + 手机端扩展 |
| TanStack Query 5 + zustand | ① TanStack 官方 ② zustand 官方 ③ 现有实现 | 最优（存量） | 存量 |
| echarts（图表） | ① Apache ECharts 官方 ② 对比否决：Recharts/Chart.js（复杂图表能力弱） | 最优：雷达图/趋势图已实现 | 存量 |

## 六、前端设计（tokens 来源）

| 选型 | 参考来源 | 自我批判 | 选用原因 |
|------|---------|---------|---------|
| 主色 indigo #4F46E5 | ① Tailwind 官方色板 indigo-600 ② 竞品调研：腾讯课堂（蓝）、网易云课堂（红）、ima（腾讯知识库，紫蓝系）、Coursera（蓝）、Udemy（紫）③ 教育行业"信任蓝紫"惯例 | **不是唯一解**：教育平台主流为蓝/紫系（Coursera 蓝、Udemy 紫），indigo 兼得专业感与差异化；腾讯课堂的纯蓝同质化严重。批判点：品牌辨识度弱于自研色——本项目以可读性优先，接受该折中 | 竞品调研 + shadcn 原生兼容 |
| 单主色红线（禁 sky/violet 功能分色） | ① 反 AI-slop 设计文章（antislop.fyi）② doc-frontend 规范既有红线 | **最优**：多主色是 AI 生成代码的典型 slop 特征 | 设计纪律 |
| 状态色 emerald/amber/rose | ① Tailwind 官方语义色 ② 各平台订单/工单状态色惯例 | 最优（语义色业界惯例） | 惯例 |
| HTML 原型审核流（每页先 HTML 参考→用户给图→返工） | ① 用户明确要求 ② 设计协作惯例（高保真原型评审）③ 对比否决：直接写 React（返工成本高） | **最优**：视觉评审发生在最便宜的介质（HTML）上，用户已有"给设计图"的工作习惯 | 用户要求 + 返工成本 |
| 断点 375/768/1024/1280/1440 | ① Material Design 断点 ② Tailwind 默认断点 ③ 现有视觉验收截图矩阵 | 最优（行业标准） | 惯例 |

## 七、数据重灌/运维

| 选型 | 参考来源 | 自我批判 | 选用原因 |
|------|---------|---------|---------|
| full 档 + 分夜跑批 + 断点续跑 | ① edu-data generate 脚本（progress.py 已有 checkpoint）② 用户决策（分夜跑批）③ 字节数据中台批量任务实践 | 最优：夜间窗口 + 幂等 upsert 是批处理标准做法 | 用户决策 + 工程惯例 |
| NetworkManager 隔离 + 禁 core dump（VM 根治） | ① RHEL/CentOS NetworkManager 官方文档（unmanaged-devices）② Docker 官方 daemon.json default-ulimits | 最优（官方配置项直接对症） | 官方文档 |
