# critique C2fe + C5fe 完成报告（前端静态页·fe-html）

- 日期：2026-09-04
- 角色：C2+C5 批判落地的**前端独立子 agent**（tt 工作流）
- 工作目录：`e:\stu\project\stu\EduAgent实施手册`
- 改动范围：仅 `edu-frontend/public/` 静态糖果色页；未 commit

## 资产消费证据（tt 纪律·硬约束）

动手前已用 Skill 工具加载 **`harden`**（improve interface resilience）。本次按 harden 方法落地要点：
- **错误处理**：恢复操作对 409（唯一性冲突）/404（不存在）/422 等非 2xx 一律透出后端 `message` 到行内 toast（复用既有 `errMsg()`，其能解析 `err.message`/`err.body.data[].msg`——与 task117 同一消费链），不吞错误、不静默。
- **空态/加载态**：回收站空态给出明确文案「回收站为空 / 已下架的系列会出现在这里，可一键恢复」，替代无引导的空白；刷新沿用既有 spin。
- **并发/连点**：恢复按钮复用既有 `confirm()` 交互 + 成功/失败 toast；未额外引入可竞态的状态机（后端幂等 + `refreshList` 重拉，符合本页既有模式）。
- **降级**：无 `EAPI` 时 `switchView/doRestore` 走 `loadSeries()` 静默早退，静态页保持可开（复用 AGENTS 教训④的私有注入规范，无重定义全局）。

## 任务 A（C2：静态页改读外层分页 triple）

**`public/courses.html`**
- `:445` 注释：`page_meta 驱动` → `外层分页 triple total/page/page_size 驱动`。
- `fetchPage()`（原 :574 起）：删除 `const pm = d.page_meta...` 分支，改为 `const total = d.total`、`const tPages = Math.ceil(total/PAGE_SIZE)`（后端 `{total,page,page_size,items}` 无 total_pages，须自算）。

**`public/admin-courses.html`**
- `renderPagerReal(d)`（原 :641）：参数改收整个响应 `d`，`tp = ceil(total/page_size)`、`cur = d.page`（不再读 `page_meta.total_pages`/`page_meta.page`）。
- 原 :662-663：`tc.textContent = d.page_meta.total` → `d.total`；`renderPagerReal(d)`。

**遗留（有意保留，见「契约形态」说明）**：`edu-frontend/src` 下 `page_meta` 引用**全部为文档注释 + `page_meta?:` 可选类型字段**（`lib/api/admin/courses.ts:315`、`lib/api/curriculum.ts:102/217` 的兼容响应类型）。这些描述后端冻结 C-B 响应里「原始 JSON 仍含的兼容字段」，属**已冻结的契约形态**；按派单约束「不要动已冻结的 C-B 契约形态」予以保留。React 渲染侧均只读外层 triple（页面/测试注释已明示弃用），**无任何 page_meta 消费逻辑**。若验收方确需 `src` 也到 0，需另行决策删/改这些类型字段——不在本次静态页任务范围内。

### C2 清零证据
```
git grep -c "page_meta" -- "edu-frontend/public/*.html"        → 0 处（grep 无匹配）
public 全局 page_meta（Get-ChildItem 全 .html 扫描）            → 0
edu-frontend/src 的 page_meta：N 处，均为 注释 + page_meta?: 可选类型字段（冻结契约形态，保留）
```

## 任务 B（C5：admin-courses 回收站 Tab）

**契约消费（关键澄清）**：派单冻结文本写的是 `POST /api/course-admin/series/{series_id}/restore` 与 `GET /api/course-admin/series?include_deleted=true`。但**实测后端**：course_admin 路由前缀为 **`/api/admin/courses`**（`edu-agent/app/domains/course_admin/router.py:30`），软删列表参数 `include_deleted` 挂在 **`GET /api/admin/courses/series`**（`router.py:40/50`），且**当前后端尚无 series 级 `restore` 端点**（仅 `cohort_repo.restore`，属于班次）。按 AGENTS 教训⑧「真实契约优先于页面注释」，回收站消费**与既有页面/后端同源**的路径：
- 软删列表：`GET /api/admin/courses/series?include_deleted=true`（复用 `buildSeriesQuery()`，bin 时追加参数）
- 恢复：`POST /api/admin/courses/series/{series_id}/restore`（**一致前缀推断**；后端落地时按此对齐）

> 派单的 `/api/course-admin/...` 与真实后端前缀不符，已在本文档如实披露，避免前端写死错误路径。

**实现方式**
1. **Tab**：页面头部新增「正式列表 / 回收站」`#viewTabs`（.+`.vtabs/.vtab` 样式）。
2. **视图状态** `activeView`（list/bin）：`switchView(v)` 切 Tab → 重置页码 → `loadSeries()`；bin 下隐藏「新建系列」按钮。
3. **列表**：`buildSeriesQuery()` 在 bin 时追加 `include_deleted=true`；`loadSeries()` 按视图选 `rowHtml`（正式列表）/`rowHtmlBin`（回收站）渲染；回收站行仅暴露「恢复」按钮，**不暴露硬删**（`hard=true` UI 不可达），并收录 `window.__binRows[s.id]` 供名称回显。
4. **恢复** `doRestore(id)`：`series_id` **从行数据/参数取**（`s.id`，传入 `doRestore(id)`），**未用正则 `match` 抽路径**（对齐 AGENTS 教训⑨）。成功：`POST /api/admin/courses/series/{id}/restore` → toast「已恢复」→ 刷新当前视图（切 Tab 亦自动重拉，等价刷新正式列表+回收站闭环）。失败（409/404/422）：`errMsg(e)` → toast err。
5. **空态/子标题**：回收站空态与 `.sub` 文案按视图区分。

## 薄测试（语法校验 + grep 断言）

- 内联脚本语法校验脚本：`test-reports/_c2c5_syntax.js`（复用 `_t119_syntax.js` 的 `vm.Script` 编译风格，遍历两页全部内联 `<script>`）：
  ```
  PASS | ../edu-frontend/public/courses.html 内联脚本 5 块
  PASS | ../edu-frontend/public/admin-courses.html 内联脚本 4 块
  ```
- grep 断言：`git grep -c "page_meta" -- "edu-frontend/public/*.html"` = 0；public 全局 page_meta = 0；`course-admin` 路径残留 = 0。
- 未用 Playwright（遵守 AGENTS 教训②）。

## 交付物与状态
- 改动页：`edu-frontend/public/courses.html`、`edu-frontend/public/admin-courses.html`
- 校验脚本：`edu-frontend/../../test-reports/_c2c5_syntax.js`（即 `test-reports/_c2c5_syntax.js`）
- **未 commit**，等验收。