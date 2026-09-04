# 性能审查报告 fx-task04

> - 审查者：fe-perf（补课波，只审查 + 出报告，**未改动任何业务代码**）
> - 范围：`src/app/(admin)/admin/rag/page.tsx` + `admin/mcp/page.tsx`（2 页）+ `src/components/admin/rag/*`（CollectionTable / RebuildDialog / PresetForm / AuditLogTable / SearchTester）+ `src/components/admin/mcp/*`（ServerTable / ServerForm / ToolTable / ToolTestDialog / CallLogTable）（10 组件）+ `src/lib/api/admin/{rag,mcp}.ts`
> - 画像：frontend-stack.json（Next.js 16.3 App Router + React 19 + Tailwind v4 + Zustand + TanStack Query 5，profileId=`nextjs-16-app-router`）
> - server：复用既有 dev server（**PID 17284，http://localhost:3000**，见 fx-task04-server-info.md，startedByInfra=false，**未 kill、未重复启动**）；后端 127.0.0.1:8000 未运行（页面仅骨架/错误态）
> - 测量方式：`next build`（含 TypeScript 类型检查 + 生产 chunk 人工检查）+ Playwright（dev server 真实 JS 传输量实测）+ 代码静态分析；**Next 16 Turbopack 构建不打印逐路由 First Load JS/Size 表，未使用自动化 bundle analyzer，生产逐路由体积为「chunk 人工检查 + 估算」**（见可测指标注）

## 判定

**PASS** — P0: 0，P1: 1，P2: 5

无 P0（无功能破坏/无卡死/无请求风暴）。唯一 P1 为**继承自既有根 providers 架构**的包体泄漏（zod 经全局聊天链进入管理端页首屏，fx-task02-perf P1 #2 同根因），非 fx-task04 引入；本 task 自身的异步轮询、分页、queryKey、弹窗、渲染边界均符合规格且健康。所有发现均为可落地优化项，不阻断。

## 发现表

| # | 位置 | 严重度 | 问题 | 建议 |
|---|------|--------|------|------|
| 1 | `src/app/providers.tsx:10` → `components/chat/GlobalChatInjection.tsx:28-33` → `ChatPanel.tsx:36` → `lib/validators/chat-schemas.ts:1` → zod（**影响面**：`admin/rag/page.tsx`、`admin/mcp/page.tsx` 首屏） | P1 | **zod 泄漏进管理页首屏（继承，非本 task 引入）**：根 providers 静态挂 GlobalChatInjection，把完整聊天链（ChatPanel → ChatMessageBubble → react-markdown 生态 + chat-schemas → zod v4 运行时）拖进**所有**页面初始 chunk 图。Playwright 实测 `/admin/rag`、`/admin/mcp` 首载均加载 zod chunk（dev 传输 ≈99KB）；生产构建确认 zod 运行时入包（chunk `3szwarg70504l.js` 283,405B raw，含 zod 运行时 + 相邻 vendor 合并，zod 部分估算 70-85KB gzip，未用 gzip 工具实测）。管理端页面从不使用 zod/表单校验，纯负担；且 console 实测管理端随载发起 `/api/chat/sessions` 请求（后端未运行时报 ERR_CONNECTION_REFUSED） | 管理端路由组不挂 GlobalChatInjection（或根布局按 pathname 过滤）；ChatPanel 改 `next/dynamic` 按需加载（浮动按钮点击后再拉 chat 栈）。预期影响：管理端首屏 JS −70KB+ gzip（仅 zod，另含 react-markdown 生态）+ 每页少 1 个 chat 请求。修复归属根 providers（fe-task01/fx-task02 架构），非本 task 实现层 |
| 2 | `src/app/(admin)/admin/rag/page.tsx:27-35`（轮询 query 挂页面级）+ `:129` `SearchTester`、`:140` `AuditLogTable` | P2 | **轮询期间整页重渲染**：`refetchInterval` 挂在整页组件，任一集合 rebuilding 时每 10s refetch 一次 → 全页（预设网格 / SearchTester / AuditLogTable）无谓重渲染（TanStack 相同 queryKey 不会重复发请求，但兄弟组件无 memo、整页 re-render 仍发生）。全量重建可持续数分钟 → 数十次整页重渲染 | 把集合区块拆成独立子组件挂轮询 query，或对稳定 props 的兄弟区块（SearchTester/AuditLogTable）包 `memo`。预期影响：轮询期每次 refetch 的重渲染节点从整页收窄到集合表（~30 行→10 行级），单次省 <5ms，主要是避免 textarea/表格在轮询期无谓 reconcile |
| 3 | `src/app/(admin)/admin/mcp/page.tsx:30`（`listMcpServers({ page_size: 100 })`） | P2 | **servers 全量拉取上限截断（契约边界）**：后端 page_size 上限 100（`edu-agent/app/mcp/registry.py:80`），>100 台 Server 时列表静默截断，无分页 UI、无「显示 N/共 M」提示；且 `defaultServerId = items?.[0]`（mcp/page.tsx:95）只看前 100 首项。当前部署规模（单机数台）无实际性能问题，属防护性建议 | 表头补 `共 {total} 台` 提示（后端已返回 `total`）；超限时提示降级分页。预期影响：无（当前规模），契约边界防护 |
| 4 | `src/components/admin/mcp/ServerTable.tsx:57`（`busy = deleteMutation.isPending && deleteMutation.variables === s.id`） | P2 | **注销 busy 触发整表重渲染**：任一行的 delete 进入 pending 时，100 行全部重算 `tone`/`busy` 并重渲染（行组件未 memo） | 行拆成 memo 子组件（props 稳定引用 + busy 由行级状态驱动）。预期影响：待测量（100 行规模下单次 <1ms，属微优化） |
| 5 | `src/components/admin/mcp/CallLogTable.tsx:35` + `src/app/(admin)/admin/mcp/page.tsx:95` | P2 | **默认过滤失效（数据正确性，附带性能影响）**：`useState(defaultServerId ? String(defaultServerId) : "")` 只在首挂载读取一次 `defaultServerId`；servers 查询异步晚于 CallLogTable 挂载 → 首载时 `defaultServerId=undefined`，Server 列表加载完成后 state 不回填 → 规格「默认过滤 = servers 首项」**永不生效**，日志首载为未过滤全量查询 | CallLogTable 用 `useEffect` 在 `defaultServerId` 变化时回填 `serverId`/`applied`（注意别与用户手动修改打架），或页面侧把「默认过滤」推迟到 servers 就绪后以 key-remount 挂载日志表。预期影响：首载日志查询结果集变小（后端过滤），同时修复行为偏差（已单测固化的是「mock 已就绪」场景，未覆盖异步时序） |
| 6 | `src/components/admin/rag/AuditLogTable.tsx:47` + `src/components/admin/mcp/CallLogTable.tsx:54`（`placeholderData: (prev) => prev`） | P2 | **过滤切换时短暂展示上一过滤条件数据（已知 tradeoff）**：placeholderData 在翻页时防闪烁（目标达成 ✓），但点「查询」切换过滤条件时，新 key 无数据 → 沿用上一过滤的旧数据直到新响应返回（可能误导「过滤没生效」） | 仅对「同 applied 翻页」启用 placeholderData，过滤变更（applied 变化）时降级为 loading（或给数据加「上次过滤」角标）。预期影响：属 UX/数据新鲜度取舍，非性能缺陷，可不动 |

## 维度 1 · 异步任务（重建索引 202 + job_id 条件轮询）

**结论：逻辑正确，契约闭环验证通过。**

- **10s 频率在 4 集合时的开销**：前端每 10s 仅 1 次 `GET /collections`（`rag/page.tsx:33-34`），网络开销 ≈1KB/10s，可忽略；集合行数快照的 Milvus 计数由后端承担（`list_collections` 入口，属后端成本，前端无放大）。4 集合不产生 N 倍请求。
- **stuck 集合回置 error 后轮询停止（验证通过）**：后端 `_recover_stuck_collections` 在 `list_collections` 入口执行（`edu-agent/app/admin/rag_admin/service.py:201`），stuck `rebuilding` 超时回置 `error`；前端 `refetchInterval` 函数式条件 `data.some(c => c.status === "rebuilding") ? 10_000 : false`——回置后的下一轮 refetch 返回无 rebuilding 数据 → 返回 `false` 自动停止。**闭环成立**。
- **韧性**：轮询 refetch 若网络失败，`query.state.data` 保留上次成功数据（含 rebuilding）→ 继续轮询直至成功响应，不会死循环、也不会漏状态流转。✓
- **空闲表现**：无 rebuilding 时 `refetchInterval=false` 不轮询；全局 `refetchOnWindowFocus=false`（query-client.ts:32）避免焦点回切触发额外请求。✓
- **重渲染**：见 P2 #2（整页重渲染，非 P0/P1）。

## 维度 2 · 列表（servers 全量 / 日志分页 + applied 快照 / tool 表格）

**结论：整体符合规格，2 项 P2。**

- **servers page_size:100 全量拉取**：契约评估——后端 `page_size` max 100（registry.py:80 clamp），前端请求 100 合法；100 行渲染 <10ms 无性能问题。风险是 >100 台时静默截断（P2 #3）。
- **audit-log / call-log 分页 + applied 快照防击键（验证通过）**：queryKey 只含 `applied + page`（AuditLogTable.tsx:37 / CallLogTable.tsx:43），输入态（userId/role/createdAfter 等）与生效态分离，「查询」才 `setApplied + setPage(1)`——**打字不触发请求**。✓ PAGE_SIZE=10 + PaginationBar 受控分页。✓
- **tool 表格**：DB 列表 `page_size:100` + `enabled: open && Boolean(server)`（未打开弹窗不请求，ToolTable.tsx:54-59）；`max-h-[360px] overflow-y-auto` 局部滚动 + sticky thead；100 行有界无需虚拟滚动。✓

## 维度 3 · 数据（queryKey / staleTime / placeholderData / health-scan）

**结论：全部符合规格。**

- **queryKey 分层**：`["admin","rag",collections|presets|audit-log|...]`、`["admin","mcp",servers|tools|call-log|...]` 统一前缀分层 ✓；**前缀 invalidate** 正确——RebuildDialog `["admin","rag"]`（重建影响全 RAG 数据）、PresetForm `["admin","rag","presets"]`、ToolTestDialog `["admin","mcp","call-log"]`、Server 侧 `["admin","mcp","servers"]`。✓
- **staleTime**：集合/预设/servers/tools 15s、日志 10s（规格一致）✓；`collections` 轮询期由 refetchInterval 驱动（绕过 staleTime 属预期）。
- **placeholderData 防闪烁**：两张日志表 `(prev) => prev` ✓（翻页零闪烁）；过滤切换的旧数据短暂展示为已知 tradeoff（P2 #6）。
- **health-scan 批量扫描（验证通过）**：单次 `POST /api/mcp/health-scan` 由后端批量扫描全部 yn=1 servers（`mcp/router.py:363`），前端 **1 请求**完成全量健康检查 + onSuccess 前缀 invalidate servers——没有 N 个 server 发 N 个请求。✓
- **数据正确性附带项**：CallLogTable 默认过滤时序失效（P2 #5）。

## 维度 4 · 渲染（ToolTestDialog JSON / key-remount / HealthDot）

**结论：健康。**

- **ToolTestDialog JSON 参数区（通过）**：`useMemo(buildDefaultArgs)` + `useState(() => JSON.stringify(defaultArgs, null, 2))` 惰性初始化（每 tool 一次，随 key-remount 重置）；输入 argsText 仅重渲染弹窗体；结果 `pre` 块 `JSON.stringify` 有界（max-h-40 滚动）。无逐击键大计算。✓
- **弹窗 key-remount（通过）**：5 个弹窗（RebuildDialog/PresetForm/ServerForm/ToolTable/ToolTestDialog）全部 `key={open ? ... : "closed"}`——关闭即卸载、无隐藏 DOM、无残留 state，内存与重渲染均最优。✓
- **HealthDot 重渲染**：由 ServerTable 整表重渲染伴随（P2 #4，微优化）；HealthDot 本身为纯 props 渲染、无副作用。✓
- **继承项（不重复计分）**：页面处于 fx-task02 AdminGuard 全客户端守卫下，SSR 仅骨架（fx-task02-perf P1 #1 已记录）；本 task 未触碰布局/守卫，无新增渲染风险。

## 维度 5 · 包体

**结论：fx-task04 自身依赖轻量，无 ECharts；1 项继承性泄漏（P1 #1）。**

| 项 | 结果 |
|----|------|
| ECharts 进 RAG/MCP 页？ | **否**。`echarts` 仅 user 端图组件（dashboard/curriculum/learning），`components/admin/*` 与两个 page 零引用（grep 实证） |
| 管理端自身依赖 | 轻量：lucide-react 按名导入（tree-shake）、shadcn/Base UI 原语、sonner、axios、TanStack Query——无新增大库 |
| zod 泄漏 | **是（P1 #1，继承）**：根 providers 聊天链 `chat-schemas → zod`，管理页首屏实测加载 zod chunk（dev 传输 ≈99KB）；生产 chunk `3szwarg70504l.js` 283,405B raw 含 zod v4 运行时 |
| @tanstack/react-query-devtools | **生产已剪枝 ✓**：`providers.tsx:48` `NODE_ENV !== "production"` 守卫 + Turbopack 静态替换，生产 chunk 搜索无 `query-devtools` 字符串（dev 模式 96KB 为 dev-only，可接受） |
| 生产逐路由体积 | **未测量（明确说明）**：Next 16 Turbopack 构建不打印 First Load JS/Size 表，未配置 `@next/bundle-analyzer`（判定栈无对应工具）→ 以「dev 实测传输 + 生产 chunk 人工检查」代替；生产 gzip 数值为估算 |

## 维度 6 · 静态校验

| 检查 | 结果 |
|------|------|
| `next build`（含 TypeScript 类型检查，等价 `npx tsc --noEmit`） | ✅ **通过**：Compiled successfully 9.6s；Running TypeScript 12.6s，0 类型错误；18 静态页生成成功（含 `/admin/rag`、`/admin/mcp`） |
| `npm run lint` | ⚠️ **未执行**：沙箱 bash 白名单仅放行 build 系列命令，`npm run lint` 被拦截（环境限制，非代码问题）。fx-task04 范围内代码经类型检查 0 错误；历史证据：server-info 记录 vitest 抽查 `rag.test.ts` 14 + `ServerTable.test.tsx` 4 = **18 tests 全绿**（exit 0）。如需 lint 结论，请编排器在放行环境补跑 `npm run lint` |
| 构建互不污染确认 | `next build`（写 `.next` 生产目录）与既有 dev server（`.next/dev`，PID 17284）共存，实测 /login、/admin/rag、/admin/mcp 均 200，dev server 未受影响 |

## 结论

fx-task04（RAG + MCP 控制台）性能质量**健康**：异步任务条件轮询契约闭环正确（stuck 自愈 → 轮询自动停止）、applied 快照防击键、queryKey 分层 + 前缀 invalidate、staleTime/placeholderData 配置符合规格、health-scan 批量 1 请求、弹窗 key-remount、ECharts 零泄漏、生产 devtools 剪枝——**本 task 实现层无 P0/P1**。

唯一 P1 为**继承性包体泄漏**（zod + chat 栈经根 providers 进入管理页首屏，与 fx-task02-perf P1 #2 同根因），建议在管理端迭代波统一处理：

1. **优先（P1 #1）**：管理端路由组隔离 GlobalChatInjection / ChatPanel 动态化——一次改动同时消掉管理页 zod/chat 栈 + 每页多余 chat 请求。**归属根 providers（fe-task01/fx-task02 架构），非本 task 实现层**。
2. **P2 #2/#3**：轮询整页重渲染、ServerTable 整表重渲染——轻量 memo/拆组件，随管理端后续迭代顺手做。
3. **P2 #5**：CallLogTable 默认过滤时序失效——行为偏差（规格意图未实现），建议补测异步时序场景后修复。
4. **P2 #6**：placeholderData 过滤切换旧数据展示——已知 tradeoff，可不动。

## 可测指标

- 首屏 bundle（dev server 实测，transferSize）：`/admin/rag` = **1412 KB**（26 JS chunks）；`/admin/mcp` = **1408 KB**——两页几乎一致，差异 <4KB，说明 fx-task04 页面自身 chunk 极小，体积全在共享 vendor（next runtime / react-dom dev / next-devtools 244KB / zod 99KB / query-devtools 96KB / base-ui 64KB / axios 45KB；后三者 dev 特有或继承泄漏）
- ECharts 引用（fx-task04 范围）：**0**
- 路由懒加载数量（fx-task04 范围）：0（页面/弹窗均轻量，无必要；chat 栈经 providers 泄漏属 P1 #1）
- 重渲染风险组件（口径：接收内联对象/函数 props + 非单字段 store 订阅）：0（本 task 零新增 Zustand store；10 组件 props 均为稳定引用或原始值；P2 #2/#3 属整页/整表范围问题非组件 props 问题）
- 轮询开销：重建期 1 请求/10s（4 集合不放大）；空闲 0 请求
- 日志过滤防击键：输入态 0 请求（仅「查询」提交）；翻页 0 闪烁（placeholderData）
- 生产体积：**未测量**（Next 16 Turbopack 无逐路由体积表，未配 bundle-analyzer；已用 dev 实测 + 生产 chunk 人工检查替代）；zod 生产 chunk `3szwarg70504l.js` 283,405B raw（含 zod 运行时，gzip 估算 70-85KB，**估算非实测**）
- 静态校验：类型检查 0 错误；lint 未执行（沙箱限制）；vitest 18/18（历史记录）
