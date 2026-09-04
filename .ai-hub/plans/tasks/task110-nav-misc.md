# task110 — 动线杂修（死链/返回/孤立页入口）

- 域：FE ｜ 平台：trae ｜ 波次：W1 ｜ 依赖：task101~103 合入后做终态修整
- 文件：`admin-courses.html`、`admin-question-detail.html`、`community.html`、`my-cohorts.html` 等散点

## 目标
清零全部死链与孤立页，让每个页面都有入口、每个链接都有去处。

## 证据
- audit §1.2-2/3：admin-courses.html:482 死链 `href="/admin/courses/${s.id}"`（唯一"列表→课程详情"出口）；admin-question-detail.html:766 doBack 只 alert 不返回；course-detail/learning/admin 两详情页为孤立页；community-post 仅能靠手输 `?post_id=` 到达。
- audit §1.1：my-cohorts.html:509/519 错误态"重试"/空态"去选课"按钮无 handler；admin-dashboard.html:440 错误态重试无 onclick。

## 改动点
1. admin-courses 行操作"班次/详情"改为 `admin-course-detail.html?id=${s.id}`（与 task102 取参一致）。
2. admin-question-detail `doBack` 改 `location.href="admin-questions.html"`；admin-course-detail 同理回 admin-courses.html。
3. community.html 帖子标题/摘要加链接 `community-post.html?post_id=${id}`（与现有注入 id 字段一致）。
4. my-cohorts"重试"绑真实重载、"去选课"跳 courses.html；admin-dashboard 错误态重试绑 reload；dashboard.html:348-349 快捷入口（个人中心/调整偏好）分别跳 me.html 与 courses.html（quick links 完整接线归 task121，本任务先保证无死按钮）。
5. learning.html 入口由 task103 产生（班次卡"去学习"），本任务做全站链接复扫确认无孤立页。

## GWT 验收
- 机验（权威）：脚本遍历 22 个 html 的全部 `href` + 注入模板字符串中的跳转，目标文件全部存在且 query 参数名与目标页取参一致——**死链 = 0**。
- 反向遍历：除 login-register 外每页至少 1 个入站链接——**孤立页 = 0**。
- Given admin token，When 在 admin-courses 点某行"班次"，Then 打开对应系列详情页（id 一致）；When 在两个详情页点返回，Then 回对应列表页。
- 人工走查：community 列表→详情→返回→列表动线、courses→detail→learning 动线各走一遍无断点。

## 风险
- 链接扫描脚本需识别模板字符串（`${id}`），按前缀匹配文件名即可，不追求解析 JS。
