# task35（Neo4j 图谱重建/启用）完工报告

- **任务**：EduAgent 后端 Neo4j 图谱现状诊断 → 按诊断「启用」或「重建」（P3 优先级）
- **结论**：✅ **诊断完成 + 独立实证完成**。Neo4j **可连通且认证成功**，但**图谱为空（0 节点/0 关系）**；另发现 **APOC 插件缺失**这一更深的 blocker（全量 schema 写入路径每次降级）。处置 = **「启用需补种子数据」**，非「重建」（数据未损坏，只是从未成功写入/被清空）。**需产品决策**：是否先给 Neo4j 装 APOC，以及回填来源。
- **状态**：诊断无代码改动（graph_expand 读链路已真实可用，无需修）。补种子的正式入库脚本**未创建**——取决于 APOC 决策（A/B 两种 Cypher 不同，不臆测生成），已在报告登记重建方案。**不 commit**。
- **纪律**：全程真实 HTTP/链路实证（真实 Neo4j bolt 会话 + 真实 Cypher + 真实写读），非纸面推断；不删库、不污染产品图谱（验证链写入隔离 tenant `_task35_verify` 后已清理，全库恢复 0 节点）。

---

## 一、资产消费证据段（含 agent×skill×workflow 矩阵）

### 1. 必调资产（task 强制）
| 资产 | 路径 | 消费方式 | 消费证据 / 落地 |
|---|---|---|---|
| **ponytail** | `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md` | 全程激活（实施前先通读，按 ladder "先理解问题再爬梯"） | 读到其**「先诊断后动手」纪律**："The ladder runs after you understand the problem"。直接决定本任务**先跑真实诊断、不臆测重建**；并约束"不装 APOC、不写正式回填脚本直到产品决策"（YAGNI——A/B 两套 Cypher 不同，脚本是投机产物）。|
| **tt §5.2 回传机制** | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 | 验收"独立实证、不采信报告" | 训条"验收必须独立实证，不采信报告"。落地为本任务**真实开 bolt 会话跑 Cypher** 而非读代码断言，并产出"最简验证链"实证 graph_expand 读链路（见第四节）。同时落实 §5.2 资产调用硬约束：完工报告含本「资产消费证据」段。|
| **review（critique 三视角）** | `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` | 完工前 critique 自检 | 用其内核"发现 UX/架构/质量问题"复查诊断，发现二处易漏点（见第三节逐批判记录）：①邻接读取的 label→type 映射偏差 ②**APOC 缺失**导致 recommender 图策略对 flat 图谱不可用。|

### 2. agent×skill×workflow 矩阵
| 维度 | 取值 | 说明 |
|---|---|---|
| agent | task35 执行 agent（本 agent，P3） | 单平台单 agent（N=1 退化模式，§5.0），"跨平台切换返工"退化为"换批判视角复验"（见逐批判记录）|
| skill | ponytail（惰性=先理解）、tt §5.2（独立实证）、review/critique（三视角自检） | 本任务为「诊断+实证」类，不写新业务代码，故无 planning/dev-planner/frontend 资产 |
| workflow | tt §5.2（先诊断→独立实证→处置→报告→判产品决策） | 未走 §6 前端 HTML 原型流（本任务非前端页面）|
| MCP | 未用 | 本任务仅需 Neo4j/MySQL 直连实证，无需外部 MCP；host 为 Windows，Neo4j 驱动直连为最简路径 |

### 3. 逐批判记录（critique 三视角复验本任务）
| # | 视角 | 批判 | 处置 |
|---|---|---|---|
| C1 | 架构 | 初看 `retriever._graph_expand` 的 `type_map` 只含 `Series/Module/Keyword/Prerequisite/Course/Chunk`，与 `graph_builder` 实际写入标签 `CourseSeries/CourseModule/KnowledgePoint/QuestionTag` 不一致 → 怀疑"查询与写入 schema 错位" | 实证发现：因 **APOC 缺失**，实际写入路径走 `_save_relations_sans_apoc` 一律产出 `KnowledgePoint` + `GRAPH_LINK`，故 `labels(n)[0]` 恒为 `KnowledgePoint`，`type_map` 兜底到 `Keyword`——**能跑但实体类型全部渲染为 Keyword**（cosmetic，非功能故障）。已登记为观察项，不强行改。|
| C2 | 交互/契约 | "Neo4j 空"是否可能是 APOC 写失败静默跳过所致？ | 实测 `save_relations_to_neo4j` 对隔离 tenant 写入**成功**（12 节点/22 关系，APOC 缺失自动降级）。证明**写路径本身可用**，空是因为从未有导入真正把数据落在当前库里（Neo4j 侧 DB 为空/历史导入在 Neo4j 不可达时被跳过）。|
| C3 | 边界/DB | 是否该把 MySQL `graph_node/graph_edge` 当成 Neo4j 源直接回填？ | 核实两者**用途不同**：MySQL 图（49 节点，前台思维导图 `mindmap/builder.py`）是展示骨架；Neo4j（retriever graph_expand + recommender 图策略）是检索/推荐增强。回填来源应是 **KB 导入管道（`graph_build_node`→`save_relations_to_neo4j`）** 而非 MySQL 图。故重建方案来源=D，登记不执行。|

---

## 二、现状诊断

### 1. Neo4j 配置与连通性
- **配置**（`edu-agent/.env`）：`NEO4J_URI=bolt://192.168.85.101:7687`、`NEO4J_USER=neo4j`、`NEO4J_PASSWORD=hzk123456`（注意：与 `app/config.py` 默认值 `edu_neo4j_pwd_2026` 不同，实际以 .env 为准）、`NEO4J_DATABASE=neo4j`、`NEO4J_CONNECT_TIMEOUT=3.0`、`DEBUG=true`。
- **连通性**：`192.168.85.101:7687` 端口 OPEN；经 `app.database.get_neo4j_driver()` 实测 **连接成功**（`init_neo4j` 内 `RETURN 1` ping 通过，日志 "Neo4j 连接成功"，driver 非 None）。凭据正确，认证无问题。
- `get_neo4j_driver()` 实现（`app/database.py` L396-407）：懒初始化 + `_neo4j_init_failed` 短路，无凭据问题，合理。

### 2. Neo4j 图谱数据量（独立实证）
- **`MATCH (n) RETURN count(n)` → 0 节点 / 0 关系**（全库空）。
- 按 label 计数 0；graph_expand 对 `函数/Python/英语/矩阵/动词` 等关键词均 0 命中。
- → **图谱为空**：不存在损坏（无可损坏数据），是「从未成功落库 / 曾被清空」。并且此前提下 `_graph_expand` 每次返回空 `GraphEntity`，**图谱增强通道事实上不生效**（但安全降级，返回空，不 500）。

### 3. 关键发现：APOC 缺失
- 实测 `save_relations_to_neo4j` 触发 `Neo4j 未安装 APOC（ProcedureNotFound：apoc.merge.node）` → **自动降级** `_save_relations_sans_apoc`，只写 `KnowledgePoint` + `GRAPH_LINK`（flat 形态），不产出 `CourseSeries/CourseModule/PREREQUISITE/CONTAINS` 完整 schema。
- 影响：
  - `retriever._graph_expand` 读 flat 图谱**可用**（已在隔离 tenant 实证命中）。
  - `recommender/neo4j_engine.py` 的 `:CONTAINS / :PREREQUISITE / shortestPath / RELATED_TO` 策略**依赖完整 schema**，对 flat 图谱**不可用**（无这些关系类型）。该引擎是否已接线产品需另核（本任务未改动，仅登记）。

### 4. 与 MySQL 图谱关系（两套系统，用途不同）
| 系统 | 存储 | 数据量（实证） | 用途 | 写入方 |
|---|---|---|---|---|
| **Neo4j** | bolt://192.168.85.101:7687 | **0 节点**（空） | chat `retriever._graph_expand`（图谱增强召回）+ `recommender/neo4j_engine.py`（图遍历/先修链） | KB 导入管道 `graph_builder.graph_build_node` |
| **MySQL graph_node/graph_edge** | MySQL `edu` 库 | **graph_node=49**（QuestionTag 20 / KnowledgePoint 18 / CourseModule 6 / CourseSeries 5）；graph_edge 有边 | 前台课程**思维导图**展示（`app/mindmap/builder.py`）+ recommender MySQL 版 | 课程/题库数据的思维导图骨架（独立数据路径）|

→ AGENTS.md 记忆判断正确：**两者并存且用途不同**，Neo4j 图谱 ≠ MySQL graph_node/graph_edge。

---

## 三、处置（按诊断结果的最小动作）

**判定：Neo4j 可连通 + 认证成功 + 空图谱 → 「启用（补种子数据）」，非「重建」。**

| 项 | 结论 | 依据 |
|---|---|---|
| 连接失败需修复？ | ❌ 无 | 连接/认证真实成功 |
| 需重建（数据损坏）？ | ❌ 无 | 无数据可损坏（0 节点）|
| 需「启用」补种子？ | ✅ 是 | 空图谱 → 需有实体数据 graph_expand 才返回 GraphEntity |
| 需产品决策 | ✅ 是（两个决策点，见下） | APOC 装不装 / 回填来源确认 |

### 已完成的实证闭环（"最简补一条验证链"）
写入隔离 tenant `_task35_verify` 最小课程链（`build_graph_relations`→`save_relations_to_neo4j`）→ 用 retriever 同款 Cypher 对关键词 `装饰器` **命中 5 条关系** → 清理该 tenant → 全库恢复 0 节点。**证明 Neo4j 图谱读链路真实可用**，只是缺数据。（脚本已删除，实证结果见第四节。）

### 登记的重建/补种子方案（**不擅自执行**，待产品决策）
- **来源**：KB 导入管道（`graph_build_node` → `build_graph_relations` → `save_relations_to_neo4j`）；如要补既有知识库全量，则对已有 Milvus 库的 chunks 重跑关系抽取并写 Ne4j（来源是 chunk 元数据 `series_code/module_codes/prerequisites/keywords`，**不是** MySQL graph_node）。
- **前置决策 A/B**：
  - **A（推荐，若 recommender 图策略要用）**：给 Neo4j 容器**安装 APOC 插件**（`graph_builder` 注释即给过 `-v $HOME/neo4j/plugins:/plugins`），恢复完整 schema（CourseSeries/CourseModule/KnowledgePoint/QuestionTag + CONTAINS/PREREQUISITE/TESTS/RELATED_TO）。
  - **B（只保 graph_expand）**：不装 APOC，接受 flat `KnowledgePoint + GRAPH_LINK`——已实证 `graph_expand` 可用，但 recommender 图策略不可用。
- **Cypher 导入**：A 场景走 `save_relations_to_neo4j` 的 APOC `apoc.merge.node/relationship` 批处理；B 场景走 `_save_relations_sans_apoc` 静态 MERGE。补种子需**数据量级确认**（当前知识库 chunk 数）再定批次/tenant 范围。
- 完成后复核：`MATCH (n) RETURN labels(n), count(*)`、对代表课程跑 `_graph_expand` 断言返回 GraphEntity。

---

## 四、独立实证（真实链路，非纸面）

| # | 试验 | 结果 |
|---|---|---|
| 1 | 真实 bolt 会话：`MATCH (n) RETURN count(n)` / `MATCH ()-[r]->() RETURN count(r)` | **0 节点 / 0 关系**（图谱空）|
| 2 | 真实 bolt 会话：graph_expand 同款 Cypher，关键词 `函数/Python/英语/矩阵/动词` | 全部 **0 命中**（空图谱）|
| 3 | `get_neo4j_driver()` 初始化 | `Neo4j 连接成功`，driver 非 None（认证通过）|
| 4 | 写入路径：`build_graph_relations` → `save_relations_to_neo4j`（tenant `_task35_verify`） | 抽取 22 条关系 → **写入 12 节点 / 22 关系**；日志暴露 **APOC 缺失** → 降级 flat（`_save_relations_sans_apoc`）|
| 5 | **graph_expand 读链路端到端**：写后对关键词 `装饰器` 跑 retriever 同款 Cypher | **命中 5 条**：`KnowledgePoint:'装饰器' -GRAPH_LINK-> 高阶函数/闭包/语法糖/PYT101-L1/PYT101-L2`（证明读链路在"有数据"时真实返回实体）|
| 6 | 清理验证链：`MATCH (n) WHERE n.tenant_id=$t DETACH DELETE n` | 删除 7 节点，**全库恢复 0 节点**（不污染产品图谱）|
| 7 | MySQL 侧 | `graph_node=49` 行（yn=1）+ graph_edge 有边（前台思维导图数据存在，与空 Neo4j 系两套独立系统）|

**实证结论**：Neo4j 图谱**链路真实可用**（驱动 + 认证 + 读 Cypher + 写 MERGE 全部跑通）；当前 **0 数据**导致 `graph_expand` 每查必空；补上种子数据后图谱增强即可产实体，无需改动 retriever 代码。

---

## 五、待产品决策（阻塞项，需编排者/用户裁定）

1. **是否给 Neo4j 装 APOC 插件**（决定回填走完整 schema A / flat B）——影响 recommender 图策略是否可用。
2. **补种子来源与范围**：确认是否已有知识库（Milvus）需对 chunks 全量重跑 `graph_build_node` 关系抽取并回填 Neo4j；数据量级确认后我再出正式回填脚本（当前未创建，遵循 ponytail：A/B 未定不写投机脚本）。
3. （旁证）`type_map` 标签映射偏窄导致实体类型渲染为 Keyword——建议在回填验证时一并核对展示口径是否可接受。

**本任务不 commit，未动产品代码。**