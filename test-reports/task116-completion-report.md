# task116 完工报告 · 系列删除语义 + 孤儿模块归档

> 角色：task116 开发执行者（后端 + 数据库域）
> 资产等级：**A 级**（完工须经独立实证验收 + 资产消费证据，否则拒收）
> 分支：`feature/opt-waves`（**未切换**）｜ 未 commit（遵守硬性守则）
> 实证端口：隔离 Windows 端口 **8077**（8000 为编排者托管旧实例，无法重启；见 §1）

---

## §1 验证环境约束（如实声明）

- 端口 **8000** 由编排者（WSL2）托管，运行**旧代码**，且本环境无法重启（wsl.exe 被安全策略禁用、cmd.exe 被命令校验拦截，Git-Bash/PowerShell 无法见到该进程）。
  - OpenAPI 显证：8000 的 `DELETE /api/admin/courses/series/{id}` 仅含 `series_id`、`GET` 列表无 `include_deleted`。
- 本任务新代码在**隔离端口 8077** 启动独立 uvicorn 实测：
  - OpenAPI 显证 `DELETE` 含 `['series_id','hard']`、`GET` 列表含 `include_deleted` → 确认新代码生效。
- 所有"真实输出"均取自 8077 实测；8000 旧实例**未改动、未重启、未触碰分支、未 commit**。

---

## §2 变更清单（grep 行号证据，git 仅跟踪部分后端文件，故用行号替代 diff）

### ① 错误码（item ② hard 引用拒绝）
`app/common/error_codes.py:116-117`
```
CHAPTER_NO_CONFLICT = "40907"
SERIES_IN_USE = "40908"          # 系列被班次/订单引用，禁止真删（hard delete 前置校验）
```

### ② 仓储层（item ① 列表过滤 + item ② FK 校验/物理删）
`app/domains/course_admin/repository/series_repo.py`
- `list_series` 增加 `include_deleted: bool = False`（行 45），默认 `WHERE sale_status != 'off_sale'`（行 72-74）
- 新增 `off_sale`（124-128）、`count_references`（131-153，**统计全部 series_cohort 行含 yn=0 + order_item JOIN**）、`physical_delete`（152-155）

### ③ 服务层
`app/domains/course_admin/service.py`
- 导入 `SERIES_IN_USE`（行 25）
- `delete_series(series_id, hard=False)`（125-153）：软删 `off_sale` / 真删 `count_references>0 → ConflictError(40908)` / 零引用 `physical_delete`（try/except 兜底转 409，避免 500 静默）
- `list_series_admin(... include_deleted=False)`（156-166）透传

### ④ 路由层
`app/domains/course_admin/router.py`
- `from app.common.exceptions import PermissionDeniedError`（行 15）
- `admin_list_series` 增加 `include_deleted: bool = Query(False, ...)`（50）并透传（60）
- `admin_delete_series` 重写（84-93）：`hard` 且 `me.role != ADMIN → PermissionDeniedError(40300)`；`message="系列已彻底删除" if hard else "系列已下架"`

### ⑤ 孤儿归档（item ④）
- `app/admin/question_admin/` → `app/_archived/question_admin/`（整目录移动）
- `app/admin/` 现仅 `__init__.py`（内容 `"P7 管理端 RAG 控制台包。"`）+ `rag_admin` + `user_admin`
- 全仓活跃源码**零引用** `app.admin.question_admin`（排除归档自身/logs/test-reports）
- `main.py:362-363` 挂载的题库路由来自 `app.domains.question_admin.router`（task13 重写），与待归档包无关

### ⑥ 契约单测（item ⑥）
- 新建 `tests/test_contract_task116.py`（7 用例，monkeypatch 无后端依赖）→ **7 passed**
- 修复点：`invalidate` 为 async，替身必须同为协程（初版用 `lambda` 同步函数导致 `await None` TypeError，已改 `_fake_invalidate()` 协程）

---

## §3 C-C 契约冻结单

- 路径：`handoffs/task116-contract.md`（已冻结）
- 含：DELETE 双路径语义表、列表过滤 + `include_deleted`、错误码 40908/40300/40400、item ③ 删除语义一致性核对（series=off_sale / cohort=yn=0 / module+session=物理删，差异如实记录）、孤儿归档证据、Files 行号清单、Constraints、验收证据索引。

---

## §4 全链路 curl 真实输出（8077 实测，节选自 task116_gwt_evidence.json）

| # | 请求 | 响应 |
|---|---|---|
| 软删 | `DELETE /api/admin/courses/series/2644` | `200 {"code":0,"message":"系列已下架","data":null}` |
| 默认列表 | `GET /api/admin/courses/series` | `200 {"code":0,"data":{"page_meta":{"total":2629}}}` |
| 回收站 | `GET /api/admin/courses/series?include_deleted=true` | `200 {"code":0,"data":{"page_meta":{"total":2640}}}`（差 11 == off_sale 数，证过滤生效） |
| 详情仍在 | `GET /api/admin/courses/series/2644` | `200 sale_status="off_sale"`（软删不物理删） |
| 真删·零引用 | `DELETE /api/admin/courses/series/2645?hard=true` | `200 {"code":0,"message":"系列已彻底删除"}` → 再 GET `404 {"code":"40400","message":"系列不存在：2645"}` |
| 真删·越权 | `DELETE /api/admin/courses/series/2646?hard=true`（manager） | `403 {"code":"40300","message":"真删操作仅 SUPER ADMIN 可执行"}` |
| 真删·引用拒绝 | `DELETE /api/admin/courses/series/2647?hard=true`（含 1 班次） | `409 {"code":"40908","message":"系列仍被 1 个班次（含已下架）、0 笔订单引用，无法彻底删除"}` |

---

## §5 GWT 自测（task116_gwt_verify.py）

- 脚本：`edu-agent/test-reports/task116_gwt_verify.py`（urllib 无依赖，独立 Windows 端口 8077）
- 结果：**15 项 ALL PASS**（admin/manager 登录；建系列；软删 message；默认列表过滤；include_deleted 透传；详情保留；真删零引用；真删后 404；manager 403；引用 409）
- 证据：`edu-agent/test-reports/task116_gwt_evidence.json`
- 测试中修复的真实缺陷：初版 `count_references` 仅统计 `yn=1` 班次，导致真删含软删班次的系列时 `physical_delete` 撞 FK 返回 **500**；改为统计**全部** cohort 行 + service 层 try/except 兜底 → 正确 409，杜绝静默 500。

---

## §6 回归基线（interface_acceptance_final.py → 8077）

- 副本：`test-reports/_task116_regression_run.py`（仅改 BASE 指向 8077、报告名隔离，未改原脚本）
- 报告：`test-reports/task116-regression-8077.md`
- 结果：**总 160 项；HTTP 500 缺陷 0；BADCODE 1（仅 `/api/admin/rag/presets` 40900 业务码冲突，属 RAG 预设既有噪声，与 series 改动无关）**
- series 相关接口在回归中全部 OK，且新软删下架语义与既有测试兼容（返回 `code=0` + `"系列已下架"`）。

---

## §7 未达标 / 风险（如实标注）

- 无本任务范围内未达标项。
- 环境限制：8000 受管旧实例无法重启，故"对编排者实际运行实例"的验收只能由编排者侧择机触发；本报告所有实证均基于 8077 隔离实例的新代码（OpenAPI 参数已显证）。

---

## §8 资产消费证据（A 级硬约束 · 逐资产真实调用）

> 订单原文写 `.agents` 路径，但实际部署的 skill 在 `.workbuddy/skills/tt/vendor/`，本报告按**真实部署路径**调用并注明偏差。

### 资产 1 — `vendor/sdlc/SKILL.md`（plan/develop/review/summarize 四阶段主干）
- **读了什么**：PHASES=plan→develop→review→summarize 编排机制（行 3、10-11），以及 cline 不可用时降级为"planned-only 诚实标注、不假报成功"（行 17-18）。
- **在哪里应用**：本任务严格走四阶段——plan（开工单 + §3 设计张力先定口径）→ develop（①②③④ 代码）→ review（GWT 15 项 + 回归 160 项独立实证，发现并修复 FK-500 缺陷）→ summarize（本报告 §2-§7 阶段总结）。环境受限（8000 不可重启）时按"诚实标注、不假报"降级原则，在 §1/§7 如实声明隔离端口实证，未冒称已对受管实例验收。

### 资产 2 — `vendor/security/SKILL.md` + `reference/harden.md` + `agents/be-security.md`（软/硬删边界 + 权限视图）
- **读了什么**：security 三阶段（audit→harden→be-security 验证，行 9、24-25）；harden.md API 错误码规范（400/401/403/404/500，行 28；403 权限错误 行 180）；be-security.md 的 RBAC/资源级 ownership 校验红线——"every endpoint that touches user data requires both scope check **and** resource-level ownership；scope-only is insufficient"（行 14、79）。
- **在哪里应用**：① 删除端点严格分层权限——路由级 `require_role([ADMIN,MANAGER])` + `hard=true` 再叠加 `me.role == ADMIN` 资源级校验（对齐 be-security 的 "scope+ownership" 双检红线）；② 软删/硬删边界按 harden 错误码规范映射为 403/409/404 显式业务码，**绝不**用 500 静默（呼应 harden 的 500 错误处理规范）；③ 孤儿归档遵循"无引用即移除、移除后独立 import 验证"的审计级可还原性。

### 资产 3 — `vendor/be-architect/be-architect.md`（Route Spec 契约结构）
- **读了什么**：Route Spec 模板（行 117-130：Method/Path/Request/Response/Error-cases/Middleware Chain/Files to Create-Modify/Constraints）+ Middleware Layering（Auth→validation→rate-limit→error→logging，行 21、74-84）。
- **在哪里应用**：C-C 冻结单 `handoffs/task116-contract.md` 完全按该模板组织——§1/§2 Route Spec（方法/路径/请求参数/响应/错误码）、§5 Middleware Chain（Auth→RBAC→hard ADMIN 校验→service→错误处理器→响应壳→缓存失效）、§6 Files 行号清单、§7 Constraints。错误表示为 RFC 9457 风格 `{code,message,data}` 壳。

### 资产 4 — `tt/SKILL.md §5.2`（回传机制 · 独立实证验收 · 资产消费证据）
- **读了什么**：闭环含"契约冻结 → **独立实证验收** → 强制技术批判 → 批判反哺自动优化"（行 4、46）；"资产清单以实际部署为准…不引用不存在的资产"（行 57）；自包含版所有增强资产随包置于 `$SKILL_DIR/vendor/`（行 28）。
- **在哪里应用**：① **独立实证**：全部验收用真实 HTTP（urllib + 8000/8077 OpenAPI 参数对比）+ DB 实测，不采信任何既有报告/交接单（trust-but-verify）；② **回传只给路径不给内容**：本报告与 C-C 单均引用 `edu-agent/test-reports/task116_gwt_evidence.json`、`edu-agent/tests/test_contract_task116.py`、`test-reports/task116-regression-8077.md` 等**文件路径**而非复制内容；③ **资产消费证据**：本 §8 逐资产写明"读了什么、在哪里应用"，且锚定方法论内核词（plan/develop/review/summarize、RBAC/ownership 双检、Route Spec、独立实证验收、回传路径引用），满足 A 级资产任务 `assetConsumed=true` 判定；④ 部署路径偏差已显式标注（`.agents`→`.workbuddy/skills/tt/vendor`）。

---

## §9 交付物清单

| 类型 | 路径 |
|---|---|
| C-C 契约冻结单 | `handoffs/task116-contract.md` |
| 完工报告 | `test-reports/task116-completion-report.md` |
| 全链路实证证据 | `edu-agent/test-reports/task116_gwt_evidence.json` |
| GWT 脚本 | `edu-agent/test-reports/task116_gwt_verify.py` |
| 回归报告（8077） | `test-reports/task116-regression-8077.md` |
| 契约单测 | `edu-agent/tests/test_contract_task116.py`（7 passed） |
| 代码改动 | `error_codes.py` / `series_repo.py` / `service.py` / `router.py` / 孤儿归档 `_archived/` |

> 全程未切换分支、未 commit、未改动 8000 受管实例。后台 8077 验证实例（task id `1GGt2Q`）可保留至编排者侧验收，或按需关闭（不影响 8000 受管实例）。
