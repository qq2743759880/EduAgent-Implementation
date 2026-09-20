# TO-EXEC-THEME-GATE — 重塑底座：theme.css 定稿 + Phosphor 图标 sprite + G3/G6-G9 门禁工具

## 使命（1 天重塑工期的第二棒）

Gate A 已批款（挑款记录见方案 §六末尾批款块）。本任务交付**逐页重塑开工前的全部底座**：三件套 = 最终 theme.css、本地图标 sprite、五只新门禁脚本。**不改任何生产页面**（public/*.html 零改动——逐页重塑由后续批量开工令做）。

## 必读资产（开工前实读）

1. `docs/前端风格重塑方案.md` —— §7.1 令牌冻结稿（基参数照抄）+ **§六末尾 Gate A 批款块（用户裁定，优先级高于 §7.1 原文）**、§3.2 十道门禁定义、§7.3 组件类规范、§7.6 图标决策
2. `edu-frontend/_prototypes/clay-gatea/` —— 已批款变体（chat-b / login-b / admin-c 的实现直接参考；注意批款修订：主表面弃 lavender 换绿系）
3. 现状盘点对象：`edu-frontend/public/*.html`（19 页，只读盘点，不改）

## 工作包 1：theme.css 定稿（`edu-frontend/public/theme.css`，本任务唯一许碰的 public 文件——新建）

1. 令牌：方案 §7.1 全量参数 + 批款修订——**主表面 lavender→绿系**（在 #B8D8A8/#C5E1A5 浅苔绿-抹茶区间选主 hex，校验与文字 #2E2A3F 对比度 ≥4.5:1 后冻结，把实测值写进 token 注释）；lemon 黄=暖点缀；**CTA 文字色=#2E2A3F**（5.43:1 已实测）
2. 组件类：§7.3 表全量（clay-card/clay-btn-primary/clay-btn-soft/clay-pill/clay-input/clay-bubble-user/-ai/clay-nav/clay-card-placeholder）+ 双密度辅助类（admin 区 clay-light 降级类备用，虽批款 C 仍保留以备 G7 红）
3. 每个表面色配一档**同色相阴影 token**（灰阴影=FAIL）；`prefers-reduced-motion` 块；`.page-<name>` 命名空间骨架注释
4. 文件头注释=token 文档（交接物 1：每个变量一行用途说明）

## 工作包 2：Phosphor 图标 sprite（`edu-frontend/public/assets/icons/`）

1. 先盘点 19 页现存图标/emoji 使用点（grep emoji 区段 + `<svg`/`<img` 图标），产出清单（页 × 图标语义 × 现状）
2. 选 **Phosphor fill 权重**（MIT），取所用语义的**子集**（预计 20-30 枚：导航/收藏/课程/社区/设置/登录/发送/复制/关闭/警告等），**本地 SVG sprite**（`icons.svg` symbol 集合 + 使用片段规范写进 theme.css 头注释）
3. 硬规则：零 CDN、零图标字体（防 FOUT）、**零 emoji 作图标**；提供 `<svg class="ic"><use href="/assets/icons/icons.svg#ic-name"/></svg>` 规范片段
4. 版权注记：sprite 文件头标注 `Icons: Phosphor Icons (MIT) https://phosphoricons.com`

## 工作包 3：门禁工具（`scripts/gates/`，新建目录；Node ≥18 无新依赖，CDP 用既有 verify_pages_cdp.mjs 同款连接方式——先实读它）

| 脚本 | 对应门禁 | 核心断言 |
|---|---|---|
| `dom-hook-inventory.mjs` | G3 | 十类扫描（getElementById/querySelector/querySelectorAll/classList 操作/closest/matches/事件委托选择器/动态拼接与模板串选择器/form.elements·name·tagName/parentNode·nextSibling 族）→ 产出 `docs/dom-hooks-frozen.md` 冻结清单（19 页逐页一节）；`--check` 模式比对清单逐条存在 |
| `style-dep-gate.mjs` | G6 | CDP computed-style：CSS 禁改黑名单元素布局属性、弹层 z-index 层级表、第三方容器背景非透明、交互元素点击区 ≥44×44 |
| `viewport-a11y-gate.mjs` | G7 | 360/768/1280/1440/1920 五视口截图+无横向溢出；键盘 Tab 可达+焦点可见；对比度 ≥4.5:1；aria-label/title 不丢 |
| `asset-cache-gate.mjs` | G8 | 零外网请求；theme.css 引用带 `?v=` 且全站同版本；本地资源无 404；模拟 woff2 失败不断字 |
| `state-matrix-gate.mjs` | G9 | CDP 网络拦截注入八态（空/加载/错误/无权限/禁用/长文本/token 过期/500）截图断言无破版 |

每只脚本：`node scripts/gates/<x>.mjs --page <url>` 单页模式 + `--all` 全站模式；exit 0=绿/非 0=红；输出人读+JSON 双报告。对**现状页**首跑各出一份基线报告（`test-reports/gate-baseline/`）——现状本就红的项（如有）如实登记为「存量债」，不阻塞逐页重塑。

另交 `docs/rollback-drill.md`（G10 剧本：单页 revert/theme.css revert/缓存清理三场景+复验命令），G10 实演练习留到逐页重塑收尾。

## 铁律

public/ 只许新建 theme.css 与 assets/icons/**；19 页存量零改动；不 push；单 commit：`feat(fe)/THEME-GATE: theme.css 定稿+Phosphor sprite+G3/G6-G9 门禁工具（Gate A 批款修订已并）`；报告 `.ai-hub/plans/artifacts/dispatch/REPORT-THEME-GATE.md`（每 WP 断言附复现命令；含资产消费证据/批判承接段；承接=无重叠写无）。开工前后 `git branch --show-current`=feature/opt-waves。
