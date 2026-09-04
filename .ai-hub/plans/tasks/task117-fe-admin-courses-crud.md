# task117 — 前端：admin-courses CRUD 真实接线

- 域：FE ｜ 平台：trae ｜ 波次：W2 ｜ 依赖：**task116 DONE**（完成依赖）+ C-C 契约已验收；task101 合入
- 文件：`admin-courses.html`

## 目标
把管理端课程列表的"保存/上架/下架/删除"从 alert 占位变成真实 CRUD。

## 证据
- audit §四-5：admin-courses.html:534-537 上架/下架/删除/保存全为 alert/toast 占位。
- audit §1.1：本页注入"部分有效但列语义错位"（列错位归 task106，本任务只做写路径）。
- 后端契约：`POST/PATCH/DELETE /api/admin/courses/series*`（domains/course_admin/router.py:39-81，ADMIN/MGR）。

## 改动点
1. 新建系列：弹窗表单接 `POST series`（必填 series_code/series_name/delivery_mode 等，按 schemas 实测；409 重复码提示已存在）。
2. 编辑：行内"编辑"接 `PATCH series/{id}`（局部字段）。
3. 上架/下架：接 sale_status 切换（PATCH 或专用动作，按后端实际形态）。
4. 删除：确认弹窗文案按 C-C 改为"下架（可含 include_deleted 恢复）"，调 DELETE；成功后行从默认列表消失。
5. 全部写操作后局部刷新列表；错误按 task101 onError 显示（409/422 文案直读 message）。
6. 视频上传按钮明示"占位"（后端 4 端点 stub，audit §2.2），禁调假接口。

## GWT 验收
- Given admin token，When 新建系列（唯一 code），Then 列表立现该行且 DB 有记录；When 重复 code 再建，Then 提示冲突不崩溃。
- When 编辑名称并保存，Then 刷新后为新值；When 下架某系列，Then 行状态变更；When 删除，Then 行从默认列表消失（C-C 语义）。
- 机验：`grep -c "alert(" admin-courses.html` 写路径相关 = 0（允许保留与后端无关的纯前端提示则逐一标注）。
- 回归：task106 的列语义断言不回退。

## 风险
- 表单字段较多，首期只做列表页主字段（code/name/mode/status/price），详情页字段编辑归后续 task78~91 批次。
