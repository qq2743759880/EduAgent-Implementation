# L4 回归缺陷修复报告 — `DELETE /api/admin/courses/modules/{存在ID}` HTTP 500

> 角色：回归缺陷修复 agent（trust-but-verify，独立复现确认根因后再改）
> 日期：2026-09-04 ｜ 后端端口：8000（已用修复代码重启，服务健康）
> 纪律履约：**未 commit、未 git add**；最小改动；不顺手重构、不改契约外逻辑。

---

## 1. 根因结论（独立实证，非仅源码推断）

**结论：编剧者 FK 假设成立——`hard_delete` 物理删除触发 MySQL 外键 `IntegrityError(1451)` → 未捕获 → `AppException(50000)`（HTTP 500）。但具体机制比"module→session"直连更深一层：**

- `module_repo.hard_delete(module_id)` 会先 `DELETE FROM series_cohort_session WHERE series_cohort_course_id=module_id`（级联清课次），再删 module 行。
- 但 `series_cohort_session` 一行被 **8 张子表** 以 FK 引用（实时 `information_schema` 实测）：
  `session_asset, session_attendance, session_exam, session_homework, session_homework_submission, session_teacher_rel, risk_alert_event, teacher_compensation_item`。
- 只要该 module 下的任意课次被其中任一表引用，删课次那步就抛 `1451` → 50000。

**真实异常栈（8000 后端日志 `logs/app.log` 实测，首个复现=module 1）：**
```
app.main:global_exception_handler:331 - 未处理的异常: (1451, 'Cannot delete or update a parent row: a foreign key
constraint fails (`edu`.`session_asset`, CONSTRAINT `fk_session_asset_session` FOREIGN KEY (`session_id`)
REFERENCES `series_cohort_session` (`id`))')
```

**第二个复现（module 6247，L4 原始报障场景）：**
```
app.middleware.auth_middleware:dispatch:75 - [a187c8a2] DELETE /api/admin/courses/modules/6247 异常  status=500
app.main:global_exception_handler:331 - 未处理的异常: (1451, '... (`edu`.`risk_alert_event`, CONSTRAINT
`fk_risk_alert_event_session` FOREIGN KEY (`session_id`) REFERENCES `series_cohort_session` (`id`))')
```

**再复现（后续 GWT 验证阶段，module 6247）：**
```
DELETE /api/admin/courses/modules/6247 → HTTP 500 {"code":"50000","message":"服务内部错误，请稍后重试",
"data":"(1451, 'Cannot delete or update a parent row: a foreign key constraint fails (`edu`.`risk_alert_event`, ...)')"}
```

### 非 import 缺陷
门禁复核提示 `service.py:28 已 import NotFoundError/AppException/ConflictError`——已证实 import 不缺（早期 interface-acceptance.md 里"`name 'NotFoundError' is not defined`"是 task116 归档前的旧 500 根因，当前代码已修复，本次 500 与其无关）。

### 删除语义核对（读 C-C 契约 + 代码）
| 资源 | 现状 | 依据 |
|---|---|---|
| series | 软删下架 / `?hard=true` 真删前置 FK 计数→`40908`（`SERIES_IN_USE`），try/except 兜底 | `service.delete_series`；`handoffs/task116-contract.md` §1.2③、线 152 |
| cohort | `soft_delete` `yn=0`（不物理删，无 FK 风险） | `delete_cohort` |
| module | **物理删**，有 FK 级联 500 风险 | `delete_module` (**本次修复**) |
| session | **物理删**，被 8 张子表引用，有 FK 级联 500 风险 | `delete_session` (**本次修复**) |

C-C 语义（task116-contract.md）要求"真删前置 FK 校验必须显式报错码，绝对禁止残留外键导致 500 静默"，且"**禁止级联删子数据**"。

---

## 2. 修改文件与 diff 摘要

| 文件 | 改动 |
|---|---|
| `edu-agent/app/domains/course_admin/service.py` | `delete_module`/`delete_session` 增加删除前引用计数守卫：`count_references()>0 → ConflictError(code=SERIES_IN_USE=40908)`，绝不级联、绝不静默；`SERIES_IN_USE` 原本已在 import 行 24。 |
| `edu-agent/app/domains/course_admin/repository/module_repo.py` | 新增 `count_references(module_id)`：`SELECT COUNT(*) FROM series_cohort_session WHERE series_cohort_course_id=%s`。 |
| `edu-agent/app/domains/course_admin/repository/session_repo.py` | 新增 `_CHILD_TABLES` 常量（实时 FK 实测 8 表）+ `count_references(session_id)`：跨 8 子表 COUNT 求和。 |
| `edu-agent/tests/test_contract_task23.py` | `FakeModuleRepo` 补 `count_references` 存根（返回 0），使既有 module 删除缓存失效契约测试保持通过。 |
| `test-reports/interface_acceptance_final.py` | 新增 `test_delete_existing_referenced_resource`（防回退用例，见 §4），并在 `__main__` 挂接。 |

> 复用既有引用拒绝码 `SERIES_IN_USE=40908`（task116 契约同为 40908），未新增错误码/未改响应壳/未改 HTTP 映射/未改 DB 结构。`delete_cohort`(软删)、`delete_series`(已护栏) 无需改动。

---

## 3. GWT 实证表（真实 HTTP + DB 实测，8000 修复后代码）

| # | 场景 | 操作 | HTTP | code | data | DB 校验 | 结论 |
|---|---|---|---|---|---|---|---|
| ① | 被引用 module（含深层 FK 课次） | `DELETE /modules/6247` | **409** | **40908** | null | module 行仍在(count=1)；级联未删，8 个 session 原样(count=8) | **修复前 500 → 修复后 409** |
| ② | 干净 module（POST 临时建、无 session） | `POST /modules`(id=23655) → `DELETE /modules/23655` | 200 | 0 | null | 临时 module 已删(count=0)，无残留 | 无引用可正常删 |
| ③ | 被引用 session（risk_alert_event） | `DELETE /sessions/29786` | **409** | **40908** | null | session 行仍在(count=1)，未级联误删 | 修复后 409 |

残余清理：临时 module 23655 已随测试删除；DB 无 `l4tmp%` 残留。

---

## 4. 补测用例说明

`interface_acceptance_final.py` 新增 `test_delete_existing_referenced_resource(rows)`：
- **为何是漏检**：旧脚本 DELETE 一律把路径 ID 替换成 `999999999`（`resolve_path`/`re.sub(r"\d+$","999999999",...)`），只命中 404，永远无法走到"存在且被子资源引用"的物理删除分支，因此 FK→500 缺陷无法被捕获。
- **新增逻辑**：直连 DB（pymysql）选 ①一个带课次的 module、②一个被 `risk_alert_event` 引用的 session，实际 `DELETE`；断言 `HTTP != 500` 且返回既有业务码（非 `50000`）。全量重跑产出：
  ```
  | DELETE | /api/admin/courses/modules/1(被引用) | 409 | 40908 | OK | 模块仍被 8 个课次引用 |
  | DELETE | /api/admin/courses/sessions/29786(被引用) | 409 | 40908 | OK | 课次仍被 45 条子记录引用 |
  ```
- 未提交该脚本到 git。

---

## 5. 回归结果

| 项 | 结果 |
|---|---|
| `pytest tests/test_course_admin.py test_contract_task116.py test_contract_task23.py`（携 admin token） | **32 passed** |
| `pytest tests/test_contract_task116.py test_contract_task23.py`（离线，mock 仓储） | **13 passed** |
| `interface_acceptance_final.py` 全量重跑 | **FAIL500 = 0**（Counter：OK 107 / BIZ 48 / DEBUG 4 / BARE 2 / BADCODE 1，无 HTTP 500） |
| `import app.domains.course_admin.service`（后端同源 kb311 python） | 导入 OK |

---

## 6. 资产消费证据（读了哪些段）

- `handoffs/task116-contract.md`：§1.2③（series hard delete 引用拒绝 40908）、§3 删除语义核对表（module/session 物理删、cohort/series 软删）、线 152（必须显式报错码，禁止残留 FK 500）。
- `app/common/error_codes.py`：确认 `SERIES_IN_USE="40908"`（行 118）为既有引用拒绝码，未新增。
- `app/domains/course_admin/repository/*.py`：`module_repo.hard_delete`（清子表 session）、`session_repo.hard_delete`（清 session_asset）、`series_repo.count_references`（series 真删引用计数范式）。
- `edu.sql` 系 schema（`alembic/baseline_schema.sql` 等）：`fk_series_cohort_session_course(series_cohort_course)`、`fk_risk_alert_event_session` 等 FK 定义；并**额外用实时 `information_schema.KEY_COLUMN_USAGE` 交叉实测**（dump 为 08-16，实时 FK 更权威）：确认 `series_cohort_course` 仅被 `series_cohort_session` 引用、`series_cohort_session` 被 8 张子表引用。
- `service.py` import 行（确认 NotFoundError/ConflictError/SERIES_IN_USE 均已导入）。

---

## 7. 自检发现并修复

1. **发现**：首次设计守卫时仅关注 module 直连子表（session），但复现栈显示真正 FK 冲突点是 `session_asset` / `risk_alert_event`（session 的深层子表）。**修复**：为 `delete_session` 同样加 8 子表引用守卫，并对 module 用"模块仍存在课次则拒绝"来闭合所有 module-level FK 场景（任何带课次的 module 都会被拦截，永不走到会抛 1451 的删课次步骤）。
2. **发现**：GWT② 临时 module 的 POST 触发 422（`ModuleCreateAdmin` 强校验 `start_date/end_date`），一度无法验证"干净删除成功"路径。**修复**：补上必填日期字段后，干净 module 200 删除 + DB 清零实证通过。
3. **发现**：新增 `count_references` 后，`test_contract_task23.py` 的 `FakeModuleRepo` 缺该方法会 AttributeError。**修复**：补存根（返回 0）使既有模块缓存失效契约测试保持通过（不破坏既有断言）。

---

## 8. 结论

- 根因：`delete_module`/`delete_session` 物理删除前置无引用防护，子资源（课次/深层子表）FK 引用存在时抛未捕获 `IntegrityError(1451)` → 50000。
- 修复：对齐 C-C 删除语义，删除前引用计数 `>0` 即抛 `40908`，禁止级联删子数据，绝不静默。
- 涉及文件 5 个（service/repository×2/test_contract_task23/interface_acceptance_final）；被引用资源删除 40908、干净资源删除 200、全契约/全量验收 0×FAIL500。
- **未 commit、未 git add**。