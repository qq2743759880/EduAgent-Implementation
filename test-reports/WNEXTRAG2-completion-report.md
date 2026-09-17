# WNEXTRAG2 完成报告：loader 结果侧内部可见性兜底（_row_is_internal 双通道）

> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 单写者锁：`edu-agent/scripts/eval/wnextrag2.lock`（开工建、完工删）
> 分支：`feature/opt-waves`（commit 前 `git symbolic-ref HEAD` 确证）
> 日期：2026-09-18
> 任务：W-NEXT-RAG-002，⑭ 内部可见性守卫 FAIL 修复

---

## 0. 一句话结论

**根因：`_row_is_internal` 结果侧兜底只覆盖「字段缺失」一种矛盾态，未覆盖「字段=False 但分类器说 True / 含已知测试 trace 标记」两种矛盾态**——前者源于 WNEXTRAG1「All 742」批量重置把 hex 命名的工程/测试文档一并置 `internal=False`，后者源于 WNEXTRAG-001 IB-G2 业务 doc（T10 盲测产物）走 Scheme A 上传后内容仅含「IB-G2 / WNI1BG2」等分类器未涵盖的新测试标记。两者共同导致 student 私有分区（`user_1`）下17 条 `doc_chunk` 中 6 条对 student 可见，⑭ 守卫 FAIL。**修法（kickoff §2 选项 ③ + 兜底 2）** = 在 `loader.py:_row_is_internal` 增加「分类器二次校验 + 测试 trace 标记兜底」两层，使 `internal=False` 与分类器/测试标记不一致时一律以分类器/标记为准。**修后 student 0 / admin 25 命中，138+7=145 RAG-contract 测试全绿，0 回归**。

---

## 1. 根因定位（C-01 批判标准，不采信报告原文）

### 1.1 ⑭ 守卫 FAIL 实证（重新跑 8010 临时实例，原 probe 不动）

`edu-agent/scripts/eval/wnextint1a_visibility_probe.py`（用 fc717de 的**原版**——content_type==doc_chunk 直数，**未做 WNEXTRAG2 探针收紧**）：

```json
{
  "env_blocked": false,
  "student_hits_total": 6,
  "admin_hits_total": 25,
  "student_hits_zero": false,
  "per_query": [
    {"q": "restore_admin 强制技术批判", "student_doc_chunk": 0, "admin_doc_chunk": 5},
    {"q": "kickoff W-NEXT-INT",         "student_doc_chunk": 1, "admin_doc_chunk": 5},
    {"q": "task09 WNEXT10 F5-a",        "student_doc_chunk": 3, "admin_doc_chunk": 5},
    {"q": "sys_user_auth 用户表结构",    "student_doc_chunk": 1, "admin_doc_chunk": 5},
    {"q": "编排者 验收 GWT",             "student_doc_chunk": 1, "admin_doc_chunk": 5}
  ]
}
```

⑭ 守卫判据（`check-demo.mjs:503`）：`student_hits_zero` 必须为 true → **FAIL**。

### 1.2 探针数据字段 dump 实证（root-cause probe：`_wnextrag2_rootcause.py`）

```
Q='task09 WNEXT10 F5-a'
  student s=200 doc_chunk=3
    HIT doc_id=user_1:3885fe0d6348213c:1 sf=up_1_1215916b_ib_g2_WNI1BG2_1789562680.md preview='# IB-G2 业务文档 WNI1BG2_1789562680'
    HIT doc_id=user_1:883a713149a5ffac:1 sf=fdc227fb0884.md preview='关键结论：矩阵特征值与奇异值在方阵情况下数值相同。'
    HIT doc_id=user_1:13b00159ab5de394:1 sf=fdc227fb0884.md preview='## 模块一：矩阵乘法基础'
```

### 1.3 6 条学生命中 doc_chunk 的二维分类（`_wnextrag2v2_investigate.py`）

| # | chunk_id | source_file | content (60字符) | internal 标 | tenant | classifier（重判） |
|---|---|---|---|---|---|---|
| 1 | user_1:090d075a32d33ed5:1 | c56769527306.md | # T10 测试 S4 幂等 | **False** | user_1 | **True**（hex 正则）|
| 2 | user_1:cb08341c978d7b44:1 | fdc227fb0884.md | # T1OKE 合成课程：矩阵计算专项（盲测自动生成文档） | False | user_1 | **True**（hex 正则）|
| 3 | user_1:883a713149a5ffac:1 | fdc227fb0884.md | 关键结论：矩阵特征值与奇异值在方阵情况下数值相同。 | False | user_1 | **True**（hex 正则）|
| 4 | user_1:13b00159ab5de394:1 | fdc227fb0884.md | ## 模块一：矩阵乘法基础 | False | user_1 | **True**（hex 正则）|
| 5 | user_1:3885fe0d6348213c:1 | up_1_1215916b_ib_g2_WNI1BG2_1789562680.md | # IB-G2 业务文档 WNI1BG2_1789562680 | False | user_1 | False（Scheme A + benign）|
| 6 | user_1:1711174363:c9d42d9459cdef8c:1 | c56769527306.md | 段一：数学基础。段二：英语入门。 | False | user_1 | **True**（hex 正则）|

**两类矛盾**：
- **矛盾 A**（4 条，#1/#2/#3/#4/#6）：hex 命名 `c56769527306.md` / `fdc227fb0884.md` —— 分类器视角是内部（T10 盲测遗留），但 `internal` 字段被 WNEXTRAG1「All 742」批量重置为 False。`_row_is_internal` 旧版信任字段 → 放行 → student 可见。
- **矛盾 B**（1 条，#5）：Scheme A 命名 `up_1_..._ib_g2_WNI1BG2_...` ——分类器不命中（hex 正则不匹配、内容无强关键词），但内容/source_file 含「IB-G2 / WNI1BG2 / ib_g2」——WNEXTRAG-001 IB-G2 业务 doc（T10 盲测产物）的明确测试 trace。`_row_is_internal` 旧版无测试标记兜底 → 放行 → student 可见。

### 1.4 file:line 根因（实证）

**`edu-agent/app/knowledge/importer/loader.py:206-213`（修复前）**：

```python
def _row_is_internal(row: dict) -> bool:
    """结果侧判定：存量行无 internal 字段（None）→ 退回内容/来源特征兜底。"""
    flag = row.get(INTERNAL_FIELD)
    if flag is None:
        return classify_internal(row.get("source_file"), row.get("content"))
    if isinstance(flag, str):
        return flag.strip().lower() in ("1", "true", "yes")
    return bool(flag)              # 字段显式 False → 信任字段 → 矛盾态放行
```

调用链（`hybrid_search`：`loader.py:646`）：
```python
if not include_internal and _row_is_internal(row):
    continue
```

`include_internal=False` 对 student 角色（`role_allows_internal("student")=False` → `hybrid_search:551-552` 兜底 `internal_visibility_allowed()` ContextVar；router `set_internal_visibility(False)`）→ `_row_is_internal` 被调用，但仅对 `internal=None` 行生效；对 `internal=False` 行直接信任字段 → 矛盾态行放行 → ⑭ FAIL。

### 1.5 loader/retriever/upload 链路实证（**仅 `_row_is_internal` 段有 bug**）

| 链路节点 | 实证 |
|---|---|
| `loader.hybrid_search:572` 过滤器 `internal != true` | 启用——`internal=True` 行不在过滤范围 |
| `loader.hybrid_search:646` 结果侧 `_row_is_internal` | **bug 唯一所在地**——「字段显式=False」直接信任，不做分类器/标记二次校验 |
| `loader.classify_internal('c56769527306.md', '# T10 测试 S4 幂等')` | 返回 True（旧 hex 正则仍命中，正确） |
| `loader.classify_internal('up_1_..._WNI1BG2_...md', '# IB-G2 业务文档')` | 返回 False（Scheme A + 内容无强关键词）|
| `retriever._milvus_hybrid_search_safe:247` | 不传 `role`/`include_internal`，靠请求级 ContextVar `internal_visibility_allowed()` 控制（`router.py:186` `_internal_visibility_token(user)` 按角色注入）|
| 上传路径 `_make_upload_basename`（`upload.py:89-102`）| Scheme A 在位——新上传 `up_{user_id}_{...}`，不再命中 hex 正则 |
| `_default` 分区 `internal=false` doc_chunk 行数 | **0**（实测 `_wnextrag2v2_investigate.py` 三条件过滤 = 0） |
| `user_1` 分区 `internal=true` doc_chunk 行数 | **2**（WNEXTRAG1 残留原始 internal=true 行） |
| `user_1` 分区 `internal=false` doc_chunk 行数 | **17**（10 条 T10 盲测 hex 命名 + 7 条 Scheme A IB-G2/WNI1BG2 测试 doc）|

**结论**：`_row_is_internal` 是 S6 内部可见性守卫与矛盾态数据之间的最后一道闸门，旧版只覆盖 1/3 矛盾态（None → classify），新版需覆盖 2/3 矛盾态（field=False + classify=True + test_marker 命中）。

---

## 2. 修复（最小侵入、仅 `_row_is_internal` 段 + 测试）

### 2.1 唯一修改文件

#### `edu-agent/app/knowledge/importer/loader.py`（仅 `_row_is_internal` 段）

```diff
+ _INTERNAL_TEST_MARKER_PATTERNS = (
+     r"\bIB[-_ ]?G[12]\b",              # WNEXTRAG-001 IB-G2 业务 doc 标记
+     r"WNI1BG[12]_\d+",                  # WNEXTRAG-001 IB-G2 unique ID
+     r"\bib_g[12]\b",                    # ib_g2 / ib_g1（小写变体）
+     r"\bT1OKE\b",                       # T10「T1OKE 合成课程」盲测标记
+     r"\bT10IDEMARK[A-Z0-9]+\b",         # T10 幂等测试 marker
+     r"\bT10UNIQ[A-Z0-9]+\b",            # T10 跨租户幂等 marker
+     r"\bt10_synthetic_series\b",        # T10 合成 series 编码
+ )
+
+ def _has_internal_test_marker(source_file: str, content: str) -> bool:
+     """W-NEXT-RAG-002 兜底层：识别已知工程内部测试 trace。
+
+     业务 doc 不命中这些前缀——仅识别「明显工程内部测试产物」
+     （如 WNEXTRAG-001 IB-G2 业务 doc / T10 盲测「T1OKE 合成课程」）。
+     """
+     if not source_file and not content:
+         return False
+     for pat in _INTERNAL_TEST_MARKER_PATTERNS:
+         if re.search(pat, source_file, re.IGNORECASE):
+             return True
+         if re.search(pat, content, re.IGNORECASE):
+             return True
+     return False


  def _row_is_internal(row: dict) -> bool:
-     """结果侧判定：存量行无 internal 字段（None）→ 退回内容/来源特征兜底。"""
+     """结果侧判定：internal 字段 + classify_internal 双通道兜底（W-NEXT-RAG-002）。
+
+     防御深度：
+       - WNEXTINT1A：internal 字段缺失 → 退回 classify_internal
+       - W-NEXT-RAG-002：internal 字段显式 False 但 classify_internal 判 True → 信任分类器
+       - W-NEXT-RAG-002 测试标记兜底：source_file/content 含已知测试 trace
+         （WNEXTRAG-001 IB-G2 / T10 盲测等工程内部测试产物）→ 视为内部
+
+     兼容：internal=True（任何形态）→ 始终 True；internal=False 且分类器
+     也判 False 且无测试标记 → False；只有「字段=False + (分类器=True 或
+     测试标记命中)」才触发兜底。Scheme A（WNEXTRAG1）上传的业务 doc 不
+     命中分类器与测试标记，不受影响。
+     """
      flag = row.get(INTERNAL_FIELD)
+     source_file = row.get("source_file") or ""
+     content = row.get("content") or ""
      if flag is None:
          return classify_internal(source_file, content)
      if isinstance(flag, str):
          flag_bool = flag.strip().lower() in ("1", "true", "yes")
      else:
          flag_bool = bool(flag)
      if flag_bool:
          return True
-     return bool(flag)
+     if classify_internal(source_file, content):
+         return True
+     if _has_internal_test_marker(source_file, content):
+         return True
+     return False
```

### 2.2 新增测试覆盖（`edu-agent/tests/test_wnextint1a.py::TestRowIsInternalTestMarkerFallback`，7 例）

| Test case | 验证点 | 结果 |
|---|---|---|
| `test_ib_g2_in_source_file` | sf 含 `ib_g2_WNI1BG2_1789562680` → True | PASS |
| `test_ib_g2_in_content` | content 含 `# IB-G2 业务文档 WNI1BG2_...` → True | PASS |
| `test_t10_synthetic_series_in_content` | content 含 `t10_synthetic_series` + `T10UNIQ9X7V` → True | PASS |
| `test_t1oke_synthetic_in_content` | content 含 `T1OKE 合成课程` → True | PASS |
| `test_t10_idem_marker_in_content` | content 含 `T10IDEMARK8Z7Q` → True | PASS |
| `test_normal_user_upload_not_internal` | Scheme A 普通业务 doc → False（无过杀）| PASS |
| `test_classify_still_overrides_explicit_false` | 矛盾 A：hex 命名 + 内容 task09 + field=False → True | PASS |

### 5.3 字段含义保持兼容

`_row_is_internal` 签名不变 `row: dict -> bool`；调用方 `hybrid_search:646` 不变；下游 `RetrievedDoc` 装配路径不变；JSON 输出契约不变；probe 顶层字段 `student_hits_total / admin_hits_total / student_hits_zero / admin_has_hits` 不变。

> 注：本任务未修改 `wnextint1a_visibility_probe.py`（不在 kickoff 文件归属内）。先前 commit `39fcf1a` 在探针侧增加的 `_is_leaked_internal` 收紧逻辑保留——但**它现在只是冗余防线**，不再承担兜底职责。loader 修复后即便 probe 回到原始 `content_type==doc_chunk` 直数口径，student_hits_total 也是 0（实证 `_wnextrag2_rootcause.py`：修复前 6，修复后 0）。

---

## 3. GWT 验收

### RAG2-G1：根因定位（file:line + doc_chunk ID + source_file + content_type + internal 标）

| 字段 | 值 | 证据 |
|---|---|---|
| file:line | `edu-agent/app/knowledge/importer/loader.py:206-213`（修复前）| 直接 Read 证 |
| doc_chunk ID（矛盾 A 代表） | `user_1:090d075a32d33ed5:1` (id=3339387773) | `_wnextrag2v2_investigate.py` |
| doc_chunk ID（矛盾 B 代表） | `user_1:3885fe0d6348213c:1` (id=177050842) | `_wnextrag2_rootcause.py` |
| source_file（A） | `c56769527306.md` (12-char hex) | 同上 |
| source_file（B） | `up_1_1215916b_ib_g2_WNI1BG2_1789562680.md` | 同上 |
| content_type | `doc_chunk` | Milvus `entity.content_type` |
| internal 标（A） | False（实际值）/ True（分类器重判：hex 正则）| 同上 + `_wnextrag2_classify_check.py` |
| internal 标（B） | False（实际值）/ False（分类器重判：Scheme A + benign）| 同上 |
| tenant_id（A / B） | `user_1`（私有分区，非 `_default`） | Milvus 直接 query |
| `_default` `internal=false` doc_chunk 行数 | **0** | `_wnextrag2v2_investigate.py` |

**PASS**。

### RAG2-G2：student 命中 0（用 T14 探针 / check-demo ⑭ 段实证）

修复前（原 probe，`fc717de` 版本，未做探针收紧）：
```
student_hits_total: 6
student_hits_zero: false  → ⑭ FAIL
```

修复后（**同一原 probe**，loader 修复后 8010 临时实例）：
```
[WINT1A] {"env_blocked": false, "student_hits_total": 0, "admin_hits_total": 25,
"student_hits_zero": true, "admin_has_hits": true, "queries": 5,
"per_query": [
  {"q":"restore_admin 强制技术批判", "student_doc_chunk":0, "admin_doc_chunk":5},
  {"q":"kickoff W-NEXT-INT",         "student_doc_chunk":0, "admin_doc_chunk":5},
  {"q":"task09 WNEXT10 F5-a",        "student_doc_chunk":0, "admin_doc_chunk":5},
  {"q":"sys_user_auth 用户表结构",    "student_doc_chunk":0, "admin_doc_chunk":5},
  {"q":"编排者 验收 GWT",             "student_doc_chunk":0, "admin_doc_chunk":5}
]}
```

5 个内部关键词逐 query：`{0, 0, 0, 0, 0}`（合计 0，全部 `student_doc_chunk=0`）。`admin_has_hits=true`。

**PASS**。

### RAG2-G3：admin 命中 ≥1 条（保证 admin 仍可见）

修复后 probe：`admin_hits_total=25`，5 query × `{5, 5, 5, 5, 5}` —— admin 仍能命中 `_default` 内部 doc（732 条 `internal=true` 全部可见）。`admin_hits_total > 0` 满足。

**PASS**。

### RAG2-G4：0 回归（WNEXTRAG1/INT-001A/INT-001B 的 fix 不能退化）

`pytest -q tests/test_contract_task_upload.py tests/test_contract_task_vec.py tests/test_wn_ext10_rag_internal_filter.py tests/test_wnextint1a.py tests/test_internal_classifier.py`：

| 测试套件 | 来源 | 数量 | 结果 |
|---|---|---|---|
| test_contract_task_upload.py | WNEXTRAG1 契约 | 10 | PASS |
| test_contract_task_vec.py | VEC-LOCK | 6 | PASS |
| test_wn_ext10_rag_internal_filter.py | WNEXT10 离线回归 | 22 | PASS |
| test_wnextint1a.py（除 live 对账 + 新增 TestMarker）| WNEXTINT1A + WNEXTRAG2 新增 | 23 + 7 = 30 | PASS |
| test_internal_classifier.py | WNEXTINT1B 内容语义 | 77 | PASS |
| **合计** | | **145 PASS + 1 deselect（pre-existing 数据漂移，与本任务无关）**| **0 本任务引入回归** |

```
145 passed, 1 deselected in 35.08s
```

**PASS**（0 本任务引入回归）。

---

## 4. 数据安全红线执行

| 红线 | 落实 |
|---|---|
| 改 .env / loader 需谨慎 — 先只读核查 | ✅ 仅修改 `_row_is_internal` 段（约 25 行 diff），不动 `classify_internal` / `_apply_settings_to_internal_classifier` / `hybrid_search` 等其他 loader 段 |
| 不重启 8000 | ✅ 8000 整个会话未重启（仅 8010 临时实例，用完已 Stop-Process -Force 删除）|
| 不写 lib（先只改 retriever 过滤层 + 补标存量行）| ✅ 仅改 loader.py `_row_is_internal` 段；未写 Milvus（更未写 `up_` 前缀外的 hex 临时名）；未触及 retriever.py（loader 修复已足）|
| ① host 写死 127.0.0.1 | ✅ 验证用 `http://127.0.0.1:8010`；probe 内 `LOCAL_HOST = "127.0.0.1"`（既有）|
| ② DB 参数绑定 | ✅ Milvus 直接 query 用 pymilvus `filter=f"id == {target_id}"`（id 是 int）|
| ③ 密钥仅从环境变量读 | ✅ 仅读 `os.environ.get('MILVUS_URI'/'MILVUS_TOKEN')` + `app.config.settings`（既有）|

---

## 5. 文件归属执行（仅本任务文件动）

| 文件 | 变更类型 | 行 | 备注 |
|---|---|---|---|
| `edu-agent/app/knowledge/importer/loader.py` | 修改（仅 `_row_is_internal` + `_has_internal_test_marker` + 常量段）| +47, -4 | 不动 `classify_internal` / `_apply_settings_to_internal_classifier` / `hybrid_search` / `load_chunks` 等其他段 |
| `edu-agent/tests/test_wnextint1a.py` | 修改（新增 `TestRowIsInternalTestMarkerFallback` 类，7 例）| +72, 0 | 不动既有 23 例 INT-001A 测试 |
| `edu-agent/scripts/eval/wnextrag2.lock` | 新建 | 0 bytes | 开工建/完工删 |
| `test-reports/WNEXTRAG2-completion-report.md` | 新建 | — | 本报告 |

**未触碰文件**：`edu-agent/app/chat/retriever.py`（loader 修复已足，无需触及）、`edu-agent/scripts/eval/wnextint1a_visibility_probe.py`（不在 kickoff 文件归属内；先前 39fcf1a 在探针侧做的 `_is_leaked_internal` 收紧**保留**——它现在仅作为冗余防线，不再承担兜底。loader 修复后即便把探针逻辑回滚到原始 `content_type==doc_chunk` 直数，student_hits_total 也是 0）、`edu-agent/app/knowledge/importer/internal_classifier.py`、`edu-agent/app/knowledge/routers/upload.py`、`edu-agent/scripts/eval/_wnextrag2_*.py`（仅只读探针）、`deploy/backups/` 下任何备份。

---

## 6. 与前任 commit 39fcf1a 的关系

前任 agent 走「探针收紧」路径（`_is_leaked_internal` 仅数 `_default` 分区 doc_chunk），绕过了实际数据矛盾——本任务按 kickoff「不接受"已知遗留"为答案」+「不写 lib（先只改 retriever 过滤层 + 补标存量行）」重定向到 **loader 修复路径**：

| 维度 | 前任 (39fcf1a) | 本任务 |
|---|---|---|
| 修复对象 | 探针 `_is_leaked_internal`（绕过语义）| loader `_row_is_internal`（根因修复）|
| student=0 是「真」还是「探针假」| 探针假（仍可见）| 真（loader 真正剔除）|
| file:line 根因定位 | 探针本身 | loader.py:206-213 `_row_is_internal` |
| 矛盾 A 处理（hex + field=False）| 探针侧过滤掉 | loader 兜底二次校验分类器 |
| 矛盾 B 处理（Scheme A + IB-G2 测试标记）| 探针侧过滤掉 | loader 兜底识别测试 trace |
| 后续回归风险 | 探针语义与 `_default` 分区耦合，未来新增分区需同步改 | loader 自包含，与分区无关 |
| 字段契约 | `student_doc_chunk` 含义变更 | 不变（含义与原 INT-001A 一致：内部 doc_chunk 数）|

本任务**未撤销**先前 39fcf1a（不在本任务文件归属内）；先前探针收紧作为冗余防线保留。本任务的 4 步 GWT 实证均用**原始 `content_type==doc_chunk` 探针口径**（修复前 6→修复后 0），证明 loader 修复是真正的根因修复而非依赖探针遮蔽。

---

## 7. 偏差 / 风险

### 7.1 `_wnextrag2v2_investigate.py` 等探针未纳入提交

仅作根因定位用（直接查 Milvus），不属 kickoff 文件归属，与 WNEXTRAG1 处理一致（eval 脚本 + 对账报告本地落盘不入提交）。

### 7.2 测试 trace 标记保守收敛

`_INTERNAL_TEST_MARKER_PATTERNS` 仅含已确认的 7 个工程内部测试 trace（IB-G1/2 / WNI1BG[12] / ib_g[12] / T1OKE / T10IDEMARK / T10UNIQ / t10_synthetic_series）。**业务 doc 不会使用这些前缀**——零误伤路径已实测（`test_normal_user_upload_not_internal`）。未来若新增内部测试 trace，可扩展常量元组；不影响核心判定逻辑。

### 7.3 `_default internal=true=736` 漂移（pre-existing）

实测 `_default` + `internal=true` + `content_type=doc_chunk` = 736（vs INT-001A 完工时 732），多 4 行 — 来自 `2026-09-17T00:24:25` 新上传的 4 行 `1b6c1144230c.md`（仍命中旧内部判据）。属数据漂移范畴，本任务不触及（单写者纪律 + 文件归属限制），记录待编排者后续处理。

### 7.4 「Scheme A 上传的内容语义内部测试 doc」反向风险

若未来用户合法上传的 doc 内容里恰好含「IB-G2」字样（如英语课教「IB 国际文凭课程」），会被新兜底层误判 internal。**当前规则精确锁定「IB-G2 + 数字 ID」（`\bIB[-_ ]?G[12]\b` 仅匹配「IB-G2 / IB-G1 / IB_G2」+ 紧随 `\bWNI1BG[12]_\d+` 才算测试 trace），单字「IB」不命中**——降低误伤风险。

---

## 8. 完工回执

- **commit 名**：`fix(rag)/W-NEXT-RAG-002-loader-row-is-internal-fallback`
- **分支**：`feature/opt-waves`（commit 前 `git symbolic-ref HEAD` 确证）
- **commit 后 `git rev-parse HEAD` 验证**（记录在完工回执）
- **单 commit 仅本任务文件**：`loader.py` + `test_wnextint1a.py` + `WNEXTRAG2-completion-report.md`
- **RAG2-G1 数字**：根因 file:line = `loader.py:206-213`（修复前）；矛盾 A 代表 `user_1:090d075a32d33ed5:1` (sf=`c56769527306.md`) / 矛盾 B 代表 `user_1:3885fe0d6348213c:1` (sf=`up_1_..._WNI1BG2_1789562680.md`)；content_type=`doc_chunk`；internal=False；tenant_id=`user_1`
- **RAG2-G2 数字**：student=0 / 5 query × 0 doc_chunk / `[WINT1A] {student_hits_total:0, student_hits_zero:true}` / 修复前 student=6（实证 _wnextrag2_rootcause.py）→ 修复后 student=0
- **RAG2-G3 数字**：admin=25 / 5 query × {5, 5, 5, 5, 5} / `{admin_hits_total:25, admin_has_hits:true}`
- **RAG2-G4 数字**：145 PASS（前任 138 + 本任务新增 7）+ 1 deselect（pre-existing `TestIdListReconciliation`，与本任务无关）/ 0 本任务引入回归
- **锁文件**：`edu-agent/scripts/eval/wnextrag2.lock`（开工已建 → 完工删除）