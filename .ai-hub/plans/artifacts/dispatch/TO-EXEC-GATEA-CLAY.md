# TO-EXEC-GATEA-CLAY — 前端重塑 Gate A：3 页 × 3 黏土变体（1 天工期第一步）

## 使命

EduAgent 前端风格已定为**黏土拟物（Claymorphism）**，路线=静态页原地重塑（结构层/行为层禁碰）。本任务只做 **Gate A 原型变体**：3 个代表页 × 3 个风格变体 = 9 个独立 HTML + 1 个挑选索引页，供用户可视化翻页挑款。**严禁触碰任何生产页面**（`edu-frontend/public/*.html` 一个字节都不许改）。

## 必读资产（开工前实读）

1. `docs/前端风格重塑方案.md` —— §7.1 设计令牌冻结稿（配色/圆角/阴影/间距/动效全部参数在此，照抄不发明）、§六 变体探索轴、§7.3 组件规范、§7.4 双密度、§7.7 动效与 reduced-motion
2. 现页参考（只看结构气质，不复制代码）：`edu-frontend/public/login-register.html`、`chat.html`、`admin-dashboard.html`

## 交付物

目录 `edu-frontend/_prototypes/clay-gatea/`（新建，隔离面）：

| 文件 | 内容 |
|---|---|
| `login-a.html / login-b.html / login-c.html` | 登录注册页三变体，探索轴=**配色浓度**（a 奶昔淡 / b 标准粉彩 / c 高饱和糖果） |
| `chat-a.html / chat-b.html / chat-c.html` | AI 对话页三变体（含：消息流假数据、用户/AI 双色气泡、一条 Markdown 回答、一张 HITL 确认卡带确认/取消按钮、输入框），探索轴=**气泡质感**（a 纯色块 / b 渐变黏土 / c 带厚度描边） |
| `admin-a.html / admin-b.html / admin-c.html` | 管理端三变体（侧栏+顶栏+4 统计卡+一张 10 行数据表格+分页器），探索轴=**黏土浓度**（a clay-light 表格区 L0 平面 / b 半黏土 / c 全黏土），须体现方案 §7.4 双密度对比 |
| `index.html` | 挑选索引：九宫格 iframe 缩略 + 「在新页打开」+ 每变体一行探索轴说明，方便用户翻页选款 |

## 硬约束

1. 单文件自包含（内联 CSS；JS 只允许挑款索引页的 iframe 切换；原型页零 JS 或仅 hover 纯 CSS）
2. 令牌照抄方案 §7.1（色值/圆角/阴影三层配方逐字一致）；阴影必须**同色相**（灰色阴影=黏土感死亡）
3. 对比度：正文文字对背景 ≥4.5:1；CTA 珊瑚底 (#FF7A6B) 上的文字色自选并标注实测对比度值（方案 §7.1 遗留问题，你的答案将定稿全站 CTA 文字色）
4. 中文界面（用项目真实文案气质：课程名/按钮/管理端表格列名可自拟合理假数据）
5. 禁外网资源（无 CDN 字体/图标；图标用内联 SVG 或 emoji）
6. 每页底部加一行注释：`<!-- variant: <id> axis: <探索轴> -->`

## 交付与报告

- 单 commit：`feat(fe)/GATEA-CLAY: 黏土 Gate A 3页×3变体原型（隔离面，零生产代码改动）`
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-GATEA-CLAY.md`：九页清单+每页探索轴一句、CTA 对比度实测值、自检清单（硬约束 6 条逐条勾）
- 报告末尾给出用户挑款指引：「打开 edu-frontend/_prototypes/clay-gatea/index.html 逐格看，每类挑一个字母」
- 铁律：不 push；开工前后 `git branch --show-current`=feature/opt-waves；生产 public/ 目录零改动（编排者将 diff 验收，发现即 FAIL）
