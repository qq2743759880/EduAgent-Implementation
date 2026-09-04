# 性能审查报告 fe-task01

> 范围：G1 用户端社区 & 成就中心（补课波：只审查+出报告，不改业务代码）
> 执行者：fe-perf ｜ 时间：2026-08-13
> 画像：frontend-stack.json（Next.js 16.3 App Router + Tailwind v4 + Zustand + TanStack Query + ECharts）
> server-info：test-reports/fe-task01-server-info.md（dev server http://localhost:3000，PID 3780，复用，未重复启动）
> 审查文件：`src/app/(user)/community/page.tsx`、`community/[postId]/page.tsx`、`achievements/page.tsx`；`src/components/community/*`、`src/components/achievement/*`；`src/lib/api/community.ts`

---

## 判定：PASS（无 P0）

- **P0：0** ｜ **P1：3** ｜ **P2：8**（发现表见下）
- 按规则（P0 为 FAIL），本次审查判定 **PASS**；但 3 项 P1 列入修正清单，建议由 fe-implementer 在修正环处理。

## 发现表

| # | 位置 file:line | 严重度 | 问题 | 建议 |
|---|----------------|--------|------|------|
| 1 | `src/lib/query-client.ts:33,43` + `src/app/providers.tsx:12-52`（影响 task01 全部 6 个 useQuery：community/page.tsx:29、[postId]/page.tsx:43、CommentSection.tsx:44、BadgeWall.tsx:24、PointLogTable.tsx:40、RankingTabs.tsx:40） | **P1** | **SSR double-fetch**：无 `HydrationBoundary`（全工程 grep 仅 query-client.ts:43 有 `dehydrate` 配置，为死代码），TanStack Query v5 在 SSR 阶段执行 queryFn（连接 127.0.0.1:8000，结果丢弃），客户端 hydrate 后 `refetchOnMount: true` 再次 fetch → 每次页面访问请求翻倍，后端负载/带宽双倍（server-info 已证实 dev 日志存在 SSR 期连接错误） | 每个 useQuery 加 `enabled: typeof window !== "undefined"`（SSR 渲染骨架，与现有骨架 UX 一致）；或 RSC 侧 prefetch + `HydrationBoundary` 传输（更优、改动大） |
| 2 | `src/app/(user)/community/[postId]/page.tsx:159-165` | **P1** | **正文 Markdown 每次重解析**：`MarkdownView` 未 memo，点赞/收藏/回帖计数 setState 触发 PostDetailInner 重渲染时，react-markdown 重新解析整篇正文（上限 20000 字），长文下阻塞主线程（INP 风险） | `const MarkdownView = memo(...)`（props 仅 content 字符串，引用稳定，memo 直接生效） |
| 3 | `src/components/community/CommentSection.tsx:139-141,148-222` | **P1** | **评论列表整列重渲染 + 逐条 markdown 重解析**：点击「回复」（setReplyTo）重渲染全部 ≤20 条 `CommentRow`，每条重新执行 ReactMarkdown 解析（CPU 密集）；CommentRow 未 memo，`onReply={() => setReplyTo(c)}` 每次新建闭包 | `CommentRow = memo()` + `onReply` 改传 comment_id 或 useCallback 稳定化 |
| 4 | `src/app/(user)/community/page.tsx:17` | P2 | **PostEditor 整体静态导入**：发帖表单逻辑（表单+校验+UI）进社区首页首屏 bundle；仅其内部 MDEditor 已 dynamic | `const PostEditor = dynamic(() => import("@/components/community/PostEditor"), { ssr: false, loading: ... })`，点击「发布帖子」才加载 |
| 5 | `src/components/community/PostEditor.tsx:27` | P2 | **MDEditor dynamic 无 loading 占位**：首次展开编辑器到 chunk 加载完成（@uiw/react-md-editor + refractor，生产 ≈90-100KB gzip）之间空白/布局跳动 | `dynamic(..., { loading: () => <编辑器中骨架/> })` |
| 6 | `src/app/(user)/community/page.tsx:98-100` | P2 | **PostCard 未 memo**：切分版/排序/页码/开关编辑器都会重渲染全部 10 张卡片（纯展示组件，props 引用在数据不变时稳定） | `export const PostCard = memo(PostCardImpl)` 隔离列表子树重渲染 |
| 7 | `src/app/(user)/achievements/page.tsx:17-58`、`community/page.tsx:51-108` | P2 | **'use client' 边界过宽**：页面头图/区块标题等纯静态内容（无 hooks、无事件）全部客户端化，随客户端 bundle 传输 | 将 header/页头拆为 Server Component（收益小，架构一致性改进） |
| 8 | `src/app/(user)/community/[postId]/page.tsx:127-141` | P2 | **ReactButtons 回调内联**：`onCountsChange` 箭头函数每次 render 新建；详情数据 refetch/invalidate 时重建 | `useCallback` 包裹或改传稳定引用 |
| 9 | `src/components/achievement/RankingTabs.tsx:49-54` | P2 | **medalFor 的 useMemo 冗余**：`useMemo(() => fn, [])` 等效模块级常量，无收益 | 提到模块级常量函数 |
| 10 | `src/app/(user)/layout.tsx:108` | P2 | lint error `no-explicit-any`（`me as any`）——社区/成就页共享壳（本组页面外壳），非 task01 实现但属于本组布局 | 修正类型；与 task01 无耦合，可顺带 |
| 11 | `src/app/providers.tsx:4,48-50` | P2 | **ReactQueryDevtools 静态导入**：devDependency 包被顶层 import，依赖构建期 DCE 兜底（dev chunk 中 devtools ≈740KB） | 改 `next/dynamic` 仅开发加载，或确认生产 bundle 不含该包 |

## 包体与资源审计

| 项 | 结论 |
|----|------|
| **ECharts 误引入** | ✅ 无。grep 全 src：echarts 仅 dashboard/learning/curriculum 4 个组件使用；社区/成就页 0 引用 |
| **react-markdown + remark-gfm**（详情页） | ⚠️ 约 40-60KB gzip，详情页正文+评论必需；列表页/成就页未引入（边界正确）。风险在「重解析」而非包体（见 P1#2/#3） |
| **@uiw/react-md-editor** | ✅ 已 `dynamic(() => import(...), { ssr: false })` 正确隔离，仅编辑器展开时加载（dev chunk 参考：refractor_lang ≈1.1MB 未压缩，生产大幅缩小）。缺 loading 占位（P2#5） |
| **PostEditor 表单逻辑** | ⚠️ 静态导入进首页首屏 bundle（P2#4） |
| **lucide-react / sonner / zustand / axios** | ✅ tree-shakable 按需；无全量引入 |
| **react-query-devtools** | ⚠️ 静态导入 devDependency（P2#11） |
| **构建产物测量** | ⚠️ 未跑 `next build`：dev server（PID 3780）正在使用 `.next` 增量缓存，build 覆盖会破坏运行中的 dev server，且后端未运行无法完整 SSG 验证。以下包体为**估算（未实测）**，不做为验收依据 |

首屏 client JS 估算（gzip，源码级 import 图推演，未实测）：React 19 运行时 ≈45KB + TanStack Query core ≈13KB + 页面组件与布局 ≈40-60KB ≈ **100-120KB/页**。生产精确值需在修正环后择机 `next build` 复核。

## 渲染审计

- **列表 key**：✅ 全部稳定——列表 `post.post_id`（page.tsx:99）、评论 `comment_id`（CommentSection.tsx:140）、徽章 `badge_code`（BadgeWall.tsx:58）、积分 `log_id`（PointLogTable.tsx:107）、排行 `${rank_no}-${user_id}`（RankingTabs.tsx:131）；骨架 key 用 index 但为纯静态占位，可接受
- **分页实现**：✅ 社区列表用 PaginationBar（复用 curriculum 组件）+ `placeholderData: (prev) => prev`（page.tsx:34）切页无闪烁；积分流水受控分页。无虚拟滚动需求（单页 ≤20 条）
- **重渲染风险组件**：3（正文 MarkdownView、CommentRow×20、PostCard×10）——全部为 P1/P2 修正项
- **骨架/三态**：✅ 所有查询均有 loading skeleton + error/empty 三态，无 CLS 隐患；正文无图片（纯 Markdown），无 img/CLS 风险点

## 数据层审计

- **queryKey 设计**：✅ 结构化且层级一致（`["community","posts",{board,sort,page}]`、`["community","post",id]`、`["community","comments",id]`、`["gamification",...]`）；发帖/回帖后前缀 invalidate（PostEditor.tsx:85-86、CommentSection.tsx:66-67）覆盖面正确
- **staleTime / 缓存**：✅ 列表 30s、成就 60s 分级合理；gcTime 5min；`retry` 策略（4xx 不重试、5xx ≤1 次，query-client.ts:34-41）合理
- **重复请求**：❌ **SSR double-fetch（P1#1）**——所有 6 个查询每次页面访问请求翻倍
- **并发合并**：✅ 成就页 3 个查询（badges/points/rankings）与详情页 2 个查询（detail/comments）为异构资源，并行独立请求是正确形态，无需合并
- **写操作**：✅ 点赞/收藏/回帖走 useMutation + 全局 onError toast（不吞错），本地计数覆盖避免陈旧值回写（ReactButtons.tsx:53-63）

## Next.js 16 特有审计

- **'use client' 边界**：⚠️ 三页面均为全量 client。交互+查询必须 client 化；但静态头图/区块标题可拆 RSC（P2#7）。`PostCard` 纯展示但被 client 页面引用（自动并入 client），当前架构（客户端数据获取）下合理
- **React 19 `use(params)`**：✅ [postId]/page.tsx:26 正确使用 Promise params + key 重置（`key={postId}`）
- **next/dynamic 使用**：✅ MDEditor 用 next/dynamic（SSR 项目正确形态，未裸用 React.lazy）；缺 loading（P2#5）
- **Turbopack/配置**：next.config.ts 无特殊项，无额外负担；生产构建未验证（见包体审计）

## 静态校验结果

| 校验 | 命令 | 结果 |
|------|------|------|
| 类型检查 | `npx tsc --noEmit`（edu-frontend） | ✅ 通过（exit 0） |
| Lint | `npm run lint` | ❌ 失败：全工程 26 errors + 26 warnings，**但 task01 范围文件 0 error 0 warning**；错误全部来自其他 task 遗留（courses/search、me、my-courses、chat、learning、curriculum、profile、lib/api/curriculum 等）。唯一与用户区页面壳相关：(user)/layout.tsx:108 `no-explicit-any`（P2#10） |
| 构建 | `next build` | ⚠️ 未执行（理由见包体审计；不编造数字） |
| 单元测试（参考） | `npx vitest run src/lib/api/community.test.ts`（server-info 已执行） | ✅ 12/12 passed |

## 最终结论

**判定：PASS**（P0=0）。task01 实现整体性能基线良好：ECharts 未误入、大编辑器库已按需隔离、queryKey/staleTime/invalidate 设计规范、key 稳定、骨架覆盖完整。3 项 P1 属「重复请求 + 主线程重解析」类问题，不影响功能正确性但影响 INP 与后端负载，应进入修正环。

### 修正清单（交 fe-implementer，本 agent 不改代码）

| 优先级 | 修正项 | 位置 |
|--------|--------|------|
| P1-1 | 消除 SSR double-fetch（6 处 useQuery 加 `enabled: typeof window !== "undefined"`，或引入 HydrationBoundary 传输方案） | community/page.tsx:29、[postId]/page.tsx:43、CommentSection.tsx:44、BadgeWall.tsx:24、PointLogTable.tsx:40、RankingTabs.tsx:40 |
| P1-2 | `MarkdownView` 包 memo | [postId]/page.tsx:159 |
| P1-3 | `CommentRow` 包 memo + onReply 稳定引用 | CommentSection.tsx:139-141,148 |
| P2-1 | PostEditor 整体 next/dynamic 懒加载 | community/page.tsx:17 |
| P2-2 | MDEditor dynamic 补 loading 占位 | PostEditor.tsx:27 |
| P2-3 | PostCard 包 memo | community/page.tsx:98 |
| P2-4 | ReactButtons onCountsChange useCallback | [postId]/page.tsx:133 |
| P2-5 | (user)/layout.tsx:108 修 no-explicit-any | (user)/layout.tsx:108 |

### 可测指标

- 首屏 bundle 大小：**未实测**（dev server 占用 .next，未跑 build）；估算 ≈100-120KB gzip/页，修正环后需 `next build` 复核
- 路由懒加载数量：当前 1（MDEditor dynamic）→ 修正后 2（+PostEditor）
- 重渲染风险组件：3（MarkdownView、CommentRow、PostCard）
- 每页重复 API 请求：当前 2×（SSR+客户端）→ 修正后 1×
