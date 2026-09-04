# 对抗性测试报告 fx-task02

## 第 1 次测试

### 判定：FAIL（一般 2 + 轻微 3；无 BLOCKER）

- 测试时间：2026-08-13
- 测试方式：源码审查 + 真实打靶双轨（后端 8000 运行中，admin/Admin@12345 与 student 账号实测）
- 落盘说明：本报告由主编排器依据 sd-challenger 会话完成的分析结论落盘（challenger 输出目录权限被拒，分析已 100% 完成）

---

### 问题清单

| # | 维度 | 严重度 | 位置 | 质疑 | 建议 |
|---|------|--------|------|------|------|
| 1 | 错误处理（红线 4 违反） | 一般 | `src/lib/query-client.ts:8-24`（globalOnError） | 全局错误兜底仅 toast.error 无 console.error；dev-plan 红线 4「写操作失败必须 toast + console.error」未完全达成 | globalOnError 补 console.error；已修正的 useMutation 双通道为范本 |
| 2 | 安全（前端角色自欺面） | 一般 | `src/lib/admin-guard.tsx`（AdminGuard 读取 localStorage role） | AdminGuard 信任可篡改的 localStorage 角色、无 JWT 声明校验；实测伪造 roles 可短暂绕过前端拦截（管理端壳短暂可见），被后端 401 兜底。前端守卫是 UX 层非安全层——需确认后端 require_role([ADMIN]) 为权威（已确认），前端绕过不可达数据 | 前端不修（成本高、收益低）；文档明确「前端守卫非安全边界，后端权威」；可选：登录态校验时校验 JWT payload.role 与 store 一致 |
| 3 | 错误处理（静默登出） | 轻微 | auth-client.ts 401 处理 | 403 静默登出无 toast 提示，用户不知被登出 | 403 时 toast 提示（保留 silent 登出为 401 专用） |
| 4 | 安全（open redirect 生成端） | 轻微 | `admin-guard.tsx:73` | 生成 redirect 参数时 `from` 为 usePathname() 内部值（低风险）；消费端 GuestOnlyRoute 已过 isSafeRedirect（redirect.ts:17-23，`/^(?![/\\])` 实测拒 `//evil.com`） | 生成端同步过 isSafeRedirect（统一口径），或注释说明 from 恒为站内路径 |
| 5 | 文档口径 | 轻微 | admin guard SSR meta | SSR meta/文案口径与守卫实际行为有偏差 | 修正文案 |

---

### 守卫绕过审计（含 SSR 泄漏检查）

| 检查项 | 结果 |
|--------|------|
| SSR HTML 泄漏管理端菜单/数据 | 未泄漏（AdminShellSkeleton 仅占位结构，菜单数据经 ADMIN_NAV_ITEMS 纯常量渲染，无业务数据） |
| 伪造 localStorage roles 绕过 | 可短暂显示壳，后端 401 权威兜底，数据不可达（问题 #2） |
| 未登录直访 | /login?redirect= 回跳正确（fe-tester 35 用例 + 浏览器实测） |
| 权限矩阵 | 后端 /api/admin/* require_role([ADMIN]) 保持权威（edu-agent/app/admin/** router 抽查） |
| isSafeRedirect | redirect.ts:17 `^\/(?![/\\])...` 实测拒绝 //evil.com / http:// / javascript:（redirect.test.ts 12 用例） |

### 契约比对（admin-api-types.ts vs 后端 admin schemas）

逐字段比对：admin-api-types.ts 与 edu-agent/app/admin/{course_admin,question_admin,user_admin,rag_admin}/schemas.py 核心字段一致；错误壳 `{code,message,detail}` 三字段归一（api-client.ts 拦截器实证）。

---

### 结论

无 BLOCKER，核心安全边界（后端 require_role 权威 + isSafeRedirect 消费端 + SSR 无泄漏）已就位。问题 #1（query-client.ts）归 fe-task00 全局处置；#2 记入薄弱点（后端权威已确认）；#3/#4/#5 可随 fe-task00/fx-task05 顺手修正。
