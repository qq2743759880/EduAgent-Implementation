# task34 完工报告：Milvus/Neo4j 清除 + 课程/题目知识切片生成与批量入库

> 执行人：后端+数据库开发者 ｜ 完成日期：2026-08-30 ｜ 分支：feature/task44-courses
> 前置产物：`test-reports/task34-pre-rebuild-snapshot.md`（清除前快照，回滚依据）

## 0. 摘要

edu_knowledge 集合 drop+重建（schema 与 loader.py 一致），Neo4j 全清；从 seeds 权威源生成
**2628 个知识切片**（219 系列 + 657 模块 + 1752 题），dense+sparse 双向量分批入库 `_default`
分区；pf_bagu_kb（5724）与 user_memory（9）原样保留。verify 全 9 项 PASS，断点续跑实证通过。

## 1. GWT 完成情况

| GWT | 内容 | 结果 | 证据 |
|-----|------|------|------|
| ① | drop+rebuild edu_knowledge + Neo4j 全清 | ✅ | collection 重建（created=True），Neo4j 1330 节点/6194 关系 → 0/0 |
| ② | courses.json + questions.json 切片 | ✅ | 219 系列 + 657 模块 = 876（courses.json）；1752 题（questions.json） |
| ③ | 200/批双向量入库（EMBED_BATCH 32）+ 断点续跑 | ✅ | 2628 条全入 `_default`；重跑全跳过、行数不变 |
| ④ | 公共知识进 `_default`；pf_bagu_kb 原样保留 | ✅ | `_default`=2628、无 user_* 分区；pf_bagu_kb=5724 不变 |
| ⑤ | 清除前快照先落盘 | ✅ | schema_fields 9 字段 + 各集合计数 + Neo4j 计数 + raw 双份统计 |

## 2. 入库结果（行数/分区/索引）

```
edu_knowledge: rows=2628  loaded=Loaded
  partition _default: 2628        （course_intro 219 + course_module 657 + question 1752）
  indexes: dense_vec   IVF_FLAT + COSINE（nlist 128）
           sparse_vec  SPARSE_INVERTED_INDEX + IP
pf_bagu_kb:   rows=5724 原样保留（未触碰）
user_memory:  rows=9    原样保留
neo4j:        nodes=0 rels=0（全清）
```

### verify 输出（全 PASS，exit=0）

```
PASS edu_knowledge 行数 == 2628（219 系列 + 657 模块 + 1752 题）
PASS _default 分区 == 2628（公共知识全进 _default）
PASS 无机构 user_* 分区残留
PASS dense 索引 IVF_FLAT+COSINE
PASS sparse 索引 SPARSE_INVERTED_INDEX+IP
PASS collection Loaded
PASS pf_bagu_kb 原样保留（5724 行）
PASS user_memory 原样保留（9 行）
PASS Neo4j 已清空（0 节点 0 关系）
```

### 断点续跑实证（GWT③ 验收标准①）

```
$ python scripts/kb_rebuild_task34.py embed_load
[embed_load] 切片总数=2628（课程 876 + 题目 1752）
[embed_load] 断点续跑：已入库 2628 条，跳过
[embed_load] 全部已入库，无需处理
rows: 2628（不重复、不丢失）
```

## 3. 数据源与切片口径

- 权威源：`E:\stu\project\stu\edu-data\seeds\`（与 `.schema-acceptance.yaml` seeds_dir 一致）
  - `2_course/series.csv`（**utf-8-sig**，219 系列：product_name/series_code/series_name/category_level*/target_*_codes/sale_price）
  - `2_course/series_course.csv`（**utf-8-sig**，657 模块：module_code/module_name/stage_no/lesson_count/total_hours/module_keywords）
  - `3_question/question.csv`（**UTF-8 无 BOM**，1752 题：stem/options_json/answer_text/analysis_text，question_code 唯一 1752、73 bank、analysis_text 全非空）
  - `3_question/question_bank.csv` + `1_foundation/dim_*.csv`（type/identity/goal/grade/category 中文映射）
- 编码差异（发现）：系列 CSV 为 utf-8-sig、题目 CSV 为纯 UTF-8，脚本分别指定，避免 gb18030 误判乱码。
- 系列描述：`product_name / category_level3_name / series_name` 拼接，与 `课程介绍.md` 素材逐条一致（抽样验证）；
  模块描述 = `module_keywords` 拼接；题目含题型中文名 + 选项多行 + 答案 + 解析。
- chunk_id 命名：`course_intro_{series_code}` / `course_module_{module_code}` / `question_{question_code}`（与存量 parser 的 question_ 前缀一致）
- tenant_id=`_default`、visibility=`public`（公共知识，GWT④）

## 4. 向量化通道（披露）

- 配置：`.env` `EMBED_BACKEND=cloud`（火山 ark / DashScope 云端优先，2026-08-22 用户裁定）。
- **实测**：云端 Embedding API 单次 input 上限 10 条，EMBED_BATCH=32 超限报 400
  （`Embeddings API input limit exceeded: max 10, got 32`）→ **embedder 降级链自动回退本地 BGE-M3 CUDA**，
  全量 2628 条由 BGE-M3（C:/ai-models/bge-m3，1024 维精确匹配 schema）完成，吞吐 ~17-18 it/s。
- 结论：批量重建实际走本地 BGE-M3 CUDA（免费、1024 精确），云端通道在重建场景不可用（批限制）；
  在线链路（EMBED_BACKEND=cloud）未改动。如需云端重建，需将批大小降到 ≤10 并接受维度裁剪风险。

## 5. 批判承接

- **task30 批判①（raw 双份存储）**：快照实证 edu_knowledge 旧库 4983 行中 **4982 行存了
  `raw_content` 原文双份**（content 前缀版 + 原文），存储膨胀近 2 倍；重建后的 2628 行
  全部为单份 content（无 contextualize 前缀），**双份存储已消除**。
- **task32 批判（云端 rerank 重跑）**：本次 task34 范围不含 reranker（task31 的 bge-reranker
  为在线链路组件，模型文件未动、无集合数据）；云端 rerank 重跑仍待 task32 批判后续处理。

## 6. 交付物

| 文件 | 说明 |
|------|------|
| `edu-agent/scripts/kb_rebuild_task34.py` | 重建脚本（snapshot/rebuild/slices/embed_load/verify 五子命令，复用 loader.ensure_collection_exists + embedder.encode_dense_batch/build_sparse_vector） |
| `edu-agent/data/kb_slices/courses.json` | 876 条（219 系列 + 657 模块）切片 |
| `edu-agent/data/kb_slices/questions.json` | 1752 条题目切片 |
| `test-reports/task34-pre-rebuild-snapshot.{md,json}` | 清除前快照（回滚依据） |
| `test-reports/task34-completion-report.md` | 本报告 |

## 7. Git 提交链（feature/task44-courses，基于 06b2caf）

```
1232de1  task34(GWT③④): 双向量分批入库 + verify 全 PASS + 断点续跑实证
11c09aa  task34(GWT②): 切片生成 courses.json + questions.json
2b1b282  task34(GWT⑤): 清除前快照落盘 + 重建脚本
```

## 8. 披露与风险

1. **git ref 并行进程干扰**（第 15 次）：执行期间 `.git/refs/heads/feature/` 目录被并行任务进程
   反复删除，commit 对象在 reflog 正常但分支 ref 停旧值；已按 task98 预案从 reflog 重建 loose ref，
   提交链线性无损（1232de1 → 11c09aa → 2b1b282 → 06b2caf）。
2. **Neo4j 图谱重建（FR-KB-03）不在 task34 精简 GWT 内**：仅执行全清，Series/Module/Question/
   KnowledgePoint 节点重建待后续任务（如需）。
3. **回滚**：如需还原旧库，依据 `task34-pre-rebuild-snapshot.json`（schema/分区/计数）重建；
   raw 双份旧数据已随 drop 不可恢复（快照仅保留统计）。

## 9. 验收留白（等验收）

- 已完成并停下等验收。后续任务衔接：task35（RAG 评估/联调）可基于本重建后的 2628 条公共知识库进行。
