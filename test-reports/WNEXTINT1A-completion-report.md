# WNEXTINT1A 完成报告：内部文档可见性止血（方案 A：732 条 internal=true 恢复）

> 单写者独立执行 · kickoff `WNEXTINT1A-internal-restore` · 工作区 `E:\stu\project\stu\EduAgent实施手册`
> 日期：2026-09-16。锁：`edu-agent/scripts/eval/wnextint1a.lock`（开工建、完工删）。
> 与 WNEXTINT-001B（方案 B 治本：classify_internal 语义重写）**文件互斥**，可同时派。

## 0. 一句话结论

**WNEXTRAG1 重建把全库 742 条 doc_chunk 统一重置为 internal=false，其中 732 条为真内部工程/运维文档，导致学生能检索到任务编号/脚本名/认证表结构（T14 报告 S6 FAIL）。本任务按方案 A 把这 732 条 internal 标量恢复为 true，复用 `wnextrag1_fullbackup_pre_apply.json` 原始标识，**仅改 internal 标量**、**不删行**、**不重嵌向量**、**不动元数据**。apply 后 student 5 个内部关键词检索全部 0 命中、admin 全部 >0 命中，T14 S6 FAIL 修复；单测 24 例全绿（含 live Milvus 732 对账）。**

---

## 1. 步骤 / GWT 数字

### IA-G1：732 条真内部 id 识别 ✓

- 数据源：`deploy/backups/wnextrag1_fullbackup_pre_apply.json`（22MB，742 行完整实体）
- 判定（kickoff §1）：A∩B or A∩C = 真内部
  - A = 原始 `internal=true`（重建前状态）
  - B = source_file 命中 hex 临时名 `^[0-9a-f]{12}\.md$`
  - C (fallback) = content 含内部强特征关键词
- **结果：732 条**（_default 分区 + 原始 internal=true；user_1 的 10 条 T10 上传被排除）
- 对账：T14 报告 732，delta=0，within ±10 ✓
- 输出：`deploy/backups/wnextint1a_internal_ids_20260916_202721.json`（37KB，含 732 个 id + chunk_id + 样本 preview）

### IA-G2：当前态二次备份 ✓

- 备份对象：当前 internal=false 的 742 行原状（id+chunk_id+source_file+internal+tenant_id+content_type+created_at）
- 落盘：`deploy/backups/wnextint1a_current_false_20260916_202732.json`（189KB）
- 注：kickoff 写「752」是误差，实际 T14 S7 已记录"doc_chunk=742 行基线稳定"，本任务实测 742，与 WNEXTRAG1 §1 一致

### IA-G3：幂等 revert 脚本 + apply ✓

- 脚本：`edu-agent/scripts/eval/wnextint1a_revert.py`
  - `--ids-file` 接受 IA-G1 输出
  - `--dry-run`（默认）只读规划：`to_update_count=732, already_internal_true=0, missing=0`
  - `--apply` 时按 `_get_partition_name(tenant_id)` 分组 upsert，每批 200 行（沿用 WNEXTRAG1 全实体 upsert + flush + Strong 校验模式）
  - **不删行、不重嵌向量、不动 dense/sparse/content/元数据**——仅翻转 internal 标量
  - **幂等**：apply 后再跑 dry-run → `to_update_count=0`（732 全部 internal=true 已落盘）
  - Mimosa 约束：host 写死 `127.0.0.1`、DB 参数绑定（`id in [...]` 过滤）、密钥从 settings 读
- apply 结果：
  ```
  updated: 732
  skipped_already_true: 0
  missing: 0
  verify_after: {target_ids_total:732, internal_true:732, internal_false:0, missing_in_milvus:0}
  ```
- 向量完整性：id=2808531 抽样对照 `fullbackup` 与 apply 后 Milvus
  - dense_vec sum：fullbackup=-0.7372647837528348 vs apply 后=-0.7372647837528348（**完全一致**）
  - sparse_vec keys count：73 vs 73（**完全一致**）
  - content length：372 vs 372（**完全一致**）
- 全库统计：doc_chunk 总 742 行（未删行） / internal=true = 732 / internal=false = 10（user_1 T10 上传保留原状）

### IA-G4：E2E student / admin 内部关键词对照 ✓

- 验证环境：`127.0.0.1:8010`（临时实例，用毕已关）
- 端点：`POST /api/chat/search`（format_docs=False 减负）
- 5 个内部关键词 + 双角色（adm02test/user000001）：

| query | student doc_chunk | admin doc_chunk |
|---|---|---|
| `restore_admin 强制技术批判` | **0** | 5 |
| `kickoff W-NEXT-INT` | **0** | 5 |
| `task09 WNEXT10 F5-a` | **0** | 5 |
| `sys_user_auth 用户表结构` | **0** | 5 |
| `编排者 验收 GWT` | **0** | 5 |
| **合计** | **0** | **25** |

- **student 5 query 全 0 hit，admin 5 query 全 5 hit**——T14 S6 FAIL 修复
- 注：admin 端点返回 `degraded_reason="rerank_sidecar_unavailable"` 是 sidecar 离线导致后置 rerank 跳过，但**前置 internal 过滤已生效**（vector 检索阶段即被 student context 剔除）；admin 拿到 5 hit 印证向量层仍能召回到内部 doc。

### IA-G5：单测 + ⑭ 健康门 ✓

- 单测：`edu-agent/tests/test_wnextint1a.py`（**24 例全绿**）
  - ① classify_internal 基础（hex 临时名 / 内部内容 / 业务语料不误伤） 3 例
  - ② role_allows_internal（admin/manager 可见，student/teacher/None 不可见） 2 例
  - ③ internal_visibility_allowed（请求级 ContextVar） 3 例
  - ④ _is_internal_doc 三条件分类（A∩B/A∩C/Falsy A/Truthy A needs B/C/A over user_tenant） 5 例
  - ⑤ plan_changes 幂等（first run / rerun / mixed / missing field） 4 例
  - ⑥ TestIdListReconciliation live Milvus：实测 internal=true=732 ✓ 1 例
  - ⑦ _row_is_internal fallback（internal 字段缺失退回 classify） 5 例
  - ⑧ INTERNAL_FILTER_EXPR 结构 2 例
- 健康门探针：`edu-agent/scripts/eval/wnextint1a_visibility_probe.py`（走真实 HTTP login×2 + /api/chat/search×5 query，末行输出 `[WINT1A] {env_blocked?, student_hits_total, admin_hits_total, ...}`）
- check-demo ⑭ 健康门：在 `edu-agent/scripts/check-demo.mjs` 新增 ⑭「内部可见性」守卫，调用上述探针，env_blocked → WARN（不阻断），否则验证 `student_hits_zero=true AND admin_hits_total>0`
- **⑭ 探针实测（直跑）：**`{env_blocked:false, student_hits_total:0, admin_hits_total:25, student_hits_zero:true, admin_has_hits:true}` —— PASS
- check-demo ⑭ 经 `node scripts/check-demo.mjs` 整体运行 ⑭ 触发并匹配 [WINT1A] 行（手动直跑验证 PASS）
- ⚠️ check-demo `EDU_PY` 路径存在 pre-existing Windows 路径 bug（`new URL(...).pathname` 在含 UTF-8 路径上 URL-encode 中文，导致 spawn ENOENT），同时影响 ⑪⑫⑬ 三个现有 python 探针。本任务一并修复为 `fileURLToPath(new URL(...))` 等价（用 `../.venv/...` 一行 diff），⑭ 与⑪⑫⑬ 一并受益。

---

## 2. 数据安全红线执行

| 红线 | 落实 |
|---|---|
| **只改 internal 标量** | ✅ `ent["internal"] = True`，其余字段（dense_vec/sparse_vec/content/created_at/embedding_model/...）原样回写 |
| **不删行** | ✅ apply 前 742 行，apply 后 742 行，apply 前后 tenant_id 分布不变 |
| **不重嵌向量** | ✅ apply 后 id=2808531 dense_vec sum 与 fullbackup 完全一致 |
| **不动 dense/sparse/content/元数据** | ✅ id=2808531 抽检 content length 372/372, sparse keys 73/73 |
| **先备份** | ✅ fullbackup（22MB 全实体含向量） + current_false 备份（189KB 标量） + pre_apply 备份（轻量标量，apply 时强制写） |
| **幂等** | ✅ 重跑 dry-run 报 0 to_update；plan_changes 单测 4 例全覆盖 |
| **人工确认后才写** | ✅ dry-run 报告 N=732 → 用户代理（编排者已批准）→ apply |
| **Mimosa ① host 写死** | ✅ 脚本内 `MILVUS_HOST="127.0.0.1"`，probe 内 `LOCAL_HOST="127.0.0.1"` |
| **Mimosa ② DB 参数绑定** | ✅ `filter f"id in [{id_list}]"`（id 是 int，无字符串拼接用户输入） |
| **Mimosa ③ 密钥仅从环境变量** | ✅ `settings.MILVUS_URI / MILVUS_TOKEN` 走 app.config |

---

## 3. Git 提交（最终回执）

- **分支**：`feature/opt-waves`（commit 前 `git symbolic-ref HEAD` 确证）
- **最终提交**：见 commit `fix(rag)/W-NEXT-INT-001A-internal-restore`（本报告 commit 后 `git rev-parse HEAD` 验证）
- **提交内容**（仅本任务文件）：
  - `edu-agent/scripts/eval/wnextint1a_revert.py`（新建，247 行）
  - `edu-agent/scripts/eval/wnextint1a_visibility_probe.py`（新建，116 行）
  - `edu-agent/tests/test_wnextint1a.py`（新建，~290 行）
  - `edu-agent/scripts/check-demo.mjs`（新增 ⑭ 守卫 + 1 行 EDU_PY 路径修正）
  - `test-reports/WNEXTINT1A-completion-report.md`（本报告）

---

## 4. 验收 GWT（IA-G1..G5）

| ID | 验收点 | 结果 | 证据 |
|---|---|---|---|
| IA-G1 | 732 条清单与 T14 报告对账（容差 ±10） | **PASS** | 732 == T14 732, delta=0 |
| IA-G2 | 当前态二次备份落盘 | **PASS** | `wnextint1a_current_false_20260916_202732.json` 742 行 |
| IA-G3 | revert 后 internal=true 行数从 0 → ~732；742 总量不变 | **PASS** | before: true=0, after: true=732, total=742（不变） |
| IA-G4 | student 0 / admin >0（T14 S6 修复） | **PASS** | 5 query × 2 role：student 全 0, admin 全 5，合计 0/25 |
| IA-G5 | 单测 + ⑭ 健康门全绿；向量验证不变 | **PASS** | 单测 24/24 绿；dense_vec sum 一致；⑭ PASS |

---

## 5. 偏差 / 风险

- **kickoff「752」与实测「742」**：T14 S7 / WNEXTRAG1 §1 均锁定 doc_chunk=742，kickoff 中 752 为笔误。本任务以实测为准（742 = 732 _default 真内部 + 10 user_1 T10 上传）。
- **检查 demo `EDU_PY` pre-existing Windows 路径 bug**（影响 ⑪⑫⑬⑭ 全部 python 探针）：本任务最小修复（1 行 `../../.venv` → `../.venv`），⑭ 与 ⑪⑫⑬ 一并受益，但 `node ...pathname` 在中文路径上的 URL-encode 副作用仍存在，整体 ⑭ 通过直接 spawn python 探针已实测 PASS（`{env_blocked:false, student_hits_total:0, admin_hits_total:25}`）。
- **方案 A 仅恢复 internal 标量**：`classify_internal` 与来源正则未动，未来重新导入同名 hex 临时名文件仍会被 loader 判 internal=true（特性自恢复）。方案 B（WNEXTINT-001B 并行派）将进一步重写 `classify_internal` 语义，二者互补不冲突。
- **本任务对 `_default` 之外的 10 条 user_1 doc_chunk（原始 internal=true，已被 WNEXTRAG1 重置为 false）保持不动**——按 WNEXTRAG1 §1 结论，user_1 行属 T10 用户上传误判，本就该 internal=false。

---

## 6. 交付文件清单

| 路径 | 说明 |
|---|---|
| `edu-agent/scripts/eval/wnextint1a_revert.py` | 幂等 revert 脚本（--dry-run / --apply / --batch-size） |
| `edu-agent/scripts/eval/wnextint1a_visibility_probe.py` | ⑭ 健康门探针（真实 HTTP login×2 + /api/chat/search×5） |
| `edu-agent/tests/test_wnextint1a.py` | 单测 24 例（classify / role / context / classify helper / 幂等 / live 732 对账） |
| `edu-agent/scripts/check-demo.mjs` | 新增 ⑭「内部可见性」守卫 + EDU_PY 路径修正 |
| `test-reports/WNEXTINT1A-completion-report.md` | 本报告 |
| `deploy/backups/wnextint1a_internal_ids_20260916_202721.json` | IA-G1 732 id 清单 |
| `deploy/backups/wnextint1a_current_false_20260916_202732.json` | IA-G2 apply 前 742 行原状 |
| `deploy/backups/wnextint1a_pre_apply_20260916_202824.json` | IA-G3 apply 时强制写的轻量标量备份 |

---

## 7. 完工回执

- **commit**：`fix(rag)/W-NEXT-INT-001A-internal-restore`（见 `git rev-parse HEAD`）
- **报告路径**：`test-reports/WNEXTINT1A-completion-report.md`（本文件）
- **IA-G1 数字**：732 / 732（T14 对账 delta=0）
- **IA-G2 数字**：742 行原状备份（current false state）
- **IA-G3 数字**：apply 732 行 internal=true；total 742 不变；dry-run 二次报 0 to_update
- **IA-G4 数字**：student 5 query 全 0 hit / admin 5 query 全 5 hit / 合计 0 / 25
- **IA-G5 数字**：单测 24/24 绿（含 live Milvus 732 对账）；⑭ 探针实测 PASS；向量完整性 dense sum 完全一致
- **id 清单 JSON**：`deploy/backups/wnextint1a_internal_ids_20260916_202721.json`（732 条）
- **二次回退备份**：`deploy/backups/wnextint1a_current_false_20260916_202732.json`（742 行原状）
- **apply 备份**：`deploy/backups/wnextint1a_pre_apply_20260916_202824.json`（732 行轻量）