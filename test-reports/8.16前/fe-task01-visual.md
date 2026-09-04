# 视觉审查报告 fe-task01

> 任务：G1 用户端社区（/community、/community/[postId]）& 成就中心（/achievements）
> 补课波：只审查 + 出报告，禁止改业务代码。审查时间：2026-08-13（UTC+8）
> 审查口径：现状即基线；分功能多色为预期发现（归 fe-task07 收敛，不判 FAIL）；布局/溢出/遮挡/断行等视觉缺陷判 FAIL

## 环境

- **启动方式**：复用 `test-reports/fe-task01-server-info.md` 既有 dev server（`http://localhost:3000`，PID 3780，`next dev`），未重复启动
- **后端**：`http://127.0.0.1:8000` 运行中（`/health` 200，`/api/community/posts` 200 共 59 条帖子）
- **登录态**：task01test / Test@123456（user_id=846）经真实 API 登录 + localStorage 注入，页面渲染真实数据（非 MOCK）
- **截图方式**：Playwright Chromium（MCP）；**本模型不支持图像输入，采用 DOM 几何 + 计算样式程序化审计替代像素级 Read 复核**（每张截图均验证目标 URL 稳定后截取，标注「非像素级复刻」）
- **截图目录**：`test-reports/screenshots/fe-task01/`

## 截图清单（17 张）

| # | 文件 | 内容 | viewport |
|---|------|------|----------|
| 1 | community-1440.png | 社区首页首屏 | 1440×900 |
| 2 | community-1440-full.png | 社区首页全页 | 1440×900 |
| 3 | community-375.png | 社区首页首屏 | 375×812 |
| 4 | community-375-full.png | 社区首页全页 | 375×812 |
| 5 | community-loading-1440.png | 社区加载态（5 张 h-32 骨架，API 延迟 4s 截获） | 1440×900 |
| 6 | community-empty-1440.png | 社区空态（虚线框「这个版块还没有帖子」） | 1440×900 |
| 7 | community-error-1440.png | 社区错误态（rose 卡「加载失败」+ 点击重试） | 1440×900 |
| 8 | community-drawer-375.png | 移动端侧边栏抽屉打开态（8 导航项） | 375×812 |
| 9 | post-detail-1440.png | 帖子详情首屏（/community/48） | 1440×900 |
| 10 | post-detail-1440-full.png | 帖子详情全页 | 1440×900 |
| 11 | post-detail-375.png | 帖子详情首屏 | 375×812 |
| 12 | post-detail-375-full.png | 帖子详情全页 | 375×812 |
| 13 | post-detail-loading-1440.png | 详情加载态（2 张 h-64 骨架，API 延迟 4s 截获） | 1440×900 |
| 14 | achievements-1440.png | 成就中心首屏 | 1440×900 |
| 15 | achievements-1440-full.png | 成就中心全页 | 1440×900 |
| 16 | achievements-375.png | 成就中心首屏 | 375×812 |
| 17 | achievements-375-full.png | 成就中心全页 | 375×812 |

## 发现表

| # | 位置 | 类型 | 严重度 | 说明（实测证据） | 处置 |
|---|------|------|--------|------------------|------|
| F1 | `PostCard.tsx:60` | 内容/文案 | 中 | 列表摘要直接渲染后端 summary 的 **Markdown 源码**：置顶帖首卡可见 `## 欢迎来到 EduAgent 学习社区！`、`- 与同学们交流…`、`**发帖礼仪**` 等语法符号（375/1440 首卡文本实测）。影响列表观感与可读性 | 建议修正：摘要预处理为纯文本（去 Markdown 标记）或轻量渲染；非布局缺陷，不阻塞本判定 |
| F2 | `(user)/layout.tsx:246-251` | 内容/文案 | 低 | 用户端顶栏常驻显示 `当前路径：/community`（`<code>` 调试面包屑）——生产环境不应暴露开发路径信息。壳层共享，非本 task 新增 | 建议修正：删除或仅 dev 模式显示 |
| F3 | `PostCard.tsx:27` 等全站卡片 | 配色漂移（圆角偏离契约） | 低 | 实测卡片计算圆角 **18px**（rounded-2xl）vs 契约 14px（rounded-xl）。范围：PostCard:27、PostEditor:103、CommentSection:83/177、BadgeWall:72、PointLogTable:54/89、achievements:35/42/49、community:116/130/142、[postId]:99/146 | 已登记 **D17**，归 fe-task07 收敛，不判 FAIL |
| F4 | `community/page.tsx:55` 光晕 | 观察项 | — | 页头径向光晕 SVG 元素实测几何右边界 1449px > 视口 1440px，但被页头 `overflow-hidden`（:54）裁剪，**scrollWidth=1440 无水平滚动**，视觉不溢出 | D1 装饰性光晕，归 fe-task07 |
| F5 | `[postId]/page.tsx:84` | 观察项 | — | sticky 工具条实测 `top=64` 与顶栏 `h-16` 完全吻合（z-10 在顶栏 z-20 之下），**无遮挡**；`top-16` 为硬编码依赖 | 已登记 D18/T10，归 fe-task07 |
| F6 | 详情页 375 工具条面包屑 | 观察项 | — | 长标题「👋 欢迎来到 EduAgent 学习社区！」在 375 下 `truncate` 省略（设计内响应式行为，clippedCount=1 为显式 ellipsis） | 记录不修；如需完整可见可缩短标题 |

**未发现**：水平溢出（1440 与 375 scrollWidth=clientWidth）、元素遮挡重叠、异常断行、卡片间距不一致（列表 `space-y-3`、主区 `space-y-4` 全局一致）、文本非设计内截断。

## 多色现状清单（预期发现，全部标注「归 fe-task07」，本任务不改）

> 实测计算样式 + 源码核对，file:line 精确；与 `visual-acceptance.md` D1-D21 一致。收敛目标 = 方向 A（slate/indigo 单主色 + 状态色表）。

| # | 位置 | 现状 | 归 fe-task07 编号 |
|---|------|------|-------------------|
| M1 | `community/page.tsx:54-55` | 页头三色渐变 `from-indigo-600 via-violet-600 to-sky-600` + 径向光晕 | D1 |
| M2 | `achievements/page.tsx:20-21` | 页头渐变 `from-amber-500 via-orange-500 to-rose-500` + 光晕 | D2 |
| M3 | `achievements/page.tsx:71` | SectionTitle 渐变图标底 `from-amber-500 to-orange-400`（实测 h=40） | D3 |
| M4 | `community-meta.ts:18-21` | 分版 8 组色值：english sky/cyan、math emerald/teal、programming violet/purple、general slate（colorClass+gradientClass 双轨） | D8 |
| M5 | `BoardTabs.tsx:43` | 分版彩色圆点 `bg-current` + gradientClass | D9 |
| M6 | `PostCard.tsx:32` | 分版 Badge 用 `board.colorClass`（多色） | D10 |
| M7 | `PostCard.tsx:28` | 置顶 `border-amber-300/60 bg-amber-50/40` | D14 |
| M8 | `PostEditor.tsx:123` | 分版选中态 `gradientClass` 渐变填充 | D11 |
| M9 | `PostEditor.tsx:106` | 发帖奖励提示 `text-amber-600` | D15 |
| M10 | `ReactButtons.tsx:78` | 点赞激活 `bg-rose-500`（rose 危险色被功能化） | D12 |
| M11 | `ReactButtons.tsx:99` | 收藏激活 `bg-amber-500`（amber 警告色被功能化） | D12 |
| M12 | `CommentSection.tsx:205` | 评论点赞激活 `fill-current text-rose-500`；:197 hover `text-rose-600` | D13 |
| M13 | `CommentSection.tsx:105` | 回帖奖励提示 `text-amber-600` | D15 |
| M14 | `BadgeWall.tsx:16-21` | 稀有度四色 slate/sky/violet/amber（游戏化惯例） | T7 决策，暂保留 |
| M15 | `BadgeWall.tsx:74` | 解锁徽章渐变卡 `from-amber-50/80 to-white` | D6 |
| M16 | `BadgeWall.tsx:77` | 进度条渐变 `from-amber-300 to-amber-200`；:119 已解锁段 `from-primary/70 to-primary` 渐变 | D7 |
| M17 | `BadgeWall.tsx:49/128` | 「下一枚」「+N 积分」提示 `text-amber-600` | D16 |
| M18 | `PointLogTable.tsx:54` | 积分头卡渐变 `from-indigo-600 via-indigo-500 to-sky-500`（实测 h=142） | D4 |
| M19 | `PointLogTable.tsx:77` | 等级进度条 `from-amber-300 to-amber-200` | D7 |
| M20 | `PointLogTable.tsx:173` | 渐变 skeleton `from-indigo-200 to-sky-200` | D5 |
| M21 | `PointLogTable.tsx:111/128` | 积分正负 `bg-emerald-50 text-emerald-600` / `bg-rose-50 text-rose-600` | 状态色正确用法，T5 token 化（保留） |
| M22 | `RankingTabs.tsx:50-54` | 金/银/铜奖牌 `text-amber-500/slate-400/orange-400` | A7 排名惯例（保留） |
| M23 | 壳层 `layout.tsx:128/157/212/267/316` | 品牌 logo/CTA/头像渐变 indigo→sky | 品牌渐变，允许保留 |
| M24 | 壳层 `layout.tsx:182` | 侧边栏激活项 `bg-gradient-to-r from-indigo-600 to-indigo-500` | 品牌范围渐变；建议 fe-task07 与 admin 壳激活态对齐确认 |
| M25 | 错误态 rose 卡（community:130、CommentSection:131、BadgeWall:33、RankingTabs:117、[postId] 系列） | 状态色语义正确 | 保留（A3） |

## 三态可达性（route 拦截验证，未改业务代码）

| 状态 | 页面 | 实测 | 截图 |
|------|------|------|------|
| 加载 | 社区列表 | 5 张 `h-32 animate-pulse` 白卡骨架（API 延迟 4s 截获） | community-loading-1440.png |
| 加载 | 帖子详情 | 2 张 h-64 脉冲骨架 | post-detail-loading-1440.png |
| 空 | 社区列表 | 虚线框 + `bg-primary/10` 图标 +「这个版块还没有帖子 / 当前没有帖子，来发布第一篇吧～」 | community-empty-1440.png |
| 错误 | 社区列表 | rose 卡「加载失败」+ 错误消息 +「点击重试」（500 模拟） | community-error-1440.png |
| 移动端 | 抽屉导航 | 汉堡按钮打开抽屉（left=0 w=256，8 导航项，遮罩 z-30/抽屉 z-40 层级正确） | community-drawer-375.png |

## 与 design-tokens.json 对照

| 检查点 | tokens 契约 | 实测 | 判定 |
|--------|-------------|------|------|
| 页面底色 | `pageBg: bg-slate-50/70` | 3 页 + 壳层均 `bg-slate-50/70` | ✅ 符合 |
| 容器 | `max-w-5xl mx-auto px-4 py-6 md:px-6` | 实测 left=328 right=1352 w=1024（1440 视口居中） | ✅ 符合 |
| 卡片间距 | `listCard p-4 md:p-5` / `sectionCard p-5 md:p-6` | PostCard `p-4 md:p-5`、成就区块 `p-5 md:p-6` | ✅ 符合 |
| 列表/主区间距 | `space-y-3` / `space-y-4` | 实测一致 | ✅ 符合 |
| 卡片圆角 | `contract: rounded-xl = 14px` | 实测全站卡片 **18px**（rounded-2xl） | ⚠️ D17 偏离，归 fe-task07 |
| 卡片样式 | 白卡 + border + 细 shadow | 实测 `border bg-white`、hover 细 shadow-sm；置顶卡 amber 底（D14） | ⚠️ 多色项归 fe-task07 |
| 字体 | 系统栈（未引入自定义字体） | `-apple-system…'Microsoft YaHei'` 生效；字号模式：h1 2xl/3xl、正文 sm、元信息 xs、标签 11px | ✅ 符合 |
| 数字 | `tabular-nums` 计数 | PostCard 四计数、积分/排行均 tabular-nums | ✅ 符合 |
| 语义 class | `bg-primary/text-muted-foreground/bg-muted/border-border/bg-destructive` | 空态图标 `bg-primary/10 text-primary`、标签 `text-muted-foreground`、错误态均语义 class | ✅ 符合（A1） |

## 响应式验收（V4）对照

- **1440**：无水平溢出（scrollWidth=1440=clientWidth）；徽章网格 4 列（实测 223px×4）；页头/卡片正常
- **375**：无水平溢出（scrollWidth=360=clientWidth，差 15px 为垂直滚动条）；徽章网格 **2 列**（实测 137px×2，`grid-cols-2 sm:grid-cols-3 lg:grid-cols-4` 生效）；侧边栏正确收为抽屉；sticky 工具条满宽不遮内容；顶栏「问 AI」按钮 `hidden sm:inline` 折叠
- **遮挡**：顶栏 z-20 / sticky 工具条 z-10 / 抽屉 z-40 / 遮罩 z-30 层级正确，无相互遮挡

## 判定

- **结论：PASS**
- **阻塞项：无**（未发现布局溢出、元素遮挡、异常断行、非设计内截断）
- **必须修正项：无**（本 task 为补课基线，不改代码）
- **不构成 FAIL 项**：分功能多色（M1-M20/M24）与圆角偏离（F3）均为视觉验收已登记的 fe-task07 执行清单（D1-D21），按任务口径如实记录现状
- **建议修正（不阻塞）**：F1 摘要 Markdown 源码暴露（影响列表观感）、F2 顶栏「当前路径」调试面包屑（壳层共享，建议与 fx-task05/fe-task07 一并处理）
- **审查限制说明**：本模型不支持图像输入，采用程序化 DOM/计算样式审计（含 route 拦截三态），截图已存盘供 fe-task07 收敛后人工像素级对比；结论标注「非像素级复刻」
