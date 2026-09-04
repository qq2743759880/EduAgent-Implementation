# task15 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task15 存量模块壳适配（Trae，commit 9483e9e）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `9483e9e`（14 文件 +1122/-165，6 模块）|
| 交付物 | ✅ task15-contract.md + 报告 + test_contract_task15.py + _smoke_task15.py |
| 契约测试 | ✅ **20/20 PASS 实跑**（17.35s）|
| auth/community/gamification 壳 | ✅ 200 + {code,message,data}（实测）|
| mcp/rag_admin 壳 | ✅ 401 + 壳 40101（权限不足但壳化正常）|
| gamification ZSET | ✅ Redis 直查：4 周期 key（DAILY/WEEKLY/MONTHLY/ALL_TIME）`g-rank:{scope}:POINTS:{period}` 格式正确，积分实时累计 |
| chat SSE done 内嵌 | ✅ done 事件 data 含 {code:0,message:"ok",data} 结构（源码确认）|

## 批判 1（P2）：mcp/rag_admin 端点实测 401（非壳问题，权限待确认）

**问题描述**：实测 `GET /api/mcp/servers`、`GET /api/admin/rag/collections` 返回 **401 + 壳 40101**（非 200）——因 adm02test 可能缺 mcp/rag_admin 所需权限，或这些接口需特定角色。壳化本身正常，但 401 说明**真实可用性未验证**（报告声称 mcp 18 端点壳化，未验证有权限下的 200 响应）。

**证据来源**：实测 401；报告 mcp 18 端点壳化声明。

**优化方案**：不阻塞（壳化已确认）。前端 task62（admin/mcp）、task61（admin/rag）联调时用 ADMIN token 验证 200；若权限模型需补，转 task70~91 管理端补全。已在交接单注明。

## 批判 2（P2）：test_auth_service/test_error_codes 存在存量字符串码/整数码断言 bug（记录待修）

**问题描述**：报告自述 `test_auth_service / test_error_codes` 中 `assert '40312' == 40312` 之类为存量字符串码/整数码断言 bug——非 task15 引入、非 task15 范围，仅记录。该 bug 会导致错误码类型断言失效（测试假绿）。

**证据来源**：报告范围外说明。

**优化方案**：转 task37（清理/测试修复）或 task98（验收体系）统一处理：断言统一为字符串码。不阻塞 task15。

## 总评

| GWT | 结果 |
|-----|------|
| ① 契约测试 6 模块 100% 壳 + SSE done 内嵌 | ✅ 20/20 全绿 + 实测壳化 + SSE 源码确认 |
| ② 排行榜 ZSET + 积分 1s 内可查 | ✅ Redis 4 周期 key 实证 + zincrby/zrevrange |
| ③ auth 壳统一但 JWT 语义不变 | ✅ auth/me 壳化 + 契约测试 |

**结论：task15 验收通过。** 契约冻结⑬ 生效 → 解锁前端 task42/50/51/52/53/55/60/62。批判 1/2 均 P2（权限联调待确认 / 存量断言 bug 转 task37）。
