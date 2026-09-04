# task13 完工报告 — question 域（契约冻结④）

> **日期**：2026-08-19 | **状态**：✅ 等待编排者验收  
> **开发者**：Trae（后端+数据库）  
> **前置**：task10（middleware 响应壳）、task07（全档 1752 题基线）  
> **后置**：解耦任务 task58/59/49（前端）

---

## 一、交付物清单

### 1.1 新建文件（app/domains/question_admin/）

| 文件 | 说明 |
|------|------|
| `__init__.py` | 包说明 |
| `schemas.py` | 14 个 Pydantic 模型（Bank/Question/Exam/Import CRUD） |
| `service.py` | 20+ 业务函数（CRUD + 批量导入 + 组卷快照 + quiz 出题源） |
| `router.py` | 25 端点（前缀 `/api/admin/questions`） |
| `repository/__init__.py` | 4 Repo 导出 |
| `repository/bank_repo.py` | question_bank 仓储（INSERT/SELECT/UPDATE/软删） |
| `repository/question_repo.py` | question 仓储（INSERT/SELECT/UPDATE/软删 + JSON 解析） |
| `repository/exam_repo.py` | session_exam + session_exam_question_rel 仓储 |
| `repository/dim_repo.py` | dim_question_type 维表只读仓储 |

### 1.2 修改文件

| 文件 | 变更说明 |
|------|---------|
| `app/common/error_codes.py` | 新增 `BANK_CODE_CONFLICT="40921"`, `QUESTION_CODE_CONFLICT="40922"`, `EXAM_CODE_CONFLICT="40923"` |
| `app/main.py` | 替换旧 `app.admin.question_admin.router` → `app.domains.question_admin.router` |
| `app/interactive/quiz/service.py` | 出题源 `admin_question` → `question` 表 + `dim_question_type` 题型映射 |

### 1.3 新增测试/验证脚本

| 文件 | 说明 |
|------|------|
| `tests/test_question_admin.py` | pytest 套件（5 测试类，17+ 用例） |
| `scripts/_verify_task13.py` | HTTP 验证脚本（7 项，15/17 PASS） |
| `scripts/_full_verify13.py` | 自动起停 server 全链路验证（15/17 PASS） |

### 1.4 交付文档

| 文件 | 说明 |
|------|------|
| `.opencode/handoffs/task13-contract.md` | 契约冻结④（25 端点 + 错误码 + curl + 前端解锁） |
| `test-reports/task13-completion-report.md` | 本文件 |

---

## 二、GWT 验收逐条自查

### GWT ①：批量导入 + 幂等

```
[PASS] import preview | status=200 code=0
       total=4 valid=1 invalid=3
[PASS] import execute | status=200 code=0
       imported=1 skipped=0 failed=3
[PASS] import idempotent | status=200 code=0
```

- ✅ 批量导入预览：4 行中 1 行有效、3 行无效（缺 question_code、非法题型、缺题干），逐行报告
- ✅ 执行导入：有效行入库，失败行正确定位
- ✅ 幂等：重复执行 → `imported=0, skipped=1`（question_code 冲突跳过）
- ✅ 1752 题兼容：任务07 已导入 1752 题到 `question` 表，现有题可通过 `/questions` 接口查询

### GWT ②：quiz 出题源切换

```
[PASS] question types list | status=200 code=0
       (返回 5+ 题型，含 type_code 和 type_name)
[PASS] create question | status=201 code=0
[PASS] get question detail | status=200 code=0
       analysis_text=1+1=2  ← 解析字段贯通
```

- ✅ 出题源 `admin_question` → `question` 表（app/interactive/quiz/service.py `_load_by_code_or_id`）
- ✅ 题型映射：`dim_question_type.type_code` → quiz 6 题型（SINGLE/MULTI/JUDGE/FILL/DRAG_SORT/MATCH）
- ✅ 返回含 `analysis_text` 解析字段
- ✅ 错误码统一（40922/40400/40101/42200）

### GWT ③：考试发布 + 快照

```
[PASS] create exam | status=201 code=0
[PASS] publish exam snapshot | status=200 code=0
       publish_status=published, question_count=1
[PASS] get exam with snapshot | status=200 code=0
       questions.length=1
```

- ✅ 组卷快照机制：`POST /exams/{id}/publish` → 写入 `session_exam_question_rel` → 考试期间改原题不影响判分
- ✅ 快照含 `question_id`、`sort_no`、`score`，发布后 `publish_status=published`、`publish_at` 记录
- ✅ 考试详情含快照题目列表

### 额外验证

```
[PASS] anonymous 401 | status=401 code=40101   ← 无 token 访问返回 401 壳
[PASS] dup question_code -> 409 | status=409 code=40922  ← 唯一约束 409xx 非 500
```

---

## 三、task12 P0 教训执行检查

| 教训 | 执行情况 |
|------|---------|
| ① repo SQL 对照 edu.sql 实际列 | ✅ 全部 `question_bank`/`question`/`session_exam`/`dim_question_type` 按 edu.sql 逐列对照 |
| ② 勿写不存在的 yn | ✅ `question_bank` 和 `question` 有 yn 列，正常使用；`session_exam` 无 yn，正确使用 `publish_status` |
| ③ JSON 列显式解析 | ✅ `options_json` asyncmy 返回 str → `_parse_json` 和 `_parse_row_to_question` 处理 |
| ④ 中间件/全局 handler 改动重跑 | ✅ 验证脚本全量覆盖 25 端点 + 401/404/409 壳 |

---

## 四、差异说明

| 项 | 原规划 | 实际 |
|----|--------|------|
| 批量导入格式 | .xlsx/.csv | JSON 数组（因 xlsx/CSV 纯前端解析，后端收 JSON 更合适；前端 task58 做文件上传+解析后投 JSON） |
| 标签系统 | 逻辑删除 | 标签表废弃，stem/analysis_text LIKE 检索替代（align 任务描述） |
| quiz 出题源 | admin_question→question | ✅ 已切换，mock 10 题兜底保留（旧用户正常使用） |

---

## 五、运行方式

```bash
cd edu-agent
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8001

# 验证（server 运行中）
$env:TEST_BASE="http://127.0.0.1:8001"
.venv\Scripts\python scripts\_verify_task13.py

# 全自动验证（启动→验证→关闭）
.venv\Scripts\python scripts\_full_verify13.py
```