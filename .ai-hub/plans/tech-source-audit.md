# tech-source-audit：B 批次 admin 域框架选型审计（Refine vs react-admin）

> 任务来源：dev-plan-reshape-a.md taskB0（批判承接核对表 C15/C17 落点，P3' 前提"冻结前 B 页面 task 不得开工"）。
> 方法：TT tech-source-audit 结构（选型 = 来源 + 自我批判 + 原因），六维对比 + DEMO spike 实测。
> 审计日期：2026-09-06（全部 URL/数据访问日期均为当日，`npm view`/`curl` 实测注册表与 GitHub API）。
> 审计者：独立调研 agent（零生产代码）。Spike 产物在系统临时目录 `C:\Users\Administrator\AppData\Local\Temp\b0-spike\`，不入 git。

---

## 0. 结论先行（供编排者快速冻结）

**推荐 Refine v5（`@refinedev/core@5.0.12` headless core，不引 UI 绑定包）。**

一句话理由：本项目 React 侧既有栈是 **Next.js 16 App Router + React 19.2.8 + @tanstack/react-query 5.101.4**（`edu-frontend/package.json:17,25-26`），Refine core v5 内部数据层就是 TanStack Query v5（peer 依赖 `@tanstack/react-query: ^5.81.5`，实测 `npm view`，2026-09-06）——选 Refine 等于把 C17 要做的 TanStack 数据层直接复用为框架数据层，数据层不分裂；且 Refine 有官方 Next.js 路由绑定 `@refinedev/nextjs-router@7.0.5`，headless 无 UI 观点使糖果 token 直接落在自写组件上，PARITY_CHECK（P6'-③）可行性最高；spike 实测包体积 118.79 kB gzip vs react-admin 294.60 kB gzip（2.48 倍）。

react-admin 不是输家：它维护节奏更稳（2026-09-04 仍在发版，10 年项目）、组件优先上手最快（spike 45 行一次通过零卡点）。若团队更看重"开箱即用的成熟后台壳"且接受 MUI 视觉，它是合理备选。输掉本案的决定性三条是：①`<Admin>` 自带 react-router 路由树与 Next.js App Router 嵌套冲突（无官方 Next 绑定）；②MUI 强依赖与糖果 token 冻结+截图 diff 的验收门正面冲突；③体积 2.48 倍。

---

## 1. 候选来源（版本快照 2026-09-06）

| 候选 | 版本 | 来源 | 许可 |
|---|---|---|---|
| Refine | @refinedev/core 5.0.12 + @refinedev/react-router 2.0.4（spike 用法：仅 core，无 UI 绑定） | https://github.com/refinedev/refine （npm registry 实测 2026-09-06） | MIT（`npm view @refinedev/core license`） |
| react-admin | react-admin 5.15.3（含 ra-ui-materialui + @mui/material 强依赖） | https://github.com/marmelab/react-admin （npm registry 实测 2026-09-06） | MIT（核心）；企业版另收费 https://marmelab.com/ra-enterprise |

## 2. 六维对比（证据均带访问日期）

### ① 维护活跃度 —— react-admin 优，Refine 有降速信号（本次审计最大风险项）

| 指标 | Refine | react-admin |
|---|---|---|
| GitHub stars | 35,635 | 26,923 |
| 仓库最近 push | **2026-06-05（距今 ~3 个月）** | **2026-09-04（距今 2 天）** |
| 最近 release | @refinedev/core@5.0.12，2026-04-02（距今 5 个月） | v5.15.3，2026-09-04；v5.15.2，2026-09-01 |
| 建仓时间 | 2021-01 | 2016-07（10 年） |
| 数据源 | https://api.github.com/repos/refinedev/refine + /releases （2026-09-06 访问） | https://api.github.com/repos/marmelab/react-admin + /releases （2026-09-06 访问） |

**自我批判**：Refine 母公司 2025 下半年起重心转向 AI 工具（refine.new / Refine agents，https://refine.dev/ ，2026-09-06 访问），core 包 5 个月未发版是客观事实，"35k stars"不能对冲"发版降速"。选 Refine 必须接受"框架层可能进入低频维护期"的前提；缓解策略见 §5。react-admin 2026-06-24 → 09-01 之间也有约 2 个月空窗，但历史节奏整体致密。

### ② 生态与文档质量 —— react-admin 优

- react-admin：10 年积累，官方 Demo 库、模块生态（ra-realtime 等）与企业版支持（https://marmelab.com/ra-enterprise ，2026-09-06 访问）；文档以组件配方为主，可直接复制。spike 中 45 行一次构建通过、零 API 断层，文档-代码一致性实测良好。
- Refine：文档结构清晰（headless 教程+各 UI 库绑定文档），但 spike 第一个构建就撞上**文档/习惯用法与 v5 实际导出不一致**（`routerProvider` 由具名导出改为 default 导出，见 §4 卡点1）——v5 刚完成现代化改造（React 19 + TanStack Query v5，https://refine.dev/blog/refine-v5-announcement/ ，2026-09-06 访问），文档滞后于包导出。两份官方对比文均为利益相关方所写（https://refine.dev/blog/react-admin-vs-refine/ 与 https://marmelab.com/blog/2023/07/04/react-admin-vs-refine.html ，2026-09-06 访问），只可参考论点不可采信结论；marmelab 版有一句中立公允的定性：差异核心在"代码量分布"——react-admin 组件优先，Refine headless/hook 优先。

### ③ 与本项目约束的适配（响应壳解包 + 分页壳映射 + Next.js 宿主）—— Refine 优，此项权重最高

**壳适配本身两边成本相同（都是 ~10 行 unwrap）**，实测两边 dataProvider 同构：

```
getList: 后端 {code:0,message,data} → 解包 data → 分页裸 DTO {total,page,page_size,items}
  → Refine:   { data: d.items, total: d.total }          （参数 {current,pageSize}）
  → react-admin: { data: d.items, total: d.total }        （参数 {pagination:{page,perPage}}）
```
真正的隐藏工作量差异在**宿主与主题**：
- **Next.js 宿主**：Refine 有官方绑定 `@refinedev/nextjs-router@7.0.5`（npm 实测 2026-09-06）；react-admin 的 `<Admin>` 内嵌 react-router v6/v7（实测其 dependencies 含 `react-router: ^6.28.1 || ^7.1.1` 与 `react-router-dom`）并自渲染整棵路由树，官方无 Next.js 集成包，只能作为 client-only 孤岛挂进 App Router 页面，内部路由与 Next 路由器并存（此项未做 Next 嵌套 spike，属架构推断，置信度 medium——见 §7 自我批判）。
- **糖果 token 主题化（⑥合并看）**：react-admin 列表/布局组件全部落在 MUI（实测 dependencies 强依赖 `@mui/material ^5||^6||^7||^9` + `@emotion/*`）——token 必须翻译成 emotion/MUI Theme 覆盖层，Material 观感与糖果设计有底盘差异，P6'-③ 的 PARITY_CHECK（token 冻结+截图 diff）通过风险高；Refine core 无任何 UI 观点，糖果 token 直接写在我们自己的组件上，框架只供数据/状态 hook，PARITY_CHECK 风险最低。
- **与 taskB2（C17 承接）的数据层关系**：Refine core 的 peer 依赖就是 `@tanstack/react-query ^5.81.5`，与既有 `@tanstack/react-query ^5.101.4`（`edu-frontend/package.json:17`）同库同 major——QueryClient 可注入复用，401 刷新收敛在同一个 queryClient 单例上做。选 react-admin 则项目里会同时存在 TanStack Query（用户端）与 ra-core 自研 dataFetch 状态机（admin 域）两套数据层，C17"消灭手写客户端"的收敛目标被腰斩。

### ④ 学习曲线 —— react-admin 优（组件优先半天出活）；Refine 概念面更多但与既有 TanStack 知识重叠

react-admin：`<Admin><Resource list={X}/></Admin>` 即得完整后台（spike 45 行零卡点佐证）。Refine：需要理解 resources/dataProvider/routerProvider 三概念（spike 撞卡点1 佐证）。但本团队已有 TanStack Query 使用计划（taskB2），Refine 的 useList/useTable 缓存语义与之同源，有效学习成本低于是表观差距。**自我批判**：此维度是"第一天效率"，对长期维护权重应低于③；不能因上手快选型。

### ⑤ 包体积 —— Refine 优（实测应用级数字）

同一 mock 应用（列表页+壳解包 dataProvider）`vite build` 实测（2026-09-06，vite 6.4.3）：

| | Refine spike | react-admin spike |
|---|---|---|
| 产物 JS（gzip） | **118.79 kB** | **294.60 kB（2.48×，触发 >500kB chunk 告警）** |
| 产物 JS（min） | 363.33 kB | 908.97 kB |
| transform 模块数 | 299 | 2324 |
| 构建耗时 | 1.97s | 6.41s |
| lockfile 包数 | 155 | 232 |

参考（包级，bundlephobia API，2026-09-06 访问）：@refinedev/core@5.0.12 = 46.8 kB gzip；react-admin@5.15.3 = 384.9 kB gzip（12 deps）。应用级数字为准，包级仅佐证。

### ⑥ 与糖果设计 token 的主题化能力 —— Refine 优（见 ③）

react-admin：MUI Theme 覆盖层翻译 token，Material 底盘与糖果风有先天观感差，且 emotion 运行时 CSS-in-JS 与 Next 16 RSC 生态有额外摩擦。Refine headless：0 UI 约束，token 直落自写组件，与既有 fe-html 视觉基准（AGENTS.md：视觉冻结）一致性最高。**代价**：Refine 不送你任何 UI——admin 布局壳/表格/按钮全要自己写（这正是 dev-plan taskB3 已规划的工作，不算额外成本）。

## 3. DEMO spike 实测记录（2026-09-06，系统临时目录，非工作区）

- 环境：Windows 10 / node v24.18.0 / npm 11.16.0 / vite 6.4.3；`npm ping` PONG 1069ms（registry 可达）。
- 位置：`C:\Users\Administrator\AppData\Local\Temp\b0-spike\{refine-app,reactadmin-app}`（`/tmp` 经 cygpath 确认映射系统 Temp）。
- 方式：手写最小 package.json + 单文件 `src/main.tsx`（未用 npm create vite 交互式脚手架，保证两版除框架外逐字节同构可比）。
- 内容：同一 users 列表页（表格+分页）+ 自定义 mock dataProvider（含 `{code:0}` 壳解包 + `{total,page,page_size,items}`→框架分页映射 + 401 跳登录）。

| 实测项 | Refine | react-admin |
|---|---|---|
| 手写源码行数（main.tsx） | 59 行 | 45 行 |
| manifest 直接依赖 | 5 prod + 2 dev | 3 prod + 2 dev（但 react-admin 单包拖入 MUI/emotion/react-router/react-hook-form/ra-* 7 个直接依赖） |
| lockfile 安装包数 | 155 | 232 |
| `vite build` | 通过（1 次卡点后通过） | 一次通过 |
| `vite preview` 拉起 | HTTP 200 | HTTP 200 |
| 构建卡点 | 2（见下） | 0 |

**卡点实录（Refine）**：
1. `@refinedev/react-router@2.0.4` 的 `routerProvider` 已改为 **default 导出**（其 `dist/index.d.ts:1`：`export { routerProvider as default }`），按社区惯用的具名导入 `import { routerProvider }` 构建报错：`"routerProvider" is not exported by "node_modules/@refinedev/react-router/dist/index.mjs"`。文档滞后于 v5 改版。
2. esbuild postinstall 被 npm allow-scripts 策略拦截（`npm warn allow-scripts esbuild@0.25.12 (postinstall: node install.js)`），vite 仍构建成功（降级路径可用），但部署机若策略更严需预批——登记为环境注意项，非选型否决项。

**诚实边界（不伪造）**：spike 验收口径 = `npm install` 成功 + `vite build` 通过 + `vite preview` HTTP 200；**浏览器内 DOM 渲染未验证**（项目硬性守则禁用 Playwright，本 agent 无浏览器验收手段）。spike 仅覆盖列表页；增删改写路径的 dataProvider（create/update/delete/getOne）未实测，按同构推算每资源 +30~50 行（见 §7 自我批判）。

## 4. 可证伪判据（冻结后由 taskB3 验收回查）

1. **C15 代码量判据**：静态基线 `edu-frontend/public/admin-users.html` = **642 行**（wc -l 实测，2026-09-06）→ 1/3 红线 = **214 行**。spike 中 Refine 列表页含 dataProvider 仅 59 行；taskB3 成品（布局壳+筛选+启停+TanStack/refine 接线）若 >214 行，判本审计推荐被证伪，回滚选型（dev-plan finding1 的处置约定）。
2. **体积判据**：taskB3 产物若 admin 域新增 gzip 体积 >200 kB（本审计实测 Refine 路线基线 118.79 kB + 业务增量），说明实际引入了 MUI 级依赖，判偏离 headless 决策。
3. **壳适配判据**：dataProvider 壳解包+分页映射代码量 ≤30 行/资源；超出即说明映射层设计错误。
4. **维护风险判据**：若 @refinedev/core 自 2026-09 起连续 6 个月零发版且出现阻塞级 issue 无人响应，触发备选预案评估（§5）。

## 5. 推荐 + 风险缓解（选型=原因）

**推荐 Refine v5 headless core。决策依据按权重排序：**
1. **数据层统一（权重最高）**：core 即 TanStack Query v5，与既有 5.101.4 同库，taskB2 的 401 收敛/queryClient 单例与框架数据层合流，C17 彻底落地；react-admin 会制造第二套数据层。
2. **宿主适配**：官方 `@refinedev/nextjs-router@7.0.5`；react-admin 与 Next.js App Router 无官方集成路径。
3. **糖果 token/PARITY_CHECK 可行性**：headless 无 UI 观点；react-admin 的 MUI 底盘与 P6'-③ 验收门冲突。
4. **体积**：118.79 vs 294.60 kB gzip（应用级实测）。
5. **维护活跃度反向项已知的接受**：见 §2①，Refine 发版降速是本案最大风险，被 1-3 压过，理由：headless 路线下框架面（dataProvider/routerProvider 接口）极薄，自写 UI 不依赖 Refine 组件库，最坏情况的替换成本 = 重写一个 ~百行 dataProvider 文件 + hook 换 TanStack Query 原生 hook（两者同源），**无 UI 锁定**。react-admin 的优势（活跃/生态/开箱）在我们"必须自绘糖果 UI"的约束下大部分被 neutralize。

**taskB2 范围修订提示（供编排者）**：选 Refine 后，taskB2 的"TanStack Query 骨架"应表述为"Refine 注入共享 queryClient + 401 interceptor 收敛"，避免出现 refine 数据层与裸 TanStack 双轨。

## 6. 备选预案

- **react-admin**：若用户否决 Refine（如更看重维护方 stability），按 spike 45 行路线走，代价=接受 MUI 主题翻译层 + 双数据层 + 294.6 kB gzip；任务 B3 验收判据不变。
- **不用框架，纯 TanStack Query 手写**：即"维护降速"最坏情形的自然退化路径，DataProvider 文件作废即可，UI 与数据 hook 全部自有——这是 Refine headless 路线的隐性保险，也是它相对 react-admin 的退出成本优势。

## 7. 审计自我批判（本审计自己的弱点，防"审计即真理"）

1. spike 未含写路径（create/update/delete/getOne），写路径壳适配是推算不是实测；两框架写路径适配成本差异未度量（大概率同构，置信度 medium）。
2. react-admin"与 Next.js 冲突"是架构推断（内嵌 react-router），未做 Next 嵌套 spike；若走 react-admin 路线需先补该 spike。
3. 1/3 代码量对比口径不完全对等：642 行 HTML 含 CSS+标记+脚本，React 版 CSS 走全局 token 不计——判据偏向 React 路线，但它本身就是 C15 批判原文口径（dev-plan 批判承接核对表），保持口径一致优先于口径公平。
4. bundlephobia 数字为包级（tree-shaking 前形态），仅作佐证；结论采用应用级 build 实测。
5. Refine v5 发布约一年（2025-09 前后），v5.x 自身的长期 patch 轨迹样本还短；本轮发版降速观测窗口仅 5 个月，存在"暑假式低谷"误读可能，§4-4 的触发判据即为对此的纠偏机制。

## 8. 独立复核记录（2026-09-06，复核 agent）

本审计为同一任务先后两段完成，第二段对第一段全部可机验声称做了独立复核，**全部通过**：

| 声称 | 复核手段 | 结果 |
|---|---|---|
| spike 源码 59/45 行 | `wc -l` 两份 main.tsx | 59/45 ✅ |
| lockfile 155/232 包 | `grep -c '"resolved":'` 两份 package-lock.json | 155/232 ✅ |
| build 产物 363.33/908.97 kB min | `ls -la dist/assets/` 实际字节数 363,327 / 908,971 | ✅ |
| gzip 118.79/294.60 kB（比 2.48×） | `gzip -c | wc -c` = 118,392 / 293,827 字节，比值 2.482 | ✅（±0.4% 为 vite 报告口径与系统 gzip 压缩级别差） |
| @refinedev/core@5.0.12 / react-admin@5.15.3 | `npm view`（2026-09-06） | 5.0.12 / 5.15.3 ✅ |
| TanStack peer `^5.81.5` | 读 spike node_modules 内 @refinedev/core/package.json peerDependencies | ✅ |
| GitHub pushed_at 2026-06-05/2026-09-04、stars 35,635/26,923 | api.github.com 实时（2026-09-06） | 逐字吻合 ✅ |
| 工作区声称：edu-frontend next16/react19.2.8/@tanstack 5.101.4、admin-users.html 642 行 | 读 package.json:17,24-26 + `wc -l` | ✅ |

结论：§0 推荐（Refine v5 headless core）所依据的事实底座全部可复现，可进入 B0 选型冻结。
