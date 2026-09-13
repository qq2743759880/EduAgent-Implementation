# task13 原型完成报告 · 系列回收站 Tab HTML 原型（仅原型，不接线）

- 日期：2026-09-12
- 产出文件：`edu-frontend/public/admin-courses-recycle-proto.html`（唯一新增文件）
- 状态：**DRAFT**（待编排者验收 → 用户 Gate A 签收后才允许接线实施）
- 硬性守则符合性：只新建 1 个 HTML 原型文件；`admin-courses.html` 零改动（`git diff --stat` 为空）；未使用 Playwright；原型不发起任何真实请求（无 `<script src>`、无 fetch/XHR，node --check 两段内联脚本通过）。

---

## 一、curl 实测证据（2026-09-12，后端 127.0.0.1:8000，账号 adm02test/Test@123456）

### 1. 登录

```
POST /api/auth/login  {"account":"adm02test","password":"Test@123456"}
→ {"code":0,"message":"ok","data":{"access_token":"eyJ...","token_type":"Bearer","expires_in":86400,...}}
```
- 实测纠正：登录 body 字段是 **`account`** 不是 `username`（传 username → 422 `Field required: body.account`）。

### 2. 系列列表 GET /api/admin/courses/series?page=1&page_size=10

- 响应壳：`{code:0, message:"ok", data:{items:[...], total:2629, page:1, page_size:10}}`（外层分页 triple）。
- item 字段（实测逐字）：`id, institution_id, delivery_mode, series_code, series_name, description, cover_url, target_learner_identity_codes, target_learning_goal_codes, target_grade_codes, sale_status, created_by, created_at, updated_at`。
- openapi 文档化参数：`keyword(1~64) / institution_id / delivery_mode / sale_status(draft|on_sale|off_sale) / include_deleted(bool 默认 false) / sort(default|newest|name_asc|name_desc) / page(min1 默认1) / page_size(min1 max100 默认20)`。

### 3. 过滤参数实测（任务指定对比项）

| 请求参数 | 实测结果 | 结论 |
|---|---|---|
| `status=off_sale` | code 0，total 仍 2629，items 中出现 draft/on_sale | **参数无效（被忽略）** |
| `sale_status=off_sale` | code 0，total 2629→**56**，items 全部 `sale_status:"off_sale"` | **有效过滤** |
| `include_deleted=true`（单独） | total **2685** = 2629 + 56 | true=**不过滤 off_sale 的全量**，非"仅软删" |
| `sale_status=off_sale&include_deleted=true` | total **56**，全部 off_sale | **回收站正确组合** |

- ⚠️ 契约要点（供编排者）：现有 `admin-courses.html` C5 bin 视图仅传 `include_deleted=true`，会把 2629 个在售/草稿系列一并拉入回收站视图——**接线实施时应改为叠加 `sale_status=off_sale`**（service.list_series_admin 的 `sale_status` 过滤在 include_deleted=true 分支仍生效，实测 #4 已证实）。
- repo 语义（`series_repo.py` L3-4/L87-89 实读）：`series` 表**无 yn 列**，软删 = `DELETE → sale_status='off_sale'`；item **无 deleted_at 专用字段**，回收站时间列仅 `created_at/updated_at`（updated_at=软删下架刷新时间）——契约缺口实披露，原型"最近变更"列用 `updated_at` 代，不做 MOCK。

### 4. restore 路由存在性（只读确认，未对真实数据执行 restore）

```
GET /openapi.json
→ ROUTE: /api/admin/courses/series/{series_id}/restore ['post']
  params: [{series_id: path, integer, required}]
  requestBody: None（无请求体）
```
运行时探测（安全，不触碰真实数据）：

```
POST /api/admin/courses/series/99999999/restore  → HTTP 404 {"code":"40400","message":"系列不存在：99999999"}
GET  /api/admin/courses/series/99999999/restore  → HTTP 405（证实 POST-only 路由真实存在）
```

- 语义（`service.py` `restore_series` L154-179 实读）：
  - off_sale → **draft**（恢复为草稿，可再上架）；成功 data：`{"series_id":..,"status":"restored"}`；
  - 系列不存在 / 非软删态 → 404；
  - `series_code` 被其它系列占用（institution_id+series_code 唯一）→ **HTTP 409，`{"code":"40901","message":"系列编码 'xxx' 已被其它系列占用，无法恢复"}`**（`error_codes.py` L113：`SERIES_CODE_CONFLICT="40901"`）→ 原型 409 冲突态文案即按此实测格式。

### 5. 彻底删除 DELETE /api/admin/courses/series/{series_id}?hard=true

- openapi 确认 query 参数：`hard: boolean 默认 false`，描述 **"true=物理真删（仅 ADMIN，且零引用）"**；
- 存在关联记录 → 409 `SERIES_IN_USE`"系列仍存在其它关联记录，无法彻底删除"（service.py L145-148）→ 原型第一步弹窗以文案披露该失败态。

---

## 二、示例行字段与实测对照表

静态示例 6 行 = `GET /api/admin/courses/series?page=1&page_size=6&sale_status=off_sale&include_deleted=true` 实测返回**原样快照**（total=56, page=1, page_size=6），页面以 proto-note 横幅 + toolbar-meta 显著标注「示例数据，接线后为真实数据」。

| # | id | series_code | series_name | delivery_mode | sale_status | created_at | updated_at | 与实测一致 |
|---|----|----|----|----|----|----|----|----|
| 1 | 2709 | rst1788614181447 | C5硬删守卫rst1788614181447 | online_live | off_sale | 2026-09-05T21:16:21 | 2026-09-05T21:16:21 | ✔ 逐字一致 |
| 2 | 2708 | rst1788614181329 | C5非法恢复rst1788614181329 | online_live | off_sale | 2026-09-05T21:16:21 | 2026-09-05T21:16:21 | ✔（+原型演示标记 `__demo_conflict`） |
| 3 | 2707 | rst1788614181030 | C5恢复测试rst1788614181030 | online_live | off_sale | 2026-09-05T21:16:21 | 2026-09-05T21:16:21 | ✔ 逐字一致 |
| 4 | 2706 | jsnn1788614180483 | JSON null 测试jsnn1788614180483 | online_live | off_sale | 2026-09-05T21:16:20 | 2026-09-05T21:16:20 | ✔ 逐字一致 |
| 5 | 2705 | jsnu1788614180344 | JSON更新jsnu1788614180344 | online_live | off_sale | 2026-09-05T21:16:20 | 2026-09-05T21:16:20 | ✔ 逐字一致 |
| 6 | 2704 | jsn1788614180224 | JSON列测试jsn1788614180224 | online_live | off_sale | 2026-09-05T21:16:20 | 2026-09-05T21:16:20 | ✔ 逐字一致 |

字段名映射（原型列 ← 实测响应字段）：系列名←`series_name`、编码←`series_code`、交付←`delivery_mode`、状态←`sale_status`（恒 off_sale，虚线 badge 沿用 task56 形态）、创建时间←`created_at`、最近变更←`updated_at`。行内不展示 `institution_id` 等未要求字段（数据保留在 JS 行对象中，接线可直接用）。

---

## 三、三视角自检

### 视角 A · 契约真实性（后端对齐）

- 列表参数/响应形状/restore 路由/硬删参数全部来自 curl+openapi+源码三重实测，头部注释「依赖端点」段完整落档；
- 主动披露 3 个契约缺口：①`status` 参数无效（正确参数是 `sale_status`）；②`include_deleted=true` 是全量不是仅软删（回收站需叠加过滤）；③无 `deleted_at`（用 `updated_at` 代"最近变更"）——均不做 MOCK；
- 409 冲突 toast 文案与实测 40901 响应逐字一致（`恢复失败（409 · 40901）：系列编码 'xxx' 已被其它系列占用，无法恢复`）；恢复语义（off_sale→草稿）写入确认弹窗文案。

### 视角 B · 交互与用户体验（送审形态完备）

- 任务要求的交互态全覆盖：**空回收站空态**（♻️ 回收站为空，demo 控制器可直达）、**恢复成功 toast 形态**（行移出+绿色 toast+可复看按钮）、**409 冲突错误态**（红色 toast；且「C5非法恢复…」行内标注"模拟 409"chip，点其恢复即触发，另有 demo 直达按钮）；
- 「恢复」= 确认弹窗形态（复用 `.confirm`/`.c-msg` 组件，文案含恢复后状态说明）；「彻底删除」= 红色危险态（`btn-danger`/`candy-red`）+ **两步确认**：第一步弹窗含「⚠ 彻底删除后数据不可恢复」警告条，第二步要求**输入系列编码完全匹配**才解锁「彻底删除（不可恢复）」按钮；
- demo 控制器提供 视图状态（成功/加载/错误/空回收站）+ 交互形态直达（恢复成功 Toast / 409 冲突 Toast / 彻底删除·两步确认），审核者无需 hunting 即可看全形态；
- 正式列表 Tab 完整保留（克隆态），回收站为默认聚焦视图；状态/排序筛选在回收站视图禁用并给 title 说明（全部恒为已下架），避免误导。

### 视角 C · 工程合规（硬性守则）

- 唯一新增文件 `admin-courses-recycle-proto.html`；`git status` 证实 admin-courses.html 无 diff（工作区其他已修改文件均为本任务开始前已存在，未触碰）；
- 样式 100% 复用 admin-courses.html 的 CSS 变量与组件类（:root 变量块、tbl-card/badge/b-dm/btn/scrim/confirm/state/sk/pager/vtabs/em-toast/gnav 全套原样克隆 + aihub-topnav-fix 同源覆盖），新增元素仅 proto-note 标注条（仅用既有变量 `--ht-fdf0e4/--candy-orange/--ht-b4600e`），**未引入新视觉语言**；
- 无外部脚本引用、无 fetch/XHR/EAPI 调用（grep 证实仅头部注释文字提及），不接线真实数据；两段内联 JS `node --check` 通过；
- 未使用 Playwright；未对真实数据执行 restore（仅用不存在 id 99999999 做只读路由探测 + openapi/read-only 确认）。

---

## 四、Gate A 签收后的接线实施清单（移交编排者）

1. `admin-courses.html` bin 视图查询改为 `sale_status=off_sale&include_deleted=true`（修正现状仅传 include_deleted 的全量问题）；
2. bin 行操作从「仅恢复」扩展为本原型形态：恢复确认弹窗（替换现 `confirm()`）+ 彻底删除两步确认（?hard=true，第二步编码输入校验）；
3. 恢复接 `EAPI.post("/api/admin/courses/series/"+id+"/restore")`（无 body），409/404 走 `em-toast` + `errMsg`（40901 文案已对齐实测）；硬删接 `EAPI.del(...+"?hard=true")`，有引用 409 SERIES_IN_USE 提示；
4. 补 task109 管理端守卫 + `window.bootAdmin()` 数据注入（本原型为纯静态，无守卫脚本，Gate A 后并入）；
5. 契约缺口跟进：如需真实"删除时间"，需后端在回收站 item 增加 `deleted_at`（当前以 `updated_at` 代，页面文案已用"最近变更"规避误导）。

## 五、遗留/降级项

- 分页在原型中为单页示意（快照单页），接线后按外层 triple `{total,page,page_size}` 翻页（56 条 → 每页 20 共 3 页）；
- 关键词/交付筛选在原型中为静态行客户端过滤，接线后改为服务端参数。
