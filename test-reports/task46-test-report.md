# 功能测试报告 task46（课程详情页 React 实现）

> 测试人：fe-tester（独立测试，不参与开发）
> 被测对象：`edu-frontend`（Next.js 16.3 + React 19 + Tailwind v4 + shadcn/Base UI）
> 被测路由：`/courses/[seriesId]` 课程详情页（series→cohort→module→session 四级展示 + 班次联动 + 领券 + 收藏 + 报名 + Tabs 四栏 + 四态）
> 测试时间：2026-08-20

## 判定：APPROVED

全部 6 项检查通过，无 P0/P1 阻断问题。唯一记录项为仓库既有的 eslint 警告（非 task46 引入），见问题清单。

---

## 一、逐项检查结果

### 1. vitest 全量测试 — ✅ 通过

命令：`npx vitest run`

```
Test Files  49 passed (49)
     Tests  365 passed (365)
   Duration  37.43s
```

- **总用例数：365，通过 365，失败 0**
- task46 相关测试全绿：
  - `src/app/(user)/courses/[seriesId]/page.test.tsx` — **8/8 passed**（四态 loading/error/empty/success + 班次联动 + 未登录跳转 + 登录后报名/收藏/领券）
  - `src/components/curriculum/course-detail-components.test.tsx` — **7/7 passed**（CohortList / FavoriteButton / CourseDetailHero / CourseDetailSyllabus / CouponPicker）

### 2. tsc 类型检查 — ✅ 通过

命令：`npx tsc --noEmit` → 退出码 0，**0 错误**。

### 3. eslint 检查 — ✅ 通过（task46 文件 0 错误 0 警告）

- task46 全部 12 个文件单独跑：`npx eslint <task46 文件...> --max-warnings=0` → 退出码 0，**0 错误 0 警告**
- 项目默认 lint：`npm run lint` → 退出码 0（0 错误，17 条警告，全部为既有文件）
- 严格模式 `npx eslint src --max-warnings=0` → 退出码 1（0 错误，12 条警告）

说明：`--max-warnings=0` 失败源于仓库**既有**警告（`react-hooks/set-state-in-effect` ×8、`no-unused-vars` ×4），分布在 `courses/search/page.tsx`、`my-courses/MyCoursesClient.tsx`、`chat/ChatSessionSidebar.tsx`、`learning/*`、`ui/offline-indicator.tsx`、`ui/stepper.tsx` 及两个测试文件，**无一条落在 task46 文件内**。其中 `set-state-in-effect` 已被 eslint.config.mjs 显式降级为 warning（P3-A 注释：React Compiler 优化建议，项目多处有意使用该模式），属既有约定，不阻断 CI。

### 4. 硬编码色值审计 — ✅ 通过

命令：`rg "bg-\[#|text-\[#|border-\[#|bg-\[rgb|#[0-9a-fA-F]{3,8}\b|style=\{\{" src/components/curriculum src/app/(user)/courses`

- 结果：**无违规**。仅命中 2 处 `style={{ width: ... }}`（CohortList.tsx:77 容量进度条、ReviewList.tsx:70 评分条），为动态宽度非色值，属合理用法。
- 全部颜色走 Tailwind 语义 token（`bg-card` / `text-candy-orange` / `border-candy-purple` 等），无内联十六进制色值。

### 5. next build — ✅ 通过

命令：`npx next build` → 退出码 0

```
✓ Compiled successfully in 1747ms
✓ Generating static pages using 15 workers (18/18) in 1525ms
```

- `/courses/[seriesId]` 路由正常注册（ƒ Dynamic，server-rendered on demand），构建产物无错误。

### 6. Playwright 截图验证 — ✅ 通过（后端不可用 → 验证前端降级）

后端 API（`http://127.0.0.1:8000`）与 dev server 均未运行，按任务要求验证前端降级处理。启动 `next dev -p 3000` 后以 Playwright（Chromium 1.62.1）验证：

| 场景 | 期望 | 结果 | 证据 |
|---|---|---|---|
| `/courses/1001`（有效 id，后端不可用） | error 态（ErrorState + 重试） | ✅ | `[role=alert][data-slot=error-state]` 渲染「加载失败 / 网络错误，无法连接后端服务，请检查网络 / 重试」 |
| `/courses/abc`（无效 id） | empty 态（EmptyState） | ✅ | `[role=status][data-slot=empty-state]` 渲染「课程不存在 / 链接无效或课程已被下架 / 返回课程中心」 |

截图：`test-reports/screenshots/task46-loading.png`、`task46-error.png`、`task46-empty.png`
验证脚本：`edu-frontend/scripts/task46-playwright-check.mjs`（可复跑）

---

## 二、发现的问题（分级）

**无 P0 / P1 问题。**

| # | 严重度 | 位置 | 说明 | 建议 |
|---|--------|------|------|------|
| 1 | P2（记录项） | 仓库既有文件（非 task46） | `npx eslint src --max-warnings=0` 因 12 条既有警告退出码 1（0 错误）。警告为 `react-hooks/set-state-in-effect`（eslint.config.mjs 已显式降级为 warn，P3-A 注释）与 `no-unused-vars`，全部位于 task46 之外的文件。task46 自身 0 错误 0 警告 | 非 task46 验收阻断项；如需 CI 严格化，可另行清理既有警告或对既有文件加豁免 |

---

## 三、结论

**APPROVED**

- 365/365 测试通过（含 task46 页面 8 项 + 组件 7 项）
- tsc 0 错误；next build 成功；硬编码色值 0 违规
- task46 文件 eslint 0 错误 0 警告
- 后端不可用场景下 error / empty 降级态经 Playwright 实测渲染正确

无 P0/P1 问题，无需返工。唯一 P2 记录项为仓库既有 eslint 警告，与 task46 实现无关。
