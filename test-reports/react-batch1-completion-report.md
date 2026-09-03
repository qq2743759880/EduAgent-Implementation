# React 线 · 批 1（用户端商流动线契约对齐）完工报告

- 任务：EduAgent 优化期 · React 线批 1 — C-A（响应壳） / C-B（分页)契约对齐
- 范围：用户端 6 页 `edu-frontend/src/app/(user)/`
  - U5 `/courses` · U6 `/courses/search` · U7 `/courses/[seriesId]`
  - U8 `/my-courses` · U11 `/community` · U12 `/community/[postId]`
- 依据：`react-line-replan-v2.md §三批次1`、`task114-contract.md`(C-A)、`task115-contract.md`(C-B)、`api-client.ts`(全局解壳)、`_frontend_real_api.txt`
- 结论：**6 页全部对齐到冻结契约，typecheck 通过、vitest 492 用例全绿、semgrep 0 发现**；仅 U5/U6 需实质迁移，U7 仅注释修正，U8/U11/U12 现状已合规（无改）。

---

## 1. 每页分页消费迁移证明（改前 grep / 改后 grep 对比）

> 说明（第 0 步定位口径）：api-client 拦截器对 `{code:0,...}` 壳自动解包返回 `data`，全页透明；故"分页消费"指对 `data` 内部结构（`page_meta` vs 外层 `total/page/page_size/items`）的读取点。

### U5 `/courses` — `src/app/(user)/courses/page.tsx`（实质迁移）

改前阅：`data?.page_meta` 解构，读 `pageMeta.total/page/page_size`：
```ts
const pageMeta = data?.page_meta ?? { page, page_size: PAGE_SIZE, total: 0, total_pages: 1, has_more: false };
// 共 {pageMeta.total.toLocaleString()} 门课程
<Pagination page={pageMeta.page} pageSize={pageMeta.page_size} total={pageMeta.total} .../>
```
改后（gs 验证已无 `page_meta` 消费）：
```ts
const total = data?.total ?? 0;
const pageSize = data?.page_size ?? PAGE_SIZE;
const currentPage = data?.page ?? page;
// 共 {total.toLocaleString()} 门课程
<Pagination page={currentPage} pageSize={pageSize} total={total} .../>
```

### U6 `/courses/search` — `src/app/(user)/courses/search/page.tsx`（实质迁移）

改前阅：`data?.page_meta` 解构，读 `pageMeta.total/page/total_pages`。
改后：外层 `data?.total` 计算 `total`、`totalPages = Math.max(1, Math.ceil(total/pageSize))`（C-B 契约 §1.4：`total_pages` 不再下发，前端自算）；头部与 `PaginationBar` 用 `data?.page ?? page`。已无 `page_meta`。

### U7 `/courses/[seriesId]` — `_components/CourseDetailClient.tsx`（仅注释修正）

审计：cohorts 消费点 `cohortsQ.data?.items ?? []` 本就读**外层 items**（api-client 解壳后 `data` 即 `{total,page,page_size,items}`），无 `page_meta` 读取，行为无需改。仅更新过时注释（`返回分页壳 {items,page_meta}` → `返回外层 {total,page,page_size,items}`）。
C-A 核查：`createOrder`（`order.order_no`）、coupons（`templates`、`myCouponsQ.data?.items`）、favorites（`favQ.data?.items?.some`）全部经拦截器单层解壳读取，无 `.data.data` 二次解包。

### U8 `/my-courses` — `_components/MyCoursesClient.tsx`（现状合规，无改）

审计：`getEnrolledCohorts()` 返回裸数组（`EnrolledCohort[]`）；C-A 后后端 `RespWrapMiddleware` 包成 `{code:0,data:[...]}`，api-client 拦截器解壳返回数组（`isEnvelope` 对数组直接返回 `false`，等价透传数组）。消费 `q.data ?? []` 按数组遍历分组 → **类型与消费一致**。三 tab（active/completed/refunded）本地分组 + badge 计数真实；`q.isError` → `ErrorState` + 重试，**错误不吞**。

### U11 `/community` — `src/app/(user)/community/page.tsx`（现状合规，无改）

审计：`listPosts` 返回类型 `PostListResponse = {total,page,page_size,items,mine_total_posts}` 本就外层 triple；消费 `data?.total`/`data?.items`，无 `page_meta`。`isError → PostErrorState` + 重试，错误不吞。

### U12 `/community/[postId]` — `page.tsx` + `CommentSection.tsx`（现状合规，无改）

审计：详情 `getPostDetail` 返回 `PostDetail` 直接读字段，浏览量 `detail.view_count`（GET 自动 +1）；评论区 `CommentSection` `listComments` → `CommentListResponse {total,page,page_size,items}` 读外层 `.items`/`.total`，分页 `totalPages=ceil(total/PAGE_SIZE)`；回帖(+2 分)/评论点赞软切换/invalidate 查询闭环完整；`commentsQ.isError → 重试 UI`、点赞失败 `toast + console.error`（R-7 不吞错）。

### 共享类型 — `src/lib/api/curriculum.ts`（迁移分页消费必须动的共享类型）

C-B 后权威 `{total,page,page_size,items}`，`page_meta` 降为**可选**兼容字段（值同源派生；弃用期移除后不破坏）：
```ts
export interface SeriesListData { total: number; page: number; page_size: number; items: SeriesListItem[]; page_meta?: PageMeta; }
export interface CohortListData { total: number; page: number; page_size: number; items: Cohort[]; page_meta?: {...}; }
```
（`page_meta` 置可选而非删除，避免破坏批 3 / admin-courses 等仍然消费的兼容窗口。）

---

## 2. 壳兼容核查结论（C-A）

对 6 页全量 grep `\.data\.data|resp\.data|response\.data`：**无任何二次解包残留**；亦无 `resp.data.code` 手动读取。所有 read/mutation 均走 `http.get/post/...` 经 api-client 拦截器（`code===0 → 返回 data`）单层解壳。核查路径：
- createOrder/coupons/favorites（U7）、enrollments 裸数组→壳（U8）、posts/comments 分页壳（U11/U12）、series/cohorts 分页壳（U5/U6/U7）——全部已对齐，无 `.data.data`。

---

## 3. 验证输出摘要

### TypeScript（`cd edu-frontend && npx tsc --noEmit`）
- **`src/` 全树通过（0 错误）**。
- 仅剩预存错误位于 **`e2e/*.spec.ts`（Playwright E2E，`03-main-flow` / `probe-admin-types` 等）**——这些文件**本批未触碰、已 git 跟踪**，与 6 页无关，且 Playwright 被项目禁用，不在本批范围。（预存基线如 `e2e/helpers.ts(63)` 类型 `Promise<number>` 与 `0` 比较等，均非本次改动引入。）

### Vitest（`cd edu-frontend && npx vitest run`）
- **Test Files 72 passed (72) · Tests 492 passed (492)**，含 curriculum / community / orders / enrollments 相关域全部通过。
- 聚焦：`courses/page.test.tsx`(5) + `courses/[seriesId]/page.test.tsx`(9) = 14 全绿。

---

## 4. 新增单测文件名与断言

`edu-frontend/src/app/(user)/courses/page.test.tsx`（U5）：
- 同步把该文件 `makeData` 对齐为 C-B 权威结构 `{total,page,page_size,items}`（移除 `page_meta` 字面量）。
- **新增用例**：`分页权威字段：总数/页码/分页尺寸从外层 triple 读取（page_meta 兼容字段不再消费）`
  - 仅返回外层 `{total:45, page:3, page_size:15, items:[样本]}`（天然不含 page_meta，若旧代码读 `page_meta.total` 将得到 0）。
  - 断言 ① 渲染「共 45 门课程」（证明 `data.total` 外层读取）；
  - 断言 ② Pagination 渲染「第 31-45 条 / 共 45 条」（`start=(page-1)*page_size+1=31`，证明 `data.page=3` 外层读取，读到 fallback=1 会显示「第 1-15 条」）。

`edu-frontend/src/app/(user)/courses/[seriesId]/page.test.tsx`（U7）：把 5 处 `listSeriesCohortsMock` mock 从 `{items,page_meta}` 对齐为外层 `{total,page,page_size,items}`（保持断言不变，修正类型一致性）。

---

## 5. 资产消费证据（真实调用 / 读取的 skill 与文档 + 自检发现）

### 真实调用的 skill（Skill 工具）
1. **`frontend-browser-testing`** — 确认项目测试栈 Vitest(v4)+@testing-library+user-event；状态矩阵（loading/empty/error/success）覆盖要求，U5/U6/U7 测试四态齐备；"不测试实现细节"约束下用渲染输出断言外层 triple。
2. **`security`** — 按 skill 三阶段执行：先 probe 到 `semgrep 1.175.0` + `gitleaks` 可用；skill 自带 `security-scan.mjs` 核心脚本**未随安装包提供**（路径不存在，属 skill 内核降级）→ 按降级规则改为**直接以 semgrep 对改动文件实扫**：`--config p/javascript` **74 rule · 0 findings**（`p/security-audit` 因无网拉取 ruleset 失败，已回退离线 `p/javascript`）。手动审计：total/page_size 纯数字、总数经 React 文本转义，无 XSS/DOM 注入；错误路径经 `error.message` 转义渲染 / `toast`，未吞静默、无密钥泄露；`page_meta` 改可选不造成类型安全缺口。
3. **`review-bugbot`** — skill 要求 spawn `bugbot` 子 agent，但**当前会话无子 agent spawn 工具**（无法真正启动 Bugbot），故按 `Diff: uncommitted changes` 方法**(自审代跑)**：对完整 `git diff --ignore-cr-at-eol` 逐文件查证，**未发现逻辑缺陷**——外层 triple 消费正确、`page_meta` 清理彻底（页面层无残留）、`totalPages`/`pageSize` 回退一致、无回归。

### 读取的权威文档
- `.ai-hub/plans/react-line-replan-v2.md`、`.ai-hub/plans/handoffs/task114-contract.md`（C-A）、`.ai-hub/plans/handoffs/task115-contract.md`（C-B）、`AGENTS.md`、`edu-frontend/src/lib/api`（api-client/curriculum/coupons/favorites/orders/enrollments/community）。

### 自检发现并修复的问题
1. 共享分页类型 `SeriesListData`/`CohortListData` 缺 C-B 外层 triple 字段，导致 U5/U6 迁移后编译不过 → 已在 `curriculum.ts` 补 `total/page/page_size`（`page_meta` 置为可选兼容）。
2. `courses/page.test.tsx` 旧 `makeData` 用 `page_meta` 字面量，与 C-B 结构冲突 → 已重构为外层 triple + 新增外层分页断言。
3. `courses/[seriesId]/page.test.tsx` 5 处 `listSeriesCohortsMock` 旧 `{items,page_meta}` 形状不再满足 `CohortListData` → 已对齐外层 `{total,page,page_size,items}`。
4. （skill 自审）新增外层分页断言初版用了**同步** `getByText`，query 未解析即断言会失败 → 改为异步 `await findByText` 后通过。

### 说明
- 本批唯一实质代码改动集中在 U5/U6 两页 + 1 个共享类型文件 + 2 个测试文件；U7 仅注释，U8/U11/U12 无改动（现状已合规）。改动集 `git status` = 5 个 M 文件（均在授权范围），未触碰 `edu-agent/` 后端、未 `git add`、未 commit。