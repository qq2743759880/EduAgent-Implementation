# R03-b 完成报告：迁移/评估只读核验（4417 迁移 + 指标零偏差可重放独立实证，解锁 T10）

> 执行者：R03-b RAG/数据工程师（独立执行，单写者锁 `scripts/eval/r03b.lock` 完工即删）。
> 工作区 `E:\stu\project\stu\EduAgent实施手册`；执行时分支 `feature/opt-waves`，HEAD `a70563e8`。
> 契约：`contracts/reshape-r-chunk.json`；任务书 `.ai-hub/plans/artifacts/kickoff-R03b-readonly-verify.md`。
> 完工时间：2026-09-16（本地）。Milvus server v2.5.5 @ `http://192.168.85.101:19530`（`edu_knowledge`），pymilvus 3.0.1。

---

## 1. 交付摘要

本任务产出 **纯只读核验脚本 `edu-agent/scripts/eval/r03b_verify.py`**，让 R03 的核心结论（4417 迁移唯一化 / hit_rate@5·mrr@5 0.9688 零偏差 / 32 golden 排名一致）可被编排者**一键复跑独立实证**，不再依赖 agent 自产 JSON 作为唯一载体。全程 **零写库**（Milvus 只用参数绑定 SELECT / count；MySQL 零访问），G3 实时评估沿用 R03 §8 GPU 绕行（精确文本查表 + GPU sidecar），**未碰任何正产代码**。

| 项 | 结果 |
|---|---|
| 交付脚本 | `edu-agent/scripts/eval/r03b_verify.py`（唯一新代码文件） |
| 报告 | `edu-agent/test-reports/R03b-completion-report.md` |
| 复跑命令 | `.venv\Scripts\python.exe scripts/eval/r03b_verify.py --result r03b_verify_result.json`（cwd=edu-agent） |
| 四步 GWT | **G1 PASS / G2 PASS / G3 PASS（0.9688 独立复现）/ G4 PASS** |
| 只读实证 | 全量 4417 行 join 核验；唯一 miss=idx22 与基线完全一致 |
| ALL_PASS | True（wall ~33s，含 32 query 实时评估） |

---

## 2. 四步 GWT 数字（独立实证，与 R03 报告对账）

### G1：id_map 翻译命中率 / new id 在库率 / 旧 id 已替换

- id_map 行数 **4417**，old→new 唯一映射 **4417/4417**（无一对多/多对一）。
- **new id 在库率 = 4417/4417 = 1.0**（逐条 join 当前库 chunk_id 全命中）。
- **旧 id 库内残留 = 0**（旧 pk 全删实证，双键兼容仅经 id_map 翻译读侧，无物理残留）。
- 新 id 契约格式 `{tenant}:{sha256[:16]}:{seq}` 违例 = 0。
- **32/32 golden 旧 id 全部在 id_map 中（覆盖 1.0）**——对齐 R03 §7.3「32/32 golden 在映射」。
- **对账 R03 §7.3**：R03 声称「31 次真实评估命中全部经 id_map 翻译达成」→ 本脚本独立复跑 G3 证实 31 hit 中 30 条 `gt_resolve_via="chunk_id+id_map"`、1 条为基线同款 miss(idx22)，直配路径 0 条（迁移后文档全为新 id，golden 旧 id 只能经 map 翻译）——**口径一致**。

### G2：canonical id 重算（hash/seq 组件）+ doc_sha256 一致率

- 抽样（实际全量 join）**4417 条**，每行从库中读 `raw_content/content` 按契约重算 canonical：
  - **canonical hash 组件一致率 = 4417/4417 = 1.0**（重算 `sha256((raw_content or content).strip())[:16]` == 库中 chunk_id 内 h16）。
  - **canonical_id 全串重算一致 = 4417/4417**（含 seq：`canonical_id(tenant, canonical, seq)` == 库中 chunk_id）。
  - **doc_sha256 一致率 = 4417/4417 = 1.0**（`sha256(content 原样 utf-8)` == id_map `doc_sha256`，golden 双键第二键）。
- **seq 一致性 = 3344 组全部 OK，0 组 gap/dup**（每 (tenant,h16) 组 seq 恰为连续 1..k）。
- **对账 R03 §1/7**：R03「逐分量失配=0 / content 失配=0」→ 本脚本独立从库重算 hash+sha 全对齐，补强「content 未变、向量原地」的可重放证据。

### G3：指标零偏差可重放（实时只读评估）

- **独立实时复跑**（retriever.retrieve_three_channel 全链：召回150→rerank20→断崖→top5，Milvus 只读 + GPU sidecar + R03 精确查表 dense）：
  - **hit_rate@5 = 0.9688，mrr@5 = 0.9688**（31/32，仅 idx22 miss）。
  - **与冻结基线 base_run1（0.9688/0.9688）偏差 = 0.00%**（阈值 ≤2% / 0.9488）；与 R03 `r03_post_migration` 逐位一致。
  - **32/32 golden 排名与基线逐一相同（rank_of_gt diff = 0 / 32）**；与 R03 迁移后 run 亦 diff=0。
  - 唯一 miss idx22「简述该场景下的处理顺序。」与基线**完全相同**（基线即 31/32 命中，非迁移引入）。
- **对账 R03 §7.2**：R03 声称 idx25 gold 两版均 #1、#2/#3 为强负例 fp16 换序 → 本脚本独立复跑 idx25 golden `_default:3be16756c6ad8ad5:1` 保持 rank1，top5 序列与 R03 迁移后 run 完全一致（差异仅在强负例内部，不影响 golden/指标）。**rank diff 0** 即证实 G3 口径。
- **关键管线修正**：VEC-LOCK 后 retriever 走 `encode_dense_batch_detailed`（返回 DenseResult），R03 旧 shim 只换 `encode_dense_batch` 已失效——本脚本同时替换 detailed 与包装入口，避免冷加载 BGE 触发 Milvus 8s 超时（期间 idx0 曾因此误报 miss，修正后 0.9688 复现；属核验装置修正，非数据问题）。

### G4：唯一性 + 跨租户隔离

- **chunk_id 唯一性违例 = 0**（行数 4417 / 唯一 chunk_id 4417）。
- **PK 唯一性违例 = 0**（crc32(new_chunk_id) 零重复，与 loader.load_chunks 同算法）。
- **跨租户隔离实证**：抽样 200 条，同内容在不同 tenant 前缀下 canonical_id 不同、同租户不同 seq 不同（抽样全通过，且 G2 已证 3344 组同内容由 seq>1 区分）。
- **对账 R03 §1/§3**：R03「新 chunk_id 4417 唯一 / PK 零碰撞 / 双租户 42 唯一」→ 本脚本在**当前库**独立重测唯一性违例=0，隔离实证通过。

---

## 3. 与 R03 报告差异（如实记录）

| 维度 | R03 报告 | R03-b 独立实证 | 差异说明 |
|---|---|---|---|
| id_map 覆盖 | 4417 / 32 golden 在 map | 4417 唯一、32/32 golden 在 map、1.0 | 一致 |
| new id 在库率 | （隐含 4417 在库） | **显式 1.0**（本脚本首报） | 补强 |
| canonical 重算一致率 | content 失配=0 | **4417/4417 hash+seq+全串一致（1.0）** | 补强, 从库重算 |
| doc_sha256 一致率 | golden 32/32 逐字相等 | **4417/4417（1.0）** | 全量补强 |
| hit_rate@5 / mrr@5 | 0.9688 / 0.9688 | **0.9688 / 0.9688（独立复现, diff=0.00%）** | 一致 |
| golden 排名一致 | 32/32 | **32/32（rank diff 0）** | 一致 |
| 唯一性 / 跨租户 | 4417 唯一 / 42 双租户 | **唯一违例=0 / 隔离抽样全过** | 一致 |
| GPU 绕行 shim | 换 `encode_dense_batch` | 须换 **`encode_dense_batch_detailed`**（VEC-LOCK 演进） | **本脚本修正点** |

无任何数字对账冲突；本脚本为 R03 全部核心验收数字提供**可重放的一手只读实证**。

---

## 4. 红线自检

- ✅ **纯只读**：Milvus 仅 `query`（参数绑定 filter `id >= 0`）/ `count(*)`，零 upsert/delete/rollback；MySQL 零访问。
- ✅ 未重启 8000（PID 19120 常驻未动）；未用 Playwright；未改 `loader.py`/`parser.py`/迁移脚本/`app/**`/contracts。
- ✅ G3 只读编码+只读检索（R03 精确查表）零写库；GPU sidecar 为独立进程辅助评估，非正产。
- ✅ 仅交付 `scripts/eval/r03b_verify.py` + 本报告；docker/git 纪律遵守。
- ✅ 单写者锁：开工建 `scripts/eval/r03b.lock`，期间所有 R03-b 写入仅本任务；完工删除。

## 5. 复跑命令（编排者一键）

```bash
cd edu-agent
.venv\Scripts\python.exe scripts/eval/r03b_verify.py --result r03b_verify_result.json
# 退出码 0 = ALL_PASS（G1~G4），非 0 = 存在 FAIL
# 可选:
#   --no-eval  跳过实时评估（G3 退回读持久化 R03 run JSON, 标记 tradeoff）
#   --result SECTION 自定义结果 JSON 输出路径
```

> 前置：Milvus `edu_knowledge` 可达 + GPU sidecar `http://127.0.0.1:8601` READY + `scripts/eval/data/_r03_query_dense.json` 存在（R03 已留本机）。若无 sidecar/dense，脚本自动回退持久化 tradeoff 并对账，标注取舍，不伪造实时结果。