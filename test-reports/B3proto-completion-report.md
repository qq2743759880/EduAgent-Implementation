# B3-proto 完工报告：admin-users Refine 版 HTML 原型（Gate A 送审件）

- 日期：2026-09-12 ｜ 执行：前端原型工程师（独立 agent，ZCode）
- 派单依据：`.ai-hub/plans/dispatch-plan-reshape-b.md` §四 B3-proto 专项 + §一 D-H3 决策（A 方案并入 B3）
- 产物：`edu-frontend/public/admin-users-refine-proto.html`（556 行，纯静态，零 script）
- 状态：**DRAFT，待 Gate A 送审**；APPROVED 前禁止出 B3-impl 开工单

## 一、资产消费证据（A级资产 → 用在哪）

| A 级资产（开工单具名） | 消费方式 |
|---|---|
| P6' 条款（HTML gate） | 原型头部 AUDIT LOG: DRAFT 状态机 + proto-note 标注条，沿用 admin-courses-recycle-proto.html（task13 APPROVED 件）范式 |
| admin-users.html 现状（642 行=判据基数） | ① :root 糖果 token 逐字同源复制（未引入新视觉语言）②组件类同源（filterbar/tbl/badge/dlg/seg/sk/redline/gnav）③行数基数 642 → C15 判据 ≤214 写入 S8 场景与头部注释 |
| admin-courses-recycle-proto.html（原型范式） | 头部 AUDIT LOG 状态机、「示例数据，实施后为真实数据」标注法、实测快照标注法（captured 日期+端点+参数原样披露）、demo 场景标注法（对标 `__demo_conflict` → S7-2「演示假设」标注） |
| edu-guard.js（只读） | S1 manager 视角态横幅/灰显口径与其守卫三段+H2a/P1-9 复查逻辑对齐；原型不引入该文件（零 script src） |

## 二、实证记录（真实契约优先，禁 MOCK）

后端 127.0.0.1:8000 运行中（未重启），adm02test/Test@123456 走 API（无 DB 直写）：

1. `POST /api/auth/login`（body 字段为 `account`，实测 42200 纠正）→ 200 取 token
2. `GET /api/admin/users?page=1&page_size=5` → 200 `{code:0,data:{total:100034,...}}`；
   AdminUserItem 字段实测逐字：`user_id,username,real_name,phone,email,role_code,status,yn,created_at,updated_at,last_login_at`
3. `GET /api/admin/users?role_code=admin|manager|teacher&keyword=adm02test` → 取得 8 行真实快照入原型 S2：
   UID 100003 adm02test/Super Admin(admin)、100004 mgr01test/Manager(manager)、1017 姚敏浩(admin)、
   975 杨峰思(teacher)、894 蔡泽书(admin)、881 彭佳晴(manager)、100038 123456(student)、100039 task06probe(student)
4. manager(mgr01test) `GET /api/admin/users` → **HTTP 403** `{"code":"40300","message":"角色无权限。当前角色=manager，允许角色=['admin']"}` —— S5 错误态与 S0 口径表按此载荷**原文**呈现
5. 红线口径：S7-2 标注「演示假设」并如实披露实测 `role_code=admin total=5`（红线当前不触发），仅呈现触发时形态——不伪造当前库状态

## 三、原型包含的交互态清单

**manager 视角态（S1，只读）**
- 顶部只读横幅「该模块仅 ADMIN 可用（后端权限口径 require_role([ADMIN])；当前角色 manager）」+ 返回仪表盘
- 导航例外灰显示意：users/mcp/dashboard 三项 `pointer-events:none+opacity:.45+title「仅 ADMIN 可用」`（与 H3-temp 过渡措施同口径）；rag 不灰显；课程/题库完整可用
- 列表区诚实空态（清骨架屏，不留误导性加载态）

**ADMIN 视角态（S2~S7，全交互态）**
| # | 态 | 场景 |
|---|---|---|
| S2 | 正常列表 | 搜索（防抖 400ms）+角色/状态筛选+窗口化分页（1 2 3 … 10004，共 100,034 条）+8 行实测快照 |
| S3 | loading 骨架 | 7 列骨架行（sk 动画渐变，同源 #uk-skel） |
| S4 | 空态 | keyword=zzz_no_match → total=0「未匹配到用户」 |
| S5 | 403 错误态 | 40300 载荷原文兜底展示（实施版请求前拦截，此为兜底形态） |
| S6 | 启停二次确认弹窗 | 禁用 mgr01test：风险文案+body{"status":0}+reason ≤255 |
| S7-1 | 编辑 diff 弹窗（正常） | role diff（教师→教务，绿底变更行）+status 未变（灰）+端点标注 |
| S7-2 | 编辑 diff 弹窗 + 40303 红线态 | 禁用/降级双行拦截（红底 diff）+红线说明+保存按钮 disabled |

**静态说明件（S0/S8）**：权限口径总览表（后端权威/manager/ADMIN/红线/rag 例外）、C15 判据、token 映射表、Refine 映射、Gate A 后接线清单。

## 四、硬性守则遵守

1. 禁 DB 直写 ✅ 仅 curl API 读取，未执行任何 INSERT/UPDATE/DELETE
2. 契约冻结禁改 ✅ 未改后端/schemas/error_codes；40300/40303 文案为实测原文
3. 零 script 实证：`grep -c '<script'` = **0**；inline handler = **0**；`javascript:` = **0**；fetch/XHR = **0**
4. 禁 Playwright ✅ 静态件无需行为验证；实证全部走 curl
5. 只新建本原型文件，未改任何页面/edu-api.js/edu-guard.js（edu-guard.js 改动属 H3-temp 独立 commit）

## 五、三视角自检

- **用户视角（Gate A 评审）**：一页看全 manager/ADMIN 两视角与 8 个交互态，顶部场景索引锚点直达；「示例数据」标注显著；manager 为什么被拦（40300 实测载荷）与拦成什么样（横幅+灰显）均有可视化答案。
- **实施者视角（B3-impl）**：布局壳元素与现状页类名/结构同源（可直接迁移 Refine 壳），token 映射表逐 token 列出，接线清单 6 步含 C15 行数自证；diff 弹窗为 Refine 版新增形态，已给出端点级标注。
- **批判者视角**：①S7-2 红线态标了「演示假设」并披露实测 admin=5，避免"伪造当前库唯一 admin"的 MOCK 指控；②S5 标明实施版请求前拦截、错误态仅为兜底，避免与 H2a/P1-9 口径矛盾（task14 教训承接）；③原型 556 行远超 214——C15 判据约束的是 **B3-impl 实施版**而非原型，报告中显式声明防误读；④零 script 是本单硬约束（区别于 task13 原型的 JS demo 控制器），交互态改为静态场景卡+锚点索引方案。

## 六、遗留/上浮

- 无 discrepancy：列表端点/字段/403 载荷实测与契约一致。
- Gate A 关注点建议：S7 编辑 diff 形态为 Refine 版新增（现状页无 diff），若 Gate A 认为超范围可退回普通表单态，不影响其余场景。
