# task107 — admin-questions.html 真实接入

- 域：FE ｜ 平台：trae ｜ 波次：W1 ｜ 依赖：task101
- 文件：`admin-questions.html`（当前全页 0 注入）+ `admin-question-detail.html` 读详情（task102 已救活脚本）

## 目标
把管理端唯一纯演示页接入真实题库 API：题库列表、题目列表、题目详情、批量导入（预览+执行）。

## 证据
- audit §1.1：admin-questions.html 全文 0 处 EAPI/edu-api.js，却挂在管理端导航；无登录提示。
- 后端可用契约（domains/question_admin/router.py）：`GET/POST/PATCH/DELETE /api/admin/questions/banks*`、`GET banks/{bank_id}/questions`、`GET/POST/PATCH/DELETE questions*`、`POST import-preview / import-execute`、`GET types`；分页统一 page/page_size，DTO `{total,page,page_size,items}`。
- 历史死契约已清理（b36e1aa 删 batch-import/papers/compose/tags），**不得复活**。

## 改动点
1. 注入 edu-api.js；题库 Tab 接 `GET banks?page=&page_size=`；题目 Tab 按 bank 过滤接 `GET banks/{id}/questions`。
2. 新建/编辑按钮：列表内联表单接 POST/PATCH（最小字段：题干、题型、选项、答案、解析——按 schemas 实测字段）；详情页跳 `admin-question-detail.html?id=`。
3. 批量导入向导接 `import-preview`（上传后展示预览统计）→ `import-execute`（确认后执行，展示成败计数）。
4. 考试管理区块若后端 exams 端点稳定可只读接入；不稳则隐藏区块（不做假功能）。
5. 未登录/非 admin 提示与 task109 守卫统一实现。

## GWT 验收
- Given admin token，When 打开 admin-questions.html，Then 题库/题目列表渲染真实数据（与 curl 返回 items 一致）。
- When 新建一道单选题并保存，Then `GET questions` 可见该题且详情页可打开；When 走导入向导上传 ≤10 题 md 文件，Then 预览显示解析条数、执行后返回成败计数与列表新增一致。
- Given 学生 token，When 打开本页，Then 显示无权限提示且不发 admin 请求。
- 机验：`grep -c "edu-api.js" admin-questions.html` ≥1；页面头注释更新为实际消费端点清单（契约注释纪律）。

## 风险
- 题目 schema 字段较多（题型枚举 SINGLE/MULTI/JUDGE/FILL/DRAG_SORT/MATCH），首期只做单选/多选/判断三类的新建编辑，其余题型只读展示——范围写进完工报告。
