# task106 完工报告 · 管理端表格列错位 + admin-mcp 契约更正

- 日期：2026-09-02
- 分支：`feature/opt-waves`（未切分支、未 commit）
- 范围：仅改 4 个文件 —— `admin-courses.html` / `admin-users.html` / `admin-mcp.html` / `admin-rag-upload.html`
- 契约权威：后端 `schemas.py` / `app/knowledge/routers/upload.py`；字段以 curl 独立实证为准

---

## 一、改动清单

| 文件 | 改动 |
| --- | --- |
| `admin-courses.html` | 注入改为按表头逐列映射（系列=series_name+series_code、交付模式=delivery_mode、状态=sale_status、创建时间=created_at）+ 操作列 button（alert 占位，标注 task117）；catch 行内错误提示 |
| `admin-users.html` | 注入 7 列逐列对齐（用户=real_name+username/user_id、手机=phone、角色=role_code、状态=status、注册时间=created_at、最近登录=last_login_at）+ 操作列 button（task117）；catch 行内错误提示 |
| `admin-mcp.html` | ① 头注释契约 `/api/admin/mcp/servers` → `/api/mcp/servers`（含 tools/call-log 路径全部更正）；② Server 表 6 列逐字段对齐（display_name+server_code、transport、last_health_ok→健康、tool_count、last_error）+ 操作列；catch 行内错误提示 |
| `admin-rag-upload.html` | ① 修正注入语法错误（多余 `}`）；② 任务表 8 列按实测字段重对齐（task_id/task_type/source_files数/imported_chunks+total_chunks 进度/succeeded 状态词/error/created_at）+ 操作列；③ 补齐「集合数」`data-collection-count` 目标 DOM（原注入找此元素但 DOM 不存在）；catch 行内错误提示 |

> 说明：操作按钮点击维持 `alert(...)` 占位并标注「task117 接线」，按钮渲染可见可点、位于独立操作列，不被数据列覆盖。

### 守则符合性
- ✅ 只改 4 个文件；未接 CRUD 写路径（归 task117）；注入未重定义全局 `$` / `renderSides`；未用 Playwright；未 commit；未改 `edu-api.js`。

---

## 二、四个列表端点 curl 真实字段（独立实证，后端 8000）

### 1. GET /api/admin/courses/series?page=1&page_size=20（admin 鉴权）
```
HTTP 200 code=0
ITEM_KEYS: ['id','institution_id','delivery_mode','series_code','series_name','description',
            'cover_url','target_learner_identity_codes','target_learning_goal_codes',
            'target_grade_codes','sale_status','created_by','created_at','updated_at']
```
- 注入已用字段：`series_name`/`series_code`/`delivery_mode`/`sale_status`/`created_at`/`id` —— 全部命中实测。

### 2. GET /api/admin/users?page=1&page_size=3（admin 鉴权，裸 DTO）
```
{"total":100017,"page":1,"page_size":3,"items":[{"user_id":100019,"username":"itest-newuser",
 "real_name":null,"phone":null,"email":null,"role_code":"student","status":1,"yn":1,
 "created_at":"2026-08-30T21:38:14","updated_at":"2026-08-30T21:38:14","last_login_at":null}, ...]}
```
- 注入已用字段：`real_name`/`username`/`user_id`/`phone`/`role_code`/`status`/`created_at`/`last_login_at` —— 全部命中。

### 3. GET /api/mcp/servers?page=1&page_size=50（admin 鉴权，已验证 ADMIN 门禁）
```
HTTP 200 code=0
ITEM_KEYS: ['id','server_code','display_name','description','provider','transport','enabled',
            'yn','created_by','created_at','updated_at','last_health_at','last_health_ok',
            'last_error','tool_count']
```
- 无效 token 鉴权验证：`BAD_TOKEN /api/mcp/servers => HTTP 401 code=40101`（证明 `/api/mcp/servers` 有 ADMIN 鉴权，前端走此路由正确）。
- 注入已用字段：`display_name`/`server_code`/`transport`/`last_health_ok`/`tool_count`/`last_error`/`id` —— 全部命中。

### 4. GET /api/knowledge/tasks?page=1&page_size=10（admin/manager 鉴权）
```
{"items": [], "total": 0, "page": 1, "page_size": 10, "total_pages": 0}
```
- 当前无数据（items 空）；items 元素字段引自后端契约（`app/knowledge/routers/upload.py` L420-421）：
  `task_id, task_type, tenant_id, visibility, status, total_chunks, imported_chunks, source_files[], error, created_at, started_at, finished_at`
- **关键修正**：status 词汇表为 `pending / running / succeeded / failed`（`succeeded`，非 demo 用的 `done`）；文件数取自 `source_files[]` 数组长度（无 `file_count` 字段）；分块进度列 `imported_chunks / total_chunks`。
- 注入已按上述字段重对齐：`task_id`/`task_type`/`source_files`(len)/`imported_chunks`+`total_chunks`/`status`/`error`/`created_at`。

---

## 三、列名 → 取值字段对照（GWT 最低机验：注入行渲染列数 === 表头列数）

| 页面 | 表头列数 | 注入 `<td>` 数 | 列名 → 取值字段 |
| --- | :---: | :---: | --- |
| admin-courses | 5 | 5 | 系列→`series_name`+`series_code`；交付模式→`delivery_mode`；状态→`sale_status`；创建时间→`created_at`；操作→button |
| admin-users | 7 | 7 | 用户→`real_name/username/user_id`；手机→`phone`；角色→`role_code`；状态→`status`；注册时间→`created_at`；最近登录→`last_login_at`；操作→button |
| admin-mcp | 6 | 6 | Server→`display_name`+`server_code`；传输→`transport`；健康→`last_health_ok`；工具数→`tool_count`；上次错误→`last_error`；操作→button |
| admin-rag-upload | 8 | 8 | 任务ID→`task_id`；类型→`task_type`；文件数→`source_files` 长度；分块进度→`imported_chunks / total_chunks`；状态→`status`；错误明细→`error`；创建时间→`created_at`；操作→button |

---

## 四、GWT 自评

| # | Given / When / Then | 结果 | 证据 |
| --- | --- | :---: | --- |
| 1 | 注入把 4~5 值塞进 6~8 表头 → 逐列映射 + 操作列保留 | PASS | 机验 4 页 td 数与表头数全等（对照表见第三部分） |
| 2 | 操作按钮必须可见可点、不被数据列覆盖 | PASS | 4 页抓取到 `<button` 且位于末列；click 保留 alert 占位标注 task117 |
| 3 | admin-mcp 契约更正为实际路由 `/api/mcp/servers` | PASS | 机验「无 /api/admin/mcp 残留」clean + 「含 /api/mcp/」pass；BAD_TOKEN→401 实证 ADMIN 鉴权 |
| 4 | Server 表字段按 curl 实测逐字段对齐 | PASS | ITEM_KEYS 逐字段命中（见二.3） |
| 5 | rag collections 计数补目标 DOM | PASS | 新增 `data-collection-count` 元素存在；注入优先写它、回退 `#hRows` |
| 6 | rag 任务表列对齐 `/api/knowledge/tasks` 实测字段 | PASS | 按契约字段重对齐；`succeeded` 状态词修正、`source_files` 计数、进度列修正 |
| 7 | 各页 catch 不再完全静默（接 EAPI.onError / 行内提示） | PASS | 4 页注入 catch 均写「⚠ …加载失败：…（task122 toast）」行内提示；机验「无静默 catch」all clean |

---

## 五、最低机验输出（`node edu-frontend\_task106_verify.js`）

```
PASS admin-courses.html 注入行列数(5)===表头列数(5) :: td=5 head=5
PASS admin-users.html   注入行列数(7)===表头列数(7) :: td=7 head=7
PASS admin-mcp.html     注入行列数(6)===表头列数(6) :: td=6 head=6
PASS admin-rag-upload.html 注入行列数(8)===表头列数(8) :: td=8 head=8
PASS admin-mcp.html 无 /api/admin/mcp 残留 :: clean
PASS admin-rag-upload.html 集合计数目标 data-collection-count 存在
ALL OK
```
- 4 页脚本语法 ALL PASS（admin-rag 曾因多余 `}` 报 `missing ) after argument list`，已修复并复验）。
- 操作列按钮存在：4 页 grep `<button` 均命中。
- 无静默 catch：4 页 grep `catch(function(){})` 均 clean。

---

## 六、降级 / 遗留（未来任务）

- 操作按钮点击仅 alert 占位，真实 CRUD 写路径（PATCH/POST ……）归 **task117** 接线。
- toast 统一样式（提示 UI 规范）归 **task122**；本 task 仅接 EAPI 行内错误提示占位。
- `/api/admin/rag/collections` 为 rag 集合计数来源；若后端该路由后续冻结/更名，需同步（task36 RAG 上传链路仍标记未冻结契约）。