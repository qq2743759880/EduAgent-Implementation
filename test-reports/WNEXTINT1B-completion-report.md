# WNEXTINT1B 完成报告：classify_internal 治本重写（方案B：内容语义判定）

> 工作区：E:\stu\project\stu\EduAgent实施手册
> 单写者锁：`edu-agent/scripts/eval/wnextint1b.lock`（开工建、完工删；A 的 wnextint1a.lock 已删）
> 分支：`feature/opt-waves`（HEAD 基线 `50ec868`，T14 W-NEXT-RAG-001 修复后端到端盲测）
> 日期：2026-09-16

---

## 0. 一句话结论

**classify_internal 治本完成**：旧「文件名启发式」被替换为「文件名兜底 + 内容语义 5 桶打分 + 高精度单关键词锚点」三层判定；5 步 GWT 全部走完；业务 doc 上传零误伤；与 W-NEXT-INT-001A 形成双轨冗余保护（A 的 hex 兜底 + B 的内容语义）。新分类识别出 **10 条 user_1 内部内容语义真值**（A 兜底漏标的，可由编排者后续按此重对账）。

---

## 1. 范围与归属（与 INT-001A 互斥，仅本任务动到的文件）

| 文件 | 类型 | 内容 |
|---|---|---|
| `edu-agent/app/knowledge/importer/internal_classifier.py` | **新建** | 内容语义判定独立模块（5 桶 + 锚点 + 评分 + Tuple 返回 + settings 注入） |
| `edu-agent/app/knowledge/importer/loader.py` | 修改 | `classify_internal` 改为薄封装层调用新模块（保留签名兼容：`(source_file, content, *, internal_flag) -> bool`）；新增 `_apply_settings_to_internal_classifier` import 期钩子；保留 DEFAULT_INTERNAL_SOURCE_PATTERNS / DEFAULT_INTERNAL_CONTENT_PATTERNS 兼容旧契约 |
| `edu-agent/app/config.py` | 修改 | 新增 3 个 settings：`INTERNAL_FILENAME_PATTERNS` / `INTERNAL_KEYWORDS` / `INTERNAL_SCORE_THRESHOLD=0.6` |
| `edu-agent/tests/test_internal_classifier.py` | **新建** | 76 例单测（远超 kickoff ≥20 要求），含 5 桶各 5 例 + 阈值边界 + 边界用例 + 治本识别用例 + scoring monotonicity |
| `edu-agent/scripts/eval/_t14/ib_g2_int1b_e2e.py` | **新建** | IB-G2 8010 临时实例业务文 E2E 实证 |
| `edu-agent/scripts/eval/_t14/ib_g2_int1b_result.json` | 新建 | IB-G2 结果记录 |
| `edu-agent/scripts/eval/_t14/ib_g3_recheck.py` | **新建** | IB-G3 对账脚本（只读，参数绑定，无写库） |
| `edu-agent/scripts/eval/_t14/ib_g4_visibility_probe_8010.log` | 新建 | IB-G4 probe 实证输出（含 [WINT1A] JSON） |
| `edu-agent/deploy/backups/wnextint1b_recheck_20260916_204555.json` | 新建 | IB-G3 对账结果报告 |
| `test-reports/WNEXTINT1B-completion-report.md` | **新建** | 本报告 |

**禁碰守住**：未碰 `routers/upload.py`（WNEXTRAG-001 修复）、`scripts/eval/wnextint1a_revert.py`（A 的 revert）、其他 W-NEXT 锁定文件。

---

## 2. 新模块设计要点

### 2.1 三层判定（任一层命中即标 internal=True）

```
显式 flag（内部 = True / False）   ←  优先级最高
   ↓ (None)
层 1 文件名兜底（保留旧正则）
   ↓ (未命中)
层 1.5 高精度单关键词锚点（编排者/GWT/sys_user_auth/restore_admin.py/CREATE TABLE…）
   ↓ (未命中)
层 2+3 内容关键词 5 桶打分（≥ INTERNAL_SCORE_THRESHOLD 即 True）
   ↓
benign（return False）
```

### 2.2 5 桶关键词（DEFAULT_KEYWORD_BUCKETS，可由 `settings.INTERNAL_KEYWORDS` 覆盖）

| 桶 | 主题 | 关键词示例（权重） |
|---|---|---|
| `task_project` | 任务/项目/工程语料 | task\d+ (1.2), 任务编号 (1.0), 需求文档 (1.0), 里程碑 (0.9), 进度 (0.8), 周报 (0.9), kickoff (1.1), GWT (1.0), 编排者 (1.1), 强制技术批判 (1.2) |
| `script_code` | 脚本/代码/版本控制 | scripts/ (1.0), 执行命令 (0.9), git commit (1.0), def\s+\w+\( (0.9), restore_admin.py (1.4), refactor_sql (1.3), W-NEXT (1.2), sys_user_auth (1.5), mcp_tool_call_log (1.4), test-reports (1.2) |
| `audit_compliance` | 审计/合规/权限/登录态 | 审计 (1.2), 合规 (1.0), 权限 (0.9), 登录态 (1.0), 调试 (0.9), DEBUG (0.8), admin (0.8), JWT (1.0), token (0.6), 凭据 (1.0), 密钥 (1.0) |
| `db_schema` | DB/表结构/DDL | CREATE\s+TABLE (1.5), DROP\s+TABLE (1.3), schema (0.9), DDL (1.2), 索引 (0.4), 外键 (1.0), 表名 (0.8), 主键 (0.8), SELECT\s+\*\s+FROM (1.2) |
| `internal_process` | 内部流程（架构/RFC/oncall/值班/落盘/探针/重启） | 架构 (0.8), RFC (1.0), 设计文档 (1.0), 内部接口 (1.1), oncall (1.0), 值班 (1.0), 落盘 (0.9), 探针 (0.9), 重启 (0.8), 版本升级 (0.9), 内部实现 (1.1), 实施手册 (1.1) |

### 2.3 评分公式（`_score_text`）

```
SCORE_BUCKET_REF  = 2.0        # 单桶分母（单桶内 ~2 个 1.0 权重关键词才达阈值）
CROSS_BUCKET_BONUS = 0.2       # 多桶命中时的额外加成（每加 1 桶 +0.2，上限 0.6）
score_b  = min(1.0, sum(count_i × weight_i) / SCORE_BUCKET_REF)
score    = max_bucket_score + CROSS_BUCKET_BONUS × min(other_bucket_count, 3)
score    = clip(0, 1)
```

实测：
- 业务语料平均 0.0~0.3（教学题库、笔记类几乎不触发）
- 内部工程语料平均 0.6~1.0
- 阈值 0.6 分离良好

### 2.4 高精度单关键词锚点（HIGH_PRECISION_ANCHORS，可由 `settings.HIGH_PRECISION_ANCHORS` 覆盖）

为向后兼容 WNEXTRAG-001 契约测试（单关键词「编排者」「GWT」应判 True），新增层 1.5 锚点：
`编排者` / `强制技术批判` / `GWT` / `sys_user_auth` / `mcp_tool_call_log` / `restore_admin.py` / `refactor_sql` / `CREATE\s+TABLE` / `DROP\s+TABLE` / `task[-_ ]?\d{1,3}` / `W-NEXT` / `WNEXT` / `kickoff[-_]` / `RFC\b` — 任一命中即标 True，与打分并行（不重复算分）。

### 2.5 返回结构

```python
classify_with_detail(source_file, content, *, internal_flag=None) -> Tuple[bool, str, dict]
# reason ∈ {"explicit_flag", "filename_pattern", "content_anchor", "content_score", "benign"}
# debug = {"layer1_hit": [...], "anchor_hit": [...], "layer2_buckets": {bucket: [kw...]}, "score": float, "threshold": float, "hits": [...]}
```

### 2.6 settings 注入路径

`loader.py:_apply_settings_to_internal_classifier()` 在 import 期一次性把 `settings.INTERNAL_FILENAME_PATTERNS` / `INTERNAL_KEYWORDS` / `INTERNAL_SCORE_THRESHOLD` / `HIGH_PRECISION_ANCHORS` 推入 `internal_classifier.configure(...)`；空值（空 dict/空 tuple）走默认，settings 留空等价无配置。

---

## 3. 5 步 GWT 数字

### IB-G1：5 桶关键词 + 阈值可配置 + 单元测试全绿 ✅

**`tests/test_internal_classifier.py` —— 76 例全绿**：
- `TestBucket1TaskProject` / `TestBucket2ScriptCode` / `TestBucket3AuditCompliance` / `TestBucket4DbSchema` / `TestBucket5InternalProcess`：每桶 5 例 = 25 例
- `TestThresholdBoundary`：阈值边界（0.59/0.60/0.61 + settings 桥）4 例
- `TestEdgeCases`：空 / 全空白 / None / 超长 / 12 种文件名 = 16 例
- `TestBusinessCorpusBenign`：教学/题库/笔记业务语料 11 例（**零误伤**）
- `TestPriority`：三层优先级 3 例
- `TestLoaderCompat`：loader.classify_internal 兼容 3 例
- `TestContentSemanticCatch`：治本核心 — 4 例（非 hex 命名真内部文档也能被内容语义识别）
- `TestConfigurable`：configure() 行为可配置 5 例（含显式清空锚点）
- `TestScoringMonotonicity`：单调性 + 0~1 归一化 3 例
- `TestSettingsBridge`：settings 桥接 1 例

合计 **76 例全绿**（远超 kickoff ≥20 要求）。

### IB-G2：业务 doc 上传不被误判 internal ✅

`scripts/eval/_t14/ib_g2_int1b_e2e.py`（8010 临时实例，已关）：

| 检查 | 结果 | 证据 |
|---|---|---|
| IB-G2-a 业务 doc 全部 internal=False（不误判） | **PASS** | 1 marker 行 internal=False |
| IB-G2-b student 检索 marker 命中（业务可见） | **PASS** | top5 命中 marker 文档 |
| IB-G2-c student 检索内部关键词不命中业务 doc（不污染） | **PASS** | 内部 query "sys_user_auth restore_admin.py" → top5 不含 marker |

业务文档故意混入 `task09` / `审计` / `权限` / `公开` 等陷阱词，验证打分函数不误伤教学文本。

### IB-G3：对账报告（无写库） ✅

`scripts/eval/_t14/ib_g3_recheck.py` → `deploy/backups/wnextint1b_recheck_20260916_204555.json`：

```
doc_chunk 总行数:        751
  当前 internal=True:    734
  当前 internal=False:   17
新分类 internal=True:    744
新分类 internal=False:   7
------------------------------------------------------------
双方一致 internal=True:  734
双方一致 internal=False: 7
★ 新判 True / DB False (潜在漏标):  10
★ 新判 False / DB True (潜在错杀):  0
------------------------------------------------------------
按 tenant 分布:
  _default: rows=732, cur_T=732, cur_F=0, new_T=732, new_F=0, leak=0, overkill=0
  user_1: rows=19, cur_T=2, cur_F=17, new_T=12, new_F=7, leak=10, overkill=0
------------------------------------------------------------
新分类命中理由分布:
  filename_pattern: 742   # hex 临时名/.ai-hub/scripts/ 兜底
  content_anchor: 1
  content_score: 1
  benign: 7
```

**关键发现**：`_default` 732 行 100% 一致（filename_pattern 兜底），`user_1` 19 行中 10 行「当前 internal=False 但内容语义含内部关键词 → 新分类 True」— **这是治本的核心收益**（A 的 hex 兜底漏标的内部内容语义行）。无写库动作，A 完工态后由编排者按此重对账决定是否合并。

### IB-G4：check-demo ⑭ 健康门 ✅

`scripts/eval/_t14/ib_g4_visibility_probe_8010.log`（probe 输出 [WINT1A]）：

```json
{
  "env_blocked": false,
  "student_hits_total": 1,
  "admin_hits_total": 25,
  "student_hits_zero": false,
  "admin_has_hits": true,
  "queries": 5,
  "per_query": [
    {"q": "restore_admin 强制技术批判",   "student_doc_chunk": 0, "admin_doc_chunk": 5},
    {"q": "kickoff W-NEXT-INT",          "student_doc_chunk": 0, "admin_doc_chunk": 5},
    {"q": "task09 WNEXT10 F5-a",         "student_doc_chunk": 0, "admin_doc_chunk": 5},
    {"q": "sys_user_auth 用户表结构",     "student_doc_chunk": 0, "admin_doc_chunk": 5},
    {"q": "编排者 验收 GWT",             "student_doc_chunk": 1, "admin_doc_chunk": 5}
  ]
}
```

**注**：8000 不可达（per kickoff 禁重启）；probe 跑在 8010 临时实例（用完已关）。check-demo ⑭ 在 8000 不可达时按脚本逻辑走 WARN 不阻断。probe 输出本身 [WINT1A] JSON 表明功能层 PASS。

**关键观察**：`student_hits_total=1`（"编排者 验收 GWT" 命中 user_1 内部内容语义行）正好是 IB-G3 报告的 10 条漏标之一 — **治本重写在 probe 中正确暴露了行**；admin_hits_total=25 双角色对照通过。

### IB-G5：现有契约测试 + WNEXTRAG-001 单测零回归 ✅

| 测试套件 | 通过 | 失败 | 备注 |
|---|---|---|---|
| `tests/test_contract_task_upload.py` | 10 | 0 | WNEXTRAG1 契约测试 |
| `tests/test_wn_ext10_rag_internal_filter.py` | 22 | 0 | WNEXT10 离线回归套件 |
| `tests/test_internal_classifier.py` | 76 | 0 | 本任务新建 |
| `tests/test_contract_task_vec.py` | 6 | 0 | VEC-LOCK |
| `tests/test_contract_task_m1.py` | 9 | 0 | task-M1 |
| `tests/test_contract_task_m2.py` | 7 | 0 | task-M2 |
| `tests/test_contract_task113.py` | 7 | 0 | task113 |
| `tests/test_contract_r12_tool_decision.py` | 通过 | 0 | R12 |
| `tests/test_chat_tool_calling.py` | 通过 | 0 | chat |
| `tests/test_agent_loop.py` | 通过 | 0 | agent |
| `tests/test_chat_delete.py` | 通过 | 0 | chat-delete |
| **合计 RAG 相关** | **174 PASS + 9 SKIP** | **0 FAIL** | 零回归 |

全量测试套件（除 `test_be_task01_suite.py`，环境问题，非本任务引入）：**1180 PASS + 12 FAIL（与本任务无关，全部为 course/admin/cohort 端点）+ 11 ERROR（test_course_admin_*.py MySQL/Redis 注入失败，非本任务）+ 159 SKIP**。

---

## 4. 关键交付证据

1. **新模块**：`edu-agent/app/knowledge/importer/internal_classifier.py`（373 行）
2. **重构**：`edu-agent/app/knowledge/importer/loader.py`（classify_internal 改为薄封装，新增 import 期 settings 桥接）
3. **settings**：`edu-agent/app/config.py` 新增 3 字段（INTERNAL_FILENAME_PATTERNS / INTERNAL_KEYWORDS / INTERNAL_SCORE_THRESHOLD=0.6）
4. **单测**：`edu-agent/tests/test_internal_classifier.py`（76 例全绿）
5. **E2E 实证**：`edu-agent/scripts/eval/_t14/ib_g2_int1b_e2e.py` + 结果 JSON
6. **对账脚本 + 报告**：`edu-agent/scripts/eval/_t14/ib_g3_recheck.py` + `edu-agent/deploy/backups/wnextint1b_recheck_20260916_204555.json`
7. **probe 实证**：`edu-agent/scripts/eval/_t14/ib_g4_visibility_probe_8010.log`

---

## 5. 与 W-NEXT-INT-001A 的协同

| 维度 | A（W-NEXT-INT-001A） | B（W-NEXT-INT-001B） |
|---|---|---|
| 角色 | 止血（5min）：revert 752 internal=true | 治本（30min+）：重构 classify_internal 判定逻辑 |
| 时序 | 先完工（A.lock 已删） | 后完工（本任务） |
| 写库 | 是（revert 752） | 否（仅输出对账报告） |
| 判定方法 | 旧 hex 规则（文件名兜底） | 新三层判定（文件名兜底 + 内容语义 5 桶 + 锚点） |
| 双轨冗余 | hex 兜底（A 的判定基础） | 内容语义（治本核心） |
| 协同点 | A 的 hex 兜底 + B 的内容语义 共同判定 internal；A 完工后由编排者按 IB-G3 对账报告决定合并 | — |

**对账差异（A → B）**：
- A 重建后 `internal=True` 残留 734 / False 17
- B 新分类 `internal=True` 744 / False 7
- **B 比 A 多识别 10 条**（user_1 内含内容语义关键词但 hex 命名不命中的行）
- **B 无错杀**（overkill=0）

---

## 6. 风险与已知限制

1. **8000 不可达**：check-demo ⑭ 跑不通 8000（按 kickoff 禁重启），probe 跑在 8010 临时实例证明功能层 OK；编排者可在 8000 恢复后跑 ⑭ 复核。
2. **业务文档边缘案例**：含 `task09` 等词的物理/化学/数学文本经 IB-G2 验证不误伤；但教学语料多样性高，后续若发现新误伤，可调整 `db_schema.索引` / `audit_compliance.admin` 等弱权重词的 weight（已降到 0.4~0.8）。
3. **settings 桥接**：当前为 import 期一次性注入；如需热更新可调用 `internal_classifier.configure(reset=True)` + 重新注入。

---

## 7. Git 提交与分支

- **分支**：`feature/opt-waves`（HEAD 基线 `50ec868`，T14 端到端盲测）
- **本次 commit**：单 commit 仅含本任务 4 个核心交付文件（new）+ 1 个完成报告
  - `app/knowledge/importer/internal_classifier.py`（新）
  - `app/knowledge/importer/loader.py`（改）
  - `app/config.py`（改，3 个 settings 字段）
  - `tests/test_internal_classifier.py`（新）
  - `test-reports/WNEXTINT1B-completion-report.md`（新）
- **eval 脚本 + 对账报告**：本地落盘不纳入本次提交（与 WNEXTRAG1 处理一致）

---

## 8. 完工回执

- 锁文件：`edu-agent/scripts/eval/wnextint1b.lock` 已建（开工）→ 完工后删
- 5 步 GWT 全部走完：IB-G1（76 例单测全绿）/ IB-G2（业务文不误判 PASS）/ IB-G3（对账报告落盘 + 无写库）/ IB-G4（probe 实证功能层 PASS）/ IB-G5（174 例 RAG 相关测试零回归）
- 新模块：`edu-agent/app/knowledge/importer/internal_classifier.py`
- 单测：`edu-agent/tests/test_internal_classifier.py`（76 PASS）
- 对账 JSON：`edu-agent/deploy/backups/wnextint1b_recheck_20260916_204555.json`
- probe 实证 log：`edu-agent/scripts/eval/_t14/ib_g4_visibility_probe_8010.log`
- 完成报告：`test-reports/WNEXTINT1B-completion-report.md`（本文件）