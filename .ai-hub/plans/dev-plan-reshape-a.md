# Feature: EduAgent 重塑计划 v3——A 批次(演示可交付)+ B 批次(批判承接)

> 版本链:v1 初拆(19 task)→ v2 契约审查定稿(契约冻结 `30aeddbe`,82 端点)→ **v3 = 整合技术批判 C15-C18 为可落地任务**(用户 P1'-P6' 前提全 agree,2026-09-06)。

## 개요
双线演示可交付(A 批次)+ 批判承接 B 批次(Refine/react-admin 选型 / TanStack Query 数据层 / health-scan 异步化)。方法论:实测契约→接线→独立实证→强制批判→批判反哺任务。批判条目与本计划的承接关系见「批判承接核对表」,杜绝"只批判不修复"。

## 需求前提挑战
### A 批次前提(v1,用户 2026-09-06 逐条确认)
| # | Premise | Confirm |
|---|---------|---------|
| P1 | 后端能力面足够支撑双线故事线,缺口停下上报不臆造 | agree |
| P2 | 页面骨架/CSS 复用不改视觉;纯接线页 HTML gate 降级为增量 diff 审查 | agree |
| P3 | 契约走棕地模式:contract-reverse 草案→用户逐条审→冻结;前端凭草案+变更单开工 | agree |
| P4 | 演示数据用现有库不造 MOCK | agree |
| P5 | 环境依赖写进演示前检查单(可机验),不做代码级高可用 | agree |
| P6 | 范围锁定故事线页面清单,清单外只保不翻车 | agree |

### B 批次前提(v3 批判承接,用户 2026-09-06 逐条确认)
| # | Premise | Confirm |
|---|---------|---------|
| P1' | 整合载体=本计划升级 v3(追加 B 批次章节),不另开计划文件;A 范围与冻结契约(30aeddbe)不动 | agree |
| P2' | A 批次只吸收纪律级动作(冻结只修不增写入 DoD;task18 GWT 扩七件套),零新代码 | agree |
| P3' | Refine vs react-admin 必须先走 tech-source-audit 选型审计,冻结前 B 页面 task 不得开工 | agree |
| P4' | C18 接口变更走变更单→B-contract 冻结→实施;冻结前前端仅凭草案做交互原型 | agree |
| P5' | C16 的 C 阶段部分(pgvector 收敛/退役)只立里程碑占位+最小验证脚本,不拆实施任务 | agree |
| P6' | B 批次 HTML gate:存量静态页=已 APPROVED 原型基线走 PARITY_CHECK;仅回收站 Tab/health-scan 异步交互/Refine 布局壳三类新增 UI 需新 HTML 原型送签收 | agree |

4 问结论:Q1 为什么现在 批判闸门刚过(4/4 URL 机验),反哺窗口=当下;B 未开工,现在整合成本是改计划,开工后是改代码 / Q2 现状方案 批判躺 tracker 待落地(TT §5.6 明防"只批判不修复"),无 B 计划则 C15-C18 漂成口头承诺 / Q3 窄楔子 B 最小可交付=选型框架版 admin-users 单页+TanStack 骨架+health-scan 异步化(变更单先行);A 收口批 task02-19 原样;不做 pgvector 实施、A 范围扩代码 / Q4 未来适配 Refine/TanStack/异步化是行业标准更核心;v3 成为 A 演示→B 组件化→C 单库生产化阶梯路线图

## 批判承接核对表(硬约束:每条批判必须有落点 task)
| 批判 | 落点 | 可证伪判据 |
|---|---|---|
| C15 双前端结构性浪费 | taskB0(选型审计)+taskB3(admin-users 单页) | Refine 版代码量<静态页接线版 1/3,不达标回滚审计 |
| C16 存储五件套 | task18(A 部分,GWT 已扩)+ C 阶段里程碑占位(P5') | 检查单<1 分钟;断链演练给出准确处置指引 |
| C17 自研客户端 | taskB2(TanStack Query 骨架) | 401 并发回归通过;页内零手写轮询 |
| C18 同步扫描崩点 | taskB1a(变更单)→B1b(冻结)→B1(实施) | 单台 health P95<500ms;扫描期 50 并发不排队 |

## 任务分解

### A 批次(契约已冻结 reshape-a.json,hash 30aeddbe;冻结顺序:auth→course/market→learning/chat→community/gamification→admin)

**A 批次全局 DoD(纪律级,P2')**:①自研客户端 edu-api 只修不增(新功能一律不再往里加封装);②fe-html 静态页只修不增(不再新增功能页/大块 UI,视觉基准冻结);两条写入每个 task 开工 prompt 硬性守则。

**task01 契约审查包**——✅ 已完成(v2 审查定稿+冻结 `30aeddbe`)。
**task02 login-register 登录注册回归加固**——选型:复用 EAPI+edu-guard 三段守卫。GWT:Given 合法/非法账号;When 登录(account 字段)/注册即登录(login-register.html:2970 已实现)/401 过期;Then 错误态诚实提示,按 role 跳转,redirect 站内校验。前置:task01✅。
**task03 courses 课程中心全量接线**——GWT:Given 真实 15 门课;When 筛选/排序/搜索防抖/分页;Then 全走真实 `/api/series` 参数,空态诚实。前置:task01✅。
**task04 course-detail 学生端课程详情**——GWT:Given 真实 id;Then 详情+班次真实渲染,报名入口未登录跳登录,坏 id 诚实空态。前置:task01✅。
**task05 coupons+下单真实闭环**——GWT:Given 学生登录;When 领券(POST trade/coupon/receive)→下单→订单可见;Then 真实库操作,余额/重复领取按错误码提示;**下单链路先 curl 补验再接前端(决策点①)**。前置:task01✅、task04。
**task06 learning 学习页**——GWT:Given 已报名;Then 课次/视频(/media 真实播放)/进度上报真实;未报名降级引导。前置:task05。
**task07 chat AI 问答**——GWT:When POST /api/chat/stream `{query,session_id,stream:true}`;Then j.delta 流式渲染/retrieval 引用/历史分页/error 诚实;P95 以流式 6.4s 口径。前置:task01✅。
**task08 community+community-post**——GWT:发帖/回帖/反应全真实,分页壳一致;写路径漂移按实测回填走变更单(决策点④)。前置:task01✅。
**task09 achievements**——GWT:徽章/积分/排行真实(gamification),无 MOCK 行。前置:task01✅。
**task10 me 个人中心**——GWT:资料/订单/券/收藏分页真实;收藏写路径 curl 补验。前置:task05。
**task11 dashboard 学生仪表盘**——GWT:统计/最近学习/推荐真实,无数据诚实空态。前置:task01✅。
**task12 admin-dashboard 真实 KPI**——GWT:接 `/api/admin/users/dashboard/metrics`(715ms 慢查询:加 loading 态,优化排 B/C,决策点②)。前置:task01✅。
**task13 admin-courses 系列管理(+回收站 Tab)**——GWT:系列 CRUD+restore 全接,40901 冲突提示;**回收站 Tab 为新增 UI→按 P6' 出 HTML 原型送用户 APPROVED 后再实施**。前置:task01✅。
**task14 admin-users 用户管理(重灾区)**——GWT:搜索/分页/详情/启停全量接 user_admin 域(现仅 1 处 EAPI),守卫三段。前置:task01✅。
**task15 admin-questions+question-detail 题库**——GWT:列表筛选/增删改/详情全接 question_admin 域。前置:task01✅。
**task16 课件/作业/考试诚实降级**——GWT:点击显示"后端未实现·后续上线"诚实占位,不留假按钮;视频入口保持真实。前置:task01✅。
**task17 清单外页面不翻车巡检**——GWT:favorites/practice/my-cohorts/refund CDP 加载无 JS 错/无死跳转,死按钮改诚实占位。前置:task01✅。
**task18 演示前检查单(v3 修订:七件套)**——选型:复用 CDP 脚本+探活模式。GWT:Given 演示机;When 跑 check-demo.mjs;Then **七项**全绿(Milvus/Redis/Mongo/8000/3000/登录链路/关键页200)+一键拉起指引(VMware/redis 容器),任一红项给一句话处置;断链演练:关 VM 跑检查单应准确报红。前置:task02-17。验收指标:<1 分钟。
**task19 全链路回归+渲染矩阵+强制技术批判**——GWT:双线 E2E(真实 HTTP+CDP 截图)+契约回归全绿出报告;批判≥3 条竞品对标登记 tracker。前置:task18。

### B 批次·批判承接(前置:task19 收口后才动生产代码;B0 审计可与之并行——纯调研零代码)
**契约冻结顺序**:B0 选型冻结 → B1a 变更单(用户签字)→ B1b 冻结 `contracts/reshape-b.json`(hash 上看板)→ B1 实施 → B2/B3。前端任务冻结前仅凭草案做原型(P4')。

**taskB0 选型审计(与 A 批次并行,零生产代码)**——选型依据:C15/C17,TT tech-source-audit 模板(来源+自批判+理由)。GWT:Given Refine/react-admin 两候选;When 六维审计(维护活跃度/生态/迁移成本/学习曲线/壳适配/包体积)+**DEMO spike:同一 users 数据各写一版 CRUD 含最小 dataProvider(壳解包+分页映射,隐藏工作量必须进审计)**;Then 产出审计文档+选型冻结,附可证伪判据。前置:无(并行)。
**taskB1a 接口变更单:health-scan 异步化**——GWT:Given C18 指标;When 变更单(动机/新契约 POST→job_id+GET 轮询/旧同步端点兼容窗口与回滚);Then 用户签字。前置:无,可与 B0 并行。
**taskB1b B-contract 契约冻结**——GWT:变更单冻结为 contracts/reshape-b.json,hash 上看板。前置:B1a。
**taskB1 health-scan 异步化+健康检查复用 sessions 池(后端)**——GWT:Given B-contract 冻结;When POST 异步扫描立即返 job_id,GET 轮询终态;单台 health 复用池;Then 单台 P95<500ms(现~5s),扫描期 50 并发不排队,兼容窗口内 admin-mcp.html 同步调用不破坏。前置:B1b、task19。
**taskB2 TanStack Query 数据层骨架**——GWT:Given B0 冻结;When queryClient 单例+401 刷新收敛(interceptor)+试点查询(admin-users 列表);Then 401 并发回归通过,页内零手写轮询/竞态。前置:B0、task19。
**taskB3 admin 布局壳+admin-users 页(窄楔子)**——HTML gate(P6'-③):新布局壳 HTML 原型→用户 APPROVED→PARITY_CHECK(糖果 token 冻结+截图 diff)→React 实施。GWT:Given 静态 admin-users(纯原型);When 选型框架版列表+筛选+启停(接冻结契约);Then 功能对等+CDP 无 JS 错+**代码量<静态页 1/3(不达标→审计回溯,批判 C15 判被证伪)**。前置:B0、B2。验收即 C15 的最小验证。

**C 阶段里程碑占位(P5',不拆任务)**:pgvector 收敛(最小验证=2629×2048 双引擎检索 P95/召回对比)、Mongo/Neo4j 退役——依赖真实部署窗口,到期单独立项。

## 规划自审
### CEO 范围自审
- finding1(v3):B 批次楔子仅 admin-users 一页,有"批判承接象征化"风险。处置:验收判据可证伪(1/3 代码量),不达标回滚选型审计;B3 验收后立即立项 B+ 批次按同模式复制其余页面。
- finding2:双批次并行度受"可并行任务数"约束,B0/B1a 虽并行但都不产生产代码,A 收口优先级不被稀释。处置:派单时 A 批 task02-05 先行,B0 仅后台调研。
### Eng 架构自审
- finding1(v3):Refine 与现有响应壳/分页壳的 dataProvider 适配层是隐藏工作量。处置:已写入 B0 DEMO spike 必选项,工作量进审计结论,不许事后追加。
- finding2:health-scan 异步化与 sessions 池复用存在池 GC 竞争,需池化锁。处置:B1 GWT 含并发用例;实现放 executor 层加池锁。confidence: medium(B0 spike 前对框架适配不下定论;后端异步化模式已有 R1-③ 队列先例)。
### Design 体验自审
- finding1(v3):选型框架默认组件风格(如 antd)与糖果 token 冲突。处置:P6'-③ 布局壳 HTML 原型先行送 APPROVED,Refine 主题做 token 映射,PARITY_CHECK 门机验;组件库默认样式不得直接上线。
- finding2:存量 UX 病灶(无 loading/空态)在纯接线页可能残留。处置:A 批每页 GWT 内置三态必查,Design 视角抽查不放全批。
