# task60 验收批判（强制技术批判）

> 对象：task60 /admin/users 管理端用户（TraeWork，commit c790735）
> 结论：**验收通过**。

## 实证结果
- commit `c790735`（11 文件 +1451/-311）；page/UserTable/EditUserDialog/UserLearningDialog/users.ts 交付 + admin-users.html。
- tsc 0；Vitest **71 文件/485 测试全 PASS**（本任务新增 13）；ESLint 0；next build 成功（/admin/users Static）。
- grep 审计 4 文件全 0（报告所述 -translate-y-1/2 命中非源码违规）；candy-playful 去 slate/hex/内联色/任意字号。
- GWT①防抖400ms+组合查询+分页；GWT②学习详情 6 指标+最近动态；GWT③最后 admin 红线（前端禁用+红线条幅+后端40303兜底）。

## 批判 1（P1）：GET /api/admin/users/{id}/learning 后端未接线，6 指标为结构占位
- **问题**：学习详情端点后端路由未注册，当前展示字段结构占位（契约缺口实披露，不写 MOCK——符合纪律）。
- **证据**：task14 契约⑤覆盖 /me+learning-summary，但 /api/admin/users/{id}/learning 未见后端实现。
- **方案**：**需后端补接线**（列入后端排期，联调节点），接线后前端自动渲染真实聚合。

## 批判 2（P2）：MutationCache 对 401/403 早退，EditUserDialog 依赖组件级 onError 兜底
- **问题**：全局 MutationCache 对 401/403 早退会吞掉错误，EditUserDialog 需本组件补齐 toast，存在被绕过风险。
- **方案**：task37 清理或后续统一错误处理时复核 MutationCache 与组件级兜底的覆盖一致性。

**结论**：批判①阻塞后端接线（非前端），task60 本体验收通过。