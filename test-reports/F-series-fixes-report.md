# F 系列修复报告（F-1 ~ F-5）

- 分支：`feature/opt-waves`
- 执行：修复工程师独立执行；本报告供编排者**独立复验（双环，不采信自述）**
- 时间：2026-09-15
- 服务环境：后端 uvicorn 8000、前端 next dev 3000（全程**未重启在跑进程**；临时验证实例用 3001 端口，验证后已停并清理）
- 硬性守则遵守：无 DB 直写（数据写入均经 API；只读核查用参数绑定 SQL / redis-py 只读）；三份冻结契约未动；未改 edu-api.js / admin-* 页面；未用 Playwright；每个发现独立 commit。

## Commit 列表

| commit | 项 | 标题 |
|---|---|---|
| `4b68a96` | F-1 | fix(f)/F1-media-proxy: /media/* 同源反代到后端 8000 |
| `3fb69da` | F-2 | fix(f)/F2-points-sync: 积分双源对齐（self-heal + 对账脚本） |
| `8e2a037` | F-3+F-5 | fix(f)/F3F5-sse-envelope-doc: 钉死 SSE 帧信封契约 + docstring 对齐（零线变更） |
| —（无） | F-4 | **现状已修复，任务描述漂移**：见下文 F-4 节，按守则 4 停下上报，不造改动 |

---

## F-1（P1）/media 跨源断链 → 前端代理

### 改动（3 文件，仅配置）

1. `edu-frontend/next.config.ts`：新增 `MEDIA_PROXY_TARGET`（默认 `http://127.0.0.1:8000`，env 可覆盖），在 `rewrites()` 的 `afterFiles` 增加
   `{ source: "/media/:path*", destination: "${MEDIA_PROXY_TARGET}/media/:path*" }`。
2. `deploy/frontend.Dockerfile`：builder 阶段 `ARG/ENV MEDIA_PROXY_TARGET=http://backend:8000`（rewrites 在 `next build` 烘焙）。
3. `deploy/docker-compose.yml`：frontend build args 增加 `MEDIA_PROXY_TARGET: ${MEDIA_PROXY_TARGET:-http://backend:8000}`。

### GWT 验证证据

- **①（现网 3000 已生效，无需重启 dev——next dev 监测 next.config 变更自动重配）**
  `curl.exe -sI http://127.0.0.1:3000/media/videos/VID-20260913-A3DA351A.mp4`
  → `HTTP/1.1 200 OK`、`content-type: video/mp4`、`content-length: 3145728`（与 8000 直连逐头一致）。
  另在独立临时实例（`.next-fverify`, 127.0.0.1:3001，验证后已停、目录已删）验证：Range `bytes=0-1023` → `206 Partial Content`、1024 B（播放器 seek/分段加载可用）。
- **② learning 视频起播（网络层面）**：`<video src="/media/videos/...">` 现落 3000 origin 由 rewrite 代理返回 200/206 + `video/mp4`，无 404；同页 8000 直连对照 200。
- **③ 零回归抽查**：临时实例下 `GET /learning.html`、`/achievements.html`、`/courses.html`、`/` 均 200；现网 3000 复查 `/achievements.html` 200。

### 行为变更声明

- 仅新增一条 afterFiles rewrite（静态资源/路由优先，未命中才代理），不改变任何 API 路径与页面；后端零改动。
- 生产形态（Docker build）默认指向 compose 网络名 `http://backend:8000`，可用 build arg/env 覆盖。

---

## F-2（P1）积分双源打架（排行榜 ZSET=35 vs 面板 349）

### 根因（已查实，非臆测）

写入侧只有一个活入口 `award_points()`（`edu-agent/app/gamification/service.py`）：MySQL `user_point_log` 落账成功后 `_zincr_points_zset()` 对 4 个 scope ZINCRBY，**两源本来同源**。35 vs 349 的分叉来自三处：

1. **历史数据绕过入口**：`user_point_log` 中 LEARN_MIN 4400 分、QUIZ_CORRECT/QUIZ_FULL_CORRECT 260 分等由历史 seed / SQL 导入 / `p6_hit.py` 打靶脚本直接 INSERT（全仓 grep 确认活应用代码无入口），ZSET 从未收到这些增量。
2. **Redis 故障/清空窗口 fail-open 丢增量**：写入策略是「MySQL 落账成功即提交，ZINCRBY 失败只告警不回滚」——uid1 在 09-02/03 的 award_points 增量（POST/COMMENT/BADGE_BONUS 共 151 分）与 ZINCRBY 一起丢失；ZSET 停在 35 旧快照。
3. **读取侧永不重算**：`_ranking_from_zset()` 仅在 key **完全为空**时用 SQL 回填；非空键（哪怕值过期/偏小）永不与账本对齐 → 分叉被冻结。

### 修复（事件驱动同步 + 一次性对账，2 个代码文件 + 1 个脚本）

1. `app/gamification/service.py` 新增 `_self_heal_my_points(user_id, scope, snap, now)`：`ranking()` 的 POINTS+ZSET 路径上，对**请求者本人一行**用账本 SUM 真值比对 ZSET 行值，漂移则 `ZADD` 绝对写回并修正本次响应；Redis/账本任何异常静默跳过（**fail-open 不变**）；用户不在榜不写；不触碰其他人的行。
2. 新增 `edu-agent/scripts/reconcile_points_zset.py`：一次性全量对账（运维用），**默认 dry-run**，`--apply` 才写 Redis；`ZADD` 绝对对齐 + `ZREM` 幽灵成员 + `EXPIRE` 续期；只处理当前周期 4 个 key，历史周期 key 仅列出 SKIP（由 TTL 自然过期）；**只写 Redis，MySQL 零写入，不清空任何真实积分**。
3. 新增 `tests/test_gamification_points_sync.py`（7 条）：入口 4-scope ZINCRBY + 幂等 biz_key 不重写 + Redis 宕机 fail-open；self-heal 的漂移写回 / 无漂移不写 / ZADD 失败仍返真值 / 账本异常原样返回 / 不在榜不写。

**不发明新积分规则**：以下事件映射仅为现状陈述（MySQL `user_point_log` 全量实证），问答/收藏是否该加分属产品决策，本单不改任何加分行为。

### 积分事件映射表（当前实际行为，2026-09-15 账本实证）

| point_type | 单次 | 条数 | 合计 | 活的应用入口 |
|---|---:|---:|---:|---|
| LEARN_MIN | 1/分钟 | 8 | 4400 | **无活入口**（历史 seed / p6_hit.py 打靶） |
| BADGE_BONUS | 徽章配置值 | 9 | 690 | `check_and_unlock_badges → award_points`（解锁自动） |
| POST_CREATE | 5 | 58 | 290 | community `create_post` |
| QUIZ_CORRECT | 10 | 19 | 190 | **无活入口**（测试/打靶） |
| COMMENT_CREATE | 2 | 66 | 132 | community `create_comment` |
| exp | 100 | 1 | 100 | 历史数据 |
| QUIZ_FULL_CORRECT | 30（实际 10） | 7 | 70 | **无活入口** |
| LIKE_GAIN | 2 | 8 | 16 | `toggle_react`（仅他人赞自己的帖/评） |
| MANUAL | 任意 | 2 | 2 | admin award |

HW_SUBMIT / EXAM_PASS / VOCAB_MASTERED 在 POINT_TYPE_LABEL 字典中，但无数据、无活入口。

### GWT 验证证据

- **① 对账后 my 分值 = 面板 total（±1 内）**：`--apply` 实测 MONTHLY 修 uid1 35→186、uid100003→257；ALL_TIME 修 17 个成员（uid1→349，并补入 uid2=4957 等账本有而 ZSET 缺的成员），共 19 个 ZADD、MySQL 零写入。对账后 API 实测：面板 `total_points=349`；`rankings?scope=ALL_TIME` source=**ZSET** my=**349**（差 0）；MONTHLY my=186（与 SQL 月度 SUM 一致）。
- **② 再造真实加分事件两源同步**：学生 token 真实 `POST /api/community/posts/74/comments`（comment#67，返回 `points:2`，COMMENT_CREATE）。事件前：面板 349 / ZSET ALL_TIME 349 / MONTHLY 186 / DAILY 0；事件后：面板 **351**（recent_logs 首条 COMMENT_CREATE +2）、ZSET ALL_TIME **351**、MONTHLY **188**、DAILY **2**，source 均 ZSET——两源逐 scope 同步同增量。
  事后再跑 `reconcile_points_zset.py` dry-run：MONTHLY/ALL_TIME 均「待修正=0、待 ZREM=0」（脚本幂等/无残留漂移）。
- **③ pytest**：`test_gamification_points_sync.py` + `test_community_service.py` + `test_contract_task15.py` + `test_contract_task113.py` 合计 56 passed（全量连跑时 `test_next_excludes_correct` 1 次 429 失败，系登录接口 60s 限流窗口被套件自身打满；安静 70s 后单跑该类 **1 passed**，与本单改动无因果——本单未触及登录/quiz 任何代码路径）。

### 红线遵守

- Redis 降级态 fail-open 行为保持（self-heal/对账异常均静默，不阻断读、不回滚 MySQL）。
- 未清空、未覆盖任何用户真实积分：对账是「账本 → ZSET」单向绝对对齐，MySQL 全程只读。

---

## F-3 + F-5（P2/P3）SSE 信封不一致 + start 字段漂移——钉契约 + 对齐文档

### 冻结的现状（curl/源码/契约测试三重实证；前端 edu-api.js 已按此解析，改线=破坏性）

| 事件 | 形状 |
|---|---|
| start | **裸帧**，恰好 `{ session_id, query }` |
| retrieval | **裸帧**，恰好 `{ docs[], graph_entities[], retrieved_count, final_count, rewrite_query, degraded_reason, mcp_tool_calls[] }` |
| token | **裸帧**，恰好 `{ delta }`（前端逐帧累加 `delta`；旧 `token` 字段已弃用） |
| done | **唯一带壳帧** `{ code:0, message:"ok", data:{ session_id, message_id, retrieved_count, final_count, latency_ms, rewrite_query, degraded_reason } }` |
| error | **裸帧** `{ code, message }`（落库失败额外带 generated_tokens/session_id/message_id） |

两条产生路径（旧 `service_chat_stream` 与默认 `flows/graph_stream.py` 图适配层）逐帧同构。原语 `app/chat/sse.py::sse_line` 线格式 `event: <名>\ndata: <json, ensure_ascii=False>\n\n`。

### 改动

1. **新增** `edu-agent/tests/test_sse_envelope_contract.py`（4 条，离线 ASGI + httpx，不连后端/LLM/DB）：
   - 旧路径（`STREAM_VIA_GRAPH=False`）与图路径（`True`，真实 `graph_stream` 发射器 + 桩图/桩 guard/MCP/finalize）各跑一遍，逐帧断言上表键集合、帧序 start→retrieval→token(n)→done、delta 拼接=答案、done 壳 code=0/message=ok/data 7 键；
   - `sse_line` 线格式逐字节断言（含中文不转义）；error 帧裸 `{code,message}` 不套壳。
2. `app/chat/router.py` `/stream` **docstring 对齐实现（F-5）**：`start` 从文档臆造的 `message_id_pre (占位用)` 改为实际的 `query`；retrieval 补 `final_count`/`mcp_tool_calls`；done 标注统一壳；error 标注 `code` 及落库失败附加字段。

### GWT 验证证据

- 契约测试 4/4 PASSED；与既有 `test_chat_stream_error.py`、`test_contract_task_r02.py` 连跑 **26 passed**。
- docstring 与实现 grep 对照：`graph_stream.py` start 发 `{session_id, req.query}`、retrieval 7 键、token `{delta}`、done `{code:0,message:"ok",data:final_info}`；router 旧路径同构；docstring 现逐行与之一致。
- **行为变更声明：零线变更**。`git diff` 该执行文件仅 docstring 15 行（9 增 6 删），`py_compile` 通过，无任何执行行改动。

---

## F-4（P2）徽章进度 150/60 超限 —— 任务描述漂移，现状已修复（未改动、未提交）

按守则 4「现状自证，漂移即停下上报」，开工核实发现该缺陷**在本单之前已修复**，故不制造任何改动：

- 静态页 `edu-frontend/public/achievements.html:540`
  `var prog = Math.min(100, Math.round(bd.progress_pct || 0));`（进度条宽度钳制）；
  同文件 L543 文案如实渲染 `<cur>/<req>`（150/60 原样显示，不谎报成 60/60）。
  `git blame`：`a86a9e9f`（2026-09-02，task105）引入，非本单改动。
- 后端 `app/gamification/service.py:132`：`pct = 0.0 if req <= 0 else min(100.0, cur / req * 100)`——下发的 progress_pct 本身已 ≤100。
- React 侧同源钳制：`src/components/achievement/BadgeWall.tsx:76` `Math.min(100, …)`（PointOverview.tsx:31 同样钳）。
- 真实数据实测（`GET /api/gamification/me/badges` user_id=1）：BDG-STUDY-1H **150/60 pct=100.0 unlocked=true**、BDG-COMMUNITY-STAR 269/10 pct=100、BDG-QUIZ-FIRST 6/1 pct=100——前端取 pct=100 渲染满条（width:100% 不溢出），文案显示真实 150/60。

**结论：GWT（超限不溢出 + 文案如实）在现状下已满足，无需 commit。请编排者裁定是否销项。**

---

## 复验建议（给双环独立复验者）

```powershell
# F-1（现网即可，无需重启）
curl.exe -sI http://127.0.0.1:3000/media/videos/VID-20260913-A3DA351A.mp4   # 期望 200 video/mp4 3145728
# F-2
cd edu-agent
.\.venv\Scripts\python.exe scripts\reconcile_points_zset.py                  # 期望全部「待修正=0」
.\.venv\Scripts\python.exe -m pytest tests/test_gamification_points_sync.py -q
# F-3/F-5
.\.venv\Scripts\python.exe -m pytest tests/test_sse_envelope_contract.py tests/test_chat_stream_error.py -q
git diff 4b68a96~1 8e2a037 -- edu-agent/app/chat/router.py                    # 确认 F-3 执行行零改动
# F-4：无提交，核对 file:line 与 blame a86a9e9f
```
