# REPORT-THEME-GATE — 重塑底座交付报告

日期：2026-09-21（Asia/Shanghai）

分支：`feature/opt-waves`

结论：底座交付完成；现状门禁红项已作为存量债冻结，不阻塞后续逐页重塑开工。

## 0. 范围与完成定义

- 派单写明 19 个生产页，但执行时 `edu-frontend/public/*.html` 实际为 **25 页**。为避免新增页面逃逸门禁，本次盘点、冻结和全量基线均覆盖 25 页。
- 生产 HTML 零修改；`public/` 仅新增 `theme.css` 与 `assets/icons/**`。
- 交付最终主题 token/组件类、本地 Phosphor fill sprite、G3/G6-G9 五只零依赖 Node 门禁、G10 回滚剧本及全量现状基线。
- G10 本轮只交剧本；按派单要求，真实 revert/缓存清理演练留到逐页重塑收尾。

范围复验：

```powershell
git branch --show-current
git diff --name-only -- 'edu-frontend/public/*.html'
(Get-ChildItem -LiteralPath 'edu-frontend/public' -Filter '*.html' -File).Count
```

期望：分支为 `feature/opt-waves`，HTML diff 无输出，页面数为 25。

## WP1 — `theme.css` 定稿

交付：`edu-frontend/public/theme.css`。

断言：

- §7.1 基参数保留；Gate A 修订把主表面冻结为浅苔绿 `#B8D8A8`，lavender 降为辅助色，lemon 仅作暖点缀。
- `#2E2A3F`/`#B8D8A8` 对比度实测 **8.84:1**；CTA `#2E2A3F`/`#FF7A6B` 为 **5.43:1**，均满足 4.5:1。
- 9 个 §7.3 组件类齐备，并保留 `clay-light` 双密度降级能力。
- moss/lavender/sky/mint/peach/pink/lemon/coral 等表面均有同色相阴影；冻结阴影块中不存在等 RGB 灰阴影。
- 文件头逐变量说明用途，包含 sprite 使用与图标无障碍约定；包含 `prefers-reduced-motion` 和 `.page-<name>` 命名空间骨架。

复验：

```powershell
rg -n -- '--clay-moss|--cta-text|--clay-shadow-|prefers-reduced-motion|\.page-<name>|\.clay-light' 'edu-frontend/public/theme.css'
node --check 'scripts/gates/_shared.mjs'
```

浏览器解析/消费证据：

- `test-reports/gate-baseline/theme-asset-smoke.json`
- `test-reports/gate-baseline/theme-asset-smoke.jpg`
- CDP 在现有登录页运行时注入主题（未写回 HTML），结果：`themeLoaded=true`、按钮最小高度 `54px`、控制台诊断 0。

## WP2 — Phosphor 本地图标 sprite

交付：

- `edu-frontend/public/assets/icons/icons.svg`
- `edu-frontend/public/assets/icons/LICENSE.phosphor.txt`
- `docs/icon-inventory.md`

断言：

- 25 页 emoji/`svg`/`img` 使用点已逐页盘点，并区分结构图标、内容图片和数据可视化。
- sprite 冻结 **30 枚** `@phosphor-icons/core@2.1.1` fill 图标，ID 唯一；零 CDN、零图标字体。
- sprite 文件头和相邻许可证均保留 Phosphor MIT 归属；来源：[Phosphor Icons](https://phosphoricons.com)。
- 实际消费验证中 `/assets/icons/icons.svg` 返回 200，`ic-book-open` 外部 `<use>` 的 SVG 包围盒非零。

复验：

```powershell
$xml = [xml](Get-Content -LiteralPath 'edu-frontend/public/assets/icons/icons.svg' -Raw)
@($xml.svg.symbol).Count
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3322/assets/icons/icons.svg'
Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:3322/theme.css?v=gate-a'
```

期望：symbol 数为 30，两项 HTTP 状态均为 200。

## WP3 — G3 DOM hook 冻结

交付：

- `scripts/gates/dom-hook-inventory.mjs`
- `docs/dom-hooks-frozen.md`
- `docs/dom-hooks-frozen.json`
- `test-reports/gate-baseline/g3-dom-hook-inventory.{json,txt}`

断言：十类 hook 扫描已覆盖 25 页，共冻结 **1214** 条规范化表达式；`--check` 同时检查缺失和新增表达式，行号变化不产生伪漂移。全量复验结果：**PASS，25 页 / 50 checks / 0 failed**。

复验：

```powershell
node 'scripts/gates/dom-hook-inventory.mjs' --all --check --out 'test-reports/gate-baseline'
node 'scripts/gates/dom-hook-inventory.mjs' --page 'http://127.0.0.1:3322/chat.html' --check --out 'test-reports/gate-single'
```

## WP4 — G6/G7/G8/G9 门禁与现状基线

交付脚本：

- `scripts/gates/_shared.mjs`：Node 标准库 CDP/Chrome 启动、Node 18 可用的 WebSocket 客户端、目标解析和双报告输出。
- `scripts/gates/style-dep-gate.mjs`
- `scripts/gates/viewport-a11y-gate.mjs`
- `scripts/gates/asset-cache-gate.mjs`
- `scripts/gates/state-matrix-gate.mjs`

所有脚本支持 `--page <url>` 与 `--all`；硬失败返回非 0；输出人读 `.txt` 与结构化 `.json`。未新增 npm 依赖。

### 全量结果

| Gate | 结果 | 基线摘要 | 存量债结论 |
|---|---|---|---|
| G6 style dependency | FAIL | 25 页 / 150 checks / 26 failed | 25 页均存在 `<44×44` 的可见交互目标；`admin-dashboard.html` 另有 1 个第三方/富内容透明背景。布局黑名单与 z-index 冻结无漂移。 |
| G7 viewport/a11y | FAIL | 25 页 / 275 checks / 49 failed；125 张截图 | 对比度 25 页；reduced motion 13 页；焦点可见 4 页；Tab 可达 3 页；横向溢出 3 页；焦点遮挡 1 页。 |
| G8 asset/cache | FAIL | 25 页 / 200 checks / 52 failed / 19 warnings | 生产页按铁律尚未接入 `theme.css?v=`，故 25+25 项预期红；`courses.html`、`refund.html` 仍请求 Google Fonts。所有本地资源与字体源检查无 404。 |
| G9 state matrix | FAIL | 25 页 × 8 态 / 1400 checks / 39 failed / 110 warnings；200 张截图 | 3 个无 API 页无法命中网络态注入，共 24 项；`admin-users-refine-proto.html` 与 `learning.html` 长内容适配共 15 项。预期错误网络诊断记 warning，不伪装成门禁实现错误。 |

现状红项是逐页重塑的输入，不是本任务回写页面的授权；本任务没有为“刷绿”修改生产 HTML。

复验前置：前端 `3322`、后端 `9988` 健康；管理页精确基线需在当前 shell 以运行时环境变量提供临时授权，禁止写入文件或日志：

```powershell
$env:EDU_GATE_TOKEN = '<runtime-only access token>'
$env:EDU_GATE_REFRESH_TOKEN = '<runtime-only refresh token>'
```

全量复验：

```powershell
node 'scripts/gates/style-dep-gate.mjs' --all --out 'test-reports/gate-baseline'
node 'scripts/gates/viewport-a11y-gate.mjs' --all --out 'test-reports/gate-baseline'
node 'scripts/gates/asset-cache-gate.mjs' --all --out 'test-reports/gate-baseline'
node 'scripts/gates/state-matrix-gate.mjs' --all --out 'test-reports/gate-baseline'
```

单页模式示例：

```powershell
node 'scripts/gates/style-dep-gate.mjs' --page 'http://127.0.0.1:3322/chat.html' --out 'test-reports/gate-single'
node 'scripts/gates/viewport-a11y-gate.mjs' --page 'http://127.0.0.1:3322/chat.html' --out 'test-reports/gate-single'
node 'scripts/gates/asset-cache-gate.mjs' --page 'http://127.0.0.1:3322/chat.html' --out 'test-reports/gate-single'
node 'scripts/gates/state-matrix-gate.mjs' --page 'http://127.0.0.1:3322/chat.html' --out 'test-reports/gate-single'
```

视觉证据目录：

- `test-reports/gate-baseline/g7-screenshots/`：25 × 5 = 125 张。
- `test-reports/gate-baseline/g9-screenshots/`：25 × 8 = 200 张。
- 已人工抽看 login 360、admin dashboard 1280、chat 1920、learning 长文本态及主题资产 smoke；均为实际页面渲染，不是空白帧。

## WP5 — G10 回滚剧本

交付：`docs/rollback-drill.md`。

断言：单页 revert、`theme.css` revert、缓存清理/冷启动三种场景均定义前置、非破坏性命令、复验门禁和通过口径；明确禁用 `reset --hard`、`clean`、force push，并对 `.next` 删除目标做绝对路径校验。

复验：

```powershell
rg -n 'Scenario A|Scenario B|Scenario C|Refusing unexpected cache target|NOT RUN' 'docs/rollback-drill.md'
```

## 批判承接

1. **主表面纠偏**：没有沿用原 lavender 主表面；moss 绿成为语义主表面，lavender 只保留为辅助/关闭态。
2. **CTA 对比度纠偏**：珊瑚 CTA 使用深色文字，不使用未达标白字。
3. **管理端浓度风险**：按用户批款保留全黏土 C 路径，同时把 `clay-light` 作为 G7/G9 触红时的低深度回退，不提前擅自降级。
4. **emoji 与网络依赖**：冻结本地 Phosphor fill 子集并登记 25 页替换语义；G8 已把两个 Google Fonts 外链定位为后续页面改造债务。
5. **数量漂移**：没有按过时的 19 页清单硬编码；五只门禁动态扫描当前 25 页，后续新增 HTML 会自动进入 `--all`。
6. **不伪造绿灯**：G6-G9 现状 FAIL 原样落报告；warning 只用于预期网络错误/控制台跟踪，不吞掉布局、资产或可访问性硬失败。

## 编排承接与边界

- 重叠写：**无**。没有修改任何生产 HTML，也没有碰触其他任务的已修改文件。
- 推送：**无**。
- MEMORY.md：仓库内不存在该文件，本任务未新建或更新。
- 剩余风险：逐页重塑必须逐项消化上述 G6-G9 存量债，并统一接入带同一 `?v=` 的 `theme.css`；否则 G8 会持续保持红灯。
