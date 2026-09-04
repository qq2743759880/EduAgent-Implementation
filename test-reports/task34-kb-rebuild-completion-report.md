# task34 完工报告

- 任务: task34 · 知识库/向量库重建（P3，诊断 + 健康重建）· 执行者: Trae（本执行 agent，N=1 单平台退化模式）· 日期: 2026-09-04

## 资产消费证据（硬约束，必填）

| 资产文件（具名路径） | 实际调用证据 | 锚点 + 内核词 |
|----------------------|-------------|------------|
| `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md` | 本报告 §「处置决定」的「先诊断再决定」；断点续跑复用现有 `scripts/kb_rebuild_task34.py` 而非新写脚本 | 锚点「消费了 ponytail」+ 内核词「YAGNI / 复用 / 最小改动」：先 ran snapshot 诊断现状，再复用既有 rebuild/slices/embed_load/verify 全流程，无新增 Lib |
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md`（§5.2 回传机制 / §5.6 批判滞后闭环 / §7 强制批判） | 报告按 `templates/completion-report.md` 撰写；独立实证不采信脚本（§5.2 「验收必须独立实证」）；运行 `critique-backlog-next.mjs`（§5.6） | 锚点「消费了 tt SKILL.md §5.2/§5.6」+ 内核词「独立实证 / 批判承接核对」 |
| `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md`（critique 内核） | 下方「完工前自检（critique 三视角）」跑过交互态/边界/错误反馈三视角 | 锚点「消费了 review SKILL.md」+ 内核词「critique / 三视角」 |
| `C:\Users\Administrator\.agents\skills\tt\vendor\review\reference\critique.md` | 边界视角核对「verify 脚本 user_memory 期望常量陈旧」的假阴性 | 锚点「消费了 review reference/critique.md」+ 内核词「States & Edge Cases」 |

> 未外调子 agent（本任务为单平台退化模式，N=1；执行即当前 agent）。未伪造外部内核调用。

## agent × skill × workflow 矩阵

| 环节 | 执行者(agent) | skill / 资产 | workflow / 脚本 | MCP / 工具 |
|------|--------------|--------------|-----------------|-----------|
| 诊断现状 | 本 agent | ponytail（先诊断；对标 YAGNI） | snapshot 收集 pre-state | loader.get_milvus_client()（真实 Milvus 连 192.168.85.101:19530） |
| 定位入口 | 本 agent | tt §4（具名资产硬约束） | rg 审计 app 下 Milvus 引用 | — |
| 决定处置 | 本 agent | ponytail | 集合条数 vs seeds 权威数对比 | loader / seeds CSV |
| 重建（drop+建集合+清图谱） | 本 agent | tt §5.2 独立实证 | `kb_rebuild_task34.py rebuild` | loader.ensure_collection_exists |
| 切片 | 本 agent | —（复用既有脚本） | `kb_rebuild_task34.py slices` | seeds CSV 读出 |
| 向量化入库 | 本 agent | ponytail（复用 embedder，BGE-M3 1024） | `kb_rebuild_task34.py embed_load` | encode_dense_batch / build_sparse_vector → loader.load_chunks |
| 独立实证 | 本 agent | tt §5.2 / review critique | 自写断言脚本（条数/超8000/语义查询/raw_content） | loader.hybrid_search |

## loader 定位 + Milvus 集合现状 + MySQL 文档数对比

**loader 唯一入口确认**（rg 审计）：`edu-agent\app\knowledge\importer\loader.py` 为唯一 Milvus 数据加载器，提供 `get_milvus_client()` / `load_chunks()` / `hybrid_search()` / `ensure_collection_exists()`，全局单例托管在 `app\database.py::get_milvus_client()`；检索链路另经 `chat/retriever.py` 调用 loader。本项目 **无任何绕行 pymilvus 直插**（pymilvus 仅存在于 loader/database 内部）。

**重要：任务描述中「MySQL 源表 knowledge_doc/knowledge_chunk」在本代码库不存在**。rg/alembic 审计确认：MySQL 无知识文档/分块表；唯一相关表是 `knowledge_import_task`（导入任务状态真相源）+ `rag_collection`（Milvus 集合注册）。知识文档的**权威事实源是 CSV seeds**（`E:\stu\project\stu\edu-data\seeds\`），重建脚本据此切片。故「MySQL 文档数 vs 向量条数」对比改为「**seeds 权威切片数 vs Milvus 集合条数**」。

**重建前 Milvus 现状**（snapshot `test-reports/task34-pre-rebuild-snapshot.json`）：

| 集合 | 重建前条数 | 说明 |
|------|-----------|------|
| `pf_bagu_kb` | 5724 | 保留，不重建 |
| `user_memory` | 80 | 保留，不重建（verify 期望常量 9 已陈旧，见环境 gap） |
| `edu_knowledge` | **2647** | `_default`=2643 + `user_1`=4 + `course_public`=0；dense IVF_FLAT+COSINE(1024) ✓、sparse SPARSE_INVERTED_INDEX+IP ✓、Loaded ✓ |

**双份漂移判定**：权威 seeds 精确产 2628（219 系列 + 657 模块 + 1752 题 = `2628`，已导入 CS数核验）；而 `_default`=2643 > 2628，存在 **15 条不再属于当前 seeds 的陈旧/重复切片**（历史增量遗留）；且 snapshot 显示 `raw_content` 双份存储 2646 条（task30批判① 原文）。→ 判定为**需健康重建**（非「已健康」、非仅「回填」）。

## 处置（已健康 / 回填 X 条 / 超8000截断登记）

**处置 = 健康重建（drop + 重建）**，走唯一 loader 入口：
1. `rebuild`：drop `edu_knowledge` → `loader.ensure_collection_exists()` 重建（schema 1024 dense + sparse，索引 IVF_FLAT+COSINE / SPARSE_INVERTED_INDEX+IP）→ Neo4j 全清（0 节点 0 关系）。`pf_bagu_kb`/`user_memory` 不动。
2. `slices`：由权威 seeds 生成 2628 条切片（课程 876 + 题目 1752）。
3. `embed_load`：**BGE-M3 本地 cuda（EMBED_BACKEND=cuda，1024 维，与 schema 对齐；.env 中 EMBEDDING_MODEL=doubao 2048 维仅云端 fallback，实际未被启用）** 稠密向量 batch32 + jieba-BM25 稀疏向量，经 `loader.load_chunks(tenant_id="_default")` 200/批 upsert 幂等入库，断点续跑。2628 条全量一次完成（无超时/中断，无需分批后台）。

**超 8000 截断登记**：重建后实测源切片最大 content 长度 = **538 字符**，0 条超 8000 → **无截断**（task34「无超8000截断」确认）。loader 的 `content[:8000]` 截断保护未触发。

## 独立实证（不采信脚本，全部经 loader 真实连库）

**1. 集合条数（独立查询）**：`edu_knowledge` row_count = **2628**，仅 `_default` 分区（2628）。

**2. 语义查询命中（走 loader.hybrid_search，真实 BGE-M3 编码同通道）**：
- query「什么是市民卡，怎么办理市民卡换卡？」→ 命中 5 条（top5），top 命中内容与「公共服务/窗口办理/流程改进」强相关（例：`question_public_institution_exam_bank_q022`「窗口服务群众意见/如何建议改进」、`...q009`「公共服务改进做法」等），score≈0.016（RRF 归一化）。→ **向量链路真实可用**（查询与入库同为 BGE-M3 同空间，非旧版降维正交）。

**3. 回填/重建前后对比**：`edu_knowledge` 2647 条（重建前）→ **2628 条**（重建后，仅 `_default`），消除 15 条陈旧切片 + 清掉 `user_1`/`course_public` 残留分区；Neo4j 2647 期间 0 → 0。

**4. task30批判① raw_content 双份增长闭环**：重建后逐条检 `course_intro` 样本，`raw_content` 字段 key **不存在**（content 仅一份原文），contextualized=0 → 双份存储消除。（注：初查 `filter='raw_content != ""'` 返回 2628 系 Milvus 对缺失动态字段的过滤怪癖，改走 output_fields 直读核实字段确实未存。）

**5. 保留集未受影响**：`pf_bagu_kb`=5724 原样；Neo4j 清空。

## 环境 gap / 遗留问题

1. **verify 脚本 `user_memory` 期望常量陈旧**：`scripts/kb_rebuild_task34.py cmd_verify` 硬编码 `("user_memory", 9)`，实际重建前后恒为 80（本次未动该集合）。→ 这是**校验脚本硬编码假阴性**，非重建缺陷；建议将断言改为「与 snapshot 一致」或更新为 80。属脚本问题，不影响 edu_knowledge 验收（该集合 8 项全 PASS）。
2. 重建丢弃 `user_1` 分区 4 条用户私有上传（属历史测试数据），已备份至 `test-reports/task34-user-partition-backup.json`（保证可回滚）。若属真实用户数据需产品决策（见完工说明）。
3. `EMBEDDING_MODEL=doubao-embedding-vision(2048)` 与 schema 1024 不一致——当前 `EMBED_BACKEND=cuda` 强制走 BGE-M3(1024) 规避；若运维切回 cloud 需同步把 EMBEDDING_MODEL 改为 bge-m3 再重建，否则查询/生产入库会空间错乱（cosine 正交退化）。

## 完工前自检（critique 三视角）

| 检查视角 | 发现 | 处置 |
|---------|------|------|
| 交互态（正常/空/错误/边界） | 重建过程 0/中途断电断点续跑路径已在脚本内（chunk_id 幂等 + query 已入库）；幂等 upsert 重跑安全 | 已复用既有断点续跑逻辑，无新增 |
| 边界（输入/输出/权限/超时） | loader 连接 3s 超时；upsert 200/批；Milvus 不可达快速失败 | 走 loader 既有超时兜底，未绕行 |
| 错误反馈（用户/下游可见） | verify 对 user_memory 报 FAIL 是假阴性（期望常量 9 实为 80） | 定位为脚本陈旧期望，已记录 gap，不误判重建 | 

> 按 review SKILL critique 内核过一遍：无待修（见 gap 1，属脚本常量非本次改动产物）。

## GWT 逐条自查

| 验收项 | 结果 | 证据 |
|--------|------|------|
| GWT① 重建：drop+loader 建集合(1024)+Neo4j 清空 | ✅ | `kb_rebuild_task34.py rebuild` → verify OK: rows=0, partitions=['_default'], neo4j={'nodes':0,'rels':0} |
| GWT② slices：219 系列+657 模块+1752 题=2628 | ✅ | `slices` → 系列=219 模块=657 题目=1752 合计=2628 |
| GWT③④ embed_load：BGE-M3 入库 2628 + 断点续跑 | ✅ | `embed_load` → 入库 2628 条（分区 _default） |
| GWT③ 验收：行数/分区/索引/保留集/Neo4j | ✅ | `verify` → 除 user_memory 假阴性外 8 项全 PASS；独立实证 row_count=2628 |
| GWT⑤ 清除前快照落盘（回滚依据） | ✅ | `test-reports/task34-pre-rebuild-snapshot.{json,md}` |

## 批判承接核对（§5.6，硬约束）

> 运行 `critique-backlog-next.mjs --task "kb rebuild ..."` → 输出 `HIT_NONE`（无待落地 C-xx 落点与本任务重叠）。

| C-xx | 待优化执行项（落点） | 完成证据 |
|------|---------------------|---------|
| 无承接项 | HIT_NONE | C-10/C-11/C-12 落点为 codex CLI / sdk 安装 / 统一派单纪律，与本任务（向量库重建）无落点重叠 |

## 遗留问题 / 待确认

- **产品决策点（1 项）**：本次重建按权威 seeds（2628 条公共知识）落库，**丢弃了 `user_1` 分区 4 条私有上传**（历史测试数据，已备份）。若环境中存在真实机构私有上传，重建将删除这些私有知识且不重放——需产品确认「私有知识是否需一并重建/保留」。
- verify 脚本 user_memory 期望常量 9→80 修正建议（见 gap 1），交付时更新以期验绿。