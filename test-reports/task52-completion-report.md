# task52 完成报告 — /community/[postId] 帖子详情页（React 实现）

## 任务概述
将 task52 帖子详情页从 HTML 效果图（`test-reports/fe-html/community-post.html`，已获用户 APPROVED）迁移为 React 实现，符合 candy-playful 冻结风格，复用契约⑬ `community/posts/{id}` 系列 API 与 task41/51 既有组件（MarkdownView / C7 EmptyState / C8 ErrorState / C2 分页），压实正文渲染、评论区、点赞/收藏交互与错误态。

## 交付内容

### 规范补充（fe-spec-writer 先行）
- `.opencode/plans/doc-frontend-design-spec.md` 新增 **P22 `/community/[postId]` 帖子详情**：布局草图（详情头/操作行/正文/评论区/分页）、组件清单（C25 PostDetail / C26 CommentList/CommentItem / C27 CommentComposer）、交互说明（点赞收藏软切换 + 积分提示、评论分页、锁定帖禁用）、数据依赖（契约⑬ 详情/评论/react 端点）。

### 效果图
- `test-reports/fe-html/community-post.html`：糖果色帖子详情页，含详情头/操作行/正文/评论区，五态演示（成功/加载/空评论/锁定帖/帖子不存在），CSS 容器查询响应式 375~1440，**已获用户 APPROVED**。

### React 实现
| 文件 | 类型 | 说明 |
|------|------|------|
| `src/components/community/ReactButtons.tsx` | 重写 | 点赞（糖果绿）/收藏（糖果黄）软切换按钮：3D 实底阴影、`useMutation` 写操作、`onSuccess` 按 target 定向回写（不覆盖兄弟字段）、`points_awarded>0` 回调积分提示、失败经全局 onError toast（R-7 不吞错） |
| `src/components/community/CommentSection.tsx` | 重写 | 评论区：分页 C2（‹ 页码 › 共 N 条）、回帖表单（Textarea + 糖果橙发布按钮 +2 积分）、锁定帖禁用输入、评论点赞软切换响应回填、四态（loading 骨架/error 重试/empty/列表） |
| `src/app/(user)/community/[postId]/page.tsx` | 重写 | 详情头（返回/版块 Badge/置顶/锁定/标题/作者行）+ 操作行 + Markdown 正文 + 评论区；锁定帖操作行隐藏 + 锁定 banner + 评论禁用；404 → ErrorState（role=alert）+「← 返回列表」CTA；403/404 语义区分文案 |

### 测试
| 文件 | 说明 |
|------|------|
| `src/components/community/ReactButtons.test.tsx` | 6 用例：初始计数、点赞成功定向回写、不覆盖兄弟字段、软切换取消、favorite 定向、失败不更新计数 |
| `src/components/community/CommentSection.test.tsx` | 5 用例：分页 C2 下一页、单页无分页器、总数展示与分页一致、回帖成功（createComment+清空+计数+1）、锁定帖禁用 |
| `src/app/(user)/community/[postId]/page.test.tsx` | 3 用例：成功渲染、404 ErrorState+返回列表 CTA、锁定帖操作行隐藏+评论禁用 |

## 关键实现决策
- **无 MOCK**：接口全部走契约⑬ 真实 API（`getPostDetail`/`listComments`/`createComment`/`togglePostLike`/`togglePostFavorite`/`toggleCommentLike`），无 fallback 假数据。
- **写操作 R-7**：点赞/收藏/回帖/评论点赞均用 `useMutation` 或显式 try/catch；失败 toast + console.error，不静默吞错；回帖成功 toast「+2 积分」+ invalidate `["community","comments",postId]`。
- **锁定帖降级**：操作行隐藏（无点赞/收藏按钮）+ 锁定 banner + 评论区输入禁用，只读浏览。
- **404 语义**：`postDetailErrorMessage` 区分 403「无权限」/404「不存在」，其余透传后端 message；ErrorState 提供「← 返回列表」CTA。
- **重试策略对齐**：移除页面级 `retry: 1`，改由全局 QueryClient 默认（4xx 不重试、5xx 重试一次），404 错误态即时呈现。
- **MarkdownView 未动**：正文/评论复用既有 MarkdownView，历史遗留 `text-[15px]` 按要求不改。

## 验证结果
独立 fe-tester 子代理初验发现 2 项（P2 unused import / P3 测试 mock 卫生），已修复并复验：
- tsc：0 error
- eslint：task52 三文件 0 problem（P2 修复后）
- Vitest：全量 428/428 通过（ReactButtons 6/6、CommentSection 5/5、[postId] 3/3）
- `next build`：成功，`/community/[postId]` 以 ƒ（Dynamic）出现在路由表
- grep 审计（硬编码 hex / 内联色值 / 禁闭色 / 任意字号）：全 0（`bg-candy-red` 仅错误态重试按钮）

## 变更
- git commit：见提交记录（message 含 task52）
- 已运行 `sync.ps1` 分发

## 遗留 / 提示
- 后端 community 域若存在未冻结字段，联调前以契约⑬ 为准，仅做展示映射。
- 评论回复（parent_id/reply_to_id）后端已支持字段，本页未做二级回复 UI（不在 task52 范围），后续任务可扩展。
