# R-N1 完成报告（KG-1 图谱同步 + KG-2 学习路径端点）

- 任务：C-01 派单 R-N1（`feature/opt-waves`，planId=reshape-r-kg）
- 接手背景：前任两次中断（API 断裂 + 宿主机崩溃），半成品以 4 个 wip commit 留痕；本报告为接手执行 agent 的独立实证收口
- 完成日期：2026-09-18 晚
- 最终 commit：（见下方「提交」节，commit 后由编排者回填 hash）

## 1. 前任半成品逐文件处置（4 commit 审查结论）

| commit | 文件 | 处置 | 说明 |
|---|---|---|---|
| `337197f` | app/domains/kg/\_\_init\_\_.py | **复用** | 域声明 5 行，无逻辑，原样保留 |
| `337197f` | app/domains/kg/graph.py | **修复** | `find_cycle` 回溯 parent 链构造环路径时**未闭合**（二环返回 `[a,b]` 而非 `[a,b,a]`，违反 GWT `cyc[0]==cyc[-1]`）；修复为补链尾→reverse→追加环入口闭合。离线三用例（two/three/larger-dag）由 fail 转 pass |
| `337197f` | app/domains/kg/router.py | **复用** | 3 端点定义、Query 校验（min/max_length）、同步 def 范式均正确 |
| `337197f` | app/domains/kg/schemas.py | **复用** | DTO 与契约草案字段一一对应 |
| `337197f` | app/domains/kg/service.py | **修复** | ①前任已在 ec7adc1 自补 `KG_SOURCE` 导入（否则 NameError→50000）；②接手后补 `_session_block`：`driver.session()` 创建/关闭期异常原先裸抛（实测 `_BoomDriver` 用例 50000），统一包 50301 脱敏降级；AppException（40460 等业务码）透传不吞；body 异常在途时 close 期故障只记日志不遮蔽原异常 |
| `337197f` | app/domains/kg/sync_core.py | **复用** | 抽取/幂等 MERGE/备份/计数自证四段完整可用；实测与其 docstring 数字一致 |
| `ec7adc1` | service.py +1 行 | **复用** | 前任自补的导入修复，保留 |
| `27421f4` | scripts/eval/febe_contract_check.py +6 行 | **复用** | KG 3 端点入 NEXTJS_UNASSIGNED 桶；复跑 `breakpoints=0, plan_broken=0, malformed=0` 通过 |
| `43e0480` | tests/test_kg_rn1.py（426 行） | **修复** | ①`test_build_chunk_graph_keyword_scoring_and_cap` 断言写 `keyword_match:2`，实现为关键词(score 2)+正文(score 1)加法打分=3，实现正确、断言错，修断言；②其余 32 离线用例 + 2 live 用例复用 |
| 工作树遗留（未 commit） | scripts/kg_sync.py（146 行） | **复用** | 前任已写好未入库：备份→(full 清子图)→幂等 MERGE→计数对比，含 `--verify-idempotent`/`--dry-run`/`--skip-milvus`；实测可用 |
| 工作树遗留（未 commit） | contracts/reshape-r-kg.json（129 行） | **复用** | draft:true 契约草案完整（3 端点 + GWT + known_data_limits 诚实登记 mentions=0/related=0） |
| 前任连带（经 e6fac1d 入库） | app/main.py kg_router 注册 2 行、app/common/error_codes.py KG 段 4 行 | **复用** | 审查无问题：40460/40461/40462/40910 语义正确；注册行仅 2 行无夹带 |

**结论：11 个文件 = 8 复用 + 3 修复 + 0 重写。** 前任代码架构质量高，缺陷集中在：环路径未闭合、异常包装缺口、1 处测试断言——均为实测暴露型缺陷（前任未跑通测试即中断）。

## 2. 连通性（实测）

- Neo4j `bolt://192.168.85.101:7687`（.env NEO4J_DATABASE=neo4j）：**连接成功**（uvicorn lifespan + 独立 driver 双验证）
- MySQL localhost:3306（edu 库）：只读抽取成功（series 2854 行）
- Milvus `192.168.85.101:19530`（edu_knowledge 3399 行）：只读抽取 doc_chunk 761 行成功
- **重要环境事实**：前任 2026-09-18 22:29 (+0800) 曾同步成功（data/kg_backup/ 留有 8 份备份，kg 子图 4292 节点/7900 关系），但接手时 Neo4j 中 kg 标签/`source` 属性**全部不存在**（图被清空/重置，仅剩 P1 遗留标签）——即接手时库为空，正好由本任务从零重建并全程实测

## 3. 同步前备份 + 计数快照（红线：备份先行）

同步前状态（PASS1 before，同时落盘为备份文件）：

- **kg_sync 子图：全 0**（node:Course/Chapter/KnowledgePoint/DocChunk = 0；rel:PREREQUISITE/BELONGS_TO/MENTIONS/RELATED = 0）
- **P1 遗留数据（不动红线对象）**：CourseModule 658、CourseSeries 219、KnowledgePoint 1149、QuestionTag 88；CONTAINS 4687、GRAPH_LINK 91、RELATED_TO 8357、TESTS 88
- 备份文件：`edu-agent/data/kg_backup/kg_backup_20260918_150320.json`（PASS1 前）、`..._150544.json`（PASS2 前）、`..._150835.json`（PASS3 前），每份含 kg 子图全属性导出 + 全图标签/关系类型计数快照（遗留数据可审计可回放）

## 4. 幂等同步实测（三轮，计数逐项对比）

执行：`scripts/kg_sync.py --mode full --verify-idempotent`（两轮）+ `--mode inc --verify-idempotent`（第三轮）

| 指标 | PASS1 (full, 空库首建) | PASS2 (full, 重建) | PASS3 (inc, 纯 MERGE) |
|---|---|---|---|
| deleted_nodes | 0 | 4292（仅 kg_sync 子图） | 0 |
| 写入行数 | 4292 节点 / 7900 关系 | 4292 / 7900 | 4292 / 7900 |
| node:Course | 0→2854 | 2854→2854 | 2854→2854 |
| node:Chapter | 0→659 | 659→659 | 659→659 |
| node:KnowledgePoint | 0→18 | 18→18 | 18→18 |
| node:DocChunk | 0→761 | 761→761 | 761→761 |
| rel:PREREQUISITE | 0→14 | 14→14 | 14→14 |
| rel:BELONGS_TO | 0→7886 | 7886→7886 | 7886→7886 |
| rel:MENTIONS / RELATED | 0→0 / 0→0 | 0→0 / 0→0 | 0→0 / 0→0 |
| 遗留数据（CourseModule 658 等 8 项） | **不变** | **不变** | **不变** |

**结论：三轮 after 计数逐项相等，脚本输出 `IDEMPOTENT: YES`**；full 重建精确删除 4292 个 kg_sync 节点后重建计数不变；遗留 P1 子图全程未被触碰（红线达成）。抽取侧基线：MySQL courses=2854/chapters=659/kps=18/prereq=14/belongs=7886；Milvus chunks=761。

## 5. 环检测实测

1. **真实数据无环**：MySQL graph_edge 全部 14 条 KP→KP PREREQUISITE 边（真实 SELECT 抽取）喂给 `kg_graph.find_cycle` → `None`（无环），与拓扑语义一致
2. **真实边最短路（算法实测）**：`shortest_path` 于真实 14 边 → KP-PY-VAR→KP-PY-CTRL→KP-PY-FUNC→KP-PY-OOP→KP-PY-HTTP→KP-PY-SQL（6 节点 5 跳），与 MySQL 基线链人工核对一致，与 live 测试断言一致
3. **注入环检出（纯内存，不碰库）**：真实 14 边 + 注入 `KP-PY-SQL→KP-PY-VAR` → 检出闭合环 `['KP-PY-CTRL','KP-PY-FUNC','KP-PY-OOP','KP-PY-HTTP','KP-PY-SQL','KP-PY-VAR','KP-PY-CTRL']`（首尾相同，符合 GWT）
4. **fail-closed 契约**：离线 stub 注入三环/自环 → `AppException 40910 KG_PREREQUISITE_CYCLE`，message 含环节点 code 序列，不做拓扑近似（test_service_cycle_fail_closed_40910 / test_service_self_loop_40910）

## 6. 真 HTTP 实测（8000 共享后端 + 当前代码一次性实例 8112 双重验证）

| 用例 | 结果 |
|---|---|
| GET /api/kg/course/1/path?from=KP-PY-VAR&to=KP-PY-SQL | 200 `{code:0, found:true, hops:5, path:[6 步含真实 KP 名称], cycle_checked:true}` |
| GET /api/kg/course/999999/path | 404 `{code:"40460", data:null}` |
| GET /api/kg/course/1/path?from=KP-NOPE&to=... | 404 `{code:"40462", data:null}` |
| GET /api/kg/course/1/path?from=KP-MATH-ADD&to=KP-PY-SQL（跨学科断链） | 200 `{code:0, found:false, hops:0, path:[], cycle_checked:true}` |
| GET /api/kg/chapter/general_purpose_programming_foundation_m1/upstream | 200（mentioned/neighbor 空数组——诚实数据态，见 P0-①） |
| GET /api/kg/chapter/.../downstream | 200，结构与 upstream 一致 |
| GET /api/kg/chapter/\_\_nope\_\_/upstream | 404 `{code:"40461", data:null}` |
| **降级**：一次性 8111 实例 `NEO4J_URI=bolt://127.0.0.1:9`（死端口） | KG 端点 **HTTP 503 `{code:"50301", message:"依赖服务暂不可用，请稍后重试", data:null}`**（脱敏：内部异常细节不进响应） |
| **主链无感**：同 8111 死端口实例 GET /api/series | 200 `{code:0, total:2628, items:[...]}` 正常返回 |

8111/8112 一次性实例用后即清（netstat+taskkill 验证无残留），共享 8000 后端全程未重启、收尾复探 KG=200/upstream=200 完好。

## 7. pytest

`tests/test_kg_rn1.py`：**34 passed**（含 Neo4j 真集成 live 2 例：子图计数断言 + MySQL 基线链 5 跳断言；均真实库只读）。修复前 7 failed → 修复后 0 failed。

## 8. febe 契约桶复跑

`scripts/eval/febe_contract_check.py`：`breakpoints=0, in_use_unfrozen=0, unfrozen_only=0, malformed=0, plan_broken=0`；KG 3 端点在 unassigned 桶（前端暂未接入，治理分类合规）。

## 9. 自批判（P0，≥3 条如实登记）

1. **P0｜MENTIONS 全 0 = 章节邻域端点"结构性可用、数据性为空"**：P1 graph_edge CONTAINS 的 module 命名空间（MOD-EN-PHON-VOWEL 等）与线上 series_cohort_course.module_code（general_purpose_programming_foundation_m1 等）**不相交**，module_contains 规则抽取诚实产出 0；Milvus doc_chunk 无 keywords/tags/series_code/module_codes 元数据且内容为内部工程文档，keyword_match 命中 0。upstream/downstream 端点对任意真实章节均返回空邻域。补救路径=plan KG-1 可后置项「LLM 批量抽取」，落地前该两端点无业务价值（契约 known_data_limits 已如实登记，未造假数据）。RELATED 同理=0（8357 条 RELATED_TO 均为遗留图非 KP 对）。
2. **P0｜写入计数口径是"提交行数"非"落库实体数"**：`write_graph` 返回的 nodes/rels 是 UNWIND 批行数（重跑 MERGE 0 新建时仍报 4292/7900），不能当创建量解读；幂等结论依赖的是 before/after 快照对比（本报告第 4 节口径）。后续若做同步监控指标，须改用 `summary.counters.nodes_created` 等真实计数器。
3. **P0｜service 每请求全图拉边，规模上限 ~10^2 KP**：`_PREREQ_CYPHER` 无 course/深度限定，18 KP 当前 P95 无感（HTTP 实测 20~133ms），但 KP 千级时 course_path/chapter_neighbors 均全图载入内存计算。当前规模可接受、有 max_depth/visited 防御兜底，但**扩容前必须**改造为 Neo4j 侧限定查询（变量路径/量化上限 + key 索引）。
4. **P0｜kg_counts 关系计数是"半开作用域"**：`startNode(r).source OR endNode(r).source` 会把"一端 kg_sync 一端遗留"的半接入关系计入子图计数；当前数据无此形态（全部关系两端同由 kg_sync 创建），纯理论口径瑕疵，登记防误读。
5. **P1｜live 测试硬编码基线**：`test_live_path_matches_mysql_baseline` 硬编码 course_id=1 与 KP-PY 链，MySQL 图数据变更即 fail（防漂移是特性也是脆弱性）；规模变大后应改为「从 MySQL 实时抽边断言与 Neo4j 路径一致率」。

## 10. 批判承接核对

- `.ai-hub/plans/tasks/plans/critique-backlog-tracker.md` 全文检索 `R-N1/rn1/KG` **零匹配**；`.ai-hub/plans/artifacts/` 无 R-N1 相关批判留痕；前任 4 个 wip commit message 亦无批判待办——**确认无承接项**，与派单说明一致。
- 本任务新产出的自批判（第 9 节）已全部登记在本报告，未发现需要立即返工的阻断项。

## 11. 资产消费证据

- `.ai-hub/plans/neo4j-mongo-activation-plan.md` §KG-1/KG-2：节点/关系建模、幂等 MERGE+备份先行、环检测 GWT、3 端点清单——逐条落地（第 3/4/5/6 节即为对应实证）
- AGENTS.md 教训：①禁用 Playwright（全部用 curl/pytest/真实 HTTP）；②契约以实测为准（mentions=0 按实测如实登记而非照抄计划乐观口径）；③DEBUG 模式语义（8111 降级实例验证的是 DEBUG skip 路径，与 service 的 50301 降级链闭环）
- 范式对齐：T19-3 reshape-b 降级链（50301 脱敏、detail 恒 None、logger.exception 全量入日志）；数据软删三核闸（备份先行，8+3 份备份落盘）
- 前任资产：4 wip commit + 工作树 2 文件全部消费（8 复用/3 修复/0 重写，第 1 节）
- 契约：`contracts/reshape-r-kg.json` draft:true 与 `app/domains/kg/schemas.py`/`error_codes.py` 权威源一致（test_contract_draft_matches_router 机验）

## 12. 提交

- 分支 feature/opt-waves；commit 前已删锁 `edu-agent/scripts/eval/rn1.lock`
- 提交文件（显式路径 add，不含 data/kg_backup、不含他人工作树遗留）：app/domains/kg/{graph,service}.py、tests/test_kg_rn1.py、scripts/kg_sync.py、contracts/reshape-r-kg.json、test-reports/RN1-completion-report.md
- 最终 commit hash：`<<RN1_COMMIT_HASH>>`（由本 agent 提交后回填）
