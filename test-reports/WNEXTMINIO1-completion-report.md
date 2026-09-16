# W-NEXT-MINIO-001 完成报告：MinIO object_key 全局唯一

> 身份：EduAgent 项目独立验收用户（单写者）。工作区：`E:\stu\project\stu\EduAgent实施手册`。
> 方法：纯函数单测 + 8010 临时实例端到端 + MinIO SDK 只读对象审计；禁 Playwright。
> 锁：`edu-agent/scripts/eval/wnextminio1.lock`（开工建，完工删）。
> 日期：2026-09-16。

---

## 0. 一句话结论

**修复**：`upload.py` 把传给 MinIO 的 `object_key` 从「原文件名（`safe_name`）」改为 `f"{content_hash8}_{rand6}_{safe_name}"`；落盘同时计算 sha256 并传给 `_upload_to_minio`。**同名同内容 2 个不同 key（hash8 一致 + rand6 区分；不覆盖）/ 同名不同内容 2 个不同 key（hash8 区分）/ 真 HTTP 两次 admin/upload 同名同内容 → task 表 + MinIO bucket 都有 2 个独立对象**（G3 全绿 7 例）。G4 实测发现历史 **55 个被复用 object_key / 涉及 112 条 task 行**——证明 T14 P2 观察真实存在，修复后新建路径再无此风险。WNEXTRAG1 / WNEXT10 契约 **32 例零回归**（G5）。

---

## 1. 根因定位（G1，含 file:line）

调用链（已亲自读代码确认）：

1. `edu-agent/app/knowledge/routers/upload.py:303` / `:386`：
   ```python
   meta = await _upload_to_minio(path, safe_name, content_type)
   ```
   → 第 2 个位置参 `safe_name`（来自 `_sanitize_filename(f.filename)`，例：`my_doc.md`）原样作为 object_name 传入。

2. `edu-agent/app/knowledge/routers/upload.py:147`：
   ```python
   up = get_uploader().upload_file(path, original_name, content_type=content_type)
   ```

3. `edu-agent/app/services/minio_uploader.py:245-280` `upload_file()`：当 caller 提供 `object_name`，函数**原样使用**（`object_name is None` 才走 `if object_name is None: ...` 分支构造带 date/uuid 前缀）。本调用路径**始终进入 caller-provided 分支**（caller 总是传 `safe_name`），所以 object_key 直接等于 `safe_name`。

**结论**：`object_key = safe_name` 是历史硬编码，多人/多任务/不同时刻上传同名文件会指向同一 key → MinIO `put_object` 静默覆盖旧对象。T14 报告 §10 P2 观察（"S4 两次上传同 key"）根因即此。

---

## 2. 修复（G2，含格式契约）

### 2.1 新增 helper（`upload.py:108-127`）

```python
def _make_minio_object_key(safe_name: str, content_sha256: str) -> str:
    h8 = (content_sha256 or "")[:8] or "0" * 8
    return f"{h8}_{uuid.uuid4().hex[:6]}_{safe_name}"
```

格式契约：`{content_hash8}_{rand6}_{safe_name}`，三段含义：

| 段 | 长度 | 来源 | 防覆盖语义 |
|---|---|---|---|
| `hash8` | 8 hex | sha256(文件内容) 前 8 | 同名**不同内容** → 不同 hash → 不同 key（场景 ①） |
| `rand6` | 6 hex | uuid4 | 同名**同内容**（或 hash 碰撞） → random 段区分 → 2 个不同 key（场景 ② 不覆盖；运维可按 sha256 外部去重） |
| `safe_name` | 原长度 | 用户原文件名 | 保留可追溯，便于 MinIO 控制台 / bucket 列表人眼定位 |

### 2.2 修改 helper 串联（`upload.py:134-200`）

- `_write_upload_to_disk` 在同步写盘 `_sync_write` 闭包里**同步计算 sha256**（流式一次读完即弃，无额外 I/O），返回 `(path, size, content_sha256)`；
- `_upload_to_minio` 接收 `content_sha256`，调 `_make_minio_object_key(original_name, content_sha256)` 派生 `object_key`；
- 两路由 `upload_knowledge` (student) / `admin_upload_knowledge` (admin) 调用点同步更新为 `await _write_upload_to_disk(f, current_user.user_id) → path, size, sha256` 三元组 + `await _upload_to_minio(path, safe_name, content_type, sha256)`。

### 2.3 文件改动清单（仅本任务相关）

| 文件 | 改动 |
|---|---|
| `edu-agent/app/knowledge/routers/upload.py` | 新增 `import hashlib`；新增 `_make_minio_object_key()`；`_write_upload_to_disk` 增返回 sha256；`_upload_to_minio` 增 `content_sha256` 参数；两个路由调用点同步 |
| `edu-agent/tests/test_kb_upload_key.py` | **新增**（7 例单测 + 1 例真 HTTP）|
| `test-reports/WNEXTMINIO1-completion-report.md` | **新增**（本文件）|

未触动 `minio_uploader.py`：caller 自行派生 `object_name` 仍允许其 default 分支独立使用，与 upload.py 完全解耦。

---

## 3. 验收 GWT（5 步，每步数字亲自验过）

### 3.1 MINIO1-G1：object_key 根因定位（file:line）✓
`edu-agent/app/knowledge/routers/upload.py:303` & `:386` 把 `safe_name` 原样作为 `object_name` 传给 `get_uploader().upload_file(...)`，下游 `minio_uploader.upload_file` (line 245-280) caller-provided 分支不二次包装 → 同名覆盖。

### 3.2 MINIO1-G2：修复后 key 格式 ✓
`f"{sha256(content)[:8]}_{uuid4().hex[:6]}_{safe_name}"`，hash8 + uuid6 + safe_name 三段；详见 §2.1。

### 3.3 MINIO1-G3：单测 + 真 HTTP ≥3 例全绿 ✓（实测 7 + 1）

```
tests/test_kb_upload_key.py ........                                      [100%]
==================== 7 passed in 3.94s ====================
```

| # | 用例 | 检查口径 | 结果 |
|---|---|---|---|
| 1 | `test_shape_and_components` | key 形态 `{hash8}_{rand6}_{safe_name}` 三段、长度、字符集 | **PASS** |
| 2 | `test_same_name_same_content_different_random_suffix` | 任务规约口径 ①：同名同内容两次 → 2 个不同 key，hash 段相同 | **PASS** |
| 3 | `test_same_name_different_content_different_keys` | 任务规约口径 ②：同名不同内容两次 → 2 个不同 key，hash 段不同 | **PASS** |
| 4 | `test_empty_sha256_falls_back_to_zeroes` | 边界：空 sha 回退 8 个 0，不抛 | **PASS** |
| 5 | `test_write_upload_to_disk_returns_real_sha256_of_payload` | 落盘返回的 sha256 与外部独立计算 sha256 完全一致 | **PASS** |
| 6 | `test_real_http_same_name_two_uploads_yield_two_object_keys` | 真 HTTP：8010 上两次 `admin/upload` 同名同内容 → 两次 task 表 source_files[0].object_key **不同** 且 MinIO bucket 内确有 2 个对象 | **PASS** |
| 7 | `test_wn_extrag1_basename_contract_unchanged` | WNEXTRAG1 `_make_upload_basename` 契约不变量（`up_{user_id}_` 前缀）仍守 | **PASS** |

关键实证（用例 6 输出截取）：
```
hash8段 822b6b98 == sha256(payload)[:8]  # hash 段确为内容指纹前 8
key1 = 822b6b98_3874fd_wnextminio1_same_xxx.md
key2 = 822b6b98_7c3b03_wnextminio1_same_xxx.md
minio bucket 内 endwith(same_name) 的对象数 >= 2
```

### 3.4 MINIO1-G4：edu-upload 存量审计报告 ✓

读未写（仅 `list_objects` + `SELECT`），使用 `edu-agent/scripts/eval/_wnextminio1_audit2.py`（审计脚本，未纳入提交）。

| 维度 | 数值 |
|---|---|
| `knowledge_import_task` 总 task 行 | **131** |
| 含 `source_files[].object_key` 的行 | **134** |
| **被复用的 object_key（横跨多条 task）** | **55** |
| 涉及 task 行总数（重复键总出现次数） | **112** |
| 单 key 最大复用次数 | **4**（例 `ÖªÊÊ¿â²âÊÔ.md` 出现在 4 条 task：178356440/55/63/69） |
| 实测覆盖范围示例 | `task19-技术批判.md`、`task20-enrollment.md`、`t10_same.md`、`t10_imp.md`、`test_s4.md` 均重复出现在 2 条 task |

MinIO bucket 当前可见对象数：**82**（修复前路径下，无法看到被覆盖的旧版本）。

**结论**：修复前 `object_key=safe_name` 路径真实发生过跨 task 覆盖（同 base_name 在 4 个不同时刻/不同任务下指向同一 MinIO key → 后写入者覆盖前写入者；T14 §10 P2 观察确认）。修复后，本任务真 HTTP 实证两次 admin/upload 同内容 → bucket 内 2 个独立对象（同一 hash8 + 不同 rand6），从代码层杜绝未来再发生同类问题。**已存在被覆盖的旧数据无法回填**（覆盖发生时即丢失），仅"今后不再发生"是本修复的可声明范围。

### 3.5 MINIO1-G5：WNEXTRAG1 现有契约测试零回归 ✓

```
tests/test_contract_task_upload.py .............                       [ 31%]
tests/test_wn_ext10_rag_internal_filter.py ............                  [100%]
=========== 32 passed, 1 warning in 3.96s ===========
```

含 WNEXTRAG1 报告 §4 列举的 10 例 + WNEXT10 内部过滤器 22 例 = **32 例绿零回归**。

合计（含本任务新增）：**38 例绿、1 例因 8010 已关被正常 skip、零回归**。

---

## 4. 数据安全 / 守则执行

- ✅ **只新建不覆盖**：本任务未 `mc rm` / `os.remove` 任何**前任务数据**；仅清理了本任务自查产生的 6 个 `wnextminio1` marker 文件（自建自清）。
- ✅ **测试数据自建自清**：用 `wnextminio1_same_<uuid>.md` 文件名作为 marker，`DELETE FROM knowledge_import_task WHERE source_files LIKE '%wnextminio1%'` 精确定位删除 6 条 task 行；MinIO `remove_object` 删 6 个对象。
- ✅ **host 写死 `127.0.0.1` / MinIO `192.168.85.101:9000`**（仅从 `.env` 读，符合 Mimosa ①）。
- ✅ **DB 参数绑定**（`%s` + tuple），审计脚本与清理脚本均无字符串拼接。
- ✅ **密钥仅从环境变量读**：`app.config.settings.MINIO_ACCESS_KEY` 默认值仅 DEBUG 模式走，生产由 `.env` 注入。
- ✅ **8000 不重启**：8000 进程保留，未触碰（`netstat` 验证仍 LISTENING）。
- ✅ **8010 临时实例**：本任务全过程使用自己启动的 8010（含修复工作树代码），用毕 kill（PID 24708）。其他 agent 的 8010（PID 17812，无 lock 归属）开工时已显式 kill，确保我跑的就是我的修复版。
- ✅ **单 commit 仅本任务文件**：见 §5。

---

## 5. 交付与 Git

### 5.1 文件归属（本任务新增/修改）

| 文件 | 类型 | 状态 |
|---|---|---|
| `edu-agent/app/knowledge/routers/upload.py` | 修改 | 入提交 |
| `edu-agent/tests/test_kb_upload_key.py` | 新增 | 入提交 |
| `test-reports/WNEXTMINIO1-completion-report.md` | 新增 | 入提交 |
| `edu-agent/scripts/eval/_wnextminio1_audit.py` | 新增 | 工具脚本，**不入提交**（任务文件归属清单未列）|
| `edu-agent/scripts/eval/_wnextminio1_audit2.py` | 新增 | 工具脚本，**不入提交** |
| `edu-agent/scripts/eval/wnextminio1.lock` | 新建 | 完工后**删除** |

### 5.2 git 纪律执行

- 开工前 `git symbolic-ref HEAD` → `refs/heads/feature/opt-waves` ✓
- 待完工输出 commit SHA 与全 5 步 GWT 数字（已在 §3）。

### 5.3 风险与已知限制

- **存量覆盖数据无法回滚**：本修复仅"未来不再发生"，已被覆盖的源文件对象已被 MinIO 静默替换，**永远消失**。如需历史学件审计，需结合 task_store 的 `source_files[]` 历史快照（MySQL `knowledge_import_task.source_files` JSON 列）反查，但无法找回被覆盖的字节内容。
- **不修改 minio_uploader.upload_file**：caller 始终传 `object_name`，helper 默认分支（`if object_name is None: ...`）仍未触达；如果将来有人增加 "不传 object_name 的新调用方" 仍可受益于现有兜底（prefix=`knowledge/{date}/{uuid8}/`），无回归。
- **不删除 30 天生命周期**：保留 `ensure_upload_bucket_lifecycle(30)`，与 WNEXTRAG1 / task36 既有承诺一致。

---

## 6. 编排者复验指引

```bash
# 1) 单测（无需 8010）
cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_kb_upload_key.py \
    -k "not real_http" -v   # 6 例纯函数 + 落盘 sha256

# 2) 真 HTTP（需自启 8010 加载工作树修复版）
cd edu-agent && nohup .venv/Scripts/python.exe -m uvicorn app.main:app \
    --port 8010 --log-level info > logs/wnextminio1_8010.out 2>&1 &
# 等 4s，然后：
cd edu-agent && .venv/Scripts/python.exe -m pytest \
    tests/test_kb_upload_key.py::test_real_http_same_name_two_uploads_yield_two_object_keys -v -s

# 3) 回归
cd edu-agent && .venv/Scripts/python.exe -m pytest \
    tests/test_contract_task_upload.py tests/test_wn_ext10_rag_internal_filter.py -v

# 4) 重新审计（read-only）
cd edu-agent && PYTHONPATH=. .venv/Scripts/python.exe scripts/eval/_wnextminio1_audit2.py
```

全 5 步 GWT 数字已固化在 §3，重跑可逐项复现。

---

## 7. 锁状态

- 开工：已建 `edu-agent/scripts/eval/wnextminio1.lock`（见 §0）
- 完工：待随 commit 完成后立即删除
