# 视觉审查报告 fx-task04（G4 管理端 RAG + MCP 控制台）

> 执行：fe-visual-auditor（补课波·只审查+出报告，未改任何业务代码）
> 日期：2026-08-13 ｜ 基准：`.claude/specs/frontend/fx-task04/`（design-tokens.json / visual-acceptance.md / screen-map.md / frontend-spec.md）+ `frontend-stack.json`
> 审查方式声明：当前模型不支持直接读图，视觉验证以 **DOM 计算样式 + 布局几何测量**（getComputedStyle / getBoundingClientRect / scrollWidth / CDP emulate）等效完成，覆盖颜色/字体/圆角/阴影/间距/溢出/层级/交互态；截图已保存供人工复核。**非像素级复刻**（无参考截图，规格驱动审查）。

## 环境

- 启动方式：复用既有 dev server（Next.js 16.3，http://localhost:3000，PID 17284，见 `test-reports/fx-task04-server-info.md`，startedByInfra=false），**未重复启动**
- 登录方式：AdminGuard 仅客户端检查 localStorage（`edu:auth:token` / `edu:auth:me`，roles:["admin"]），注入 admin 登录态进入管理端（无后端依赖，等价 fx-task02 实测判定）
- 数据方式：后端 127.0.0.1:8000 未运行 → Playwright `page.route` 拦截 `http://127.0.0.1:8000/api/**` 模拟后端 API（含 OPTIONS preflight + CORS），覆盖 `/api/admin/rag/*` 与 `/api/mcp/*` 全部契约端点（collections/presets/audit-log/search/rebuild、servers/tools/discover-live/tools-test/call-log/health-scan）
- 截图目录：`test-reports/screenshots/fx-task04/`（22 张）
- 工程目录：edu-frontend（nextjs-16-app-router，Tailwind v4）

## 截图清单

| # | 文件 | 场景 |
|---|------|------|
| 1 | `rag-1440.png` | /admin/rag 1440×900 首屏 |
| 2 | `rag-1440-full.png` | 1440 全页 |
| 3 | `rag-375.png` | 375×812 首屏 |
| 4 | `rag-375-full.png` | 375 全页 |
| 5 | `rag-rebuild-dialog.png` | RebuildDialog 打开（incremental） |
| 6 | `rag-rebuild-full.png` | 切换「全量」模式 |
| 7 | `rag-rebuild-result.png` | 提交后 202 job_id 结果块 |
| 8 | `rag-search-input.png` | SearchTester 输入 query |
| 9 | `rag-search-result.png` | 检索结果（召回/最终 + degraded 黄条 + docs） |
| 10 | `rag-dark.png` | html.dark（管理端 light-only 实证） |
| 11 | `rag-hc.png` | forced-colors 高对比 |
| 12 | `rag-200pct.png` | CDP 200% 缩放 |
| 13 | `mcp-1440.png` | /admin/mcp 1440×900 首屏 |
| 14 | `mcp-1440-full.png` | 1440 全页 |
| 15 | `mcp-375.png` | 375×812 首屏 |
| 16 | `mcp-375-full.png` | 375 全页 |
| 17 | `mcp-health-scan.png` | 健康扫描摘要徽章 |
| 18 | `mcp-server-form.png` | ServerForm（含 import-url 快速导入块） |
| 19 | `mcp-tools-db.png` | ToolTable DB 工具列表 |
| 20 | `mcp-tools-live.png` | 实时 Discover 结果 |
| 21 | `mcp-tool-test.png` | ToolTestDialog 参数 JSON 编辑 |
| 22 | `mcp-tool-test-result.png` | 工具测试结果（状态徽章 + 终端块） |

## 发现表

### [规格违背]（记录确认——全部已在 visual-acceptance.md 预登记为「挂账 fe-task00」，本 task 不判定失败、不改代码）

| # | 位置 | 类型 | 严重度 | 实测 | 期望（基准） |
|---|------|------|--------|------|-------------|
| V-1 | `rag/page.tsx:99`（预设卡）；`CollectionTable.tsx:26`；`AuditLogTable.tsx:121`；`SearchTester.tsx:44`；`ServerTable.tsx:41`；`CallLogTable.tsx:140` | 规格违背（A1 卡片缺 shadow） | MUST-FIX (fe-task00) | 全部容器实测 `bg white + rounded-xl(14px) + border-slate-200 + box-shadow: none`（lab 91.7 边框色） | 基准 = white + rounded-xl + border-slate-200 + **shadow-sm**；缺 shadow 与 fx-task02 GAP-03 同源，挂账 fe-task00 全站统一 |
| V-2 | `rag/page.tsx:106`（is_default 徽章） | 规格违背（C1 语义色边界） | MUST-FIX (fe-task00) | 实测 `border-emerald-200 bg-emerald-50 text-emerald-700`（lab bg 97.8/-6.9）——emerald 用于「默认项」业务标识 | 收敛为主色徽章（bg-indigo-50 text-indigo-700）或中性（bg-slate-100 text-slate-600） |
| V-3 | `ToolTestDialog.tsx:173`（终端块） | 规格违背（C3 语义边界记录） | 记录 (fe-task00) | 实测 `bg-slate-900`(lab 7.79) + `text-emerald-100`(lab 94.9) + Geist Mono 12px——深色终端块保留，emerald-100 为终端绿输出惯例 | token 化 `--code-block-bg/--code-block-fg`，注释注明不占状态色槽位 |
| V-4 | 2 页 + 10 组件 + controls.tsx（~58 处） | 规格违背（B 类 arbitrary 字号） | MUST-FIX (fe-task00) | grep 复核：`text-[13px]`×30 / `text-[12px]`×13 / `text-[11px]`×15（fx-task04 范围，与 visual-acceptance §2.3 实测口径一致） | 收敛为语义字号 token（--text-sm-table / text-xs / --text-2xs）；`text-[12px]` 与 text-xs 同值纯写法问题 |
| V-5 | `globals.css:10`（`--font-sans: var(--font-sans)` 自引用） | 规格违背（字体 token，fx-task02 V-3 同源） | BLOCKER (fe-task00) | 实测 UI 字体栈回退 `"Times New Roman"`（h1/h2/卡片/正文全部 serif 回退），Geist 特征未生效；font-mono 正常（Geist Mono） | `--font-sans: var(--font-geist-sans)`；非本 task 引入，挂账 fe-task00 统一修正 |

### [浏览器行为错误]（必须修正）

无。两页首屏/全页/375/交互/条件视图全部实测正常：无页面级水平溢出（1440/375 scrollWidth==clientWidth）、无遮挡、无断行、表格 `overflow-x-auto` 内滚动正常（ToolTable 内嵌表 sticky thead + max-h-360 局部滚动正常）。

### [内容/文案]（建议修正）

无。空值占位统一「—」（text-slate-300）、错误文案可见（ErrorState message + 重试）、degraded 黄条文案「降级提示：…」、健康扫描摘要「OK 1 / ERR 2（共 3，156ms）」全部符合规格。

### [主观建议]（不强制）

| # | 位置 | 建议 |
|---|------|------|
| S-1 | 全站容器 | radius 实测 `rounded-xl` = **14px**（`--radius-xl` 由 `--radius*1.4` 派生），与 tokens 文档 12px 口径不符——与 fx-task02 W-2 同源，建议 fe-task00 统一口径 |

## 视觉验收项逐条核对（visual-acceptance §2/§3 逐项）

| 验收项 | 实测 | 结论 |
|--------|------|------|
| 状态灯/徽章四档语义色（emerald/amber/rose/slate，仅状态场景） | RAG StatusBadge：就绪=emerald-100/700、重建中=amber-100/700 + amber-500 pulse 点、异常=rose-100/700 ✓；MCP HealthDot：OK=emerald-500 点+emerald-600 标签、ERR=rose-500 点+rose-600、未知=slate-300 点+slate-400（实心点+文字标签）✓；CallStatusBadge：成功 emerald/失败 rose/超时 amber/跳过 slate 四档 ✓；全 task 0 处 sky/violet 功能色 | **保持** ✓ |
| 图标单主色 indigo-500 | Database/SlidersHorizontal/Cable 实测同色 lab(48.3, 38.3, -82) = indigo-500 ✓；Trash2 rose-500（注销=危险操作，C5 合理保持）✓ | **保持** ✓ |
| arbitrary 色值 0 处（C8 / 红线 12） | grep `bg-[#` / `text-[#` / `style={{color}}` / oklch 全 task **0 命中**，全部 Tailwind palette 语义类 | **保持** ✓ |
| is_default emerald 徽章（C1） | 默认徽章实测 emerald（见 V-2），**挂账 fe-task00 记录在案**，渲染正常不受阻 | 挂账（不判失败） |
| 终端块（C3） | `pre bg-slate-900 text-emerald-100 font-mono` 实测（见 V-3），深色块存在且仅此 1 处 | 记录（不判失败） |
| 表格/卡片容器 white + rounded-xl + border-slate-200（A1） | 实测一致但缺 shadow-sm（见 V-1），**挂账 fe-task00** | 挂账（不判失败） |
| 页面底色 / 区块标题 / 页头 | 壳 bg-slate-100/70（fx-task02 AdminShell）✓；区块 h2 `text-sm font-semibold text-slate-700` 14px ✓；页头 h1 `text-xl font-semibold text-slate-900` 20px ✓ | **保持** ✓ |
| import-url 功能块（C2） | ServerForm「一键导入（import-url）」实测 text-indigo-700（lab 32.4/49.2/-84.7）indigo 主色功能强调，非分功能多色 | **保持** ✓（记录边界） |
| degraded 黄条 | `border-amber-200 bg-amber-50 text-amber-800` + TriangleAlert 实测 ✓（业务降级非错误） | **保持** ✓ |
| 成功块 / 错误块 | RebuildDialog 202 结果 `border-emerald-200 bg-emerald-50 text-emerald-800` ✓；工具测试 ERROR `bg-rose-50 text-rose-700` ✓；live discover 失败弹窗内 rose banner（直连超时）✓ | **保持** ✓ |
| 健康扫描摘要徽章 | `bg-slate-100 text-slate-600` 中性徽章 ✓ | **保持** ✓ |
| JSON 输入错误态 | 非法 JSON → 输入框 `border-rose-400`（lab 64.4/63/19.2）+ FieldRow 行内 rose 错误，不触发请求 ✓ | **保持** ✓ |
| 三态（加载/空/错误） | LoadingState（min-h-180 + spinner）、EmptyState（dashed border + Inbox）、ErrorState（rose 边框 + AlertCircle + 重试）均按规格存在（代码级确认 + 交互实测错误路径） | **保持** ✓ |
| 间距一致性 | 页 space-y-6、区块 space-y-2、卡片 p-3、表格 px-3 py-2.5、过滤栏 gap-2 全 task 一致 | **保持** ✓ |
| 响应式 375 | 无页面级溢出（scrollW=375=clientW）；过滤栏 flex-wrap；预设网格单列（grid-template-columns 343px）；表格容器内滚动；侧边栏抽屉（transform none 关闭态 + 菜单按钮可见） | **保持** ✓ |
| 管理端风格与 fx-task02 壳一致性 | 同 AdminShell（侧边栏白底 w-64、顶栏 h-14 blur、主区 p-4/p-6、面包屑）；卡片同款无 shadow（GAP-03 同源）；菜单「RAG/MCP」激活态渐变 from-slate-800 to-indigo-700 | **保持** ✓ |
| dark 视图 | `html.dark` 后壳仍白（sidebar/表格 bg white 不变）——管理端仅 light 视觉，与 tokens colorsDark 占位声明一致 | **保持** ✓（记录） |
| 高对比 / 200% | forced-colors active 生效（表格边框强制黑）；CDP pageScaleFactor 2 无水平溢出（scrollW=1440=clientW） | **保持** ✓ |

## 结论

- **判定：PASS**
- 阻塞项：**无**（本 task 无「规格违背」修正项与「浏览器行为错误」；V-1/V-2/V-3/V-4/V-5 均为 visual-acceptance 预登记的挂账 fe-task00 项，记录在案不判失败，见 §5 挂账清单）
- 视觉验收通过标准达成情况：§2「保持 ✓」与「记录」项**全数通过**；挂账项（A1/C1/B 类/D 类记录 + 字体自引用同源）全部可见于本报告发现表，随 fe-task00 落地复验
- 备注：① 本报告基于 DOM 计算样式 + 布局几何测量（模型不支持读图），22 张截图存档供人工复核；② 后端 8000 未运行，API 数据由 route mock 注入（契约端点全覆盖），不影响视觉验收；③ 与 fx-task02 壳基准逐项对照无新增偏差

```json
{"taskId": "fx-task04", "result": "PASS", "blockers": []}
```
