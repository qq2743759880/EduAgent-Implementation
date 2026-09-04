# task121 — me 资料编辑 + dashboard 快捷入口接线

- 域：FE ｜ 平台：trae ｜ 波次：W3 ｜ 依赖：task101；C-A 冻结后复核 users/me 契约
- 文件：`me.html`、`dashboard.html`

## 目标
个人中心从只读变可编辑；仪表盘快捷入口不再是无 handler 死按钮。

## 证据
- audit §四-4：me.html:4219"编辑资料"无 handler；dashboard.html:348-349"个人中心/调整偏好"无 handler。
- 后端契约：`GET/PUT /api/users/me/profile`（UserProfile：nickname/avatar_url/gender/birthday/grade_code/weekly_available_hours/learning_goals[]/subject_preferences[]/interest_tags[]，PUT 全 Optional 部分更新）；gamification points（等级徽标已有）。
- audit §X3：me 统计字段已由 task105 对齐，本任务只做编辑路径。

## 改动点
1. "编辑资料"弹窗化：昵称/性别/生日/年级/每周可用时长/学习目标（多选）/学科偏好（多选）——按 UserProfile 实测字段裁剪；保存接 `PUT profile`（只发改动字段），成功后头部资料区即时更新。
2. dashboard 快捷入口接真实跳转："个人中心"→me.html；"调整偏好"→me.html 编辑弹窗直开（URL 参数 `?edit=1`）或 courses 兴趣选择（取实现小者）；其余快捷卡逐一绑定或移除（不留死按钮）。
3. 头像：后端若有 avatar_url 字段则支持 URL 粘贴更新（不做文件上传，后端无存储端点）。

## GWT 验收
- When 修改昵称与每周可用时长并保存，Then PUT 请求 payload 仅含改动字段，刷新后仍为新值（DB users 实证）。
- When dashboard 点"个人中心"，Then 进 me.html；点"调整偏好"，Then 直达编辑弹窗或偏好页，**无任何无响应按钮**。
- 机验：dashboard.html 快捷入口全部有 click 绑定（脚本断言）；me.html `grep "编辑资料"` 处有 handler。

## 风险
- UserProfile 字段命名在 C-A 前后不同（learningGoal vs learning_goal），编辑表单取值统一走 task105 已对齐的读取层，避免二次错配。
