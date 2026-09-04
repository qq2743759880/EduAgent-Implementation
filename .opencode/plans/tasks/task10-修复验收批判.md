# task10-fix 验收批判（补充）

> 依据：全局规则「任务审核验收强制技术批判」+ 6 点验收原则
> 对象：task10-fix 错误码 int→str 修复（commit 993df37）
> 结论：**验收通过**（修复正确、实证全绿），补充 2 条批判（P1 级，转后续任务）

---

## 批判 6（P1）：admin 管理端点未强制鉴权 —— 无 token 访问 /api/admin/users 返回 200

**问题描述**：实测 `GET /api/admin/users` **不带 Authorization token 返回 200 + 数据**。task10 中间件仅注册 6 个（SecurityHeaders/Trace/Idempotency/RateLimit/CircuitGuard/RespWrap），**无全局 AuthMiddleware 强制鉴权**。虽 task08 已验证明文带 token 时 require_role 生效（student 403），但**未带 token 的匿名访问未被拦截**（预期应 401）。

**证据来源**：
- 实跑（2026-08-18，服务运行中）：`GET /api/admin/users` 无 token → 200 + items 列表
- `app/main.py` add_middleware 列表（6 个，无 auth）
- `app/middleware/` 目录无 auth_middleware.py（task10 报告称 TraceMiddleware 在 auth_middleware.py 中，但实际无鉴权逻辑）

**与正确做法差距**：生产级 API 需匿名访问管理端点返回 401（未认证）/403（已认证无权）。当前匿名 200 属安全缺口（OWASP 越权访问）。

**优化方案**：不阻塞 task10（其 GWT 只要求响应壳结构）。转 **task11~15 后端域改造** 或新增安全补丁任务：①为 `/api/admin/*` 加全局 AuthMiddleware（Bearer 解析 + 缺失 401 `"40101"`）；②匿名访问保护资源返回 401 壳。列入 task11（course 域首改时）或 task15（存量适配）GWT。

**最小验证方法**：`curl /api/admin/users` 无 token → 401 + `{"code":"40101","data":null}`。

**预期收益与成本**：收益=关闭越权访问漏洞；成本=1~2h（AuthMiddleware + 测试）。

---

## 批判 7（P2）：/health 返回裸 JSON 未包壳（豁免未声明）

**问题描述**：`GET /health` 返回 `{"status":"ok","app":"EduAgent","version":"0.3.0"}` 裸 JSON。RespWrap 白名单含 `/docs` 等但 health 豁免未在交接单/报告中显式声明（响应壳规范应说明 health 是否豁免）。

**证据来源**：实跑 health 响应（裸 JSON）；RespWrap `_SKIP_PREFIXES`（docs/redoc/openapi/favicon，未见 /health）。

**优化方案**：交接单 v1.1 补「health 端点豁免响应壳（运维探活用）」说明，或 RespWrap 显式加入 health 白名单 + 文档声明。P2 低优先级。

**最小验证方法**：交接单 + 实现一致。

**预期收益与成本**：收益=契约无歧义；成本=5 分钟。

---

## 修复质量总评

| 项 | 结果 |
|----|------|
| A1 字符串化 | ✅ 44 字符串码，0 数字残留（实证） |
| A2 契约测试 | ✅ 24/24 实跑 PASS（服务启动后，203s）——首次 24 FAIL 为服务未启动环境问题 |
| A3 交接单 v1.1 | ✅ v1.1 + 字符串声明 + P6 变更日志 |
| A4 报告修正 | ✅ GWT 原文一致（源码+交接单交叉确认） |
| A5 无散装数字码 | ✅ grep 确认（报告 + 契约测试兜底） |
| P6 口径声明 | ✅ 交接单含变更记录 |

**结论：验收通过。批判 6/7 不阻塞（转 task11~15 安全补强 + health 豁免文档化）。**
