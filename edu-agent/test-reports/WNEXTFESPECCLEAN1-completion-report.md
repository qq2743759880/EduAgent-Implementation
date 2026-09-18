# W-NEXT-FE-SPEC-CLEAN-001 完工报告

> 任务 ID：W-NEXT-FE-SPEC-CLEAN-001（public/*.html 规格字样清污收口 + 空串兜底中性化）
> 子 agent：W-NEXT-FE-SPEC-CLEAN-001 接手执行 agent（前任 API 中断，WIP `f05c97c` 承接）
> 派单：C-01 orchestrator 主会话（逐断言独立实证验收）
> 完工日期：2026-09-18
> 本批 commit：**`c44768a`**（fix(fe-html)/W-NEXT-FE-SPEC-CLEAN-001，仅 18 个 public/*.html）
> 前任 WIP：`f05c97c`（wip(FE-SPEC-CLEAN)：admin 3 页规格字样已清，14 页中 3）
> lock：`edu-agent/scripts/eval/wnextfespecclean1.lock` 已于 commit 前删除（沿用前任锁，无竞态）

---

## 一、前任 3 页承接说明

| 前任页 | 承接核验方式 | 结果 |
| --- | --- | --- |
| admin-dashboard.html | `git show f05c97c` 比对 + 可见文本复扫（剔除 script/style/注释） | 0 可见命中，干净承接，未再改动 |
| admin-mcp.html | 同上 + 运行时文案 grep | 静态文案 0 命中；但发现 **JS 回写遗漏 2 处**（L539/L556 按钮文案 `"▶ 执行测试（POST /api/mcp/tools/test）"` 运行时覆盖前任已清的静态按钮）→ 本批补清为 `"▶ 执行测试"` |
| admin-rag-upload.html | 同上 | 静态残留 2 处（L389 `invalidateQueries(["rag","collection"]) · FR-RAG-02 行数闭环`、L398 `Dense + Sparse 双路 · Milvus`）→ 本批补清 |

前任判定口径（照抄执行）：**规格字样 = 任务编号 / 内部代号 / 接口路径 / 开发注释泄漏 / mock 演示数字**，仅清「用户可见渲染文本」；HTML 注释（含顶部契约注释）与 JS 功能代码保留。口径依据：① `git show f05c97c`（前任保留 `<!-- 真实接入说明（task61…） -->` 等注释行）；② 更早批 `219fce6`（WNEXT9 spec-cleanup：17 页 title + dashboard/me 正文，顶部契约注释保留）；③ AGENTS.md「fe-html 静态页顶部注释即接口契约来源」。

## 二、「14 页」口径对账

任务书口径：14 页全量 = 前任 3 页 + 剩余 11 页。本批以**可见文本机扫**（正则族：taskNN / C5-D2 / B3 / 契约①-⑩ / FR-x-y / FROZEN / candy-playful / 审核稿 / 效果图 / MOCK / 演示数据 / 示例数据 / API 路径 / GET|POST|PATCH|DELETE / Milvus / ZSET / Refine / Gate A / curl 实测 / require_role / AdminUserItem / 测试账号 / role_breakdown / 4xx·42x 错误码 / 诚实降级 等）对全部 25 个 public/*.html 独立重盘点，**实证命中 15 页**（2 页承接干净 + 13 页待清），比任务书 11 页多 2 页（admin-course-detail.html 与 admin-courses-recycle-proto.html 的增量命中在任务书口径外），按「执行到底」原则全部纳入。逐文件命中数（复扫前 → 复扫后，均为剔除 script/style/注释的渲染文本）：

```
0 命中（承接确认干净）：admin-dashboard.html、admin-mcp.html（后者 JS 回写 2 处已补清）
13→0：admin-users-refine-proto.html（46 命中，含注释层最多）
 8→0：admin-courses-recycle-proto.html
18→0：admin-question-detail.html        4→0：admin-courses.html
13→0：admin-questions.html              5→0：admin-course-detail.html
 7→0：admin-users.html                  2→0：admin-rag-upload.html（承接残留）
15→0：practice.html                    11→0：my-cohorts.html
 3→0：coupons.html                      1→0：course-detail.html / favorites.html / me.html* / chat.html*
* me.html、chat.html 唯一命中为保留项（见三）。
```

## 三、盘点清单（清理 / 保留分类）

### 清理（渲染可见 → 用户面中性文案），共 84 处渲染文本 + 12 处 JS 回写串

| 页 | 清理内容（原文 → 改后） |
| --- | --- |
| admin-users-refine-proto.html | title `B3-proto 原型 · …Refine 版 /admin/users（仅原型不接线）`→`管理端用户管理原型 · EduAgent`；标注条 curl 实测快照（`adm02test，全量 total=100,034` / Gate A / C15 ≤214 行 / admin-users.html 642/3 / 复核日 2027-03）→中性示例声明；S0 表 `require_role([ADMIN])`+403 载荷原文+mgr01test 实测 →「仅 admin 可访问，manager 403（角色无权限）」；S1 `mgr01test 经守卫（role∈{…}）`+H2a/P1-9 →中性；S2 chip `列表 GET /api/admin/users`→`列表（示例数据）`、`40303`→「保护机制」；**8 行真实测试账号泄漏**（adm02test/mgr01test/123456/task06probe/edu_user_00xxxx + 真实 UID 100003/100004/100038/100039）→ demo_* 合成账号；AdminUserItem 字段 dump →「行字段与正式版一致」；S3 `setListState("loading")`、S4 `keyword=zzz_no_match → total=0`、S5 `40300 兜底`+HTTP 403 载荷原文 JSON →中性；S6 `POST /api/admin/users/100004/status（body…）`→「提交禁用状态」；S7-2 `40303 红线`+`metrics.role_breakdown.admin=5`+2 处 `POST /api/admin/users/100003/*` →「保护拦截/已拦截」；S8 `C15 判据·Gate A 后接线清单`+Refine/B2/queryClient/useTable/interceptor →「设计说明·组件映射·接线要点」；gnav-foot/toe S7·S8 锚点文案 |
| admin-courses-recycle-proto.html | 标注条 `task13 原型`+curl 实测快照（`GET /api/admin/courses/series?sale_status=…，total=56`）+Gate A →中性；行内 `C5非法恢复…`/「模拟 409」chip →「示例冲突恢复系列…」/「示例冲突」；head-sub 两个端点等式 →「支持恢复与彻底删除」；工具条 `共 56 个`（真实 total 泄漏）→「已下架系列 · 示例 6 条」；恢复/删除弹窗 2 处端点+`sale_status`+`SERIES_IN_USE` →中性；JS `meta-count`/`head-sub` 回写 2×2 处同步 |
| admin-question-detail.html | 骨架 `GET /api/admin/questions/questions/{id} 加载中…`→「加载中…」；field-note ×2（GET /types 实测 28 项 / objective_flag 派生于 dim_question_type 契约④）→中性；观测点区块 8 行（task59 契约对齐/PATCH body dump/curl 实测 200/40400·42200/P16/analysis_text/QuizPanel/MarkdownView/v0.2.0 灰系史）→「页面行为说明」7 行中性；表单标签 `题干 stem / 选项 options_json / 答案 answer_text / 预览 题干 stem` →纯中文；`★ 重构核心：analysis_text…PATCH 兜底（422）`→中性 |
| admin-questions.html | 搜索占位 `bank_code（防抖 400ms）`→「名称 / 编码」；select title `契约缺口：后端 banks…`→「分类筛选暂不可用」；ft-note ×2（40921/诚实降级/不做假筛选/LIKE/objective_flag）→中性；chip `GET /banks/{id}/questions 联动` ×2；ft-note 观测点 `跳 task59 /admin/questions/[id]`→中性；`body 字段实测(…)（PATCH schema）`→「创建需填写…编辑仅可修改名称与分类」；`题号 *（唯一 per 题库）`+`T107-Q001`→「题库内唯一」+`Q001`；`题干 stem / 答案 answer_text / 解析 analysis_text` 标签→纯中文；`解析 & 落库（powered by POST /import-execute，幂等）`→「解析与入库中…」；JS 回写 bank-form-hint ×2、del-bank-cnt ×1 同步 |
| admin-users.html | sub `require_role(ADMIN)…40303`→「保护机制」；chip `列表 GET /api/admin/users`→「列表实时加载」；契约缺口区块（GET /api/admin/users/{id}/learning 未注册/实测 404/user_admin router）→「暂未开放…功能上线后自动呈现，本页不展示占造数据」；编辑弹窗 label ×2 `→ POST …（实测 200）`→「保存后生效」；红线区块（status=0/≠admin/40303）→中性；JS learn-sub `数据源 GET /api/admin/users 列表项`→「来自用户列表数据」 |
| practice.html | sub `糖果色 · candy-playful FROZEN` 删除；wrong-book-note `analysis_text/question 表（契约④）`；topic-note `dim_question_type/待 interactive 后端落地后联调`；`数据上报 progress 契约⑤`；`本题解析 · analysis_text（…task59 管理端一致）`；错误文案 2 处 `（GET /api/... 暂不可达）`；footer 数据契约 2 行（3 个 API + 契约④ + React 待联调禁止 MOCK）→「数据来源：…均来自真实接口数据」；demo-note task49 审核流 R3 整段 →中性；tooltip `演示数据 · ` 前缀 ×7 |
| my-cohorts.html | tooltip `演示数据 · ` 前缀 ×9（含 `证书功能后端未实现·后续上线`→「证书功能即将上线」）；错误文案 `（GET /api/enrollments/me/cohorts 暂不可达）` |
| admin-course-detail.html | field-tip ×3（institution_id/head_teacher_id/40902/cohort_id/40903/series_cohort_course_id/40904）→中性；label `阶段 stage_no（唯一）`/`课次序号 session_no（唯一）`→「阶段序号/课次序号（唯一）」 |
| coupons.html | sub + sec-cap ×2 共 3 处 API 路径 |
| course-detail.html | demo-note task46 审核流整段（STYLE frozen/stage_no/teaching_status/RadioGroup/GET·POST 端点/契约⑦⑧ task16/17/React 阶段）→「页面形态：…」；JS 骨架 `（GET /api/series/1001 + /cohorts + …）`→「正在加载课程详情…」 |
| favorites.html | sub `GET /api/favorites（真实数据）`→「真实数据」 |
| admin-rag-upload.html（承接残留） | hint `invalidateQueries…FR-RAG-02`→「自动刷新知识库统计」；`Dense + Sparse 双路 · Milvus`→「向量 + 关键词双路检索」 |
| admin-mcp.html（承接 JS 补清） | ttRun 按钮回写文案 ×2 →「▶ 执行测试」 |
| learning.html（任务书 11 页外） | JS tickNotice `后端缺播放会话创建端点·缺口 task06-G1`→「播放打点暂未上报，功能开放后自动记录」 |
| dashboard.html（任务书 11 页外，空串兜底） | 见四 |

### 保留（12 类，含理由）

| 保留项 | 位置 | 理由 |
| --- | --- | --- |
| 顶部契约注释（taskNN/API 清单/curl 实测记录） | 全部 25 页 `<head>` 后首块注释 | AGENTS.md 明文：「fe-html 静态页顶部注释即接口契约来源」；前任 f05c97c 与 219fce6 均保留；不渲染 |
| HTML/JS 内部注释（`<!-- task13 原型标注条… -->`、`/* task117 toast */` 等） | 各页 | 不渲染；同上口径 |
| JS fetch/函数代码中的 API 路径 | 各页 script | 功能必需，非文案 |
| chat.html 降级横幅（`排队人数较多，已为你降级回答`） | L97-99 | 产品功能文案（真实降级提示），非规格泄漏 |
| me.html `售后工单页未上线` aria-label/入口灰显 | L98 | 诚实的未上线产品口径 |
| my-cohorts 未登录角标「演示数据」（task122 JS 徽章） | L671 | 诚实标注演示态防真实/演示混淆，产品决策（注释载明动机），登录态不显示 |
| 原型页 S0~S8 场景编号、示例数据声明、token 映射表（--candy-* 等 CSS 变量名） | admin-users-refine-proto | 设计规范标识非秘密；场景编号是原型文档结构；token 表是该页核心交付物 |
| 原型页样例行的中文姓名（姚敏浩等 4 人）与 series_code（rst17886…） | admin-users-refine-proto L330-357 / recycle-proto 数据区 | 账号名与 UID 已全部换合成值；姓名声明为示例数据（风险见 P0-3 自批判） |
| `scheduled 未开始` 等枚举双语选项、`分类 ID *`/`机构 ID *` 数字输入标签 | admin-course-detail L499/L502、admin-questions L460-461 | 管理端表单功能字段（与前任保留 `last_health_ok/last_error` hint 同类） |
| 导入 JSON placeholder（question_code/options_json 等） | admin-questions L563 | 数据格式模板（类似 `如：PROG-L2`），指导管理员粘贴正确 JSON，非泄漏 |
| `零 script（无 script src / fetch / XHR / 内联事件）` 声明 | refine-proto 标注条 | 实现属性陈述，grep 实证该页 0 个 script 标签为真 |
| 保留项：admin-courses JS `ss.title` 空串分支 | L559-560 | 非回收站视图无 tooltip 属正确 UX（本批仅改其中文案） |

## 四、空串兜底（任务 #2）：10 处改中性占位，不造 MOCK

可机检模式：`textContent|innerHTML|title|placeholder … (|| ''|?? ''|: '')`。判定：**错误提示类**（前缀恒显示，仅错误详情为空，如 `⚠ 班次加载失败：'+esc(e.message||"")`）与**容器清空类**（`body.innerHTML=…:""`、校验错误清除 `e.textContent=bad?msg:""`、toast `msg||""`）不改——用户可见文案不为空；**渲染为空/悬空标点类**修复：

1. admin-courses L723 `编辑系列 · "+(series_name||"")` → 条件拼接（无悬空「·」）
2. admin-courses L755/L760 `series_name||""` → `"未命名系列"`
3. admin-courses L810 `series_code||""` → `"—"`
4. dashboard L604 `· 快照 "+(d.snapshot_date||"")` → 条件拼接（无悬空「· 快照」）
5. course-detail L1244 面包屑 `||""` → `"课程详情"`
6. learning L603 `series_title||""` → `"当前课程"`
7. admin-question-detail L728 `question_code||""` → `"—"`
8. practice L1324 `mastery_status||''` → `"未评估"`（原会渲染成 `· 间隔 X 天…` 悬空前导点）
9. achievements L592 `level_title||""` → 条件拼接（无悬空「·」）
10. community-post L605 `created_at||""` → `"—"`

另：admin-courses L722 tooltip `（后端更新接口不含该字段）` 顺带中性化。全批未新增任何 MOCK 数字/假数据。

## 五、逐页 diff 摘要

`git show c44768a --stat`：18 files changed, +164/-167。命中最多的 4 页：admin-users-refine-proto（~99 行段）、admin-question-detail（36）、admin-questions（34）、admin-courses-recycle-proto（28）、practice（31）、my-cohorts（22）。单行 1-2 处页：achievements/community-post/dashboard/favorites/learning/coupons/course-detail。逐条对照见「三」，diff 原文可复核 `git show c44768a`。

## 六、curl 证据（3000 生产形态直出，2026-09-18 23:4x）

- **25/25 页全 200**：`for f in *.html; curl -o /dev/null -w %{http_code} http://127.0.0.1:3000/$f` → achievements/admin-course-detail/admin-courses-recycle-proto/admin-courses/admin-dashboard/admin-mcp/admin-question-detail/admin-questions/admin-rag-upload/admin-users-refine-proto/admin-users/chat/community-post/community/coupons/course-detail/courses/dashboard/favorites/learning/login-register/me/my-cohorts/practice/refund 全部 `200`。
- **服务内容即清理后内容**（防缓存假象，curl 输出 grep）：`candy-playful FROZEN`=0、`adm02test` 注释层 1（可见层 0）、`total=100,034`=0、`GET/POST/PATCH/DELETE`（admin-courses 可见）=0、`task06-G1` 注释层 4（可见层 0）、`POST /api/mcp/tools/test`=0、`契约⑤`=0；新文案命中：`错题复盘 · 单词回忆 · 专项突破`=1、`领券 / 下单真实闭环`=1。
- **可见文本终扫 = 0 命中**：正则族（taskNN/C5/B3/契约①-⑩/FR-x-y/FROZEN/效果图/MOCK/API 路径/实测/诚实降级/require_role/AdminUserItem/测试账号/role_breakdown/Gate A/Refine/窗口化分页…）×（剔除 script/style/注释）→ `TOTAL VISIBLE HITS: 0`。
- **注入模式完整**：`git diff` 中 `<script` 增删行数 = 0（未新增/删除任何 script 标签）；抽样页 edu-api.js 引用仍在（admin-users=1、practice=1、coupons=3）。
- **内联 JS 语法**：18 个被改页全部 `<script>` 块抽出 `node --check` → `FAILS: 0`。
- **check-demo 回归**（task #4）：`node scripts/check-demo.mjs` → **⑤ PASS（前端 3000 /login-register.html + 生产 build 形态判别）**、**⑦ PASS（8 核心页 200，8/8）**、**⑨ PASS（/admin-users-refine-proto.html 200）** —— 三项全绿。全单：绿 17/21，红 ⑯（8000 lifecycle 健壮性，后端进程层预存问题，与本批纯前端文案改动无关，③④①②⑪⑬⑭⑰⑱⑲ 等 real-backend 项均 PASS 佐证环境本身健康），WARN ⑧（DEBUG 后门提示，预存）/⑩（契约对账 WARN，预存）/㉒（MinIO 历史审计，预存）。

## 七、P0 自批判（≥3）

1. **注释层测试账号残留（口径继承风险）**：`adm02test / mgr01test / user000001` 及 task14/15/56 等仍存在于多页顶部契约注释与 JS 注释，curl 可见（本批实测 admin-users-refine-proto 注释层命中 `adm02test`=1）。前任口径 + AGENTS.md 契约来源条款要求保留注释，本批照抄；但「生产形态 view-source 可见真实测试账号名」与「3000 是生产形态」存在张力。**建议承接方**：生产出包流水线加一步注释剥离（html-minify）而非改源注释，一举两得。
2. **原型页 = 内部审核稿公开发布（结构性残留）**：admin-users-refine-proto / admin-courses-recycle-proto 本质是面向实施者的 Gate 送审件，本批已清全部泄漏性文案（API/账号/UID/真实总量/载荷原文/内部流程代号与日期），但页面形态（S0~S8 场景、原型标注条、token 映射表、零 script 声明）仍非产品页。若产品要求 3000 全站「零开发痕迹」，**应下线原型页或加访问控制**——属结构性决策，超出文案清理授权（check-demo ⑨ 依赖该页 200，下线需先改 C5-D2 扩清单，牵连守卫契约，不敢擅动）。
3. **样例行中文姓名来源存疑（隐私残留候选）**：refine-proto 标注条原文自称「curl 实测快照」，则 4 个中文姓名（姚敏浩/杨峰思/蔡泽书/彭佳晴）可能是真实用户数据，本批仅替换登录账号名与 UID 而保留姓名（现声明为示例数据）。若确认源自真实库，应以纯合成姓名重写 8 行样例——为不扩权未执行，**留给承接方以 DB 比对实证后决策**。
4. **空串兜底覆盖面有限**：只穷举了 `textContent/innerHTML/title/placeholder` 赋值语句尾部的 `|| ''/?? ''/: ''` 模式；innerHTML 长模板中段嵌套的 `${x?.y||""}` 深层空值未逐一审计（量级大且多为结构属性而非文案）。二阶效应：改 9 处为「未评估/—/当前课程」等占位，若上游把这些占位当作有效值回读会引入脏数据——已核对 9 处均为纯展示 span（无回读逻辑），风险受控。
5. **check-demo ⑯ 红 + ⑧ WARN 未处置**：本批红线禁碰 app/**，lifecycle（⑯）与 DEBUG 后门（⑧）属后端/部署域，只能登记不能修——若 C-01 要求全绿回归，需另派后端单。

## 八、批判承接核对

grep `critique-backlog-tracker.md`、`.ai-hub/plans/artifacts/critique-tracker-v1.md` 及全部 plans/artifacts：**无任何针对 W-NEXT-FE-SPEC-CLEAN / 规格字样的批判承接项**（0 命中）。本批无未闭环承接项；新增自批判 5 条见「七」（其中 1/2/3/5 为建议承接，4 已自证受控）。

## 九、资产消费证据

| 资产 | 消费方式 |
| --- | --- |
| `git show f05c97c` | 前任 diff 逐行研读，确立判定口径（可见文本 vs 注释/JS、契约缺口→「暂未开放」句式、`加载中…（GET …）`→`加载中…`） |
| AGENTS.md | 教训 2（禁 Playwright→本批 curl/node --check 独立实证）、教训 4/9（注入模式与全局污染）、顶部契约注释条款（保留依据） |
| `edu-agent/scripts/check-demo.mjs` | ⑤⑦⑨ 判据源码级确认（PAGES 8 页清单、FRONTEND_PORT 派生、⑨ C5-D2 扩清单） |
| `edu-agent/scripts/eval/wnextfespecclean1.lock` | 沿用前任锁防并发，commit 前删除（`rm` + ls 复核 No such file） |
| `git show 219fce6`（WNEXT9 前批） | title 统一口径 `X · EduAgent`（refine-proto title 按此补清）、dashboard/me 已清范围对账 |
| check-demo ⑥ 测试账号 | `adm02test/user000001` 用于识别页面泄漏的同类账号名（未新造凭据） |
| 红线遵守 | 0 改动于 src/**、deploy.mjs、app/**、contracts/**；commit `c44768a` 经 `git diff --cached --name-only` 复核仅 18 个 public/*.html（期间曾因并行 DEPLOY-HARD 预暂存混入 3 个外来文件，已软回退摘除重提交，外来文件工作树内容原样未动） |

---

## 十、返工节：编排者验收抓漏 5 处 + 全量 JS 面机扫追加 6 处

> 返工 commit：**`e0c8de4`**（10 文件 +12/-12，仅 public/*.html）；报告 commit：`c523432`（首版）/ 本节随返工报告 commit 更新。

### 10.1 编排者 C-01 复现证伪的必修 5 处（全部认领修复）

| # | 位置 | 原文（泄漏物） | 修后 |
| --- | --- | --- | --- |
| 1 | admin-courses.html:842 | JS 回写 `t.textContent="⚠ 请用 admin 账号登录（adm02test / Test@123456）后刷新本页"`（守卫 needle `includes("admin 账号")` 同步） | `⚠ 请用管理员账号登录后刷新本页`（needle→`"管理员账号"`，幂等语义保持） |
| 2 | admin-dashboard.html:467 | 同型（`indexOf("admin 账号")`） | 同上 |
| 3 | admin-questions.html:659 | 同型 | 同上 |
| 4 | admin-users-refine-proto.html:268 | `<span class="chip">总计 <b>100,034</b> 人</span>`（真实用户总量渲染） | `总计 <b>1,024</b> 人（示例）`（与页内 demo_*/UID 881~1017 合成口径一致） |
| 5 | admin-users-refine-proto.html:386 | `共 100,034 条 · 第 1 页 · 快照示例 8 行` | `共 1,024 条 · 第 1 页 · 示例 8 行` |

### 10.2 全量 JS 面专项机扫：追加抓漏 6 处（同型盲区自证）

**盲区根因（自批判 P0-6）**：首版 JS 面扫描的模式表只有 `/api/|实测|契约|task\d+|MOCK`，**漏了账号名/密码/裸数字**——「admin-mcp JS 回写」抓到 1 处后未把同型 token 加进模式并全量复扫，违反「机扫兜底」原则。返工扫描：**全部 public/*.html 的 `<script>` 块逐行 × token（adm02test/mgr01test/user000001/Test@123456/100,034/100034/taskNN/C5-D2/Gate A/C15/B3-*/契约①-⑩/FR-x-y/admin 账号）× 渲染 API 赋值分类（textContent/innerHTML/innerText/insertAdjacentHTML/setSub(/toast(/title/placeholder）**，共 102 条 token 行，分类结果 `RENDERED FAILS`：

| 追加 # | 位置 | 分类 | 原文要点 | 修后 |
| --- | --- | --- | --- | --- |
| 6 | admin-mcp.html:591 | `setSub("…")` 渲染（非 textContent 直赋，首版 ASSIGN 正则漏网） | `setSub("⚠ 请用 admin 账号登录（adm02test / Test@123456）…")` | `setSub("⚠ 请用管理员账号登录后刷新本页")` |
| 7 | admin-question-detail.html:537 | textContent 赋值 | 同款账号+密码 | 同 #1 |
| 8 | admin-users.html:693 | textContent 赋值 | 同款账号+密码 | 同 #1 |
| 9 | admin-course-detail.html:535 | textContent 赋值（弱化版：无账号密码但「admin 账号」口径不一，needle 检查抓到） | `⚠ 请用 admin 账号登录后刷新本页` | `⚠ 请用管理员账号登录后刷新本页` |
| 10 | learning.html:734-735 | 渲染三元串（非直接赋值形态，首版漏网） | `已标记完成（后端真实写入 completed=true）` / `…播放会话未建立·缺口 task06-G1` | `🎉 已标记完成` / `…（播放会话未建立），请稍后重试` |
| 11 | admin-courses-recycle-proto.html:508 | innerHTML 拼接渲染串 | `沿用 task56 形态（本原型不聚焦）` | `沿用正式列表形态（本原型不聚焦）` |

### 10.3 返工后终态扫描证据（机扫输出原文）

```
=== JS 面专项扫（script 块逐行 × token × 渲染赋值分类）===
FINAL: RENDERED FAILS=0 | comment=80 | code-ident/tail=21
（comment=80：块注释 /* … */、行注释 //，按编排者裁决保持原样；
  code-ident/tail=21：行尾注释（如 loadFavState(); /* task04 */）、
  代码标识符（community.html:427 boards.dataset.task118Bound="1"，DOM dataset 键非渲染文案）、
  块注释内部行（community/community-post 契约注释块），均非渲染串）

=== 可见文本扫描（剔除 script/style/注释，token 含 admin 账号/Test@123456/100,034）===
VISIBLE TOTAL: 0

=== 内联 JS 语法（10 个返工页全部 <script> 块 node --check）===
JS SYNTAX FAILS: 0
```

### 10.4 返工验证

- **curl**：10 个返工页全 200（admin-courses/admin-dashboard/admin-questions/admin-users-refine-proto/admin-mcp/admin-question-detail/admin-users/learning/admin-courses-recycle-proto/admin-course-detail）。
- **服务面探针**（3000 直出 grep）：`Test@123456` 6 页全 0；`admin 账号` 0；`100,034` 0；新文案 `1,024` ×2、`管理员账号登录后刷新本页` ×1 命中。
- **注释层残留**（保持原样，裁决见编排者返工单）：learning task06-G1 ×3（head/JS 注释）、recycle-proto task56 ×2（注释）、refine-proto adm02test 等头部注释块——已在首版 P0-① 披露，结构性处置待用户决策。
- **git 纪律**：`git symbolic-ref`（feature/opt-waves）+ `git rev-parse`（tip=c523432 未前移）先查后提；暂存区核空后精确 add 10 文件，`git diff --cached --name-only | wc -l`=10 复核后提交，无外来文件混入。

### 10.5 返工后 diff 摘要

`git show e0c8de4 --stat`：10 files changed, +12/-12。逐处见 10.1/10.2 两表；改动全部为 JS 字符串字面量与 2 处静态 chip/cnt 文本，无结构/逻辑变化（needle 同步保持幂等守卫语义），不新增 script，edu-api.js 注入模式未动。
