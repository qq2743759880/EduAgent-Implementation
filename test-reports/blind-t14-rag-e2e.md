# T14 RAG 端到端验证报告（W-NEXT-RAG-001 修复后端到端 + 治理压力盲测）

> 身份：EduAgent 项目独立验收用户（单写者）。工作区：`E:\stu\project\stu\EduAgent实施手册`。
> 方法：8010 临时实例（工作树代码，含 Scheme A 修复，已关闭）+ adm02test/user000001 双角色真实 HTTP + Milvus/MySQL 只读参数绑定核验。禁 Playwright。测试数据自建自清（已闭环，见 §10）。
> 日期：2026-09-16。锁：`edu-agent/scripts/eval/t14.lock`（开工建、完工删）。

---

## 0. 一句话结论

**修复后学生能检索到自己上传的 doc（修复前 0 命中 → 修复后 marker 精确命中 + 标题关键字命中，8/8 检查全过）；但 732 条真实内部工程文档当前对 student 全可见（S6 回归保护实测 FAIL，All-742 重建的用户选择副作用，classify 门逻辑本身完好）。**

---

## 1. 环境与前态（S7 基线）

- 验证实例：`127.0.0.1:8010`（uvicorn，工作树代码；8000 运行中未动）。用毕已关。
- **前态基线（probe_before.json）**：Milvus `edu_knowledge` 总 3379 行（count 口径）；doc_chunk 742 行（internal=True=0）；租户 `_default`=3359 / `user_1`=10；分区 `_default/course_public/user_1`；MySQL `knowledge_import_task` 124 行；`up_` 前缀行 0。
- ⚠️ count(*)=3379 与 query 实际 3369 存在 **10 行幽灵差**（WNEXTRAG1 重建 upsert 的 user_1 旧版本被 count 路径多计，详见 §6），前态即存在、非本任务引入。

## 2. S5【本批关键】internal 误判修复后端到端 — **8/8 PASS**

真实产品 API 上传（`POST /api/knowledge/upload` / `admin/upload`），上传后立刻检索：

| 检查 | 结果 | 证据 |
|---|---|---|
| S5-a student 检索自己上传 doc（marker `T14STU9K2X7Q` 精确） | **PASS** | top 命中 `user_1:6c9052029dade16e:1`（修复前 0 命中） |
| S5-b student 检索标题关键字（光合作用/卡尔文循环）命中 user_1 行 | **PASS** | top5 含 tenant_id=user_1 doc_chunk |
| S5-c admin 检索公共上传 doc（marker `T14ADM7M3Q2W`） | **PASS** | top 命中 `_default` 行 |
| S5-d student 检索 admin 公共 doc（TCP 三次握手） | **PASS** | 命中 `_default` 行（公共可见性正确） |
| S5-e student doc `source_file` 以 `up_{user_id}_` 开头 | **PASS** | `up_1_8ed26ab3_t14_s5_student.md` |
| S5-f admin doc `source_file` 以 `up_{user_id}_` 开头 | **PASS** | `up_100003_108ec533_t14_s5_admin.md` |
| S5-g 新上传 doc `internal=False`（不再误判） | **PASS** | 8+8 行全 False |
| S5-h 租户归属（student→user_1，admin→_default） | **PASS** | Milvus 实测租户正确 |

证据：`scripts/eval/_t14/s5_result.json`。

## 3. S1 核心检索能力（学生视角 12 条）— 10 PASS / 2 FAIL

判定口径：golden 类=golden chunk_id 在 top5；doc_chunk 类=marker 命中且 content_type=doc_chunk；泛化类=人工复核 top5 相关性。证据：`s1_result.json`。

| # | query | 类别 | 判定 | top1 / 说明 |
|---|---|---|---|---|
| 1 | 化学方程式总是写错时，最该加强的是？ | golden | **PASS** | golden `_default:f3b54bdeeb7573a9:1` 命中 |
| 2 | 缓存数据和数据库不一致的处理思路？ | golden | **PASS** | golden `_default:8627e30844db7514:1` 命中 |
| 3 | 概率独立和条件概率的区别 | golden | **PASS** | golden `_default:0eee6cf7bf220af4:1` 命中（答案正文 top1） |
| 4 | T14STU9K2X7Q 光合作用光反应产物 | doc_chunk | **PASS** | `user_1:6c9052029dade16e:1` doc_chunk top1 |
| 5 | TCP 三次握手为什么不能两次 | doc_chunk | **PASS** | top1 题库简答题 + 命中 `_default` doc_chunk（marker 在 top5） |
| 6 | 牛顿第一定律 惯性 质量量度 | doc_chunk | **PASS** | `_default:5bc4b1b2237d0259:1` doc_chunk top1 |
| 7 | 英语一般现在时用法和时间状语 | doc_chunk | **PASS** | `user_1:4ae68dcdb7aa1876:3` doc_chunk top1（重复段 seq=3） |
| 8 | 雅思听力填空题技巧 | 泛化 | **FAIL** | top1 英语完形填空题，top5 无雅思听力材料（库内无此知识，属"该命中的没命中"） |
| 9 | 前端点击按钮无反应排查 | 泛化 | **PASS** | top1/top2 精确命中（事件绑定/控制台/遮挡） |
| 10 | 数据库索引 B+树原理 | 泛化 | **PASS** | top1/top2 精确命中；**top4/5 出现内部工程 doc_chunk**（见 §8 问题 2） |
| 11 | 导数定义和极限的关系 | 泛化 | **PASS** | rank2 命中"由导数定义 lim 推导"公式题；top1 为相邻主题（导数与单调性） |
| 12 | 定语从句 which 和 that 区别 | 泛化 | **FAIL** | top1 翻译题（不相关）；**top2-5 全是"验收标准 GWT"内部工程 doc_chunk（score 0.85-0.99 压过教学内容）** |

- **doc_chunk 路径覆盖：4 条**（Q4/Q5/Q6/Q7，T10 原 12 条 0 覆盖，本批补齐 ≥3 要求）。
- 黄金集 3/3 命中；12 条真实问题 10 条合理。

## 4. S2 多角色隔离（同内容双租户）— 4/4 PASS

同一文件 `t14_s2_same.md`（marker `T14SAME5R8W3Z`）经 student 与 admin 分别上传：

| 检查 | 结果 | 证据 |
|---|---|---|
| S2-a 同内容双租户各自成行、互不覆盖 | **PASS** | `user_1`=8 行 + `_default`=8 行（含无 marker 块；marker 块 4+4） |
| S2-b 同内容 → 同 h16 跨租户一致 + seq 集一致 | **PASS** | 两租户 h16 集合完全相同（如 `2f5ae5080d09de8b` 等 4 组），seq 均 [1] |
| S2-c 上传者检索到同内容 doc | **PASS** | top1=`_default` 副本、top2=`user_1` 副本（自己私有+公共均可见，合法） |
| S2-d 独立租户学生零 `user_` 泄露 | **PASS** | 数据层模拟他人租户集 `["_default","course_public","user_999"]` 查询 marker → 4 行全 `_default`，user_1 泄露=0；代码路径 `retriever._search_tenant_ids`（学生=`["_default", course_public, user_{self}]`）结构性排除他人分区 |

证据：`s234_result.json`。说明：未注册第二个学生账号（避免 sys_user 写入不可经产品 API 自清），S2-d 用「数据层租户集模拟 + 代码路径」双证据替代，与 T10 口径一致。

## 5. S3 同内容多块 / S4 幂等重导 — 5/5 PASS

| 检查 | 结果 | 证据 |
|---|---|---|
| S3-a 重复段落 → 同 h16 多 seq 区分 | **PASS** | 重复 3 次的段落 → `user_1:4ae68dcdb7aa1876` seq=[1,2,3] |
| S3-b chunk_id 全唯一 | **PASS** | marker 6 行 6 unique（全文件 7 行无冲突） |
| S3-c 重复内容可检索命中 | **PASS** | top1=该文档 doc_chunk（score=1.0） |
| S4-a 同文件重导 2 次 chunk 不翻倍 | **PASS** | 首次 3 行（marker 口径）→ 第二次后仍 3 行；全文件 6 行不变 |
| S4-b 两次上传 chunk_id 集合完全一致 | **PASS** | content 同 → canonical id 同 → upsert 幂等；第二次上传仅把 `source_file` 改写为新 uuid 名（`up_1_daf610fa_...`） |

## 6. R03-b 基线对账（防回退）

**⚠️ `r03b_verify.py` 原样当前不可跑**：其 `_read_all_light` 自检要求 `query==count(*)`，实测 count(*)=3424 vs query=3414，**稳定差 10 行**（非瞬态，Strong/Bounded/Eventually 各一致性级别均复现）。逐 chunk_id 定位：10 行幽灵全在 `user_1` 租户 doc_chunk，即 WNEXTRAG1 重建 upsert 的旧版本——`count=2 / query=1`，Milvus count 路径未反映已删除旧版本；query 层数据唯一正确。

对账改用 `scripts/eval/_t14/r03b_crosscheck.py`：**import r03b_verify 原 G1/G2/G4 权威判定函数**，仅读取路径换分页拉取（绕开失真的 count==query 自检，差异已记录）；G3 按脚本自身回退规则（sidecar 8601 实测不可用 → persisted replay）。

| 步骤 | 结果 | 数值 |
|---|---|---|
| G1 id_map | **FAIL（已知陈旧口径，与 critique-T10 一致）** | id_map 4417 / new_in_lib 3343 / 旧残留 0 / golden 32/32 在 map / 格式违例 0 |
| G2 canonical | **PASS** | hash 100%、doc_sha256 100%、seq 组 3344 ok / 0 bad |
| G3 指标 | **PASS** | **hit_rate@5=0.9688 / mrr@5=0.9688 / delta=0.0 / within_threshold=true**（持久化对账，非实时——critique P0-6 仍成立，实时复跑需 sidecar 8601） |
| G4 唯一性/隔离 | **PASS** | row 3414 / dup_chunk_id=0 / dup_pk=0 / 隔离抽样 145/200（与 critique 时代同值） |

**kickoff 对账目标全部达成：hit_rate 0.9688 ✓、mrr 0.9688 ✓、唯一性 0 违例 ✓。**

## 7. S6【回归保护】真内部工程文档可见性 — **FAIL（重要）**

- 实测对象：`_default:b463bf27f242c042:1`（`source_file=1578ae407f71.md`，hex 临时名，含"实现规划/RespModel"语料的真内部工程文档），当前 `internal=False`。
- **student 检索命中该文档（可见）**——kickoff 预期"仍不可见"，实测 FAIL。
- 对照：admin 同样命中（双角色一致）。
- **门逻辑本身完好**：`classify_internal('296c5e2852b3.md', 良性内容)=True`——hex 来源正则仍判 internal；问题纯为数据状态：WNEXTRAG1 按用户显式选择把全部 742 条（含 732 条真内部）重建为 `internal=False`。当前全库 `internal=True` 行数=0。
- **这不是修复代码的缺陷，是用户知情选择的直接后果（WNEXTRAG1 报告 §8 已声明）**。但按本任务"回归保护"口径必须记 FAIL：**「内部文档对学生隐藏」特性当前在全库处于关闭状态。**

## 8. S7 并发基线漂移

| 时点 | 总行数(count) | doc_chunk | user_1 | tasks |
|---|---|---|---|---|
| before | 3379 | 742 | 10 | 124 |
| mid（测试中） | 3424 | 787 | 39 | 131 |
| after（自清后） | **3379** | **742** | **10** | **124** |

- 漂移 +45 chunk / +7 task **全部归因于本任务 7 次上传**（逐 source_file 归集确认，无他方写入；同期无其他 agent 写库迹象）。
- 自清后各口径**零净漂移**（含 count 幽灵差回到前态同值 10）。

## 9. 守则执行与偏差声明

- ✅ 禁 Playwright；全部 curl/requests（`127.0.0.1:8010` host 写死）；Milvus/MySQL 核验全部只读参数绑定；密钥仅从 app.config(.env) 读。
- ✅ 上传全走产品 API；8000 未重启；8010 临时实例用毕已关。
- ⚠️ **偏差 1（产品能力缺口）**：kickoff 要求"用完按 knowledge_import_task 全删（走产品 API + admin 路径）"——**产品 API 不存在文档级/任务级删除端点**（全应用仅 `DELETE /api/knowledge/partitions/{tenant}`，user 租户 50301、`_default` 受保护；复证 critique P0-3）。实际自清经**用户本会话明确批准**后走「全量备份 → 脚本直删」：Milvus 45 行（6 个 source_file 白名单，foreign=0 防呆）+ MySQL 7 task 行（参数绑定 DELETE）；备份 `scripts/eval/_t14/cleanup_backup_t14_rows.json`（45 行全实体，可回滚）。本地上传文件由产品 `_process_import.finally._cleanup_paths` 自动清理；MinIO 对象 key 已登记（`cleanup_minio_keys.json`，产品 30 天 TTL 自然过期）。
- ⚠️ **偏差 2（守则措辞冲突）**：守则"只读 SQL/Milvus"与红线"自建自清"在无产品删除能力的现实下不可兼得；按红线优先 + 用户批准执行了上述写删除，全程白名单 + 备份 + 删后复核。

## 10. 问题清单（仍存在 / 新冒）

| # | 严重度 | 问题 | 状态 |
|---|---|---|---|
| 1 | **P0 安全** | **732 条真实内部工程文档对 student 全可见**（S6 FAIL）：全库 internal=True=0；学生泛化查询被内部文档噪声污染（定语从句 top2-5、B+树 top4/5 均命中"验收标准 GWT"等工程 md）。建议按 `deploy/backups/wnextrag1_fullbackup_pre_apply.json` 把 732 条 `_default` 行 internal 置回 True 并 upsert（可逆，WNEXTRAG1 §8 同方案） | **新冒（用户选择的副作用，需治理决策）** |
| 2 | P1 检索质量 | 泛化查询 top5 被内部工程文档抢占（score 0.85-0.99 压过教学内容）；"雅思听力/定语从句"类库内无知识的查询 top1 相关性弱 | 新冒（与 #1 同源，#1 解决后应缓解） |
| 3 | P1 工具 | `r03b_verify.py` 在当前库不可跑（count 幽灵差 10 行撞 `_read_all_light` 自检）；G3 实时复跑仍需 sidecar 8601（critique P0-6 未闭环） | 新冒 |
| 4 | P0 产品能力 | 无文档级/任务级删除 API（复证 critique P0-3）：测试数据/用户误传无法经产品路径自清 | 仍存在 |
| 5 | P2 基线 | r03b G1 陈旧口径 FAIL（id_map 4417 vs new_in_lib 3343） | 仍存在（已知） |
| 6 | P2 观察 | MinIO `object_key`=原文件名，同名文件跨任务/跨用户互相覆盖（S4 两次上传同 key） | 仍存在（低风险登记） |
| 7 | P2 观察 | T10 遗留测试数据（user_1 的 10 行 T10 marker doc_chunk）仍在库中，非本任务产生、未动 | 仍存在（建议其 owner 清理） |
| 8 | **P1 交付风险** | **W-NEXT-RAG-001 修复代码尚未进入 `feature/opt-waves` 分支**：HEAD 版本 upload.py 仍是旧 `uuid4().hex[:12]` 命名，修复仅以暂存区改动 + 孤立提交 `1a1922f` 存在；本次 8010 跑的是工作树代码。编排者需确保其正式落盘，否则其他环境部署的仍是旧逻辑 | 新冒（git 状态观察） |

## 11. 编排者复验清单对照

| 复验重点 | 本报告结果 |
|---|---|
| S1 12/12 命中合理 + ≥3 条 doc_chunk 路径 | 10/12 合理（2 条 FAIL 见 §3）；doc_chunk 路径 4 条 |
| S2 同内容跨租户隔离数据层确定 | PASS（Milvus 亲测：同 h16 双前缀 8+8 行） |
| S3 同内容多块 seq 区分 | PASS（seq=[1,2,3]） |
| S4 幂等不翻倍 | PASS（3+3=3 unique） |
| R03-b 数字对账 | hit 0.9688 / mrr 0.9688 / dup 0 全对上；G1 陈旧口径 FAIL（已知） |
| S5 student 检索自己上传 doc 真命中 | **PASS（真命中）** |
| S6 旧内部工程文档仍不可见 | **FAIL（可见，732 条全可见）** |
| S7 总行数漂移 ±N 登记 | +45/+7 全归因本任务，自清后归零 |

## 12. 证据文件（`edu-agent/scripts/eval/_t14/`，未跟踪不入提交）

`s1_result.json` / `s234_result.json` / `s5_result.json` / `s6_result.json` / `r03b_crosscheck_result.json` / `probe_before.json` / `probe_mid.json` / `probe_after.json` / `cleanup_backup_t14_rows.json`（45 行全实体备份）/ `cleanup_minio_keys.json` / 场景脚本 `s1_*.py s234_*.py s5_*.py s6_*.py r03b_crosscheck.py probe_baseline.py cleanup.py harness.py` + 测试语料 `data/t14_*.md`。

## 13. 附：环境观察（非本任务问题）

- 仓库存在坏备份 ref `refs/backup/surfaced1-12-2cfaa7b`（`git log --all` 报 fatal: bad object），来自并行 agent 环境，不影响本任务提交。
- 锁文件 `edu-agent/scripts/eval/t14.lock` 已于完工删除。
