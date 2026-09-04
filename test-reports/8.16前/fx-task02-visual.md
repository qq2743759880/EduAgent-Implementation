# 视觉审查报告 fx-task02（G2 管理端布局与权限）

> 执行：fe-visual-auditor（补课波·只审查+出报告，未改任何业务代码）
> 日期：2026-08-13 ｜ 基准：`.claude/specs/frontend/fx-task02/`（design-tokens.json / visual-acceptance.md / design-options.md）

## 环境

- 启动方式：复用 fe-task01 dev server（Next.js 16.3 Turbopack，PID 3780，http://localhost:3000，见 test-reports/fx-task02-server-info.md），**未重复启动**
- 登录方式：**真实登录**。注意：server-info 记载「后端未运行」已过时——实测 `http://127.0.0.1:8000` **在运行**（`POST /api/auth/login` 200）。使用测试账号 `admin / Admin@12345`（p9_step6_e2e_hit.py 文档口径）经后端取得真实 JWT，注入 localStorage `edu:auth:token` / `edu:auth:me`（roles:["admin"]）后进入管理端。AdminGuard 判定依据已读源码确认：**仅客户端检查**（`ready && token && isAdminRole(me?.roles)`，hydrate 自 localStorage，不调 `/api/auth/me`），token 有效期内不会被后端 401 拦截器清掉。
- 关键坑（记录备查）：MCP playwright 的 page 实例间 localStorage 不共享且存在 URL 漂移竞态（曾误导航至 /community），最终采用 `addInitScript` + 单脚本原子执行（登录→注入→导航→测量→截图）稳定复现。
- 截图目录：`test-reports/screenshots/fx-task02/`（7 张）
- 审查方式声明：当前模型不支持直接读图，视觉验证以 **DOM 计算样式 + 布局几何测量**（getComputedStyle / getBoundingClientRect）等效完成，覆盖颜色/字体/圆角/阴影/间距/溢出/层级；截图已保存供人工复核。**非像素级复刻**（无参考截图，规格驱动审查）。

## 截图清单

| # | 文件 | 场景 |
|---|------|------|
| 1 | `screenshots/fx-task02/admin-dashboard-1440.png` | /admin/dashboard 1440×900 首屏 |
| 2 | `screenshots/fx-task02/admin-dashboard-1440-full.png` | 1440 全页 |
| 3 | `screenshots/fx-task02/admin-dashboard-1440-dark.png` | 1440 + `html.dark`（管理端 light-only 实证） |
| 4 | `screenshots/fx-task02/admin-dashboard-375.png` | 375×812 首屏（抽屉关闭） |
| 5 | `screenshots/fx-task02/admin-dashboard-375-full.png` | 375 全页 |
| 6 | `screenshots/fx-task02/admin-dashboard-375-drawer.png` | 375 抽屉打开 + 遮罩 |
| 7 | `screenshots/fx-task02/admin-courses-1440.png` | /admin/courses 1440（共享壳抽查） |

## 发现表

### [规格违背]（挂账确认，全部已在 design-tokens.json `_hardcodedMap` / `_knownGaps` / visual-acceptance §2.2 预登记，归 fe-task00 修正——本 task 不越权）

| # | 位置 | 类型 | 严重度 | 实测 | 期望 |
|---|------|------|--------|------|------|
| V-1 | `src/components/ui/card.tsx:15`（渲染于 dashboard MetricCards） | 规格违背（卡片规范二义，GAP-03） | MUST-FIX (fe-task00) | 卡片实测 `rounded-xl bg-card ring-1 ring-foreground/10`（box-shadow 0 0 0 1px oklab(0.145/0.1)，无 border、无 shadow-sm） | 基准卡片规范：white + `rounded-xl` + `border-slate-200` + `shadow-sm`（design-guide §2.4③ / visual-acceptance §1） |
| V-2 | `edu-frontend/src/app/globals.css:58`（`:root --primary: oklch(0.205 0 0)`） | 规格违背（主色 token，GAP-01） | BLOCKER (fe-task00) | 全局 primary 为中性近黑；管理端主色视觉（激活/品牌/头像/图标 hover）全部绕开 token 走硬编码渐变（`from-slate-800 to-indigo-700` 等，实测渐变端点 lab(16.13…) / lab(32.45 49.22 -84.67) 即 slate-800/indigo-700） | `--primary` 应为 indigo-600 系 oklch(0.511 0.262 276.966) + 新增 `--color-primary-strong`（slate-800 端） |
| V-3 | `edu-frontend/src/app/globals.css:18`（`--font-sans: var(--font-sans)` 自引用） | 规格违背（字体 token，GAP-02） | BLOCKER (fe-task00) | 自引用失效，实测 body/UI 字体栈回退 `"Microsoft YaHei"`（Windows 系统字体），Geist 字体特征从未生效 | `--font-sans: var(--font-geist-sans)` |
| V-4 | `src/app/(admin)/layout.tsx:134`（版权 `text-[11px]`） | 规格违背（arbitrary 字号） | 建议 (fe-task00) | 版权区 11px arbitrary 字号 | 收口为 `text-2xs`（typography token） |

### [浏览器行为错误]

无。RBAC 未登录重定向（/admin/dashboard → /login?redirect=）、admin 放行、非 admin 拦截、抽屉开/关、遮罩关闭、面包屑、激活态切换全部实测正常（详见基准确认）。

### [已知挂账·非本 task 验收项（实证确认，供 fx-task03 收敛）]

| # | 位置 | 说明 | 来源 |
|---|------|------|------|
| W-1 | `src/components/admin/MetricCards.tsx`（dashboard 页实际渲染） | 6 张指标卡图标底 6 色并存（实测 lab 色相各异：indigo/emerald/amber/rose/sky/violet 系），含 3 枚分功能色（sky/violet/amber） | visual-acceptance §4.1（fx-task03 retro 收敛：删 sky/violet/amber，保留 indigo + emerald/rose 状态语义） |
| W-2 | `design-tokens.json radius` | tokens 记 lg=12px，实测 `rounded-xl` = **14px**（`--radius:0.625rem`=10px，`--radius-xl: calc(10px*1.4)`=14px）。全壳 14px 一致（菜单项/品牌图标/卡片），无视觉问题，仅 token 文档与实际偏差，fe-task00 收口时校准 | globals.css @theme |

### [主观建议]（不强制）

| # | 位置 | 建议 |
|---|------|------|
| S-1 | 全局 | `--radius-xl` 目前由 `--radius*1.4` 派生（14px），与 tokens 文档 12px 口径不符；建议 fe-task00 统一口径（改 token 文档或调 `--radius`）后，全站维持单一来源 |

## 基准风格确认（fe-task07 收敛基准的引用点）

以下实测值即「管理端基准视觉」的事实基线，后续 fe-task07 用户端向此收敛：

| 维度 | 实测值（1440×900 / 375×812） | 判定 |
|------|-------------------------------|------|
| 主色 | slate/indigo 单主色系：激活渐变 `from-slate-800 to-indigo-700` 白字 + shadow-sm；品牌图标/头像同源渐变；菜单图标 hover 染 indigo | ✅ 符合（无分功能多色，壳内 0 例） |
| 页面底色 | `bg-slate-100/70`（实测 oklab(0.968)/0.7） | ✅ |
| 侧边栏 | 白底 `w-64`(256px) `fixed z-40` + `border-r` slate-200 系；品牌区 h-16(64px)；版权 `text-[11px]` slate-400 | ✅ |
| 顶栏 | `h-14`(56px) sticky top-0 z-20 `bg-white/80` `backdrop-filter: blur(8px)` + border-b slate-200 | ✅ |
| 菜单项 | `rounded-xl`(14px) px-3 py-2.5 text-sm(14px)；未激活 `text-slate-600` + 图标 slate-500，hover → bg slate-100 / text slate-900 / 图标 indigo-600 / 尾箭头 opacity 0.6；激活 `aria-current="page"` | ✅ |
| 卡片 | white + rounded-xl(14px)；**现状 ring 而非 border+shadow**（V-1，fe-task00 收口后以 border-slate-200 + shadow-sm 为唯一基准） | ⚠️ 挂账 |
| 面包屑 | 「管理端」slate-500 + ChevronRight slate-400 + 末段 font-medium slate-800；truncate 防溢出 | ✅ |
| 顶栏右侧 | 头像 28px 圆渐变 + 昵称（`hidden md:inline`）+ 退出 ghost 按钮 slate-600 | ✅ |
| 响应式 | ≥md 固定侧边栏 + 主区 ml-64 + p-6；<md 抽屉（-translate-x-full→0，z-40）+ 遮罩 z-30（实测 z 序 30<40 ✓）+ 菜单按钮；内容 p-4 | ✅ |
| 交互路径 | 抽屉：Menu 开 / 遮罩点击关 / X 关（三条路径实测均正常）；退出登录 → toast + /login（代码路径确认，未实际点击避免破坏会话） | ✅ |
| 溢出 | 1440/375 双 viewport 实测 `scrollWidth == clientWidth`，无水平溢出；`min-w-0` 生效 | ✅ |
| dark | 管理端 light-only：加 `html.dark` 后壳不变（aside 仍白）——符合 tokens `colorsDark.note`（管理端当前仅 light 视觉），无亮色残留问题 | ✅（按规格） |

## 结论

- **判定：PASS**
- 阻塞项：无（fx-task02 壳范围内的视觉行为与基准声明全部一致）
- 挂账转交（不阻塞本 task，但阻塞「管理端 token 化验收」）：**V-1 卡片规范二义（MUST-FIX）、V-2 `--primary` 中性黑（BLOCKER）、V-3 字体自引用（BLOCKER）→ fe-task00**；**W-1 MetricCards 6 色 tone → fx-task03 retro 收敛**。与 visual-acceptance.md §2.2 的验收门一致：以上修正落地前，不判定「管理端 token 化视觉验收」通过（fe-task00 的门，非本 task 的门）。
- 备注：① 本报告基于 DOM 计算样式测量（模型无法读图），截图已存档供人工复核，必要时可追加像素级比对；② server-info 中「后端未运行」表述已过时，实际后端在运行（登录 200、dashboard 指标返回真实数据 916 用户），后续任务可直接真实登录，无需 fake token。
