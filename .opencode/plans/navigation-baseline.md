# 导航栏基准规范（HTML 原型必读 · 2026-08-22 用户反馈后确立）

> 适用：**所有 HTML 原型**（test-reports/fe-html/*.html）与 React 实现。
> 背景：用户反馈"很多页面没有导航栏（尤其用户页面）"+ 风格/交互回退。
> React 运行时已由 AppShell 统一（user 8 项 / admin 6 项），**HTML 原型必须与之一致**，不得退回无导航/局部导航。

## 1. 导航覆盖强制清单（HTML 原型每页必含）

### 用户端（8 项，桌面侧边栏形态）
| # | 导航项 | href 前缀 | 图标 |
|---|--------|-----------|------|
| 1 | 学习仪表盘 | /dashboard | LayoutDashboard |
| 2 | 课程中心 | /courses | BookOpen |
| 3 | 我的班次 | /my-courses, /learning | BookOpenCheck |
| 4 | 错题 / 单词本 | /practice | NotepadTextDashed |
| 5 | AI 学习问答 | /chat | Sparkles |
| 6 | 社区 | /community | MessagesSquare |
| 7 | 成就中心 | /achievements | Trophy |
| 8 | 个人中心 | /me | UserRoundCog |

### 管理端（6 项，桌面侧边栏形态）
| # | 导航项 | href 前缀 | 图标 |
|---|--------|-----------|------|
| 1 | 管理端仪表盘 | /admin/dashboard | LayoutDashboard |
| 2 | 课程管理 | /admin/courses | BookOpen |
| 3 | 题库管理 | /admin/questions | BookOpenCheck |
| 4 | 用户管理 | /admin/users | UserRoundCog |
| 5 | RAG 知识库 | /admin/rag | Database |
| 6 | MCP 工具 | /admin/mcp | Puzzle |

### 例外（允许无主导航）
- 登录/注册页（isAuthGate）：仅品牌条
- 学习页内嵌播放器（learning）：「面包屑 + 课程内大纲侧栏」，但页面仍需有品牌条 + 返回入口

## 2. 形态基准（对齐竞品 + AppShell）

- **桌面（≥768px）**：左侧固定侧边栏 w-64，品牌条 + 8/6 项导航 + 当前项渐变高亮（primary-deep→primary-strong）+ footer
- **移动（<768px）**：顶部汉堡按钮 → 抽屉侧边栏（translate-x 滑入 + 遮罩 + Escape 关闭 + 焦点管理）
- **顶栏**：sticky，左侧（移动端汉堡 + 面包屑）、右侧（问 AI + 用户头像下拉 或 登录按钮）
- **激活态**：matchPrefix 前缀匹配，当前项 aria-current="page"

## 3. 交互水平基准（修复"交互回退"）

HTML 原型交互必须达到早期高质量原型（learning/chat/achievements）水平：
- **完整演示控制器**：每页右下角分组按钮可切换各状态（loading/empty/success/error）
- **真实动效**：hover 提升、按下反馈、骨架屏加载、进度条动画、toast 滑入
- **错误/空/加载三态**全展示，空态带 CTA
- 数值字段用真实数据形态（非千篇一律占位符），图表/进度可视化

## 4. 与 React 一致性

- HTML 原型的导航结构、标签、图标、激活逻辑 **必须与 AppShell/(user)/(admin) layout 一致**
- 审核标准增加一条：**HTML 无主导航 = 不 APPROVED**（同 grep 5 项红线）
- React 实现不新增导航逻辑，只消费 AppShell（薄 layout 注入配置）

## 5. 竞品参考（websearch 2026-08）

- Duolingo：持久顶部菜单 + 单一任务焦点（页面只服务一个目标）
- Coursera：极简全局导航 + 课程序列/课程导航分离（课程内聚焦 prev/next）
- Khan Academy：迷你课程地图（侧栏进度导航）
- 移动端教育平台：「探索/学习/我的」底部三栏（拇指热区）+ 统一标签
- 共性：统一标签不重命名、固定位置不随滚动丢失、icons+labels 并用、面包屑定位、简化导航项不超载

## 6. 生效方式

- 本规范写入 doc-frontend 设计规范（新增 P20 导航基准）或作为独立基准文件
- 后续所有 HTML 原型任务（task45/49/61恢复等）的 prompt 附带本规范路径
- 历史 HTML（courses/dashboard/achievements/chat/community/admin-*）纳入整改任务批量补齐