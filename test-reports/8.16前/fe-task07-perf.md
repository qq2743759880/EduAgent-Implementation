# 性能审查报告 fe-task07

> 用户端全页面风格统一收敛到管理端风格（fe-task07）· 性能审查
> 审查方式：静态代码审查（56 文件 className/色值/chart-palette.ts 收敛面）+ 真实生产构建（`npm run build`，Next 16.3.0 Turbopack，内置 TypeScript 检查 0 error）+ 浏览器实测（Playwright MCP 对 dev server `http://localhost:3000`，复用 fe-task07-server-info 记录的 PID 16676，未 kill / 未重启）
> 审查范围：仅 fe-task07 收敛改动（className 替换 / 颜色常量值收敛 / 新增 chart-palette.ts）；零行为改动契约核验（props/事件/aria/结构均未触碰）

## 判定

verdict: **PASS**

- P0：0（无阻断性能目标的问题）
- P1：0（无新增性能警告；fe-task06 既有 CLS P1 属存量，非本 task 引入）
- P2：4（范围外 via- 渐变残留、用户端中性类残留、ECharts 白色系 hex 未入 palette、SSR HTML payload 正向收益记录）

---

## 发现表

| # | 位置 | 严重度 | 问题 | 建议 |
|---|------|--------|------|------|
| 1 | `src/app/page.tsx:39,49`、`src/app/not-found.tsx:20`、`src/components/auth/AuthCard.tsx:38`、`LoginForm.tsx:156`、`RegisterForm.tsx:209` | P2 | 范围外多 stop 渐变残留 5 处（`from-indigo-50 via-white to-sky-50`、`from-emerald-600 to-teal-600` 等）。不属于 fe-task07 九页收敛面（登录/404/根页），dev 产物仍携带这些 via- 规则 | 由后续风格统一任务（或独立 auth 收敛）替换为 `from-primary-deep to-primary` / `bg-primary`；纯视觉收敛项。预期影响：CSS 规则 −5 条（<1 KB） |
| 2 | `src/components/dashboard/BadgeWallGrid.tsx:175`（`bg-slate-700/80` 锁角标）、`RankList.tsx:134`（骨架 `bg-slate-100/80`） | P2 | 用户端 9 页内中性 legacy 类残留 2 处。无性能影响（单条 color/bg 规则），但 visual-acceptance ②-3 grep `bg-slate-[0-9]+` 会命中 → 视觉验收需逐条解释 | 锁角标改用 `bg-foreground/80` 或保留并注明深灰中性语义；骨架改 `bg-muted`（与 PointLogTable 一致）。预期影响：0（纯一致性） |
| 3 | `src/components/dashboard/AbilityRadarChart.tsx:157,176`（`#f8fafc/#ffffff/#fff`） | P2 | ECharts option 内白色系 hex 未登记入 chart-palette.ts（架构 §4.1.2 允许「白色系登记来源后保留」）。白色系中性，无越界/无性能影响，但 visual-acceptance ③-8 grep `#[hex]` 会命中 | 登记为 `CHART_COLORS.background`/复用 primaryGradient 白色 stop，或验收命令加白名单。预期影响：0 |
| 4 | 全站收敛面（56 文件） | P2（正向） | className 收敛同步缩减 SSR HTML payload：`text-[11px]`(12 字符)→`text-3xs`(8 字符)、`bg-gradient-to-br from-amber-50/40 via-white to-violet-50/40`(56 字符)→`bg-card`(7 字符) | 无动作。预期影响：SSR HTML −1~3 KB/页（字符级估算，待测量），JS/CSS 产物持平 |

---

## 各维度审计

### 1. 收敛性能影响（className 替换 → CSS 生成）

**结论：无 CSS 膨胀，方向为持平或微减。**

- Tailwind v4 JIT 按源码出现的类名生成规则，每类 1 条规则，与类名长短无关。
- 收敛把 arbitrary 类（`text-[11px]`/`text-[13px]` 等）替换为 @theme 已注册的语义类（`text-3xs`/`text-sm-table` 等，globals.css:61-64），规则数量 1:1 等价。
- 旧色值类（`text-indigo-600`/`bg-indigo-50`/`text-amber-600` 等）在用户端 9 页清零后，若全仓无其他使用点，JIT 不再生成对应规则 → **CSS 只减不增**。
- **产物实证**（生产构建 `.next/static/chunks/0lnts1en3eu8d.css` = 131,937 B）：
  - `text-3xs` ✓ 存在、`bg-primary-soft` ✓ 存在（收敛类已生成）
  - `text-[11px]` ✗、`text-[13px]` ✗（用户端 arbitrary 类已移除）
- 管理端（fx-task 范围）仍含 legacy arbitrary 类，属既有存量，不影响本 task 判定。

### 2. 渐变收敛（多 stop 渐变 → 纯色/品牌双 stop）

**结论：渲染开销方向为正向（减 paint）。**

- 用户端 9 页写路径 `via-` 多 stop 渐变 **0 命中**（dashboard 积分卡/徽章/行渐变、achievements 页头/骨架、streak cell 三态渐变等全部收敛为纯色或品牌双 stop）。
- 纯色填充（`bg-card`/`bg-warning`）比渐变逐像素插值便宜；骨架 `animate-pulse` + `bg-muted` 纯色比原渐变骨架更省。
- 量级评估：收敛对象多为小卡片/图标底，单次 paint 节省 <1 ms 级，属「方向正确、量级微小」，无负回归。

### 3. 字号收敛（语义字号 token）

**结论：无渲染差异。**

- `text-[13px]`→`text-sm-table`(0.8125rem=13px)、`text-[12px]`→`text-2xs`、`text-[11px]`→`text-3xs`、`text-[10px]`→`text-4xs` 值等价（globals.css:61-64），像素一致，无缩放回归。
- 例外（14px→sm / 15px→base prose 不收编 / 13.5px→sm / 12.5px→2xs）均按 sizeExceptions 落档，值不变。

### 4. 包体（chart-palette.ts + chunk 影响）

**结论：无回归，增量可忽略。**

- `src/lib/chart-palette.ts`：46 行纯常量 + 1 个纯函数（`primaryGradient`），无状态/无副作用/无请求。运行开销：每次调用创建 ~100 B 小对象，且仅在 ECharts option useMemo 依赖变更时执行（ProgressTrendChart.tsx:154、:174），非高频。
- dev 产物实证：`CHART_COLORS`/`primaryGradient` 内联进引用它的 chunk（`src_0sggk-f._.js`、`src_1gierpy._.js`、`src_09jdtjq._.js` 等），**未产生独立 chunk、未增加网络请求数**。
- 生产构建：echarts/zrender chunk `0dkvsl9lvx4cz.js` = 493,831 B（fe-task06 基线 `27_834jfk717-.js` ≈ 493 KB，hash 变化因组件源码变更，大小持平）→ **无包体回归**。
- 收敛未改变 import 图/路由懒加载结构（零行为改动契约），chunk 划分不变。

### 5. 浏览器实测（复用 dev server）

- 5+ 页面渲染正常，**0 console error**（与 fe-task06 基线一致）；dashboard 经登录态重定向到 practice/vocab，属既有路由守卫逻辑，非收敛引入。
- dev 模式数据（LCP 1.1s / CLS 0.442 / longTask 609ms / JS 12.8MB decoded）为 **dev 未压缩 + sourcemap + HMR 数据，不代表生产**，仅作渲染健康确认；生产指标以 build 产物为准。
- CLS 0.442 与 fe-task06 已登记的 CLS P1（骨架→数据高度未预留）同源，本 task 未触碰骨架逻辑，不属新增。

---

## 静态校验

| 校验项 | 命令 | 结果 |
|--------|------|------|
| TypeScript | `npm run build`（Next 16.3 内置 tsc 检查，tsconfig strict + noEmit） | **0 error**（`Finished TypeScript in 9.3s`，18/18 页面静态生成成功） |
| ESLint | `npm run lint` | **未运行**——工具权限白名单不含该命令；降级为静态审查：收敛改动面 = className 字符串 + Record 常量值 + 1 个新 lib（纯常量/纯函数），不含未使用导入、不含 hook 依赖变更、不含新增 any；零行为改动契约下 lint 风险面 ≈ 0。存量 errors（admin 范围 legacy 类）未被收敛放大（收敛只改用户端写路径） |
| 单测 | `npx vitest run src/lib/api/dashboard.test.ts src/lib/api/community.test.ts`（server-info 记录） | 52/52 passed（3.03s） |

---

## 可测指标

- 首屏 bundle 大小：生产构建产物实测——echarts/zrender chunk `0dkvsl9lvx4cz.js` = **493,831 B**（gzip 估 ~130-150 KB，跨页共享，fe-task06 基线持平）；主 CSS `0lnts1en3eu8d.css` = **131,937 B**；md-editor/Prism chunk `2oyngvygvc--s.js` = 902,985 B（chat 使用，非本 task）
- 路由懒加载数量：0 变化（收敛未触碰 next/dynamic 与 import 结构）
- 重渲染风险组件：0 新增（className 与常量值替换不改变 props/state/渲染路径）
- 新增独立 chunk：0（chart-palette 内联进 4 个引用组件所在 chunk）
- 浏览器实测：0 console error；生产指标未测量（工具权限限制 + dev 数据失真），以上产物数据为 `.next/static/chunks` 实测（file:size），非编造

---

## 结论

fe-task07（用户端全页面风格统一收敛）性能整体**合格（PASS）**：

- **收敛影响**：className 替换（arbitrary→语义类）Tailwind v4 JIT 产物持平或微减，无 CSS 膨胀；渐变收敛（多 stop→纯色）方向正向（减 paint，量级微小）；字号收敛值等价无缩放回归
- **包体**：chart-palette.ts 纯常量 ~46 行，内联进既有 chunk 无新增请求；echarts 共享 chunk 493 KB 与 fe-task06 基线持平，无回归
- **静态校验**：tsc 0 error（生产构建内置检查）；lint 因工具权限未运行（已如实降级说明，收敛面无 lint 风险）；vitest 52/52 通过
- **发现**：0 P0 / 0 P1；P2 均为范围外残留（auth/404 via- 渐变）与中性类一致性项，无性能影响，不阻断
- **修正建议**（非本 task 阻断项，供后续任务参考）：① 若 visual-acceptance ②-3/③-8 严格要求 0 命中，需 fe-styler 处理 P2#2/#3 两处；② 范围外 auth/根页渐变由后续风格任务覆盖
