# task115 — 后端契约统一②：分页统一 + SSE error 事件（冻结 C-B）

- 域：BE+契约 ｜ 平台：claude ｜ 波次：W2 ｜ 依赖：task114 合入（同域串行更稳）
- 类型：**契约变更**（冻结单 handoffs/task115-contract.md）

## 目标
分页 DTO 全站唯一 `{total,page,page_size,items}`；chat SSE `error` 事件真实可发。

## 证据
- audit §P1-9：课程域返回 `{items, page_meta:{page,page_size,total,total_pages,has_more}}`（domains/course/schemas.py:21-30），与全站其余域（community/market/admin/gamification/refunds）DTO 不同（D2 默认：并入全站 DTO）。
- audit §P1-10：`SseEventType.ERROR` 已定义但 `/api/chat/stream` 生成器无 error 分支（chat/router.py:224-273），流中失败静默转 done+degraded_reason，前端错误分支形同虚设。
- 消费面：courses.html（task103 过渡期读 page_meta）、admin-courses、achievements 分页。

## 改动点
1. 课程域列表/搜索接口改返回 `{total,page,page_size,items}`；`has_more/total_pages` 移入响应扩展字段或由前端计算（契约单明确）。
2. 兼容窗口：保留 `page_meta` 字段一个迭代期（值同源派生），前端 task103 切换后下一迭代删除——兼容策略写入契约单。
3. SSE error 事件：生成器 try/except 分支发 `event: error` + `data:{"code":"<错误码>","message":"..."}` 后安全收束；连接前失败仍走普通 HTTP 错误（契约单明确两段式错误模型）。
4. 前端消费：chat.html error 分支渲染错误气泡（task104 已预留）；courses.html 分页字段切换（随本任务或 C-B 验收后小改）。

## GWT 验收
- `curl "GET /api/series?page=1&page_size=12"` → jq `.total>=0 and .page==1 and (.items|type=="array")`；`page_meta` 在兼容期内同时存在且数值一致。
- Given 强制检索后端报错（如断 LLM key），When POST /api/chat/stream，Then 前端收到 `event: error` 且 UI 显示错误气泡，连接正常关闭（不悬挂）。
- 回归：interface_acceptance_final.py + 前端 vitest + chat 流式冒烟（token 事件正常）全绿。

## 风险
- 兼容窗口内双字段并存要防"老前端读新字段"歧义——契约单写明权威字段与弃用时间表。
