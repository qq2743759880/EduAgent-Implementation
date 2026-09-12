# taskB0 完成报告：Refine vs react-admin 选型审计

> 日期：2026-09-06。零生产代码（未改任何 .py/.html/.js）。未 git commit（按守则留给编排者）。
> 交付物：`.ai-hub/plans/tech-source-audit.md`（§8 为本轮独立复核记录）。

## 1. 做了什么

1. 六维审计（维护活跃度/生态文档/响应壳适配/学习曲线/包体积/糖果 token 主题化）全部落档，证据带 URL + 访问日期（2026-09-06）。
2. DEMO spike 实测完成于系统临时目录 `C:\Users\Administrator\AppData\Local\Temp\b0-spike\{refine-app,reactadmin-app}`（不入 git）。
3. 本轮对全部可机验声称做独立复核（npm view / GitHub API / wc -l / gzip 实测），复核表见审计文档 §8。

## 2. 资产消费证据段

| 消费的资产 | 用途 | 证据 |
|---|---|---|
| `.ai-hub/plans/dev-plan-reshape-a.md` taskB0 GWT + 批判承接核对表 C15 行 | 审计范围（六维+spike+可证伪判据）与 1/3 代码量红线 | 文档 §4 判据 1 直接引用 642 行/214 行红线 |
| `.ai-hub/plans/reshape-a-技术批判.md` C15/C17 | 审计动机与"双数据层"批判视角 | 审计 §2③、§5-1 回应 C17 数据层收敛 |
| `edu-frontend/package.json:17,24-26` | 结论核心依据：既有栈 Next16+React19.2.8+TanStack 5.101.4 | 复核 grep 实测吻合 |
| `edu-frontend/public/admin-users.html`（642 行） | C15 可证伪判据基线 | wc -l 实测 642 |
| TT tech-source-audit 结构（选型=来源+自批判+原因） | 文档骨架 | 审计 §1 候选来源 / §2 六维含每维"自我批判" / §5 推荐+原因 |
| 后端响应壳/分页壳（AGENTS.md 契约） | spike dataProvider 壳解包设计 | refine-app main.tsx:9-31 实装 {code:0} 解包+{total,page,page_size,items} 映射 |

## 3. Spike 实测数字（复核后终值）

| 项 | Refine | react-admin |
|---|---|---|
| 手写源码行数 | 59 | 45 |
| lockfile 包数 | 155 | 232 |
| 产物 JS gzip | 118,392 字节（vite 报告 118.79 kB） | 293,827 字节（vite 报告 294.60 kB）＝ 2.48× |
| 产物 JS min | 363,327 字节 | 908,971 字节 |
| 构建卡点 | 2（routerProvider default 导出；esbuild postinstall 被 allow-scripts 拦截） | 0 |

**SPIKE 未延期**（npm 网络可用，`npm ping` PONG）。诚实边界：浏览器内 DOM 渲染未验证（项目守则禁 Playwright，无浏览器验收手段）；写路径 dataProvider 未实测。

## 4. 结论（供 B0 冻结）

**推荐 Refine v5 headless core（@refinedev/core 5.0.12）**，理由按权重：①数据层即 TanStack Query v5（peer `^5.81.5` 实测），与既有 5.101.4 同库，C17 收敛不分裂；②官方 Next.js 路由绑定，react-admin 无；③headless 与糖果 token/PARITY_CHECK 验收门无冲突；④体积 2.48× 优势。已知反向项：Refine 发版降速（core 最近 release 2026-04-02，repo push 2026-06-05），已被"无 UI 锁定、退出成本低"缓解；备选 react-admin 预案留档（审计 §6）。

## 5. 自检发现

1. 本任务分两段完成（第一段产物 tech-source-audit.md 落盘于 16:16，两份完成报告缺失）——第二段没有轻信既有文档，对全部数字做了独立复核后追加 §8 复核记录。发现并修正的口径差：系统 gzip 实测 118,392/293,827 字节 vs 文档 vite 报告值差 ~0.4%，已在 §8 标注为压缩级别口径差，不影响 2.48× 结论。
2. 审计文档 §2③ 自我批判已声明：react-admin 与 Next App Router 冲突是架构推断（未做嵌套 spike）；若用户否决 Refine 转投 react-admin，需先补该 spike。
3. spike 的 react 依赖是 18.3.1 而生产是 19.2.8——Refine peer 声明同时支持 18/19（`npm view` 复核），风险低，但 taskB3 实施时应在真实 Next 16 宿主复验一次（登记给 B3）。
4. spike 产物目录保留在系统 Temp 未删，供编排者抽查；按守则未放入工作区、未入 git。
