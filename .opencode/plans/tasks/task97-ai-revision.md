# task97 — AI 8 项修订任务（self-critique 落地）

> 执行工具：**Trae** ｜ 依赖：— ｜ 状态：TODO
> 修订来源：`.opencode/plans/self-critique-ai-agent-vs-competitors.md` + `ai-agent-revision-plan.md`
> 核心定位：R5 缓存监控——使命中率目标可验证

## 1. 验收标准（Given/When/Then）

- **类型/工具**：agent / Trae ｜**依赖**：task95, task27 改造 ｜**并行组**：W3 ｜**工作量**：M ｜**选型依据**：self-critique §三 R5 + Claude Code prompt-caching（cache_read/creation 指标）
- **交付物**：description_reviewer.py（改写存延迟加载层）+ 摘要列表稳定 + per-server 熔断 + admin_only 过滤 + schema 版本告警 + 只读缓存 60s
- **验收**：① Given 多轮对话，When 观察 /metrics，Then 命中率持续上报 >50% ② Given MCP 变更，Then 命中率不受影响（R3 生效）③ Given 模型切换，Then 命中率下降且记录失效原因

## 附录 A：交付物总清单

1. 数据库：重构 SQL（66 表重建 + 13 删除 + 改造 + 索引 + 任务表）+ diff 校验脚本
2. 数据：full 档全量数据 + 六项计数校验报告 + 分层生成手册
3. 后端：core/ + middleware/ + 7 新域（market/order/payment/refund/enrollment/study/tickets）+ 4 改造域 + Redis 缓存层 + 响应壳统一 + pytest
4. AI 助手：LangGraph 新图 + Redis checkpointer + 三层记忆 + compaction + tool_specs + HITL + 评估报告
5. RAG：contextualize + reranker + course_public 分区 + rag_evaluator 报告
6. MCP：描述审查器 + per-server 熔断 + 审计日志
7. 前端：api-client 改造 + 8 新/10 改造客户端 + 14 基础组件 + **27 页面**（每页：HTML 审核台账 + React + 测试）
8. RAG 上传：前端 UploadPanel/PartitionPanel/TaskTable + 后端 tasks 接口 + Redis/表双写 + MinIO edu-upload 留存
9. 知识库：Milvus/Neo4j 重建报告
10. 收尾：清理报告 + 四份文档 + E2E 套件 + Locust 压测报告 + 容灾演练报告

## 附录 B：task-agent-matrix.md 重排说明（v3.0）

> 旧矩阵（59 任务编号）已随本文件重排，映射关系：旧 task36→新 task40、旧 task37→新 task41、旧 task38~53（18 页+适配组）→新 task42~68（27 页，每页一任务）、旧 task54→新 task36、旧 task55→新 task37、旧 task56→新 task38、旧 task57→新 task69、旧 task58→新 task39；后端 task00~35 编号不变。新矩阵以本文件总览表 + `tasks/taskNN-*.md` 的「Agent 调度链」节为准；`task-agent-matrix.md` 本体由编排者在下次维护时同步（本文件为规划权威）。

## 2. agent / mcp / tool / skill 调度链

- agent 链：sd-dev → sd-tester
- 竞品参考：参考 Claude Code prompt-caching.md（cache_read/creation 指标/三层组织/TTL）
- 选型依据：tech-source-audit.md + self-critique 报告（每次修订须对照竞品文档逐项验收）

## 3. workflow 调用

```js
Workflow(dev-standard.mjs, args={ skipDocs:true, skipExplore:true, skipPlan:true, startFrom:NN, rounds:NN })
```

## 4. 与其他 task 关联

- 前置依赖：—
- 联动：task92（R1）是 task24 重构基础；task93/94（R2）依赖 task92 fork 能力；task95（R3）与 task33 改造并行；task96（R4）改造 task26；task97（R5）依赖 task95 + task27
- 执行顺序：见 dev-plan.md「执行顺序（v3.2 优化后）」章节 E 阶段

## 5. 实现规划要点

- 严格对照竞品文档（Claude Code memory/sub-agents/skills/prompt-caching 官方文档已抓取，见 self-critique 报告 §〇证据来源）
- 完成动作：写完工报告 test-reports/task97-completion-report.md → git commit → sync.ps1
