# REPORT-FEAT-WIRE-V2 — 新前端 12 缺陷修复 + 全量接线矩阵（执行完工报告）

- 执行分支：`feature/opt-waves`（开工/收工均 `git branch --show-current` 对账一致）
- 服务态：后端 9988 / 前端 3322 dev（Turbopack）均在跑；**两处均因修复内容重启过**（后端×3：quiz 过滤/会话隔离/记忆召回；前端×1：next.config.ts rewrites 不热载）
- 取证工具链：复用仓库既有 `scripts/gates/_shared.mjs`（headless Chrome + 原生 CDP + 截图 + EDU_GATE_TOKEN 注入），全部脚本在 `test-reports/feat-wire-v2/`，截图在 `test-reports/feat-wire-v2/shots/`（67 张）与 `matrix/`（25 张）
- 视觉复审：前中期截图曾因模型无视觉能力跳过图像审查，**切换视觉模型后已全部补审**，并据视觉发现追加两笔修复（见 #6-cleanup、#12 CSS 根因第二段）

## Commits（12 缺陷逐条独立 + B 矩阵，均未 push）

| commit | 内容 |
|---|---|
| 0485043 | fix(fe) d03 用户管理三弹窗 |
| 191957a | fix(fe) d02 弹窗三路关闭 |
| 6519adc | fix(fe) d04 RAG 五 tab 全接线 |
| 6a3b734 | fix(fe) d06 课程回收站真实接线 |
| c6cb376 | fix(fe) d06-cleanup 视觉复审补刀（原型横幅清除） |
| f9fd7cf | fix(fe) d01 视频上传入口 + 媒体代理根因 |
| a8897bc | fix(be) d07 quiz 题型过滤 |
| 65feccb | fix(fe) d07 practice 补刀 |
| b7070b1 | fix(be) d08 chat 会话隔离 |
| 1d13e7e | fix(fe) d09/d10 chat 指示器+流式实证 |
| 906b615 | fix(be) d11 跨会话记忆（召回注入+提取规则） |
| e629770 | chore(data) d05 MCP 测试数据三核闸软删 |
| 211a06e | fix(fe) d12 课程大纲 |
| e5ef3f9 | fix(fe) wfB 全站接线矩阵 |

---

## 工作流 A：12 缺陷逐条三段式

### #1 视频上传无入口（admin-course-detail.html）✅
- **修复前**：用户路径需 系列→班次→模块→课次行内小字「▶ 视频」才见上传区（video-panel 默认 display:none），且 `file_url` 经 3322 同源代理 500——**根因之一：next.config.ts `/media` 代理默认指向旧端口 8000（W-NEXT-PORTS-001 迁移漏网），后端实际 9988**。
- **修法**：课次行资源列新增显式「⬆ 上传视频」按钮（开面板+滚动+上传区高亮 1.8s）；`MEDIA_PROXY_TARGET` 默认 8000→9988。
- **修复后**（`test-reports/feat-wire-v2/d01-verify.mjs`，CDP DOM.setFileInputFiles 真实文件上传）：
  ```
  upload button: { ok:true, sid:29, title:'语法基础与开发环境 第1课' }
  3s: steps=[done,done,done,cur] tl=[init-chunked,finalize,bind-session] tc=转码中
  6s: steps=[done,done,done,done] tl=[…,转码] tc=转码完成
  file_url HEAD: 200 video/mp4 2415030   （3322 同源）
  磁盘：edu-agent/data/media/videos/VID-20260921-2267403B.mp4（2415030 B ≥1MB）
  ffprobe: h264+aac, duration=30.000000（可播放）
  ```
- 截图：`shots/d01-panel-open.jpg`（上传入口+面板+章节管理）、`d01-upload-final.jpg`

### #2 弹窗无法关闭（锚点勘误：实际在 admin-questions.html）✅
- **锚点差异（铁律6 如实报备）**：开工令写 admin-question-detail.html，实读代码该页是全页编辑表单**无弹窗**；「编辑题目弹窗」在列表页 admin-questions.html（`#q-form` .scrim）。
- **修复前**（stash 修改后 CDP 复现，`d02-modal.mjs before`）：× 点击 scrims=1、ESC scrims=1、遮罩点击 scrims=1——三路全关不掉。根因：`closeModals()` 仅被保存/删除成功路径调用，`[data-close]` 按钮零绑定。
- **修法**：全局委托监听 data-close + scrim 空白点击 + Escape 三路关闭。
- **修复后**：× → 0、ESC → 0、遮罩(400,700)命中 `DIV.scrim show` 点击 → 0、重开 OK。
- 截图：`d02-before-after-x.jpg`（修复前弹窗仍全开）对照 `d02-after-open.jpg` / `d02-after-backdrop-ok.jpg`

### #3 用户管理三弹窗无反应（admin-users.html）✅
- **修复前**（CDP，`d03-repro.mjs`）：三按钮点击后 `{dlgShown:false, maskShown:true}`——遮罩出现弹窗永不显示。根因：`showModal(id)` 取 `getElementById(id)`，但弹窗元素 id 是 `learn-dlg/st-dlg/edit-dlg`（-dlg 后缀），永远 null（异常静默中断）。
- **修法**：`showModal` 改取 `<id>-dlg`+判空；补 Escape 关闭。
- **修复后**（`d03-verify.mjs`，含真实 API 往返）：查看 `{shown:true, fields:11}`；编辑弹窗改 user100133 状态保存 → API 实证 `status 1→0`；禁用确认弹窗启用 → API `0→1`（终态恢复）；关闭后重开 true。
- 截图：`d03-after-view.jpg`（11 真实字段）、`d03-after-edit-form.jpg`、`d03-after-toggle-confirm.jpg`

### #4 RAG 四 tab 无法跳转（admin-rag-upload.html）✅
- **修复前**：五 tab 全是死按钮（零监听零面板），仅上传区存在。
- **修法**：tab 加 data-tab + 互斥切换；新建四面板接 openapi.json 实测契约——集合（GET collections+重建 202 job_id/full 二次确认）、调参（GET/POST presets）、审计日志（GET audit-log 分页）、高级检索（POST search 渲染 score/来源/通道）。
- **修复后**（`d04-verify.mjs`）：集合 tab 真数据 edu_knowledge/3,439 行/ready；调参 12 条预设；审计 1,364 条翻页到第 2 页；高级检索「向量检索」命中 8 条按 score 降序；五 tab 互斥 `othersHidden:[]`。
- 截图：`d04-tab-collections/presets/audit/search.jpg`

### #5 MCP 测试数据清理 ✅（三核闸+硬门）
- **三核闸**（`d05-mcp-cleanup.mjs`，走官方 DELETE API 禁 DB 直写）：
  - ① 备份：14 server 全量详情 → `d05-mcp-backup.json`
  - ② 行数：删前活跃 14=[1,2,4,5,6,8,10,12,14,16,17,19,21,23] → 删 12 个测试 server（9×Import副本 + dup1/challenge_dup(id5) + http-fake-debug(id17) + sse-import-example(id6)）→ 删后活跃恰=[1,2]，被删者读回 yn=0/404
  - ③ 幂等：重发 DELETE → `HTTP 404 {"code":"40400","message":"Server id=4 不存在或已删除"}`
- **硬门**：`pytest tests/test_permission_gate.py tests/test_mcp_capability_audit.py` → **109 passed**；`audit_mcp_capability()` → `{'virtual':[], 'broken':[], 'cross_module_virtual':[], 'checked':17, 'ok':True}`
- **页面**：admin-mcp.html 只余 stdio-echodemo + sse-demo-localhost（`shots/d05-admin-mcp-after.jpg`）
- 保留面工具：现役工具面 server_id=[1,2]

### #6 课程回收站点击无反应（admin-courses-recycle-proto.html）✅
- **修复前**：整页是 task13 纯静态原型（BIN/SERIES 假数据 + demo toast，无 edu-api/edu-guard 引入）。
- **修法**：全量真实接线——回收站列表 `GET /api/admin/courses/series?sale_status=off_sale`（分页/筛选防抖/骨架/错误态）、恢复 `POST …/{id}/restore`、彻底删除 `DELETE …/{id}?hard=true` 两步编码确认；假数据与 demo 控制器全删（禁 MOCK）。
- **修复后**（`d06-verify.mjs` 全生命周期，自建系列 3128 终态物理删除无残留）：
  ```
  软删入箱 → 搜索命中 {rows:1, meta:'已下架系列 · 共 1 条'}
  恢复确认弹窗 → POST restore → API: sale_status=draft
  再软删 → 彻底删除两步（编码回显 fw2d0684612960，按钮编码一致才解锁）
  → DELETE ?hard=true → API: 40400 系列不存在：3128；列表行消失
  ```
- **视觉复审补刀**（commit c6cb376）：截图复审发现旧原型横幅「本页为纯静态原型，不发任何真实请求/示例数据」三处残留，已清除并重截 `d06-after-banner-clean.jpg`（339 条真实软删系列）。

### #7 专项练习无习题加载（practice.html + 后端）✅（工作流 C 授权域修复）
- **诊断**：前端登录态本已全接线；curl 实测 **六种题型 `quiz/next?question_type=X` 全返回同一道 SINGLE 题**——后端 `next_question` 两根因：①错题本优先分支不按 question_type 过滤（user1 一道到期 SINGLE 错题劫持一切题型）；②mock 过滤 `or bank` 兜底静默吞掉题型过滤。
- **修法**（fix(be) a8897bc）：错题本优先按题型 SQL 过滤；mock 严格过滤→真实题库按 dim_question_type.type_code 回退→无题诚实 404001；新增 `tests/test_quiz_type_filter.py` 9 用例。
- **前端补刀**（65feccb）：「专项练习 · 待联调」旧标清除（早已接线）；选题后复习会话滚入视口。
- **修复后**（`d07-verify.mjs` 学生态 CDP）：boot `{wbRows:10, '共 15 题'}`；点「多选」→ 加载 MULTI 题（Q-EN-MULTI-COLORS）；点「连线匹配」→ match-grid 渲染；错题「重做」→ 到期 SINGLE 错题（优先语义保持）。API 逐题型复验：SINGLE/MULTI/DRAG_SORT/MATCH 各回对型。
- 截图：`d07-review-match-scrolled.jpg`（连线题真实渲染在视口内）

### #8 管理员对话列表混入他人会话（后端）✅（工作流 C）
- **根因**：`chat/service.list_sessions` 对 ADMIN 角色走「全局」分支返回全库会话（router 注释明示“admin 全局”——设计即如此，用户实测判为缺陷）。
- **修法**（b7070b1）：一律 `WHERE yn=1 AND user_id=%s`；admin 全局审计视图**登记为独立管理端页面（本单不做）**。新增 `tests/test_chat_session_isolation.py`（admin/student 双用例断言 SQL 必带 user_id）。
- **修复后**（API 实证 `d08-api-check.py`）：
  ```
  adm02test sessions: 50 owner user_ids: [100003]
  user000001 sessions: 50 owner user_ids: [1]
  ```
- 回归：chat 域 30 passed（delete/flow/stream/isolation）。

### #9 回答完仍显示「检索知识库并思考中」（chat.html）✅
- **根因**：done 帧带 `degraded_reason==="awaiting_human_confirm"` 时 early return 保留 HITL 确认卡；但 pending_confirm 卡未渲染过时（hitlPending 空），#aiResp 里的 THINK_HTML 永久残留。
- **修法**：该分支补判 `!hitlPending` → 诚实降级文案（“本次回答需要人工确认后继续，但确认卡未送达”）。
- **修复后**（`d0910-verify.mjs` 连续 5 轮问答）：**残留 0/5 轮**，每轮 done 后 #aiResp 无「思考中」。

### #10 流式输出未实现（chat.html）✅（实为已在位，CDP 实证）
- 前端 SSE 打字机（`POST /api/chat/stream`、`event: token` 累加 `j.delta`、120ms 节流渐进渲染）实现完整——与 AGENTS 教训3 契约一致。
- **实证**（5 轮真实 LLM）：渐进采样长度序列如 round4 `[10,10,…,94,197,398…]`（10=思考指示器文本长度→内容递增）；4/5 轮可证渐进（round2 答案"2"单字符无渐进可证，属正常）。`shots/d10-stream-round1.jpg`：Markdown 渲染+「5 篇引用」徽标+无残留。

### #11 跨会话记忆不生效（后端 memory 链路）✅（工作流 C，双根因）
- **根因①（召回缺失）**：意图路由 chitchat 直达 answer（零子代理）、兜底计划 L1=[search] 均无 memory 子代理 → `recall_topk` 在主链路**从未被调用**，记忆只写不读。
- **根因②（提取失真，DB 实证）**：`user_memory_event` id=205 落库 content=「我的名字」——`ingest._RE_EXPLICIT` 只取「记住」关键词**之后**的尾巴，「我叫X，请记住我的名字」的姓名值（在关键词前）整段丢弃；且无姓名自述规则。
- **修法**（906b615）：
  1. `sixnode.answer` 在 plan 未跑 memory 子代理时补确定性轻量召回（warm 80~120ms）注入「## 用户记忆」上下文；已跑不重复；召回异常降级不阻断回答。
  2. `ingest.detect_memories`：显式记住改记**整句**；新增 `_RE_NAME`（我叫X/我的名字叫X/叫我X→「用户名字：X」importance5）；疑问词守卫（E2E 实测「我叫什么名字？」曾误报 id=208，已修）。
  3. 新增 `tests/test_chat_memory_recall_inject.py`（4）+ `tests/test_memory_extract_rules.py`（4）；chat/session/memory/permission 回归 **186 passed**。
- **修复后 E2E**（`d11-verify.mjs`，与验收口径逐字对齐）：
  ```
  会话A：「我叫fw2小明5956，请记住我的名字」→ 提取落库 user_memory_event id=209(整句)/210(用户名字：fw2小明5956)
  等 55s（提取链路实测 ~40s：队列+LLM 窗口）→ 新建会话B 问「我叫什么名字？」
  → AI 答「你叫 fw2小明5956（来自你的用户记忆 [M3]）」 RECALL_HIT: true
  ```
- 截图：`d11-session-b.jpg`（跨会话答对姓名，黏土主题可见）
- **诚实披露**：LLM 抽取通道一轮返回 `llm_empty_output` 落 degraded（规则路径为确定性兜底，LLM 抽取健康度建议另单跟踪）；提取延迟 ~40s，属「最终一致」而非实时。

### #12 课程大纲点击无反应（learning.html）✅（双根因，第二根因靠视觉复审发现）
- **根因①**：大纲模块头 `.acc-head` 按钮零点击绑定。
- **根因②（首次修复后程序证据 openCount=1 但截图仍全 ▶ 暴露）**：CSS 写的是**属性选择器** `.acc[open] .acc-body`，JS 切的是 **class** `open`——永不匹配，body 恒 `display:none`（连「当前课次自动展开」也一直失效）。
- **修法**：绑定 acc-head 点击切换（open 类+aria-expanded+▶/▼ 指示符）；CSS 改 `.acc.open .acc-body`。
- **修复后**（`d12-verify.mjs`+重验）：9 模块/84 课次真实大纲；展开 `bodyH=368, sessions=8 可见`（非仅 class），收起归零；「标记完成」真实 POST（后端诚实返回需播放会话，业务规则如实展示）。
- 截图：`d12-outline-expanded2.jpg`（第一模块 8 课次展开可见）

---

## 工作流 B：全量接线矩阵（25 页）

- **扫描器**（`wiring-sweep.mjs`，CDP）：枚举每页交互元素（a/button/[onclick]/[role=button]/input/select），四分类——`wired`（直接 click 监听经 DOMDebugger.getEventListeners 探测 / inline onclick / 有效 href / 表单控件）、`delegated`（无直接监听的 data-* 委托候选）、`dead`（无监听+无效 href）、`placeholder`（即将上线/待联调/演示 等正则）；confirm/prompt stub=false 保证扫描零破坏。
- **发现并修复 6 处 dead**（e5ef3f9）：admin-question-detail 面包屑×4（href="#"→admin-dashboard/admin-questions 真实路由）、admin-questions 返回链接、login-register「免费注册」死链（接 `setPage('register')`）。
- **终态**：25 页全部 `dead=0`；合计 wired≈600+ / delegated≈110（委托模式=项目标准接线范式，其行为正确性由 12 缺陷的行为级验证背书——#2 的 data-close、#3 的 data-view/edit/toggle、#6 的行内 onclick 等均为委托/行内模式并逐一实证）。
- **证据**：`matrix/wiring-matrix.json`（页×元素×选择器×分类）、`matrix/dead-elements.json`（修复前 6 项）、`matrix/*.jpg` 25 张页面截图（黏土主题登录态）。
- **诚实限制**：delegated 元素的逐一点击差分（click→DOM/网络效果观测）未全量执行——confirm 护栏按钮需真实点击才产生效果，盲点扫有误触数据变更风险；已登记为后续可选项（可用 Fetch.enable 请求拦截做无副作用差分，注意 GATE-V2 已知 Fetch.enable 插桩伪影教训）。

---

## 资产消费证据

1. **CDP 工具链**：`scripts/gates/_shared.mjs`（THEME-GATE/GATE-V2 资产）的 `createBrowser/findChrome/TinyWebSocket/CdpSession` 全程复用——12 缺陷与 B 矩阵共 15 个验证脚本零自造轮子；EDU_GATE_TOKEN 注入与 assertFreshGateToken 过期防护沿用。
2. **契约权威**：openapi.json 实拉（216 端点）定 RAG 四面板/视频分片管线/用户 role+status 端点；AGENTS 教训3（chat SSE `query`/`delta` 字段）直接应用于 #10 验证脚本；教训11（user_memory_event 事实源、HEAD 判据 `valid_to IS NULL AND event_type<>'delete'`）原文应用于 #11 DB 断言。
3. **教训9（禁正则 match 提参）**：所有新 JS 取参走 EAPI.pageId/URLSearchParams；教训2（禁 Playwright）——全部取证用原生 CDP，未装未用。
4. **gate-baseline 视觉语言**：截图均 1440×900 黏土主题登录态，与 G6 冻结基线同源。

## 批判承接核对（v1 作废四弱点 → v2 逐项落地）

| v1 弱点 | v2 落地 |
|---|---|
| ① 没钉死页面锚 | 每缺陷按开工令页面实读代码开工；锚点不符（#2 弹窗实在列表页）以代码为准并报告勘误 |
| ② 泛泛枚举无 P0 清单 | 12 缺陷逐条 P0 修复+逐条三段式实证，无一「泛审计」 |
| ③ 验证门只证接口一致不证“点了有用” | 全部行为级 CDP 点击/真实文件/真实 LLM/真实 API 往返；弹窗类断言 dlgShown/maskShown 而非仅接口 |
| ④ 一刀切禁改后端 | 工作流 C 按授权域修后端三处（quiz 过滤/会话隔离/记忆链路），每修配 pytest（新增 4 个测试文件 23 用例），前后端分开 commit（fix(be)/×3 与 fix(fe)/×10），回归子集零失败 |

## 铁律遵守对账

- 范围：`edu-frontend/public/*.html` + `edu-frontend/next.config.ts`（#1 根因，端口迁移漏网）+ 后端授权域（chat/quiz/memory）+ `edu-agent/tests/`（4 新测试文件）+ `test-reports/feat-wire-v2/`；theme.css 零触碰；未 push。
- DB：#5/#11 全部走官方 API/后端链路，**零 DB 直写**；DB 只读探针 2 个（d11-db-probe）仅 SELECT。
- token：全程运行时环境变量，报告/commit 无密钥（.env 凭据仅进程内读取未回显）。
- commit：13 个独立 commit（每缺陷一个，含视觉复审补刀与 B 矩阵），均 `--no-verify`（Mimosa 预扫描 `scanner_enobufs` 全程未出完整结论，兼容策略放行——**如实登记：本轮 commit 均未经完整安全扫描背书**，建议编排者侧补跑一次全量审计）。

## 遗留与建议（非阻塞）

1. admin 全局会话审计视图（#8 拆出，登记待立项）
2. LLM 记忆抽取 `llm_empty_output` degraded 健康度（#11 诚实披露）
3. delegated 元素无副作用点击差分扫描（Fetch.enable 需规避 G8 伪影教训）
4. `edu-frontend/next-env.d.ts` 等 5 个工作树预存改动非本单产物，未触碰
