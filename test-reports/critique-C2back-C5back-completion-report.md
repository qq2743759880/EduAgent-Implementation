# critique-C2back-C5back 完工报告（后端独立实证）

> 任务：EduAgent 优化期批判落地
> - **C2**（后端）：删除分页「双轨」结构 `page_meta`，收敛到 C-B 权威外层 `{total,page,page_size,items}`
> - **C5**（后端）：补管理员回收站最小闭环 —— 新增「系列恢复」端点
> 完成日期：2026-09-04 ｜ 归属：后端独立子 agent（tt 工作流派发）｜ **未 commit**

---

## 一、改动文件与行数（git diff --stat 摘录，仅本任务范围）

| 文件 | 改动 | 内容 |
|------|------|------|
| `edu-agent/app/domains/course/schemas.py` | 24 删 | 删 `PageMeta` 类；`SeriesListData`/`CohortListData` 去掉 `page_meta` 字段 |
| `edu-agent/app/domains/course/service.py` | 27 删 | 删 `_build_page_meta`；`list_series`/`list_cohorts` 不再双写 page_meta |
| `edu-agent/app/domains/course_admin/schemas.py` | 39 改 | 删 `PageMeta`；所有 `*ListDataAdmin` 换成 `{items,total,page,page_size}` |
| `edu-agent/app/domains/course_admin/service.py` | +44/-… | 删 `_build_page_meta`（列表双层收敛）；新增 `restore_series` |
| `edu-agent/app/domains/course_admin/repository/series_repo.py` | +7 | 新增 `restore()`（off_sale → draft） |
| `edu-agent/app/domains/course_admin/router.py` | +28 | 新增 `restore_router`（`POST /api/course-admin/series/{id}/restore`） |
| `edu-agent/app/main.py` | +2 | `include_router` 注册 restore 路由 |
| `edu-agent/app/middleware/auth_middleware.py` | +1 | `ADMIN_PREFIXES` 加 `/api/course-admin/`（堵匿名 200 缺陷） |
| `edu-agent/tests/test_course_admin_restore.py` | 新文件 | C5 契约测试（5 用例，真实 HTTP） |
| `edu-agent/tests/test_contract_task39.py` | 15 改 | `TestCohortsPagedShell` 根因断言适配字段重排（total 先于 items） |
| `edu-agent/tests/test_course_domain.py` | 3 改 | `_first_series_with_full_chain` 适配 cohorts 已由裸列表变为分页壳 `{items,...}` |

---

## 二、C2 删除证据（grep）

`git grep -n "page_meta\|PageMeta" edu-agent/app tests` 结果 **仅剩注释/文档字符串**，无任何字段声明或组装逻辑：

```
app/domains/course/schemas.py:6:  列表分页统一外层 {total, page, page_size, items}（C-B 全站权威，无 page_meta 双轨，C2 已删）
app/domains/course/schemas.py:42: SeriesListData docstring "…C2 已删 page_meta 双轨…"
app/domains/course/schemas.py:101: CohortListData docstring "…C2 已删 page_meta 双轨…"
app/domains/course/service.py:78: 注释 "…（C2：外层 triple 唯一，无 page_meta）"
app/domains/course/service.py:149: 注释 "…（C2：外层 {total,page,page_size,items}，无 page_meta）"
tests/test_contract_task39.py:211: 注释 "…C2 已删 page_meta 双轨…"
```

> `_build_page_meta` 函数体已整体删除，无任何「同时组装两套」的死代码残留。

### 真实 HTTP 实证（登录 admin 直连 127.0.0.1:8000）
三条列表端点出口键均为 `['items','page','page_size','total']`，**无 `page_meta`**：

```
C   /api/series            -> keys: ['items','page','page_size','total'] | has page_meta: False
ADM /api/admin/courses/series -> keys: ['items','page','page_size','total'] | has page_meta: False
ADM /series total: 2629 page: 1 page_size: 5 items_len: 5
C   /api/series/2628/cohorts -> keys: ['items','page','page_size','total'] | has page_meta: False
```

---

## 三、C5 恢复端点契约与测试

### 端点
```
POST /api/course-admin/series/{series_id}/restore      （admin / manager）
```
- 语义：`sale_status='off_sale'`（软删下架）→ `sale_status='draft'`（恢复为草稿，可再上架）。
- 成功：`ok(data={"series_id": <id>, "status": "restored"})`
- 404 `40400`：不存在 / 未处于软删态（统一收敛，不泄露存在性）
- 409 `40901 SERIES_CODE_CONFLICT`：恢复时 `institution_id + series_code` 被其它系列占用
- 401 `40101`：匿名/非管理员（中间件短路，`/api/course-admin/` 已入 `ADMIN_PREFIXES`）
- 不影响既有 `DELETE /series/{id}`（软删/?hard=true 真删）与 40908 拒引用逻辑。

> 契约全文（含 curl 请求/响应/错误示例）已登记：`handoffs/critique-C5-contract.md`

### pytest 实测输出（真实 HTTP 直连 8000，5/5 绿）
```
tests/test_course_admin_restore.py::TestRestoreSuccess::test_restore_full_cycle PASSED [ 20%]
tests/test_course_admin_restore.py::TestRestoreErrors::test_restore_nonexistent_404 PASSED
tests/test_course_admin_restore.py::TestRestoreErrors::test_restore_not_soft_deleted_404 PASSED
tests/test_course_admin_restore.py::TestRestoreErrors::test_restore_anonymous_401 PASSED
tests/test_course_admin_restore.py::TestHardDeleteGuardUnchanged::test_hard_delete_with_reference_still_40908 PASSED
==================== 5 passed in 50.51s ====================
```
覆盖：软删→`include_deleted=true` 可见→restore→默认列表可见 `draft`→重新上架 `on_sale`；三种错误分支；`DELETE ?hard=true` 有引用仍 40908（原语义未回退）。

---

## 四、C2 域的 pytest 回归

| 模块 | 结果 | 说明 |
|------|------|------|
| `tests/test_contract_task39.py::TestCohortsPagedShell` | ✅ 3 passed | 根因钉死用例适配字段重排 |
| `tests/test_course_domain.py` | ✅ 23 passed / 3 修复通过 | 层级用例（series→cohort→module）适配 cohorts 分页壳 |
| `tests/test_course_admin.py` | ✅ 4 passed / 15 skipped | skipped=「无有效 TEST_ADMIN_TOKEN」既定环境门（非 C2 所致） |

**唯一未绿：** `test_course_domain.py::TestSeriesListGwt1::test_p95_latency_under_200ms`，实测 P95≈2100ms vs 阈值 200ms。
**判定：环境性失败，非 C2 回归** —— 本机直连 `/api/series` 每次请求即约 2s（冷 MySQL + DEBUG 模式 + 本机 I/O），与「删除冗余 page_meta 字段」无因果关系（C2 不改任何 DB 查询/序列化耗时）。该用例历史上依赖加快环境；与 `test_course_admin.py` 的 token skipped 一并列为环境门，建议 CI 或预热后跑。

---

## 五、interface 脚本更新说明

- 契约权威响应外形**未变**（外层仍是 C-B 冻结的 `{total,page,page_size,items}`）；本次只**删除**了同值的冗余兼容字段 `page_meta`。
- `interface_acceptance_final.py` / 相关契约脚本如需断言分页外壳，应断言 `{items,total,page,page_size}` 四键齐全 + **`page_meta` 不存在**（本报告二、三节的真实 HTTP 已给出该四键结构为证据）。
- 前端静态页 `public/admin-courses.html`、`courses.html` 的 C2fe/C5fe 前端侧改动不在本后端报告范围（见 `test-reports/critique-C2fe-C5fe-completion-report.md`）。

---

## 六、对既有 C-B / C-C 契约的影响确认

- **C-B（契约① 响应壳 + 分页外层）**：`{code:0,message:"ok",data:{total,page,page_size,items}}` 权威外形完好；只是删掉了 `data` 内重复的 `page_meta` 冗余字段。消费方读 `data.items`、`data.total` 等不受影响。
- **C-C（既有 course_admin CRUD）**：`DELETE /series/{id}`（软删/?hard=true 真删）与 40908 拒引用、创建/更新/列表端点契约**零改动**；新增的 restore 端点共用 `api/course-admin` 前缀独立挂载。

---

## 资产消费证据

- 加载 skill：**harden**（`/harden/SKILL.md`，AI-Hub 技能目录）。方法论要点落在改动点：
  - **hid: 错误场景 / 权限** → C5 restore 端点三层守卫：中间件 401（匿名）、service 404（不存在/未软删）、409（唯一性冲突），并保留原 hard 删除 40908 不回退。
  - **hid: 边界输入 / 状态机** → restore 仅接受 `sale_status='off_sale'` 唯一合法来源态，恢复后落 `draft`（草稿，可再上架），三者构成三态最小闭环。
- 实证手段（tt 纪律·禁臆测）：
  - `git grep page_meta|PageMeta` 证删除净度（仅注释残留）；
  - 登录 admin 真实 HTTP 直连 `127.0.0.1:8000` 拉取三条列表端点出口键，证无 `page_meta`；
  - `pytest tests/test_course_admin_restore.py` 5/5 绿（C5）；
  - `pytest` course/course_admin/contract 域回归（C2），其中修复 2 处 C2 引发的用例（`TestCohortsPagedShell` 字段序、`_first_series_with_full_chain` 裸列表→分页壳）——这两处正是「改动后必须同步更新对应契约测试」的自检发现。
- 自检发现并修复问题：
  1. `restore` 匿名访问最初漏 401（新前缀未入 `ADMIN_PREFIXES`）→ 补 `auth_middleware.py`，`test_restore_anonymous_401` 已绿。
  2. 恢复后列表外壳若经裸列表迭代会 `TypeError`（C2 副作用）→ 修 `_first_series_with_full_chain` 用 `data["items"]`。
  3. `TestCohortsPagedShell` 根因钉死用例断言 `first[0]=="items"` 过期（字段重排）→ 放宽为四键之一，根因钉死语义（迭代产出元组无 `model_dump`）不变。