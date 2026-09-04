# task116 — 后端：系列删除语义落定（冻结 C-C）

- 域：BE+契约 ｜ 平台：claude ｜ 波次：W2 ｜ 依赖：无（D3 确认后可开工）
- 类型：**契约变更**（冻结单 handoffs/task116-contract.md）；**完成依赖方**：task117

## 目标
消除"DELETE 返回删除成功但记录仍在列表"的假删除缺陷（L2）。

## 证据
- interface-acceptance.md P1：`DELETE /api/admin/courses/series/{id}` 返回 200 code=0"系列删除"，GET/DB 确认记录仍在（仅 sale_status→off_sale）。
- audit §1.2：前端 admin-courses 的删除确认弹窗文案宣称"删除"，用户感知为假删除。
- 关联现状：孤儿模块 `app/admin/question_admin/`（audit §2.3）与本任务同属"管理端语义清理"，归档动作一并执行（D5 默认归档 `_archived/`）。

## 改动点
1. 按 D3 默认方案落定：DELETE series = 软删下架（sale_status=off_sale + yn=0），响应 message 明示"系列已下架"；列表接口默认过滤 `yn=0`，`?include_deleted=true` 仅供管理端回收站（本期只留参数，不建 UI）。
2. 若无引用约束（无班次/订单），提供真删路径：`DELETE ?hard=true` 仅 ADMIN 角色且 DB 外键校验通过——契约单写清两条路径与错误码。
3. cohorts/modules/sessions DELETE 语义一致性核对（同口径：软删优先），差异写入契约单。
4. 归档孤儿模块 `app/admin/question_admin/` → `app/_archived/question_admin/`（不参与 import），全仓 grep 确认零引用。
5. POST series 重复 series_code 返回 409（b36e1aa 已修 ConflictError，回归确认）。

## GWT 验收
- Given admin token，When DELETE `/api/admin/courses/series/{id}`，Then 响应 code=0 且 message 含"下架"；`GET /api/admin/courses/series` 默认列表**不再出现**该系列；DB 行仍在且 sale_status=off_sale。
- When `?include_deleted=true`，Then 该系列可见（回归站字段可辨）。
- When hard=true 对有班次引用的系列，Then 409/422 带明确错误码（不可静默）。
- 回归：pytest 涉及域 + interface_acceptance_final.py 全绿；孤儿模块归档后 `python -c "import app.main"` 正常启动。

## 风险
- "下架 vs 删除"文案需前后端一致（task117 同步改确认弹窗文案），写入 C-C 契约单避免再次错配。
