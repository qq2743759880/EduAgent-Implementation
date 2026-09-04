# 管理端（B 端）功能补全方案 v1.1

> 触发：用户指出 C 端已有下单/支付/退款/报名/申诉，但管理端无对应管理界面。
> 证据：edu.sql 66 表中 **59 张表后端零引用**、管理端（app/admin）仅引用 series/sys_user 2 张。
> 结论：edu-data 数据模型按完整教培 SaaS 设计，但重构计划的管理端范围只覆盖课程/题库/用户/rag/mcp —— **交易/教务/学员/客服/内容/报表六大管理域整体缺失**。
> **对标来源（真实爬取，2026-08-16）**：使用 `E:\stu\project\提示词工具\crawler`（crawl4ai+Playwright）成功爬取云朵课堂（yunduoketang.com，专业教培 SaaS）4 个功能页 + 小鹅通/ClassIn/粉笔/黑马官网。产出物：`crawler/output_edu/`（11 个 md 文件，含云朵产品功能页 4 份 3336/1961/2660/2769 词）。以下 M1~M9 的"对标依据"列直接引用云朵功能页原文模块名。
> 反爬记录：校管家/小麦助教（DNS 失败）、CCtalk（无 body 反爬）、腾讯课堂/作业帮（JS 渲染词数不足）——均未能爬取；采用云朵课堂作为**同类型专业教培 SaaS** 对标（功能集高度同构）。

---

## 〇、爬取对标结论（云朵课堂功能页 → 本项目管理端模块映射）

| 云朵后台功能（爬取原文） | 本项目对应模块 | 落点 |
|--------------------------|---------------|------|
| 教务工具：智能排课/电子档案/教师管理/**课酬绩效** | M4 排课 + M9 组织师资 | /admin/schedule、/admin/staff |
| 网校管理：数据统计/**权限分配**/**财务审核**/人员管控 | M8 报表 + 新增权限管理 | /admin/reports、RBAC 强化 |
| 多校区：权限划分/课程发布/招生管理/教务管理 | M9 组织（机构/校区/部门） | /admin/org |
| 智能题库：自动阅卷/**错题本**/**成绩统计/错误率/自动排名** | M3 学员作答 + 题库增强 | /admin/students/[id]/answers |
| 订单/交易（云朵无独立页，但行业 SaaS 标配） | M1 订单 + M2 退款 | /admin/orders、/admin/refunds |
| 营销裂变：优惠卡券/拼团/会员积分/分销代理/佣金提现/兑换码 | **新增 M10 营销管理**（超出原方案） | /admin/marketing |
| CRM：客户/跟进/查重/销售统计/通话质检/触发器 | **新增 M11 CRM 线索管理**（超出原方案） | /admin/crm |
| 论坛管理：置顶/删帖权限 | M5 师生交流（班级讨论监控） | /admin/community |
| 公众号群发/标签推送/渠道码 | 二期（依赖微信生态，本项目无） | 排期外 |

> 爬取发现云朵还具备营销（拼团/分销/卡券/兑换码）与 CRM（线索/销售管理）两大域，原 M1~M9 未覆盖 → 补充为 **M10 营销管理、M11 CRM 线索管理**（见 §二 新增模块）。

---

## 一、现状 vs 缺失盘点

| 管理域 | 已有（dev-plan v3.0） | 缺失（本次补全） |
|--------|---------------------|-----------------|
| 课程管理 | ✅ task12/56/57（系列/班次/模块/课次 CRUD + 视频） | 班级学员列表、教师分配、排课日历 |
| 题库管理 | ✅ task13/58/59（题库/题目/解析/导入） | 组卷管理（session_exam 关联题目）、考试发布 |
| 用户管理 | ✅ task60（用户列表/角色/状态） | 学员学习画像、教师档案、机构/校区/部门（org_* 零引用） |
| **交易管理** | ❌ 无 | **订单管理、支付流水、退款审核（HITL）、优惠券管理** |
| **教务管理** | 部分 | **报名管理、考勤管理、作业批改、成绩作答详情** |
| **师生交流** | ❌ 无 | **班级讨论监控、站内信通知、公告发布** |
| **客服售后** | ❌ 无 | **工单管理、申诉处理、满意度统计** |
| **内容运营** | 部分（rag 上传） | **内容审核（ugc_moderation）、课程评价管理** |
| **数据报表** | ❌ 无 | **营收报表、学员转化漏斗、完课率/出勤率** |
| **风控结算** | ❌ 无 | **风控事件、渠道佣金、教师课酬** |

## 二、新增管理端模块详细设计（8 模块，按数据表证据）

### M1 订单管理（对标：校管家订单中心 / 腾讯课堂机构版交易管理）

| 项 | 内容 |
|----|------|
| 数据表 | `order`、order_item、payment_record（全部已建，零引用） |
| 后端接口 | `app/domains/trade/order/admin.py`：GET /api/admin/orders（过滤 status/时间/金额区间/分页）、GET /api/admin/orders/{id}（含 items+payments）、POST /api/admin/orders/{id}/cancel（管理端代取消）、POST /api/admin/orders/{id}/note（备注） |
| 前端页面 | `/admin/orders`：订单列表（订单号/学员/班次/金额/状态徽章/时间）+ 详情抽屉（items+支付流水+退款入口） |
| 状态机 | 复用 C 端 order_status（pending→paid→completed/cancelled/partial_refunded→refunded） |
| 自我批判 | 是否必须？——**必须**。无管理端订单中心则无法对账/仲裁/代操作；优先级 P1（交易闭环的 B 端半） |

### M2 退款管理（对标：教培 SaaS 退款审批流 / 电商售后后台）

| 项 | 内容 |
|----|------|
| 数据表 | refund_request（已建）、payment_record、student_cohort_rel |
| 后端接口 | GET /api/admin/refunds（过滤 status/原因/分页）、GET /api/admin/refunds/{id}、POST /api/admin/refunds/{id}/approve、POST /api/admin/refunds/{id}/reject（含 remark）——**HITL 审批**（LangGraph interrupt，task28 已有设计，管理端是审批入口） |
| 前端页面 | `/admin/refunds`：退款单列表（学员/班次/金额/原因/状态）+ 审批弹窗（通过=执行退款+报名回滚+订单联动；拒绝=填写理由） |
| 与 task28 关系 | task28 已设计 HITL 退款审批（LangGraph interrupt/resume），本模块是其**管理端 UI 落地** |
| 自我批判 | 审批必须人工确认（资金安全红线 R-2）；不引入第三方审批引擎，用 LangGraph interrupt 已够 |

### M3 报名与学员学习管理（对标：校管家学员管理 / 黑马班级管理）

| 项 | 内容 |
|----|------|
| 数据表 | student_cohort_rel（已建）、student_profile、session_attendance、session_video_play、session_homework_submission、session_exam_submission、session_exam_question_rel |
| 后端接口 | GET /api/admin/cohorts/{id}/students（报名学员列表+进度聚合）、GET /api/admin/students/{id}/profile（学习画像：课次进度/出勤/作业/成绩）、GET /api/admin/students/{id}/answers（作答详情：每题的 answer_text/判分/解析）、POST /api/admin/cohorts/{id}/students/{sid}/kick（移出班级） |
| 前端页面 | `/admin/cohorts/[cohortId]`：学员列表（姓名/进度条/出勤/作业完成/考试分）+ 学员详情抽屉（画像+作答明细）；`/admin/students`：全学员搜索 |
| **用户点名"学员成绩班级作答情况"落点** | session_exam_submission + session_exam_question_rel → 每道题作答/得分/解析；班级维度聚合 |
| 自我批判 | 作答详情是学员管理的核心价值（教师要看学生错在哪）；表已齐，只需查询服务 |

### M4 教务排课与考勤（对标：ClassIn 排课系统 / 校管家教务）

| 项 | 内容 |
|----|------|
| 数据表 | series_cohort_session（已建）、session_teacher_rel、session_attendance、staff_profile、org_classroom |
| 后端接口 | GET /api/admin/sessions/calendar（排课日历：教师/教室/时间）、PUT /api/admin/sessions/{id}/teacher（换教师）、GET /api/admin/sessions/{id}/attendance（课次出勤名单）、POST /api/admin/sessions/{id}/attendance（补录考勤） |
| 前端页面 | `/admin/schedule`：月历视图（班次课次/教师/教室/状态）；课次详情含出勤名单 |
| 自我批判 | 排课日历是教培教务核心（ClassIn 主打）；full 档 25k+ 课次需日历懒加载 + Redis 缓存 |

### M5 师生交流：班级讨论监控 + 公告 + 站内信（对标：ClassIn 班级群 / 校管家家校通）

| 项 | 内容 |
|----|------|
| 数据表 | cohort_discussion_topic/post（已建）、community_post（已建）；**公告/站内信需新增 2 张自建表** |
| 新增表 | `announcement`（id, institution_id, title, content, target_scope[all/cohort/grade], publish_status, published_at, created_by, created_at）；`user_notification`（id, user_id, type[system/announcement/teacher_message/ticket_reply/refund_result], title, content, link_url, read_status, created_at） |
| 后端接口 | 公告：GET/POST /api/admin/announcements、PATCH /api/admin/announcements/{id}（发布/下线）；站内信：GET /api/me/notifications、POST /api/me/notifications/{id}/read、GET /api/admin/notifications/send（教师发信给班级）；班级讨论：GET /api/admin/cohorts/{id}/topics（监控）、DELETE（删除违规帖） |
| 前端页面 | `/admin/announcements`（公告列表+编辑器+发布范围选择）；`/admin/messages`（站内信发送台：选班级/学员+模板）；教师端 `/messages`（回复学生） |
| C 端联动 | C 端导航栏新增"消息铃铛"（未读数角标）+ 公告展示位 |
| **用户点名"师生交流/公告发布"落点** | 公告表 + 站内信表是**新增**（edu.sql 未设计），属自建表扩展，符合"保留自建表"模式 |
| 自我批判 | edu.sql 无公告/站内信表（其设计里用 community 论坛代替），但**公告是教培后台标配**（作业帮/猿辅导均有系统公告），新增自建表是正确扩展 |

### M6 客服工单与申诉管理（对标：教培 SaaS 工单中心 / 电商售后台）

| 项 | 内容 |
|----|------|
| 数据表 | service_ticket、service_ticket_follow_record、service_ticket_satisfaction_survey（全部已建，零引用） |
| 后端接口 | GET /api/admin/tickets（过滤 type/status/priority/分页）、GET /api/admin/tickets/{id}、POST /api/admin/tickets/{id}/reply（客服回复→follow_record）、POST /api/admin/tickets/{id}/assign（分配客服）、POST /api/admin/tickets/{id}/close、GET /api/admin/tickets/satisfaction-stats（满意度统计） |
| 前端页面 | `/admin/tickets`：工单列表（类型含 appeal 申诉/优先级/状态）+ 工单详情（时间线：用户→客服多轮）+ 回复框 + 满意度统计卡 |
| **用户点名"申诉客服回复界面"落点** | 工单详情的时间线回复 UI + 申诉类型专属流程（申诉→人工核实→结果回复） |
| 自我批判 | 工单表已建 3 张（含 follow_record 多轮时间线），数据模型完备，只差管理端消费 |

### M7 内容运营：审核 + 评价管理（对标：教培内容审核台）

| 项 | 内容 |
|----|------|
| 数据表 | ugc_moderation_task（已建）、cohort_review（已建）、community_post（已建） |
| 后端接口 | GET /api/admin/moderation（待审列表）、POST /api/admin/moderation/{id}/approve-reject、GET /api/admin/reviews（课程评价列表）、DELETE /api/admin/reviews/{id}（下架违规评价） |
| 前端页面 | `/admin/moderation`（审核队列）；评价管理并入课程详情 |
| 自我批判 | ugc_moderation_task 已建模（任务类型），full 档有 6000 条待审目标，审核台是必备运营工具 |

### M8 数据报表（对标：校管家数据中心 / 猿辅导经营看板）

| 项 | 内容 |
|----|------|
| 数据源 | order/payment（营收）、student_cohort_rel（报名转化）、session_attendance（出勤）、session_video_play（完课）、dim_*（维度） |
| 后端接口 | GET /api/admin/reports/revenue（营收趋势/渠道/课程维度）、GET /api/admin/reports/funnel（曝光→咨询→领券→下单→支付→报名 转化漏斗）、GET /api/admin/reports/attendance（出勤率/完课率） |
| 前端页面 | `/admin/reports`：echarts 报表（趋势线/漏斗图/柱状）；接入现有 dashboard（task55） |
| 自我批判 | 数据全部在现有表（series_exposure_log/visit_log 等曝光表就是为此设计），报表是纯查询层，成本低价值高 |

### M9 组织与师资管理（对标：校管家组织架构 / 多校区管理）

| 项 | 内容 |
|----|------|
| 数据表 | org_institution/campus/department/staff_profile/org_staff_role/org_classroom/org_*_manager、teacher_compensation_bill/item、session_teacher_rel（全部已建，零引用） |
| 后端接口 | GET/POST /api/admin/org/institutions|campuses|departments|classrooms（机构/校区/部门/教室 CRUD）、GET/POST /api/admin/staff（教师档案/角色）、GET /api/admin/compensation（课酬结算单） |
| 前端页面 | `/admin/org`（组织架构树）、`/admin/staff`（教师列表+角色）、课酬并入 |
| 自我批判 | 6 机构分片（institution_id）是数据模型地基，管理端必须有机构/校区/部门管理才能运转；full 档 6 机构 20 校区 120 部门 |


### M10 营销管理（对标：云朵网校营销裂变模块·爬取原文"优惠卡券/拼团/会员积分/分销代理/佣金提现/兑换码"）

| 项 | 内容 |
|----|------|
| 数据表 | coupon/coupon_category_rel/coupon_series_rel/coupon_receive_record（已建，零引用）+ 拼团/分销需新增自建表 |
| 新增表 | groupon_activity（拼团：id, institution_id, series_id, cohort_id, target_count, virtual_count, price, discount_price, start_at, end_at, status, created_at）；distribution_agent（分销：id, user_id, inviter_id, level, commission_rate, created_at） |
| 后端接口 | 券：GET/POST /api/admin/coupons（发券）、GET /api/admin/coupons/receives（核销统计）；拼团：POST /api/admin/groupons（建活动）、GET /api/admin/groupons（列表/状态）；分销：GET /api/admin/distribution（代理树/佣金结算） |
| 前端页面 | /admin/marketing：券管理（发券/统计）+ 拼团活动列表/新建 + 分销代理树 |
| 自我批判 | 云朵将营销列为网校核心模块；本项目 C 端已有点券（task16），补管理端发券+统计即可闭环；拼团/分销为增量营销能力，二期可做 |

### M11 CRM 线索管理（对标：云朵 CRM·爬取原文"客户资料/跟进/查重/销售统计/通话质检/触发器"）

| 项 | 内容 |
|----|------|
| 数据表 | consultation_record（已建，用户点名"咨询改人工申诉"后此表闲置——正好复用为 CRM 线索表）+ org_staff_role（销售角色）+ dim_channel（渠道） |
| 后端接口 | GET/POST /api/admin/crm/leads（线索列表/新建，来源=渠道/咨询记录）、POST /api/admin/crm/leads/{id}/follow（跟进记录）、GET /api/admin/crm/stats（销售统计：线索→成单漏斗）、POST /api/admin/crm/leads/{id}/transfer（客户流转/回收） |
| 前端页面 | /admin/crm：线索列表（渠道/状态/跟进时间）+ 详情（跟进时间线）+ 销售漏斗统计 |
| 与用户决策关系 | 用户曾要求"咨询改为人工申诉"（C 端不建咨询页）；但 consultation_record 表仍在 edu.sql —— 复用为**管理端 CRM 线索**符合数据模型设计意图（云朵 CRM 同源），C 端咨询入口不建、管理端线索管理建 |
| 自我批判 | consultation_record 在 66 表中且有 channel 关联（series_exposure_log 也有）——数据模型本来就设计了获客链路；补管理端 CRM 使其闭环 |

## 三、新增数据库表（2 张自建，其余全用已建表）

```sql
-- 公告表（新增自建）
CREATE TABLE announcement (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  institution_id BIGINT NOT NULL,
  title VARCHAR(128) NOT NULL,
  content TEXT NOT NULL,
  target_scope VARCHAR(16) NOT NULL DEFAULT 'all',  -- all/cohort/grade
  target_cohort_id BIGINT NULL,
  publish_status VARCHAR(16) NOT NULL DEFAULT 'draft',  -- draft/published/offline
  published_at DATETIME NULL,
  created_by BIGINT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  KEY idx_announcement_scope (institution_id, publish_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='公告发布';

-- 站内信/通知表（新增自建）
CREATE TABLE user_notification (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  notification_type VARCHAR(24) NOT NULL,  -- system/announcement/teacher_message/ticket_reply/refund_result
  title VARCHAR(128) NOT NULL,
  content TEXT NULL,
  link_url VARCHAR(255) NULL,
  read_status TINYINT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL,
  KEY idx_notification_user (user_id, read_status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='站内信/通知';
```

## 四、与 C 端闭环对应关系（用户点名逐项落实）

| C 端功能 | 管理端对应 | 落点 |
|---------|-----------|------|
| 下单（order+order_item） | M1 订单管理 | /admin/orders |
| 支付（payment_record） | M1 订单详情内支付流水 + 对账 | /admin/orders/[id] |
| 退款（refund_request） | M2 退款审批（HITL） | /admin/refunds |
| 报名（student_cohort_rel） | M3 报名/学员学习管理 | /admin/cohorts/[id]、/admin/students |
| 申诉 | M6 工单申诉管理 | /admin/tickets |
| 学习作答 | M3 学员作答详情 | /admin/students/[id]/answers |
| （C 端缺）师生交流 | M5 站内信+班级讨论监控 | /admin/messages、/admin/announcements |
| （C 端缺）公告 | M5 公告发布 | /admin/announcements |

## 五、任务划分补充建议（新增 8 后端任务 + 10 前端任务）

> 插入 dev-plan v3.0：后端插入 task40 之后（re-number 或追加 task70~77 + 前端 task78~87），建议**追加编号**避免重排。

### 后端（Trae，8 任务）
| 任务 | 模块 | 依赖 | 关键点 |
|------|------|------|--------|
| task70 公告+站内信表与接口 | M5 | task03, task10 | 2 张新表 DDL + 公告/通知 CRUD + C 端未读接口 |
| task71 订单管理后端 | M1 | task17 | admin orders 4 接口 + 状态过滤 |
| task72 退款审批后端 | M2 | task19, task28 | admin refunds 4 接口 + HITL 挂载 |
| task73 报名/学员画像后端 | M3 | task20, task21 | cohort students + student profile + answers 聚合 |
| task74 排课考勤后端 | M4 | task21 | 日历 + 换师 + 考勤 CRUD |
| task75 工单管理后端 | M6 | task22 | admin tickets 6 接口 + 满意度统计 |
| task76 内容审核+评价后端 | M7 | task15 | moderation + reviews |
| task77 报表+组织师资后端 | M8/M9 | task71~73 | 报表聚合 + org/staff CRUD + 课酬 |

### 前端（TraeWork，10 任务，每页 HTML 审核流）
| 任务 | 页面 | 依赖契约 |
|------|------|---------|
| task78 /admin/orders 订单管理 | M1 | task71 |
| task79 /admin/refunds 退款审批 | M2 | task72 |
| task80 /admin/cohorts/[id] 班级学员 | M3 | task73 |
| task81 /admin/students/[id] 学员详情+作答 | M3 | task73 |
| task82 /admin/schedule 排课日历 | M4 | task74 |
| task83 /admin/tickets 工单+申诉回复 | M6 | task75 |
| task84 /admin/announcements 公告发布 | M5 | task70 |
| task85 /admin/messages 站内信台 | M5 | task70 |
| task86 /admin/moderation 内容审核 + /admin/reports 报表 | M7/M8 | task76/77 |
| task87 /admin/org+staff 组织师资 | M9 | task77 |
| C 端联动 | 消息铃铛+公告位 | task70 | 并入现有页面适配任务 |

## 六、自我批判与优先级（用户要求的技术选型审计）

| 批判点 | 结论 |
|--------|------|
| 是否全部必须本轮做？ | **M1/M2/M3/M6（订单/退款/报名学员/工单）必须**（C 端交易闭环的 B 端半，不做则 C 端功能无意义）；M5 公告站内信**必须**（用户点名师生交流）；M4/M7/M8/M9（排课/审核/报表/组织）建议本轮做 M8 报表（纯查询低成本），M4/M7/M9 可排二期 |
| 新增 2 张表是否破坏 edu.sql 权威？ | 否——announcement/user_notification 是**自建扩展表**（非 edu.sql 66 表范畴），与"保留自建表"模式一致；补入保留清单 |
| 报表用 echarts 是否最优？ | 是（现有 dashboard 已用 echarts，复用 chart-palette）；不引入 BI 工具（超规模） |
| HITL 审批用 LangGraph interrupt 是否最优？ | 是（task28 已设计，管理端是 UI 落地，避免自研审批状态机） |
| 对标来源 | 行业共识（校管家/ClassIn/腾讯课堂机构版/作业帮/猿辅导后台均含：教务/交易/学员/师资/内容/运营/报表七域）；edu.sql 数据模型设计意图（59 表零引用即铁证） |

## 七、优先级建议（供用户决策）

- **P0（本轮必做，C 端交易闭环的 B 端半）**：
  - M1 订单、M2 退款、M3 报名学员+作答、M5 公告+站内信、M6 工单申诉
  - M10 券管理（管理端发券，C 端 task16 已点券，必须闭环）
  - 对应任务：后端 task70~75 + 前端 task78~85
- **P1（本轮建议）**：M8 报表（纯查询低成本）、M11 CRM 线索（复用 consultation_record 闲置表）
- **P2（二期）**：M4 排课日历、M7 内容审核、M9 组织师资/课酬、M10 拼团/分销（增量营销）

## 八、任务补充（v1.1 新增，追加编号 task88+ 避免重排）

> 已在 §五 列 task70~87；v1.1 爬取对标后追加：

### 后端（Trae）
| 任务 | 模块 | 依赖 | 关键点 |
|------|------|------|--------|
| task88 营销管理后端 | M10 | task16 | 券管理 admin CRUD + 核销统计 + groupon/distribution 新表（P2 部分可空） |
| task89 CRM 线索后端 | M11 | task10 | leads CRUD + follow + stats 漏斗 + transfer（复用 consultation_record） |

### 前端（TraeWork，每页 HTML 审核流）
| 任务 | 页面 | 依赖契约 |
|------|------|---------|
| task90 /admin/marketing 营销管理 | M10 | task88 |
| task91 /admin/crm CRM 线索 | M11 | task89 |
