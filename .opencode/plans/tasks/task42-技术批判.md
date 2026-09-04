# task42 验收批判（强制技术批判）

> 对象：task42 /login + /register 认证页 + /根路由（TraeWork，commit f74bf99）
> 结论：**验收通过**。

## 实证结果
- commit `f74bf99`（8 文件 +3217/-23）；AuthCard/LoginForm/RegisterForm/protected-route/page.tsx 交付 + task42-auth-pages-spec.md + login-register.html。
- 路由确认：(user)/login、(user)/register、根路由 page.tsx、protected-route.tsx 全部存在。
- tsc 0；Vitest **71 文件/485 测试全 PASS**；ESLint 0；next build 成功（/login、/register 注册）。
- grep 7 文件全 0（candy-playful token 化：sky→primary-soft、slate→muted-foreground、text-xs 去 arbitrary）。
- 契约⑬字符串码（AUTH_EXPIRED/40111/40912/40101）ApiError.code 透传 + isAuthEndpoint 表单原地渲染防重载。

## 批判 1（P2）：登录态持久化依赖 session/token 机制，重载/刷新场景未端到端验证
- **问题**：protected-route 守卫已实现，但 token 持久化（localStorage/HttpOnly cookie）与刷新后恢复登录态未端到端确认。
- **方案**：task69 E2E 或后续补刷新/多标签登录态保持用例。

## 批判 2（P2）：redirect 回跳透传在深层路由/带 query 场景未全覆盖
- **问题**：/login?redirect={原路} 透传已实现，但带 query 参数的深层路由回跳（如 /admin/users?page=2）未验证。
- **方案**：task69 E2E 补 redirect 含 query 回跳用例。

**结论**：两条为后续验证项，不阻塞 task42。