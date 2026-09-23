# YY Dev-Plan：十点修复拆任务总纲（v1，前提挑战待签收）

> PRD：`docs/PRD-阶段性测试-十点修复-v1.md`（已签收，四裁定：HITL 默认开/Jaeger 部署/人工一键拉起/措辞同步改）。
> 本文档=阶段 3 拆任务产物。**人工 gate：前提挑战签收后才能派单。**

## 一、前提挑战（6 条，逐条：主张/依据/风险/结论）

| # | 前提 | 依据 | 风险 | 结论 |
|---|---|---|---|---|
| P1 | 流式后端 SSE 正常，问题在前端渲染或路径分歧 | T7 轮 CDP 曾实测静态页渐进渲染（10→94→197→398 tokens）；owner 从未生效=真 | 若后端真断，修复面扩大到流层 | **双端（React /chat 与静态 /chat.html）CDP 抓帧定因先行，1h 内定界；定界前不动手** |
| P2 | HITL 卡 UI 链路完整，只差开关 | T12 E2E 临时开窗六场景全过（五字段帧/confirm 落库/reject 零落库） | 默认开会改变 knowledge_import 等高危工具行为 | **demo/dev 默认 true**；生产切换保留 .env 能力；用户手册标注 |
| P3 | 黄条后端字段真、前端渲染断点未知 | T7 响应字段亲测 True；chat.html `.receipt-warn` CSS/JS 代码在（:174-178）但从未视觉验证 | 渲染路径真断，需改 chat.html 渲染时序 | **CDP 视觉实证先行**，断点在哪修哪；顺手产出稳定触发话术进手册 |
| P4 | 遗留测试数据可安全清理 | T14 已有 12 个 MCP 测试 server 清理先例（三核闸） | 误删演示要用的数据 | **清理清单先给 owner 过目再执行**；三核闸（备份+行数+幂等） |
| P5 | neo4j_engine.py 接线即可用 | Neo4j 数据在（1167KP/2854 Course）、driver 在（get_neo4j_driver）、模块自带查询 | 模块内部逻辑过时/查询超时/响应 schema 与前端无对齐 | **先单测该模块直跑**；坏了修模块再接线；响应带 source 标注 |
| P6 | Jaeger all-in-one 单容器即可演示 trace | OTel SDK 埋点全（OTLP HTTP 导出）；Jaeger 支持 OTLP | 端口冲突/资源占用/SDK 与 Jaeger 版本兼容 | docker 独立端口起；失败回退=从简历删句（P0 不依赖此项） |

## 二、任务拆解（14 任务：P0 五单 / P1 五单 / P2 四单）

### P0 演示阻断（~1 天）

| ID | 任务 | GWT 验收（owner 自验口径） | 域 | 依赖 |
|---|---|---|---|---|
| **TA1** | 流式双端定因+修复：CDP 抓 SSE 帧→DOM 渲染时序，React `/chat` 与静态 `/chat.html` 双测，断点修复 | owner 亲测 3/3 次看到逐字渐进渲染 | chat 前端+React | 无 |
| **TA2** | HITL demo 默认开：.env HITL_ENABLED=true + 用户手册/简历口径标注 + admin 对话建课实弹 | admin 对话建课→确认卡→确认落库→reject 零落库，owner 亲测 | config+.env | 无 |
| **TA3** | 黄条视觉实证+稳定触发：CDP 构造触发场景→截图黄条；断点修复；触发话术进手册 | owner 照手册话术操作，黄条视觉可见 | chat.html | **依赖 TA1**（同文件串行） |
| **TA4** | 遗留数据清理：RAG 测试集合/MCP 复查/题目脏数据，三核闸+清单 owner 过目 | owner 过目清理清单后执行；清理后演示面无测试残留 | DB+Milvus | 无 |
| **N1** | 后端死亡处置=人工一键拉起（已定）：start/stop 脚本已有，手册第 5 章急救包已写 | — | 无开发 | 已结 |

### P1 体验+真实性（~1-2 天，P0 后全并行）

| ID | 任务 | GWT | 域 | 依赖 |
|---|---|---|---|---|
| **TB1** | 图谱推荐接线：neo4j_engine 单测直跑→接 recommender router（/api/recommend/graph 或 next 加 graph 源）+开关+降级 MySQL 图 | 推荐响应含 Neo4j 源候选；Neo4j 停机降级不报错；简历措辞同步改 | recommender 后端 | 无 |
| **TB2** | OTel+Jaeger：docker 起 Jaeger all-in-one（独立端口）+ .env 设 OTEL_EXPORTER_OTLP_ENDPOINT + 一次 chat 全链 trace 截图 | Jaeger UI 看到一次请求完整 span 瀑布 | docker+env | 无 |
| **TB3** | 基础设施页（admin-only）：admin-infra.html + 只读 API——Redis 四件套 live（限流计数/缓存前后耗时对比/锁状态/队列深度）+ Mongo 三集合统计+learning_event 样例 | admin 打开点「运行演示」→四件套+Mongo 实时数据可见；student 403 | 后端新端点+前端新页 | 无 |
| **TB4** | RAG/MCP 控制台 UX：五 tab+MCP 各加功能说明卡；MCP「新增 Server」分步引导表单；遗留数据复查 | owner 不读文档 5 秒内说出每页干什么、能自己完成一次配置 | admin-rag-upload/admin-mcp.html | 无 |
| **TB5** | Agent 协作自证包：docs/agent-collab-verify.md + verify-auto20.cmd 一键复核 | owner 照做 ≤15 分钟复现 17 任务核心证据 | docs+脚本 | 无 |

### P2 全量重测（~0.5 天，TB 全部交回后）

| ID | 任务 | GWT | 域 | 依赖 |
|---|---|---|---|---|
| **TC1** | 26 主张全量重测矩阵 → `docs/简历实测矩阵.md`（每条：今日实测数字+复现命令；含措辞修订建议） | 26/26 有今日实测证据 | 验证域 | TB1-TB4 |
| **TC2** | 盲测新场景执行：B10 流式 UI / B11 黄条视觉 / B12 HITL 卡 | 三场景 owner 口径全过 | 验证域 | TA1-TA3 |
| **TC3** | 手册更新 18 站（新增：图谱站补充/基础设施页/OTel 演示/建课确认卡站） | 手册与实际 UI 逐站一致 | docs | 全部 |

## 三、依赖图与并行组

```
P0: [TA2] ∥ [TA4] ∥ [TA1 → TA3]        （chat.html 同文件串行链）
P1（P0 全清后并行）: [TB1] ∥ [TB2] ∥ [TB3] ∥ [TB4] ∥ [TB5]
P2（TB 全清后）: [TC1 ∥ TC2] → [TC3]
```

## 四、契约冻结顺序与选型依据

- 契约顺序：TA1 若改 SSE 帧结构 → 先冻 SSE 契约再动 React chat.ts；TB1 推荐响应 schema（带 source 字段）冻结后 TB3 才能展示；TB3 infra API schema 先冻再接页
- 选型依据：dev 态演示（页面永远最新，见启停脚本教训）；Jaeger all-in-one（单容器 OTLP 原生支持）；window.name 门控身份机制复用（T13b 定稿）；三核闸复用（数据清理）；C-01 验收+盲测纪律全程

## 五、派单纪律

- 串行改并行按域：每任务开工令自包含（GWT+铁律+报告路径 AUTO20/reports/ 沿用）；C-01 逐断言验收；盲测队列滚动；每完成 5 单向 owner 汇报一次（比 20 密，本批是体验修复）
