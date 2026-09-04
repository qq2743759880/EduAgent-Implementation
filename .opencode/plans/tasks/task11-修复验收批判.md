# task11-fix 验收批判（补充）

> 依据：全局规则「任务审核验收强制技术批判」+ 6 点原则
> 对象：task11 P0 修复（RespWrap 透传 + 中间件链 + 契约补测）
> 结论：**✅ 验收通过**（P0 修复实证全绿），2 条补充批判（P2，不阻塞）

---

## 修复实证结果（真实 HTTP，最新代码服务）

| 项 | 实测 |
|----|------|
| 匿名 /api/admin/users | ✅ **401 + code="40101" + data=null + x-trace-id + www-authenticate: Bearer**（P0 修复生效，不再 500）|
| student → admin | ✅ **403 + code="40300" + data=null + x-trace-id** |
| 限流 429 壳 | ✅ 契约测试 test_rate_limit_429_shell（报告）+ 手动验证 x-trace-id |
| resp_wrap dict 透传 | ✅ 源码确认两处 list→dict（含 P0 根因注释）|
| 中间件顺序 | ✅ Trace 移至 CircuitGuard 后/RespWrap 前（外层），X-Trace-Id 不丢 |
| trace_id_var 统一 | ✅ auth_middleware import app.core.trace 同一实例 |
| 契约测试 | ✅ 13 PASS + 1 FAIL(限流用例自身) + 1 skip（与报告一致，限流重置后复测）|

## 批判 4（P2）：修复代码未 git commit

**问题描述**：实测时 `git status` 显示 4 个文件改动未提交（main.py/auth_middleware.py/resp_wrap.py/test_contract_all_routers.py），git log 仍停在 3f2d237（task11 原始 commit）。报告称"git commit + sync 全部就位"与实际不符——修复未落 commit，若丢失则 P0 修复白做。

**证据来源**：`git status --short`（4 个 M 文件）；git log -3（无新 commit）。

**优化方案**：编排者补执行 `git commit`（task11-fix）+ sync；或要求 Trae 补提交。已由编排者处理。

**预期收益与成本**：收益=修复可追溯可回滚；成本=0。

## 批判 5（P2）：test_rate_limit_on_auth 用例自身无限流控制（缺陷用例）

**问题描述**：该用例登录 3 次断言全 200，但契约套件其他用例已消耗限流额度（auth/login 10/min）→ 偶发 429 → assert 失败。实测复现（限流重置后 1 FAIL 恰为此用例）。这是**测试环境污染 + 用例设计缺陷**（critique ③ P1 已知，修复方案 C 计划中）。

**证据来源**：test_contract_middleware.py:147 `assert 429 == 200`；限流配置 `auth/login: (60, 10)`。

**优化方案**：按优化修改方案 C——module 级 fixture 复用 admin_token（登录一次），或测试专用限流豁免 env。列入 task10 契约重构 + task98 CI 门禁。

**预期收益与成本**：收益=测试确定性；成本=1h（已计划）。

## 总评

| 原批判 | 状态 |
|--------|------|
| ① RespWrap S2 透传（P0）| ✅ 修复（dict 透传）+ 实证 401/403/429 壳正常 |
| ② 契约补测 | ✅ test_admin_anonymous_401/403/429 用例新增 |
| ③ 限流豁免（P1）| ⏳ 未解决（批判⑤ 归属），转 task10 重构 + task98 |

**结论：task11 验收通过（P0 修复 + 安全补强 + 契约冻结② 主体全部达标）。** 剩余批判③/⑤（限流测试环境污染）为已知 P1，不阻塞 task12 开工，但需在 task10 契约重构/task98 中解决。修复代码已由编排者补 commit。
