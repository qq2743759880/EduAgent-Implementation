# task51 · /community 社区列表页 · 独立测试子代理验证报告

- 测试日期：2026-08-21
- 验证范围：src/app/(user)/community/page.tsx、src/components/community/PostCard.tsx、src/components/community/CommunityFilterBar.tsx、src/lib/community-meta.ts、page.test.tsx、PostCard.test.tsx、CommunityFilterBar.test.tsx（BoardTabs.tsx 已删除）。
- 环境：edu-frontend（Next 16.3.0 / React 19.2.8 / Vitest 4.1.10），npx 运行，PowerShell。

## 逐项验证结果

| 项 | 结果 | 说明 |
|----|------|------|
| 1. 全量 vitest | **FAIL** | 57 个文件 / 423 用例，**1 失败 / 422 通过**（99.76%）。失败项见下方详述。未在 task51 之外发现回归；其余 56 文件全绿。 |
| 2. TypeScript (`tsc --noEmit`) | PASS | 0 错误。 |
| 3. ESLint 全量 | PASS | 0 errors / 15 warnings；**无一条属于 task51 文件**（告警分布于 scripts、courses/search、chat 侧栏、CourseSearchInput、QuizPanel/VocabDailyPanel、offline-indicator、stepper、dropdown-menu-select 等历史文件）。 |
| 4. Build (`next build`) | PASS | 编译成功（exit 0），`/community`（静态）与 `/community/[postId]`（动态）均已生成；18 静态页生成 725ms。 |
| 5. 审计 grep | PASS | 三组 grep 命中均 0：硬编码 `#[hex]{3,8}` = 0、任意字号 `text-[Npx]` = 0、内联 `style=` = 0。page.tsx 内 7 处 `<button>` 全部带 `type=`（CandyPager 上一页/页码/下一页、FAB、桌面 CTA、重试、发第一篇），且均不在 `<form>` 内（页面无 form）。 |
| 6. 契约⑬ 字段核对 | PASS | 页面 `listPosts({sort, board_code, keyword, page, page_size})` 消费 `total/page/page_size/items/mine_total_posts`（page.tsx L34/41/42）；PostCard 每条用 `view_count`👁/`comment_count`💬/`like_count`👍（PostCard.tsx L121-123）；API 层 `listPosts` 对 `keyword` 应用 `escapeLikeKeyword`（src/lib/api/community.ts L210-222），`PostSummary` 含 `view_count/comment_count/like_count`。字段映射与 API 契约一致。 |

## 失败项详述（vitest）

**失败文件**：`src/components/community/CommunityFilterBar.test.tsx`
**失败用例**：「点击版块 chip 回传 onBoardChange 并切换 aria-pressed」（测试文件 L37-55 中 L42 断言）
**报错**：
```
AssertionError: expected "vi.fn()" to not be called at all, but actually been called 1 times
Received: 1st vi.fn() call: Array [ "" ]
```
即 `expect(onSearch).not.toHaveBeenCalled()` 失败——`onSearch("")` 被调用了一次。

**根本原因（两层）**：

1. 组件行为缺陷（轻量）：`CommunityFilterBar` 的防抖 effect（L42-48）在挂载时即对空值 `input=""` 排程 300ms 后调用 `onSearch(input.trim())` 即 `onSearch("")`。也就是说组件**挂载约 300ms 后会自动触发一次多余的 onSearch("")**。在页面上下文中这会造成初始加载时一次冗余查询/`setPage(1)` 重置（参数值不变，功能上无害，但为多余的副作用，属可优化点）。

2. 测试竞态（直接致错）：用例 #2 断言“点击版块不触发搜索”。当测试环境偏慢、挂载到断言执行超过 300ms 时，挂载期排程的那次 `onSearch("")` 已触发，断言失败。这是**时间片竞态**：在主线程隔离快跑社区子集（29/29）及本机首轮快速运行中该用例通过；本机全量重跑（环境负载高、单文件耗时 >300ms）时失败。属测试不稳（flaky），非业务数据逻辑错误。

## 建议修复（不直接改动源码，供 student 参考）

- **首选（消除挂载副作用）**：`CommunityFilterBar` 防抖 effect 改为只在 `input` 首次变更后触发，可用 `useRef` 记录“是否已跳过首次挂载”，或将该 effect 依赖 `input` 且内部判断 `if (!mountedRef.current) { mountedRef.current = true; return; }`；或把挂载首帧的排程去掉（挂载时不应发起搜索）。
- **或（仅稳测试）**：用例 #2 中把 `expect(onSearch).not.toHaveBeenCalled()` 改为 `expect(onBoardChange).toHaveBeenCalledWith("math")` 后再用 `vi.useFakeTimers()` / `vi.advanceTimersByTime` 控制 300ms 防抖时序，或先 `clearTimeout` 再断言，消除时序依赖。
- 建议两者都做：修掉组件挂载即排程的多余 `onSearch("")`（顺带减少页面初始一次冗余请求），同时让测试对防抖时序显式可控，避免 flaky。

## 其他观察（非阻断）

- 四态覆盖完整（page.test.tsx：loading 骨架/error+重试/empty+发第一篇/success+我的帖子计数+分页+共N条），PostCard 用例含置顶/锁定只读(无链接+aria-label)/未知分版兜底「综合」，覆盖面足够。
- ESLint 告警中有若干 `react-hooks/set-state-in-effect`，均不涉及 task51 文件，非本轮引入。
- 首轮全量运行时因与 tsc/eslint 并行抢占 CPU 出现 3 个 worker 启动超时（admin-guard/price-text/ReactButtons）属环境干扰；脱离并行独立重跑后这些文件全部通过，非代码问题。

## 总结论：**REJECT**

理由：全量 vitest 存在 **1 个失败用例**（CommunityFilterBar.test.tsx #2，防抖挂载副作用 + 时序竞态），未达到“全量回归全绿”的交付标准。该失败为**可复现的轻量行为缺陷 + flaky 测试**，非业务数据逻辑错误；按上述建议修复（建议优先消除组件挂载期多余 onSearch("")，并让测试对 300ms 防抖时序显式可控）后，其余全部验证项（tsc 0 / eslint 0 err / build 通过 / 审计 0 / 契约⑬ 一致）均满足验收要求。

关键数字：vitest 57 文件 / 423 用例，422 通过 1 失败；tsc 0 错误；eslint 0 错误 / 15 告警（均为非 task51）；next build 成功；审计命中 0（硬编码色/任意字号/内联样式）且按钮 7/7 带 type。

---

## R2 复验（2026-08-21，学生已修复挂载期防抖副作用）

**修复内容**：`src/components/community/CommunityFilterBar.tsx` L41-54 在防抖 effect 前新增 `mounted` ref，首次挂载直接跳过（`if (!mounted.current) { mounted.current = true; return; }`），仅在 `input`/`onSearch` 变化时排程 300ms 防抖 —— 消除挂载期多余的一次 `onSearch("")`，即修复 R1 阻断点（组件挂载副作用 + 测试 #2 时间片竞态）。

实测环境：edu-frontend（Next 16.3.0 / React 19.2.8 / Vitest 4.1.10），npx 独立顺序重跑，避免 CPU 抢占干扰。

| 复验项 | 结果 | 说明 |
|--------|------|------|
| 1. 全量 vitest | **PASS** | 57 个文件 / 423 用例，**423 通过 / 0 失败（100%）**。R1 唯一失败项 CommunityFilterBar.test.tsx #2「点击版块 chip 回传 onBoardChange 并切换 aria-pressed」现稳定通过；该文件 5/5 全绿，全量无回归。 |
| 2. TypeScript (`tsc --noEmit`) | PASS | 0 错误（exit 0）。 |
| 3. ESLint 全量 | PASS | 0 errors / 15 warnings，全部为历史文件告警（scripts、courses/search、chat 侧栏、CourseSearchInput、QuizPanel/VocabDailyPanel、offline-indicator、stepper、dropdown-menu-select、api-client.test），**无一条属于 task51 文件**。 |
| 4. Build (`next build`) | PASS | 编译成功（exit 0），`/community`（静态）与 `/community/[postId]`（动态）均已生成；18 静态页 667ms。 |

### 复验总结论：**PASS（R2）**

R1 唯一阻断点（挂载期防抖对空值排程 `onSearch("")` 导致的冗余查询 + 测试 #2 竞态）已由 `mounted` ref 修复并实测消除：CommunityFilterBar 单文件 5/5 稳定通过（无 flake），全量 57 文件 / 423 用例 100% 通过、0 失败。其余验证项均保持满足：tsc 0 / eslint 0 err / build 通过 / /community 路由生成。**验收通过。**

R2 关键数字：vitest 57 文件 / 423 用例，**423 通过 0 失败（100%）**；tsc 0 错误；eslint 0 errors / 15 warnings（均非 task51）；next build 成功，`/community` 与 `/community/[postId]` 路由生成。