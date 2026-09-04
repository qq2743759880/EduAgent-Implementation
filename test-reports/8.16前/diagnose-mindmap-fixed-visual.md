# diagnose-mindmap-fixed 视觉复验报告

> 复验对象：思维导图字段不匹配修复（后端 `rel_type`/`line_style` vs 前端 `relation`/`lineStyle`，tooltip 全显「关联」、PREREQUISITE amber 虚线丢失）。
> 修复内容（代码审查确认）：API 层 `normalizeMindMap` 归一化（`rel_type→relation`、`line_style→lineStyle`、status 大写枚举→小写）+ `CourseMindmapView` 组件读取对齐 + `statusColor` 状态映射。
> 本次为复验（只审查，未改任何代码）。报告文件名沿用任务命名 `diagnose-mindmap-fixed`（编排器未下发 fe-taskNN 编号）。

## 环境

- 启动方式：复用既有 dev server（未重复启动）——Next dev @ `http://localhost:3000`（Turbopack），后端 FastAPI @ `http://127.0.0.1:8000`
- 登录账号：admin / Admin@12345（UI 表单登录成功 → `/dashboard`）
- 页面：`/courses/1` → 「思维导图」Tab（`CourseMindmapView`，ECharts 6.1 Graph force layout）
- Playwright：chromium 1.62.1，视口 1280×1500（图表完整入视）；截图目录 `test-reports/screenshots/`
- 验证方式：**程序化 DOM + canvas 像素级断言**（当前模型不支持读图，故全程以 `getImageData` 像素统计 + 真实鼠标悬停 tooltip DOM 文本为准，无任何视觉主观依赖）
- ⚠️ 环境注意：dev server 以 `localhost:3000` 为自身 origin；用 `127.0.0.1:3000` 访问时带 `Origin` 头的 `_next/static/chunks/*.js` 全部被 403（Next dev 源保护）→ 页面 JS 加载失败、hydrate 卡死。**必须用 `http://localhost:3000`**。属环境行为，非应用 bug。

## 验证点结论

| # | 验证点 | 结论 | 证据 |
|---|--------|------|------|
| a | 边 tooltip 关系文本（PREREQUISITE 边不再全显「关联」） | **PASS** | 悬停 amber 边捕获 3/4 条 PREREQUISITE 边 tooltip，均显示 `关系：PREREQUISITE`（如 `KP-EN-VOWEL-SINGLE → KP-EN-VOWEL-DOUBLE 关系：PREREQUISITE`）；CONTAINS 边显示 `关系：CONTAINS`；**全部采样中「关系：关联」出现次数 = 0**（`genericTooltips: []`） |
| b | PREREQUISITE 边 amber 颜色（#F6BD16，不再全灰） | **PASS** | canvas 像素统计：amber 720 px，**实际平均色值 (245,189,22) ≈ #F6BD16 (246,189,22)**；blue 902 px，平均 (90,143,249) ≈ #5B8FF9（CONTAINS 边）；灰色节点 6784 px |
| c | 节点状态色 | **PASS（NOT_STARTED）/ N/A（MASTERED）** | 8/8 节点灰 `#525252`（chartNeutral[2]），悬停全部显示 `状态：未开始`（NOT_STARTED→未开始 映射生效，含 `类型：模块/知识点/系列课程`）；**MASTERED 绿色无法实测**：课程 1 数据 `mastered_count: 0`（无 MASTERED 节点）→ 数据级 N/A；代码路径存在（`normalizeMindMap` `MASTERED→mastered` + `statusColor('mastered')→#059669`） |
| d | 图谱正常渲染 + console 0 错误 | **PASS** | canvas 17,799 不透明像素；8 节点 / 11 边像素聚类齐全；图例数据随接口返回；**console 0 错误、pageerror 0** |

## 发现分类

### [规格违背]（必须修正）
无。三项关键验证点 + console 全部 PASS，修复目标达成。

### [浏览器行为错误]（必须修正）
无。

### [内容/文案]（建议修正）
- `CourseMindmapView.tsx:77` — 边 tooltip 关系文本输出**后端枚举原值**（`关系：PREREQUISITE` / `关系：CONTAINS`），未映射为中文「先修/包含」。用户期望「先修」；当前仅图例含中文（后端 `legend: "PREREQUISITE (先修)"`）。核心 bug（全显「关联」）已修复，中文标签属增强建议：在 formatter 增加 `RELATION_LABEL = { PREREQUISITE: "先修", CONTAINS: "包含", RELATED_TO: "相关", TESTS: "考核" }` 映射。**不进入阻塞判定**。
- 图例未渲染：组件已配置 `legend: { data: d.legend(4 项), type: "scroll" }`，但渲染结果中容器 DOM 仅 canvas 包裹层 + tooltip div，canvas 底部 60px 像素为 0，全页无 `PREREQUISITE` 图例文本。疑似 ECharts 6.1 `type: "scroll"` 图例在该容器尺寸/布局下未挂载。**非本修复引入**（修复前同样配置），建议单独核实。**不进入阻塞判定**。

### [主观建议]（不强制）
- dark 视图：项目**有意未实现 dark 主题**（`globals.css:7-10` 注释：`.dark` 变量块已删除、全仓无启用逻辑，`@custom-variant dark` 为 class 门控停用）。已按 Tailwind class 策略强制 `.dark` 截图存档（`diagnose-mindmap-fixed-dark.png`），body 保持亮色属预期行为，非回归。
- 375 视口：`document.scrollingElement` 无水平溢出（scrollWidth 375 = clientWidth 375），canvas 自适应 317px，截图已存。

## 判定

- 结论: **PASS**
- 阻塞项: 无

## 机器可读结论（供评测自动断言）

```json
{"taskId": "diagnose-mindmap-fixed", "result": "PASS", "blockers": []}
```

## 证据与产物

- 主截图（整页，tooltip 悬停态）：`test-reports/screenshots/diagnose-mindmap-fixed.png`
- 图表区域：`test-reports/screenshots/diagnose-mindmap-fixed-chart.png`
- tooltip 特写（amber 边悬停）：`test-reports/screenshots/diagnose-mindmap-fixed-tooltip.png`
- dark 视图（按项目 class 门控强制，行为符合"无 dark 主题"设计）：`test-reports/screenshots/diagnose-mindmap-fixed-dark.png`
- 375 视口：`test-reports/screenshots/diagnose-mindmap-fixed-375.png`
- 完整结构化数据（像素统计/聚类/tooltip 全量文本/console 错误列表）：`test-reports/screenshots/diagnose-mindmap-fixed-summary.json`

关键原始证据（summary.json 摘要）：
- `pixels`: `{amber: 720, blue: 902, gray: 6784, opaque: 17799, amberAvg: [245,189,22], blueAvg: [90,143,249]}`
- `prereqTooltips`: 3 条唯一 PREREQUISITE 边 tooltip（含 `关系：PREREQUISITE`）
- `genericTooltips`: `[]`（无「关系：关联」回退）
- `nodeTooltips`: 8 个节点全部 `状态：未开始`
- `consoleErrors: []`, `pageErrors: []`
