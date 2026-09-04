# task42 完工报告 — /login + /register 认证页 + / 根路由

> **日期**：2026-08-25｜**执行**：Trae（前端开发者·手下调度）
> **类型**：frontend（P6 · W7）｜**契约**：task15 契约⑬（auth 壳 + AUTH_EXPIRED 字符串码）
> **前置**：task41、task15、task60 验收通过

---

## 一、任务目标（GWT 摘要）
- fe-spec-writer 先行补充本页规范 → HTML 原型 → APPROVED → React 实现
- /login 表单 + 错误态 + toast + redirect 回跳原路
- /register 409 冲突提示 + 成功跳登录
- / 根路由：已登录→/dashboard、未登录→/login
- AUTH_EXPIRED 等字符串码 toast（契约⑬）

## 二、交付物与验收对照

| GWT | 验收记录 |
|-----|---------|
| 规范先行 | `.opencode/handoffs/task42-auth-pages-spec.md`（P-LOGIN/P-REGISTER/P-ROOT：布局/组件/交互/状态机/数据依赖，对齐 doc-frontend §二） |
| HTML 原型 | `test-reports/fe-html/login-register.html`（v1.3，演示登录/注册/根路由/401 横幅/409/字符串码 toast/redirect 回跳；用户多轮反馈后停等 APPROVED） |
| 未登录访问受保护页 → /login?redirect= 回跳 | auth-client+guards 完善（admin/用户守卫均有测试） |
| 注册重复 account → 409 冲突 toast/字段 | RegisterForm 字段级 setError + toast，契约 `40912` |
| 根路由分流 | `app/page.tsx`：未登录→/login（透传 redirect）、已登录→/dashboard |
| AUTH_EXPIRED 等字符串码 | api-client.ApiError.code 透字符串码；非认证接口 401 → toast「登录已过期」+ 跳登录（onApiUnauthorized） |

## 三、React 实现（本质：契约⑬ 已在前序整合，本次为风格对齐 /dashboard token 化）

**改动文件（5）与要点**
| 文件 | 改动 |
|------|------|
| `src/app/page.tsx` | 根路由占位背景 `sky`→`from-primary-soft via-white to-secondary`、`slate`→`muted-foreground` |
| `src/components/auth/AuthCard.tsx` | 背景 sky→主/副色渐变；Card `border-slate`→`border-border bg-card/90 shadow-card`；品牌 `indigo+sky`→`from-primary to-primary-deep`；标题/描述/footer slate→语义 token |
| `src/components/auth/LoginForm.tsx` | 登录按钮 `to-sky-600`→`from-primary to-primary-strong`；错误横幅 rose→`destructive` 语义；记住我/遗忘 slate→muted-foreground；checkbox indigo→primary；显隐按钮 slate→语义 |
| `src/components/auth/RegisterForm.tsx` | 注册按钮 `to-teal-600`→`emerald` 副色渐变（去 teal）；条款 `text-[11px]`→`text-xs`（去 arbitrary）+ slate→muted-foreground；显隐×2 语义化 |
| `src/lib/protected-route.tsx` | 守卫加载占位 `text-slate-500`→`text-muted-foreground`（4 处） |

**设计取舍（独立审查提出，保留有据）**：RegisterForm 提交按钮保留 `emerald` 字面色阶而非 primary 语义 token——因用户诉求「副色与登录后首屏 /dashboard 匹配」，emerald 即 /dashboard KPI 副色之一；登录主按钮 primary 主色、注册按钮 emerald 副色，符合主/次动作区语义。emerald 不在禁闭色。

**逻辑零改动**：认证逻辑（预填、自动登录、redirect 安全回跳、401/403 表单横幅、409 字段/toast）均于 task15+ 已整合，本次不触碰 handler/条件。

## 四、质量门禁（全部通过）
- `tsc --noEmit`：0 错误
- ESLint：auth 域 `--max-warnings 0` = 0 warning（全量 warning 均为既有文件，非本任务引入）
- Vitest：**71 files / 485 tests PASS**
- `next build`：成功（`/`、`/login`、`/register` 路由存活）
- CSS 审计 5 项（hex 内联/内联色/禁闭色 sky-violet-cyan-teal-fuchsia/任意字号/灰系）：auth 域 0 命中
- **独立子代理审查（general_purpose_task）**：token 有效性、契约未破坏、a11y 无退化 全通过；唯一提示为 emerald 取舍（已评估保留）

## 五、契约⑬ 对齐说明
- 壳消费：api-client 拦截器剥壳；`ApiError.code` 保留字符串码（40111/40912/40101/AUTH_EXPIRED）
- `isAuthEndpoint`：/login /register 失败在表单页原地渲染（不触发全局登出重载）
- AUTH_EXPIRED：非认证接口 401 → toast「登录已过期」+ 清 token + 跳 `/login?redirect=原路`

## 六、已知边界
- 无 MOCK：表单字段/端点均真实契约，失败态为真实 shell 驱动
- 注册 409 冲突定位依赖后端 message 关键词（契约仅定 `40912` 全局码，未细分字段）；无法定位时回退 toast（规范已写明）

## 七、下一步
- 看板 task42=DONE（sync.ps1 分发）
- git commit（含 task42 编号）
- 停等编排者验收，未验收不开始 task