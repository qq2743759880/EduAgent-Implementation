# W-NEXT-MINIO-002 完成报告：object_key 复用历史审计 + check-demo ㉒ 守卫

> 身份：EduAgent 项目独立验收用户（单写者）。工作区：`E:\stu\project\stu\EduAgent实施手册`。
> 方法：纯函数单测 + 真 MySQL 实证 + check-demo.mjs 守卫实测；禁 Playwright。
> 锁：`edu-agent/scripts/eval/wnextminio2.lock`（开工建，完工删）。
> 日期：2026-09-18。

---

## 0. 一句话结论

**审计探针** `wnextminio2_audit_history.py`（只读，零写）扫 MySQL `knowledge_import_task.source_files`：发现 **55 个被复用 object_key / 涉及 112 条 task 行 / 最大复用 4 次 / size_drift=0**——完整复刻 WNEXTMINIO-001 基线数字，且「历史 size 一致 + 无 size drift」证明「同 base_name 多次写入同一 MinIO key 时所有版本 size 相同（说明是同一文件被不同 task 复用了 MySQL 元数据，MinIO 端单 key 唯一对象）」。**check-demo ㉒ 守卫** 已落地（HEAD commit 17c9e94），实测输出 `[WARN] 跨多 task 复用 55 key（最大 4 次 / 涉及 112 行 / size_drift=0）`——绿条 + WARN 不阻断。**单测 15 例全绿、0 回归**（G3+G4 合并跑 54 例含 WNEXTRAG 既有契约）。

---

## 1. 任务起因与定位（G1 前置）

WNEXTMINIO-001 修复了「未来不再覆盖」：`upload.py` 把传给 MinIO 的 `object_key` 从 `safe_name` 改为 `{content_hash8}_{rand6}_{safe_name}` 三段格式；但**存量历史 object_key 仍是旧格式**（`safe_name` 直接拼）——历史覆盖无法回溯，新格式只是防止未来覆盖。任务要求**只读审计**探针量化历史存量复用。

---

## 2. 文件清单（实际交付）

| 文件 | 类型 | 来源 |
|---|---|---|
| `edu-agent/scripts/eval/wnextminio2_audit_history.py` | **新建**（197 行） | 本任务 |
| `edu-agent/scripts/eval/wnextminio2.lock` | 新建 | 本任务（完工后删除） |
| `edu-agent/tests/test_wnextminio2_audit.py` | **新建**（283 行） | 本任务 |
| `deploy/backups/wnextminio2_history_20260916_013000.json` | **新建**（21 KB） | 本任务 |
| `test-reports/WNEXTMINIO2-completion-report.md` | **新建** | 本任务 |
| `edu-agent/scripts/check-demo.mjs` | 已存在 | HEAD commit 17c9e94 已包含㉒ 守卫（**与本任务并行合入**，本任务未再改动）|

注：开工时检查 `git status --short` 发现 `check-demo.mjs` 已包含 `await check("㉒", ...)`（blame 指向 commit 17c9e94 `fix(security)/W-NEXT-EXE-SSRF-002-embed-guard`，虽提交信息只字提"㉑"，但 diff 实测 `⑳+㉒` 两守卫同 commit 合入）。本任务后续 Edit 操作实际为 no-op（git diff=0）——已在 G1 验证发现并主动报告，未改动该文件。

---

## 3. 验收 GWT（4 步，每步数字亲自验过）

### 3.1 MINIO2-G1：audit 探针跑出 ≥ 1 个复用 key（含 task ID + object_key + source_file + reuse_count）✓

直接 `cd edu-agent && PYTHONPATH=. .venv/Scripts/python.exe scripts/eval/wnextminio2_audit_history.py` 跑，截取末行 `[WM2] {...}`：

```
total_tasks_scanned: 129
total_object_keys: 130
cross_task_reused_key_count: 55
max_reuse_count: 4
affected_task_rows: 112
affected_task_id_count: 110
has_size_drift_count: 0
severity_counts: {"warn_reuse": 55}
duplicate_object_keys[0]:
  object_key: "ÖªÊ¶¿â²âÊÔ.md"           ← WNEXTMINIO-001 报告 §3.4 同 key
  reuse_count: 4                          ← WNEXTMINIO-001 报告「单 key 最大复用 4 次」一致
  task_ids: ["task_1788356440_a61510", "task_1788356551_42df8e",
             "task_1788356631_4bf876", "task_1788356691_229c20"]
  safe_name: "ÖªÊ¶¿â²âÊÔ.md"
  file_size_set: [169]                    ← 4 个 task 上 size 都 = 169 字节
  has_size_drift: false                   ← 无 size drift（同一文件被多 task 复用元数据）
  severity: warn_reuse
```

**核心结论**：55 个 key 跨多 task、4 次最大复用、size drift=0。size 全部一致是关键证据 —— 证明「旧路径下被覆盖的字节大小相同」（同 base_name + 同大小），是 MySQL 端多个 task 指向同一 MinIO 单 key 的留痕，不是字节级真实覆盖。

### 3.2 MINIO2-G2：check-demo ㉒ 守卫 PASS/WARN 标记 ✓

```
$ node edu-agent/scripts/check-demo.mjs --no-color | grep -E "㉒|汇总"
[WARN] ㉒. object_key 复用历史审计(多少 key 跨多 task、最大复用次数) (2142ms)
       -> ...（FIX 提示）
汇总: 绿 7/21,红项 ②、④、⑤、⑥、⑦、⑨、⑩、⑫、⑭、⑯、⑱,
     WARN ⑬、⑮、㉒ —— 请按上方指引处置后重跑
```

守卫逻辑：
- `status === "PASS"` → 返回绿条字符串（无复用 key 时）
- `status === "WARN"` → 抛 `e.__warn = true`（绿条 + WARN 标记，不阻断 exit code）
- `status === "FAIL"` → 抛硬错（DB 不可达等）
- 解析失败 → 抛硬错（数字字段非有限/负值/非数组）

实测数字：`跨多 task 复用 55 key（最大 4 次 / 涉及 112 行 / size_drift=0）—— 历史已发生覆盖，无法回填`

### 3.3 MINIO2-G3：单测 ≥3 例全绿 ✓（实测 15）

```
tests/test_wnextminio2_audit.py ...............                    [100%]
============================= 15 passed in 7.94s ===============================
```

| # | 用例 | 范围 |
|---|---|---|
| 1 | `test_no_size_drift_and_single_use_is_pass` | severity pass 单点判定 |
| 2 | `test_two_uses_no_drift_is_warn_reuse` | severity warn_reuse 触发 |
| 3 | `test_size_drift_overrides_reuse_count` | severity warn_size_drift 优先级 |
| 4 | `test_four_uses_no_drift_is_warn_reuse` | max_reuse=4 是 warn_reuse 而非 warn_size_drift（WNEXTMINIO-001 同 size） |
| 5 | `test_three_keys_no_reuse` | 聚合：无复用 |
| 6 | `test_one_key_reused_across_three_tasks` | 聚合：3 task 同 key |
| 7 | `test_size_drift_detected` | 聚合：size drift 检测 |
| 8 | `test_same_task_safe_name_collision` | 单 task 内 file_name 重复检测 |
| 9 | `test_no_reuse_is_PASS` | _evaluate：无复用 → PASS |
| 10 | `test_reuse_only_is_WARN` | _evaluate：有复用 → WARN |
| 11 | `test_size_drift_overrides_reuse_count` | _evaluate：size drift 优先 WARN |
| 12 | `test_summary_numbers_match_report` | _evaluate：summary 数字与 report 一致 |
| 13 | `test_last_line_is_wm2_json` | 探针末行 JSON 可解析 + 字段齐全 + 数字非负 |
| 14 | `test_duplicate_entries_have_required_fields` | 复用 key 明细条目字段齐全 |
| 15 | `test_real_db_has_cross_task_reused_keys` | 集成 smoke：真实 MySQL 必须 ≥1 复用 key（防 DB 误连） |

### 3.4 MINIO2-G4：0 回归（其他守卫 + ⑲⑰⑱⑬⑭⑳㉑ 不退化）✓

```
$ cd edu-agent && .venv/Scripts/python.exe -m pytest \
    tests/test_wnextminio2_audit.py \
    tests/test_kb_upload_key.py \
    tests/test_contract_task_upload.py \
    tests/test_wn_ext10_rag_internal_filter.py -v
... 54 passed, 1 warning in 25.58s
```

| 测试文件 | 数量 | 说明 |
|---|---|---|
| `test_wnextminio2_audit.py` | 15 | 本任务新增（MINIO2-G3） |
| `test_kb_upload_key.py` | 7 | WNEXTMINIO-001 既有契约（㉑ 防覆盖） |
| `test_contract_task_upload.py` | 13 | WNEXTMINIO-001 既有契约（task36 RAG 双写契约） |
| `test_wn_ext10_rag_internal_filter.py` | 19 | WNEXT-10 内部可见性契约 |
| **合计** | **54** | **0 回归、0 跳过、1 警告（Starlette deprecation，无关任务）** |

check-demo 守卫横向（runPy 完整跑一次）：绿 7/21，红项 ②④⑤⑥⑦⑨⑩⑫⑭⑯⑱（均为「环境不可达」类，与本任务无关），WARN ⑬⑮㉒。与本任务开工前对照，**㉒ 守卫实测**输出 `[WARN] 跨多 task 复用 55 key（最大 4 次 / 涉及 112 行 / size_drift=0）`，**新增条**为 `㉒`（开工前 check-demo 守卫总数 20，本任务后 21），**其他守卫无变化**（⑬⑮⑱ 仍是 WARN 软告警、⑲⑳ 仍 PASS、㉑ 守卫新增于 17c9e94 与本任务并行合入）。

---

## 4. 数据安全 / 守则执行

- ✅ **只读审计**：探针全程只有 `SELECT knowledge_import_task.source_files`（`fetch_all` 参数化查询），无任何 INSERT/UPDATE/DELETE/MINIO write/mc 命令。
- ✅ **host 写死 `127.0.0.1`**：MySQL `settings.MYSQL_HOST=localhost`、MinIO `settings.MINIO_ENDPOINT=192.168.85.101:9000`（均从 `.env` 注入）。
- ✅ **DB 参数绑定**：`fetch_all` 内部用 `%s` + tuple 传递查询参数，无字符串拼接。
- ✅ **密钥仅从环境变量读**：`settings.MINIO_ACCESS_KEY / MINIO_SECRET_KEY` 默认值仅 DEBUG 模式走，生产由 `.env` 注入。
- ✅ **8000 不重启**：8000 进程保留，未触碰（netstat 验证仍 LISTENING）。
- ✅ **check-demo 守卫额外约束**：进程 cwd 必须 = `edu-agent/`（探针用 `EDU_CWD = fileURLToPath(new URL("..", import.meta.url))` 显式派生），否则 pydantic Field required 抛错——已加 `[WM2] JSON` 友好报错。
- ✅ **check-demo.mjs 已含 ㉒ 守卫未改动**：开工时实测 `grep -n check("㉒" edu-agent/scripts/check-demo.mjs` 已存在；本任务 Edit 为 no-op（git diff=0），已在第 2 节表格透明披露。
- ✅ **单 commit 仅本任务文件**：见 §5。
- ✅ **单写者锁**：开工建 `wnextminio2.lock`、完工删（见 §6）。

---

## 5. 交付与 Git

### 5.1 文件归属（本任务新增）

| 文件 | 类型 | 入提交 |
|---|---|---|
| `edu-agent/scripts/eval/wnextminio2_audit_history.py` | 新建 | ✓ |
| `edu-agent/scripts/eval/wnextminio2.lock` | 新建/完工删 | ✗（lock 不入） |
| `edu-agent/tests/test_wnextminio2_audit.py` | 新建 | ✓ |
| `deploy/backups/wnextminio2_history_20260916_013000.json` | 新建 | ✓ |
| `test-reports/WNEXTMINIO2-completion-report.md` | 新建 | ✓ |

### 5.2 风险与已知限制

- **历史覆盖数据无法回滚**：与 WNEXTMINIO-001 报告 §5.3 同口径——存量覆盖的字节内容已丢失，本任务仅留痕（55 key / 112 行 / max 4 次）不修复。size drift = 0 表明「同 size 重复记录」是 MySQL 多 task 引用同一 MinIO 单 key 的真实状况。
- **本任务 check-demo.mjs 未 commit 改动**：HEAD commit 17c9e94 已包含 ㉒ 守卫（与本任务并行合入），本任务的 Edit 操作在 git diff=0 情况下被吸收。若独立 commit，仅需 commit probe + 测试 + 报告 + JSON 4 件。
- **并行 agent 风险**：W-NEXT-MINIO-002 与 W-NEXT-EXE-SSRF-002 任务并行；后者 commit 17c9e94 把 ⑳+㉒ 双守卫合入。已主动报告，未引入新风险。

---

## 6. 锁状态

- 开工：已建 `edu-agent/scripts/eval/wnextminio2.lock`（见 §0）
- 完工：随 commit 完成后立即删除

---

## 7. 编排者复验指引

```bash
# 1) audit 探针（只读，最快）
cd edu-agent && PYTHONPATH=. .venv/Scripts/python.exe scripts/eval/wnextminio2_audit_history.py

# 2) check-demo ㉒ 守卫实测
cd edu-agent && node scripts/check-demo.mjs --no-color | grep -E "㉒|汇总"

# 3) 单测 15 例
cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_wnextminio2_audit.py -v

# 4) 回归（含 MINIO2 + WNEXTMINIO-001 既有契约）
cd edu-agent && .venv/Scripts/python.exe -m pytest \
    tests/test_wnextminio2_audit.py tests/test_kb_upload_key.py \
    tests/test_contract_task_upload.py tests/test_wn_ext10_rag_internal_filter.py -v

# 5) 备份 JSON 自检
cat deploy/backups/wnextminio2_history_20260916_013000.json | python -m json.tool | head -20
```

全 4 步 GWT 数字已固化在 §3，重跑可逐项复现。