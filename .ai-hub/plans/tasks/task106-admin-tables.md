# task106 — 管理端表格列错位修复 + admin-mcp 契约更正

- 域：FE ｜ 平台：trae ｜ 波次：W1 ｜ 依赖：task101；C-A/C-B 冻结后复核
- 文件：`admin-courses.html`、`admin-users.html`、`admin-mcp.html`、`admin-rag-upload.html`（任务表部分）

## 目标
修复 4 个管理端列表"值塞错列 + 抹掉操作列"的注入缺陷，并更正 admin-mcp 的过时契约注释。

## 证据
- admin-courses.html:547：5 值（code/name/delivery/status/price）对 表头（系列名/交付/状态/时间/操作）全错位，操作列被覆盖。
- admin-users.html:629：4 值塞 7 列头；admin-mcp.html:383：4 值塞 6 列头；admin-rag-upload.html:599：4 值塞 8 列头。
- audit §X6：admin-mcp 头注释契约写 `/api/admin/mcp/servers`，后端实际路由 `/api/mcp/servers`（ADMIN 中间件兜底）——**前端调用路径正确，注释过时**；响应字段 `{name, transport, last_health_ok, tool_count}` 需按 mcp schemas 实测核对。
- admin-rag-upload 的 collections 计数无目标 DOM（`[data-collection-count]` 不存在）。

## 改动点
1. 四页注入渲染改为"按表头语义逐列映射 + 操作列 DOM 保留"（操作按钮绑定归 task116/117 与后续任务，本期先不抹掉按钮）。
2. admin-mcp：更正头注释为真实路由；字段实测后对齐；`health-scan` 按钮（若绑）标注"响应 ~50s"（L7 后端异步化不在本期，前端先加超时提示）。
3. admin-rag-upload：collections 计数补目标 DOM；任务表列对齐 `{task_id|id, status, total_chunks, created_at}`（实测 knowledge/tasks 返回）。
4. 各页错误分支不再 `catch(function(){})` 静默：接 task101 的 onError 显示行内错误条（toast 统一样式归 task122）。

## GWT 验收
- Given admin token，When 依次打开 4 页，Then 每列表每行各列语义与表头一致（截图 4 张比对），操作列按钮可见可点（点击行为允许 alert 占位但需标注"待 task117"）。
- When 打开 admin-mcp.html，Then 头注释与实际请求路径一致；Server 表字段与 curl `/api/mcp/servers` 返回逐字段一致。
- 机验：注入行渲染代码列数 === 表头列数（脚本断言）；`grep -n "api/admin/mcp" admin-mcp.html` = 0（仅允许 /api/mcp）。

## 风险
- mcp/knowledge 响应若为裸 dict 弱类型（audit §B4/P2-16），字段核对以实测 JSON 为准并回写页面头注释（契约注释即本站契约来源）。
