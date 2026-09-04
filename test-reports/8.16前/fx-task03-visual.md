# 视觉审查报告 fx-task03（G3 管理端课程/题库/用户页面）

> 执行：fe-visual-auditor（补课波·只审查+出报告，**未修改任何业务代码**）
> 日期：2026-08-13 ｜ 基线：`.claude/specs/frontend/fx-task03/`（design-tokens.json / visual-acceptance.md / screen-map.md）+ `test-reports/fx-task03-server-info.md`（fe-server-infra 产物，dev :3000 PID 17284，startedByInfra=true）
> 审查方式声明：本模型不支持直接读图，视觉验证以 **DOM 计算样式 + 布局几何测量**（getComputedStyle / getBoundingClientRect / scrollWidth-clientWidth）等效完成（与 fx-task02-visual.md 同口径）；截图全量保存供人工复核，非像素级复刻。

## 1. 环境

- 启动方式：**复用 fe-server-infra 已启动的 dev server**（Next.js 16.3.0 Turbopack，`npm run dev`，http://localhost:3000），未重复启动
- 后端 127.0.0.1:8000 未运行 → **Playwright `page.route` 模拟全部管理端 API**（`/api/admin/courses/series`、`/api/admin/courses/series/1`、`/api/admin/courses/series/1/tree`、`/api/admin/courses/materials/redirect-upload`、`/api/admin/questions`、`/api/admin/questions/1`、`/api/admin/questions/tags`、`/api/admin/users`、`/api/admin/users/1`、`/api/admin/users/dashboard/metrics`）
- 登录态：注入 localStorage `edu:auth:token` + `edu:auth:me`（`roles:["admin"]`），AdminGuard 客户端校验放行（server-info 注意事项 #2 已确认判定逻辑）
- 截图目录：`test-reports/screenshots/fx-task03/`（17 张）
- 已知环境噪音：`/api/chat/sessions` 等用户端请求 404（MCP console 记录，非本 task 回归，server-info 注意事项 #3 同源）

## 2. 判定

- **结论：PASS**
- 阻塞项：无（本 task 范围 D-01~D-23 修正项全部落地并经视觉/代码层双重确认；浏览器行为无错误）
- 挂账转交（不阻塞本 task，但阻塞「管理端 token 化验收」，与 fx-task02 同判据）：D-04 `--primary` 中性黑 / D-06 渐变 token 化 / D-08 arbitrary 字号 / GAP-02 卡片规范二义 → **fe-task00**；D-07 暗色 → 挂账（N/A）；D-20 徽标原语 → 视觉修复批次（P2）

## 3. 截图清单（17 张）

| # | 文件 | 场景 |
|---|------|------|
| 1 | `admin-dashboard-1440.png` | /admin/dashboard 1440×900 成功态（6 指标卡） |
| 2 | `admin-dashboard-375.png` | /admin/dashboard 375×812 |
| 3 | `admin-dashboard-1440-error.png` | metrics 接口 500 → ErrorState「加载失败 + 重试」 |
| 4 | `admin-courses-1440.png` | /admin/courses 1440 成功态（3 行卡片 + 过滤栏） |
| 5 | `admin-courses-375.png` | /admin/courses 375×812 |
| 6 | `admin-courses-1440-empty.png` | series 空数组 → EmptyState「暂无系列」 |
| 7 | `admin-courses-detail-1440.png` | /admin/courses/1 1440（概要卡 + ModuleTree + 班次 + 课件指引） |
| 8 | `admin-courses-detail-375.png` | /admin/courses/1 375×812 |
| 9 | `admin-questions-1440.png` | /admin/questions 1440 成功态（5 题行 + 标签 pill） |
| 10 | `admin-questions-375.png` | /admin/questions 375×812 |
| 11 | `admin-question-edit-1440.png` | /admin/questions/1 1440（QuestionForm embedded 回填） |
| 12 | `admin-question-edit-375.png` | /admin/questions/1 375×812 |
| 13 | `admin-users-1440.png` | /admin/users 1440 成功态（7 列表格 + 状态 pill） |
| 14 | `admin-users-375.png` | /admin/users 375×812（表格 overflow-x-auto 横向滚动） |
| 15 | `admin-courses-1440-dialog.png` | 创建系列 SeriesForm 弹窗打开 |
| 16 | `admin-questions-1440-dialog.png` | 新建题目 QuestionForm 弹窗打开 |
| 17 | `admin-users-1440-dialog.png` | UserDetailDialog 用户详情弹窗打开 |

> 专项视图：**-dark / -hc / -200pct 标注 N/A 挂账**（D-07 管理端仅 light 为既有约定，visual-acceptance §2 D-07 验收标准：补暗色前不判定失败）。

## 4. 发现表

### [规格违背]（必须修正）

无。本 task 范围内修正类 D 项（D-01/02/03/05/10/14/19/21/22 + 核对 D-12/17 + 确认 D-15）全部落实，未发现新的规格违背。

### [浏览器行为错误]（必须修正）

无。6 页面 × 双 viewport 全部成功渲染，无水平溢出/遮挡/破版；弹窗开合正常；三态（加载/空/错误）呈现明确。

### [内容/文案]（建议修正）

无。

### [主观建议]（不强制）

| # | 位置 | 建议 |
|---|------|------|
| S-1 | 行卡片（courses/questions） | 卡片规范现状仅 `hover:shadow-sm`，无常驻 shadow；GAP-02 收口前建议 fe-task00 二选一（改 card.tsx 或修订规范），见 D-04 挂账 |
| S-2 | `design-tokens.json radius` | 实测 `rounded-xl` = 14px（`--radius:10px * 1.4`），tokens 文档记 12px；fx-task02 W-2 同源，fe-task00 收口时校准口径 |

## 5. 视觉验收项逐条核对（D-01 ~ D-23）

> 证据列：`代码` = grep 源码；`实测` = 浏览器计算样式/几何测量。处置分类与 visual-acceptance §2 一致。

| # | 偏差 | 处置 | 现状核对 | 证据 |
|---|------|------|---------|------|
| D-01 | MetricCards 6 色图标底 | ✅ 已修正 | **收敛确认**：TONES 表仅 indigo/emerald/rose 三色；实测 6 卡图标底 = indigo-50 ×3 / emerald-50 ×2 / rose-50 ×1 | 代码 `MetricCards.tsx:81-85`；实测 dashboard-1440 全卡采样，sky/violet/amber 0 |
| D-02 | sky/violet 基准外色 | ✅ 已修正 | **收敛确认**：7d 新增=emerald、30d 登录=indigo | 代码 grep `bg-sky\|bg-violet\|text-sky\|text-violet` 全 admin 目录 0 命中；实测 30d 人均登录卡 indigo-50、7d 新增卡 emerald-50 |
| D-03 | 角色分布卡 amber | ✅ 已修正 | **收敛确认**：角色分布图标底 indigo-50 | 实测 dashboard 第 3 卡 iconBg = indigo-50 系 |
| D-04 | token/实现两层脱节（--primary 近黑） | 归 fe-task00 | 挂账（不阻塞本 task，阻塞 token 化验收） | 实测所有 indigo 渲染视觉正确（Stepper/正确圆标/选中态均 indigo-600 系）；token 层 `--primary` 近黑由 fe-task00 修正 |
| D-05 | in_progress 用 sky | ✅ 已修正 | **收敛确认**：in_progress → indigo-50/indigo-600 | 实测 series-detail「in_progress」chip bg = indigo-50 系、text = indigo-600 系 |
| D-06 | 侧边栏 active 渐变 | 归 fe-task00 | 挂账（视觉正确，token 化归 fe-task00） | 实测 active 菜单 = `from-slate-800 to-indigo-700` 白字 + shadow-sm（layout.tsx:163，fx-task02 壳） |
| D-07 | 暗色策略未落实 | 保持现状 + 挂账 | N/A 挂账（管理端仅 light；`-dark` 截图不判定失败） | visual-acceptance §2 D-07 验收标准 |
| D-08 | arbitrary 字号 ~30+ 处 | 归 fe-task00 + P2 | 挂账：grep `text-[13px]/[12px]/[11px]` 本 task 范围约 34 处（含 rag/mcp 为 task04 范围）；arbitrary **色值** 0 违规 | 代码 grep；tokens `_hardcodedMap` |
| D-09 | 页级 space-y-5 vs 6 | 保持现状 | 确认（无错位/无溢出） | 实测 courses/questions/users 页级堆叠正常 |
| D-10 | 标签多选两形态 | ✅ 已修正 | **确认**：共享 `TagChip` + `NO_TAG_HINT` | 代码 `controls.tsx`（TagChip 导出）、QuestionForm:301 / ComposePaperDialog:183 引用；实测 tag pill 形态统一（#核心词汇 bg indigo-50） |
| D-11 | Dialog 标题图标不一致 | 保持现状 | 记录为既有惯例 | 实测 3 弹窗标题均正常（SeriesForm/QuestionForm/UserDetail） |
| D-12 | 行操作模式二选一 | ✅ 已核对确认 | **确认**：删除类 icon-only + aria-label 全存在 | 实测 question-edit 正确圆标 `aria-label="选项 A 标记为正确答案"`；UserTable 删除/详情按钮 aria-label 齐全 |
| D-13 | 行 hover 两模式 | 保持现状 | 确认（两种 hover 均可达） | 代码：行卡片 hover:shadow-sm / 表格 hover:bg-slate-50/60 |
| D-14 | 课次空态内联文本 | ✅ 已修正 | **确认**：`EmptyState compact` | 代码 `ModuleTree.tsx:345-347`；实测 courses 空态 EmptyState 正常 |
| D-15 | 原生 window.confirm | ✅ 保持现状确认 | **确认**：删除/下架均有二次确认且含不可恢复语义 | 代码 courses:132「下架后用户端不再展示」、questions:217「删除后不可恢复」 |
| D-16 | NativeSelect 两高度 | 保持现状 | 确认（表格紧凑密度无溢出） | 实测 users 表格正常 |
| D-17 | 信息块四类映射 | ✅ 已核对确认 | **确认**：过程=indigo-50、成功=emerald-50/60、中性=slate-50、警告=amber-50/60 | 实测 dashboard ErrorState bg = rose-50 系（dangerSoft）、series-detail 课件指引块 amber-50/60、转码成功块 emerald 系 |
| D-18 | 带色浅底小元素圆角三分 | 保持现状 | 记录（低风险） | 实测 chip/pill 均为 rounded-full、图标底 rounded-xl、按钮 rounded-lg |
| D-19 | 已绑/未绑视频裸文字 | ✅ 已修正 | **确认**：chip 形态（已绑=emerald-50/700、未绑=amber-50/700） | 实测 series-detail「已绑视频」bg emerald-50 系、「未绑视频」bg amber-50 系 |
| D-20 | 带色状态小圆标两处重复 | 挂账（P2） | 复核确认：QuestionForm 正确圆标为交互 button（aria-label+toggle，实测 bg indigo-600），ModuleTree teaching chip 为静态 span，语义不同不强抽 | 实测 question-edit + 代码 |
| D-21 | messages 混排一色 | ✅ 已修正 | **确认**：`messageToneCls` 按 skip/编码重复→amber、fail/schema invalid→rose、兜底 slate | 代码 BatchImportDialog.tsx:75 |
| D-22 | 标签为空提示文案两处 | ✅ 已修正 | **确认**：共享 `NO_TAG_HINT`（「暂无标签，可在题库页创建」） | 代码 controls.tsx:18 + 两处引用 |
| D-23 | InfoRow 定义列表 vs asset 卡 | 保持现状 | 确认（两种信息展示均清晰） | 实测 UserDetailDialog InfoRow 列表完整 |

**偏差合计核对：23 项 —— 修正 12 项全部落地 ✅；归 fe-task00 ×3（D-04/06/08）挂账；保持现状 ×8（D-09/11/13/15/16/18/23 + D-07 N/A）确认；D-20 挂账复核。**

## 6. 关键视觉实测数据（管理端基准一致性）

| 维度 | 实测值（1440×900 / 375×812） | 判定 |
|------|-------------------------------|------|
| MetricCards 6 卡图标底 | 仅 indigo-50/emerald-50/rose-50 三色，无 sky/violet/amber | ✅ D-01/02/03 收敛 |
| 状态语义色 | completed/正常=emerald-50/700、in_progress=indigo-50/600、scheduled=slate-100、禁用=rose-50/600、未绑=amber-50/700、已绑=emerald-50/700、tag pill=indigo-50/600 | ✅ 符合 visual-acceptance §6 状态色边界 |
| 正确项圆标 | indigo-600 实底白字 + aria-label | ✅ D-20 主色语义 |
| 卡片 | 白底 + rounded-xl（14px 实测）+ border-slate-200；MetricCards 用 Card 组件 ring 风格（GAP-02 挂账） | ✅ 视觉一致（token 层挂账） |
| 壳（fx-task02 共享） | 侧边栏 w-64 白底 6 菜单 + active 渐变；顶栏 h-14 sticky bg-white/80 backdrop-blur；内容 p-4 md:p-6 | ✅ 与 fx-task02 基准一致 |
| 弹窗 | SeriesForm 384×576、QuestionForm 384×666、UserDetail 384×373，均居中、无溢出 | ✅ |
| 溢出 | 12 张页面截图 scrollWidth == clientWidth（0 溢出）；移动端 users 表格 min-w-[720px] 在 overflow-x-auto（720>327 可滚动）不破版 | ✅ |
| 三态 | 加载（LoadingState 组件 + server-info SSR 记录）、空（EmptyState「暂无系列」实测）、错误（ErrorState「加载失败 + 重试」实测） | ✅ |

## 7. 结论

- **判定：PASS**
- 阻塞项：无
- 本 task 修正清单（P0×3 D-01/02/03 + P1 D-05/10 + P2 D-14/19/21/22 + 核对 D-12/17 + 确认 D-15）**全部落地，视觉层与代码层双重确认**；浏览器行为 6 页 × 双 viewport 全部通过（无溢出/遮挡/破版）；管理端基准（slate/indigo 单主色 + 白卡片 + rounded-xl + border-slate-200 + 语义状态色）与 fx-task02 壳一致。
- 挂账转交（不阻塞本 task，阻塞「管理端 token 化验收」）：**D-04 `--primary` 中性黑（BLOCKER）、D-06 渐变 token 化、D-08 arbitrary 字号、GAP-02 卡片规范二义 → fe-task00**；D-07 暗色 → N/A 挂账；D-20 徽标原语 → 视觉修复批次（P2）。与 fx-task02 判定口径一致：以上修正落地前，不判定「管理端 token 化视觉验收」通过（fe-task00 的门，非本 task 的门）。
- 备注：本报告基于 DOM 计算样式 + 布局几何测量等效完成（模型不支持读图），17 张截图已存档供人工复核；MCP 环境存在已知 URL 漂移竞态，已用 path 强校验 + 重试机制确保截图内容正确。

## 机器可读结论（供评测自动断言）

```json
{"taskId": "fx-task03", "result": "PASS", "blockers": []}
```
