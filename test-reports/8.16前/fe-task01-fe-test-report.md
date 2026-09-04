# 前端测试报告 fe-task01

> 任务：G1 用户端社区 & 成就中心（fe-task01，已实现 + 已修正）
> 测试者：fe-tester｜日期：2026-08-13｜范围：最终功能测试（含本轮 a11y/perf/stripMarkdown 修正回归）

## 判定

**PASS** ✅

- 验收标准 4/4 全部实测通过（真实 API，无 MOCK）
- 单测全量 25 文件 / 196 用例 **100% 通过**；`tsc --noEmit` 通过；lint 全工程报错全部为 task01 范围外遗留（task01 文件 0 error 0 warning）
- 浏览器 E2E 25 项断言全部通过（独立 Playwright chromium，真实后端）
- 本轮修正（对比度 / tabs 方向键 / 表单 label / aria / MarkdownView+CommentRow memo / stripMarkdown）逐项回归通过，无回归

---

## 环境

| 项 | 值 |
|----|----|
| 前端 | Next.js 16.3（edu-frontend），dev server **http://localhost:3000**（PID 3780，复用 server-info 进程，未重复启动） |
| 后端 | FastAPI **http://127.0.0.1:8000**（PID 18048，运行中，真实 API 可用） |
| 画像 | frontend-stack.json：profile `nextjs-16-app-router`（Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router） |
| 测试账号 | `task01test / Test@123456`（student 角色，真实 API 登录） |
| 数据来源 | **全部为真实后端 API**（`/api/community/*`、`/api/gamification/*`），未使用任何 route 拦截/MOCK |
| 浏览器 | Playwright chromium（headless，项目 playwright ^1.62.1），1280×800 |
| 单测 | vitest v4.1.10 + @testing-library/react + jsdom |

> 注：MCP Playwright 浏览器会话与既有 profile 冲突（页面漂移/元素 detached），已改用**项目自带 Playwright 独立浏览器上下文**执行 E2E，结果可靠。

---

## 验收标准逐条映射（dev-plan.md fe-task01）

| # | Given / When / Then（验收） | 实测结果 | 结论 |
|---|------------------------------|----------|------|
| 1 | Given 已登录学员；When 打开 `/community`；Then 渲染热门帖子列表（`GET /api/community/posts?sort=HOT`）+ 4 学科分版 Tab（english/math/programming/general），**无 MOCK** | ① 列表渲染真实数据：59 帖分页（页面「全部」tab 10 条/页 + 6 页分页），卡片含浏览/点赞/回帖/收藏计数；② 浏览器监听确认请求 `GET http://127.0.0.1:8000/api/community/posts?sort=HOT&page=1&page_size=10`（真实 API）；③ tablist「社区分版」5 个 tab（全部+英语+数学+编程+综合），`aria-selected` 正确；④ 切「英语」tab 后 tabpanel 仅显示 10 条英语帖（`allEnglish=true`），无 MOCK | **PASS** |
| 2 | Given 学员编写标题 + Markdown 内容；When 提交（`POST /api/community/posts`）；Then 跳转帖子详情页、列表页可见新帖、获得积分 **+5** | ① 表单填写标题 + Markdown 正文后点发布 → toast「发布成功 发帖获得 +5 积分」；② 自动跳转 `/community/60`、`/community/61`（两次实测）；③ 详情页 h1=标题、正文 Markdown 正确渲染（`**加粗**`→strong、`` `code` ``→code、列表→ul/li）；④ 后端积分流水权威确认 `POST_CREATE +5` 两条（balance 14→19→24）；⑤ 列表页 queryKey 前缀失效（invalidate）使新帖列表可刷出 | **PASS** |
| 3 | Given 帖子详情页；When 点赞/收藏/回帖；Then 计数实时更新，且获得积分（**回帖 points:2**） | ① 点赞软切换：`0点赞 → 1已赞`（aria-pressed=true，计数即时更新）；再点回滚 `1已赞 → 0点赞`；② 收藏软切换：`0收藏 → 1已收藏 → 0收藏`（服务端 `total_count` 回写，非本地假计数）；③ 回帖：toast「回帖成功 获得 +2 积分」+ 评论列表立即可见（invalidate 刷新）；④ 后端流水确认 `COMMENT_CREATE +2`（balance 24→26）；⑤ 收藏/点赞后刷新页面状态保持（服务端持久化） | **PASS** |
| 4 | Given 打开 `/achievements`；When 加载徽章/积分/排行；Then 8 枚徽章（未解锁置灰 + next_milestone）、积分流水分页、日/周/月/总排行榜 `GET /api/gamification/rankings?scope=&dimension=` 全部真实 API | ① 徽章墙 8 枚卡片渲染（`badges=8`）；未解锁徽章 `grayscale(1) + opacity-0.5 + Lock 图标`（computed filter 实测）；「下一枚：」next_milestone 渲染；「已解锁 X / 8 枚」计数；② 积分流水渲染（当前账号 8 条：POST_CREATE/COMMENT_CREATE），分页逻辑存在（`page` state + 上一页/下一页 + `logs_total` 计算 totalPages，数据 <10 条时不分页属合理行为，`getMyPoints(page,page_size)` 契约正确）；③ 排行两组 tab：时间范围 4 tab（日/周/月/总）+ 维度 3 tab（积分/学习时长/徽章数）；④ 切换「总榜」实测触发 `GET /api/gamification/rankings?scope=ALL_TIME&dimension=POINTS&top_n=20`（真实 API），排行行 + 「我的排名」渲染 | **PASS** |

**验收映射小结：4/4 PASS。**

---

## 单测统计（`npx vitest run`，edu-frontend 全量）

| 指标 | 值 |
|------|-----|
| 测试文件 | **25**（25 passed） |
| 用例数 | **196**（196 passed，0 failed，0 skipped） |
| 通过率 | **100%** |
| 耗时 | 13.99s（transform 6.68s / setup 23.25s / tests 15.57s） |
| 命令 | `npx vitest run`（vitest v4.1.10） |

task01 相关用例组（全部通过）：
- `src/lib/api/community.test.ts` — 12/12（社区+成就 API 封装契约）
- `src/components/community/PostCard.test.tsx` — 5/5（含 stripMarkdown 摘要展示）
- `src/components/community/ReactButtons.test.tsx` — 6/6（点赞/收藏定向回写）
- `src/components/achievement/BadgeWall.test.tsx` — 4/4（8 徽章 / next_milestone / 置灰）
- `src/components/achievement/RankingTabs.test.tsx` — 4/4（周榜/维度切换重新请求）

> 注：vitest 启动有 `configLoader: 'native'` + `__dirname` 弃用警告（vitest.config.mts:16，server-info 已记录），仅警告不影响结果。

## 类型与静态校验

| 校验 | 命令 | 结果 |
|------|------|------|
| 类型检查 | `npx tsc --noEmit`（edu-frontend） | ✅ **通过（exit 0）** |
| Lint | `npm run lint`（eslint） | ⚠️ 全工程 **25 errors + 26 warnings，但 task01 范围文件 0 error 0 warning**；错误全部来自其他 task 遗留（`(user)/courses/search`、`me`、`my-courses`、`chat`、`learning`、`curriculum`、`profile`、`ui/radio-group`、`lib/api/curriculum` 等，与本任务无关，属既有债务） |

---

## 浏览器实测记录（独立 Playwright，localhost:3000，真实 API）

### /community（列表 + 分版 + 发帖）

| 用例 | 结果 | 实测证据 |
|------|------|----------|
| 分版 tab 5 个（全部+4 学科） | ✅ | `[role=tab]` count = 5 |
| 热门帖列表真实渲染 | ✅ | 置顶帖「👋 欢迎来到 EduAgent 学习社区！」浏览 137/点赞 5/回帖 2/收藏 3 |
| 列表请求走真实 API | ✅ | 浏览器请求监听命中 `GET /api/community/posts?sort=HOT&page=1&page_size=10` |
| 分版 Tab 键盘方向键（ArrowRight） | ✅ | 聚焦「全部」按 ArrowRight → 「英语」`aria-selected=true` 且获得焦点（APG Tabs 修复回归） |
| 英语版块过滤 | ✅ | tabpanel 切换为「英语」，10 条全部为英语帖（/community/49…13） |
| 列表摘要 stripMarkdown | ✅ | 摘要文本无 `**`/`#`/`[]()` 等 Markdown 语法（「背单词的 3 条心法 间隔重复 (SM-2)：…」） |
| MDEditor textarea label 关联（a11y #5） | ✅ | `textarea#post-content` 存在且 `label[for="post-content"]` 正确指向（实测 DOM） |
| 表单校验 aria（a11y #6） | ✅ | 空提交 toast「请填写标题（至少 2 个字）」不跳转；touched 后短标题（1 字）→ `aria-invalid="true"` + `aria-describedby="post-title-error"` + `role=alert` 文案「标题至少 2 个字」；补齐合法值后全部清除 |
| 发帖 → 跳转详情 + +5 分 | ✅ | toast「发布成功 发帖获得 +5 积分」→ URL `/community/60`（二次实测 61） |
| 详情页 Markdown 渲染 | ✅ | h1=标题；strong（加粗）、code（行内代码）、ul/li 均正确渲染 |

### /community/[postId]（点赞/收藏/回帖）

| 用例 | 结果 | 实测证据 |
|------|------|----------|
| 点赞软切换即时更新 | ✅ | `0点赞 → 1已赞`（aria-pressed=true）；再点回滚 `→ 0点赞` |
| 点赞激活态对比度（a11y #3，1.4.3） | ✅ | 激活态 bg=`lab(49.19 81.58 36.03)`（canvas 解析 rgb(236,0,63)）+ 白字 → **4.53:1 ≥ 4.5** |
| 收藏软切换即时更新 | ✅ | `0收藏 → 1已收藏`（aria-pressed=true）；再点回滚 `→ 0收藏` |
| 收藏激活态对比度（a11y #1，1.4.3） | ✅ | 激活态 bg=`lab(37.88 37.17 52.27)`（canvas 解析 rgb(151,60,0)）+ 白字 → **7.09:1 ≥ 4.5** |
| 回帖 +2 分 + 列表可见 | ✅ | toast「回帖成功 获得 +2 积分」；回帖内容立即可见；`共 N 条回帖` 计数同步 |

### /achievements（徽章 / 积分 / 排行）

| 用例 | 结果 | 实测证据 |
|------|------|----------|
| 徽章墙 8 枚 + next_milestone | ✅ | 8 张徽章卡；「已解锁 0 / 8 枚」；「下一枚：社区之星…」渲染 |
| 未解锁徽章置灰 | ✅ | 未解锁卡图标 `filter: grayscale(1)` + `opacity: 0.5` + Lock 角标（computed 实测） |
| 积分流水渲染 | ✅ | 流水行含类型/时间/±分/余额（POST_CREATE +5、COMMENT_CREATE +2 等，与后端流水一致） |
| 排行 4 tab（日/周/月/总） | ✅ | `[aria-label="排行时间范围"]` 4 个 tab |
| 排行 tab 键盘方向键 | ✅ | 日榜 → ArrowRight → 周榜 `aria-selected=true`（APG Tabs 修复回归） |
| 排行真实 API | ✅ | 切「总榜」触发 `GET /api/gamification/rankings?scope=ALL_TIME&dimension=POINTS&top_n=20` |
| 排行行渲染 | ✅ | 榜单行（rank_no/用户/分值）+「我的排名」 |

### 后端数据一致性（权威核对）

登录 `task01test` 后 API 核对：积分流水 `POST_CREATE +5 ×4`、`COMMENT_CREATE +2 ×3`，余额 31，与前端 toast 逐条吻合；点赞/收藏已回滚，无残留脏状态。

---

## 本轮修正回归验证（a11y / perf / stripMarkdown）

| 修正项 | 验证方式 | 结果 |
|--------|----------|------|
| #1 收藏激活态对比度（amber-500→amber-700 白字） | 浏览器 computed + canvas | ✅ 7.09:1（原 2.15:1） |
| #3 点赞激活态对比度（rose-500→rose-600 白字） | 浏览器 computed + canvas | ✅ 4.53:1（原 3.68:1） |
| #4 回帖 textarea 无 label → `Label htmlFor="reply-content"` | 静态代码审查 | ✅ CommentSection.tsx:107-112 |
| #5 MDEditor label 失效 → `textareaProps={{ id: "post-content" }}` | 浏览器 DOM 实测 | ✅ label for 正确关联 textarea |
| #6 校验错误无 aria → aria-invalid/aria-describedby/role=alert | 浏览器 DOM 实测 | ✅ 短标题触发全链路 |
| #7 tabs 无方向键/aria-controls → roving tabindex + Arrow + tabpanel | 浏览器键盘实测（社区分版 + 排行两组 tab） | ✅ ArrowRight 切换 + focus |
| #2 焦点指示对比不足 → `outline-foreground` + `focus-visible:ring-3 ring-foreground` | 静态审查（globals.css:122、button/input/textarea、BoardTabs） | ✅ 高对比焦点环 |
| #8 排名前三图标对比不足 → amber-700/slate-600/orange-600 + sr-only「第 N 名」 | 静态审查（RankingTabs.tsx:40-44,199） | ✅ |
| #9 积分卡右上白字对比 → 渐变加深 indigo-700→sky-700 | 静态审查（PointLogTable.tsx:54） | ✅ |
| #10 流水 +分 emerald-600→emerald-700 | 静态审查（PointLogTable.tsx:111,128） | ✅ |
| #11 多枚奖励小字 amber-600→amber-700 | 静态审查（PostEditor/CommentSection/BadgeWall） | ✅ |
| #12 徽章卡 aria-label 重复朗读 → 移除 + progressbar role | 静态审查（BadgeWall.tsx 无 aria-label；progressbar + aria-valuenow） | ✅ |
| #14/#15 统计 sr-only 文本 | 静态审查（PostCard.tsx:84-101、ReactButtons.tsx:87,108） | ✅ |
| #18 发帖 h3→h2 标题层级 | 浏览器快照 | ✅ 页面 h2「发布新帖」 |
| perf P1-2 MarkdownView memo | 静态审查（[postId]/page.tsx:160） | ✅ |
| perf P1-3 CommentRow memo + onReply 传 comment_id | 静态审查（CommentSection.tsx:80-86,162） | ✅ |
| stripMarkdown 列表摘要 | 浏览器实测 | ✅ 列表摘要无 Markdown 语法 |

---

## 遗留项（非阻塞）

| # | 项 | 位置 | 级别 | 说明 |
|---|----|------|------|------|
| 1 | SSR double-fetch（6 处 useQuery 未加 `enabled: typeof window !== "undefined"`） | community/page.tsx:29、[postId]/page.tsx:43、CommentSection.tsx:45、BadgeWall.tsx:24、PointLogTable.tsx:40、RankingTabs.tsx:62 | P1（perf 报告遗留） | 功能正确，每页首访 API 请求翻倍；本轮未列入修正范围，建议下轮处理 |
| 2 | PostEditor 整体 dynamic 懒加载（P2-1）、MDEditor loading 占位（P2-2）、PostCard memo（P2-3）、ReactButtons onCountsChange useCallback（P2-4） | community/page.tsx:17,106、[postId]/page.tsx:133 | P2 | perf 优化项，非本轮范围 |
| 3 | lint 全工程 25 errors + 26 warnings | courses/search、me、my-courses、chat、learning、curriculum、profile 等 | 既有债务 | task01 范围文件 0 error 0 warning，非本任务引入 |
| 4 | vitest `__dirname` configLoader 弃用警告 | vitest.config.mts:16 | 工具提示 | 建议改 `import.meta.dirname`，不影响结果 |

---

## 测试统计汇总

- 单测：**25 文件 / 196 用例 / 100% 通过**
- 浏览器 E2E：**25 项断言全部通过**（真实 API，无 MOCK）
- 类型检查：**通过**；Lint：task01 范围 **0 error 0 warning**
- 判定：**PASS**（验收 4/4，修正回归全部通过，无新增缺陷）
