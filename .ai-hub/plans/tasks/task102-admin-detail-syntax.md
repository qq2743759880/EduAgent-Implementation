# task102 — admin 详情页 SyntaxError 修复 + `?id=` 取参统一

- 域：FE ｜ 平台：trae ｜ 波次：W0 ｜ 依赖：task101 合入
- 文件：`admin-course-detail.html`、`admin-question-detail.html`、（新增工具函数入 edu-api.js 或页面内共享片段）

## 目标
救活两个整块失效的注入脚本，并终结全站三种 id 传参风格并存（路径正则/query/localStorage）的混乱。

## 证据
- audit §1.1/§四-1：两页 L781 写 `location.pathname.match(//(d+)/)`，`//` 被解析为行注释 → 该 `<script>` 块 SyntaxError，数据注入与未登录提示 IIFE 全不执行。
- audit §1.2：learning.html:3191、admin 两详情页均期望路径式 URL（`/learning/{a}/{b}`、`/admin/courses/{id}`），静态服务下永不匹配。

## 改动点
1. 修复两页正则为对 `location.search` 的解析：`new URLSearchParams(location.search).get("id")`，缺失时取列表页默认第一条或显示"未指定 id"空态（禁止再硬编码回退 1001）。
2. 在 edu-api.js 增加 `EAPI.pageId(name)` 统一取参工具（query 优先），后续 task103/119 复用。
3. 两页未登录提示 IIFE 恢复执行（随语法修复自动恢复，验收确认）。
4. admin-question-detail 的 `stem_html` innerHTML 注入改为文本安全渲染（先 textContent，富文本渲染统一归 W3 评估 XSS 白名单）。

## GWT 验收
- Given admin token，When 打开 `admin-course-detail.html?id=<真实系列id>`，Then 页头/班次/模块课次区块渲染该系列真实数据（DevTools Network 200 且 DOM 出现系列名）。
- Given 打开同页**不带 id**，Then 显示空态提示而非错装 1001/上一条数据。
- Given 学生 token 访问两页，Then 显示"请以管理员登录"提示（原来因脚本失效该提示也不出现）。
- 机验：`node -e` 对两页 script 块做语法解析（new Function）无 SyntaxError；全站 `grep -n "match(/" *.html` 无 `//(d+)` 类损坏正则残留。

## 风险
- 两页表格结构同样存在列错位（audit §1.1），本期只救活脚本+对齐主字段，列错位精修归 task106，避免任务膨胀。
