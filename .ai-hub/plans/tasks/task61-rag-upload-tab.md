# task61 — 前端：RAG 控制台上传 Tab 真实接入（沿用既有编号）

- 域：FE ｜ 平台：trae ｜ 波次：W2 ｜ 依赖：**无阻塞**——契约⑥已冻结（handoffs/task36-contract.md），看板 READY
- 文件：`admin-rag-upload.html`

## 目标
把"开始上传"从 demo 进度动画变成真实知识库上传闭环（原 task61，编号沿用看板）。

## 证据
- audit §1.1/§1.3-5：`#upBtn` 只跑 demo 动画，无 `<input type="file">`、无上传 POST——页面核心动作是假的。
- 契约⑥（已冻结）：`POST /api/knowledge/admin/upload`（FormData：md/txt/markdown/pdf/docx，单文件 ≤200MB，20/50 个上限）、`GET /api/knowledge/tasks?page&page_size&status`（倒序）、`GET /api/knowledge/status/{task_id}`、`GET/DELETE /api/knowledge/partitions`；任务状态机 pending/running/succeeded/failed。
- task106 已修本页任务表列错位与 collections 计数 DOM（前置小改，注意合并顺序）。

## 改动点
1. 上传区补真实 `<input type="file" multiple accept=".md,.txt,.markdown,.pdf,.docx">`；选择后逐文件 FormData 调 admin/upload；前端预校验扩展名与大小（200MB）。
2. 上传成功 → 任务表插行（status=pending）→ 轮询 `GET tasks`（5s 间隔，页面隐藏时暂停）刷新状态与 total_chunks；失败行展示 failed 原因字段（按契约⑥）。
3. 分区 Tab 接 `GET /api/knowledge/partitions`（列表）与 DELETE（危险操作二次确认）。
4. 健康环/集合计数对接 `GET /api/admin/rag/collections`（admin-rag-upload 已有调用，字段实测对齐）。

## GWT 验收
- Given admin token 与 3 个测试文档（md/pdf/docx 各一），When 上传，Then 3 个任务行出现并依次 pending→running→succeeded，total_chunks>0（DB/Milvus 实证入库）。
- When 上传 201MB 文件，Then 前端拦截并提示；When 上传 .exe，Then 拒绝。
- When 删除一个测试分区（二次确认），Then 列表移除（验收后清理测试数据）。
- 回归：task106 列语义断言不回退；`grep -c "type=\"file\"" admin-rag-upload.html` ≥1。

## 风险
- VM（Milvus/MinIO）不可达时上传会失败——验收前置检查 VM 状态（08-31 记录已恢复）；不可达则本任务 BLOCKED 上浮，不造假数据。
