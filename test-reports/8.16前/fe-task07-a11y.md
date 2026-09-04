# fe-task07 无障碍审查报告（a11y）

> 审查角色：fe-a11y-auditor ｜ 依据：WCAG 2.2 AA
> 审查对象：fe-task07（用户端全页面风格统一收敛 → 管理端风格）
> 审查方式：**实机验证**（Playwright + Chromium 实测 5 页 + 浏览器内 oklch→sRGB 精确对比度计算 + 代码静态审查）
> 基线：frontend-stack.json（nextjs-16-app-router）· `.claude/specs/frontend/fe-task07/design-options.md`（keepList 保留清单）· `test-reports/fe-task07-server-info.md`（dev :3000，PID 16676，后端 8000 运行中）

---

## 审查范围

- 用户端 9 页中的 5 个验收页：`/dashboard` `/community` `/achievements` `/courses` `/chat`（其余 4 页 my-courses/learning/me/practice 与 5 页共用组件，静态同源）
- 收敛组件（按 design-options §6 锚点逐项核对 className）：PostCard、ReactButtons、ReviewList、BoardTabs(community-meta)、SourceCardList、ChatMessageBubble、ChatFloatingButton、ChatSessionSidebar、RankingTabs、RankList、KpiCard、BadgeWallGrid、PointCard、StreakBadge、PointLogTable、BadgeWall、CommentSection、PostEditor、CourseCard、MyCourseCard、StatStrip(my-courses)、ProfileLayout
- 审查时间：2026-08-13 12:10
- 被审文件（file:line 在发现表中标注）

## 验证方式

- **实机**：Playwright 连接 `http://localhost:3000`（复用 fe-task06 登录态），5 页逐一渲染 + 全页对比度扫描（canvas 解析 computed lab()/oklch() 颜色 → WCAG 对比度，含 alpha 合成）+ 键盘 Tab 焦点抽查 + console 核查。
- **计算**：token 理论值按 globals.css `:root` oklch 值做 oklch→linear-sRGB 精确换算（与浏览器实测渲染 rgb 一致，误差 ±0.02）。
- 说明：本 task 为**纯视觉收敛**（className/色值，零行为/结构/aria 改动），静态审查逐项确认 ReactButtons `aria-pressed`、SourceCardList `role="list"`、RankingTabs roving tabindex 等无障碍属性**全部保留**。

---

## 判定：**FAIL**

- 违规总数：**17 项**（BLOCKER 5 / HIGH 7 / LOW 5）
- 阻塞项：5 项 BLOCKER 必须修正后方可发布（见下）。

---

## 发现表

| # | 位置 | 严重度 | 原则 | 问题 | 修复建议 |
|---|------|--------|------|------|----------|
| B1 | `src/components/dashboard/StreakBadge.tsx:41-44` | **BLOCKER** | 1.4.3 文字对比度 | 连续打卡天数徽章 `bg-warning text-white`：白字 on amber-500 **2.13:1**（实测），远低于 4.5:1。「0」「天」为关键信息文字（18px bold 未达大文本门槛 18.66px）。warning token（oklch 0.769 0.188 70.08=amber-500）过亮，白字/深字在其上均不达标 | 徽章底改用深档：`bg-warning-foreground text-white`（amber-700 底+白字 ≈8:1），或 `bg-warning/15 text-warning-foreground` 浅底深字（4.71:1） |
| B2 | `src/components/chat/ChatFloatingButton.tsx:106` | **BLOCKER** | 1.4.3 | 未读消息 badge `bg-warning text-white`：text-4xs(10px) 白字 on amber-500 **2.13:1**，「未读消息数」是提醒关键信息，实际几乎不可读 | 同 B1：改 `bg-warning-foreground text-white` 或 `bg-warning/15 text-warning-foreground` |
| B3 | `src/components/curriculum/ReviewList.tsx:86-88` | **BLOCKER** | 1.4.3 | 评分均分数字 `text-warning`（amber-500）on white **2.15:1** < 4.5:1；14px semibold 信息文字（平均分），低视力用户不可读 | 均分数字改用 `text-warning-foreground`（amber-700，5.05:1 ✓）；design-options §2.3 的「text-warning」在 token 值为 amber-500 时不成立 |
| B4 | `src/components/dashboard/StreakBadge.tsx:89` | **BLOCKER** | 1.4.3 | partial 打卡格 `bg-warning text-white`（「~」12px 字符）**2.13:1**，部分打卡状态字符不可读 | 同 B1：格内符号改深色 `text-warning-foreground` 或底加深 |
| B5 | `src/components/curriculum/ReviewList.tsx:99,168` | **BLOCKER** | 1.4.11 非文本 | 星级图标 `fill-warning text-warning`（amber-500）on white **2.15:1** < 3:1（非文本图形对比度）；星级是评分量表核心可视反馈 | 星形改用 `fill-warning-foreground text-warning-foreground`（amber-700，≥3:1）或加深 amber 档位 |
| H1 | `src/components/dashboard/PointCard.tsx:90-94,143`；`src/components/community/CommentSection.tsx:127`；`PostEditor.tsx:124`；`PointLogTable.tsx`；`KpiCard.tsx:105`；`RankList.tsx:185`；`CourseSyllabusTree.tsx:110,117` | **HIGH** | 1.4.3 | `text-success`（emerald-600）作 10-14px 小字 on white **3.65:1** < 4.5:1（积分增减 +2/+5、回帖奖励、免费/完成等状态文字）；emerald-600 作为小字不达标（仅大文本/图形 3:1 可用） | 小字信息场景改用 `text-success-foreground`（emerald-700，4.80:1 ✓）；保留 `text-success` 仅用于大数字/图标/圆点 |
| H2 | `src/components/dashboard/PointCard.tsx:94-97` 等 `bg-success/10 text-success` 组合 | **HIGH** | 1.4.3 | text-success on bg-success/10 合成底 **3.28:1** < 4.5:1（浅底进一步降低对比） | 浅底场景统一 `text-success-foreground`（4.80:1 ✓） |
| H3 | `src/components/**` 错误态 `bg-destructive/10 text-destructive`（community/dashboard 等） | **HIGH** | 1.4.3 | text-destructive on bg-destructive/10 **3.94:1** < 4.5:1（rose-600 浅底小字） | 错误提示小字改用 `text-destructive-foreground`（rose-700 深档） |
| H4 | 用户端实心 destructive 按钮 `bg-destructive text-white`（shadcn destructive variant，错误态操作按钮） | **HIGH** | 1.4.3 | white on bg-destructive **4.32:1** < 4.5:1（14px 按钮字，临界不足） | 按钮文字加深为 destructive-foreground 同值深档或按钮底加深 rose-700 |
| H5 | `src/components/achievement/RankingTabs.tsx:44`；`dashboard/RankList.tsx:52`（第一名 Crown 奖牌 `text-warning`） | **HIGH** | 1.4.11 | 奖牌图标 amber-500 on white **2.15:1** < 3:1（名次数字 badge 已有结构补偿，但图标本身对比不足） | 奖牌改 `text-warning-foreground`（amber-700）或加深档位；数字补偿维持 |
| H6 | `src/components/curriculum/ReviewList.tsx:102`（评分统计条 `bg-warning` on `bg-muted`） | **HIGH** | 1.4.11 | 统计条 amber-500 vs slate-100 **1.96:1** < 3:1，分布条视觉不可辨 | 统计条改 `bg-warning-foreground`（amber-700）或加深 amber |
| H7 | `src/components/chat/ChatMessageBubble.tsx:260`（系统消息 `bg-muted text-muted-foreground`） | **HIGH** | 1.4.3 | text-muted-foreground(slate-500) on bg-muted **4.35:1** < 4.5:1（14px 系统消息正文，临界） | 系统消息正文改 `text-secondary-foreground`（slate-800，13.4:1）或全站调深 muted-foreground |
| L1 | 全站 `text-muted-foreground` 小字（KPI 标题/卡片描述/排行榜名次/tab 未激活态，实测 4.35:1） | LOW | 1.4.3 | slate-500 on white 4.35:1 临界不达标（10-14px 大量使用）；**全站基座问题，非 fe-task07 收敛引入**（管理端同源、token 系 fe-task00 固化），建议全站统一优化 | 后续全站 task 将 muted-foreground 加深至 slate-600（≈5.7:1）或限制 10px 信息文字（text-4xs 仅装饰角标） |
| L2 | `src/components/dashboard/RankList.tsx:209-237`（我的排名行 `bg-primary-soft` 上 `text-muted-foreground` 4.26:1） | LOW | 1.4.3 | 收敛后新背景上 muted-foreground 10-11px 小字 4.26:1 临界 | 同 L1 基座处理，或该行文字改用 secondary-foreground |
| L3 | 全站输入框 `border-border`/`border-input`（slate-200）vs white | LOW | 1.4.11 | 输入框边界 **1.23:1** < 3:1（表单控件边界识别依赖）；shadcn 全站基座（管理端同源），非本 task 引入 | 全站统一：输入框边框加深（slate-300+）或加内阴影/底色区分；后续基座 task 处理 |
| L4 | `src/components/chat/ChatFloatingButton.tsx:113`（sparkles 角标 `bg-warning text-white` 2.13:1） | LOW | 1.4.11 | 装饰性角标图形对比不足（无信息承载，产品识别用途） | 随 B2 一并改为深档 |
| L5 | `src/components/dashboard/StreakBadge.tsx:36`（标题 Sparkles 图标 `text-warning` 2.15:1）；done 格 white on bg-success 3.51:1（✓ 状态图形 3:1 达标） | LOW | 1.4.11 | 标题装饰图标对比不足（有文字「连续打卡」补偿）；done 格属状态图形 3.51≥3:1 可接受 | 装饰图标随 warning 档位加深；done 格维持 |
| 范围外 | `src/components/auth/AuthCard.tsx:38,44`（`via-white to-sky-50`、`from-indigo-600 to-sky-500`）、`LoginForm.tsx:135,156`（rose raw 错误态、`to-sky-600` 渐变按钮）、`RegisterForm.tsx:209`（`from-emerald-600 to-teal-600`） | — | 1.4.11/7 | auth 页面存在 sky/teal 越界色 + 装饰渐变，**不在 fe-task07 9 页收敛清单内**（design-options §6），但违反「全站唯一规范」（§1.1 封闭色板） | 交后续收敛 task（或扩展 fe-task07 范围）将登录/注册页纳入主色板；本报告不计入 fe-task07 违规数 |

---

## 对比度实测表（收敛后语义色全量）

> 基准：文字 4.5:1（大文本 3:1）；非文本/图形/边框/焦点环 3:1（WCAG 1.4.11）。实测 = Chromium 渲染 + canvas 解析合成；理论 = oklch→sRGB 精确换算（一致）。

| # | 色对 | 实测比值 | 门槛 | 判定 |
|---|------|---------|------|------|
| 1 | `text-warning`（amber-500）on white | 2.15 | 4.5 | ❌ 严重 |
| 2 | white on `bg-warning`（打卡数/未读 badge/partial 格） | 2.13 | 4.5 | ❌ 严重 |
| 3 | `text-warning-foreground`（amber-700）on `bg-warning/10`（置顶角标） | 4.71 | 4.5 | ✅ |
| 4 | `text-success`（emerald-600）on white | 3.65 | 4.5 | ❌ |
| 5 | `text-success` on `bg-success/10` | 3.28 | 4.5 | ❌ |
| 6 | `text-success-foreground`（emerald-700）on `bg-success/10` | 4.80 | 4.5 | ✅ |
| 7 | white on `bg-success`（done 格，图形 ✓ 3.51≥3 达标） | 3.51 | 3/4.5 | ⚠️ 图形可、文字不可 |
| 8 | `text-destructive`（rose-600）on white | 4.51 | 4.5 | ✅ 临界 |
| 9 | `text-destructive` on `bg-destructive/10` | 3.94 | 4.5 | ❌ |
| 10 | white on `bg-destructive`（实心按钮） | 4.32 | 4.5 | ❌ 临界 |
| 11 | `text-primary`（indigo-600）on white | 6.44 | 4.5 | ✅ |
| 12 | `text-primary` on `bg-primary-soft`（indigo-50） | 5.76 | 4.5 | ✅ |
| 13 | `text-primary` on `bg-primary/10` | 5.56 | 4.5 | ✅ |
| 14 | `text-primary-soft-foreground` on `bg-primary-soft` | 7.22 | 4.5 | ✅ |
| 15 | white on `bg-primary`（主按钮/激活态） | 6.17 | 4.5 | ✅ |
| 16 | white on 品牌渐变 `from-primary-deep to-primary-strong`（深端→浅端） | 14.0 / 7.7 | 4.5 | ✅ |
| 17 | `text-foreground` on white | 17.8 | 4.5 | ✅ |
| 18 | `text-muted-foreground` on white / on `bg-muted` | 4.35 | 4.5 | ❌ 临界（基座） |
| 19 | 图标 warning on white（1.4.11） | 2.15 | 3 | ❌ |
| 20 | 图标 success on white（1.4.11 在线点） | 3.67 | 3 | ✅ |
| 21 | 图标 destructive / primary on white（1.4.11） | 4.51 / 6.44 | 3 | ✅ |
| 22 | 进度条 `bg-warning` vs `bg-muted`（统计条 1.4.11） | 1.96 | 3 | ❌ |
| 23 | `border-border` vs white（输入框边界 1.4.11） | 1.23 | 3 | ❌（基座） |
| 24 | `ring` vs white（焦点环 1.4.11） | 4.58 | 3 | ✅ |

**核心结论**：收敛的**正面成果**——primary 系/品牌渐变/中性/foreground 全部达标（#11-17），courses 页零违规（价格 `text-foreground font-bold`、购买按钮 `bg-primary`、封面主色渐变均达标）。
**负面**——`warning`（amber-500）token 全系崩坏（#1/#2/#19/#22）：对比度 1.96-2.15，远低于文字 4.5 与非文本 3；`success`（emerald-600）在小字场景不足（#4/#5）。根源是 design-tokens 将 warning 定在 amber-500（oklch 0.769 0.188 70.08）、success 定在 emerald-600（oklch 0.596 0.145 163.225）过亮，fe-task07 keepList 保留 amber/emerald 状态色时直接使用 `text-warning`/`bg-warning text-white`/`text-success` 导致对比度回归（legacy amber-600 文字 ≈4.6:1 尚可，token 化后跌至 2.15:1）。

---

## 补偿措施验证（WCAG 1.4.1 非纯颜色）

| 收敛项 | 色相删除后补偿 | 验证 |
|--------|--------------|------|
| 社区分版 4 色 | 分版名文字 label（英语/数学/编程/综合）— `community-meta.ts:22-25` colorClass 全 `bg-primary-soft text-primary` | ✅ 文字标签存在，不依赖颜色 |
| 稀有度 4 色 | 稀有度文字 label（普通/稀有/史诗/传说）— `BadgeWall.tsx:22-26,113-114` | ✅ 文字标签存在 |
| 学科封面 5 色 | 课程名文字 + 学科标签 — CourseCard/MyCourseCard 统一 `from-primary-deep to-primary` | ✅ 课程名不依赖色 |
| 来源类型 3 色 | TypeBadge 文字（课节/题目/资料）— `SourceCardList.tsx:32-36,45-58` | ✅ 文字标签存在 |
| 点赞/收藏激活双色 | Heart vs Bookmark 图标 + `fill-current` 填充态 + `aria-pressed`（ReactButtons.tsx:75,97,79,100） | ✅ 图标+aria 双通道 |
| 排行榜名次多色 | 名次数字 badge + 奖牌图标（RankingTabs/RankList） | ✅ 数字为主通道 |
| 价格 amber/rose | `text-foreground font-bold` + 原价 `line-through`（courses/[seriesId]/page.tsx） | ✅ 字重+删除线结构 |
| 系统消息 amber 底 | `bg-muted` 底色深浅 + 消息对齐 + 系统标签（ChatMessageBubble.tsx:259-260） | ✅ 结构补偿 |
| StatStrip sky/rose | 图标 + 文字标签 + 计数数字（my-courses/page.tsx:60-65） | ✅ |
| 积分/打卡分类色 | KIND_LABEL/CAT_LABELS 文字（PointCard.tsx:36-41 / BadgeWallGrid.tsx:77-83） | ✅ |

**1.4.1 判定：PASS**（所有色相删除处均有文字/图标/结构补偿，无纯颜色传达）。

---

## 保留项确认（keepList 不误收敛）

| 保留项 | 位置 | 未误收敛 | 对比度 |
|--------|------|---------|--------|
| 星级 amber（§2.3 豁免） | ReviewList.tsx:99,168 fill-warning | ✅ 保留 | ❌ 2.15:1 <3（B5） |
| 均分数字 | ReviewList.tsx:86 text-warning | ✅ 保留 | ❌ 2.15:1 <4.5（B3） |
| 奖牌第一名 | RankingTabs.tsx:44 / RankList.tsx:52 text-warning | ✅ 保留（orange 已删、2/3 名 muted-foreground） | ❌ 2.15:1 <3（H5，数字补偿在） |
| 置顶 amber | PostCard.tsx:28,36 `border-warning/40 bg-warning/10` + `text-warning-foreground` | ✅ 保留且 token 化 | ✅ 4.71:1 |
| 未读 badge | ChatFloatingButton.tsx:106 bg-warning | ✅ 保留 | ❌ 2.13:1（B2） |
| 在线点 emerald | ChatMessageBubble.tsx:199 bg-success | ✅ 保留 | ✅ 3.67 ≥3 |
| 回帖奖励 emerald | CommentSection.tsx:127 text-success | ✅ 保留 | ❌ 3.65 <4.5（H1） |
| 完成率三色 | courses/[seriesId]/page.tsx:433 success/warning/destructive | ✅ 保留 | success/warning 档位不足（H1/B 系） |

**结论：保留项未被误收敛（✓），但保留项直接继承 warning/success token 导致对比度不达标（✗）** —— 保留语义正确，色值档位需下调（warning→warning-foreground / success 小字→success-foreground）。

---

## 键盘 / 焦点 / ARIA 回归（本 task 零行为改动，确认零回归）

- **代码静态**：ReactButtons `aria-pressed`（75/97）、`disabled={busy}`；SourceCardList `role="list"`/`role="listitem"`/`aria-label`；RankingTabs APG Tabs（role=tablist/tab + roving tabindex + 方向键）；ChatFloatingButton `aria-expanded`/`aria-label` —— 全部保留，收敛只改 className。
- **Tab 实测**：焦点顺序与 DOM 一致（品牌 → 侧边栏 7 项 → 退出登录 → 顶部问 AI → 头像 → 个人中心/调整偏好 → 内容快捷卡片），18 步无键盘死区、无焦点丢失；全部元素 `:focus-visible` 命中。
- **焦点环实测**：侧边栏导航焦点环为 Tailwind ring（indigo-500 实色 box-shadow），ring vs white 4.58:1 ≥3:1 ✓；快捷卡片/顶部按钮均有可见 ring/outline。
- **console**：本次会话 5 页加载 0 error / 0 warning（server-info 同确认）；MCP 历史日志中的 Next dev HMR WebSocket 失败与 `/_next/static/chunks` 403 为**开发环境噪音**（dev server 重启后旧 chunk 失效），与应用代码及本 task 收敛无关。
- **prefers-reduced-motion**：globals.css:136-144 全局 `@media (prefers-reduced-motion: reduce)` 覆盖所有动画/过渡 ✓；StreakBadge/骨架/Badge 等 animate-* 均被门控。
- **触控目标（2.5.8）**：抽查全部交互目标 ≥24px（nav 231×40、问 AI 69×28、头像 67×36、个人中心 107×36、快捷卡片 227×121、悬浮助手 56×56）✓。

---

## 结论

**FAIL —— 存在 5 项 BLOCKER。**

fe-task07 的收敛方向与补偿设计正确（1.4.1 全部满足、主色/渐变/中性系对比度达标、courses 页零违规、键盘/焦点/aria 零回归），但 **keepList 保留的 amber/emerald 状态色在 token 档位（amber-500 / emerald-600）上对比度系统性不足**，属于收敛落盘时引入的 a11y 回归（legacy amber-600 文字 4.6:1 → token 化后 2.15:1）。核心修复为：**warning 系白字/文字改用 `warning-foreground`（amber-700）档，success 系小字改用 `success-foreground`（emerald-700）档**，可在不改语义、不破坏封闭色板的前提下全部达标；深层问题是 design-tokens 中 warning/success 主档位过亮，建议 token 层下调（如 warning→oklch 0.65 档、success→oklch 0.51 档），一次解决全站同类问题。

**阻塞项（与 BLOCKER 一一对应）**：
1. StreakBadge.tsx:41-44 打卡数徽章 `bg-warning text-white` 2.13:1
2. ChatFloatingButton.tsx:106 未读 badge `bg-warning text-white` 2.13:1
3. ReviewList.tsx:86-88 均分数字 `text-warning` 2.15:1
4. StreakBadge.tsx:89 partial 格 `bg-warning text-white` 2.13:1
5. ReviewList.tsx:99,168 星级 `fill-warning` 2.15:1（<3:1 非文本）
