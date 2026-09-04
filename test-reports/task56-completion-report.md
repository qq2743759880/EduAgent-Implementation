# task56 完工报告 — /admin/courses 管理端课程（系列+班次总览）

> 执行人：前端开发者（Trae）｜阶段：P6｜并行组：W7｜工作量：L
> 日期：2026-08-23｜类型：frontend

## 1. 一页摘要

管理端课程总览页已按 **HTML 原型 → APPROVED → React** 流程交付。核心达成：

- 系列 **CRUD** 全通：`POST/PATCH/DELETE /api/admin/courses/series`，软删语义「下架优先于删除」（series 表无 yn 列，DELETE 实现为置 off_sale）。
- **RBAC**：非 admin 由 `(admin)/layout.tsx` 的 `AdminGuard` 拦截（toast + 重定向），菜单经 `filterAdminNav` 仅 admin 渲染 6 项。
- **sale_status 枚举渲染**：`draft→muted 草稿 / on_sale→success 在售 / off_sale→muted 已下架`，行内上架⇄下架互切。
- 前置契约：消费 task12 四级 CRUD（series/module/session/cohort 管理端点）；行内「班次」跳 `/admin/courses/{id}`（task57）。

## 2. GWT 验收逐条自查

| # | Given / When / Then | 结果 | 证据 |
|---|---------------------|------|------|
| G1 | Given HTML APPROVED，When 系列 CRUD，Then POST/PATCH/DELETE /api/admin/courses/series 全通（软删 yn=0） | **PASS** | 页面三 mutation（create/patch 上下架/delete）；`SeriesForm.create` 调 POST、`SeriesForm edit` 调 PATCH、`deleteAdminSeries` 调 DELETE；page 上架/下架/删除三项行操作齐全；软删 confirm「下架优先于删除」提示；`courses.test.ts` mock POST/PATCH/DELETE 路径断言 15/15 |
| G2 | Given RBAC，When 非 admin 访问，Then AdminGuard 拦截；菜单 filterAdminNav 过滤 | **PASS** | `admin-guard.tsx` 非 admin → toast「无权限访问管理端」+ 重定向 `/dashboard`；未登录 → 跳登录页带 `?redirect=`；`admin-nav.ts` `filterAdminNav` 仅 admin 返回 6 菜单，其余角色 0 项；`(admin)/layout.tsx` 用 `filterAdminNav(me?.roles)` 渲染菜单、`<AdminGuard>` 包裹 children；`admin-guard.test.tsx` 8/8、`admin-nav.test.ts` 12/12 |
| G3 | Given sale_status 枚举，When 渲染，Then draft→muted 草稿 / on_sale→success 在售 / off_sale→muted 已下架 | **PASS** | `saleBadge()` 三分支：on_sale→`bg-candy-green-soft text-candy-green`（绿 success 语义）/ draft→`bg-muted text-muted-foreground`（灰）/ off_sale→`border-dashed bg-muted/50`（灰虚线）；上架⇄下架按钮随状态切换；枚举来自 `SALE_STATUS_OPTIONS`（draft/on_sale/off_sale）；`saleStatusLabel` 纯函数测试覆盖 |

## 3. 数据面盘点与契约对齐附注

- 对齐源：`domains/course_admin` 契约、`app/admin/course_admin/router.py + schemas.py`（L1 权威）。
- 系列列表：`GET /api/admin/courses/series`，支持 `page/page_size/keyword/delivery_mode/sale_status/sort/institution_id`；返回 `page_meta{page,page_size,total,total_pages,has_more}`。
- 系列创建：POST body 含 `institution_id + delivery_mode + series_code + series_name + sale_status(可选) + description/cover_url/target_*`。
- 系列更新：PATCH 全 Optional；`series_code`/`institution_id` **创建后不可改**（`SeriesForm` edit 模式禁用两字段，`buildEditPayload` Delta 算法排除，单测锁定）。
- 软删：series 无 yn → DELETE 置 off_sale，响应「系列已下架」；页面 confirm 文案已说明「删除为软删，将置为已下架」。
- 契约修订记录：t3 阶段曾用旧 subject_code/level_code 契约，经数据面盘点改为 delivery_mode/institution_id 并对齐 checker 提示，之后 HTML 原型的筛选栏、SeriesForm 均同步。

## 4. 交付物清单

| 类别 | 文件 | 说明 |
|------|------|------|
| 规范 | `.opencode/plans/doc-frontend-design-spec.md` P13 | 管理端课程总览设计规范（数据契约/布局/组件/交互） |
| 原型 | `test-reports/fe-html/admin-courses.html` | 已 APPROVED，含筛选栏/DataTable/分页器/行操作下拉 |
| React 页面 | `edu-frontend/src/app/(admin)/admin/courses/page.tsx` | 列表/筛选/分页/上下架/软删/行操作 |
| React 表单 | `edu-frontend/src/components/admin/SeriesForm.tsx` | 创建/编辑弹窗，Delta 提交，a11y 焦点定位 |
| API 层 | `edu-frontend/src/lib/api/admin/courses.ts` | 系列 CRUD + deliveryModeLabel 等纯函数，对齐新契约 |
| 复用 | `PaginationBar` / `AdminGuard` / `filterAdminNav` / `controls`(Loading/Error/Empty/NativeSelect/FieldRow) | 已有组件，无重复造轮子 |
| 测试 | `src/lib/api/admin/courses.test.ts` 15 项 + `src/components/admin/SeriesForm.test.tsx` 6 项（+ 既有 admin-guard 8 + admin-nav 12） | 契约/纯函数/RBAC 全覆盖 |

## 5. 截图矩阵（HTML 原型审核证据）

| 视图 | 文件 | 状态 |
|------|------|------|
| 成功态（1280 桌面） | `test-reports/fe-html/ad-courses-success-1280.png` | ✅ |
| 成功态（375 移动） | `test-reports/fe-html/ad-courses-success-375.png` | ✅ |
| 加载态 | `test-reports/fe-html/ad-courses-loading-1280.png` | ✅ |
| 错误态 | `test-reports/fe-html/ad-courses-error-1280.png` | ✅ |
| 空态 | `test-reports/fe-html/ad-courses-empty-1280.png` | ✅ |
| 行操作下拉展开 | `test-reports/fe-html/ad-courses-dropdown-1280.png` | ✅ |
| 截图脚本 | `test-reports/fe-html/shoot-admin-courses.js` | ✅ |

分页器初始不显示 bug（v1 发现）已修复：动态计算 `totalPages`、成功态同时渲染行与分页器，截图 `success-1280` 已复核正常。

## 6. 质量门禁

| 门禁 | 结果 |
|------|------|
| Vitest 全量 | **66 文件 450 测试 PASS**（含本任务 courses 15 + SeriesForm 6 + admin-guard 8 + admin-nav 12） |
| TypeScript `tsc --noEmit` | 0 错误 |
| ESLint | 0 error / 0 warning |
| Next `next build` | 成功，`/admin/courses` 生成静态页（18/18 static） |
| 独立审查/测试子代理 | 依据用户最高优先级工作流纪律，本任务由 fe 实现 + 单测锁定纯函数与契约，主对话框完成；R1-R5 式的 Red-Line 检查请编排者在 React 交付后复核（本次无约定独立评审节点，未冒进） |

## 7. 已知边界 / 后续

- task57 的「班次 `/admin/courses/{id}`」当前为可点击路由（`/admin/courses/[seriesId]` 已有占位），班次内详情的 CRUD 属 task57 范围，task56 仅提供入口链接（J23）。
- 上下架/删除均实时调后端 PATCH/DELETE，无 mock；唯一前端侧装订为 `page_size=10`（分页器显示，后端 max 100）。

## 8. 纪律声明

- 单任务聚焦：仅 task56 相关文件改动，未触碰 task23/task92/用户端模块。
- 本任务已按「HTML APPROVED → React → 全量测试 → build → 完工报告」顺序完成，**停下等待编排者验收**，验收通过前不开始 task57。