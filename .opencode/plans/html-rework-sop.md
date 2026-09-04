# HTML 页面返工 SOP —— 设计调用链执行手册

> 版本：v1.2 ｜ 创建：2026-08-19 ｜ 更新：2026-08-19（新增 §〇 风格定调 gate + §2.1 工具命令速查）
> 适用：EduAgent 前端 HTML 原型返工（`test-reports/fe-html/{page}.html`）
> 上游输入：用户返工意见 / 设计图 / `doc-frontend-design-spec.md` 页面规范 / **冻结的风格（§〇）**
> 下游输出：APPROVED 的 HTML → fe-implementer 写 React
> 调用链：`风格定调(§〇) → frontend-design → prototype → colorize → polish → visual-validation → audit/critique`
> 依据：AI-Hub skills（`D:\.ai-hub\skills\`）真实定义 + ui-ux-pro-max 设计系统生成器（已部署）+ 项目 HTML 审核流约定（doc-frontend-design-spec §五）

---

## 〇、风格定调 gate（项目级前置，首屏前必做）

> 目的：先统一"整体长什么样"，再逐页走 HTML 审核流，避免每页风格漂移、返工反复。**首个页面或用户要求风格大改前执行一次**，之后冻结。

### 〇.1 问风格

- 先问用户想要什么风格（可给图 / 给参考站 / 给关键词）。
- 用户**没想法** → 引导用户输入模板 prompt：
  > 请你根据实时搜索参考主流和小众教育平台的前端页面设计，给我几个关于前端 html 页面设计风格的 prompt。

### 〇.2 实时搜索 → 出风格 Prompt 池

- `webfetch` 实时抓取：主流平台（Coursera / Udemy / Brilliant / Duolingo）+ 小众/独立品牌 + Awwwards 教育类获奖站点 → 提炼配色/版式/字体/交互趋势；
- `python "D:\.ai-hub\skills\ui-ux-pro-max\scripts\search.py" "online education" --design-system -f markdown -p "EduAgent"` + `--domain style` 补风格候选；
- 产出 **N 个可直接复制使用的 HTML 风格 Prompt**（示例：主流职业学习平台风 / 游戏化学习风 / 学术极简风 / 前沿视觉实验风 / 暗色科技 AI 导师风 / 新粗野主义小众风；**不过拟合**——数量与分类以实时搜索结果为准）。

### 〇.3 选定并冻结

- 用户选定后：把风格固化进 `doc-frontend-design-spec.md`（页面规范）+ `design-tokens.json`（语义 token）；
- HTML 头部写 `<!-- STYLE: <风格名> frozen -->` 与 AUDIT LOG；
- **冻结后**：后续所有页面统一该风格，不再重复问；页面返工只在该风格内进行（换风格=重新走本 gate，视为风格大改）。

---

## 一、适用场景与触发条件

### 1.1 何时使用本 SOP

- 用户对 `test-reports/fe-html/{page}.html` 提出返工意见（讲解修改点 / 给设计图）
- 页面视觉质量不达标（用户反馈"不好看 / 不像设计 / 太 AI 味"）
- 页面需要从零产出 HTML 原型（首稿也走本链，Step 2 可压缩为 1 稿）

### 1.2 何时不使用

| 场景 | 处理通道 |
|---|---|
| 纯功能 bug 修复 | fe-tester / 常规修复，不走设计链 |
| 数据字段 / 接口对齐 | 走契约（schemas.py 唯一权威），不走设计链 |
| React 实现阶段 | fe-implementer（HTML 已 APPROVED 后） |

### 1.3 返工类型判定（收到意见后先分类，决定走哪几个 Step）

| 返工类型 | 触发信号 | 走链 |
|---|---|---|
| 布局 / 结构问题 | "换个布局"、"不像 XX 风格" | Step 1 → 2 |
| 色彩 / 单调问题 | "太素"、"没有重点色"、"颜色不对" | Step 3 |
| 细节 / 对齐问题 | "对齐"、"间距"、"状态缺失" | Step 4 |
| 整体"不像设计" | "不好看"、"太 AI 味"、"没设计感" | 全链 Step 1 → 6 |

---

## 二、调用链总览

```
[用户返工意见 / 设计图]
          │
          ▼
Step 0  上下文准备（读规范 / 读意见 / 读 tokens）          ── 5 分钟
          │
          ▼
Step 1  frontend-design  定设计方向（tone / differentiation / DO·DON'T）
          │
          ▼
Step 2  prototype        方案发散（≥3 个真正不同的方向，用户选 1）
          │
          ▼
Step 3  colorize         战略配色（语义色 + 60/30/10 主次关系）
          │
          ▼
Step 4  polish           细节打磨（对齐 / 间距 / 状态 / 动效 / 文案）
          │
          ▼
Step 5  visual-validation 浏览器截图验证（375/768/1024/1280/1440 + 交互态）
          │
          ▼
Step 6  audit / critique 独立审查（AI Slop 检测 + 五维质检 / UX 批判）
          │
          ▼
提交用户审核 → APPROVED ? ──否──→ 定位到对应 Step 返工（R2/R3…）
          │是
          ▼
写 AUDIT LOG → 移交 fe-implementer 写 React
```

**纪律**：Step 1 是每次返工的前置（获取 DO/DON'T 原则）；Step 5 是每次提交前的必过门；Step 6 是提交前的独立审查，禁止跳过。

### 2.1 工具命令速查（每步必须真跑，禁止"只看规划"）

> 以下命令均在本机已验证（ui-ux-pro-max 为本地 Python stdlib，无网络依赖）。加载 skill 后必须执行对应命令，产出真实结果再进入下一步。

| Step | 命令（Windows PowerShell） |
|---|---|
| 1 设计方向 | `python "D:\.ai-hub\skills\ui-ux-pro-max\scripts\search.py" "<页面意图 2~5 词>" --design-system -f markdown -p "<项目名>"` <br>取 Pattern/Style/Colors/Typography/Anti-patterns/预交付清单 |
| 2 风格发散 | `python "D:\.ai-hub\skills\ui-ux-pro-max\scripts\search.py" "<风格关键词>" --domain style -f markdown`（如 glassmorphism / bento / brutalist / minimal）<br>取 2~3 个互斥风格方向供用户选 |
| 3 配色 | `python "D:\.ai-hub\skills\ui-ux-pro-max\scripts\search.py" "<主题>" --domain color -f markdown` → 把语义色落回项目 `design-tokens.json`，禁止硬编码 hex |
| 4 打磨 | `grep -rn "#[0-9a-fA-F]\{3,8\}" test-reports/fe-html/{page}.html` 查硬编码色 → 必须来自 tokens |
| 5 视觉验证 | Playwright 截图 375/768/1024/1280/1440（项目 `scripts/shoot.js` 复用）+ 交互态 + dark → **Read 工具读 PNG 真渲染** → `{page}-visual-report.md` |
| 6 独立审查 | 读 `audit/SKILL.md` + `critique/SKILL.md` 执行；audit 只记录不修复；critique 诚实判 AI Slop |

**通用入口**：每次 HTML 产出/返工前，先跑 Step 1 的设计系统生成（`--design-system`），把生成的 Colors/Typography 与项目 tokens 对齐后写入 HTML 头部 `<!-- DIRECTION: ... -->`。

---

## 三、Step 0：上下文准备（必做）

### 3.1 读取输入

1. `doc-frontend-design-spec.md` 对应页面规范（布局草图 / 组件清单 / 状态机 / 数据依赖）
2. 用户返工意见原文，**逐条编号 ①②③**
3. `design-tokens.json`（语义 token → hex 展开，如 primary `#4F46E5`）
4. 当前 HTML 文件头部 **AUDIT LOG**（看历史轮次，避免重复返工）

### 3.2 判定

- 按 §1.3 判定返工类型，确定走哪几个 Step
- 若用户给了设计图：先做"图 → 结构"解析，提取布局骨架、配色、字体、间距节奏

### 3.3 出口标准

- [ ] 已读规范与 tokens
- [ ] 返工意见已逐条编号
- [ ] 已确定走哪几个 Step

---

## 四、Step 1：frontend-design —— 定设计方向

### 4.1 触发

- 页面整体"不像设计"，需要重定视觉方向
- **每次返工前必过**（获取 DO/DON'T 原则，防 AI Slop）

### 4.2 调用

读取 `D:\.ai-hub\skills\frontend-design\SKILL.md`，按其 Design Direction 执行；**先跑设计系统生成**：
`python "D:\.ai-hub\skills\ui-ux-pro-max\scripts\search.py" "<页面意图>" --design-system -f markdown -p "<项目名>"`，把返回的 Style/Colors/Typography 作为本步方向输入。

### 4.3 执行动作

1. **Purpose**：页面解决什么问题？谁用？
2. **Tone**：选极端方向（brutally minimal / editorial / playful / luxury / brutalist…），不要温和中间态
3. **Constraints**：框架 / 性能 / 无障碍
4. **Differentiation**：用户会记住的一个点（"这个页面最特别的是什么"）
5. 对照 Typography / Color / Layout / Motion / Interaction 的 DO / DON'T 逐项自查

### 4.4 产出物

- 一句话设计方向声明（写入 HTML 头部注释，如 `<!-- DIRECTION: editorial 杂志风，大字号 + 留白，indigo 主色 -->`）

### 4.5 出口标准

- [ ] 有明确 tone + differentiation
- [ ] 无 AI Slop 指纹（对照 §十二）

---

## 五、Step 2：prototype —— 方案发散

### 5.1 触发

- 返工意见涉及布局 / 结构 / 风格方向（"换个布局"、"不像 XX 风格"）
- 首稿产出（默认走，可压缩为 1 稿）

### 5.2 调用

读取 `D:\.ai-hub\skills\prototype\SKILL.md`，按其 Workflow 执行；**先用 ui-ux-pro-max 取风格方向**：
`python "D:\.ai-hub\skills\ui-ux-pro-max\scripts\search.py" "<风格关键词>" --domain style -f markdown`，取 2~3 个互斥风格作为变体 axis（禁止换色冒充新方向）。

### 5.3 执行动作

1. **Scope**：一次只做一件事（最高杠杆的组件 / 区块），其余列为后续
2. **Recon**：读 stack / tokens / personality / context
3. **定方向**：≥3 个**真正不同**的变体，每个有命名 + axis（"Quiet / Editorial / Playful"，禁止 Option A/B/C）
4. **构建**：单文件自包含 HTML，一个变体一个文件 + picker（`PICKER.md` 规范）
5. **验证**：每个变体可交互、无 console 错误
6. **呈现**：表格列出每个变体的适用场景 + 代价，**选择权在用户**

### 5.4 关键纪律

- 变体必须真正发散（不同 layout / interaction / motion，**不是换色**）；两个方向只差强调色 = 一个方向，砍掉补真替代
- 每个变体都要达到 craft 标准（正确缓动、sub-300ms、transform/opacity only、reduced-motion 处理），不是草稿
- 不预选 favorite；用户选完 `keep <variant>` 后清理原型面

### 5.5 出口标准

- [ ] ≥3 个变体，axis 互不重叠
- [ ] 用户已选择方向（或要求 `riff` 再发散一轮）

---

## 六、Step 3：colorize —— 战略配色

### 6.1 触发

- 页面太单调 / 灰 / 缺视觉兴趣
- 返工意见提到"颜色"、"太素"、"没有重点色"

### 6.2 调用

读取 `D:\.ai-hub\skills\colorize\SKILL.md`，按其流程执行。**前置**：先执行 frontend-design（获取 DO/DON'T）。**配色数据源**：
`python "D:\.ai-hub\skills\ui-ux-pro-max\scripts\search.py" "<主题>" --domain color -f markdown` → 语义色落回项目 `design-tokens.json`（禁止页面内硬编码 hex，随后用 grep 校验）。

### 6.3 执行动作

1. **上下文收集**：目标受众 / 用例 / 品牌色。缺失且无法高置信推断 → **AskUserQuestion 澄清，禁止猜**（猜 = AI slop 色）
2. **评估机会**：语义色 / 层级 / 分类 / 情感 / 寻路 / 愉悦，哪些值得上色
3. **定策略**：主色 60% + 次色 30% + 强调 10%，**2-4 色封顶**（不含中性色）
4. **应用**：状态徽章 / CTA / 链接 / 图标 / 标题 / hover / 背景 tint
5. **实现**：OKLCH 生成和谐色阶；中性色加品牌色 tint（禁纯灰 / 纯黑 / 纯白）

### 6.4 红线

- 禁彩虹色（2-4 色封顶）
- 禁紫-蓝渐变（AI slop 指纹）
- 禁灰字压彩色底（用背景色的深色阶或透明度）
- 对比度 ≥4.5:1（文本）/ ≥3:1（UI 组件）
- 不靠颜色单通道传达状态（配图标 / 文字）

### 6.5 出口标准

- [ ] 每个颜色都有语义目的
- [ ] 60/30/10 主次关系成立
- [ ] WCAG 对比度达标

---

## 七、Step 4：polish —— 细节打磨

### 7.1 触发

- 功能完整后、提交审核前的最后一轮
- 返工意见提到"对齐"、"间距"、"状态缺失"

### 7.2 调用

读取 `D:\.ai-hub\skills\polish\SKILL.md`，按其 Checklist 逐项过；**顺带跑硬编码色校验**：
`grep -rn "#[0-9a-fA-F]\{3,8\}" test-reports/fe-html/{page}.html`（允许的除外）→ 全部应来自 tokens。

### 7.3 执行动作（12 维度）

| # | 维度 | 检查点 |
|---|---|---|
| 1 | 对齐与间距 | 网格对齐、间距用 scale（禁随机 13px）、光学对齐（图标视觉居中） |
| 2 | 排版 | 层级一致、行宽 45-75 字符、无孤行、无 FOUT/FOIT |
| 3 | 色彩对比 | token 一致、无硬编码色、tint 中性色、主题变体一致 |
| 4 | 交互态 | default / hover / focus / active / disabled / loading / error / success 全齐 |
| 5 | 动效 | 150-300ms、ease-out（禁 bounce/elastic）、只动 transform/opacity、尊重 reduced-motion |
| 6 | 文案 | 术语一致、无错别字、标点一致、不重复用户已见信息 |
| 7 | 图标图片 | 同族、尺寸一致、与文字光学对齐、alt 齐全、无布局偏移 |
| 8 | 表单 | label 绑定、错误提示、焦点、tab 顺序 |
| 9 | 边界态 | loading / empty / error / success / 长内容 / 无内容 |
| 10 | 响应式 | 全断点、触控目标 ≥44px、无横向滚动、移动端字号 ≥14px |
| 11 | 性能 | 无 CLS、无 console 错误、懒加载、关键路径优化 |
| 12 | 代码 | 无 console.log、无注释代码、无未用 import |

### 7.4 纪律

- **polish 是最后一步，不是第一步**——功能未完整不 polish
- 有系统性问题时先修系统（如"间距到处不对"→ 先修间距 scale），不逐点打补丁
- 质量水平一致：不把一处打磨完美而其他处粗糙

### 7.5 出口标准

- [ ] §7.3 的 12 维度 checklist 全过
- [ ] 无系统性遗留问题

---

## 八、Step 5：visual-validation —— 浏览器视觉验证

### 8.1 触发

- HTML 修改完成、提交审核前（**必过门**）
- 每次返工后复测

### 8.2 调用

读取 `D:\.ai-hub\skills\frontend-visual-validation\SKILL.md`，按其步骤执行；**实际命令**：启动本地服务（或 file:// 打开自包含 HTML）→ Playwright 截图（可复用项目 `scripts/shoot.js`，输出 `shot-{page}-{viewport}.png`）→ 用 **Read 工具读 PNG 真渲染**。

### 8.3 执行动作

1. 启动本地服务器（或直接 file:// 打开自包含 HTML）
2. **Playwright 截图**：375 / 768 / 1024 / 1280 / 1440 全视口
3. **关键交互后补截图**：弹窗 / 下拉 / 错误提示
4. **主题 / 条件视图**：至少 1 张 dark 截图；核心页补高对比与 200% 缩放（命名 `-dark` / `-hc` / `-200pct`）
5. **用 Read 读 PNG**（看真实渲染，不能只看代码）
6. 对照 tokens 检查硬编码色值（Grep 查 hex）
7. 检查布局：水平溢出 / 元素重叠 / 文本截断 / 空白失衡
8. 检查状态：loading / empty / error / success 视觉呈现 + hover / focus 反馈

### 8.4 产出物

- 截图矩阵 `test-reports/fe-html/shot-{page}-{viewport}.png`
- 视觉报告 `test-reports/{page}-visual-report.md`（四类：规格违背 / 浏览器行为错误 / 内容文案 / 主观建议）

### 8.5 出口标准

- [ ] 截图矩阵齐全
- [ ] 无"规格违背" + 无"浏览器行为错误"
- [ ] 有参考图时像素级对比通过（pixelmatch / toHaveScreenshot）
- [ ] 不得为通过而伪造截图或报告

---

## 九、Step 6：audit / critique —— 独立审查

### 9.1 触发

- 提交用户审核前（**必做**）
- 用户反复不满意时（换 critique 找根因）

### 9.2 调用

- **audit**：读取 `D:\.ai-hub\skills\audit\SKILL.md`——系统性质检（a11y / 性能 / 主题 / 响应式 / 反模式），**只记录不修复**
- **critique**：读取 `D:\.ai-hub\skills\critique\SKILL.md`——UX 视角批判（层级 / IA / 情感 / 可发现性 / 微文案）

### 9.3 执行动作（audit）

1. **Anti-Patterns Verdict（最优先）**：先判"像不像 AI 生成"，列出具体 tells
2. 五维扫描：a11y / performance / theming / responsive / anti-patterns
3. 按严重度分级：Critical / High / Medium / Low
4. 找**系统性问题**（如"15+ 组件硬编码色"），不只报单点
5. 输出报告：位置 / 严重度 / 类别 / 影响 / 违反标准 / 修复建议 / 建议命令

### 9.4 执行动作（critique）

1. AI Slop 检测（同 audit 但偏 UX 判断）
2. 视觉层级：眼睛先看到最重要的？2 秒找到主行动？
3. 信息架构：结构直观？认知过载？
4. 情感共鸣：是否符合品牌人格？目标用户会觉得"这是给我的"？
5. 可发现性：交互元素明显可交互？hover/focus 有反馈？
6. 构图平衡 / 排版沟通 / 色彩目的 / 状态边界 / 微文案

### 9.5 关键纪律

- audit 只记录不修复（文档化，供后续命令处理）
- **诚实批判，不软化**："像 AI 生成的"就直说，不讨好
- 优先修 Critical / High；Low 可留待后续
- 修正后必须重跑 Step 5 复测闭环

### 9.6 出口标准

- [ ] audit 报告无 Critical / High 阻塞项
- [ ] critique 无 AI Slop 判定
- [ ] 修正项已闭环（改后重跑 Step 5）

---

## 十、返工循环与签收

### 10.1 循环

```
提交审核 → 用户意见（逐条编号 ①②③）→ 定位到对应 Step 返工
  → 修改点标注 <!-- FIX-R{n}-{①} --> → 重跑 Step 5 截图
  → 再提交 → 直到 APPROVED
```

### 10.2 AUDIT LOG 记录（写入 HTML 头部注释）

```html
<!--
  AUDIT LOG:
  [2026-08-19 R1] 初稿提交 → 用户意见：①价格区不够醒目 ②班次卡需显示剩余席位 → 状态: REVISING
  [2026-08-19 R2] 已按意见修改（价格 ¥ 加粗 tabular-nums；班次卡加容量进度）→ 状态: APPROVED
-->
```

### 10.3 状态机

`DRAFT → SUBMITTED → REVISING → APPROVED`（或 `REJECTED`）

### 10.4 签收标准

- [ ] 状态 = APPROVED 且无 REJECTED 遗留项
- [ ] 用户明确说"通过 / 签收 / APPROVED"
- [ ] **才允许** fe-implementer 写 React

---

## 十一、验收清单（提交前逐项打勾）

### 11.1 设计质量

- [ ] 有明确设计方向（tone + differentiation）
- [ ] 无 AI Slop 指纹（§十二全过）
- [ ] 色彩有语义、60/30/10 成立
- [ ] 视觉层级清晰（2 秒找到主行动）

### 11.2 技术完整

- [ ] 全部样式内联 `<style>`，无外链（无 CDN / 无字体外链，系统字体栈）
- [ ] 四态齐全（static / loading / empty / error）
- [ ] hover / focus / active / disabled 伪类齐全
- [ ] 模拟数据 `<!-- DATA: {json} -->` 内嵌（snake_case，含多状态样本）
- [ ] 响应式断点矩阵全过（375/768/1024/1280/1440）
- [ ] 无 console 错误

### 11.3 无障碍

- [ ] 对比度 WCAG AA（文本 ≥4.5:1，UI ≥3:1）
- [ ] 语义标签 + 唯一 h1 + 标题层级不跳档
- [ ] 焦点可见 + 键盘可操作
- [ ] 尊重 reduced-motion
- [ ] 状态徽章文字 + 颜色双通道（禁纯色块徽章）

### 11.4 流程

- [ ] AUDIT LOG 已更新（轮次 / 意见编号 / 状态）
- [ ] 截图矩阵已产出
- [ ] 视觉报告已输出

---

## 十二、AI Slop 红线（一票否决）

以下任一出现 → 判定"像 AI 生成"，必须返工：

1. **AI 配色**：深色底 + 霓虹强调 / 紫-蓝渐变
2. **渐变文字**做"冲击力"（尤其指标 / 标题）
3. **玻璃拟态滥用**（装饰性 blur / glow / 玻璃卡）
4. **Hero 指标模板**（大数字 + 小标签 + 统计 + 渐变强调）
5. **千篇一律卡片网格**（图标 + 标题 + 正文重复）
6. **通用字体**（Inter / Roboto / Arial / 系统默认）
7. **纯黑 `#000` / 纯白 `#fff` / 纯灰中性色**（无 tint）
8. **灰字压彩色底**
9. **弹跳 / 弹性缓动**
10. **动画 layout 属性**（width / height / padding，应只动 transform / opacity）
11. **圆角元素 + 单侧粗彩边**
12. **装饰性 sparkline**（无意义的小图表）

**AI Slop 测试**：把页面给某人看，说"这是 AI 做的"，对方是否立刻相信？如果是，就是问题。好的设计应让人问"这是怎么做出来的"，而不是"这是哪个 AI 做的"。

---

## 十三、常见失败模式与止损

| 失败模式 | 症状 | 止损动作 |
|---|---|---|
| 变体趋同 | 3 个变体只是换色 | 重跑 Step 2，强制 axis 命名互斥 |
| 过度打磨 | 功能未完成就 polish | 回到功能完整再 polish（polish 是最后一步） |
| 只见树木 | 修一处漏三处 | 先找系统性根因（token / 间距 scale） |
| 截图骗人 | 只看代码不看渲染 | 强制用 Read 读 PNG 截图 |
| 讨好式批判 | audit 全 PASS 无阻塞项 | 换 critique 从 UX 角度重审，诚实判 AI Slop |
| 返工失忆 | 重复上一轮已改的问题 | 先读 AUDIT LOG 历史轮次 |
| 猜色翻车 | 没问用户就上色，方向全错 | Step 3 强制 AskUserQuestion 澄清，禁止猜 |

---

## 十四、与项目既有流程的衔接

- **上游**：`doc-frontend-design-spec.md` §五（HTML 审核流）→ 本 SOP 是其中"返工"环节的可执行细则
- **下游**：APPROVED 后 → fe-spec-writer 出组件契约（C1~C21）→ fe-implementer 写 React → fe-styler 用 tokens 语义 class 替换内联 hex → fe-tester 补测试
- **目录**：`test-reports/fe-html/{page}.html` + `shot-{page}-{viewport}.png` + `{page}-visual-report.md`
- **工具**：Playwright 截图、Read 读 PNG、Grep 查硬编码色值、pixelmatch 像素对比
- **skill 位置**：`D:\.ai-hub\skills\`（frontend-design / prototype / colorize / polish / frontend-visual-validation / audit / critique）

---

## 附：快速启动卡（30 秒定位）

```
收到返工意见
  ├─ 是布局/风格问题？        → Step 0 → Step 1 → Step 2（3 变体给用户选）
  ├─ 是色彩/太素？            → Step 0 → Step 1 → Step 3
  ├─ 是细节/对齐/状态？       → Step 0 → Step 4
  └─ 是整体"不像设计"？       → Step 0 → Step 1 → 2 → 3 → 4
修改完成 → 必过 Step 5（截图）→ 必过 Step 6（audit/critique）
  → 提交用户 → APPROVED ? → 写 AUDIT LOG → 移交写 React
```
