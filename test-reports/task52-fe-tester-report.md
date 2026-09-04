# task52 /community/[postId] 帖子详情页 — 独立验收报告（fe-tester）

- 验证日期：2026-08-22
- 验证人：fe-tester 独立子代理（与开发主对话隔离，独立运行命令、独立判断）
- 前端目录：`E:\stu\project\stu\EduAgent实施手册\edu-frontend`
- 技术栈：Next.js 16.3.0 + React 19.2.8 + Tailwind v4 + React Query 5 + Vitest 4.1.10

## 0. 交付物确认

| 交付物 | 路径 | 状态 |
|---|---|---|
| P22 规范 | `.opencode\plans\doc-frontend-design-spec.md` | 存在，git diff 确认新增 P22（L742） |
| 效果图 | `test-reports\fe-html\community-post.html`（163KB） | 存在，含详情头/正文/评论/锁定态/404 演示（任务声明已 APPROVED） |
| ReactButtons.tsx | `edu-frontend\src\components\community\ReactButtons.tsx` | 存在（8/22 修改） |
| CommentSection.tsx | `edu-frontend\src\components\community\CommentSection.tsx` | 存在（8/22 修改） |
| [postId]/page.tsx | `edu-frontend\src\app\(user)\community\[postId]\page.tsx` | 存在（8/22 修改） |
| ReactButtons.test.tsx | `edu-frontend\src\components\community\ReactButtons.test.tsx` | 存在（task51 已提交，task52 未改动，6 测试全过） |
| CommentSection.test.tsx | `edu-frontend\src\components\community\CommentSection.test.tsx` | 存在（8/22 修改） |
| [postId]/page.test.tsx | `edu-frontend\src\app\(user)\community\[postId]\page.test.tsx` | 存在（8/22 新建，untracked） |

## 1. 验证步骤结果

### 1.1 类型检查 `npx tsc --noEmit`
- 结果：**0 错误**（exit 0）— PASS

### 1.2 ESLint `npm run lint`
- 结果：**0 错误，16 warnings**（exit 0）
- 其中 **1 个 warning 落在 task52 文件**：
  - `CommentSection.tsx:16:46` — `'MessageCircle' is defined but never used`（@typescript-eslint/no-unused-vars）
- 其余 15 个 warning 均在非 task52 文件（scripts/*.mjs、courses/search、chat、curriculum、learning、ui 等历史遗留）
- 结论：**FAIL（lint 验收项）** — 验收标准要求「warning 需确认不在 task52 的 3 个组件/页面文件中」，未满足
- ✅ **复验（2026-08-22 09:00）**：已删除 `MessageCircle` import，对 task52 三文件单独跑 `npx eslint` → **0 问题（exit 0）**，转 PASS

### 1.3 单元测试 `npm run test`（vitest run）
- 结果：**58 个测试文件 / 428 个测试全部通过**（exit 0）
- task52 专项：
  - `ReactButtons.test.tsx`：6/6 通过（定向回写 like、不覆盖兄弟字段、软切换取消、favorite 定向、失败不更新计数）
  - `CommentSection.test.tsx`：5/5 通过（分页 C2 下一页、单页无分页器、总数展示、回帖成功、锁定禁用）
  - `[postId]/page.test.tsx`：3/3 通过（成功渲染、404 ErrorState+CTA、锁定帖操作行隐藏+评论禁用）
- 附带 stderr 提示（非失败）：`CommentSection.test.tsx > 回帖成功` 用例触发 React Query 警告
  `Query data cannot be undefined ... ["community","comments",1,1]` — 回帖成功后 invalidateQueries 触发重拉，但 mock 仅设置一次 `mockResolvedValueOnce`，第二次调用返回 undefined。属测试 mock 卫生问题，非产品缺陷，不影响通过。
- ✅ **复验（2026-08-22 09:00）**：已将该用例改为 `mockResolvedValue`（非 Once），重跑 CommentSection 测试 5/5 通过，警告消除

### 1.4 构建 `npm run build`
- 结果：**构建成功**（exit 0），`/community/[postId]` 以 **ƒ（Dynamic）** 出现在路由表
- 结论：PASS

## 2. 4 项 grep 审计（仅 task52 3 个 React 文件）

| # | 审计项 | 命令模式 | 命中 | 结论 |
|---|---|---|---|---|
| a | 硬编码 hex 颜色 | `#[0-9a-fA-F]{3,8}\b` | 0 | PASS |
| b | 内联 style 颜色 | `style=\{\{` | 0 | PASS |
| c | 禁闭色 bg-candy-red | `bg-candy-red` | 1 | PASS（仅 `CommentSection.tsx:141` 错误态「🔄 重试」按钮，属允许范围） |
| d | 任意字号 | `text-\[\d+px\]` | 0 | PASS |

## 3. 代码审查结论

### 3.1 ReactButtons.tsx — 通过
- 点赞/收藏均用 `useMutation`（R-7）✓
- `onSuccess` 按 target 定向回写：`onCountsChange?.("like", {active, count})` / `("favorite", ...)`，不整体覆盖兄弟字段 ✓（单测第 3 条专门验证）
- `points_awarded > 0` 时回调 `onPointsAwarded` ✓
- 失败不静默吞错：依赖全局 `MutationCache onError`（`src/lib/query-client.ts` `globalOnError`）→ toast 错误信息；401/403 额外 console.error ✓（与全站 R-7 约定一致）
- 糖果绿/黄 toggle + 3D 实底阴影（`shadow-[0_4px_0_color-mix(...)]`）✓

### 3.2 CommentSection.tsx — 通过（1 个 lint 问题见 §4）
- 评论分页 C2（‹ 页码 › 共 N 条，`CommentPager` + `aria-label="评论分页"`）✓
- 回帖成功：`toast.success("回帖成功")` + `invalidateQueries({queryKey:["community","comments",postId]})`（前缀匹配，全页失效）+ `onCommentCountChange?.(1)` ✓
- 锁定帖：textarea `disabled={locked}` + placeholder「本帖已锁定，无法评论」+ 发布按钮禁用 ✓
- 评论点赞软切换：`toggleCommentLike` → 响应回填 `setLiked(resp.active)` / `setLikeCount(resp.total_count)`；失败 `toast.error` + `console.error`（不吞错）✓
- 四态：loading 骨架（role=status）/ error（role=alert + 重试）/ empty（role=status）/ 列表 ✓

### 3.3 [postId]/page.tsx — 通过
- 详情头（返回/版块 Badge/置顶/锁定/标题/作者行）+ 操作行 ✓
- 锁定帖：操作行隐藏点赞/收藏 + 锁定 banner（`bg-candy-orange-soft`）+ 评论区禁用 ✓
- 404 → `NotFoundCard`（`role="alert"` + 「帖子不存在」）+ 「← 返回列表」CTA（`router.push("/community")`）✓
- 403/404 语义区分：`postDetailErrorMessage` — 403「你没有权限查看该帖子」/ 404「帖子不存在或已被删除」，其余透传后端 message ✓
- `onCountsChange` 定向回写（setLikeOverride / setFavOverride 分离）✓；`onPointsAwarded` → toast「+N 积分」✓
- 正文 MarkdownView 渲染 ✓

### 3.4 MarkdownView.tsx — 未被本次修改
- git diff 为空，确认未改动；历史遗留 `text-[15px]`（L27）按要求不动 ✓

## 4. 发现的问题清单

| # | 严重度 | 文件 | 问题 | 状态 |
|---|---|---|---|---|
| P2 | 低（lint 验收项违规） | `CommentSection.tsx:16` | 未使用的 `MessageCircle` import（lucide-react），触发 ESLint warning，违反「warning 不在 task52 文件」验收标准。修复：删除该 import（一行） | ✅ 已修复（复验 0 问题） |
| P3 | 极低（测试卫生） | `CommentSection.test.tsx`（回帖成功用例） | invalidateQueries 重拉时 mock 耗尽导致 React Query stderr 警告「Query data cannot be undefined」。不影响通过，建议补第二个 `mockResolvedValueOnce` | ✅ 已修复（改 `mockResolvedValue`，复验 5/5） |

## 5. 最终结论：**PASS（复验后）**

- 全部功能/质量门禁（tsc 0 错、428 测试全过、build 成功、grep 4 项 0、代码审查 3 文件通过）均绿；
- 初验发现的 P2（unused import）与 P3（测试 mock 卫生）已由开发者修复，复验确认：
  - task52 三文件 `npx eslint` → 0 问题
  - `CommentSection.test.tsx` 5/5 通过，React Query 警告消除
  - 全量 `tsc --noEmit` 0 错误、`npm run test` 428/428、`npm run build` 成功
- **task52 验收通过。**
