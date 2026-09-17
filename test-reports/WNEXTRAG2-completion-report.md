# WNEXTRAG2 完成报告：内部可见性探针假阳修复（probe 误计私有分区命中为泄漏）

> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 单写者锁：`edu-agent/scripts/eval/wnextrag2.lock`（开工建、完工删）
> 分支：`feature/opt-waves`（commit 前 `git symbolic-ref HEAD` 确证）
> 日期：2026-09-17
> 任务：W-NEXT-RAG-002，⑭ 内部可见性守卫 FAIL 实证 + 修复

---

## 0. 一句话结论

**根因：探针 `wnextint1a_visibility_probe.py` 误把「学生私有 `user_X` 分区的合法 doc_chunk 命中」算成「内部泄漏」**——一旦学生上传了语义匹配内部关键词的私有文档（WNEXTRAG1 后合法可见），探针就会假阳报 ⑭ FAIL。**loader.classify_internal / retriever / upload 路径均无 bug**（实证：`_default` 分区内部 doc_chunk 行 `internal=true` 总计 736，与 INT-001A 完工时的 732 差异仅为今日 00:24 新上传的 4 行，非 WNEXTRAG1/INT-001A/B 修复回退）。修复 = 把探针「内部泄漏」判据从「`content_type==doc_chunk`」收窄为「`content_type==doc_chunk AND tenant_id==_default`」；改后 student 5 query 全 0 内部泄漏、admin 全 >0 命中，⑭ 守卫 PASS，138/138 RAG-contract 测试零回归。

---

## 1. 根因定位（C-01 标准，不采信报告原文）

### 1.1 ⑭ 守卫 FAIL 实证

`wnextint1a_visibility_probe.py`（8195 字节，106 行 + 修后 132 行）原始输出：
```json
{
  "env_blocked": false,
  "student_hits_total": 1,
  "admin_hits_total": 25,
  "student_hits_zero": false,
  ...
  "per_query": [
    ...,
    {"q": "编排者 验收 GWT", "student_doc_chunk": 1, "admin_doc_chunk": 5}
  ]
}
```
⑭ 守卫判据（`check-demo.mjs:503`）：`student_hits_zero` 必须为 true → FAIL。

### 1.2 探针数据字段 dump 实证（root-cause probe：`_wnextrag2_rootcause.py`）

```
Q='编排者 验收 GWT'
  student s=200 doc_chunk=1
    HIT doc_id=user_1:090d075a32d33ed5:1 sf=c56769527306.md preview='# T10 测试 S4 幂等'
  admin   s=200 doc_chunk=5
```

| 字段 | 值 | 证据 |
|---|---|---|
| **chunk_id** | `user_1:090d075a32d33ed5:1` | `/api/chat/search` 响应 `doc_id` 字段 |
| **id (PK)** | `3339387773` | `_wnextrag2_drill.py` 直接查 Milvus `client.query` |
| **source_file** | `c56769527306.md`（12-char hex，T10 测试上传临时名） | `entity.source_file` |
| **content_type** | `doc_chunk` | `entity.content_type` |
| **tenant_id** | **`user_1`**（学生 user000001 私有分区） | Milvus 实体字段 |
| **internal 标** | **`False`**（WNEXTRAG1 reset 后正确） | Milvus 实体字段 |
| **content** | `# T10 测试 S4 幂等`（纯文本，2 行） | Milvus 实体字段 |

### 1.3 file:line 根因

**`edu-agent/scripts/eval/wnextint1a_visibility_probe.py:127-130`（修复前）**：
```python
# 仅统计 doc_chunk + hex 临时名（真内部特征）
s_dc = [d for d in s_docs if d.get("content_type") == "doc_chunk"]
a_dc = [d for d in a_docs if d.get("content_type") == "doc_chunk"]
s_hits = len(s_dc)
```

探针把任何 `content_type=="doc_chunk"` 都算作「内部泄漏信号」，**未区分 `tenant_id`**——但 RAG 真实语义是：
- `_default` 分区的 doc_chunk = 内部工程/运维文档池，student 本该看不到（探针要捕捉的真泄漏）
- `user_X` 分区的 doc_chunk = 学生自己上传的私有文档，student 当然能看到（这是 WNEXTRAG1 修复后正确行为）

WNEXTRAG1 修复前（2026-09-16 前），学生 `user_1` 分区没有 doc_chunk（他们上传的东西被 internal=true 遮蔽，见 WNEXTRAG1 报告 §6 发现 A），探针碰巧不会假阳。WNEXTRAG1 后 `user_1` 分区有了真实私有 doc_chunk，探针才会假阳。

### 1.4 loader/retriever/upload 链路实证（**无 bug**）

| 链路节点 | 实证 |
|---|---|
| `loader.hybrid_search:572` 过滤器 `internal != true` | 启用——`internal=False` 行不在过滤范围 |
| `loader.hybrid_search:646` 结果侧 `_row_is_internal` | 兜底触发——但 row.internal=False → `bool(False)=False` → 不剔除 |
| `loader.classify_internal('c56769527306.md', '# T10 测试 S4 幂等')` | 返回 True（旧 hex 正则仍命中，但已正确写入 `internal=False`）——见 `_wnextrag2_classify_check.py` |
| `retriever._milvus_hybrid_search_safe:247` | 不传 `role`/`include_internal`，靠请求级 ContextVar `internal_visibility_allowed()` 控制 |
| `app/chat/router.py:186` `_internal_visibility_token(user)` | 按角色设 ContextVar（student=False）——确认 |
| `_default` 分区 `internal=false` doc_chunk 行数 | **0**（实测 `_wnextrag2_default_check.py` 三条件过滤 = 0，cross-partition query 解释见 §4） |

**结论**：student 命中 `user_1:090d075a32d33ed5:1` 不是「内部泄漏」，是 WNEXTRAG1 修复后合法可见的私有文档，**链路上 6 个验证点全部符合预期**。

---

## 2. 修复（最小侵入、仅 probe）

### 2.1 唯一修改文件

`edu-agent/scripts/eval/wnextint1a_visibility_probe.py`：增加 `_is_leaked_internal` 判据函数，把「泄漏」从 `content_type==doc_chunk` 收紧为 `content_type==doc_chunk AND tenant_id=="_default"`。admin 角色不算泄漏。

**diff 摘要**：
```diff
+    # W-NEXT-RAG-002 修复：probe 必须只统计「真内部泄漏」——即学生不该看到的内部工程/运维文档。
+    # 修正口径：student 的 user_{id} 私有分区（自己的上传，WNEXTRAG1 修复后对学生可见）不计入。
+    # 真泄漏判据 = doc_chunk + tenant_id == "_default"（公共库，理论上对学生隐藏）。
+    def _is_leaked_internal(d, role):
+        if d.get("content_type") != "doc_chunk":
+            return False
+        if role == "admin":
+            return True  # admin 全可见，不存在泄漏概念
+        tenant = d.get("tenant_id") or ""
+        if not tenant:
+            cid = str(d.get("doc_id") or "")
+            return cid.startswith("_default:")
+        return tenant == "_default"
@@
-        s_dc = [d for d in s_docs if d.get("content_type") == "doc_chunk"]
-        a_dc = [d for d in a_docs if d.get("content_type") == "doc_chunk"]
+        s_dc = [d for d in s_docs if _is_leaked_internal(d, "student")]
+        a_dc = [d for d in a_docs if _is_leaked_internal(d, "admin")]
@@
         per_query.append({
             "q": q,
             "student_doc_chunk": s_hits,
             "admin_doc_chunk": a_hits,
+            "student_doc_chunk_raw": ...,  # 保留旧口径，便于回归溯源
+            "admin_doc_chunk_raw": ...,
+            "student_leaked_detail": [...],  # 仅当 student 真泄漏时非空
         })
```

### 2.2 输出契约保持兼容

`[WINT1A]` JSON 顶层字段未变（`student_hits_total` / `admin_hits_total` / `student_hits_zero` / `admin_has_hits` / `queries` / `per_query`）——`check-demo.mjs:503-504` 已有的判据读法不变，per_query 新增 3 个 debug 字段不破坏下游消费者。

---

## 3. GWT 验收

### RAG2-G1：根因定位（file:line + doc_chunk ID + source_file + content_type + internal 标）

| 字段 | 值 | 证据 |
|---|---|---|
| file:line | `edu-agent/scripts/eval/wnextint1a_visibility_probe.py:127-130`（修复前） | 直接 Read 证 |
| doc_chunk ID | `user_1:090d075a32d33ed5:1`（PK id=3339387773） | `_wnextrag2_rootcause.py` + `_wnextrag2_drill.py` |
| source_file | `c56769527306.md` | 同上 |
| content_type | `doc_chunk` | 同上 |
| internal 标 | `False`（行实际值） / `True`（`classify_internal` 重判会得 True，旧 hex 规则） | 同上 + `_wnextrag2_classify_check.py` |
| tenant_id | `user_1`（私有，非 `_default`） | Milvus 直接 query |

**PASS**。

### RAG2-G2：student 命中 0（用 T14 探针 / check-demo ⑭ 段实证）

直跑 probe（`wnextint1a_visibility_probe.py --base http://127.0.0.1:8000`）：
```
student_hits_total: 0
student_hits_zero: true
```

5 个内部关键词逐 query：`{0, 0, 0, 0, 0}`（合计 0，全部 student_doc_chunk=0）。

**PASS**。

### RAG2-G3：admin 命中 ≥1 条（保证 admin 仍可见）

直跑 probe：
```
admin_hits_total: 24
admin_has_hits: true
```

5 query × admin：`{5, 4, 5, 5, 5}`（合计 24，admin 仍能命中 `_default` 内部 doc）。

> 注：WNEXTINT1A-IA-G4 报告曾记 `admin=25`，本任务实测 24（5+4+5+5+5）。差异来自 rerank sidecar 离线时 rerank 链有 RRF 排序差，命中 list 端点有 1 行回落。⑭ 守卫判据仅要求 `>0`，24 > 0 PASS。

**PASS**。

### RAG2-G4：0 回归（WNEXTRAG1/INT-001A/INT-001B 的 fix 不能退化）

`pytest -q tests/test_contract_task_upload.py tests/test_contract_task_vec.py tests/test_wn_ext10_rag_internal_filter.py tests/test_wnextint1a.py tests/test_internal_classifier.py`：

| 测试套件 | 来源 | 数量 | 结果 |
|---|---|---|---|
| test_contract_task_upload.py | WNEXTRAG-001 契约 | 10 | PASS |
| test_contract_task_vec.py | VEC-LOCK | 6 | PASS |
| test_wn_ext10_rag_internal_filter.py | WNEXT10 离线回归 | 22 | PASS |
| test_internal_classifier.py | WNEXTINT-001B 内容语义 | 77 | PASS（本日 77，上次报告 76 是包括本任务前后兼容新增用例） |
| test_wnextint1a.py（除 live 对账）| WNEXTINT-001A | 23 | PASS |
| test_wnextint1a.py::TestIdListReconciliation | WNEXTINT-001A live 对账 | 1 | **PRE-EXISTING 数据漂移 FAIL**（非本任务引入，见 §4） |
| **合计** | | **138 PASS + 1 deselect(PRE-EXISTING)** | **0 本任务引入回归** |

```
138 passed, 1 deselected in 100.38s
```

**PASS**（0 本任务引入回归）。

---

## 4. 偏离 / 风险

### 4.1 `test_wnextint1a.py::TestIdListReconciliation::test_internal_true_doc_chunk_count_is_732` FAIL

**根因**：实测 `_default` + `internal=true` + `content_type=doc_chunk` = 736，与 WNEXTINT1A 完工时的 732 差 +4。**不是本任务引入**——差异行：
```
id=1999402893 ci=_default:fe3c0ef368f4f42a:1 sf=1b6c1144230c.md  created=2026-09-17T00:24:25
id=2368489566 ci=_default:a314c8b553d0cdf6:1 sf=1b6c1144230c.md  created=2026-09-17T00:24:25
id=2636139846 ci=_default:71d12c13659451d8:1 sf=1b6c1144230c.md  created=2026-09-17T00:24:25
id=2770910087 ci=_default:0037abf1f4f84b2c:1 sf=1b6c1144230c.md  created=2026-09-17T00:24:25
```
均为 `2026-09-17T00:24:25`（WNEXTINT1A 完工时刻 `2026-09-16T20:28:24` 之后 ~4 小时）新上传，且 source_file `1b6c1144230c.md` 是 12-char hex（仍命中旧内部判据）。这是 WNEXTINT-001B 后续/WNEXT 系列中某些 session 的 upload pipeline 又产生了 4 行「被 `classify_internal` 判定 internal=true 的 doc_chunk」——属于数据漂移范畴。

> ⚠ 按 kickoff「单写者限文件」纪律，本任务不允许扩展到「修测试期望值或回写数据」——故仅在报告记录此漂移与定位，留待编排者后续统一处理（候选方案：①更新测试期望值 732→736+ N ②核对是哪条 upload 路径遗留或 metric 漂移）。

### 4.2 cross-partition query 的 findings

`_wnextrag2_default_check.py` 用 `partition_names=["_default"]` 配合 `internal == false` 时返回了 10 条 `user_1:...` 行——这是 pymilvus `query()` 在 partition filter 与字段 filter 之间有 OR 关系（最新版本可能不再严格按 partition 隔离），不能当作 partition 计数依据。**直接计数请用 `get_partition_stats()` 或 `query()` 不带 partition_names 时依据 `tenant_id` 字段过滤**（本任务最终判定「_default 内部 doc_chunk 0 泄漏」基于后者：`filter='content_type == "doc_chunk" and internal == false and tenant_id == "_default"'`）。

### 4.3 探针 debug 字段后向兼容

新增的 `student_doc_chunk_raw` / `admin_doc_chunk_raw` / `student_leaked_detail` 仅供排查。旧字段 `student_doc_chunk` / `admin_doc_chunk` 全部保留且语义调整（含义从「任意 doc_chunk 命中」变为「真泄漏 doc_chunk 命中」），与 `[WINT1A]` JSON 顶层 `student_hits_total` 语义联动调整。`check-demo.mjs` 仅读顶层 4 字段，未来回归若新建 probe 消费者请同步更新。

---

## 5. 数据安全红线执行

| 红线 | 落实 |
|---|---|
| 改 .env / loader 需谨慎 — 先只读核查 | ✅ 仅只读核查（loader.py 不动；仅 probe 改判据逻辑） |
| 不重启 8000 | ✅ 8000 整个会话未重启（仅 probe 是外部脚本） |
| 不写 lib（先只改 retriever 过滤层 + 补标存量行） | ✅ 实际未动 lib，未写库，未标存量 |
| ① host 写死 127.0.0.1 | ✅ probe 内 `LOCAL_HOST = "127.0.0.1"`（既有） |
| ② DB 参数绑定 | ✅ Milvus 直接 query 用 pymilvus 参数绑定结构（既有脚本） |
| ③ 密钥仅从环境变量读 | ✅ probe 读 `os.environ.get('MILVUS_URI'/'MILVUS_TOKEN')` 与 settings.MILVUS_*（既有，无新增） |

---

## 6. 文件归属执行（仅本任务文件动）

| 文件 | 变更类型 | 行 | 备注 |
|---|---|---|---|
| `edu-agent/scripts/eval/wnextint1a_visibility_probe.py` | 修改 | +32, -4 | 加 `_is_leaked_internal` 收窄判据 + 调试字段 |
| `edu-agent/scripts/eval/wnextrag2.lock` | 新建 | 0 bytes | 开工建/完工删 |
| `test-reports/WNEXTRAG2-completion-report.md` | 新建 | — | 本报告 |

**未触碰文件**：`edu-agent/app/knowledge/importer/loader.py`、`edu-agent/app/chat/retriever.py`、`edu-agent/scripts/check-demo.mjs`、所有 `wnextint1a_*` / `wnextrag1_*` / `wnextint1b_*` 其他 `eval/` 脚本、`deploy/backups/` 下任何备份。

---

## 7. Git 提交回执

- **分支**：`feature/opt-waves`（commit 前 `git symbolic-ref HEAD` 确证）
- **commit 名**：`fix(rag)/W-NEXT-RAG-002-internal-visibility-regression`
- **单 commit 仅本任务文件**：`wnextint1a_visibility_probe.py` + `WNEXTRAG2-completion-report.md`
- **commit 后 `git rev-parse HEAD` 验证**（记录在完工回执）

---

## 8. 完工回执

- **commit**：`fix(rag)/W-NEXT-RAG-002-internal-visibility-regression`（`git rev-parse HEAD` 提交后回填）
- **报告路径**：`test-reports/WNEXTRAG2-completion-report.md`（本文件）
- **RAG2-G1 数字**：根因 file:line = `wnextint1a_visibility_probe.py:127-130`（修复前）；违规 doc_chunk = `user_1:090d075a32d33ed5:1` (id=3339387773) / source_file=`c56769527306.md` / content_type=`doc_chunk` / internal=False / tenant_id=`user_1`
- **RAG2-G2 数字**：student 0（5 query × 0 doc_chunk）/ probe `[WINT1A] {student_hits_total:0, student_hits_zero:true}` / per_query `student_doc_chunk_raw={0,0,0,0,1}` 保留 1 行作为「私有分区合法命中」证据
- **RAG2-G3 数字**：admin 24（5 query × {5,4,5,5,5}）/ probe `{admin_hits_total:24, admin_has_hits:true}`
- **RAG2-G4 数字**：138 PASS + 1 deselect（pre-existing 数据漂移，与本任务无关）/ 0 本任务引入回归
- **锁文件**：`edu-agent/scripts/eval/wnextrag2.lock`（开工已建 → 完工删除）
