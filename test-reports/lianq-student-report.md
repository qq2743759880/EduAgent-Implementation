# 联调报告 · 学生侧学习数据链路（lianq-student）

- 执行日期：2026-09-15（11:25 ~ 12:00 前后）
- 执行人：Hermes Agent（联调执行 handoff `blind-t1-student-chain.md`）
- 工作区：`E:\stu\project\stu\EduAgent实施手册`；基线 HEAD = `83ba696`（工作区另有 116 条未提交改动，均为存量，本次未触碰）
- 测试账号：user000001 / Test@123456（role=student, user_id=1）
- 方法：全程真实 HTTP（curl/python 探针）+ 真实浏览器（前端 3000 实操）；禁 Mock；异常原样记录不修不绕
- 本次提交：仅本报告文件（探针/响应快照等辅助文件留在磁盘未提交，见附录）

---

## 0. 环境前置状态（与任务书不符处，原样记录）

| # | 现象 | 证据 |
|---|------|------|
| E1 | 任务书写"前端 3000 已运行"，实测 **未运行**（`curl 127.0.0.1:3000` Connection refused；netstat 仅 8000 LISTEN） | 启动记录见 `edu-frontend/next-dev-liaotestudent.log` |
| E2 | AGENTS.md 启动命令 `node next/dist/bin/next dev -p 3000` 报 `MODULE_NOT_FOUND`（仓库根无 `next/` 目录）；实际可用命令为 `node node_modules/next/dist/bin/next dev -p 3000`（Ready in 1303ms） | 启动日志首屏 |
| E3 | 后端 8000 全程在线，`GET /` 200 | — |
| E4 | `next.config.ts` 无任何 `/media` 代理/rewrites（全文 13 行，仅 allowedDevOrigins/standalone/distDir） | `edu-frontend/next.config.ts` |

> 上述 E1/E2 均为"与既有记载不符的环境事实"，本次未修改任何文件，按实测记录。

---

## 1. 登录链路

**请求**
```
POST /api/auth/login  HTTP/1.1
{"account":"user000001","password":"Test@123456"}
```
**响应摘要**：`code:0`，`data.access_token`（JWT，已留存 `test-reports/_liaotestudent_token.txt`，未提交），`data.user.role = "student"`，`user_id=1`。

**页面行为**：`/login-register.html` 表单 `#login-form`（`#li-id`/`#li-pwd`/`#login-btn`）提交后跳转 `dashboard.html`；`localStorage` 写入 `edu:auth:token` + `edu:auth:refresh`。✔ 页面与 API 一致。

---

## 2. AI 问答链路（POST /api/chat/stream，SSE）

### 2.1 实测前置：必须先建会话

对全新 session_id 直接发流式请求：

```
POST /api/chat/stream {"query":"ping","session_id":"s-curl-check","stream":true}
→ HTTP 404
{"code":"CHAT_SESSION_NOT_FOUND","message":"会话不存在：s-curl-check","data":null}
```

即流式端点**要求 session 先经 `POST /api/chat/sessions`（body 可空，成功返回 `session_id`，自动标题"新会话 xxxx"）创建**，否则在 SSE 建连前同步 404。这与 router.py:235-239 注释的"两段式错误模型"一致。

### 2.2 事件序列（raw 抓包，`test-reports/lt_raw_sse.txt`）

```
event: start     data: {"session_id":"s_19c17231c75d","query":"…"}          ← 裸对象
event: retrieval data: {"docs":[...],"graph_entities":[...],"retrieved_count":150,
                        "final_count":5,"rewrite_query":"…",
                        "degraded_reason":"rerank_sidecar_unavailable",
                        "mcp_tool_calls":[...]}                             ← 裸对象
event: token     data: {"delta":"1+1等于2。"}                                ← 裸对象，字段名 delta
event: done      data: {"code":0,"message":"ok","data":{"session_id":…,
                        "message_id":"m_…","retrieved_count":150,"final_count":5,
                        "latency_ms":4839,"rewrite_query":"…",
                        "degraded_reason":"rerank_sidecar_unavailable",
                        "mcp_tool_calls":[…]}}                              ← 包了响应壳！
```

**SSE 契约实测细节（与 `router.py:207-212` docstring 的出入）**：
1. `done` 事件 payload 外层包了 `{code,message,data}` 响应壳；`start/retrieval/token` 是裸对象 —— **同一流内包裹方式不一致**。消费方若统一按 docstring 读顶层 `latency_ms` 会读空。
2. `start` 实际字段是 `{session_id, query}`；docstring 写的是 `{session_id, message_id_pre(占位)}` —— 字段漂移，实测无 `message_id_pre`。
3. `token` 事件字段为 `delta`（与 AGENTS.md 教训 3/8 一致，注释里的 `token` 字段确已弃用）。

### 2.3 提问矩阵与时延（探针 `liaotestudent_sse_probe.py`，输出 JSON 快照 lt_*.json）

会话 A = `s_19c17231c75d`，会话 B = `s_fd9217767f10`（均为本次新建）。

| 轮次 | label | 类型 | 会话 | 首token(ms) | retrieval(ms) | done.latency_ms | retrieved/final |
|------|-------|------|------|------------:|--------------:|----------------:|----------------:|
| R1 | s1-concept | 概念题 | A | 5247 | 2917 | （探针v1未解壳） | — |
| R1 | s2-math | 计算题 | A | 20677 | 17079 | （同上） | — |
| R1 | s3-chitchat | 闲聊 | A | 4942 | 2198 | （同上） | — |
| R1 | s4-context | 上下文追问 | A | 14310 | — | （同上） | — |
| R1 | b1-concept | 概念题 | B | 3058 | — | （同上） | — |
| R1 | b2-crosstalk | 串会话试探 | B | 4911 | — | （同上） | — |
| R2 | r2-s1-concept | 概念题 | A | 4224 | 2393 | 5327 | 150/3 |
| R2 | r2-s2-math | 计算题 | A | 9203 | 7639 | 10497 | 150/5 |
| R2 | r2-s3-chitchat | 闲聊 | A | 3153 | 1152 | 4974 | 150/2 |
| R2 | r2-b1-concept | 概念题 | B | 3174 | 1220 | 3984 | 150/3 |
| R2 | r2-b2-crosstalk | 串会话试探 | B | 3567 | 1315 | 5420 | 150/5 |

（探针 v1 未解 `done` 的响应壳导致 done_lat 为空，v2 已修；两轮数据均保留。R1 整体慢于 R2，原样并列不解读成因。）

**回答质量摘要**：
- 概念题：两轮/两会话均给出准确的"最近发展区"定义（维果茨基、独立水平 vs 支架水平、教学启示），带 markdown 结构。
- 计算题（45 人、3/5 女生、女生比男生多几人）：分步表格正确，答案 **9 人**（27−18）无误。
- 闲聊：正常给去处清单，语气合适。
- 检索：每次 `retrieved_count=150 → final_count 2~5`，`retrieval.degraded_reason = "rerank_sidecar_unavailable"`（**11/11 次请求全部命中，无一例外**）；r2-s2-math 额外出现 `"Neo4j 扩展跳过（ValidationError）"`。
- 工具链路：提问"1+1等于几"时 `mcp_tool_calls` 出现 `add(a:1,b:1) → SUCCESS, latency 150ms, result {"sum":2}`（R12 LLM 工具决策链路活体）。

### 2.4 会话隔离实测

- 会话 B 第二问（b2，"接着刚才的问题…女生到底比男生多几人"）：回答明确否认见过该题，**未泄露会话 A 的数学题上下文**。✔ 跨会话不串。
- 但 B 的回答自称"**这其实是我们对话的开始**"，而当时 B 已有 1 轮历史（b1）—— 原样记录该回答与"已有历史"不符的现象。
- 会话 A 第四问（s4，"还记得刚才的计算题吗"）：完整复述题目并答 9 人。✔ 会话内上下文生效。
- **持久化核对（只读 API）**：`GET /api/chat/sessions` 返回 15 个会话（含历史存量与 `__probe__` 空会话），本次两个会话在列，A 标题被首问自动命名为"什么是最近发展区?…"；`GET /api/chat/sessions/{id}/history?limit=50`：A=16 条（8 轮），B=8 条（4 轮），与请求矩阵吻合。✔ 落库真实。
- 页面 `chat.html`：会话列表含本次两会话，点开 B 正确渲染 b1/b2 问答（与 API history 一致）；"3 篇引用"角标对应 retrieval.docs。✔

### 2.5 页面会话列表时间戳现象（原样）

`chat.html` 侧栏对 2026-08-13 的旧会话（`新会话 252ba0` 等）显示相对时间"**刚刚**"，与真实创建时间不符。

---

## 3. 学习页 learning.html（浏览器真实操作）

**操作序列**：登录 → `/learning.html`（选择班次页，2 张班次卡）→ hook fetch/XHR → 点击班次①「通用编程入门班·直播 202608期 · 继续学习」→ 课次页（第1课）→ 尝试播放 → 点击「标记完成（真实写入）」。

**实际网络调用（hook 捕获，全 GET 200）**：
```
GET /api/study/courses/1/access     （鉴权）
GET /api/study/courses/1/outline    （大纲：84 课次，0 完成）
GET /api/study/sessions/1           （课次详情）
POST /api/study/sessions/1/complete （标记完成）
GET  /api/study/courses/1/outline   （完成后自动刷新）
```
键控链路正确：班次卡携带 series_id=1 → outline/sessions 均以 series_id/session_id 请求（learning.html 页头契约与实现一致）。

**页面 ↔ API 一致项** ✔：课次标题"语法基础与开发环境 第1课"、teaching_status=completed、模块列表（0/8、0/10、0/10 ×3 组）、"0/84 完成"、作业 tab=2 条资源、考试 tab=0（诚实空态"本节暂无考试安排"）、简介字段缺失时的诚实说明文案。

### 3.1 【阻塞现象】视频 404（页面侧）

- 课次详情返回 `video_url: "/media/videos/VID-20260913-A3DA351A.mp4"`（相对路径）。
- 页面 `learning.html:672` 直接 `vdo.src = v.video_url` → 浏览器解析到 **http://127.0.0.1:3000/media/...**。
- 实测：
  - `HEAD :3000/media/videos/VID-...mp4`（页面内 fetch）→ **404**
  - `curl -r 0-1000 :8000/media/videos/VID-...mp4` → **206，video/mp4**（同一文件后端可达）
  - `<video>` 元素状态：`readyState=0, paused=true, networkState=2(NETWORK_LOADING), error=null`（无 error 事件，持续 loading 卡住；`v.play()` 返回 promise 但 currentTime 恒 0）
- 结论性事实：**同一 URL 经 8000 可达、经 3000 404**；next.config.ts 无代理（见 E4）。页面注释"实测 GET /media/... 200"（learning.html:662）与当前实测不符。

### 3.2 进度上报真实行为

- 页面**全程未发出任何 progress 打点请求**（hook 无 `tick-batch` 等调用）；页面文案明示"播放打点暂不上报（后端缺播放会话创建端点·缺口 task06-G1）"。
- `POST /api/study/sessions/1/complete`（未经观看直接调用）→ `{"code":0,"data":{"session_id":1,"completed":false}}`；页面同步显示降级文案"⚠️ 后端返回未完成：该课次暂无学习记录（播放会话未建立·缺口 task06-G1）"，按钮置灰。✔ 页面降级分支真实生效。
- 完成后 `outline` 仍 `completed_sessions: 0 / 84, ratio 0.0`；session 详情 `watch_ratio` 无变化。→ 本次操作**未产生虚假持久化**；同时意味着**当前链路下 watch_ratio 恒 0、complete 恒 false**（观看≥80% 判定永远无法满足）。

### 3.3 【不一致点】班次卡 0/28 vs 大纲 0/84

- 班次列表 payload（`GET /api/enrollments/me/cohorts`）：`session_total: 28, session_done: 0`，next_session.session_id=31（第3课）。
- 同一 series 的 `GET /api/study/courses/1/outline`：`total_sessions: 84`。
- 页面同屏呈现"课次进度 0 / 28"（班次卡）与"0/84 完成"（大纲），同屏数字不一致。（`GET /api/study/courses/2/outline` 另见 §8-P9：modules 有 9 组、18 个 module，8 组 sessions 空、仅 1 组 1 个课次，total_sessions=1。）

---

## 4. 收藏与成就

### 4.1 收藏

- 基线：`GET /api/favorites?page=1&page_size=20` → total=4（series 1/1005/2618/2628）。
- 操作：`POST /api/favorites {"series_id":2}` → `code:0, favorite_id:30014, series_title:"通用编程入门班·录播"` ✔ 幂等语义见 service.py:172。
- **【现象，原样】** 响应中 `created_at: "2026-08-30T21:38:14"` —— 是过去时间（操作发生在 2026-09-15），非本次操作时刻。复测 `GET /api/favorites` 中该条 created_at 同为 2026-08-30T21:38:14。
- 复查：total=5，新 series 2 在列。✔ 收藏真实落库。
- `me.html` 收藏区：显示"共 5 个收藏 · 展示最近 4 个"，卡片与 API 前 4 条一一对应（标题/收藏时间一致）。✔

### 4.2 成就页 achievements.html

- **【现象，原样】token 被清空**：浏览器会话中段（登录→learning 操作成功之后）访问 achievements.html 显示"🔑 登录后查看我的成就"登录门，且 `localStorage['edu:auth:token']` 长度=0、`EAPI.store.getToken()` 为空；同一时刻 curl 携带留存 token 调 `GET /api/auth/me` 仍 200。将留存 token 重新写回 localStorage 后页面正常渲染。事后 hook 未再捕获任何 401（清空动作发生在何时/由哪次请求触发，未观测到，按守则不解读成因）。
- 恢复后页面真实渲染，与 API 对照：
  - 积分面板：`349 当前积分 / Lv.1 萌新 / 流水共 31 条`，最新流水 `2026-09-06 18:13:12 COMMENT_CREATE +2` ✔ 与 `/api/gamification/me/points` 完全一致。
  - 排行榜（总榜 ALL_TIME×POINTS，页面点选后 `200`）：Adm02Test 160分 > **edu_user_000001（我）35分** > 123456 5分；我的徽章数 3 —— 行数据与 API `top[]`/`my_rank` 一致 ✔。
  - **【不一致点 P1】同页两个积分对不上**：排行组件显示我 `metric_value=35`，积分面板显示 `total_points=349`（数据分别来自 `/api/gamification/rankings` 的 ZSET 与 `/api/gamification/me/points`）。
  - **【现象 P2】徽章进度超 100% 未解锁**：`BDG-STUDY-1H progress_current=150 / progress_required=60, unlocked=false`（BDG-STUDY-10H/100H 同为 150 起步）；`next_milestone:"📚 勤学苦练（进度 150/600，25%）"`。
  - **【现象 P3】今日活动零流水**：本次 12 轮问答+收藏操作后，`/me/points` 最新流水仍是 2026-09-06（logs_total=31 不变）。
  - 默认 tab（WEEKLY×POINTS）显示"该榜暂无数据"——API 语义下周榜为空属正常，但页面无空态引导时观感像故障（原样记录）。
  - 参数风格：`scope/dimension` 必须大写枚举（ALL_TIME/POINTS…），小写报 `code:"42200"`（页面用法正确）。
- `GET /api/users/me/learning-summary`：`total_watched_seconds: "6664"` —— **字符串类型**（数字被引号包裹），页面 me.html 显示"2 h"（6664s≈1.85h，四舍五入为 2）。✔/⚠ 类型与展示口径各记一条。

### 4.3 me.html 交叉核对

| 区块 | 页面显示 | API 实测 | 结论 |
|------|----------|----------|------|
| 我的订单 | 共 33 笔 · 第 1/7 页（前 5 条：3×已取消、1×待支付…实付 ¥2999） | `GET /api/trade/orders?page=1&page_size=1` → total=33 | ✔ 一致 |
| 优惠券（未使用） | 共 96 张 · 第 1/24 页（平台通用解锁券·减10000 ×4 可见） | `GET /api/coupons?status=unused&page=1&page_size=1` → total=96 | ✔ 一致 |
| 收藏 | 共 5 个 · 展示最近 4 | total=5，顺序一致 | ✔ 一致 |
| 积分/等级 | 349 / Lv.1 萌新 | total_points=349, level_no=1 | ✔ 一致 |
| 数据概览-学习时长 | 2 h | learning-summary total_watched_seconds="6664"（string） | ✔（口径成立，类型见 P4） |

---

## 5. 数据一致性终查（步骤 2-4 产生数据的只读回读）

| 数据 | 产生方式 | API 回读 | 页面呈现 | 一致性 |
|------|----------|----------|----------|--------|
| 会话 A 8 轮对话 | SSE 提问 | history 16 条消息，内容/顺序吻合 | chat.html 渲染一致 | ✔ |
| 会话 B 4 轮对话 | SSE 提问 | history 8 条 | chat.html 渲染一致 | ✔ |
| 收藏 series 2 | POST /api/favorites | total 4→5，条目在列 | me.html 5 个收藏 | ✔ |
| 课次完成标记 | POST complete | completed:false，outline 仍 0/84 | 页面降级文案 | ✔（无假写） |
| 播放进度 | （页面不打点） | watch_ratio 0 | 页面 0% | ✔（但恒 0，见 §3.2） |
| 积分流水 | —（今日无新增） | 最新 2026-09-06 | 成就页流水一致 | ✔（P3 现象另记） |
| 排行榜我的分值 | — | ZSET=35 vs points=349 | 同页两值并列 | ✘ P1 |

---

## 6. 本次产生的测试数据清单（按守则保留，不删除）

| 数据 | ID/键 | 规模 | 说明 |
|------|-------|------|------|
| chat 会话 A | `s_19c17231c75d` | 8 轮（16 条消息） | 标题被首问占用 |
| chat 会话 B | `s_fd9217767f10` | 4 轮（8 条消息） | — |
| 收藏 | favorite_id `30014`（series_id 2） | 1 条 | 复用了 2026-08-30 的历史记录位（见 §4.1 现象） |
| 课次完成请求 | session_id 1 | completed:false | 未持久化任何完成态 |
| SSE/输出快照 | `test-reports/lt_*.json`、`lt_raw_sse.txt`、`lt_cohorts.json`、`lt_outline*.json`、`lt_sess1.json`、`lt_rank.json`、`_lt_body.json` | 17 文件 | 未提交，见附录 |
| 前端启动日志 | `edu-frontend/next-dev-liaotestudent.log` | 1 文件 | 本次新起前端产生 |

说明：后端存在 `DELETE /api/chat/sessions/{session_id}`（软删）可清会话，按守则本次**未调用**；收藏无删除端点见 router 注释（DELETE /api/favorites/{series_id} 存在于 market/router.py:13，本次同样未调用）。其余页面无删除入口，均未产生不可追溯数据。

---

## 7. 页面 ↔ API 不一致点汇总

| 编号 | 位置 | 现象 | 影响 |
|------|------|------|------|
| P1 | achievements.html / rankings ZSET | 排行榜我=35 分 vs 积分面板/`/me/points`=349 分，同页并列 | 高：积分口径分裂 |
| P2 | achievements.html / badges | BDG-STUDY-1H 进度 150/60（>100%）unlocked=false，10H/100H 同值 | 高：进度单位疑似错位 |
| P3 | achievements.html / points 流水 | 今日问答/收藏零流水，最新 2026-09-06 | 高：激励数据不实时 |
| P4 | learning/me / learning-summary | `total_watched_seconds` 为字符串 "6664" | 中：消费方需容错 |
| P5 | learning.html:672 + next.config.ts | `/media` 相对路径落 3000 → 404；8000 直连 206 正常 | **高：视频在当前部署形态不可播** |
| P6 | learning.html 班次卡 vs outline | 0/28（cohorts.session_total）vs 0/84（outline.total_sessions） | 中：同屏数字矛盾 |
| P7 | chat.html 侧栏 | 8 月旧会话相对时间显示"刚刚" | 低 |
| P8 | SSE done 事件 | 外层包 `{code,message,data}` 壳；start/retrieval/token 裸对象；start 无 docstring 所述 `message_id_pre` | 中：流消费方解析陷阱 |
| P9 | `GET /api/study/courses/2/outline` | series_id=2（录播）总课次=1，9 组 module 重复、8 组 sessions 为空 | 低（未入页面主流程，疑种子数据形态） |
| P10 | achievements.html 初次进入 | 已登录状态下显示登录门 + token 已被清空（清空时机未观测到） | 中：登录态可靠性 |

---

## 8. 报错/卡顿/困惑原样记录（未修未绕）

```
1. POST /api/chat/stream (新 session_id) → HTTP 404 {"code":"CHAT_SESSION_NOT_FOUND","message":"会话不存在：s-curl-check"}（探针首跑 status None, 0 events）
2. AGENTS.md 前端启动命令 → node: Cannot find module 'E:\...\edu-frontend\next\dist\bin\next' (MODULE_NOT_FOUND)
3. 每次 retrieval 均带 "degraded_reason":"rerank_sidecar_unavailable"；r2-s2-math 额外 "Neo4j 扩展跳过（ValidationError）"
4. 探针 v1 读 done.latency_ms 全为 null（壳包裹所致，v2 解壳后正常）——困惑点：同一流内壳包裹不一致
5. R1 s2-math 首 token 20.7s、s4 追问 14.3s，R2 同题 9.2s；R1/R2 时延差异明显
6. <video> 经 3000 播放：HEAD 404；元素 networkState=2 持续 loading，无 error 事件，无播放
7. localStorage token 在会话中段被清空（登录门出现），当时无 401 被观测；重写 token 后恢复
8. POST /api/favorites 返回 created_at=2026-08-30T21:38:14（操作时刻为 09-15）
9. rankings 小写参数 → {"code":"42200","message":"String should match pattern '^(DAILY|WEEKLY|MONTHLY|ALL_TIME)$'"}
10. b2-crosstalk 回答自称"这其实是我们对话的开始"，但该会话此前已有 1 轮问答
11. chat.html 侧栏 __probe__ 等历史空会话显示"刚刚"
12. 页面 cohort 卡"0 / 28"与大纲"0/84"同屏并存
```

---

## 9. 下周开发者最需要知道的 3 件事（学习周报聚合端点）

1. **"学习时长/进度"目前没有真实数据源**：页面不发 tick-batch（task06-G1 缺口），`/complete` 恒 `completed:false`，watch_ratio 恒 0；`learning-summary.total_watched_seconds` 还是字符串类型（"6664"）。周报里任何学习时长/完成率指标，要么等缺口闭环，要么明确写清降级口径——直接聚合会把 0 当真实值。
2. **积分是双源且打架的**：rankings（ZSET）=35 vs points 表=349，且今日活跃不产生新流水（最新 2026-09-06），徽章进度还会出现 150/60 的超限值。周报的积分/激励维度必须先裁定权威源（建议 points 表），并把"实时性"写进口径，否则同一份周报会出现两个总积分。
3. **问答数据从表聚合、别走 SSE 回放**：会话/消息已真实落库（`GET /api/chat/sessions` + `/{id}/history`，user/assistant 成对、含 rag_retrieved_count 等 RAG 字段），够周报统计；若确需复用 SSE，注意 done 事件带响应壳、start 字段与 router docstring 漂移、且必须先 POST /api/chat/sessions 建 session（否则 404 CHAT_SESSION_NOT_FOUND）。另：当前环境 rerank sidecar 不可用（11/11 次 retrieval degraded），如周报含检索质量指标，先看 `degraded_reason` 分布再下结论。

---

## 附录 · 本次磁盘辅助文件（均未提交）

```
test-reports/liaotestudent_sse_probe.py     SSE 计时探针（可复跑）
test-reports/_liaotestudent_token.txt       学生 JWT（敏感，勿入库）
test-reports/lt_s1..s4, lt_b1, lt_b2.json   R1 提问快照（探针 v1）
test-reports/lt_r2_s1, r2_s2, r2_s3, r2_b1, r2_b2.json  R2 提问快照（探针 v2）
test-reports/lt_cohorts.json / lt_outline1.json / lt_outline2.json / lt_sess1.json / lt_rank.json
test-reports/_lt_body.json / lt_raw_sse.txt / lt_openapi.json
edu-frontend/next-dev-liaotestudent.log     前端本次启动日志
```

复跑方式：`cd test-reports && python liaotestudent_sse_probe.py "<问题>" <session_id> <label>`（需先 `POST /api/auth/login` 换新 token 写入 `_liaotestudent_token.txt`）。
