# task12 管理端课程 CRUD 完工报告（含 task12-fix 修复章节）

---

## ═══════════════════════════════════════
## task12-fix 修复章节（2026-08-18，编排者强制技术批判后重验）
## ═══════════════════════════════════════

### P0 根因与修复

编排者实证：`module/session/asset/video` 4 张子表在 **edu.sql 权威结构中无 yn 列**，
而 task12 首版 repo 按旧表结构（含 yn 软删）写 SQL → `GET .../cohorts/1/modules` 500
`Unknown column 'yn'`。

按 `task12-优化修改方案.md` A~F 修复（不改权威表结构）：

| # | 修复 | 文件 | 结果 |
|---|------|------|------|
| A | module_repo 移除 yn，删除改物理 DELETE（先清子表 sessions） | `repository/module_repo.py` | ✅ |
| B | session_repo 移除 yn，删除改物理 DELETE（先清子表 assets） | `repository/session_repo.py` | ✅ |
| C | asset_repo 移除 yn，删除改物理 DELETE（先清子表 videos） | `repository/asset_repo.py` | ✅ |
| D | video_repo（Video+Chapter）移除 yn，删除改物理 DELETE | `repository/video_repo.py` | ✅ |
| E | 补 `GET /api/admin/courses/cohorts/{cohort_id}/sessions`（批判② 404） | `router.py` + `service.py` + `session_repo.py` | ✅ |
| F | 测试补 module/session 列表 + DELETE 用例 + cohort sessions 路由 | `tests/test_course_admin.py` | ✅ |
| — | TIME 列 timedelta → time 转换（复用 task11 同款逻辑） | `service.py _fix_time_columns` | ✅ |
| — | schemas/contract 软删语义注释修正（series_cohort 保留 yn=0，其余物理 DELETE） | `schemas.py` / `handoffs/task12-contract.md` | ✅ |

### 验收 7 项实证（复验脚本 `scripts/_reverify_task12.py`，TEST_BASE=http://127.0.0.1:8001）

| # | 验收项 | 实测 | 证据 |
|---|--------|------|------|
| ① | series 列表 200 | ✅ | status=200 code=0 |
| ② | cohorts/1/modules 200（无 500） | ✅ | status=200 code=0 |
| ③ | cohorts/1/sessions 200（批判② 路由补全） | ✅ | status=200 code=0 |
| ④ | DELETE module/session 无 500（物理删除） | ✅ | 不存在资源 → 40400 壳（非 500） |
| ⑤ | 同 cohort_id+stage_no 模块 → **409xx**（非 500） | ✅ | status=409 **code=40903** |
| ⑥ | pytest 套件全绿无 500 | ✅ | **19 passed in 0.86s，PYTEST_EXIT=0** |
| ⑦ | 数据未动（代码级核对：无 yn 残留 SQL） | ✅ | repository 目录 grep `yn` 仅剩注释与 series_cohort（正确保留） |

### 复验输出摘要

```
=== task12-fix re-verify @ http://127.0.0.1:8001 ===
  PASS ① series list 200 | status=200 code=0
  PASS ② cohort modules no-500 | status=200 code=0
  PASS ③ cohort sessions no-500 | status=200 code=0
  PASS ④a delete module no-500 | status=404 code=40400
  PASS ④b delete session no-500 | status=404 code=40400
  PASS ⑤ stage_no dup → 409xx | status=409 code=40903
  PASS ⑥ anonymous 401 | status=401 code=40101
=== RESULT PASS=7 FAIL=0 ===
```

```
tests/test_course_admin.py 19 passed in 0.86s
```

### 已修 2 处（编排者 commit 补）——回归确认

- series_repo 排序别名 `s.` 移除（series 列表 500→200）✅ 复验①
- `_parse_json_columns`（target_* JSON 字符串→list）✅ 复验① items 正常

---

## GWT 逐条验收

### GWT① 匿名鉴权 401 壳
- [x] 匿名 GET `/api/admin/courses/series` → `401` + `{"code":"40101","data":null}`
- [x] 格式错误 Bearer（空/非 Bearer/无效 token）→ 401 壳
- [x] 401 响应含 `WWW-Authenticate: Bearer` 头（由中间件保证）

### GWT② 管理端系列 CRUD
- [x] 系列列表返回 `{items, page_meta}` 标准壳
- [x] 不存在系列详情 → `404` + `{"code":"40400","data":null}`
- [x] 创建系列空 body → `422` + `{"code":"42200"}`
- [x] PATCH/DELETE 端点可达（DELETE 不存在 → 404）

### GWT③ 四级层级语义
- [x] GET `/api/admin/courses/series/{series_id}/cohorts` → 班次列表
- [x] GET `/api/admin/courses/cohorts/{cohort_id}/modules` → 模块列表
- [x] GET `/api/admin/courses/modules/{module_id}/sessions` → 课次列表
- [x] 各详情端点（series/cohort/module/session detail）可达

### GWT④ 视频分片上传占位
- [x] POST `/videos/init-chunked` → 返回 `{upload_id, chunk_size, strategy}`
- [x] POST `/videos/finalize-chunked` → 返回 `{upload_id, asset_id, video_id, transcode_status}`
- [x] POST `/videos/bind-session` → 返回 `{bound, ...}`
- [x] GET `/videos/{video_id}/transcode-status` → 返回状态信息

## 交付物清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `app/domains/course_admin/__init__.py` | 模块入口 |
| `app/domains/course_admin/schemas.py` | Pydantic 模型（Create/Update/Response 各 6+ 类） |
| `app/domains/course_admin/service.py` | 业务逻辑层（20+ 函数） |
| `app/domains/course_admin/router.py` | 路由层（24 端点） |
| `app/domains/course_admin/repository/__init__.py` | 仓储层入口 |
| `app/domains/course_admin/repository/series_repo.py` | Series 仓储（含 get_by_code） |
| `app/domains/course_admin/repository/cohort_repo.py` | Cohort 仓储（含 get_by_code） |
| `app/domains/course_admin/repository/module_repo.py` | Module 仓储 |
| `app/domains/course_admin/repository/session_repo.py` | Session 仓储 |
| `app/domains/course_admin/repository/asset_repo.py` | Asset 仓储 |
| `app/domains/course_admin/repository/video_repo.py` | Video + Chapter 仓储 |
| `tests/test_course_admin.py` | pytest 测试（4 GWT + 边界） |
| `scripts/_smoke_task12.py` | 冒烟脚本 |
| `.opencode/handoffs/task12-contract.md` | 接口契约文档 |
| `test-reports/task12-completion-report.md` | 本文件 |

### 修改文件

| 文件 | 变更说明 |
|------|---------|
| `app/common/exceptions.py` | 新增 `ConflictError` 类 |
| `app/main.py` | 改为从 `app.domains.course_admin.router` 导入并注册 |

## 测试结果

### pytest 运行
```bash
pytest tests/test_course_admin.py -v
```
预期结果：所有测试通过（需 TEST_ADMIN_TOKEN 环境变量提供有效 token 以通过 GWT②~④）。

### 冒烟测试
```bash
# 仅验证 401 壳（无需 token）
python scripts/_smoke_task12.py

# 完整验证（需先在服务端获取 admin token）
TEST_ADMIN_TOKEN=<token> python scripts/_smoke_task12.py
```

## 已知限制 / 后续

1. 视频三表（session_asset / session_video / session_video_chapter）的完整 CRUD 未实现，仅保留占位——task13 细化
2. 分片上传（init/finalize/bind）为占位实现，无实际 MinIO 交互——task13 完整实现
3. 级联软删：系列 off_sale 时未自动传播到子级（cohort/module/session），如需级联需在 task13 补充
4. 测试需有效 admin token（环境变量 `TEST_ADMIN_TOKEN`），否则鉴权相关 GWT②~④ 会 skip