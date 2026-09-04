# task-NAV: HTML 原型导航补齐 + 风格/交互统一（整改专项）

> **类型**：frontend 整改 ｜**执行工具**：TraeWork ｜**工作量**：L
> **触发**：用户反馈"很多页面没有导航栏（尤其用户页面）+ HTML 风格/交互回退"
> **基准**：`.opencode/plans/navigation-baseline.md`（本任务必读）

## 1. 背景
React 运行时已由 AppShell 统一导航（user 8 项/admin 6 项），但 **HTML 原型审核流**中多页面无主导航/导航不完整/交互回退，导致用户审核 HTML 时体验降级。本任务对历史 HTML 原型批量整改。

## 2. 待整改清单（导航审计 2026-08-22）

### 用户端（需补完整 8 项侧边栏导航）
| 文件 | 现状 | 整改 |
|------|------|------|
| courses.html | 仅局部导航 | 补 8 项侧边栏 |
| dashboard.html | 仅局部 CTA | 补 8 项侧边栏 |
| achievements.html | 仅 2 项 | 补完整 8 项 |
| chat.html | 0 项（有 aside.side）| 对齐 8 项 + headerRight（问AI/用户）|
| community.html | 局部（错题/社区）| 补 8 项 |
| community-post.html | 局部 | 补 8 项 |
| course-detail.html | 仅课程中心 | 补 8 项 |
| my-cohorts.html | 局部 | 补 8 项 |
| practice.html | 局部 | 补 8 项 |
| login-register.html | 品牌条（例外豁免）| 保持 |

### 管理端（需补 6 项侧边栏导航）
| 文件 | 现状 | 整改 |
|------|------|------|
| admin-courses.html | 无主导航 | 补 6 项 |
| admin-course-detail.html | 无主导航 | 补 6 项 + 面包屑 |
| admin-questions.html | 无主导航 | 补 6 项 |
| admin-question-detail.html | 无主导航 | 补 6 项 + 面包屑 |
| admin-dashboard.html | 仅仪表盘 | 补完整 6 项 |
| admin-users.html | 局部 | 补完整 6 项 |
| admin-rag-upload.html | 混用 user+admin | **改为纯 admin 6 项**（用户导航错混）|

## 3. 整改要求
- 严格按 navigation-baseline.md：桌面侧边栏 + 移动抽屉 + 顶栏 + 激活态 + footer
- 交互水平对齐早期高质量原型（learning/chat）：完整演示控制器 + 三态 + 动效 + 骨架屏
- candy-playful 风格一致；grep 5 项全 0（hex 仅 style token）
- 数值/图表用真实形态，不千篇一律占位

## 4. 验收标准
- Given 用户端页面，When 审核 HTML，Then 8 项导航齐全 + 移动抽屉可用 + 激活态正确
- Given 管理端页面，When 审核 HTML，Then 6 项导航齐全 + 面包屑（详情页）
- Given 任意页面，When 审核，Then 交互三态 + 演示控制器 + 动效水平对齐早期高质量原型
- Given 全部整改，When 复核，Then 导航审计 N 项归零（对照 navigation-baseline §2 清单）

## 5. 交接
- 完成 → 看板 task-NAV=DONE → sync.ps1
- 交付物：整改后 HTML（原文件覆盖 or 新文件）+ 审计报告