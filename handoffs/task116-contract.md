# 契约冻结单 C-C · task116 — 系列删除语义 + 孤儿模块归档

> 状态：**FROZEN（冻结）** ｜ 类型：A 级资产任务产出 ｜ 域：后端 + 数据库
> 关联开工单：task116（EduAgent 优化期 W2 · 系列删除语义 + 孤儿模块归档）
> 实证端口：独立隔离 Windows 端口 **8077**（后端 8000 为编排者托管旧实例，详见 §0 验证约束）
> 全部请求/响应均来自真实 HTTP 实测（见 `edu-agent/test-reports/task116_gwt_evidence.json`，8077 端口新代码）。

---

## §0 验证约束（必读）

- 后端 **8000** 由编排者（WSL2）托管，**运行旧代码且本环境无法重启**（wsl.exe 被安全策略禁用、cmd.exe 被命令校验拦截、Git-Bash/PowerShell 均无法见到该进程）。OpenAPI 显证：8000 的 `DELETE /api/admin/courses/series/{id}` 仅含 `series_id` 参数、`GET` 列表无 `include_deleted`。
- 本任务的新代码在**隔离 Windows 端口 8077** 启动独立 uvicorn 实测：OpenAPI 显证 `DELETE` 含 `['series_id','hard']`、`GET` 列表含 `include_deleted`。
- 故：所有"真实输出"证据均取自 8077 实测；8000 旧实例未改动、未重启、未触碰分支、未 commit（遵守开工单硬性守则）。

---

## §1 Route Spec — `DELETE /api/admin/courses/series/{series_id}`

- **Method**: `DELETE`
- **Path**: `/api/admin/courses/series/{series_id}`
- **Auth / RBAC**: `require_role([ADMIN, MANAGER])` 路由级依赖（course_admin 路由）；`hard=true` 额外要求 `me.role == ADMIN`（manager 调用 `hard` 返回 **403**）。
- **Request parameters**:
  - `series_id`：路径参数（int，必填）
  - `hard`：`bool = Query(False)`，仅 ADMIN 可用；`True` = 物理真删（零引用时），`False/缺省` = 软删下架。

### 1.1 双路径语义

| 路径 | 条件 | 行为 | 响应 message |
|---|---|---|---|
| 软删（默认） | `hard` 缺省或 `false` | `series.sale_status = 'off_sale'`（**不物理删除**，series 表无 `yn` 列） | `系列已下架` |
| 真删 | `hard=true` 且 **零引用** | `DELETE FROM series WHERE id = %s` | `系列已彻底删除` |
| 真删被拒 | `hard=true` 且 **存在引用**（班次/订单，含已软删班次） | 抛 `ConflictError(40908)`，**绝不静默** | `系列仍被 N 个班次（含已下架）、M 笔订单引用，无法彻底删除` |
| 真删越权 | `hard=true` 且 `me.role != ADMIN` | 抛 `PermissionDeniedError(40300)` | `真删操作仅 SUPER ADMIN 可执行` |

- **软删口径依据**：series 表无 `yn` 列（edu.sql 权威），故软删以 `sale_status='off_sale'` 状态机表达，与前端"下架"文案一致，消除"假删除"缺陷（开工单 D3）。
- **硬规则**：禁止为 series 新增 `yn` 列；真删前置 FK 校验必须显式报错码，**绝对禁止**因残留外键导致 500 静默（已用 try/except 兜底转 409）。

### 1.2 真实请求/响应（8077 实测）

**① 软删下架（默认）**
```http
DELETE /api/admin/courses/series/2644
→ 200 {"code":0,"message":"系列已下架","data":null}
```
随后 `GET /api/admin/courses/series/2644` 仍 `200`，`data.sale_status == "off_sale"`（记录保留）。

**② 真删（零引用）**
```http
DELETE /api/admin/courses/series/2645?hard=true
→ 200 {"code":0,"message":"系列已彻底删除","data":null}
```
随后 `GET /api/admin/courses/series/2645` → `404 {"code":"40400","message":"系列不存在：2645","data":null}`（物理消失）。

**③ 真删被拒（存在引用：1 个班次，含已下架）**
```http
DELETE /api/admin/courses/series/2647?hard=true
→ 409 {"code":"40908","message":"系列仍被 1 个班次（含已下架）、0 笔订单引用，无法彻底删除","data":null}
```
> 关键：FK 计数**包含 `yn=0` 的软删班次行**（FK 仍绑定），避免 `physical_delete` 触发 500。

**④ 真删越权（manager 角色）**
```http
DELETE /api/admin/courses/series/2646?hard=true
→ 403 {"code":"40300","message":"真删操作仅 SUPER ADMIN 可执行","data":null}
```

### 1.3 错误码

| code | HTTP | 触发 | 是否静默 |
|---|---|---|---|
| `0` | 200 | 成功 | — |
| `40400` | 404 | 系列不存在（软删/真删前 `get_by_id` 校验） | 否 |
| `40908` | 409 | 真删存在引用（FRIENDLY：明确中文原因） | **否** |
| `40300` | 403 | 非 ADMIN 调用 `hard=true` | 否 |

---

## §2 Route Spec — `GET /api/admin/courses/series`（列表过滤）

- **Method**: `GET` ｜ **Path**: `/api/admin/courses/series`
- **新增 Query 参数**：`include_deleted: bool = Query(False, 回收站用)`
- **默认行为（不传）**：**过滤已下架系列**（`WHERE sale_status != 'off_sale'`），即软删记录不出现在常规管理列表。
- **`include_deleted=true`**：不过滤 off_sale，返回含已下架系列（回收站视图）。
- 响应壳与分页**不变**：`{code:0, message:"ok", data:{items:[...], page_meta:{page,page_size,total,total_pages,has_more}}}`。

### 2.1 真实请求/响应（8077 实测，差异即软删过滤证据）

```http
GET /api/admin/courses/series
→ 200 {"code":0,"message":"ok","data":{"items":[...],"page_meta":{"total":2629,...}}}
```
```http
GET /api/admin/courses/series?include_deleted=true
→ 200 {"code":0,"message":"ok","data":{"items":[...],"page_meta":{"total":2640,...}}}
```
> `total` 相差 11 == 当前 `off_sale` 数量的差值，实证默认列表已正确剔除软删系列。

---

## §3 删除语义一致性核对（item ③，差异如实记录）

| 资源 | 删除语义 | 依据 | 与 series 是否一致 |
|---|---|---|---|
| **series** | 软删 = `sale_status='off_sale'`（无 `yn` 列） | edu.sql：series 表无 yn | 基准 |
| **cohort（班次）** | 软删 = `yn=0`（`UPDATE ... SET yn=0`） | `cohort_repo.soft_delete`；series_cohort 含 `yn` 列 | 一致于"软删优先"原则，但字段不同（yn vs sale_status） |
| **module（模块）** | **物理删除**（`DELETE`，先清子表 `series_cohort_session`） | `module_repo.hard_delete`；`series_cohort_course` 无 `yn` 列 | **不一致（物理删）**——schema 决定，硬规则禁增列 |
| **session（课次）** | **物理删除**（`DELETE`，先清子表 `session_asset`） | `session_repo.hard_delete`；`series_cohort_session` 无 `yn` 列 | **不一致（物理删）**——同上 |

**结论**：series/cohort 走软删优先；module/session 因关联表无软删列，只能物理删除。这是 schema 决定的非对称，本任务**不新增列**，仅如实写入本契约，供后续 task（如引入统一软删列）参考。series 的 `hard=true` 已补上"零引用才物理删 + 引用拒绝"的显式护栏，是该资源族里最严格的删除契约。

---

## §4 孤儿模块归档（item ④）

- **动作**：`app/admin/question_admin/` → `app/_archived/question_admin/`（整目录移动，不参与 import）。
- **证据**：
  - `app/admin/` 现仅含 `__init__.py`（内容 `"P7 管理端 RAG 控制台包。"`，无 import question_admin）、`rag_admin`、`user_admin`。
  - 全仓活跃源码零引用 `app.admin.question_admin`（排除归档自身、logs、test-reports）。
  - `main.py:362-363` 挂载的题库路由来自 `app.domains.question_admin.router`（task13 重写），**与待归档的 `app.admin.question_admin` 无任何关系**。
  - `import app.main` → `IMPORT_OK`（routes=37）；**显式 `import app._archived.question_admin` → 直接 `ModuleNotFoundError: No module named 'app.admin.question_admin'`**（归档包内部仍用旧绝对导入，证明它已彻底隔离、不可能被意外激活）。

---

## §5 Middleware Chain

`Auth(CurrentUser) → RBAC(ADMIN|MANAGER) → [hard?] ADMIN-only 校验 → service(软删/真删分支) → ConflictError/PermissionDenied 错误处理器 → 统一响应壳 ok() → 缓存失效(invalidate detail)`。

---

## §6 Files to Create/Modify（grep 行号证据）

| 文件 | 行号 | 改动 |
|---|---|---|
| `app/common/error_codes.py` | 116-117 | 新增 `SERIES_IN_USE = "40908"` |
| `app/domains/course_admin/repository/series_repo.py` | 45,52,54,72-74 | `list_series` 增加 `include_deleted` 参数；默认 `WHERE sale_status != 'off_sale'` |
| 同上 | 124-128,131-153,152-155 | 新增 `off_sale()` / `count_references()`（统计**全部** series_cohort 行 + order_item JOIN 计数）/ `physical_delete()` |
| `app/domains/course_admin/service.py` | 25 | 导入 `SERIES_IN_USE` |
| 同上 | 125-153 | `delete_series(series_id, hard=False)`：软删 off_sale / 真删 FK 校验→409 或物理删（try/except 兜底避免 500） |
| 同上 | 156-166 | `list_series_admin(... include_deleted=False)` 透传 |
| `app/domains/course_admin/router.py` | 15 | `from app.common.exceptions import PermissionDeniedError` |
| 同上 | 41-60 | `admin_list_series` 增加 `include_deleted` Query 并透传 |
| 同上 | 84-93 | `admin_delete_series` 重写：ADMIN-only 校验 + 双路径 message |
| `app/admin/question_admin/` → `app/_archived/question_admin/` | — | 整目录归档，零实时引用 |

---

## §7 Constraints（硬性守则履约）

1. 响应壳 `{code,message,data}` 与分页 `page_meta` **不变**（未引入新壳/新分页结构）。
2. series 软删**仅** `sale_status='off_sale'`，**不新增 `yn` 列**（硬规则）。
3. 真删前置 FK 校验必须显式 `40908`，**绝不静默 500**（含软删班次行计数 + try/except 兜底）。
4. 不切分支、不 commit、不动 8000 受管实例（遵守开工单）。
5. 禁用 Playwright；接口验收全部用真实 HTTP（urllib/requests）+ DB 实测。
6. 测试数据自行清理（GWT 脚本 `finally` 直连 SQL purge，残留行 2644/2645/2646/2647 + 班次 7888 已清）。

---

## §8 验收证据索引

- 全链路真实 HTTP 实证（15 项 ALL PASS）：`edu-agent/test-reports/task116_gwt_evidence.json`（8077）
- 契约单测（无后端依赖，monkeypatch）：`tests/test_contract_task116.py`（**7 passed**）
- 回归基线（对 8077 新代码）：`test-reports/task116-regression-8077.md`（160 项，HTTP 500 缺陷 0，BADCODE 1 为 RAG 预设既有噪声，与 series 无关）
- 完工报告：`test-reports/task116-completion-report.md`
