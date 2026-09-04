调研完成。所有前置资料已核实：`frontend-stack.json`（架构）、`edu-data-refactor-plan.md`（重构规划 v2.0）、`edu.sql`（66 表权威 DDL）、`design-tokens.json`（令牌契约层）、PRD、现有 19 个 ui 组件与 23 个页面现状。以下为最终报告（纯文本输出，未修改任何文件）。

---

# EduAgent 前端重构设计规范报告 v1.0

> **角色**：doc-frontend（前端设计规范师）｜**产出**：供 fe-architect / fe-design-director / fe-spec-writer / fe-implementer / fe-styler 直接执行的重构规范
> **数据权威**：`E:\stu\project\stu\edu-data\sql\edu.sql`（66 表）｜**重构规划**：`.opencode/plans/edu-data-refactor-plan.md` v2.0｜**PRD**：`EduAgent_PRD_完整落地版.md` v1.0
> **模式**：只读调研完成，未修改任何文件

## ⭐ 风格定调冻结（Style Direction Gate，2026-08-19 定稿）

> **风格名**：`candy-playful`（学中玩糖果色）
> **来源**：用户指定 Duolingo 系"学中玩"风格（task44 /courses HTML 审核中用户引导出糖果色）→ 已签收 APPROVED
> **状态**：**FROZEN（已冻结）**——后续所有页面统一此风格，不再重复问风格；页面级返工只在该风格约束内进行；换风格=走 §6.1b 重新定调（视为风格大改）

**冻结内容**：
1. **配色**：candy 糖果色板（orange/green/purple/yellow/blue/pink/red），已在 `globals.css` @theme 注册 25 处 + `design-tokens.json` 同步（用户指定 Duolingo 系）
2. **封面**：糖果渐变封面 + 白字标题 + emoji 装饰（CourseCard 实现）
3. **版式**：rounded-3xl 圆角、间距 scale、图文卡片
4. **标记**：效果图 HTML 头注释 `<!-- STYLE: candy-playful frozen -->`

**引用**：Tgent skill §6.1b（风格定调 gate）+ §6.5（强制要求）。HTML 审核流：每页先产 test-reports/fe-html/{page}.html → 用户审核 → 返工 → APPROVED → 写 React。

## 〇、前置校验与依据

| 输入 | 路径 | 状态 |
|---|---|---|
| 架构文件 | `edu-frontend/frontend-stack.json` + `edu-agent` 后端实际 | ✅ 存在 |
| 重构规划（ARCH） | `.opencode/plans/edu-data-refactor-plan.md`（v2.0，含 RAG 上传） | ✅ 存在 |
| 数据模型权威 | `E:\stu\project\stu\edu-data\sql\edu.sql`（66 表 DDL 已读） | ✅ 存在 |
| 令牌契约层 | `.claude/specs/frontend/tokens/design-tokens.json`（436 行已读） | ✅ 存在 |
| PRD | `EduAgent_PRD_完整落地版.md` | ✅ 存在 |
| 前端 CLAUDE.md | `edu-frontend/CLAUDE.md` → 仅 `@AGENTS.md`（Next.js 16 破坏性变更提示） | ⚠️ 无前端章节 |

> **NOTE**：`edu-frontend/CLAUDE.md` 无前端技术栈章节（仅引用 AGENTS.md 的 Next.js 16 破坏性变更警告），技术栈以 `frontend-stack.json` 为准。与根目录 CLAUDE.md（PromptForge 项目）无交集，不适用。
> **CONFLICT 声明**：本报告与 `frontend-stack.json` 无冲突项；`design-tokens.json` 的 `chart-1..5` 保持中性灰并声明"图表场景另议"，本次给出 echarts 推荐色板（§1.7），属补全而非改写。

### 0.1 技术栈确认行（供 fe-architect 对照 `techStackConfirmLine`）

```
Next.js 16.3 + React 19.2 + Tailwind v4（CSS-first @theme inline）+ shadcn/ui（Base UI）+ Zustand 5 + TanStack Query 5 + axios + echarts + App Router（(user)/(admin) 路由组）
```

### 0.2 重构全局红线（所有 fe-* 必须遵守，违规即打回）

1. **字段统一 snake_case**（edu.sql 列名权威）：前端类型定义只写 `series_name / cohort_name / sale_price / order_status`，**删除全部别名兜底**（`curriculum.ts:184` 的 `series_name ?? series_title` 双轨、`fallbackPrice/fallbackRating/fallbackStudents` 假数据兜底、`getSeriesTreeFlat` 别名归一全部删除）。
2. **响应壳统一**：成功 `{code:0, message:"ok", data}`；失败 `{code:<字符串错误码>, message, data:null}`。`api-client.ts` 响应拦截器**新增成功态解包**（code===0 → 返回 `data`；非 0 → reject ApiError 携带 message）。code 类型放宽 `string | number`（`ApiError.code`）。
3. **禁止 MOCK 兜底**：页面数据一律来自后端；dashboard 15 处 MOCK 替换为真实 API（FR-11）；禁止在组件内造假评分/价格/人数。
4. **写操作失败必须 toast + console.error**；禁止 `catch` 返回空态吞错（frontend-stack forbidden-5）。
5. **tokens 单源**：新页面禁止另起色板、禁止 arbitrary 色值（`bg-[#...]`）、禁止 arbitrary 字号（`text-[13px]`）、禁止分功能多色（sky/violet/cyan 越界）。颜色一律 shadcn 语义 class。
6. **单主色**：indigo（primary 系）+ slate（中性）+ emerald/amber/rose（仅状态场景）。light-only，`dark:*` 永不生效。
7. **'use client' 边界**：交互组件必须 `"use client"`；Server Component 禁内联事件。
8. **管理端 RBAC 仅 admin**：`ADMIN_ALLOWED_ROLES = ["admin"]`；菜单 `filterAdminNav`；页面守卫 `AdminGuard`。
9. **queryKey 约定**：`["module","entity","scope"]`（无分区前缀）。
10. **Next.js 16 破坏性变更**：写代码前先读 `edu-frontend/node_modules/next/dist/docs/` 对应章节（AGENTS.md 要求）；`useSearchParams` 必须包 Suspense；未启用 `cacheComponents` 时禁止 `use cache/cacheLife/cacheTag`；Middleware 已更名 `proxy.ts`。
11. **HTML 原型审核流**：每页先产出 `test-reports/fe-html/{page}.html` 通过用户审核，再写 React（§五）。

---

## 一、设计令牌（Design Tokens）

> 契约层：`.claude/specs/frontend/tokens/design-tokens.json` ↔ 运行层 `src/app/globals.css`（双源一一对应，任何变更双写 + grep 一致性核对）。下方 **oklch 为权威值（globals.css 实际生效）**，hex 为 Tailwind v4 官方色板对照（paletteName 已锁定色板，供 HTML 效果图与评审换算用）。

### 1.1 色彩体系

**① 主色（品牌，indigo 系）**——按钮/链接/激活态/渐变

| Token | oklch（权威） | hex | Tailwind 名 | 用途 | class |
|---|---|---|---|---|---|
| `--primary` | oklch(0.511 0.262 276.966) | `#4F46E5` | indigo-600 | 主按钮底、主链接、激活单色 | `bg-primary text-primary border-primary` |
| `--primary-foreground` | oklch(0.985 0 0) | `#FFFFFF` | white | 主按钮文字 | `text-primary-foreground` |
| `--primary-strong` | oklch(0.457 0.24 277.023) | `#4338CA` | indigo-700 | hover 加深、渐变浅端、强调文字 | `text-primary-strong to-primary-strong` |
| `--primary-deep` | oklch(0.279 0.041 260.031) | `#1E293B` | slate-800 | 品牌渐变深端 | `from-primary-deep` |
| `--primary-soft` | oklch(0.962 0.018 272.314) | `#EEF2FF` | indigo-50 | 浅色强调底（标签/计数徽章/激活行） | `bg-primary-soft` |
| `--primary-soft-foreground` | oklch(0.457 0.24 277.023) | `#4338CA` | indigo-700 | 浅底文字 | `text-primary-soft-foreground` |
| `--primary-border` | oklch(0.882 0.059 272.879) | `#C7D2FE` | indigo-200 | 主色边框/hover 边框 | `border-primary-border` |
| `--ring` | oklch(0.585 0.233 277.117) | `#6366F1` | indigo-500 | 焦点环 | `ring-ring focus-visible:ring-ring` |

**② 中性（slate 系）**——文本/底/边框/侧边栏

| Token | oklch（权威） | hex | 用途 | class |
|---|---|---|---|---|
| `--background` `--card` `--popover` `--sidebar` | oklch(1 0 0) | `#FFFFFF` | 页面/卡片/弹层/侧边栏底 | `bg-background bg-card bg-popover bg-sidebar` |
| `--foreground` `--card-foreground` `--popover-foreground` `--sidebar-foreground` | oklch(0.208 0.042 265.755) | `#0F172A` | slate-900 标题/正文 | `text-foreground` |
| `--secondary` `--muted` `--accent` `--sidebar-accent` | oklch(0.968 0.007 247.896) | `#F1F5F9` | slate-100 次级按钮底/弱化底/hover 底 | `bg-secondary bg-muted bg-accent hover:bg-muted` |
| `--secondary-foreground` `--accent-foreground` `--sidebar-accent-foreground` | oklch(0.279 0.041 260.031) | `#1E293B` | slate-800 次级按钮文字/导航文字 | `text-secondary-foreground` |
| `--muted-foreground` | oklch(0.554 0.046 257.417) | `#64748B` | slate-500 次级文字/提示/placeholder | `text-muted-foreground` |
| `--border` `--input` `--sidebar-border` | oklch(0.929 0.013 255.508) | `#E2E8F0` | slate-200 边框/输入框边框/分隔线 | `border-border border-input border-sidebar-border` |
| `--sidebar-primary(-foreground)` | 同 `--primary`/white | `#4F46E5`/`#FFF` | 侧边栏激活主色 | `bg-sidebar-primary` |

**③ 语义状态色**——**仅状态场景**（成功/警告/危险），不做功能区分

| Token | oklch（权威） | hex | 场景 | class 规范 |
|---|---|---|---|---|
| `--success` | oklch(0.596 0.145 163.225) | `#059669` | emerald-600 已完成/已支付/已报名 | `text-success`（深底）或 `bg-success/10 text-success`（浅底徽章） |
| `--success-foreground` | oklch(0.508 0.118 165.612) | `#047857` | emerald-700 浅底成功文字 | `text-success-foreground` |
| `--warning` | oklch(0.769 0.188 70.08) | `#F59E0B` | amber-500 待处理/即将到期/部分退款 | `text-warning` / `bg-warning/10 border-warning/40` |
| `--warning-foreground` | oklch(0.555 0.163 48.998) | `#B45309` | amber-700 浅底警告文字 | `text-warning-foreground` |
| `--destructive` | oklch(0.586 0.253 17.585) | `#E11D48` | rose-600 失败/取消/拒绝/删除 | `text-destructive bg-destructive` |
| `--destructive-foreground` | oklch(0.514 0.222 16.935) | `#BE123C` | rose-700 浅底危险文字 | `text-destructive-foreground` |

**④ 渐变（3 个 token 位置，业务组件禁自造）**

| Token | stops | class | 位置 |
|---|---|---|---|
| `gradient-brand` | `from-primary-deep to-primary-strong`（slate-800→indigo-700） | `bg-gradient-to-br from-primary-deep to-primary-strong` | AppShell 品牌区图标底 |
| `gradient-nav-active` | 同上（横向） | `bg-gradient-to-r from-primary-deep to-primary-strong text-white` | 侧边栏导航激活态 |
| `gradient-avatar` | `from-primary-deep to-primary` | `bg-gradient-to-br from-primary-deep to-primary` | 头像/图标底 |

**⑤ 图表色板（echarts，chart-1..5 中性灰仅作 fallback）**——dashboard/管理端图表专用，**8 色定性序**

```
推荐：indigo-600 #4F46E5 · emerald-500 #10B981 · amber-500 #F59E0B · rose-500 #F43F5E
     sky-500 #0EA5E9（图表仅允许）· violet-500 #8B5CF6 · slate-500 #64748B · indigo-300 #A5B4FC
规则：单系列线/柱用 primary 系；多系列按上序取前 N；饼图禁用相邻色
实现：src/lib/chart-palette.ts（已存在，改造为上述色板；echarts color 数组注入）
```

**⑥ 使用红线（grep 审计依据）**：合法色集 = 上表全部 + `white`；**非法** = `sky/violet/cyan/teal/fuchsia` 用于业务组件、`bg-[#...]`、`text-[13px]` 等 arbitrary、`style={{color:...}}` 内联色。科目图标色（英语 sky/编程 violet 等）**从 curriculum.ts 的 SUBJECT_OPTIONS 迁移为语义灰**：统一 `bg-muted text-muted-foreground`，学科用文字/首字母区分，不再用彩色圆点（在线教育清爽风格 + 单主色红线）。

### 1.2 字体阶梯（字号 / 字重 / 行高）

> 字体族：`--font-sans: Geist Sans + 系统栈 + 微软雅黑`；`--font-mono: Geist Mono`；金额/数字用 `tabular-nums`。

| 层级 | 字号 token / px | 字重 | 行高 | 场景 |
|---|---|---|---|---|
| 页面主标题 h1 | `text-3xl` 30px | 700 | 36px | 课程详情头部、订单详情头部 |
| 区块标题 h2 | `text-2xl` 24px | 600 | 32px | 页面区块（我的班次/优惠券列表标题） |
| 卡片标题 h3 | `text-lg` 18px | 600 | 28px | 卡片/弹窗标题、课程卡片标题 |
| 列表主文案 | `text-base` 16px | 500 | 24px | 列表项名称、菜单 |
| 正文 | `text-sm` 14px | 400 | 20px | 默认正文、描述 |
| 表格/表单正文 | `text-sm-table` 13px | 400 | 20px | 表格单元格、表单 label、辅助说明 |
| 次级元信息 | `text-2xs` 12px | 400 | 16px | 标签、hint、错误小字、时间 |
| 元信息/版权 | `text-3xs` 11px | 400 | 16px | 版权、角标、footer |
| 极小编号 | `text-4xs` 10px | 400 | — | 仅装饰性计数角标（a11y 边界，fe-a11y 审查项） |
| 价格强调 | `text-2xl`~`text-4xl` + `font-bold` | 700 | 与行级一致 | 价格数字，`tabular-nums`，前缀 ¥ |

**禁止**：`text-[13px]` 等 arbitrary 字号（存量按 `design-tokens.json sizeMapping` 收编）；正文层级不得低于 12px（10/11px 仅元信息/装饰）。

### 1.3 间距系统

| 档位 | px | 用途 |
|---|---|---|
| 4px（unit） | 4 | 图标与文字间隙、badge 内边距 |
| 8px | 8 | 紧凑分组内距、表格单元格 padding |
| 12px | 12 | 表单控件间距 |
| 16px | 16 | 区块内距、卡片 padding 基准（`p-4`） |
| 24px | 24 | 页面留白（`md:p-6`）、卡片间 gap |
| 32px | 32 | 大区块分隔 |

- 页面：`p-4 md:p-6`（AppShell `contentClassName`，管理端传、用户端按页）。
- 区块：`space-y-4/6`；卡片网格 `grid gap-4 md:gap-6`；列表行 `gap-3`。
- 表格行高：`h-12`（48px 触控达标）；表格容器 `rounded-xl border border-border shadow-card`。

### 1.4 圆角

| token | px | 场景 |
|---|---|---|
| `rounded-sm` | 6 | 小控件角 |
| `rounded-md` | 8 | 输入框、按钮（常用 `rounded-lg`） |
| `rounded-lg` | 10 | 表单控件、小卡片 |
| `rounded-xl` | **14（全站卡片基准）** | 卡片、表格容器、侧边栏、弹窗 |
| `rounded-2xl` | 18 | 大卡片、缩略图容器 |
| `rounded-3xl` | 22 | 课程封面图 |
| `rounded-4xl` | 26 | pill 徽章（badge 已用） |

### 1.5 阴影

| token | 值 | 场景 |
|---|---|---|
| `shadow-card` | `0 1px 2px 0 rgb(0 0 0 / 0.05)` | 卡片/表格默认阴影（替代 shadow-sm） |
| `shadow-drawer` | `0 25px 50px -12px rgb(0 0 0 / 0.25)` | 移动端抽屉开启阴影 |
| 悬停提升 | `hover:border-primary-border` + 保持 shadow-card | 卡片 hover 边框着色，**不新增阴影 token** |

### 1.6 断点

| 断点 | 值 | 行为 |
|---|---|---|
| 默认 | <640 | 单列、抽屉式侧边栏 |
| sm | 640 | 表单两列开始 |
| md | **768（抽屉断点临界）** | ≥768 固定侧边栏；卡片网格 2 列 |
| lg | 1024 | 课程列表 3 列、详情双栏 |
| xl | 1280 | 管理端表格宽布局 |
| 2xl | 1440 | 内容容器 max-w 上限 |

视口验收集合：**375 / 768（双态各截）/ 1024 / 1280 / 1440**。

### 1.7 design-tokens 源指针

```
.claude/specs/frontend/tokens/design-tokens.json   ← 已存在（fe-task00 创建，fe-* 全链只读引用，本重构沿用）
```

---

## 二、页面规范（9 新 + 13 重构 = 22 页）

> 通用规则：每页 = 布局 ASCII 草图 + 组件清单 + 交互说明 + 状态流转 + 数据依赖。守卫统一：用户端业务页 `ProtectedRoute`（SSR 占位），管理端 `AdminGuard`。数据获取：React Query `useQuery`，queryKey 见各页；写操作 `useMutation` + `onError` toast + `onSuccess` `invalidateQueries`。金额展示统一 `formatAmount(n)`（¥ 千分位，来自 `src/lib/utils`，新增）。枚举文案统一 `statusText(map)`，与 StatusBadge 共用映射表（§三 3.3）。

### P1 `/coupons` 优惠券中心（新）

```
┌────────────────────────────────────────────┐
│ [我的优惠券]                        [可用] [已用] [已过期]   ← Tabs(已有) + 数量徽章
├────────────────────────────────────────────┤
│ ┌─ CouponCard ──────────┐  ┌─ CouponCard ──┐
│ │ ¥50  满500可用         │  │ 8折 满1000可用 │
│ │ [满减券] 编程系列      │  │ [折扣券] 数学系 │
│ │ 有效期至 08-31  [去使用]│  │ 已领取          │
│ └───────────────────────┘  └───────────────┘
│ （已用/已过期 tab：卡片变灰 + 状态徽章，无 CTA）
├────────────────────────────────────────────┤
│ [可领取的券]  （P1 区块，Grid 3 列 lg）       │
│ ┌──────────────────────┐                    │
│ │ ¥30 满200可用  [立即领取]                 │
│ │ 领取进度 120/500  ▓▓▓░░ 剩余 380          │
│ └──────────────────────┘                    │
├────────────────────────────────────────────┤
│ 空态（无券）：EmptyState「暂无可用的优惠券」   │
└────────────────────────────────────────────┘
```

- **组件清单**：Tabs（已用）、StatusBadge、CouponCard（新）、EmptyState（新）、Skeleton（加载）、ErrorState（新）
- **交互**：领取按钮 → `useMutation` → 成功 toast「领取成功」+ 卡片移入"可用"tab + 进度刷新；超量/过期 → toast 错误 + 按钮 disabled；「去使用」→ 跳 `/?coupon_id=`（无携带场景则跳课程中心）；倒计时（距过期 <48h）用 `text-warning` 渲染。
- **状态流转**：券模板 `coupon.coupon_type ∈ {cash,discount,trial,gift}`（cash 显示 ¥{discount_amount}；discount 显示 {discount_rate*10} 折）；领取记录 `coupon_receive_record.receive_status ∈ {unused,used,expired}`。
- **数据依赖**：`GET /api/coupons`（可领列表）、`GET /api/coupons/me`（我的券）、`POST /api/coupons/{coupon_id}/receive`。queryKey：`["coupons","me","{tab}"]`、`["coupons","available"]`。

### P2 `/orders` 我的订单（新）

```
┌──────────────────────────────────────────────┐
│ [我的订单]   [全部][待付款][已支付][已完成][已退款]  ← Tabs + 计数
├──────────────────────────────────────────────┤
│ OrderRow（Card 列表）                          │
│ ┌──────────────────────────────────────────┐ │
│ │ 订单号 20260816123456    [待付款][badge]  │ │
│ │ ┌封面┐ 通用编程入门班·暑期一班（班次）      │ │
│ │ │img│ ¥399 ×1   共1件  实付 ¥399          │ │
│ │ └───┘ 2026-08-16 下单        [去支付][详情]│ │
│ └──────────────────────────────────────────┘ │
├──────────────────────────────────────────────┤
│ Pagination + 空态「暂无订单」[去选课]          │
└──────────────────────────────────────────────┘
```

- **组件清单**：Tabs、DataTable（或列表 Card 布局，推荐 Card 列表）、StatusBadge、Pagination（新）、EmptyState、OrderCard（新，含 order_item 缩略）
- **交互**：tab 切换重查；「去支付」（待付款）→ 跳 `P3`；「详情」→ 展开子面板展示 order_items 明细 + 支付记录 + 退款入口；「申请退款」→ 跳 `P4` 带 `order_item_id`；「评价/进学习」→ 已完成态跳学习页/课程详情。
- **状态流转（订单状态机，权威枚举）**：

```
order.order_status:
  pending ──支付成功──► paid ──自动报名完成──► completed
    │                                          ▲
    │ 超时/取消                                 │ 部分退款
    ▼                                          │
  cancelled            partial_refunded ◄──────┤
                          │ 全额退款            │
                          ▼                    ▼
                       refunded ◄──────────────┘
徽章映射: pending→warning「待付款」| paid→success「已支付」| completed→muted「已完成」
          cancelled→muted「已取消」| partial_refunded→warning「部分退款」| refunded→destructive「已退款」
```

- **数据依赖**：`GET /api/orders?order_status=&page=`（返回 order + items + payments 嵌套）、`POST /api/orders/{id}/cancel`（待付款取消）。queryKey `["orders","list","{status}","{page}"]`。

### P3 `/orders/[orderId]/pay` 支付页（新）

```
┌──────────────────────────────────────────────┐
│ 收银台                                       │
│ ┌──────────────────────────────────────────┐ │
│ │ 订单号 20260816123456     应付金额         │ │
│ │ 通用编程入门班·暑期一班     ¥399.00        │ │
│ │ 优惠券 -¥50 [满500可用·已自动抵扣]          │ │
│ └──────────────────────────────────────────┘ │
│ 支付方式（RadioGroup）                        │
│ (•) 模拟支付（开发/演示环境）                  │
│ ( ) 微信支付  ( ) 支付宝  ( ) 线下转账（待审核）│
│ [立即支付 ¥349]      [取消订单]              │
│ ┌ 支付结果态（3 状态切换演示）────────────────┐ │
│ │ ⏳ 处理中（轮询 payment_status ≤15s）      │ │
│ │ ✅ 支付成功 → 5s 倒计时跳转 /orders         │ │
│ │ ❌ 支付失败 → 重试按钮（保留原单）           │ │
│ └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

- **组件清单**：Stepper（新：确认订单→支付→完成）、RadioGroup、PriceText（新）、Button（loading 态）、Alert（错误条）、Countdown（成功跳转，用定时器实现）
- **交互**：进入页面 `GET /api/orders/{id}` 校验状态（非 pending → 提示并跳订单列表）；选支付方式（默认模拟支付）；点「立即支付」→ `POST /api/payments` 创建支付记录 → **轮询** `GET /api/payments/{payment_no}`（2s 间隔，`refetchInterval`，≤15s 或 status 终态停）；成功后 `GET /api/orders/{id}` 确认 → **5s 倒计时跳转 /orders**（可点立即查看）；失败显示错误 + 重试；「取消订单」→ ConfirmDialog → 跳 /orders。**防重复提交**：提交按钮 loading + `disabled`，禁止双击生成双单。
- **支付状态机**：`payment_record.payment_status ∈ {pending, paid, failed, closed, partial_refunded, refunded}`；**支付渠道** `{wechat_pay, alipay, bank_card, offline_transfer, public_account, campus_cashier}`——线下转账选择后显示「到账审核中」提示而非即时回调；模拟支付回调走 `/payment-notifications/mock`（后端已规划，不真实对接）。
- **报名联动**：支付成功回调后 `student_cohort_rel.enroll_status` 置 `active`（后端动作），前端在支付成功页展示「报名成功，前往学习」CTA → `/my-courses`。
- **数据依赖**：`GET /api/orders/{id}`、`POST /api/payments`、`GET /api/payments/{payment_no}`、`POST /api/orders/{id}/cancel`。queryKey `["orders","detail","{id}"]`。

### P4 `/refunds` 退款记录（新）

```
┌──────────────────────────────────────────────┐
│ [退款记录]                                    │
│ ┌──────────────────────────────────────────┐ │
│ │ 退款单 20260816170001    [审核中][warning] │ │
│ │ 班次：通用编程入门班·暑期一班               │ │
│ │ 原因：课程不满意     金额：¥399.00         │ │
│ │ 申请 08-16 → 审核 08-17 → 到账 08-18      │ │ ← Timeline
│ │ 订单轨迹: 待付款→已支付→申请退款→已退款     │ │
│ │                        [查看订单] [撤销申请]│ │
│ └──────────────────────────────────────────┘ │
│ 发起退款入口（右上角）[申请退款] → Dialog 表单  │
│   - 选择订单/班次（下拉，仅 paid/completed 单）│
│   - 原因 refund_type 单选 + 说明 textarea      │
│   - 金额（默认全额，可改≤payable）             │
└──────────────────────────────────────────────┘
```

- **组件清单**：Timeline（新）、StatusBadge、Dialog + Form（已有）、Select（新，shadcn select）、EmptyState、RefundCard（新）
- **交互**：列表 `GET /api/refunds`（倒序）；「申请退款」→ Dialog：先选可退订单（`GET /api/orders?refundable=true`）→ 选班次 item → 选原因 → 提交 `POST /api/refunds` → 成功后列表刷新 + toast；「撤销申请」（仅 pending）→ ConfirmDialog → `POST /api/refunds/{id}/cancel`；「查看订单」→ `/orders`；已拒绝态显示拒绝理由（approver remark）。
- **状态流转**：`refund_request.refund_status ∈ {pending, approved, rejected, refunded}` → 徽章 warning「审核中」/ success「已通过，退款中」/ destructive「已拒绝」/ success「已退款」。`refund_type ∈ {personal_reason, course_unsatisfied, schedule_conflict, duplicate_purchase}` → 文案映射「个人原因/课程不满意/时间冲突/重复购买」。
- **数据依赖**：`GET /api/refunds`、`POST /api/refunds`、`POST /api/refunds/{id}/cancel`。queryKey `["refunds","list"]`。

### P5 `/tickets` 售后工单 + 人工申诉（新）

```
┌──────────────────────────────────────────────┐
│ [售后工单]                    [+ 新建工单]     │
│ Tabs: 全部 / 处理中 / 已关闭   （含申诉类型）   │
│ ┌──────────────────────────────────────────┐ │
│ │ TK20260816001 [售后][高][处理中][badge]    │ │
│ │ 班次：通用编程入门班·暑期一班               │ │
│ │ 最后跟进：客服 08-16 14:30 已回复          │ │
│ │ ▸ 展开：跟时间线（Timeline）               │ │
│ │   用户发起 → 客服回复 → 状态更新 → 关闭    │ │
│ │                        [回复工单] [满意度] │ │
│ └──────────────────────────────────────────┘ │
│ 新建工单 Dialog：                             │
│   类型：[售后][申诉][退款] + 班次选择          │
│   标题 + 内容（textareas）→ 提交 POST         │
└──────────────────────────────────────────────┘
```

- **组件清单**：Tabs、Timeline、StatusBadge、Dialog + Form、EmptyState、TicketCard（新）、Badge（优先级）、Textarea
- **交互**：列表 `GET /api/tickets?ticket_type=&ticket_status=`；新建 Dialog（类型含 **appeal 人工申诉**，前端文案「人工申诉」）；展开工单 → 加载跟进记录 `GET /api/tickets/{id}/follows` 渲染 Timeline；「回复工单」→ Dialog 输入 → `POST /api/tickets/{id}/follows`（follow_type=reply_user）；关闭的工单可评满意度（score 1-5 星 + 评语）→ `POST /api/tickets/{id}/survey`；优先级徽章：urgent→destructive「紧急」/ high→warning「高」/ medium→muted「中」/ low→muted「低」。
- **状态流转**：`service_ticket.ticket_status ∈ {pending, in_progress, closed}` → 「待受理」warning /「处理中」primary /「已关闭」muted；`ticket_type ∈ {after_sales, complaint, refund, appeal}` → 售后/投诉/退款/申诉（appeal 为本次新增）。**用户端只读自己的工单**（user_id 隔离）；响应时间参考：`first_response_at` 为空显示「等待受理」。
- **数据依赖**：`GET /api/tickets`、`POST /api/tickets`、`GET /api/tickets/{id}/follows`、`POST /api/tickets/{id}/follows`、`POST /api/tickets/{id}/survey`。queryKey `["tickets","list","{tab}"]`、`["tickets","detail","{id}","follows"]`。

### P6 `/favorites` 我的收藏（新）

```
┌──────────────────────────────────────────────┐
│ [我的收藏]                   共 N 门课程       │
│ Grid（lg:3 列）CourseCard（复用课程中心卡片）   │
│ ┌──────────────────────┐                    │
│ │ 封面图（16:9 圆角3xl）│                    │
│ │ 通用编程入门班         │                    │
│ │ 编程 · L1 · 在线直播   │  ♥ 已收藏(填充)     │
│ │ 12 班次 · 4.8 分       │                    │
│ │ [查看详情]            │                    │
│ └──────────────────────┘                    │
│ 空态：「暂无收藏」[去逛逛]→ /courses          │
└──────────────────────────────────────────────┘
```

- **组件清单**：CourseCard（重构复用）、EmptyState、Skeleton、Badge（delivery_mode/级别）
- **交互**：列表 `GET /api/favorites`（服务端收藏，非本地）；心形按钮 hover 显示「取消收藏」，点击 → ConfirmDialog → `DELETE /api/favorites/{series_id}` → 卡片移出 + toast；点击卡片 → `/courses/[seriesId]`；分页（full 档 10 万用户，收藏可能多页）。
- **收藏来源**：`series_favorite.favorite_source ∈ {series_detail, search_result, recommendation, activity_page}`——课程详情页收藏按钮（P8）写入时携带 `favorite_source=series_detail`。
- **数据依赖**：`GET /api/favorites?page=`、`POST /api/favorites/{series_id}`、`DELETE /api/favorites/{series_id}`。queryKey `["favorites","list","{page}"]`。

### P7 `/courses` 课程中心（重构）

```
┌────────────────────────────────────────────────┐
│ 课程中心  [搜索框（防抖 400ms）]                │
│ 筛选条 FilterBar：                              │
│ 学科: [全部][编程][英语][数学][语文][物理]        │
│ 交付: [全部][在线直播][录播][线下]               │
│ 价格: [不限][0-500][500-1000][1000+]  ← Select  │
│ 排序: [综合][销量][价格↑][价格↓]                 │
├────────────────────────────────────────────────┤
│ Grid lg:3（CourseCard）                         │
│ ┌────────────┐  ┌────────────┐                 │
│ │封面 16:9    │  │封面         │                 │
│ │系列名       │  │系列名       │                 │
│ │编程·L1·直播 │  │数学·L2·录播 │                 │
│ │12班次 ·4.8分│  │8班次 ·4.6分 │                 │
│ │¥399 ¥599   │  │¥299 ¥399   │                 │
│ └────────────┘  └────────────┘                 │
├────────────────────────────────────────────────┤
│ Pagination（page_meta 驱动）                    │
└────────────────────────────────────────────────┘
```

- **组件清单**：FilterBar（新，组合式筛选条）、CourseCard（重构：封面/标题/元信息/价格）、Pagination、EmptyState、Skeleton、SearchInput（防抖）
- **交互**：**筛选变化即重查**（queryKey 含全部筛选参数）；关键词输入 **防抖 400ms**（复用 `src/lib/hooks/use-debounced-value.ts`）；排序切换重查；价格区间 Select；卡片 hover `border-primary-border` + 阴影微升；**删除 MOCK 兜底**（fallbackPrice 等），空字段显示「-」。
- **字段**（snake_case）：`series.institution_id / delivery_mode / series_code / series_name / sale_status ∈ {draft,on_sale,off_sale} / cover_url`；`delivery_mode ∈ {online_live, online_recorded, offline_face_to_face}` → 徽章「在线直播/在线录播/线下面授」。分类经 `series_category_rel → dim_course_category`。仅展示 `sale_status=on_sale`。
- **数据依赖**：`GET /api/series?category=&delivery_mode=&min_price=&max_price=&keyword=&sort=&page=&page_size=`。queryKey `["series","list",{...filters}]`。

### P8 `/courses/[seriesId]` 课程详情（重构，系列→班次→模块→课次四级）

```
┌────────────────────────────────────────────────────┐
│ 面包屑: 课程中心 / 编程 / 通用编程入门班              │
│ ┌─────────────────────────┬──────────────────────┐ │
│ │ 封面 16:9（lg:left 2/3）│ 购买面板（right 1/3） │ │
│ │ 通用编程入门班           │ ┌──────────────────┐ │ │
│ │ 编程·L1·在线直播·8周     │ │ 班次选择（CohortList）│ │
│ │ 面向零基础学习者...       │ │ ○ 暑期一班 ¥399    │ │
│ │ ▓▓▓ 学员 1250 · 4.8分   │ │   (剩余 18/60 席) │ │
│ │ [♥ 收藏] [领券]          │ │ ○ 秋季二班 ¥499    │ │
│ │                         │ │   (已满员 disabled)│ │
│ │ [报名]（选中班次后启用）  │ │ ○ 寒假三班 ¥299    │ │
│ │                         │ └──────────────────┘ │ │
│ │                         │ 优惠券：¥50满500可用   │ │
│ │                         │ [立即报名 ¥399]       │ │
│ └─────────────────────────┴──────────────────────┘ │
│ Tabs: [课程大纲][班次详情][课程评价][思维导图]         │
│ 大纲（四级树）：                                     │
│ ─ 模块一: Python 基础（6课次 · 18学时）   stage 1     │
│    ├─ 课次1 变量与类型（03-01 09:00 已结束）          │
│    ├─ 课次2 流程控制（03-08 09:00 进行中）            │
│    └─ ...                                            │
│ 班次详情: 排期/容量/授课教师/上课地点                 │
└────────────────────────────────────────────────────┘
```

- **组件清单**：Breadcrumb、CourseHero（新）、CohortList（新：RadioGroup 风格班次卡）、CouponPicker（新：可用券下拉，已领取可抵）、FavoriteButton（新：心形，登录态必需）、Tabs、TreeAccordion（新：模块→课次四级展开）、Rate/评价列表、MindMap（复用 echarts 图谱）
- **交互**：进入加载 `GET /api/series/{id}` + `GET /api/series/{id}/cohorts`；**班次选择**：选中启用「立即报名」，价格联动显示；已满员（`current_student_count >= max_student_count`）disabled + 「已满员」；「领券」→ 弹窗展示该系列适用券（`GET /api/coupons?series_id=`）→ 领取 → 弹窗刷新 + 可用券列表更新；「收藏」→ 登录校验 → 切换实心/空心 + toast；「立即报名」→ 登录校验 → `POST /api/orders`（body: cohort_id + coupon_receive_record_id）→ 成功跳 `P3 支付`；未登录 → 跳 `/login?redirect=/courses/[seriesId]`。
- **四级结构**：系列 `series` → 班次 `series_cohort` → 模块 `series_cohort_course`（stage_no 升序）→ 课次 `series_cohort_session`（session_no 升序，teaching_status 徽章：scheduled→muted「未开始」/ in_progress→primary「进行中」/ completed→success「已完成」/ cancelled→destructive「已取消」）。
- **数据依赖**：`GET /api/series/{id}`、`GET /api/series/{id}/cohorts`、`GET /api/cohorts/{id}/modules`（含课次）、`GET /api/coupons?series_id=`、`POST /api/orders`、`POST /api/favorites/{id}`。queryKey `["series","detail","{id}"]`、`["series","cohorts","{id}"]`。

### P9 `/learning/[seriesId]/[sessionId]` 学习页（重构）

```
┌────────────────────────────────────────────────────────┐
│ ← 返回我的班次     通用编程入门班·暑期一班  课次 3/24      │
│ ┌──────────────────────────┬─────────────────────────┐ │
│ │ 视频区（16:9，主区）      │ 右侧大纲（lg 1/4）        │ │
│ │  ├ 播放器/章节跳转        │ 模块树（Accordion）       │ │
│ │  ├ 上一课次 下一课次       │ ▾ 模块一: Python 基础     │ │
│ │  └ 视频进度（15s 打点）    │   ✓ 课次1 变量（已完成）  │ │
│ │                          │   ▶ 课次2 流程（当前）    │ │
│ │ Tabs: [视频][作业][考试]   │   ○ 课次3 函数            │ │
│ │  作业: 题目列表→提交→判分  │                          │ │
│ │  考试: 计时器/交卷         │ 学习进度: ▓▓▓░░ 68%      │ │
│ └──────────────────────────┴─────────────────────────┘ │
│ 底部工具栏: [AI 提问][错题本][复习入口]                    │
└────────────────────────────────────────────────────────┘
```

- **组件清单**：VideoPlayer（复用，接 `session_video` 源）、Progress（已有）、Accordion（新）、QuizPanel（复用，改从 `question` 表出题）、Tabs、Button 组、ErrorState（403 未报名拦截）
- **交互**：路由守卫升级——**仅 enrolled（student_cohort_rel.active）可看 enrolled_only 资源**；视频 15s 打点（复用 `tick-batch`，改写 edu-data 提交表）；章节跳转（`session_video_chapter` 起止秒）；课次切换在右侧大纲点击；作业/考试提交走 `session_homework_submission / session_exam_submission`（**恢复 edu.sql 外键语义**）；「AI 提问」→ `/chat?context=session:{id}`；资源区展示 `session_asset`（material_category: video/handout/exercise/reference/image；access_scope: public/trial/enrolled_only/internal_only——trial 未报名可看、enrolled_only 需报名）。
- **状态流转**：课次完成判定 = 观看 ≥90% 或作业提交；`teaching_status` 徽章同 P8；视频 `transcode_status ∈ {pending,in_progress,completed,failed}` → 未 completed 显示「转码中/不可播」占位。
- **数据依赖**：`GET /api/cohorts/{cohortId}/modules`、`GET /api/study/sessions/{sessionId}`（含 assets/video/chapters）、`POST /api/progress/video/tick-batch`、`POST /api/study/sessions/{id}/homeworks/{hid}/submit`、`/exams/{eid}/submit`。

### P10 `/my-courses` 我的班次（重构为 enrollments）

```
┌──────────────────────────────────────────────────┐
│ [我的班次]  Tabs: [学习中][已完成][已退款]           │
│ Grid lg:2 CohortCard（报名卡片）                   │
│ ┌──────────────────────────────────────────────┐ │
│ │ 通用编程入门班·暑期一班    [学习中][success]   │ │
│ │ 课程进度 ▓▓▓▓▓▓░░░░ 68%（模块 4/6 · 课次16/24）│ │
│ │ 下次课: 模块一·课次3  03-08 09:00             │ │
│ │ [继续学习] [课程详情] [作业/考试] [售后]        │ │
│ └──────────────────────────────────────────────┘ │
│ 已完成: [查看证书/评价][再次报名]                   │
│ 已退款: 灰色 + [查看退款]                          │
│ 空态: 「还没有报名班次」[去选课]→ /courses         │
└──────────────────────────────────────────────────┘
```

- **组件清单**：CohortCard（重构，enrollments 语义）、Progress、StatusBadge、EmptyState、Tabs、Grid
- **交互**：「继续学习」→ 跳最近未完成课次 `/learning/{seriesId}/{sessionId}`；「课程详情」→ `/courses/[seriesId]`（带班次高亮 `?cohort_id=`）；「售后」→ `/tickets?order_item_id=`；进度条点击跳学习页；卡片展示 `student_cohort_rel.enroll_status ∈ {active, completed, cancelled, refunded}`。
- **数据依赖**：`GET /api/enrollments/me/cohorts?status=`（进度聚合 series_cohort_session + 提交表）、`GET /api/progress/courses`（3 层完成率改造为四级）。queryKey `["enrollments","me","{status}"]`。

### P11 `/practice/[mode]` 复习中心（重构）

```
┌──────────────────────────────────────────────────┐
│ [复习中心]                                         │
│ 入口卡 Grid lg:3                                   │
│ ┌───────────┐ ┌───────────┐ ┌───────────┐        │
│ │ 错题本     │ │ 单词本     │ │ 专项练习   │        │
│ │ 23 题待复  │ │ 12 词待回  │ │ 选择模式   │        │
│ │ [开始复习] │ │ [开始回忆] │ │ [去练习]   │        │
│ └───────────┘ └───────────┘ └───────────┘        │
│ 复习题目列表（DataTable）: 题型/知识点/正确率/最近错  │
│ 单选 | 题干 | 最近错误 08-14 | 正确率 67% | [重做]  │
│ 复习会话（进入后全屏 Card）:                        │
│  ▓ 3/23  题干 → 作答 → 即时判分 → 解析（analysis）  │
│  [上一题][下一题][结束复习]（结束=提交结果报告）      │
└──────────────────────────────────────────────────┘
```

- **组件清单**：QuizPanel（复用，**出题源切换 `question` 表**）、DataTable、Progress、StatCard（新：待复习数）、Button
- **交互**：错题本 `GET /api/interactive/quiz/wrong-book`（改造为 edu-data 题目）；复习作答 → 判分 → **展示 analysis_text 解析**（重构核心：题库解析贯通）；SM-2 词卡回忆（复用 vocab，不动）；专项练习按题型/难度过滤（`dim_question_type`）；复习结果上报（可选）。
- **数据依赖**：`GET /api/interactive/quiz/wrong-book?page=`、`GET /api/vocab/daily`、`GET /api/questions?type_id=&difficulty=`。queryKey `["practice","wrong-book"]` 等。

### P12 `/me` 个人中心（重构）

```
┌──────────────────────────────────────────────────┐
│ ┌头像(渐变)┐ 昵称    [编辑资料]                    │
│ │  avatar  │ 学习目标: 编程入门                    │
│ └─────────┘ 偏好: 编程/数学                        │
│ ┌──────────── 数据概览（4 StatCard）─────────────┐ │
│ │ 学习时长 68h │ 完成课次 24 │ 积分 1,280 │ 等级10 │ │
│ └──────────────────────────────────────────────┘ │
│ 功能入口（List，行内图标+箭头）                     │
│   ▸ 我的订单 /orders        ▸ 我的优惠券 /coupons  │
│   ▸ 我的收藏 /favorites     ▸ 我的班次 /my-courses │
│   ▸ 退款记录 /refunds       ▸ 售后工单 /tickets    │
│   ▸ 错题本 /practice/wrong-book                   │
│ ┌ 学员档案表单（student_profile 扩展）────────────┐ │
│ │ 身份/目标/学历/年级/学校/行业/岗位/工作年限       │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

- **组件清单**：Avatar、StatCard、List 行（新：NavListItem）、Dialog + Form、Tabs（基本资料/档案/偏好）
- **交互**：`GET /api/users/me` + `GET /api/users/me/student-profile`（新接口）+ `GET /api/progress/dashboard`（改造后真实数据，**删除 15 处 MOCK**）；编辑资料 `PATCH /api/users/me`；档案表单保存 `PUT /api/users/me/profile`；入口跳转表见 §四。
- **数据依赖**：如上 + `GET /api/gamification/me/badges`、`/me/points`、`/rankings`（积分/等级/时长真实化，FR-11）。queryKey `["users","me"]`、`["progress","dashboard"]`。

### P13 `/admin/courses` 管理端课程（重构，系列+班次两级总览）

> **契约对齐（task56 数据面盘点，2026-08-23）**：运行后端为 `app/domains/course_admin`（main.py L337 挂载），与旧 `app/admin/course_admin` 并存但**以 domains 为权威**。
> - 系列列表 `GET /api/admin/courses/series` 仅接受筛选参数 `keyword / institution_id / delivery_mode(online_live|online_recorded|offline_face_to_face) / sale_status(draft|on_sale|off_sale) / sort(default|newest|name_asc|name_desc) / page / page_size`（**无 subject/level 参数**）；当前实现**不返回** `institution_name`、`cohort_count`、`subject/level` —— 因此 P13 图中「机构」「班次数」两列为**契约缺口**，本页暂以「交付模式/状态/创建时间」列代替，不做 MOCK。
> - 系列 CRUD：`POST/PATCH/DELETE /api/admin/courses/series`；**删除为软删**且 `series` 表无 `yn` 列 → 实现为 `sale_status='off_sale'`（响应 `系列已下架`），故删除语义≈下架；`DELETE` 属 task56 GWT① 必须全通，需前端新增 `deleteAdminSeries`。
> - 班次按系列取：`GET /api/admin/courses/series/{id}/cohorts`；行内「班次」→ 跳 `[seriesId]` 详情（task57）。`GET /api/admin/courses/series/{id}` 详情含 `target_learner/learning_goal/grade_codes` 三组目标标签数组。

```
┌────────────────────────────────────────────────────┐
│ 课程管理  [搜索] [筛选:机构/交付模式/状态] [+新建系列] │
│ Tabs: [系列] [班次]                                  │
│ ┌ DataTable（系列）───────────────────────────────┐ │
│ │ 系列名 | 机构 | 交付 | 班次数 | 状态 | 操作        │ │
│ │ 入门班 | 总校  | 直播 | 3      | 在售 | 管理▾     │ │
│ │  操作下拉: [编辑][班次][上下架][删除(软)]          │ │
│ └─────────────────────────────────────────────────┘ │
│ 新建系列 Dialog：名称/编码/机构/交付模式/分类/封面/描述 │
│ 上下架 = sale_status draft⇄on_sale⇄off_sale          │
└────────────────────────────────────────────────────┘
```

- **组件清单**：DataTable（新）、FilterBar、Dialog + Form（含 Select 机构/交付模式）、StatusBadge、DropdownMenu（新）、Pagination、ConfirmDialog
- **交互**：系列 CRUD `POST/PATCH/DELETE /api/admin/courses/series`（**软删除 yn=0**）；行内「班次」→ 跳班次 Tab 或详情页；「上下架」切换 `sale_status`（在售时用户端可见）；删除需 ConfirmDialog 并说明「下架优先于删除」；分页（full 档 219 系列）。
- **数据依赖**：`GET /api/admin/courses/series?page=&keyword=&institution_id=&delivery_mode=`、CRUD 系列 + `GET /api/admin/courses/series/{id}/cohorts`。queryKey `["admin","courses","series","{page}"]`。

### P14 `/admin/courses/[seriesId]` 管理端课程详情（重构，四级 CRUD）

```
┌────────────────────────────────────────────────────┐
│ 面包屑: 课程 / 入门班                                │
│ 系列信息卡（可编辑） + [新增班次]                     │
│ ┌ 班次表 DataTable ──────────────────────────────┐ │
│ │ 班次 | 价格 | 容量(已报) | 起止 | 状态 | 操作     │ │
│ │ 暑期一班|399|18/60|03-01~04-30|在售| [管理]      │ │
│ └────────────────────────────────────────────────┘ │
│ 选中班次 → 模块管理（下方 Panel，Accordion）          │
│ ▾ 模块一 Python基础  6课次/18学时 [新增课次][编辑]    │
│    课次列表（Table）: 序号|标题|日期|状态|资源|操作   │
│    资源: [课件][视频][作业][考试]（4 入口 Dialog）    │
│    └ 视频上传: 分片→转码状态轮询（transcode_status） │
│      + 章节管理（start_second/end_second）           │
└────────────────────────────────────────────────────┘
```

- **组件清单**：DataTable、Accordion、Stepper（分片上传）、Uploader（新：分片/进度）、StatusBadge（transcode/review）、Dialog + Form、Timeline（视频转码轨迹）
- **交互**：班次 CRUD（sale_price/max_student_count/start_date）；模块 CRUD（stage_no 排序，唯一约束 cohort_id+stage_no/module_code）；课次 CRUD（session_no 唯一）；**视频上传三表流程**：`session_asset`（material_category=video, access_scope）→ `POST /api/admin/courses/videos/init`（分片 init/finalize）→ `bind` 到课次 → 转码状态轮询（pending→in_progress→completed/failed，3s refetchInterval，终态停）+ 审核状态徽章（pending/approved/rejected）；章节管理（分片起止秒，可拖拽预览）；删除全部软删。
- **数据依赖**：四级 CRUD `/api/admin/courses/{series|cohort|module|session}` + 视频 `init/finalize/bind` + `GET /api/admin/courses/sessions/{id}/assets`。queryKey `["admin","courses","series","{id}"]` 等层级 key。

> **task57 契约对齐附注（2026-08-24，权威源 = 后端 `app/domains/course_admin/router.py + schemas.py`，与 task12-contract.md 一致）**
> - 四级 CRUD 端点齐全：`*Series / *Cohort / *Module / *Session` 各含 list+detail+create+patch+delete。
> - **归属字段（前端勿沿用旧契约）**：`Module` 归属 `cohort_id`（非 series_id）；`Session` 归属 `series_cohort_course_id`（当前 schema 即 module 物理 ID，非 module_id）；`Cohort` 创建必填 `institution_id + head_teacher_id`。
> - **视频分片真实端点（与旧 upload/init 不同）**：`POST /videos/init-chunked`（body: session_id/file_name/file_size/chunk_count）→ `POST /videos/finalize-chunked`（upload_id）→ `POST /videos/bind-session`（query: session_id/video_id/sort_no=0）→ `GET /videos/{video_id}/transcode-status`。
> - **转码枚举**：`transcode_status ∈ pending|in_progress|completed|failed`；`review_status ∈ pending|approved|rejected`（后端 `VideoCreateAdmin` 校验）。前端徽章映射：pending→warning、in_progress→primary、completed→success、failed→destructive；审核徽章 pending/approved/rejected。
> - **唯一约束错误码（conflicting → HTTP 409，code 为字符串）**：系列 `40901`/班次 `40902`/模块阶段 `40903`/课次 `40904`/资源 `40905`/视频 `40906`/章节 `40907`。前端在 create 类 mutation `onError` 按 `err.code` 分支 toast 提示对应业务码，禁吞错（R-7）。
> - **契约缺口（前端 UI 先呈现，后端端点未注册）**：
>   - 课次「资源 4 入口 Dialog」的课件/作业/考试 → 无 `sessions/{id}/assets` 活跃端点；**视频入口**走真实 init-chunked/finalize/bind/transcode-status。
>   - **章节管理（session_video_chapter）**：路由层无章节 CRUD 端点（仅 repo `ChapterAdminRepo.insert/update/hard_delete` + schema 就绪）。前端章节 UI 做存量展示，保存/新增需后端端点，标注占位；待后端开放后接线。
>   - Series 详情/列表返回**不含** subject/level/target_hours/level_name —— 旧 `[seriesId]/page.tsx` 的 `subjectLabel(series.subject_code)` 属旧契约残留，重构时移除，以 `institution_id + delivery_mode + target_*_codes` 为准。

### P15 `/admin/questions` 管理端题库（重构，题库+题目两级）

```
┌────────────────────────────────────────────────────┐
│ 题库管理  [搜索] [筛选:分类] [+新建题库] [批量导入]    │
│ Tabs: [题库] [题目]                                 │
│ ┌ DataTable（题库）──────────────────────────────┐ │
│ │ 题库名 | 分类 | 题目数 | 状态 | 操作             │ │
│ │ 编程题库 | 编程 | 320 | 启用 | [管理]▾          │ │
│ └────────────────────────────────────────────────┘ │
│ 题目 Tab（选中题库后）:                             │
│ ┌ DataTable（题目）─────────────────────────────┐ │
│ │ 题号 | 题型 | 题干(截断) | 客观 | 状态 | 操作   │ │
│ │ Q1001|单选|Python变量...|✓|启用|[编辑][解析]    │ │
│ └────────────────────────────────────────────────┘ │
│ 批量导入 Dialog: 拖拽 .xlsx/.csv → 校验 → 预览 N 行 │
│   → 导入（进度条）→ 结果（成功/失败行明细）           │
│ 删除题库 ConfirmDialog（题量确认提示）               │
└────────────────────────────────────────────────────┘
```

- **组件清单**：DataTable、Tabs、Uploader、ImportPreviewDialog（新）、StatusBadge（objective_flag 客观/主观）、Pagination、FilterBar
- **交互**：题库 CRUD（bank_code 唯一）；选题库 → 题目列表 `GET /api/admin/questions?bank_id=`；题目行「编辑/解析」→ 跳 `P16` 或右侧 Dialog；**批量导入**：校验（题干/答案必填、题型枚举）→ 预览 → 确认导入（轮询进度，1752 题量）→ 结果报告（错误行定位）；**标签能力废除**：改为题目知识点全文检索（stem+analysis_text LIKE），不维护标签表（edu-data 决策⑤）。
- **数据依赖**：`GET/POST/PATCH/DELETE /api/admin/questions/banks`、`GET/POST /api/admin/questions`、`POST /api/admin/questions/import`。queryKey `["admin","questions","banks"]`、`["admin","questions","list","{bankId}","{page}"]`。

### P16 `/admin/questions/[id]` 管理端题目（重构，含解析编辑）

```
┌────────────────────────────────────────────────────┐
│ 面包屑: 题库 / 编程题库 / Q1001                     │
│ ┌ 题目编辑表单 ──────────────────────────────────┐ │
│ │ 所属题库（只读） | 题号（只读）                  │ │
│ │ 题型 Select（dim_question_type: 单选/多选/判断/  │ │
│ │              填空/拖拽/连线/...）                │ │
│ │ 题干 Textarea（Markdown 支持）                  │ │
│ │ 选项编辑器（JSON，按题型切换控件）                │ │
│ │   单选→RadioGroup 组 | 多选→Checkbox 组         │ │
│ │ 答案 answer_text Textarea                      │ │
│ │ ★解析 analysis_text Textarea（Markdown 预览）   │ │ ← 重构核心
│ │ 客观题开关 objective_flag（自动判题）            │ │
│ │ [保存] [保存并继续] [返回列表]                   │ │
│ └────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

- **组件清单**：Form（复杂表单）、Select、RadioGroup、Checkbox、Textarea、MarkdownPreview（复用）、JSONEditor（选项）
- **交互**：`GET /api/admin/questions/{id}` 回填；保存 `PATCH /api/admin/questions/{id}`；**analysis_text 解析编辑为必修**（保存前校验非空提示）；题型切换时选项控件联动（options_json 结构按题型 schema）；预览 tab 同时渲染题干+解析（与用户端 QuizPanel 一致）。
- **数据依赖**：`GET /api/admin/questions/{id}`、`PATCH /api/admin/questions/{id}`、`GET /api/dim/question-types`（题型枚举）。queryKey `["admin","questions","detail","{id}"]`。

### P17 `/admin/users` 管理端用户（重构）

```
┌────────────────────────────────────────────────────┐
│ 用户管理  [搜索(昵称/手机/账号)] [角色筛选] [状态筛选] │
│ ┌ DataTable ────────────────────────────────────┐ │
│ │ 用户 | 手机 | 角色 | 状态 | 注册时间 | 学习 | 操作 │ │
│ │ 张三 | 138**|学生|启用|08-01|6门课|[查看][编辑] │ │
│ └────────────────────────────────────────────────┘ │
│ 行「查看」→ 学习详情 Dialog（6 指标面板）：            │
│   报名班次/进度/最近学习/作业正确率/考试/收藏         │
│ 行「编辑」→ 角色切换（student/teacher/manager/admin） │
│   状态切换（启用/禁用）——最后 1 个可用 admin 禁操作    │
└────────────────────────────────────────────────────┘
```

- **组件清单**：DataTable、FilterBar、Dialog（学习详情：6 StatCard + 最近动态列表）、RoleSelect（新）、StatusBadge、ConfirmDialog、Pagination、SearchInput（防抖）
- **交互**：列表 `GET /api/admin/users?page=&keyword=&role=&status=`；搜索防抖 400ms；角色/状态切换 `PATCH /api/admin/users/{id}`；**红线保护**：最后 1 个可用 admin 的禁用/降级操作前端禁用 + 提示；学习详情弹窗 `GET /api/admin/users/{id}/learning`（聚合 student_cohort_rel + progress）。
- **数据依赖**：如上。queryKey `["admin","users","list","{page}"]`。

### P18 `/admin/rag` 管理端 RAG（新增上传入口区块）

```
┌────────────────────────────────────────────────────┐
│ RAG 控制台  Tabs: [集合][上传][调参][审计日志][高级检索]│ ← 新增"上传"Tab
│ 上传 Tab（UploadPanel）：                           │
│ ┌────────────────────────────────────────────────┐ │
│ │ 拖拽/点击选择（.md/.txt/.markdown/.pdf/.docx，  │ │
│ │ 单文件≤200MB，≤50 文件）  [选择文件] 多选         │ │
│ │ 文件列表: 名称 | 大小 | 校验状态 | 移除           │ │
│ │ [开始上传]（axios onUploadProgress 进度条）      │ │
│ │ 上传进度 ▓▓▓▓▓░░░ 3/5  ·  转知识任务中…          │ │
│ └────────────────────────────────────────────────┘ │
│ 任务列表（TaskTable，5s 轮询）：                     │
│ ┌ DataTable ────────────────────────────────────┐ │
│ │ 任务ID|类型|文件数|chunks 进度|状态|错误|时间     │ │
│ │ T-882|文档|3|120/300|运行中|—|08-16 14:00       │ │
│ │ T-881|文档|1|80/80|完成|—|08-16 13:40           │ │
│ └────────────────────────────────────────────────┘ │
│ 分区管理（PartitionPanel）：列表/_default 禁删提示    │
│ 集合健康卡：行数自动刷新（上传完成后 refetch）         │
└────────────────────────────────────────────────────┘
```

- **组件清单**：Tabs、Uploader（新，拖拽+多选+进度）、TaskTable（新 DataTable 变体）、StatusBadge（pending/running/done/failed）、PartitionList（新）、Alert（_default 保护提示）、PollingBadge
- **交互**：**文件校验**（扩展名白名单 + 大小）前端拦截；`POST /api/knowledge/admin/upload`（FormData 多文件，RBAC admin/manager）；**上传进度** `onUploadProgress` → 进度条；上传完成后进入任务列表；**任务轮询** `refetchInterval: 5000`（pending→running→done/failed，chunks 进度展示，终态停）；任务失败显示 error 明细 + 重试入口；分区列表 `GET /api/knowledge/partitions`，`_default` 显示「公共分区·不可删除」禁用删除；上传完成 → `invalidateQueries(["rag","collection"])` 刷新行数（FR-RAG-02 全链路）。
- **后端配套**（前端依赖契约）：`GET /api/knowledge/tasks`（分页倒序）、任务持久化 Redis + `knowledge_import_task` 表、源文件留 MinIO `edu-upload`。
- **数据依赖**：`POST /api/knowledge/admin/upload`、`GET /api/knowledge/tasks`、`GET /api/knowledge/status/{task_id}`、`GET/DELETE /api/knowledge/partitions`。queryKey `["rag","tasks"]`、`["rag","collection"]`、`["rag","partitions"]`。

### P18b `/admin/dashboard` 管理端仪表盘（重构，task55）

> **入口**：管理端侧边栏「仪表盘」（`ADMIN_NAV_ITEMS[0]`，`/admin/dashboard`）。风格 candy-playful（糖果色，`STYLE: candy-playful frozen`）。RBAC：非 admin 由 `AdminGuard` 拦截（manager/teacher/student 重定向用户端，后端 `/api/admin/*` ADMIN-only 为权威）。
> **数据契约（task55 数据面盘点，2026-08-23）**：后端当前**唯一**管理端真实聚合端点 = `GET /api/admin/users/dashboard/metrics`（user_admin 域，`schemas.DashboardMetrics`）：

```
{ total_user_count, active_user_count_7d, role_breakdown:{admin,manager,teacher,student},
  disabled_user_count, new_register_count_7d, avg_login_days_per_user_30d,
  register_trend_7d:[{date,count}x7] }   // 服务端已补零到 7 点
```

> **契约缺口（禁 MOCK，如实披露）**：订单数/营收/热门课程榜 —— trade/order|payment|refund 均为用户本人视角（`CurrentUser`），**无管理端全局聚合端点**。本轮**不伪造数据**：KPI / 趋势用上述真实用户类 metrics；订单/营收/榜单区块在 HTML 以**示例形态**呈现 + 标注「待后端 task70~91 聚合端点」，React 阶段缺端点时渲染**契约缺口占位卡**（非假数）。GWT② 的「KPI 真实聚合」落点为用户类 metrics 全真实。

```
┌ 指标卡(6) ───────────────────────────────────────────────┐
│ [用户总数] [7d活跃] [7d新增] [禁用账号] [角色分布] [人均登录30d] │  ← C18 StatCard + 角色分布卡
└──────────────────────────────────────────────────────────┘
┌ 近7天注册趋势（柱状，单系列 primary，§1.7）───────────────┐
└──────────────────────────────────────────────────────────┘
┌ 角色分布饼图（多系列 §1.7 前 N 色，饼图禁用相邻色）──────┐  × 热门课程榜（契约缺口占位）
└──────────────────────────────────────────────────────────┘
数据源: GET /api/admin/users/dashboard/metrics（真实）；订单/营收/榜单=契约缺口占位（待后端 task70~91）
```

- **组件清单**：MetricCards（重构现有 6 卡，去除 `text-[13px]` arbitrary 字号 → 收编 token）、StatCard（C18）、RegisterTrendChart（重构现有，单系列柱状 primary）、RoleDonutChart（新：角色分布饼图，名称映射 `userRoleLabel`）、RankFallback（新：契约缺口占位卡，展示「待后端订单/营收聚合端点」+ 跳转 `/admin/orders`? 含空态引导）。
- **交互**：KPI 卡只读；图表 hover tooltip（`valueFormatter` 带单位）；榜单占位卡无交互（标注数据源就绪时间）；加载失败 → `ErrorState` + 重试；未返回数据 → `LoadingState` 骨架。
- **状态流转**：仅 `loading`(骨架) → `success`(数据) / `error`(C8 + 重试)；三态不吞错。
- **数据依赖**：`GET /api/admin/users/dashboard/metrics`。queryKey `["admin","users","metrics"]`。
- **图表取色**：单系列趋势/主维 = `CHART_COLORS.primary`；角色分布饼图 = §1.7 8 色定性序取前 N（按角色数 **疏取避免相邻**：admin→indigo-600、student→violet-500、teacher→sky-500、manager→rose-500）。**禁**相邻同系（§1.7「饼图禁用相邻色」）。

### P19 `/dashboard` 学习仪表盘（适配重构，MOCK→真实数据）

> 用户重构清单未单列，但 FR-11 强制：15 处 MOCK + 5 处 TODO 全替换。列为适配项，优先于新页面验收（A4）。

```
┌ 指标卡(4) ──────┐ 折线: 学习时长 7 日    ┐
│ 学习时长/课次/  │ 柱状: 学科掌握度       │
│ 积分/连续打卡   │ 饼图: 学习结构         │
└────────────────┴──────────────────────┘
┌ 徽章墙(3) ──────┐ 排行榜 Top5          ┐
│ 最近解锁徽章     │ 我的排名 + 积分      │
└────────────────┴──────────────────────┘
数据源: /api/progress/dashboard + /api/gamification/me/badges + /me/points + /rankings
```

### P20 `/chat` AI 问答（新，SSE 流式）

> **入口**：AppShell 导航「智能问答」；学习页「AI 提问」`?context=session:{id}` 携带上下文（task21/23 联调后生效）。风格 candy-playful（糖果色，`STYLE: candy-playful frozen`）。
> **契约⑬ 依据**：SSE 事件 `start`/`retrieval`/`token`/`done`；`done` 事件 data **内嵌壳** `{code,message,data}`；`data.data.degraded_reason` 承载流中断降级文案；HTTP 4xx/5xx 前置错误走全局壳（code<字符串>+data:null）。

```
┌────────────────────────────────────────────────┐
│ [智能问答]              [＋ 新会话]               │
│ 消息区（flex-col 帖底，overflow-y-auto）          │
│  · 历史消息（chat_message）                      │
│    😊 用户(右对齐/糖果紫底/白字)                 │
│         [3xs 时间·muted]                        │
│    🤖 AI(左对齐/卡片白底/border，可含 Markdown)  │
│         [3xs 时间·muted][🔎] 收起引用            │
│  · 流式入列: token 增量追加 + 闪烁 cursor ▌       │
│  ┌─────── 输入区（sticky 底部，卡片容器）───────┐ │
│  │ [📎 context 徽标(可关闭)]                   │ │
│  │ [Textarea 自动增高]  [发送(糖果绿)]/[■停止]  │ │
│  │ 排队提示: 10s「AI 正在思考…」/ 60s 降级文案   │ │
│  └───────────────────────────┘                │
└────────────────────────────────────────────────┘
```

- **组件清单**：**ChatBubble**（新 C22，用户/AI 分角色气泡）、**MessageComposer**（新 C23，输入+发送/停止+排队提示）、EmptyState（C7，无历史）、ErrorState（C8，历史/流式错误）、StatusBadge（C3，引用计数角标）、Toast（流 `error` 事件提示）。
- **SSE 流式渲染**：用 `fetch(POST /api/chat/stream)` + `ReadableStream` 逐行解析 `event:`/`data:`（**非 EventSource**：需 POST body 传 prompt/context）。`token` 事件 `data` 追加到**当前 AI 消息缓冲**并增量 `setState` 渲染（末字符闪烁 `▌`, `animate-pulse`）；`retrieval` 事件 → 展示临时状态「🔎 检索知识库…」；`start` 事件 → 进入流式态。
- **done / 降级 / 错误态**：`done` 事件解析内嵌壳——`data.code===0` 完成（可选展示 `retrieved_count`/`final_count`/`latency_ms` 元信息）；`data.data.degraded_reason` 非空 → **降级 banner**（琥珀警告，展示 reason 文案而非报错，内容保留）；`error` 事件 → toast + **保留已流式部分** + 提供重试；HTTP 4xx/5xx → 全局壳解包 → C8 ErrorState。所有失败不吞错。
- **历史消息**：`GET /api/chat/sessions` 会话列表；`GET /api/chat/sessions/{id}/history` 取消息（空 → C7 引导提问）；`?context=session:{id}` → 直接加载该会话历史 + 输入区顶部显示上下文徽标（可关闭）。历史加载失败 → C8 + 重试。
- **输入区（MessageComposer）**：Textarea 自动增高（max 约 5 行）；Enter 发送 / Shift+Enter 换行；发送后 `streaming`（禁用发送，按钮变「■ 停止」）；空内容 / 未登录 disabled；第一包 `token` 前 10s 显示**排队提示**「AI 正在思考…」、>60s 无 token → **降级文案提示**（对齐 task92/93 多 agent 排队与降级，非报错）。
- **状态机**：`loading`(历史拉取) → `ready`(空态或历史) → `composing`(提交+等 start) → `streaming`(retrieval/token 增量) → `complete`(done 成功)｜`degraded`(degraded_reason 非空，内容完整)｜`error`(HTTP 壳/流 error/网络断 → C8+toast+保留部分+重试)。停止按钮：终止 fetch（AbortController）+ 保留已流部分。
- **数据依赖**：`POST /api/chat/stream`（SSE，body: `{prompt, session_id?, context?}`）、`GET /api/chat/sessions`、`GET /api/chat/sessions/{id}/history`、`DELETE /api/chat/sessions/{id}`（清空/新会话）。queryKey `["chat","sessions"]`、`["chat","history",id]`。

### P21 `/community` 社区列表（新，task51）

> **入口**：AppShell 导航「社区互助」。风格 candy-playful（糖果色，`STYLE: candy-playful frozen`）。
> **契约⑬ 依据**：`GET /api/community/posts` 翻页列表（响应壳解包 `data{total,page,page_size,items,mine_total_posts}`）；4 版块枚举 `english/math/programming/general`；排序 `HOT/NEW/LIKE`；`COLLABORATION` 布尔（登录）。点击帖子 → `/community/[postId]`（J 表内联动）。发布入口 → `/community/[postId]` 之外的发布表单入口（button 显式呈现）。

```
┌────────────────────────────────────────────────────────┐
│ [🐣 社区互助横幅 Hero（糖果渐变底 + 白字 + emoji）]        │
│   「一起讨论一起进步 · 找到同路人」                        │
│ 筛选行（FilterBar C9）：                                  │
│   [全部][英语][数学][编程][综合]  排序[热门▾]  [🔍 搜索kw] │
│   「我的帖子 {mine_total_posts}」计数                      │
│ ┌──────────────────────────────────────────────┐ │
│ │〔📌置顶〕标题（h3 点击→/community/[postId]）   │ 帖子卡
│ │  摘要 summary(sm·muted, 2行截断)              │(C24)
│ │  [编程] [教程] 标签徽章                        │
│ │  👤 作者名 · 🕒 时间 · 👁 浏览 · 💬 评 · 👍 赞 │
│ └──────────────────────────────────────────────┘ │
│  ...（列表，flex-col gap）                        │
│ [＋ 发新帖(糖果橙)]       分页 C2（共 N 条）      │
└─────────────────────────────────────────────────┘
```

- **组件清单**：**PostCard**（新 **C24**，帖子卡片）、**Pagination**（C2，翻页）、**FilterBar**（C9，版块筛选行）、**Select**（C12，排序）、**Input**+Button（搜索）、EmptyState（C7，`暂无帖子`）、ErrorState（C8，列表加载失败）、Badge（现有 ui 组件，tags 标签）。
- **列表渲染**：PostCard 展示 `title`（h3，点击 navigate `/community/{post_id}`）、`summary`（sm/muted，`line-clamp-2`）、`tags`（Badge 糖果浅底）、作者行（`author_name` · `created_at` 相对时间 · `view_count` 浏览 · `comment_count` 评论 · `like_count` 点赞，全部 `text-2xs` muted）；`is_pinned` 置顶显示 📌 徽标 + 置顶帖排前；`is_locked` 锁定帖展示锁图标（不可发评论仅提示）。
- **筛选/排序/搜索（FilterBar+Select+Input）**：版块按钮组（全部/英语/数学/编程/综合，映射 `board_code`）；排序 Select（热门 HOT/最新 NEW/点赞 LIKE）；关键词 Input 回车/防抖（≥2 字符）提交 `keyword`。任何筛选变更 → **重置 page=1** → refetch（React Query，queryKey 含筛选维度）。
- **分页（C2）**：`data.page/page_size/total` 驱动页码与「共 N 条」；`onPageChange` 更新 page 重取；page 越界回退 1（后端壳报错走 C8）。
- **发布入口**：页面固定 CTA「＋ 发新帖」（糖果橙，candy 主 CTA 样式），点击进入发布表单（弹出/独立路由 `/community/posts/new`，随发帖表单落地）；未登录跳登录。
- **状态机**：`loading`(列表拉取 skeleton) → `ready`(有数据) | `empty`(items 空 → C7「暂无帖子，来发第一篇吧」+ 发布 CTA) | `error`(HTTP 壳/网络断 → C8 + 重试)。筛选/排序/翻页切换：清空列表展示 `loading`（防旧数据闪），拉回后 `ready`/`empty`/`error`。所有失败不吞错。
- **数据依赖**：`GET /api/community/posts?board_code=&keyword=&sort=&page=&page_size=`（响应壳解包 `data`）；发布 `POST /api/community/posts`（点 CTA 后）；点赞 `POST /api/community/posts/{id}/like`（详情页）。queryKey `["community","posts",{board,kw,sort,page}]`、`["community","posts","count"]`。跳转 `/community/{post_id}`。
- **响应式**：帖卡网格——桌面卡片横排（作者/时间/统计在卡底）；移动单列 + 卡片占满；筛选行移动横滑（overflow-x-auto）；发布 CTA 移动端固定右下浮钮（FAB）。断点矩阵见 §6.1。

### P22 `/community/[postId]` 帖子详情（新，task52）

> **入口**：P21 帖子卡点击 → `/community/{post_id}`（J 表内联动）。风格 candy-playful（`STYLE: candy-playful frozen`）。
> **契约⑬ 依据**：`GET /api/community/posts/{post_id}` 详情（浏览 +1）；`GET/POST /api/community/posts/{post_id}/comments` 评论；`POST /api/community/posts/{id}/like|favorite` 点赞/收藏 react；`POST /api/community/comments/{id}/like` 评论点赞。响应壳解包 `data`。

```
┌────────────────────────────────────────────────────────┐
│ [← 返回列表]  [英语] 📌置顶  🔒锁定                      │
│ 标题 h1（糖果粗体）                                     │
│ 👤 作者名 · 🕒 时间 · 👁 浏览 · 👍 赞 · ⭐ 藏 · 💬 评   │
│ 操作行：[👍 点赞(糖果绿)] [⭐ 收藏(糖果黄)]  [+2分提示]  │
│ ┌────────────────────────────────────────────┐ │
│ │ 正文 content_md → MarkdownView 渲染          │ │
│ │ （prose 排版：标题/列表/引用/代码块/链接）    │ │
│ └────────────────────────────────────────────┘ │
│ ── 评论区（N 条）────────────────────────────── │
│ [评论输入框(Textarea 自动增高)] [💬 发布(糖果橙)]│
│ ┌ 评论卡 ────────────────────────────────┐    │
│ │ 👤 作者 · 🕒 时间 · [👍 赞]             │    │
│ │ 内容 content_md（MarkdownView 小字号）  │    │
│ └────────────────────────────────────────┘    │
│ 分页 C2（评论翻页）                             │
└─────────────────────────────────────────────────┘
```

- **组件清单**：**PostDetail**（新 **C25**，详情头 + 操作行 + 正文容器）、**CommentList/CommentItem**（新 **C26**，评论区）、**CommentComposer**（新 **C27**，评论输入）、**MarkdownView**（现有，正文/评论渲染，勿改其 `text-[15px]` 历史遗留）、Button/Textarea（ui）、Badge（版块/标签）、EmptyState（C7，`暂无评论`）、ErrorState（C8，详情/评论加载失败）、Pagination（C2，评论分页）、Skeleton（详情加载）。
- **详情头**：`board_code` 版块 Badge（糖果色）；`is_pinned` 📌 / `is_locked` 🔒 徽标；`title` h1；作者行 `author_name` · `created_at` 相对时间 · `view_count` 浏览 · `like_count` 赞 · `favorite_count` 藏 · `comment_count` 评（`text-2xs` muted）。
- **操作行（react）**：👍 点赞 / ⭐ 收藏 两个 toggle 按钮，`mine_react_like`/`mine_react_favorite` 驱动高亮态；点击 `POST .../like|favorite`（useMutation + toast R-7），响应 `ReactToggleResp{active,total_count,points_awarded}` → 乐观更新计数 + `points_awarded>0` 时 toast「+N 积分」；失败 toast + `console.error`（不吞错）。🔒 锁定帖：操作行隐藏点赞/收藏，仅提示「本帖已锁定」。
- **正文渲染**：`content_md` → `MarkdownView`（prose 排版：标题/列表/引用/代码块/链接）；`is_locked` 帖正文底部显示锁定提示条。
- **评论区（C26/C27）**：`GET .../comments?page&page_size` 分页列表（`total` 驱动「N 条」+ C2 翻页）；每条 `author_name` · 相对时间 · `content_md`（MarkdownView 小字号）· `mine_liked` 高亮 + 评论点赞 `POST /api/community/comments/{id}/like`（同 react 规则）；`parent_id` 回复缩进展示。**CommentComposer**：Textarea 自动增高 + 「💬 发布」按钮；提交 `POST .../comments {content_md}` → 成功 toast「评论成功 +2 积分」+ **invalidate 评论 queryKey**（重拉列表）；失败 toast + `console.error`。🔒 锁定帖：输入区禁用 + 提示。
- **状态机**：详情 `loading`(Skeleton) → `ready` | `error`(404 壳 `COMMUNITY_POST_NOT_FOUND` / 网络断 → **C8 + 「← 返回列表」CTA**，GWT③)。评论区独立状态：`loading`(骨架) → `ready`(有评论) | `empty`(C7「暂无评论，来抢沙发」+ 输入区) | `error`(C8 + 重试)。写操作失败均 toast + `console.error` 不吞错。
- **数据依赖**：详情 `GET /api/community/posts/{post_id}`；评论 `GET/POST /api/community/posts/{post_id}/comments`；react `POST /api/community/posts/{id}/like|favorite`、`POST /api/community/comments/{id}/like`。queryKey `["community","post",id]`、`["community","comments",id,page]`。返回 `router.back()` 或 `/community`。
- **响应式**：详情头/操作行桌面横排、移动换行堆叠；正文容器全宽；评论输入区 sticky 底部（移动端）；断点矩阵见 §6.1。

### P23 `/achievements` 成就中心（重构，task53）

> **入口**：AppShell/Hero 导航「成就中心」。风格 candy-playful（糖果色，`STYLE: candy-playful frozen`）。
> **契约⑬ 依据**：`GET /api/gamification/me/badges` 徽章墙（响应壳解包 `data{total,unlocked_count,next_milestone,items[]}`）；`GET /api/gamification/me/points?page&page_size` 积分/等级/流水；`GET /api/gamification/rankings?scope&dimension&top_n` 排行榜（ZSET，task15 已验证 4 周期 key + 积分实时累计）。均无 MOCK，真实 API。

```
┌────────────────────────────────────────────────────────┐
│ [🐻 Hero 成就横幅（糖果渐变底 + emoji「成就中心·让努力被看见」）]│
│ ┌ 徽章墙 ──────────────────────────────────────────┐ │
│ │ [🎖 已解锁 N/M]  [✨ 下一枚:<next_milestone>]      │ │
│ │ ┌徽章卡┐┌徽章卡┐┌徽章卡┐┌徽章卡┐（grid）         │ │
│ │ │😍 传说   ││🔒 稀有   ││…    │     已解锁高亮 │ │
│ │ │+50 积分  ││进度 3/10 ││     │     未解锁置灰 │ │
│ │ └───────┘└───────┘└───────┘                  │ │
│ └─────────────────────────────────────────────┘ │
│ ┌ 积分总览 ──────────────────────────────────────┐ │
│ │ [🏅 Lv.N · 等级名]    [💸 总积分]  进度条→下一级 │ │
│ │ ┌积分流水（分页）─────────────────────────┐   │ │
│ │ │[↑] 发布帖子  +5  余额 2330│            │   │ │
│ │ │[↓] 学习时长  -0        │（delta±色）   │   │ │
│ │ │ 分页 C2（‹ 页码 › 共 N 条）            │   │ │
│ │ └────────────────────────────────────┘   │ │
│ └─────────────────────────────────────────────┘ │
│ ┌ 排行榜（ZSET）────────────────────────────────┐ │
│ │ [日榜][周榜][月榜][总榜]  [积分][时长][徽章数]   │ │
│ │ 1👑 admin (my)   12850 分 ┐ is_myself 高亮    │ │
│ │ 2🥈 小明          9876 分 │ 前三名奖牌          │ │
│ │ …                                        │ │
│ │ 📍我的排名：第 N 名 · xxx 分                │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

- **组件清单**：**BadgeWall**（重构 **C28**，徽章墙，已解锁高亮/未解锁置灰+进度）、**PointOverview**（重构 **C29**，积分/等级总览 → 现 PointLogTable 拆分）、**PointLogList**（重构 **C30**，积分流水分页）、**RankingTabs**（重构 **C31**，排行双 tablist：时间范围×维度）、StatusBadge（C3，等级/稀有度）、EmptyState（C7）、ErrorState（C8，各板块失败重试）、Pagination（C2，积分流水）、Skeleton（三板块加载）。
- **徽章墙（C28）**：`unlocked` 区分已解锁（糖果彩色底 + `reward_points` 积分提示「+N 积分 · 已解锁」）/ 未解锁（置灰 `grayscale opacity-50` + 右下 🔒 lock 角标 + 解锁进度条 `progress_current/progress_required` 驱动 + `progress_pct` aria-valuenow）。`icon_emoji` 展示、缺省 🎖️。`rarity` 稀有度四类（COMMON/RARE/EPIC/LEGENDARY → 普通/稀有/史诗/传说）。**满级判定**（对抗 fe-task01 #5）：`unlocked_count >= total` → 展示「已满级」，不展示后端 `next_milestone` 占位。统计行「已解锁 N/M 枚」+（非满级时）「下一枚:xxx」。按 `category`（LEARNING/ACHIEVEMENT/SOCIAL）分组或 grid。
- **积分总览（C29）**：`level_no/level_title` 徽标 + `total_points` 大数字（tablular-nums）+ 等级进度条（`level_progress_pct`；**最高级判定** `next_level_min <= level_min` → 满 100% + 「已达最高等级」）。三态：loading 骨架 / error 错误卡（**绝不以 0 分占位**，对抗 fe-task01 #4）/ ready。
- **积分流水（C30/分页 C2）**：`recent_logs[]` 每条 `point_type` 文案映射（POINT_TYPE_LABEL：POST_CREATE 发布帖子 / COMMENT_CREATE 发表回帖 / LIKE_GAIN 帖子获赞 / QUIZ_FULL_CORRECT 练习满分 / COURSE_FINISHED 完成课程 / VOCAB_MASTERED 单词掌握 / STUDY_TIME 学习时长 / LOGIN 每日登录 / BADGE_REWARD 徽章奖励，未知类型透传）+ `note` + `created_at` 时间 + `delta`（`+5`/`-0`，正向 success 绿 / 负向 destructive 红）+ `balance_after` 余额。`logs_total` 驱动 C2 分页（PAGE_SIZE=10）。空态 C7「还没有积分记录，去社区发帖/回帖、完成学习任务赚取第一笔积分吧～」。
- **排行榜（C31，ZSET）**：双 tab 组（时间范围 `SCope` DAILY 日榜/WEEKLY 周榜/MONTHLY 月榜/ALL_TIME 总榜 × 维度 `dimension` POINTS 积分/STUDY_MIN 学习时长/BADGE_COUNT 徽章数），APG Tabs（双 tablist 共用 `aria-controls` 指向排行面板 + roving tabindex + 方向键）。`top[]` 列表：前三名奖牌（第 1 👑 `text-warning`/2、3 🥈 中性）、名次数字、`user_name`（`is_myself` 高亮 + 「我」徽标）、`metric_value`（+维度单位 分/分钟/枚）。底部「我的排名」`my_rank`（`rank_no` + `metric_value`）。`source` 展示（`ZSET` → 标记「实时」）。快照 `snapshot_date`。空态 C7「该榜暂时还没有数据，快去学习抢榜首吧～」。
- **状态机**：三板块各自独立状态（徽章/积分流水/排行分别 loading → ready | empty | error + 重试），互不阻塞；排行为 tab 切换天然触发重查（queryKey 含 scope/dimension）、积分流水翻页重查（queryKey 含 page）；失败 toast + `console.error` 不吞错。徽章墙与「成就中心」页头 `unlocked_count` 共享 queryKey `["gamification","badges"]` 去重。
- **数据依赖**：`getMyBadges`/`getMyPoints(page,10)`/`getRankings(scope,dimension,20)`（均 `src/lib/api/community.ts` 已封装，壳解包）。queryKey `["gamification","badges"]`、`["gamification","points",page]`、`["gamification","rankings",scope,dimension]`。
- **响应式**：徽章墙 grid `2→3→4` 列（移动 2 列）；积分总览桌面横排/移动堆叠；排行行内 `user_name` truncate；断点矩阵见 §6.1。

---

## 三、组件复用清单

### 3.1 现有 `src/components/ui`（实际 19 个，无 DataTable/Pagination/Stepper/Uploader 等复合组件）

```
avatar  badge  button  card  checkbox  dialog  error-boundary  form  input  label
offline-indicator  progress  radio-group  separator  skeleton  slider  tabs  textarea  toast
```

**复用规则**：以上全部为 shadcn（Base UI）风格，新组件必须同风格（`cva` + `useRender` + `cn`，见 badge.tsx 范式）；`error-boundary` 每个页面根挂载；`offline-indicator` 保持现状。

### 3.2 新增组件清单（按依赖序实现，fe-spec-writer 逐一出契约）

| # | 组件 | 位置 | 用途 | 关键 Props 契约（初版） |
|---|---|---|---|---|
| C1 | **DataTable** | `components/ui/data-table.tsx` | 管理端 5 页 + 复习中心 | `<DataTable<T> columns={ColumnDef<T>[]} data rows? pageMeta? onSort? onRowClick? loading? empty? />`；内嵌排序/加载骨架/空态 |
| C2 | **Pagination** | `components/ui/pagination.tsx` | 全部列表页 | `<Pagination page pageSize total onPageChange disabled />`；页码 + 上一页/下一页 + 总数；`aria-label` |
| C3 | **StatusBadge** | `components/ui/status-badge.tsx` | 状态展示统一 | `<StatusBadge status tone="success|warning|danger|neutral|primary" label />`；基于 Badge + 语义色 class；**枚举文案映射表集中于此（§3.3）** |
| C4 | **Stepper** | `components/ui/stepper.tsx` | 支付/退款/导入流程 | `<Stepper steps={[{title,status}]} current />`；status: done/current/todo |
| C5 | **Uploader** | `components/ui/uploader.tsx` | RAG 上传/视频分片/批量导入 | `<Uploader accept multiple maxSize onFiles onProgress />`；拖拽 + 点击 + 校验 + 进度 |
| C6 | **Timeline** | `components/ui/timeline.tsx` | 工单跟进/退款轨迹/视频转码 | `<Timeline items={[{title,desc,time,status}]} />`；垂直节点线，语义色节点 |
| C7 | **EmptyState** | `components/ui/empty-state.tsx` | 全站空态 | `<EmptyState icon title description action? />`；图标 + 文案 + CTA，居中 |
| C8 | **ErrorState** | `components/ui/error-state.tsx` | 全站错误态 | `<ErrorState title message retry? />`；**不吞错**，展示 message + 重试 |
| C9 | **FilterBar** | `components/ui/filter-bar.tsx` | 课程中心/管理端列表 | `<FilterBar children />`；flex wrap + gap-2 容器，内含 Select/Input 组合 |
| C10 | **ConfirmDialog** | `components/ui/confirm-dialog.tsx` | 删除/取消/撤销等危险确认 | 基于 Dialog；`title description confirmText tone destructive`；确认按钮 destructive |
| C11 | **DropdownMenu** | `components/ui/dropdown-menu.tsx` | 行操作（管理端） | Base UI Menu；触发按钮 + 菜单项；键盘导航 |
| C12 | **Select** | `components/ui/select.tsx` | 表单下拉（类型/状态/机构） | Base UI Select；含 label + error + disabled |
| C13 | **Accordion** | `components/ui/accordion.tsx` | 课程大纲四级树/模块管理 | Base UI Accordion；单/多展开 |
| C14 | **PriceText** | `components/ui/price-text.tsx` | 金额展示 | `<PriceText amount prefix="¥" original? highlight? />`；划线原价 + tabular-nums |
| C15 | **CouponCard** | `components/feature/coupon-card.tsx` | 优惠券展示（P1/P8） | `coupon` 数据 + `onUse? onReceive? state` |
| C16 | **CohortCard** | `components/feature/cohort-card.tsx` | 班次选择/我的班次 | `cohort` + `selected? disabled? onSelect`；容量进度 |
| C17 | **CourseCard** | `components/feature/course-card.tsx`（重构现有） | 课程中心/收藏 | `series` 摘要 + href；封面 16:9 rounded-3xl |
| C18 | **StatCard** | `components/ui/stat-card.tsx` | 仪表盘/个人中心/学习详情 | `label value unit icon?` |
| C19 | **TaskTable** | `components/feature/task-table.tsx` | RAG 任务列表 | 基于 DataTable + StatusBadge + 轮询 |
| C20 | **NavListItem** | `components/ui/nav-list-item.tsx` | 个人中心入口列表 | `icon label href badge? chevron` |
| C21 | **EmptyState 派生：CollectionHealthCard** | `components/feature/rag/` | RAG 集合健康 | 行数 + 分区 + 索引状态 |
| C22 | **ChatBubble** | `components/feature/chat/chat-bubble.tsx` | AI 问答消息（P20） | `role("user"\|"ai") content sessionId streaming? meta?`；用户右对齐糖果紫底白字 / AI 左对齐卡片底；`streaming` 加闪烁 cursor；`meta` 展示 retrieved/latency |
| C23 | **MessageComposer** | `components/feature/chat/message-composer.tsx` | AI 问答输入区（P20） | `onSend streaming onStop disabled contextTag? queueHint? degradedHint?`；Textarea 自动增高 + Enter 发送 / Shift+Enter 换行 + 发送/停止切换 + 排队/降级提示 |
| C24 | **PostCard** | `components/feature/community/post-card.tsx` | 社区帖子卡片（P21） | `post` + `onOpen(post_id)`；标题/摘要 2 行截断/标签 Badge/作者·时间·浏览·评论·点赞统计；置顶📌/锁定🔒 |
| C25 | **PostDetail** | `components/feature/community/post-detail.tsx` | 帖子详情头+操作行+正文容器（P22） | `post` + `onBack` + `onLike`/`onFavorite`；版块 Badge/置顶锁定/标题/作者行/点赞收藏 toggle（mine_react_* 高亮 + 乐观计数） |
| C26 | **CommentList/CommentItem** | `components/feature/community/comment-list.tsx` | 评论区（P22） | `comments` + `onLike(comment_id)` + `onPageChange`；作者/时间/内容 MarkdownView/点赞高亮/回复缩进/空态 C7 |
| C27 | **CommentComposer** | `components/feature/community/comment-composer.tsx` | 评论输入（P22） | `onSubmit(content_md)` `disabled locked?`；Textarea 自动增高 + 发布按钮 + 锁定禁用提示 |
| C28 | **BadgeWall** | `components/achievement/badge-wall.tsx`（重构现有） | 徽章墙（P23） | `data`；已解锁糖果彩/未解锁置灰 + 进度条 `progress_current/required` + `rarity` 稀有度 + 满级判定 + 分 category 网格 |
| C29 | **PointOverview** | `components/achievement/point-overview.tsx`（重构现 PointLogTable） | 积分/等级总览（P23） | `level_no/level_title/total_points/level_progress_pct`；最高级判定 `next_level_min<=level_min` → 满 100% + 「已达最高等级」；三态不吞错 |
| C30 | **PointLogList** | `components/achievement/point-log-list.tsx`（重构现 PointLogTable） | 积分流水分页（P23） | `recent_logs[]` + `logs_total` + C2 分页（PAGE_SIZE=10）；`point_type` 文案映射 + `delta` 正负色 + `balance_after` 余额 |
| C31 | **RankingTabs** | `components/achievement/ranking-tabs.tsx`（重构现有） | 排行榜双 tab（P23） | 时间范围 × 维度双 tablist（APG Tabs + roving tabindex）；`top[]` 前三奖牌 + `is_myself` 高亮 + `my_rank` 我的排名 + `source` 实时标记 |

> 实现顺序建议：C1→C2→C3→C7→C8→C9→C10（基础设施）→ C12→C13→C14（表单）→ C5→C6→C4→C11（复合）→ C15~C21（业务）。每组件配套 vitest 单测（render + 交互 + a11y 快照）。

### 3.3 全局映射表（StatusBadge 集中维护，两处消费：徽章 + 文案）

```
订单 order_status:        pending→warning"待付款" paid→success"已支付" completed→muted"已完成"
                          cancelled→muted"已取消" partial_refunded→warning"部分退款" refunded→destructive"已退款"
订单明细 order_item_status: 同上（pending/paid/completed/cancelled/refunded）
支付 payment_status:      pending→warning"处理中" paid→success"已支付" failed→destructive"失败"
                          closed→muted"已关闭" partial_refunded→warning"部分退款" refunded→destructive"已退款"
退款 refund_status:       pending→warning"审核中" approved→primary"已通过" rejected→destructive"已拒绝" refunded→success"已退款"
券 receive_status:        unused→primary"未使用" used→muted"已使用" expired→muted"已过期"
报名 enroll_status:       active→success"学习中" completed→muted"已完成" cancelled→muted"已取消" refunded→destructive"已退款"
课次 teaching_status:     scheduled→muted"未开始" in_progress→primary"进行中" completed→success"已完成" cancelled→destructive"已取消"
转码 transcode_status:    pending→warning"待转码" in_progress→primary"转码中" completed→success"已就绪" failed→destructive"失败"
审核 review_status:       pending→warning"待审核" approved→success"已通过" rejected→destructive"已驳回"
工单 ticket_status:       pending→warning"待受理" in_progress→primary"处理中" closed→muted"已关闭"
优先级 priority_level:    low→muted"低" medium→muted"中" high→warning"高" urgent→destructive"紧急"
系列 sale_status:         draft→muted"草稿" on_sale→success"在售" off_sale→muted"已下架"
交付 delivery_mode:       online_live→primary"在线直播" online_recorded→primary"在线录播" offline_face_to_face→primary"线下面授"
退费类型 refund_type:     personal_reason"个人原因" course_unsatisfied"课程不满意" schedule_conflict"时间冲突" duplicate_purchase"重复购买"
工单类型 ticket_type:     after_sales"售后" complaint"投诉" refund"退款" appeal"人工申诉"
```

---

## 四、页面间跳转地图

### 4.1 主业务链路（领券 → 下单 → 支付 → 报名 → 学习 → 售后）

```
/courses ──点卡片──► /courses/[seriesId] ──领券按钮──► 领券 Dialog（页内）
                          │ 报名按钮（选中班次+券）
                          ▼
                     POST /api/orders ──成功──► /orders/[orderId]/pay
                                                     │ 模拟支付回调
                                                     ▼
                                              POST /api/payments（轮询）→ paid
                                                     │ 后端: order→paid + 报名 active
                                                     ▼
                                         支付成功页 ──跳转──► /orders（订单列表）
                                                     │「前往学习」
                                                     ▼
                                               /my-courses ──继续学习──► /learning/[seriesId]/[sessionId]
                                                     │「售后」入口
                                                     ▼
                                               /tickets（工单/申诉）或 /refunds（退款）
```

### 4.2 跳转表（源 → 目标 → 触发 → 参数）

| # | 源页面 | 目标页面 | 触发条件 | 携带参数 |
|---|---|---|---|---|
| J1 | `/courses` | `/courses/[seriesId]` | 点击 CourseCard | `seriesId`（路径） |
| J2 | `/courses/[seriesId]` | 领券 Dialog（页内） | 点「领券」 | `seriesId`（查适用券） |
| J3 | `/courses/[seriesId]` | `/orders/[orderId]/pay` | 点「立即报名」成功创建订单 | `orderId`（路径）；请求体 `cohort_id + coupon_receive_record_id` |
| J4 | `/courses/[seriesId]` | `/login` | 未登录点报名/领券/收藏 | `redirect=/courses/{seriesId}` |
| J5 | `/courses/[seriesId]` | `/favorites` | 收藏成功（收藏在服务端） | 无（列表页刷新） |
| J6 | `/orders` | `/orders/[orderId]/pay` | 点「去支付」（pending 单） | `orderId` |
| J7 | `/orders/[orderId]/pay` | `/orders` | 支付成功 5s 倒计时/立即查看 | `orderId`（列表高亮 `?highlight=`） |
| J8 | `/orders/[orderId]/pay` | `/my-courses` | 支付成功「前往学习」 | 无（报名已生效） |
| J9 | `/orders` | `/refunds` | 点「申请退款」 | `order_item_id + orderId`（query） |
| J10 | `/orders` | `/tickets` | 点「售后/投诉」 | `order_item_id`（query） |
| J11 | `/refunds` | `/orders` | 点「查看订单」 | `orderId` |
| J12 | `/tickets` | 新建工单 Dialog（页内） | 点「+新建工单」 | `order_item_id`（预填班次） |
| J13 | `/tickets` | `/refunds` | 工单类型=退款 | 无（Tab 联动可选） |
| J14 | `/my-courses` | `/learning/[seriesId]/[sessionId]` | 点「继续学习」 | `seriesId + sessionId`（最近未完成） |
| J15 | `/my-courses` | `/courses/[seriesId]` | 点「课程详情」 | `seriesId + ?cohort_id=`（班次高亮） |
| J16 | `/my-courses` | `/tickets` | 点「售后」 | `order_item_id` |
| J17 | `/learning/[seriesId]/[sessionId]` | `/chat` | 点「AI 提问」 | `?context=session:{sessionId}` |
| J18 | `/learning/[seriesId]/[sessionId]` | `/practice/[mode]` | 点「错题本/复习」 | `mode` |
| J19 | `/practice/[mode]` | `/learning/...` | 复习结果→巩固 | 无 |
| J20 | `/me` | `/orders` `/coupons` `/favorites` `/refunds` `/tickets` `/my-courses` `/practice/wrong-book` | 点入口行 | 无 |
| J21 | `/favorites` | `/courses/[seriesId]` | 点卡片 | `seriesId` |
| J22 | `/coupons` | `/courses` | 点「去使用」 | `?coupon_id=`（可选） |
| J23 | `/admin/courses` | `/admin/courses/[seriesId]` | 点「管理/班次」 | `seriesId` |
| J24 | `/admin/questions` | `/admin/questions/[id]` | 点「编辑/解析」 | `id` |
| J25 | `/login` | 目标页面 | 登录成功回跳 | `redirect` 原路 |

### 4.3 导航挂载策略

- 用户端侧边栏 8 项**保持不变**（仪表盘/课程/我的课程/错题/问答/社区/成就/个人）；6 个新页面**不占导航**，入口放 `/me` 功能列表 + 业务上下文（J2/J3/J6/J9/J10/J16 等）。
- 管理端 6 菜单不变；RAG 上传在 `/admin/rag` 内新增 Tab（P18），不改导航结构。
- 面包屑：管理端沿用 `CRUMB_LABELS` 模式，新增 `课程详情 / 题目详情` 两级。

---

## 五、HTML 效果图审核流程产出物规范

> 流程（edu-data 决策⑤/原则 5 强制）：**每页先 HTML → 用户审核 → 用户给设计图 → 改 HTML → 通过 → 写 React**。顺序（重构规划 §6.3）：课程中心→课程详情→我的班次→优惠券→订单/支付→退款→收藏→工单/申诉→管理端课程→管理端题库→RAG 上传→其余。

### 5.1 目录与命名

```
test-reports/fe-html/            ← 根目录（本次新建；若已存在则追加）
├── courses.html                 # /courses
├── course-detail.html           # /courses/[seriesId]
├── my-cohorts.html              # /my-courses（enrollments 语义）
├── learning.html                # /learning/[seriesId]/[sessionId]
├── practice.html                # /practice/[mode]
├── me.html                      # /me
├── coupons.html                 # /coupons
├── orders.html                  # /orders
├── order-pay.html               # /orders/[orderId]/pay
├── refunds.html                 # /refunds
├── tickets.html                 # /tickets
├── favorites.html               # /favorites
├── admin-courses.html           # /admin/courses
├── admin-course-detail.html     # /admin/courses/[seriesId]
├── admin-questions.html         # /admin/questions
├── admin-question-detail.html   # /admin/questions/[id]
├── admin-users.html             # /admin/users
├── admin-rag-upload.html        # /admin/rag（上传 Tab）
├── dashboard.html               # /dashboard（MOCK→真实适配）
└── _audit.md                    # 全页审核台账（可选聚合）
```

**命名规则**：`kebab-case`；路由去 `/` 前缀与动态段占位（`[seriesId]→detail` 语义后缀）；页面=页面文件名，同名覆盖前先归档。

### 5.2 单文件内容要求（每个 `.html` 必须包含）

1. **文档头注释块**（`<!-- -->`）：页面名 / 对应路由 / 对应 FR 编号（edu-data-plan §6.3 序号）/ 依赖 API 列表 / 状态机枚举 / 版本号。
2. **`<meta charset="utf-8">` + 内联 `<style>`**：**全部样式内联于 `<style>` 标签**（design-tokens 语义 token 展开为 hex：primary `#4F46E5`、bg `#FFF`、border `#E2E8F0`、语义色等；字号/间距/圆角按 §一）；**无任何外链**（无 CDN/无字体外链，用系统字体栈）→ 双击即可独立打开。
3. **完整交互态**（每页必含，用 `class` 前缀标注 + 注释说明）：
   - 静态成功态（默认）
   - `loading` 骨架态（skeleton 块，灰色占位 + 动画可选）
   - `empty` 空态（EmptyState 组件形态）
   - `error` 错误态（ErrorState：message + 重试按钮形态）
   - hover / active / disabled / focus（`:hover` `:focus-visible` 伪类写在 `<style>` 内）
   - 关键交互模拟：弹窗（隐藏 div + `<input type="checkbox">` hack 或注释说明）、展开面板、下拉
4. **模拟数据**：`<!-- DATA: {json} -->` 注释块内嵌该页 mock 数据（snake_case 字段、含多状态样本：如订单 pending/paid/refunded 各一行）。
5. **状态标注**：页面内不可交互元素的说明用 `<!-- 说明 -->` 注明（如「此处为轮询展示，5s 刷新」）。
6. **内联 `<script>` 可选**：仅用于演示交互态切换（如点击按钮切换 loading/empty），**禁止依赖任何框架**。

### 5.3 审核轮次记录（写入 HTML 头部注释 + 页面级说明）

```
<!--
  AUDIT LOG:
  [2026-08-16 R1] 初稿提交 → 用户意见：①价格区不够醒目 ②班次卡片需显示剩余席位 → 状态: REVISING
  [2026-08-17 R2] 已按意见修改（价格 ¥ 加粗 tabular-nums；班次卡加容量进度）→ 状态: APPROVED
-->
```

- 轮次编号 `R1/R2/...`；状态机：`DRAFT → SUBMITTED → REVISING → APPROVED`（或 `REJECTED`）。
- 每轮意见逐条编号（`① ② ③`），修改点在 HTML 内以 `<!-- FIX-R2-① -->` 就近标注。
- **通过标准**：APPROVED 且无 `REJECTED` 遗留项 → 才允许 fe-implementer 写 React；React 实现完成后按 HTML 对照走 visual-acceptance（§六截图集合）。

### 5.4 审核通过的移交清单

HTML 文件 + 审核结论 → fe-spec-writer 出组件契约（§三 C1~C21）→ fe-implementer 实现 → fe-styler 用 tokens 语义 class 替换内联 hex → fe-tester 补测试。

---

## 六、响应式与无障碍

### 6.1 断点矩阵（每页验收）

| 页面类型 | 375 | 768（双态） | 1024 | 1280 | 1440 |
|---|---|---|---|---|---|
| 用户端列表（课程/收藏/券） | 单列 | 2 列 | 3 列 | 3~4 列 | 内容 max-w |
| 详情页（课程/题目） | 单栏堆叠 | 单栏 | 双栏（2/3+1/3） | 双栏 | 双栏 |
| 学习页 | 视频全宽+大纲抽屉 | 同左 | 双栏 | 双栏 | 双栏 |
| 管理端表格 | 横向滚动容器（`overflow-x-auto`） | 同左 | 全宽 | 全宽 | 全宽 |
| 侧边栏 | 抽屉（md 以下） | 抽屉/固定临界 | 固定 | 固定 | 固定 |

- 表格在移动端**不裁剪列**：容器横向滚动 + 首列 sticky；操作列收进 DropdownMenu。
- 弹窗：375 下 `w-full max-w-[calc(100vw-2rem)]`；表单两列在 sm 以上。
- 200% 缩放（等效 1440→720）：无水平溢出、无遮挡、无断行（visual-acceptance §6）。

### 6.2 焦点管理

- 全站交互元素 `focus-visible:ring ring-ring`（indigo-500，对比度 ≥3:1 可见）。
- Dialog/抽屉：打开聚焦首元素（关闭按钮或标题）、**Escape 关闭 + 焦点归还触发元素**、`role="dialog" aria-modal="true"`；开启时背景 `inert`（AppShell 已有实现，Dialog 组件沿用 Base UI 语义）。
- 抽屉：打开聚焦首菜单项；关闭归还 openBtn（现有行为保留，新页面不得破坏）。
- 表单：label 绑定（`htmlFor`/`aria-labelledby`）；错误信息 `aria-describedby` 关联；Select/Combobox 键盘导航（Base UI 自带，禁用 `pointer-events` hack）。

### 6.3 ARIA 与语义

- 页面结构：`header/nav/main/aside/footer` 语义标签；每页唯一 `h1`；区块标题 `h2/h3` 层级不跳档。
- 表格：`<table>` + `<caption class="sr-only">`（DataTable 内建）；排序按钮 `aria-sort`。
- 状态徽章：装饰性 `aria-hidden="true"` + 文本本身承载语义（不依赖颜色传达状态——StatusBadge 必须带文字 label，**禁止纯色块徽章**）。
- 进度条：`role="progressbar" aria-valuemin/max/now`（ui/progress 已有）。
- 轮询/倒计时：更新时 `aria-live="polite"` 提示（toast 已有 role）；任务进度变化广播。
- 收藏心形：`aria-pressed`（切换按钮语义）；「领券」「报名」按钮带明确文本（禁图标-only 无 aria-label）。
- 弹窗确认（ConfirmDialog）：`aria-describedby` 描述 + 焦点陷阱。

### 6.4 reduced motion

- `globals.css` 已有全局 `@media (prefers-reduced-motion: reduce)`（动画/过渡 0.01ms）——**新组件不得覆盖**；新动画一律 CSS transition（≤200ms），禁止 JS 驱动的入场动画（除非 `matchMedia('(prefers-reduced-motion: reduce)')` 分支禁用）。
- 抽屉滑入/进度条动画在 reduced motion 下直接显隐。

### 6.5 对比度（WCAG 2.2 AA，light 唯一）

| 检查对 | 判定 |
|---|---|
| 主按钮白字/indigo-600 | ≥4.5:1（达标） |
| 正文 foreground/白 | ≥4.5:1 |
| muted-foreground(slate-500)/白、slate-100 | ≥4.5:1（达标） |
| 状态色（success/warning/destructive）文字/浅底 | ≥4.5:1；大文字/图标（≥18.66px 或粗体 14px）≥3:1 |
| 焦点环 indigo-500 | 可见性 ≥3:1 |
| 语义状态传达 | 徽章必须 颜色+文字 双通道（禁止仅颜色） |

- 验收：每页 HTML 审核 + React 实现后，Playwright 截图 375/768/1024/1280/1440 × 成功/空/错误三态（截图命名沿用 `{page}-{viewport}{-hc|-200pct}.png`，`-dark` 全部 N/A）。

---

## 七、机器可读摘要（供 fe-* 消费）

```
techStackConfirmLine: Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router
  （= frontend-stack.json 逐字一致；edu-frontend/CLAUDE.md 无前端章节 → 以 frontend-stack.json 为准，无 CONFLICT 项）
designTokensSource: .claude/specs/frontend/tokens/design-tokens.json（已存在，fe-task00 创建，本重构沿用只读；
  chart-1..5 中性灰维持，图表色板见 §1.7 —— 属补全，非改写）
htmlAuditDir: test-reports/fe-html/（本次新建，18 页 + _audit.md）
apiEnvelope: 成功 {code:0,message:"ok",data} / 失败 {code:<字符串>,message,data:null} → api-client 成功态解包
fieldConvention: snake_case（edu.sql 列名权威，删除全部别名兜底与 MOCK fallback）
authGuard: 用户端 ProtectedRoute / 管理端 AdminGuard（仅 admin）
stateConventions: order/payment/refund/ticket/coupon/enroll 状态机枚举见 §二各页 + §三 3.3 映射表
componentBaseline: ui 现有 19 个（avatar..toast）；新增 C1~C21（DataTable/Pagination/StatusBadge/Stepper/Uploader/Timeline/EmptyState/ErrorState/FilterBar/ConfirmDialog/DropdownMenu/Select/Accordion/PriceText + 业务卡）
pagePlan: 6 新（coupons/orders/order-pay/refunds/tickets/favorites）+ 12 重构（courses/course-detail/learning/my-cohorts/practice/me/admin-courses×2/admin-questions×2/admin-users）+ RAG 上传 + dashboard 适配 = 20 处，HTML 审核顺序见 §5.1
```

---

## 交付统计

- 章节：前置校验 + 设计令牌 + 页面规范（20 处/18 页 + 2 适配）+ 组件清单 + 跳转地图 + HTML 审核流 + 响应式无障碍 + 机器摘要，共 8 部分（覆盖一~七全部要求）
- 页面规范：6 新 + 12 重构 + RAG 上传 + dashboard 适配，每页含 ASCII 布局草图 + 组件清单 + 交互说明 + 状态流转 + 数据依赖
- 设计令牌：主色 indigo 8 档 / 中性 slate 8 档 / 语义色 6 档（oklch 权威 + hex 对照）/ 图表 8 色 / 字号 9 级 / 间距 6 档 / 圆角 7 档 / 阴影 2 个 / 渐变 3 个 / 断点 5 级
- 组件：现有 19 个复用 + 新增 21 个（含契约初版）
- 跳转表：25 条（J1~J25）
- 状态机：8 组枚举映射（订单/支付/退款/券/报名/课次/转码/工单/审核/系列/交付）

> 无文件被修改（只读调研）。如需落盘为 `前端重构设计规范_edu-data_v1.0.md` 或拆分出 `design-tokens` 扩展 JSON，请指示后执行。
