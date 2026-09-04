# task22 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task22 after_sales/ticket 域（Trae，commit 5772215）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `5772215`（10 文件 +781）|
| 交付物 | ✅ after_sales 四件套 + task22-contract.md + 报告 + test_contract_task22.py |
| 契约测试 | ✅ **task22 7/7 + task20/21 回归 15/15 = 22 passed 实跑** |
| GWT① appeal 创建 | ✅ 200 + ticket_id=8275 + type=appeal + **first_response_at=None**（等待受理）|
| GWT② user 隔离 | ✅ stu 访问 adm 工单 → **404 + code=40441**；adm 本人 → 200 |
| GWT③ 满意度幂等 | ✅ 首次 submitted=True(5)，再次 **submitted=False**（幂等）|
| GWT④ 过滤分页 | ✅ 200 + total=7 + items=5（TicketPage）|
| 契约裁定 | ✅ 对齐 api-request §7 + 前端 tickets.ts（4 端点 + 4 type）|
| contract-diff | ✅ Ticket 14 字段 / TicketPage 4 字段零差异 |

## 批判 1（P2）：8003 服务需重启加载新域（旧进程 404）

**问题描述**：实证时 8003 进程（10:13 启动）未加载 task22 after_sales 域（创建工单 404），重启后正常。Trae 报告称"服务留存 8003"但未确认加载最新代码。

**证据来源**：实测 404 → 重启后 200；进程启动时间早于 commit。

**优化方案**：不阻塞（重启后全绿）。后续任务验收前确认服务加载最新代码（或依赖 in-process ASGI 契约测试）。

## 批判 2（P2）：满意度幂等返回 submitted=False（非错误响应）

**问题描述**：重复评分返回 200 + submitted=False（幂等成功），而非 4xx 错误。语义 = 不重复生效（DB 仅 1 条），但前端若需区分"已评分"提示，200 幂等响应需前端判断 submitted 字段。

**证据来源**：实测再次评分 submitted=False；报告满意度幂等（ticket_id 唯一）。

**优化方案**：不阻塞（幂等正确）。前端 task68 实现时用 submitted 字段区分"已评分"提示。

## 总评

| GWT | 结果 |
|-----|------|
| ① appeal 创建 + first_response_at 空 | ✅ 实测 |
| ② user 隔离（越权 404）| ✅ 实测 40441 |
| ③ 满意度幂等 | ✅ 实测 submitted=False |
| ④ 过滤分页 TicketPage | ✅ 实测 total=7 |

**结论：task22 验收通过。** 契约冻结⑫ 生效 → 解锁前端 task68（/tickets 页）。批判 1/2 均 P2（服务重启 / 前端区分已评分语义）。
