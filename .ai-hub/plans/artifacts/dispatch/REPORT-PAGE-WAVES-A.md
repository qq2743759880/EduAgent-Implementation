# REPORT-PAGE-WAVES-A — 逐页重塑包 A 交回（学生端核心 8 页）

- 执行分支：`feature/opt-waves`（开工前/收尾后均已复核 = feature/opt-waves）
- 执行窗口：2026-09-21
- 结论：**8/8 页重塑完成、逐页独立 commit、G3/G6/G7/G8/G9 逐页实测**。其中 6 页五门全绿；2 页存在**数据面/门禁前提**类红项（详见 §4 变更单，均非样式层缺陷、视觉层无解）。
- 环境：前端 3322 / 后端 9988 health 通过；门禁统一以真实学生 token（user000001 实时登录注入 EDU_GATE_TOKEN/REFRESH）运行，避免未登录 302 跳登录造成的 route-stable 假红。

## 1. 门禁结果矩阵（checks 总数 / error-failed 数）

| 页面 | commit | G3 (2) | G6 (6) | G7 (11) | G8 (8) | G9 (56) | 红项性质 |
|---|---|---|---|---|---|---|---|
| favorites.html | `24eea20` | 2/0 | 6/0 | 11/0 | 7/**1** | 56/0 | G8 zero-external=5：种子数据 `cover_url` 外链占位图（§4-①） |
| dashboard.html | `9c84d03` | 2/0 | 6/0 | 11/0 | 8/0 | 56/0 | — 全绿 |
| courses.html | `911e66d` | 2/0 | 6/0 | 11/0 | 8/0 | 56/0 | — 全绿（含 Google Fonts 外链清除） |
| course-detail.html | `4e397fc` | 2/0 | 6/0 | 11/0 | 8/0 | 56/0 | — 全绿 |
| learning.html | `fb1f920` | 2/0 | 6/0 | 10/**1** | 8/0 | 56/0 | G7 tab-reachable 19/21：roving tabindex 规范模式 vs 门禁盲区（§4-②） |
| practice.html | `6a1e422` | 2/0 | 6/0 | 11/0 | 8/0 | 56/0 | — 全绿 |
| login-register.html | `17a1523` | 2/0 | 6/0 | 11/0 | 8/0 | 48/**8** | G9 state-intercepted×8：登录页 load 时零 API 调用，G9 前提不成立（§4-③，N/A） |
| me.html | `d6e3934` | 2/0 | 5/**1** | 10/**1** | 7/**1** | 56/0 | G6/G7 console-errors + G8 zero-external=1：档案 `avatar_url` 外链占位（§4-①） |
| **G1（包级）** | — | \multicolumn{6}{c}{`febe_contract_check.py --quiet` → breakpoints=0，in_use_unfrozen=0，unfrozen_only=0，to_connect=72，exit 0（接口面零变化）} |

原始报告（JSON/TXT，最新一轮逐页运行）：`test-reports/gate-baseline/g3-dom-hook-inventory.*`、`g6-style-dep-gate.*`、`g7-viewport-a11y-gate.*`、`g8-asset-cache-gate.*`、`g9-state-matrix-gate.*`；G7 视口截图存档 `test-reports/gate-baseline/g7-screenshots/`、G9 八态截图 `g9-screenshots/`。

## 2. 内联 JS 与 CDP 运行态验证（包级）

- **内联 JS `node --check`**：8 页共 28 个内联 script 块，语法失败 **0**（逐页执行记录见各页门禁过程）。
- **CDP console 零报错汇总实测**（等效 verify_pages_cdp 语义：Runtime.exceptionThrown + Log.entryAdded(error) + console.error，1280×900，真实 token，settle 1.2s）：
  - 6/8 页 **console=0 全净**：dashboard、courses、course-detail、learning、practice、login-register；
  - favorites=5 条、me=1 条，**全部**为 `net::ERR_NAME_NOT_RESOLVED`（`cdn.example.com` 封面/头像占位域）→ 数据面，见 §4-①；
  - 未直接使用 `verify_pages_cdp.mjs`：该脚本硬编码已退役端口 3000/8000，`docs/rollback-drill.md` L23 已明文「not an acceptable G5 command until separately migrated」，且脚本不在本包文件域（8 页+公共静态资源）；门禁 G6-G9 内置同语义 console 捕获已逐页覆盖。

## 3. 存量债清偿对照（本次清了哪些红项）

| # | 存量债 | 位置 | 处置 | 结果 |
|---|---|---|---|---|
| 1 | Google Fonts 外链（G8 红项，派单点名） | courses.html `@import Baloo 2` | 删除，本地系统字体栈 | G8 zero-external 全绿（courses 8/0） |
| 2 | 手绘内联 SVG 控件 | courses 搜索/筛选/下拉 3 枚；learning 视频/作业/考试 3 枚 tab 图标 | 换 sprite：ic-magnifying-glass / ic-gear / ic-caret-down（保留 `.filterbar.open svg` 旋转语义，旋转收窄到 caret）/ ic-play / ic-pencil-simple / ic-certificate | icon-inventory 处置意见落实 |
| 3 | emoji 结构性图标（Gate A 批款禁令） | 8 页静态 HTML 全量 | 30 枚冻结 sprite 语义映射（§5 表）；无对应 sprite 语义的 glyph **删除留文本，未自造** | 静态面 emoji 图标清零 |
| 4 | 点按区 <44×44 | 全 8 页：导航项/页脚链接、chips、分页钮、清空钮、筛选 select、redo/撤销、t10 翻页、eyeball 钮、pf-goal、statebar 演示钮、记住我 checkbox（16px→44）等约 40 处 | min-width/height 44 + padding 调整 | G6 interactive-target-44 全绿（me/course-detail 曾红已清） |
| 5 | 文字对比度 <4.5:1 | 彩字-on-浅底（green-deep/blue-deep/orange-deep/purple on soft ≈3.7-4.8）、白字-on-粉彩（按钮/徽章/角标/封面标题）、muted/faint 灰阶、disabled UA GrayText（rgba(16,16,16,.3)）、Chrome 默认 placeholder #757575、JS 内联珊瑚色价格字（!important 样式层接管） | 文字一律收敛到 text-strong/cta-text/status-danger(≥5.0)/text-muted(仅白底)，按钮改粉彩底+墨字或珊瑚底+cta-text | G7 contrast-4.5 全绿（dashboard 曾 40 处红、course-detail 25 处红、practice/learning/login/me 均已清零） |
| 6 | 无限运行动画（§7.7 禁令 + G7 reduced-motion） | courses hero float、course-detail mascot、learning mascot/bounce、各页 shimmer/spin | 永久动画删除；loading 指示器保留但 reduced-motion 下停转 | G7 reduced-motion 全绿（learning 曾 running=2 已清） |
| 7 | 作者 CSS 压过 `[hidden]` 的存量 bug | learning `.transcode{display:flex}`、`.tab .cnt{display:inline-grid}` | 补 `.x[hidden]{display:none}`，显隐控制权归还 hidden 属性（JS 行为不变） | G9 state-long-content-fit 7 态红 → 全绿；转码遮罩不再常驻 |
| 8 | color-mix 工具盲区 | dashboard/courses 等 | **全包禁用 color-mix**（G7 parse() 把 Chrome 的 `color(srgb …)` 序列化按 0-255 误读为近黑），浅色 tint 全部改令牌色相静态推导值 | dashboard G7 contrast 40→0 |
| 9 | login-register 弃紫（Gate A 批款：主表面 lavender 紫→绿/黄系） | 主 `:root` violet 系全量 | `--primary`→moss、CTA→珊瑚+cta-text、accent 条→moss/sky/mint/lemon、品牌 chip 改墨底 | 批款色执行完毕 |
| 10 | focus 可见性 | login-register 缺全局焦点环；learning tab 焦点环用 sky | 补 `:focus-visible` 全局规则（focus-ring 令牌） | G7 focus-visible 全绿 |

## 4. 变更单（需编排者裁定，视觉层无解项）

1. **【数据面】种子数据外链占位资源**：`cover_url`（favorites 5 张）与 `avatar_url`（me 1 张，`https://cdn.example.com/...`）为不可达假域名。G8 zero-external / G6+G7 console-errors 据此红（加载失败产生 LOG error + 外链请求计数）。JS 渲染 `<img src=data 值>` 属行为层禁碰；CSP/隐藏图片等方案会引入新的 console error 或破坏真实封面显示，均不可取。**建议**：seed 数据改为本地占位 `/assets/img/…`（顺带修复线上裂图体验），或 G8/门禁对占位域白名单+降噪。影响页：favorites、me（me 的 G6/G7/G8 三处红全部由此一项引起）。
2. **【门禁盲区】learning G7 tab-reachable 19/21**：unreachable=`#tab-hw/#tab-exam`。task06 以 SDK 式 roving tabindex 实现 WAI-ARIA tabs 规范（非激活 tab `tabindex=-1`，方向键 Home/End/←→ 切换，JS 已实现且 G3 冻结）。G7 仅注入 Tab 键，不识别方向键模式。按「行为层一个字符不动」铁律未改 JS。**建议**：门禁对 `role=tablist` 容器识别 roving 模式，或登记页面级豁免。
3. **【门禁前提】login-register G9 state-intercepted ×8**：登录页 load 时零 API 调用（仅提交时 POST login/register，已核 JS），G9 前提「拦截到 /api/* 请求」结构性不成立。**建议**：G9 对零 API 页输出 N/A 而非 FAIL。
4. **【sprite 扩展建议】** `eye`（密码可见性）语义无冻结 sprite：3 个 eye 按钮保留 👁 glyph（已补 `aria-label="显示或隐藏密码"`），待 sprite 按纪律扩展 ic-eye 后替换；票据/时钟/图表/指南针等语义按「无 sprite 删字形留文本」处理，未自造。
5. **【工具陈旧，未动】** `verify_pages_cdp.mjs` 硬编码 3000/8000（rollback-drill 已标注）；`scripts/gate-baseline` 内 aria/style 基线由 THEME-GATE 验收于重塑前冻结（2026-09-20T11:33），本包以「零新增 class」纪律全量适配（8 页 aria-title-frozen 全 PASS）。

## 5. 资产消费证据

1. **theme.css（L2 冻结）**：8 页均以 `<link rel="stylesheet" href="/theme.css?v=7fed87f">` 接入（G8 theme-version-present 8/8 PASS、site-theme-version=7fed87f 统一）；只用其中令牌与 `.ic` 组件类，**theme.css 本身零改动**；页内私有变量全部经旧变量名→令牌映射（变量名不变=行为层零影响），禁改黑名单六条全程遵守（G6 layout-blacklist 8/0 无 drift；`pointer-events`/状态类显隐语义/结构选择器零触碰）。
2. **icons.svg sprite（30 枚冻结子集，未扩展）**：实际启用 20 枚——ic-star/ic-book-open/ic-pencil-simple/ic-trophy/ic-certificate/ic-gear/ic-magnifying-glass/ic-caret-down/ic-user/ic-sign-in/ic-warning/ic-check-circle/ic-x/ic-info/ic-chat-circle/ic-bookmark-simple/ic-graduation-cap/ic-play/ic-copy/ic-arrow-left。映射示例：错题本→pencil-simple、积分→trophy、等级→certificate、学习时长→play、优惠券→bookmark-simple、订单→copy、退款→arrow-left、登录 CTA 语义→sign-in。JS 字符串内 emoji（判分 ✓/✗、JS 重试 🔄、badge icon_emoji 数据等）属行为层逐字节未动。
3. **login-b 原型（批款款）**：moss 主表面 + 珊瑚 CTA + `--cta-text #2E2A3F`（5.43:1）+ 三层黏土阴影配方 + 粉彩 blob 背景在 login-register 及各页落地；G7 contrast 全绿为实测佐证。
4. **dom-hooks-frozen.md**：G3 `--check` 8 页全 PASS（frozen-hooks-present=0 missing、new-hooks-reviewed=0 added）——JS/结构层零改动实证。
5. **icon-inventory.md / dom-hooks-frozen.md / rollback-drill.md**：icon 处置按表执行；单页 commit 即 Scenario A 粒度（8 个独立可 revert 提交）；G5 替代路径依剧本 L23 立场（见 §2）。
6. **Gate A 批款块**（方案 §六）：弃紫令、禁 emoji 图标令、CTA 文字色定稿逐项落实（§3-9、§3-3）。

## 6. 批判承接段（与在跑任务的重叠风险自查）

- 文件域：仅 `edu-frontend/public/` 8 个页面文件 + 其引用的公共静态资源引用（theme.css/sprite 只读未改）；未触碰其他包页面、后端、门禁脚本与基线文件。
- 门禁基线：`test-reports/gate-baseline/` 的 G6 style-dep / G7 aria 快照在本包运行中新增了 8 页条目（首轮运行自动落盘，属门禁设计行为）；未覆盖/改写其他页条目。
- 与 B/C 包（管理端/chat 等其余页）、WRITE1、THEME-GATE 无文件交集；本包发现的三条跨页机制（color-mix 工具盲区、`[hidden]` 被作者 CSS 压制、disabled GrayText）**可能同样存在于未重塑页**，建议编排者在派 B/C 包时把 §3-6/7/8 三条作为已知坑注入开工令，避免重复试错。
- 遗留移交：无未完成动作；上板红项均已定性并附建议（§4）。
