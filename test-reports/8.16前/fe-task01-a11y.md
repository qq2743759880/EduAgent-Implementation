# 无障碍审查报告 fe-task01

> 审查者：fe-a11y-auditor｜日期：2026-08-13｜范围：G1 用户端社区 & 成就中心（补课波：只审查出报告，未改任何代码）
> 标准：WCAG 2.2 AA｜方法：静态代码审查 + Playwright 实机验证（dev server http://localhost:3000，复用 fe-task01-server-info.md 进程）

## 审查范围

| 页面 | 实现文件 |
|------|----------|
| /community（社区列表+发帖） | `src/app/(user)/community/page.tsx`、`src/components/community/{BoardTabs,PostCard,PostEditor}.tsx` |
| /community/[postId]（帖子详情） | `src/app/(user)/community/[postId]/page.tsx`、`src/components/community/{ReactButtons,CommentSection}.tsx` |
| /achievements（成就中心） | `src/app/(user)/achievements/page.tsx`、`src/components/achievement/{BadgeWall,PointLogTable,RankingTabs}.tsx` |
| 基础设施（影响上述页面） | `src/components/ui/{button,input,textarea,label}.tsx`、`src/app/globals.css`、`src/app/providers.tsx`（sonner Toaster） |

## 实测记录（Playwright，http://localhost:3000）

### /community（smoke 账号登录后）
- 标题层级：h1「学习社区」✓；tablist「社区分版」（5 tab，aria-selected ✓）；排序按钮组 aria-pressed ✓；PostCard 为 article + 详情 Link ✓。
- **焦点指示（2.4.7）**：Tab/排序按钮聚焦时 computed outline = `oklab(0.708 0 0 / 0.5) auto 0.667px`（globals.css L122 全局 `outline-ring/50`），即 50% 透明浅灰细线，在白/浅灰底上对比 ≈1.4:1，肉眼几乎不可见；shadcn Button 为 `focus-visible:ring-3 ring-ring/50`（3px 半透明灰，≈1.5:1），均不满足可见焦点指示。
- **方向键**：聚焦 tab 按 ArrowRight 无任何反应（aria-selected 不变、焦点不动）→ 无 APG tabs 方向键导航。
- PostEditor 打开后实测：`label[for="post-content"]` 存在，但 `id="post-content"` 被渲染到 `.w-md-editor` **DIV** 上；内部 textarea `id=""`、无 aria-label/aria-labelledby → label 关联失效。
- sonner Toaster：`aria-live="polite"` + `aria-label="Notifications alt+T"` ✓（状态提示可被读屏器播报）。
- console：**0 errors / 0 warnings**。

### /community/48（详情页）
- h1=帖子标题，Markdown 正文 h2 ✓；article/header/section 语义 ✓。
- ReactButtons：button + aria-pressed ✓，点击后状态/计数正常切换（1→0）。
- **点赞激活态实测**：bg `lab(49.19 81.58 36.03)`（rose-500）+ 白字 → 对比 **3.68:1** < 4.5:1（1.4.3 违规）。
- CommentSection 回帖 textarea：`id=""`、`aria-label=null`、`aria-labelledby=null`，仅 placeholder → **无程序化 label**（3.3.2 违规）。
- 视口 1440×900：点赞/收藏按钮名称「1已赞」「3收藏」（含语义文字，sm:inline 生效）；<640px 时文字隐藏，名称只剩数字。

### /achievements
- 标题层级 h1「成就与成长」→ h2「徽章/积分/排行榜」→ h3「我的徽章/学习排行榜」✓。
- 双 tablist（排行时间范围 4 tab / 排行维度 3 tab）aria-selected ✓；**无 tabpanel / aria-controls / 方向键**（与 BoardTabs 同构）。
- 徽章卡片：`div[aria-label="徽章 X（未解锁）"]` 生效，但无 role 的非交互 div 上加 aria-label → 实测 a11y 树中卡片名称与内部文本（描述/进度 0/60）**并存重复朗读**。
- 排名行 1-3：crown `text-amber-500` / medal `text-slate-400` / medal `text-orange-400`，均位于 amber-50 底上（对比 2.07–2.47:1，均 <3:1）；第 2/3 名 Medal 同形状仅颜色不同；1-3 名**无排名数字文本**。
- console：0 errors。

### 说明
- /achievements 实机验证期间 MCP 浏览器会话出现标签页漂移，部分测量基于同构组件（BoardTabs 与 RankingTabs 结构一致已实机确认）与静态计算，计算项已在表中标注「计算」。

## 发现表

| # | 位置 | 严重度 | 原则 | 问题 | 修复建议 |
|---|------|--------|------|------|----------|
| 1 | `ReactButtons.tsx:99`（收藏激活态 `bg-amber-500 text-white`） | BLOCKER | 1.4.3 | 收藏激活态白字 on amber-500 对比 **2.15:1**（计算），按钮文字+计数不可读 | 激活态改 `bg-amber-700 text-white`（5.02:1）或等效深色底；确保 ≥4.5:1 |
| 2 | `globals.css:122`（`* { outline-ring/50 }`）+ `ui/button.tsx:8`、`ui/input.tsx:12`、`ui/textarea.tsx:10`（`focus-visible:ring-ring/50`）；`BoardTabs.tsx:83-97`（tab 无显式 focus-visible） | BLOCKER | 2.4.7 | 全站焦点指示为 50% 透明浅灰 oklab(0.708)，对比 ≈1.4–1.5:1；分版 tab 更只有 0.667px 细线，键盘用户无法定位焦点 | 将 ring/outline 改为高对比色（≥3:1，如 `ring-foreground`/`ring-primary` 全不透明）并给自定义 tab/排序按钮补 `focus-visible:ring-3` |
| 3 | `ReactButtons.tsx:78`（点赞激活态 `bg-rose-500 text-white`） | HIGH | 1.4.3 | 白字 on rose-500 = **3.68:1**（实测）< 4.5:1 | 加深底色为 rose-600（白字 ≈4.7:1）或改深色文字 |
| 4 | `CommentSection.tsx:97-103` | HIGH | 3.3.2 / 1.3.1 | 回帖 textarea 无 `<label>`/aria-label（实测 aria-label=null、id=""，仅 placeholder） | 加 `Label htmlFor="reply-content"` 或 `aria-label="回帖内容"` |
| 5 | `PostEditor.tsx:155-164` | HIGH | 1.3.1 / 3.3.2 | `Label htmlFor="post-content"` 指向 MDEditor 容器 DIV（实测），内部 textarea 无 id/aria-label，label 点击不聚焦、读屏器不关联 | 向 MDEditor 传 `textareaProps={{ id: "post-content" }}`（或给 textarea 加 aria-label/aria-labelledby） |
| 6 | `PostEditor.tsx:61-62, 141-150` | HIGH | 3.3.1 / 1.3.1 | 表单校验错误无 `aria-invalid`、无 `aria-describedby`；错误文案是普通 span，无 aria-live/role=alert，读屏器不播报 | Input/Textarea 加 `aria-invalid={touched && !valid}` + `aria-describedby="post-title-error"`，错误 span 加 `id` 与 `role="alert"`（或 aria-live） |
| 7 | `BoardTabs.tsx:29-47, 83-97`；`RankingTabs.tsx:69-107` | HIGH | 4.1.2 / 2.1.1 | role=tablist/tab 但无 `aria-controls`、无对应 `tabpanel`、无方向键导航（实测 ArrowRight 无效）；Tab 键遍历所有 tab（非 roving tabindex），不符合 APG tabs 模式 | 补 roving tabindex + ArrowLeft/Right（RankingTabs 为上下）切换 + `aria-controls` 指向 tabpanel，或降级为普通按钮组（去掉 role=tab） |
| 8 | `RankingTabs.tsx:49-54, 147-151` | HIGH | 1.4.11 / 1.4.1 / 1.1.1 | 前三名图标 on amber-50：amber-500=2.07:1、slate-400=2.47:1、orange-400=2.18:1（计算）均 <3:1；第 2/3 名 Medal 同形仅色差；1-3 名无排名数字文本（读屏器听不到「第 1 名」） | 深色图标（如 amber-600/slate-600/orange-600）+ 保留排名数字（`sr-only` 文本或直接显示数字） |
| 9 | `PointLogTable.tsx:54-85` | HIGH | 1.4.3 | 渐变卡右上 sky-500 区域白字 ≈2.77:1、text-white/80 与 /70 更低（计算） | 渐变改用更深色（indigo-700→sky-600）或将右侧文本置于深色区/加深背景 |
| 10 | `PointLogTable.tsx:111, 128` | HIGH | 1.4.3 | 积分流水 +分 `text-emerald-600` = 3.77:1（计算）< 4.5:1（text-sm） | 用 emerald-700（≈5.5:1） |
| 11 | `PostEditor.tsx:107`、`CommentSection.tsx:105`、`BadgeWall.tsx:49, 129` | HIGH | 1.4.3 | 多枚奖励提示小字（text-xs / text-[11px]）`text-amber-600` = 3.19:1（计算）< 4.5:1 | 改用 amber-700（≈5.0:1） |
| 12 | `BadgeWall.tsx:77` | HIGH | 4.1.2 / 1.3.1 | 无 role 的 div 上使用 aria-label（实测 a11y 树中卡片名称与内部文本并存，徽章名/描述/进度被重复朗读） | 移除 aria-label（内部已有完整文本）；如需分组语义用 `role="group"` 或改 `article` |
| 13 | `PointLogTable.tsx:107-138` | LOW | 1.3.1 | 积分流水用 div 行而非 `<table>`（行内数据点：类型/时间/±分/余额），读屏器无行列结构 | 可选：改为语义表格；列表形式可接受，不阻塞 |
| 14 | `PostCard.tsx:82-93` | LOW | 1.1.1 / 1.3.1 | 浏览/点赞/回帖/收藏统计仅有 `title` 属性（实测被读为名称「浏览 130」，但 title 非可靠无障碍机制） | 加 `sr-only` 文本或 `aria-label="浏览 130"` |
| 15 | `ReactButtons.tsx:87, 108` | LOW | 1.1.1 | 窄视口（<640px）下「已赞/点赞」「已收藏/收藏」文字 display:none，按钮名称只剩数字 | 用 `sr-only` 替代 `hidden sm:inline` |
| 16 | `CommentSection.tsx:93` | LOW | 1.4.3 | 回复取消 chip 的 `×` 为 text-slate-400（2.57:1） | 改 slate-600 |
| 17 | `PostEditor.tsx:112-130` | LOW | 2.1.1 | role=radiogroup 无方向键导航（每个 radio 独立 tab stop，APG radio 模式不完整） | 补 roving tabindex + Arrow 键 |
| 18 | `PostEditor.tsx:105`（h3「发布新帖」） | LOW | 1.3.1 | /community 页面 h1 之后直接 h3（无 h2），标题跳级 | 改 h2 或补 h2 层级 |
| 19 | 全局（`CommentSection.tsx:228`、`PostEditor.tsx:198`、页面骨架等 animate-pulse/spin/transition） | LOW | 2.3.3（AAA）/ 动效偏好 | 项目无 `prefers-reduced-motion` 处理（globals.css、tw-animate-css 均无 reduce 规则） | 全局加 `@media (prefers-reduced-motion: reduce)` 禁用 pulse/spin；AA 级不阻塞 |
| 20 | `BadgeWall.tsx:117-122` | LOW | 1.3.1 | 进度条无 `role="progressbar"`/aria-valuenow（有文本「0/60」兜底，可接受） | 可选：加 role=progressbar + aria 值 |

## 判定

- **结论：FAIL**（存在多项 WCAG 2.2 AA 违规）
- 违规统计：BLOCKER 2 项、HIGH 10 项、LOW 8 项（共 20 项发现，涉及 1.4.3 / 1.4.11 / 1.4.1 / 2.4.7 / 2.1.1 / 3.3.1 / 3.3.2 / 4.1.2 / 1.3.1 / 1.1.1）
- **阻塞项（必须修正后才能判 PASS）**：
  1. `ReactButtons.tsx:99` — 收藏激活态白字 on amber-500 = 2.15:1（1.4.3 严重不达标）
  2. 全站焦点指示对比不足：`globals.css:122` + 各组件 `focus-visible:ring-ring/50` = 50% 透明浅灰（2.4.7，键盘用户无法定位焦点；分版 tab 仅 0.667px 细线）
- 其余 HIGH（表单 label 关联 #4/#5、错误提示 #6、tabs 模式 #7、排名图标 #8、多处对比度 #3/#9/#10/#11、徽章 aria-label #12）应随下一个 task 一并修复；LOW 项可排期优化。
- 实机验证覆盖率：/community、/community/[postId] 完整实测；/achievements 因 MCP 会话漂移部分以静态计算佐证（#8/#9/#10 的计算值基于 Tailwind 色值，换算误差 ±0.05:1）。
