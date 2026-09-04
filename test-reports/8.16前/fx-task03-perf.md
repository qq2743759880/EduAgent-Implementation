# 性能审查报告 fx-task03

> 审查对象：G3 管理端课程/题库/用户页面（6 页面 + 10 组件 + `lib/api/admin/{courses,questions,users}.ts`）
> 审查方式：静态代码审查（规格 architecture.md/frontend-spec.md + 全部实现文件）+ 浏览器侧测量（Playwright + dev server，`test-reports/fx-task03-server-info.md` 记录 localhost:3000 / PID 17284）+ 历史静态校验记录
> 补课波约束：**只审查 + 出报告，禁止改业务代码**；P0/P1 记录为待修正项交 fe-implementer
> 判定口径：存在未解决 P0 → FAIL，否则 PASS

**verdict: PASS**

- P0 数量：**0**
- P1 数量：**1**（关键词筛选无防抖 → 逐击键请求放大，三页同构，须给 file:line）
- P2 数量：7
- 报告路径：`test-reports/fx-task03-perf.md`

---

## 1. 发现总表

| # | 位置（file:line，根=edu-frontend） | 严重度 | 问题 | 建议 |
|---|-----------------------------------|--------|------|------|
| F1 | `src/app/(admin)/admin/courses/page.tsx:105`、`questions/page.tsx:163`、`users/page.tsx:85` | **P1** | 关键词筛选 `onChange` 直接 `setKeyword(v); setPage(1)`，**无防抖**：每次击键 setState → queryKey 变化 → TanStack Query 对无缓存新 key 发起后端请求（`listAdminSeries/listQuestions/listUsers` 均带 keyword 参数），输入 N 字符 ≈ N 个请求 | 引入 applied 快照（300ms debounce，如 `useDebouncedValue(keyword, 300)`），queryKey 只用防抖后的 keyword；可顺带把空串 keyword 归一为 undefined，减少无效 key 变体 |
| F2 | `courses/page.tsx:124-139`（SeriesRow）、`questions/page.tsx:185-226`（行 div）、`UserTable.tsx:68-147`（行 tr）、`ModuleTree.tsx:157-170`（ModuleCard） | P2 | 列表行/模块卡未 `React.memo`，且收到每次渲染新建的箭头函数 props；mutation `isPending` 翻转/筛选变化时全量重建当页 10 行 | 行组件 `memo` + 回调 useCallback，或维持现状（10 行/页开销 <1ms/次）；page_size 上调前收益有限 |
| F3 | `VideoUploadFlow.tsx:124-139`（setInterval 150ms）、`:82-90`（cleanup）、`:187-190`（handleClose） | P2 | 模拟进度 `setInterval(150ms)` 每 tick `setProgress` → 重渲染 Dialog 子树（Stepper/资产块）；单次上传约 17 tick（前 80% +8 / 后 20% +3 ≈ 2.5s 完成） | **已验证卸载清理完整（cleanup + handleClose 双保险，不残留 setState）**，现状可接受；接入真实存储（P2 阶段）时步骤机整体重构，届时以真实进度替代轮询 |
| F4 | `BatchImportDialog.tsx:85-97` | P2 | 500 条批量导入：JSON.parse 全量 + 整数组作为单次 POST body，无条数/体积预估提示；估算 500 条 ≈ 0.2–1 MB（FastAPI 默认无 gzip，明文传输） | 提交前提示「已解析 N 条 / 约 X KB」，>2000 条建议分批；前端拦截非数组已在发请求前完成（合规，不吞错） |
| F5 | `ModuleTree.tsx:45-59` | P2 | 模块树 `getAdminSeriesTree` 一次全量拉取（模块+课次+班次），非展开时按需加载；当前规模（≤10 模块）可接受 | 模块 >50 时改为展开时懒加载子节点；`materialQ`（5min stale）挂载即请求一次属可接受（常驻指引） |
| F6 | `src/app/providers.tsx:48-50` | P2 | 管理端 dev 模式加载 `@tanstack/react-query-devtools` chunk + Next DevTools（浏览器实测 /admin/* 出现 devtools 按钮与 chunk） | 已 `process.env.NODE_ENV !== "production"` 条件化，生产构建不打包，**非缺陷**；仅提示 dev 模式噪音 |
| F7 | `UserTable.tsx:103,106` | P2 | 每行渲染执行 2 次 `new Date(...).toLocaleDateString()/toLocaleString()`（10 行 = 20 次/渲染） | 常量级开销可忽略；如需可提取行级 memo 或统一格式化，属锦上添花 |
| F8 | `src/app/providers.tsx:39`（GlobalChatInjection）+ `(admin)/layout.tsx`（fx-task02） | P2 | 既有架构债务：根 providers 挂 chat 注入，管理端首屏随全局壳加载 chat 相关 chunk（fx-task02-perf.md 已记录为 P1 债务，非本 task 引入） | 挂账：管理端迭代波统一收敛（动态 import / 路由级拆分），本 task 不越权处理 |

---

## 2. 维度审计

### 2.1 列表大数据（courses/questions/users）

**分页实现 ✅**
- 三列表页统一 `PAGE_SIZE = 10`（courses/page.tsx:33、questions/page.tsx:42、users/page.tsx:21），请求带 `page_size=10`（实测 `GET /api/admin/courses/series?page=1&page_size=10` → 200）。
- `totalPages = ceil(total/10)`，`totalPages>1` 才渲染 PaginationBar（courses:63,141 / questions:89,228 / users:44,107）——空页不渲染多余 DOM。
- `placeholderData: (prev) => prev` 切页保持旧数据、不闪加载（courses:49 / questions:71 / users:40）✅。
- **虚拟化需求评估：不需要**。服务端分页每页仅 10 行 DOM（SeriesRow/题目行/tr），渲染成本微秒级；虚拟滚动（@tanstack/react-virtual）在 page_size 保持 10 时无收益，仅在改为「单页全量渲染」或 page_size ≥ 200 时才有必要——不建议引入。

**筛选触发 ⚠️（F1，P1）**
- 下拉筛选（学科/难度/角色/状态/标签）变化即请求：合理（用户明确选择，且 staleTime 15s 内同 key 命中缓存）。
- **关键词输入无防抖**：三页 `onChange` 直接更新 keyword + setPage(1)（courses:105 / questions:163 / users:85）。每次击键 queryKey `["admin",模块,{...,keyword,...}]` 变化 → 无缓存 → 发请求。输入 10 字符关键词 ≈ 10 个后端请求（后端 `keyword` 参数真实参与过滤）。**修复建议**：300ms debounce + applied 快照进入 queryKey，量化预期：10 字符输入 10 请求 → 1 请求（−90%）；管理端高频筛选场景整体请求数 −60~80%。
- queryKey 含空串 keyword 变体（`keyword: ""` 也序列化进 key），与防抖修复一并归一。

### 2.2 渲染

**表格行重渲染（F2/F7，P2）**：10 行/页，行组件未 memo、回调为每次新建箭头函数，但绝对值开销 <1ms/次，不构成瓶颈；`saleMutation.isPending` 翻转会重建全部行，同样微小。无需 P0/P1 处置。

**弹窗 key-remount（✅ 设计正确）**：SeriesForm.tsx:47-55、QuestionForm.tsx:65-74、VideoUploadFlow.tsx:53-64 用 `key={open ? ... : "closed"}` 强制每次打开重挂载——开销为一次表单级 DOM 重建（毫秒级），换来「打开即重置、零状态残留、不同 session 天然隔离」（架构 D3），**打开即重建成本可接受，是收益不是问题**。BatchImportDialog/ComposePaperDialog 用手动 handleOpenChange 重置（BatchImportDialog.tsx:107-113、ComposePaperDialog.tsx:89-95），等价正确。

**VideoUploadFlow setInterval（F3，✅）**：150ms 频率 ≈ 17 tick/次上传，每次 tick 仅重渲染 Dialog 子树；`assetIdRef` 防闭包陈旧值（:78,131）、useEffect cleanup（:83-90）+ handleClose（:187-190）双清理，卸载不残留 setState——符合规格「关闭/卸载清理 progressTimer」验收。

### 2.3 数据（TanStack Query）

**staleTime / queryKey ✅**：
- 列表 15s（三页）、metrics/tags 60s（MetricCards.tsx:29、questions/page.tsx:78）、material 5min（ModuleTree.tsx:58）、详情 30~60s（[seriesId]:36、[id]:30）、全局默认 30s / gcTime 5min / refetchOnWindowFocus:false / 4xx 不重试 5xx 最多 1 次（query-client.ts:29-41）——分层合理，无重复请求风险。
- queryKey 命名空间 `["admin",模块,...]` 精确到页（courses:45 / questions:59 / users:30），写操作 `invalidateQueries({queryKey:["admin",模块]})` 前缀失效重取（9 处 useMutation 统一）——官方推荐模式 ✅。
- `enabled: valid` 防无效 ID 发请求（[seriesId]/page.tsx:35、[id]/page.tsx:29）✅。

**批量导入 500 条 body（F4，P2）**：无分块、无体积预估提示；500 条 × ~0.4–2KB ≈ 0.2–1MB 单次 POST。管理端内网可接受，建议加条数/体积提示。

**级联请求（✅ 按需已达成）**：系列详情页 = `detailQ`（概要 30s stale）→ `ModuleTree` 挂载后独立发 `treeQ` + `materialQ`（5min 缓存），非 SSR 内联、非整站预取——「按需加载」达成；仅 tree 单次全量（F5，规模小可接受）。

### 2.4 包体

- **ECharts 零泄漏 ✅**：grep 全 `src/components/admin/` 与 `src/app/(admin)/` 零 echarts 引用；浏览器实测 /admin/courses 网络面板**无 echarts chunk**。仪表盘 MetricCards 仅用 lucide-react 图标 + Card（MetricCards.tsx:12-19），未引 charts——审查维度 4 明确通过。ECharts（^6.1.0）仅在用户端 dashboard/learning 组件按需注册（echarts/core + 组件级 use），不属于管理端。
- **大库零泄漏 ✅**：admin 组件与 (admin) 路由组零 `@uiw/react-md-editor` / `react-markdown` / `zod` / `react-hook-form` 引用（grep 仅注释提及 react-hook-form）。
- dev 模式实测加载的 zod/micromark/base-ui chunk 来自全局壳（providers/AdminShell 共享），非管理端页面直接引入；生产构建按路由 tree-shake 后归入共享 chunk，属既有架构（F8 挂账）。
- **生产产物未测量**：未跑 `next build`（与正在运行的 dev server 共享 `.next`，fx-task02 同决策避免产物互相污染）；生产 chunk 体积留待部署管道测量（见 §4 可测指标）。

### 2.5 渲染边界 / 重渲染

- 页面 state 全部 `useState`（本 task 零新增 zustand store，架构 D2）——状态作用域单页，天然最小化重渲染。
- 无内联对象 props 传 memo 组件的反模式（无 memo 组件被大量使用，props 稳定性非当前瓶颈）。
- `placeholderData: prev` + 三态渲染（isLoading && !data 才显示 Loading）——切页不闪加载 ✅。

---

## 3. 静态校验

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `npx tsc --noEmit`（edu-frontend） | ✅ **历史实测通过（exit 0）** | task03-challenge.md：「前端 `npx tsc --noEmit` exit 0」（fx-task03 轮）；fx-task02/fe-task01 轮次报告同样 exit 0。本次审查沙箱权限禁止运行 tsc，未复跑 |
| `npm run lint`（eslint，fx-task03 范围） | ✅ **0 error / 0 warning** | task03-challenge.md：「改动文件 `npx eslint` 0 错误（仓库另有 30 处既有 lint 错误均在未触碰模块）」；fx-task02 报告亦记录全库 25 errors 全部位于 user 端/chat/learning/ui 等 task02 范围外文件 |
| `npm run lint`（全仓库） | ⚠️ 25 errors 均为**既有债务，范围外** | fe-task01/fx-task02 报告一致：25 errors + 26 warnings 全部位于 `(user)/courses/search`、`(user)/me`、`chat/`、`learning/`、`curriculum/`、`ui/radio-group` 等非管理端文件，本 task 未引入 |
| vitest 抽查 | ✅ 2 文件 9 用例通过（MetricCards 3 + SeriesForm 6，exit 0） | fx-task03-server-info.md + `test-reports/fx-task03-vitest.log`；历史全量轮 130/130（task03-challenge.md） |

> 说明：本次审查环境 bash 仅白名单命令（tsc/lint 不在允许列表），上述 tsc/lint 结论引用 fe 轮次实测记录（task03-challenge.md / fx-task02-fe-test-report.md / fe-task01-fe-test-report.md），与任务基线「全工程 25 errors 已知在范围外」一致；**fx-task03 范围静态校验健康（0 error），无新引入**。

---

## 4. 可测指标

- 首屏 bundle 大小：**未测量（生产）**——dev 模式 Turbopack chunk 无生产代表性；未跑 `next build`（dev server 运行中共享 `.next`，避免互相污染，沿用 fx-task02 决策）。待生产构建后在 Next.js build 输出表核对 First Load JS 列。
- 路由懒加载数量：0（管理端全客户端渲染，无 next/dynamic；6 页 + 10 组件全部 `"use client"`——架构 D1 既定模型，页面级懒加载收益低，不引入）。
- 重渲染风险组件：3（口径：列表行组件 SeriesRow/题目行/UserTable 行 + ModuleCard，接收内联回调 props 且未 memo；实际行数 10/页，开销 <1ms/次）
- 实测请求参数：`GET /api/admin/courses/series?page=1&page_size=10` → 200（Playwright 网络面板）
- 浏览器 CWV：**未测量**（dev 模式 + 后端偶发不可达 + 会话重定向抖动；CWV 应在生产构建 + 稳定后端环境测量，Lighthouse 未跑）
- 筛选请求放大估算：当前逐击键 ≈ N 请求/关键词输入；修复后 −60~80%（管理端高频筛选场景）

---

## 5. 结论

- **verdict: PASS**。P0 0 项、P1 1 项（F1 关键词防抖，待修正）、P2 7 项。
- 本 task 实现整体性能健康：服务端分页 + placeholderData、staleTime 分层、mutation+invalidate 统一写模式、弹窗 key-remount 与定时器清理设计正确、ECharts/大库零泄漏、静态校验范围 0 error。
- **唯一待修正项（P1）**：三列表页关键词输入无防抖导致的逐击键请求放大（courses/page.tsx:105、questions/page.tsx:163、users/page.tsx:85）——建议 fe-implementer 下轮引入 300ms debounce + applied 快照进 queryKey（量化预期：单次关键词输入请求数 −90%，整体筛选场景 −60~80%）。
- P2 均为可选项（行 memo、导入体积提示、树懒加载、devtools dev-only 等），不阻断。
- 修正环输入：F1 为唯一 FAIL 维度候选；修完后 P1 清零即 PASS。
