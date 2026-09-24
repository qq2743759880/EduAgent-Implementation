# REPORT-TC1 — 简历主张全量重测矩阵（yy · P2）交回

> 开工令：`.ai-hub/plans/artifacts/dispatch/TO-EXEC-TC1.md`
> 分支 `feature/opt-waves`；开工基线 `git log --oneline -3` 首行 = `976002a`
> 产物：`docs/简历实测矩阵.md`（矩阵全文 + 修订建议 §2 + 缺陷 §3 + 复现命令附录）；**其全文已誊录于本报告 §9**，故本报告自包含。

## 1. 跑批统计

矩阵 **29 行**（覆盖 27 条主张；「HITL 确认卡」一条拆为 卡 / reject 零写 / approve 落库 3 行，另补 VEC-LOCK、OTLP 两个门禁行）。

| 判定 | 条数 | 占比 | 序号 |
|---|---|---|---|
| PASS | **17** | 58.6% | 3,4,7,8,9,11,14,15,16,19,22,23,25,26,27,28,29 |
| PARTIAL | **8** | 27.6% | 1,2,5,6,10,12,18,21 |
| FAIL | **2** | 6.9% | 13（跨会话记忆召回）、24（内部可见性数字口径） |
| SKIP | **2** | 6.9% | 17（HITL approve，避免在共享演示库重复建课）、20（108MB 断网分片上传） |

**PASS+PARTIAL = 25/29 = 86.2%**；两项 FAIL 均指得到具体证据（§3 TC1-F1 / TC1-F3）。

## 2. 主张来源说明（重要）

开工令口径 ①「owner 随开工令附的简历原文（信使转派时粘贴）」**本次未随单到达**——转派消息只带了 `TO-EXEC-TC1.md` 本体，全仓检索 `*简历*` / `*resume*` 也无该文本。
→ 按口径 ② 回退到仓库权威清单合并去重：`docs/check-demo-21项详解.md`（21 项体检单全项）+ `docs/面试演示-逐步点击手册.md`（全部站点 + 服务全景表）+ `.opencode/plans/critique-backlog-tracker.md` 已闭环项，得 **27 条主张**。
→ **若 owner 手上有简历原文，请回贴**，我按同一矩阵口径可半天内补齐差异行（矩阵结构已固化，补行成本极低）。

## 3. 今日新发现缺陷（建议转返工单；本单零代码/配置改动）

| ID | 现象 | 证据（可复跑） | 影响 | 建议 |
|---|---|---|---|---|
| **TC1-F1** | **跨会话记忆召回恒空** | `[Memory:vector] Milvus upsert 失败，转下一档：value 'NaN' is not a number or infinity`（4/4 轮）；新会话答「我不知道你的名字，memory 为空」；`user_memory_event` 写入正常（`memory_type=profile`，槽位 `user_name` 关旧 HEAD） | 记忆功能对客不可演示 | ① 查 NaN 来源；② **档位不对称**：`upsert` 降级到进程内档，`search()` 仍固定优选 Milvus → 应记录"当前生效档"并让 search 跟随 |
| **TC1-F2** | 记忆抽取 LLM 上游不可用 | `LLM HTTP 400: InvalidSubscription … account (2120516166) does not have a valid AgentPlan subscription`，degraded 累计 6→11 | 抽取质量降级（规则候选仍入库） | 续订 / 换 key；失败率进监控页 |
| **TC1-F3** | 内部可见性断言口径失效（门禁 ⑭ 将长期红） | `wnextint1a_visibility_probe` → `student_hits_total=14 / admin=25 / student_hits_zero=false`；命中源为 `_default` 分区内 `up_100003_*` 用户自上传文档 | 门禁 ⑭ 红线 | 断言改为分区/来源级（student 不得命中非自身 tenant 文档），别用关键词级 |
| **TC1-F4** | 前端门禁须**双令牌**否则假红 | 仅 `EDU_GATE_TOKEN`（admin）：G6 1 红 / G7 2 红，全部 `refund.html`；补 `EDU_GATE_STUDENT_TOKEN` 后 **G6 0 / G7 0** | 易被误判"页面回归" | 已文档化于 `scripts/gates/page-roles.json`；建议缺学生令牌时**显式提示**而非静默假红 |
| **TC1-F5** | 探针默认端口漂移 | `mcp_tristate_probe.py` 默认 `http://127.0.0.1:8000`，裸跑报"后端不可达"；传 9988 即 PASS（`audit_checked=17`） | 排查误导 | 默认改 9988 或读 `CHECK_DEMO_BACKEND` |
| **TC1-F6** | 🔴 **⑯ lifecycle 门是「假红」——探针自身 bug，后端启停其实健康** | 复跑 `_lifecycle_real_verify.py 5` 仍 `pass=false / avg_start_ms=0 / avg_stop_ms=0 / detail="lifecycle 不达标"`；但同轮日志 `logs/lifecycle_real_{1..5}.log`（**仓库根** `logs/`，非 `edu-agent/logs/`）**每轮都完整启动成功**：`Started server process [22872]` → `Application startup complete.` → `Uvicorn running on http://127.0.0.1:18000`，且 `grep -c "Traceback\|CancelledError\|Application shutdown failed"` = **0**。根因直证：探针 `edu-agent/scripts/_lifecycle_real_verify.py:46` 用了**从未定义的 `PROBE_PORT`**（局部变量实为 `probe_port`，:29），抛出 `NameError: name 'PROBE_PORT' is not defined` 被同段 `except Exception: pass` **吞掉**（`python -c` 单行复现已出同型 NameError）→ 健康检查永假 → 每轮空转 30s 后 `proc.kill()` → 5 轮 ≈156s 恒 FAIL，且**从未真正走到优雅关停分支**（等于零覆盖） | ① **21 项体检单永远无法全绿**，`演示环境就绪` 汇总被长期污染为红；② 极易被误归因为"后端启停不健壮"（本次首轮我就先记为"结论受限"，靠复跑+读日志才翻案） | 1 行修：`:46` 的 `PROBE_PORT` → `probe_port`（或模块级定义 `PROBE_PORT = probe_port`）；建议顺带把 `except Exception: pass` 收窄为 `except OSError`，否则同类"未定义变量/拼写错误"型探针 bug 会继续被静默吞掉 |
| **TC1-F7** | KG 文档块→知识点边缺失 | 后端日志 `UnknownRelationshipTypeWarning … missing relationship type is: MENTIONS`（`DocChunk-[:MENTIONS]->KnowledgePoint`）；检索侧 `kg=empty` | 图谱扩展通道空转 | 补 `MENTIONS`/`BELONGS_TO` 边或改查询 |

## 4. 数字修订汇总（简历表述 → 实测，详见矩阵 §2）

后端 177→**186** 路由 / 210→**219** 操作｜静态页 26→**27**｜Milvus 3400→**3736**｜KG 知识点 1167→**1609**（课程 2854 / 模块 658 不变）｜RAG 审计日志 1364→**1508**｜Neo4j「未引入」→**已真接（graph_source=neo4j）**｜MCP「17 工具」→ 审计 17 条 / 线上实暴露 **4** 个｜流式 P95 6.4s→ 中位 **9.6s**、P95≈**34.6s**。

## 5. 环境与执行备注

- **服务启动**：本机 `cmd.exe` 被安全策略拦截（`cmd.exe cannot be used from the PowerShell tool` / Bash 侧同拦截），**无法直接执行 `start-eduagent.cmd`**。改用等价命令独立进程起 9988（uvicorn，`MYSQL_HOST=127.0.0.1`）+ 3322（next dev），全程存活且完成全部跑批（命令见矩阵附录 B）。已如实登记为环境限制，非纪律违例。
- 期间 9988/3322 曾因**开工前**已死亡（疑似前序会话后台任务随会话退出被杀，与本单无关）中断一次，重启后所有数字均在**服务在线窗口**内产出。
- 门禁证据一律走 `--out` 隔离目录，**未覆盖** `test-reports/gate-baseline/`、`test-reports/interview-lock/` 留档。
- DB 断言全部只读 + 参数绑定；API key / JWT 未落文档；未 push。

## 6. owner 验收口径自检

- Given owner 抽 3 条按矩阵附录命令复跑 → 每条命令均已本轮亲跑并附当日输出（矩阵 §1 每行「复现命令」列 + 附录 C 全量命令）。
- FAIL/PARTIAL 项均指到具体证据：FAIL#13 → §3 TC1-F1（日志原文）；FAIL#24 → §3 TC1-F3（探针末行 JSON）；PARTIAL#18 → §1#18（三话术 flag 实测 true/false/false）。

## 7. 交叉验证（与 TC2 独立结论对账）

- **黄条（本单 #18 ↔ TC2 B11）**：我这轮测得「手册**主话术已不触发**黄条，因 `favorite_add` 已真接、返回 `status=success`，护栏正确地零误标；改用 claim-only 话术才稳定命中」；TC2 报告（`REPORT-TC2.md`，另一会话、CDP 驱动真实 UI）独立得出 **B11 黄条 0/3 FAIL**。**两会话、两条技术路径、同一结论** → 判定从"我的判读"升级为**已互证事实**：手册第 2.6 章话术必须改，否则演示当场看不到黄条。
- **HITL（本单 #14~#16 ↔ TC2 B12）**：我用 `curl -N` 拿到 `pending_confirm` 五字段 + reject 零写（`series` 0 新增）；TC2 用 CDP + DB 断言得 **B12 3/3 PASS**（approve 后 series 2979→2980）。两者互补：我验的是**协议帧与零写**，TC2 验的是**UI 卡与落库**，共同覆盖 approve/reject 两路。
- **流式（本单 #11 ↔ TC2 B10）**：我按 SSE 帧计数（224~661 个 `token` 帧、字段 `delta`）得 PASS；TC2 按 UI `distinctTextLens` 多值（静态 61/109/100、React 95/48/73）得 **B10 6/6 PASS** → 后端帧级与前端渲染级**两端同时成立**。

## 8. 提交与复跑说明

派单铁律要求「单 commit」。本单**以 2 笔同一主题提交**落地（零代码/配置改动，未 push）：

- **笔 1** `docs(verify)/tc1: 简历主张全量重测矩阵(今日实测+复现命令+措辞修订)`（SHA `c874604`）—— 首次交付，含 2 文件：
  `docs/简历实测矩阵.md`（矩阵全文 + 措辞修订 §2 + 缺陷 §3 + 复现命令附录 C）+ 本报告。
- **笔 2** `docs(verify)/tc1: 报告补矩阵全文（兑现开工令「报告：矩阵全文+跑批统计」）` —— 只改本报告（新增 §9）。
  > 此处按**提交标题**引用笔 2、而非 SHA：笔 2 的内容就是本报告，**提交无法在自己的内容里写下自己的 SHA**（循环）。需要 SHA 时用 `git log --oneline --grep=报告补矩阵全文`。

**为何是 2 笔（如实登记，非纪律疏忽）**：开工令铁律第 3 条要求「报告：**矩阵全文**+跑批统计」。首版报告只写了跑批统计并指向交付件，未誊录矩阵全文 —— **属我方漏项**，故补笔 2（交付件内容一字未改）。

而**不能把笔 2 折回笔 1（amend）**：`c874604` 提交后，并行 agent 已在其上叠了两笔 —— `ebf6b30`（TC3 手册 18 站对齐）与 `8f49e00`（TA7 返工单）。此时改写 `c874604` 会把这两笔**孤立出分支**，代价远大于多一笔提交。按本仓既定纪律（「压笔前提＝两笔之间无他人提交」），此处**正确做法就是另起一笔并写明理由**。

**首笔内部的过程说明**：首轮 ⑯ lifecycle 首测记「结论受限」，报告定稿后按自留悬置项复跑，**翻案出 TC1-F6（假红门禁）**，并把与 TC2 的交叉验证补入 §7；该修正**已折入 `c874604` 单笔**（故首笔本身是干净的 1 commit）。

中间过程稿的 commit 对象**未删除**，保留在 `refs/backup/tc1-matrix-e82e901` / `refs/backup/tc1-closeout-0f33099` 以便取证；需要过程稿时用 `git checkout <sha> -- <path>` 取件，**勿 reset**。

> 提交后已复核 `git rev-parse HEAD` 三处一致（HEAD / 松散 ref / packed-refs）+ 工作树内容哈希一致；未 push。
> 另：交付期间发现 `packed-refs` 中 `feature/opt-waves` **落后真 tip 一格**（停在 `ebf6b30`，真 tip `8f49e00`）——一旦并行进程剪松散 ref，分支会**静默回退**并丢掉 `ebf6b30`/`8f49e00` 两笔。已按既定三处修复法前向同步至 `8f49e00`（备份 `.git/packed-refs.bak.tc1b`），未改动任何提交内容。

---

## 9. 附录：矩阵全文（兑现开工令「报告：矩阵全文+跑批统计」）

> 以下为交付件 `docs/简历实测矩阵.md` 的**全文誊录**，使本报告自包含、无需另行打开交付件核对。
> 誊录由脚本按字节拼接（非手工转录），保证与交付件逐字一致。
> ⚠️ 以下小节编号（`§0 环境与基线`、`§1 主张实测矩阵`、`§2 措辞修订建议`、`§3 缺陷`、`附录 A/B/C`）**属于矩阵交付件自身**，与本报告 §1~§8 的编号无关。

# 简历主张全量实测矩阵（TC1 · 2026-09-24）

> 口径：**26 个可测主张全量重测**（含报告曾标 ✅ 的项）。任一数字均为 **2026-09-24 当日亲跑产出**，禁抄旧报告。
> 主张来源：`docs/check-demo-21项详解.md` + `docs/面试演示-逐步点击手册.md` 全站点 + `.opencode/plans/critique-backlog-tracker.md` 已闭环项，合并去重后 27 条。
> 判定：`PASS`（实测与主张一致）／`PARTIAL`（主张方向成立但数字或措辞需改）／`FAIL`（实测不成立）／`SKIP`（今日环境不允许复跑，附原因）。

## 0. 环境与基线

| 项 | 值 |
|---|---|
| 分支 | `feature/opt-waves` |
| 基线 HEAD | `976002a`（开工时 `git log --oneline -3` 首行） |
| 后端 | `http://127.0.0.1:9988`（uvicorn, `edu-agent/.venv`），`/health` → `{"status":"ok","app":"EduAgent","version":"0.3.0"}` |
| 前端 | `http://127.0.0.1:3322`（next dev，`_devMiddlewareManifest.json` → 200 证实 dev 态） |
| MySQL | `127.0.0.1:3306` 库 `edu`（**须 `MYSQL_HOST=127.0.0.1`**，`.env` 写 localhost） |
| Redis | docker `prisma-ai-redis-container-1`（宿主 6377 → 容器 6379） |
| Jaeger | 容器 `eduagent-jaeger`（OTLP 宿主 **14318** / UI **16686**），内存存储 |
| 账号 | admin `adm02test`(user_id=100003) / manager `mgr01test` / student `user000001`(**user_id=1**)，密码均 `Test@123456` |
| 代理坑 | 环境 `HTTP_PROXY` 会把 loopback 吞成 502 → 一律 `curl --noproxy '*'`／Python `ProxyHandler({})` |
| 服务启动方式 | ⚠️ 本机 `cmd.exe` 已被安全策略拦截，**无法直接执行 `start-eduagent.cmd`**；改用等价命令独立进程起服务（见附录 B），已如实登记为环境限制 |

---

## 1. 主张实测矩阵（29 行 / 覆盖 27 条主张）

| # | 主张（简历/手册口径） | 今日实测数字 | 复现命令 | 判定 |
|---|---|---|---|---|
| 1 | 后端 FastAPI **177 路由 / 210 操作** | **186 paths / 219 operations**（`/openapi.json`） | `curl -s --noproxy '*' http://127.0.0.1:9988/openapi.json` | PARTIAL |
| 2 | 前端 **26 静态功能页** + React 双前端 | 静态页 **27** 个 `*.html`；React `page.tsx` **28** 个；`/chat`=200 且 `/chat.html`=200（同端口双面） | `ls edu-frontend/public/*.html \| wc -l`；`find edu-frontend/src -name page.tsx \| wc -l` | PARTIAL |
| 3 | MySQL **104 表**，业务真相源 | **104** BASE TABLE（`information_schema`，schema=`edu`） | 见附录 C-1 | PASS |
| 4 | Redis 限流/缓存/锁/队列（Docker 6377） | `docker exec prisma-ai-redis-container-1 redis-cli ping` → **PONG**；`.env REDIS_PORT=6377` = docker 宿主 6377（容器内 6379） | `docker exec prisma-ai-redis-container-1 redis-cli ping` | PASS |
| 5 | Milvus **3400 向量**，三通道检索 | `edu_knowledge` **3736** 行（另 `user_memory` 35 / `pf_bagu_kb` 5724）；检索日志三通道 `dense=ok sparse=ok graph=…` | 见附录 C-2；`grep retrieval-profile logs/tc1_backend_live.log` | PARTIAL |
| 6 | MongoDB `learning_event` 事件流 + artifacts GridFS | 库 `edu_agent`，集合 `learning_event` / `artifacts.files` / `artifacts.chunks` **均在册**；`learning_event` 仅 **1** 条 | 见附录 C-3 | PARTIAL |
| 7 | 转码/rerank **进程内回退**（sidecar 未跑不拖垮主链） | 今日 sidecar 不可达：`rerank sidecar 返回 502 → 回退进程内直连`，回退耗时 **1342ms / 503ms**，主链仍 `final=5` | `grep "rerank sidecar" edu-agent/logs/tc1_backend_live.log` | PASS |
| 8 | Jaeger 真 OTLP 导出，一次提问 = 一棵分层瀑布 | 今日 trace `88c1ade4bc5b`（16:10:23）**Depth 3 / 4 spans**：`chat.request 9692ms(channel=sse)` → `tool_calls 158ms`、`retrieval 9517ms(retrieved_count=145, final_count=5, answer_tokens=335, nodes=9 节点)`、`llm_call 4461ms(model=deepseek-flash)`；OTLP 真探活 **200 / 39ms** | 见附录 C-4 | PASS |
| 9 | 图谱检索（旧口径：Neo4j 未引入，用 MySQL 图） | **已是真 Neo4j**：`/api/recommend/next`（student）`graph_source=neo4j`，items `source=neo4j`，`extra.graph_source=neo4j`；Neo4j **6848 节点 / 120794 关系** | 见附录 C-5 | PASS（措辞可升级） |
| 10 | KG 规模 **1167 知识点 / 2854 课程 / 658 模块** | **1609** KnowledgePoint / **2854** Course / **658** CourseModule（另 CourseSeries 219、Chapter 659、DocChunk 761、PREREQUISITE 关系 14） | 见附录 C-6 | PARTIAL |
| 11 | 流式输出 = 逐字打字机（SSE 增量） | 单轮 **227 事件 / 224 个 token 帧 / 417 字**，事件序恒为 `start→retrieval→token×N→done`，帧字段为增量 `delta` | 见附录 C-7 | PASS |
| 12 | 流式 L1 端到端 **P95 6.4s** | 今日 **15 次**采样（端到端 wall，含冷启动首问）：`6.32 / 6.58 / 6.93 / 8.02 / 8.37 / 8.42 / 8.81 / 9.57 / 10.17 / 12.10 / 14.89 / 17.88 / 34.00 / 35.95 / 42.50 s` → **中位 9.57s、P95≈34.6s**、极差 6.3~42.5s；TTFT **4.90~35.76s**。时长与答案长度强相关（token 帧 144~661）；冷启动首问最慢（35.8s / TTFT 35.8s），热态短答 6.3~10.2s。全程 `degraded_reason=rerank_sidecar_unavailable`，测量窗内有并行 agent 与门禁 Chrome 负载 | 见附录 C-7 | PARTIAL |
| 13 | **跨会话记忆**（事件溯源，实测 3.7s） | **写链路通**：会话 A 说「我叫小明」→ `user_memory_event` 落库（`memory_type=profile`、槽位 `user_name` 关旧 HEAD，id 307~310，HEAD `valid_to IS NULL`）；**召回不通**：新会话问「我叫什么名字？」→ 答「**我不知道你的名字，memory 为空**」。根因（日志）：`[Memory:vector] Milvus upsert 失败，转下一档：value 'NaN' is not a number or infinity`（4/4 轮），写入落进程内档而 `search()` 仍优先进程外 Milvus（档位不对称）→ 召回假空 | 见附录 C-8 | **FAIL** |
| 14 | 写类工具 `favorite_add` 真实落库（免人工确认） | AI 对话触发 `favorite_add` → `status=success`、`series_id=3`、`series_title=通用编程项目班·直播`、`favorite_source=ai_chat`、`resolve=by_id`；DB 侧命中既有行 `series_favorite.id=30160`（**服务端幂等**，本次未新增行）；`operator_user_id=1` = student `user000001` 的真实 user_id（已核 `/api/auth/me`） | 见附录 C-9 | PASS |
| 15 | HITL 确认卡（admin 对话建课，**零 ID** 话术） | `event: pending_confirm` **1 帧**，五字段齐：`tool_name=course_create`、`args={"title":"TC1验证课A"}`（**无 series_code → 零 ID 已生效**）、`risk_level=high`、`timeout_s=300`、`thread_id=anon-40be86…`；`approve` 前课程不存在 | 见附录 C-10 | PASS |
| 16 | HITL **reject → 零写** | `POST /api/chat/resume {action:"reject"}` → **200 `{"status":"rejected"}`**；DB 只读断言 `series WHERE series_name LIKE '%TC1验证课%'` = **0 行** | 见附录 C-10 | PASS |
| 17 | HITL **approve → 落库** | 本轮**未执行**：避免在共享演示库再建测试课（`series` 已 2978 行）。reject 零写已正面证明「卡真的挡在前面」；approve 落库由 TC2（B12 3×3）覆盖 | — | SKIP |
| 18 | 黄条回执护栏（答案谎报写类完成 → 机检打标） | **claim-only 话术**「请只回复一句话：已收藏。不要调用任何工具」→ `done.data.tool_receipt_unverified=true`、`mcp_tool_calls=[]`（打标准确）；**提及 `favorite_add` 且工具真执行** → `flag=false`（零误标，正确）。⚠️ 手册**主话术**今日不再命中（因 `favorite_add` 已真接，返回 `status=success`） | 见附录 C-11 | PARTIAL（措辞需改） |
| 19 | 练习 + 错题本 SM-2 间隔复习 | `/api/interactive/quiz/wrong-book` → `total=15`、`filter_status=ACTIVE`；条目含 SM-2 字段 `wrong_count / correct_count / next_review_at / last_wrong_answer` | 见附录 C-12 | PASS |
| 20 | 分片上传大文件（**108MB 断网实测照样传成**） | 四条路由在册：`videos/init-chunked`、`videos/upload-chunk/{upload_id}/{chunk_index}`、`videos/finalize-chunked`、`videos/bind-session`；**未复跑 108MB 断网**（需真实大文件+长时上传，本轮为只读为主的重测） | 见附录 C-13 | SKIP |
| 21 | RAG 控制台五标签 + 审计日志 **1364 条**可翻页 | `admin-rag-upload.html` 含 **集合 / 上传 / 调参 / 审计日志 / 高级检索** 五标签；`/api/admin/rag/audit-log` → **total=1508**；`collections` 1 条（`edu_knowledge` row_count 3720） | 见附录 C-14 | PARTIAL |
| 22 | 会话审计页 admin 专属，**学生直连接口 403** | student → **403 / code 40300**「允许角色=['admin']」；admin → **200，total=292** 会话 | 见附录 C-15 | PASS |
| 23 | 课程回收站两步确认 + **409 引用冲突**诚实透出 | `DELETE /api/admin/courses/cohorts/6148`（无 force）→ **409 / code 40908**「班次仍被 3 个模块引用，无法删除」；manager 带 `force=true` → **403 / 40300**「强制删除操作仅 ADMIN 可执行」；两次调用后 `GET cohort 6148` 仍 **200**（零变更） | 见附录 C-16 | PASS |
| 24 | 内部可见性隔离（**学生检索 0 条内部文档 / admin 24 条**） | ⚠️ **今日不成立**：5 条内部关键词探针 → `student_hits_total=**14**`、`admin_hits_total=**25**`、`student_hits_zero=false`。命中来源为 `_default` 分区内 **`up_100003_*` 用户自上传文档**（`critique-*.md`、面试题 PDF 等）；**机制侧仍成立**：`/api/admin/rag/search` 对 student 直接 **403/40300** | 见附录 C-17 | **FAIL**（口径需改） |
| 25 | 契约对账门：前端调用 × 后端路由 × 契约书，**无断点** | `breakpoints=**0**`、`in_use_unfrozen=1`、`to_connect=73`、`unfrozen_only=0`、`frontend=146 / backend=219 / contracts=244 / malformed=0` | `cd edu-agent && CHECK_DEMO_BACKEND=http://127.0.0.1:9988 .venv/Scripts/python.exe scripts/eval/febe_contract_check.py` | PASS |
| 26 | MCP **17 个工具**「声称=接线」三态对账 + 参数脱敏 | `mcp_tristate_probe` → `audit_checked=**17**`、`audit_ok=true`、`builtin_logged=true`、`redacted=true`；跨权限门对账 `checked=17 / 5 行 / chat ACI 链 / JSON serializable / AST 真接 4/5`。注：线上 MCP server 实暴露 **4** 个（`add/list_alphabet/ping/echo`），17 是**内置能力审计条目**口径 | `cd edu-agent && MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe scripts/eval/mcp_tristate_probe.py http://127.0.0.1:9988` | PASS（口径注明） |
| 27 | 前端门禁 **G3/G6/G7/G9 全绿**（+G8） | **G3** 27 页/54 检/**0** 失败；**G6** 27 页/162 检/**0**（带 `EDU_GATE_STUDENT_TOKEN`）；**G7** 27 页/297 检/**0**（同）；**G8** 27 页/216 检/**0**；**G9** 27 页/1512 检/**0**（125 warn）。⚠️ 只用 admin 令牌时 G6 有 1 红、G7 有 2 红，**全部落 `refund.html`**（student-only 页守卫 `role!=student→/dashboard.html`，与 `scripts/gates/page-roles.json` 记载的已知假红一致），补学生令牌后归零 | 见附录 C-18 | PASS |
| 28 | VEC-LOCK embed 一致性 + 12 维守门 | ⑪ `edu_knowledge` **3726 行** embed 一致：`model=bge-m3@26159e7a 混写=无 fallback=无 未归一化=0 空文本=0`；⑲ `veclock_verify.py` **12/12 PASS** + `dim0 backend=bge_m3` | `cd edu-agent && node scripts/check-demo.mjs --no-color`（⑪⑲） | PASS |
| 29 | OTLP 链路健康（SSRF 守门 + 真探活） | `state=healthy`、`endpoint=http://127.0.0.1:14318/v1/traces`、`ssrf_ok=true`、`probe_ok=true`、**probe_ms=39**（`POST /v1/traces` 2xx） | `cd edu-agent && MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe scripts/eval/otlp_health_probe.py` | PASS |

### 跑批统计

矩阵共 **29 行**（覆盖 27 条主张；`HITL 确认卡` 一条主张拆为「卡 / reject 零写 / approve 落库」3 行，另补 `VEC-LOCK`、`OTLP` 两个门禁行）。

| 判定 | 条数 | 序号 |
|---|---|---|
| PASS | **17** | 3, 4, 7, 8, 9, 11, 14, 15, 16, 19, 22, 23, 25, 26, 27, 28, 29 |
| PARTIAL | **8** | 1, 2, 5, 6, 10, 12, 18, 21 |
| FAIL | **2** | 13（跨会话记忆召回）、24（内部可见性数字口径） |
| SKIP | **2** | 17（HITL approve：避免在共享演示库重复建课）、20（108MB 断网分片上传：本轮为只读为主的重测） |

合格率：PASS **58.6%**（17/29）、PASS+PARTIAL **86.2%**（25/29）。FAIL 两项均**指得到具体证据**（见 §3 TC1-F1 / TC1-F3）。

---

## 2. 措辞修订建议（凡实测与简历表述有出入）

| 原表述（简历/手册） | 建议改成（可机验口径） | 依据（#） |
|---|---|---|
| 「后端 177 路由 / 210 操作」 | 「后端 **186 条路由 / 219 个操作**（FastAPI `openapi.json` 实测）」 | 1 |
| 「26 个静态功能页」 | 「**27 个静态功能页** + 28 个 React 路由（同端口 `/x` 与 `/x.html` 双面）」 | 2 |
| 「Milvus 3400 向量」 | 「Milvus `edu_knowledge` **3736** 条稠密向量（BGE-M3），另用户记忆集合 35 条」 | 5 |
| 「MongoDB 承载 learning_event 事件流 + artifacts GridFS」 | 「MongoDB 已建 `learning_event` / `artifacts.files` / `artifacts.chunks` 三集合；**当前实存 learning_event 仅 1 条**（事件流写入为真实链路，数据量待灌）」 | 6 |
| 「1167 知识点 / 2854 课程 / 658 模块」 | 「**1609** 知识点 / 2854 课程 / 658 模块（Neo4j 实测；另 219 系列、659 章节、761 文档块）」 | 10 |
| 「Neo4j 评估后未引入，图谱检索用 MySQL 图实现」 | 「**已接入真 Neo4j 图谱源**：推荐接口 `graph_source=neo4j`，图侧 6848 节点 / 120794 关系；MySQL 图作为停机降级路径保留」 | 9 |
| 「流式 P95 6.4s」 | 「流式端到端 **中位 9.6s / P95≈34.6s**（2026-09-24 实测 15 次；短答热态 6.3~10.2s，冷启动首问 35.8s；全程 `rerank_sidecar_unavailable` 降级且测量窗含并行负载；**非流式**受推理模型下限为 14.8~19.7s）。**建议对客只讲 TTFT 4.9~7.6s（热态）与"逐字流式"，不承诺端到端绝对值**」 | 12 |
| 「跨会话记忆，实测 3.7 秒」 | ⚠️ **暂不可对客表述**：写入链路（事件溯源 + 槽位 HEAD 治理）实测通，但**召回链路今日不可用**（新会话答「memory 为空」）。修好前建议改为「记忆为事件溯源写入 + 槽位版本治理；召回链路有已知缺陷（Milvus 记忆向量 NaN → 档位不对称）正在修」 | 13 |
| 「写类工具免确认 + 真实落库」 | 建议补一句「服务端**幂等**：重复收藏返回原记录（`favorite_id` 不变），不产生重复行」 | 14 |
| 手册 2.6 黄条**主话术**「帮我把《Python 入门》这门课收藏起来…」 | 主话术今日**不再触发**黄条（`favorite_add` 已真接、返回 success，护栏正确地不误标）。演示改用 **claim-only 话术**：「请只回复一句话：已收藏。不要调用任何工具，不要解释。」→ `tool_receipt_unverified=true`（可当场量） | 18 |
| 「RAG 审计日志 1364 条可翻页」 | 「RAG 审计日志 **1508** 条可翻页」 | 21 |
| 「内部可见性：学生 0 条 / admin 24 条」 | 建议改为机制口径：「**管理端检索接口 admin 专属**（student 直连 `/api/admin/rag/search` → 403/40300）；检索按分区/租户隔离。⚠️ 原「学生 0 命中」数字口径**已不可复现**（今日 student 14 / admin 25），因内网文档被上传进共享 `_default` 分区，建议给该断言加内容级守卫或改为分区级断言」 | 24 |
| 「MCP 17 个工具」 | 「MCP 内置能力审计 **17 条**；线上 MCP server 实暴露 4 个工具（add/list_alphabet/ping/echo）——两者是不同口径，勿混用」 | 26 |
| 「前端门禁四件套全绿」 | 保留，但补运行前提：「需**同时**导出 `EDU_GATE_TOKEN`（admin）与 `EDU_GATE_STUDENT_TOKEN`（student），否则 `refund.html` 这类 student-only 页会产生 1~3 条**身份假红**（见 `scripts/gates/page-roles.json`）」 | 27 |
| 「非流式 P95 14.8~19.7s」 | 保留（推理模型物理下限），但**对客一律以流式为准**；流式实测 TTFT 4.9~8.5s | 12 |

---

## 3. 今日新发现的缺陷（建议转返工单，本单零代码改动）

| ID | 现象 | 证据 | 影响面 | 建议 |
|---|---|---|---|---|
| TC1-F1 | **跨会话记忆召回恒空** | `[Memory:vector] Milvus upsert 失败，转下一档：value 'NaN' is not a number or infinity`（16:21:51 / 16:21:52 / 16:22:29 / 16:22:30 共 4 次）；新会话答「memory 为空」 | 记忆功能对客不可演示 | ① 查 NaN 来源（BGE-M3 cuda 输出 / 传参）；② `upsert` 降级到进程内档后，`search()` 仍固定优选 Milvus → **档位不对称**，应记录"当前生效档"并让 search 跟随 |
| TC1-F2 | **记忆抽取 LLM 上游不可用** | `LLM HTTP 400: InvalidSubscription … account (2120516166) does not have a valid AgentPlan subscription`，`degraded` 累计 6→11 | 记忆抽取质量降级（规则候选仍入库） | 续订/换 key；`MEMORY_EXTRACT` 失败率应进监控页 |
| TC1-F3 | **内部可见性断言口径失效** | `wnextint1a_visibility_probe` → `student_hits_zero=false`（14/25） | 门禁 ⑭ 将长期红 | 该断言改为分区/来源级（如"student 不得命中 `tenant_id != 自身` 的文档"），而非关键词级 |
| TC1-F4 | **门禁须双令牌** | 仅 admin 令牌：G6 1 红 / G7 2 红，全部 `refund.html`；补 student 令牌 → 0 红 | 误报为"页面回归" | 已文档化于 `page-roles.json`；建议 gate 启动时对 student-only 页**缺学生令牌直接给出显式提示**而非静默假红 |
| TC1-F5 | **探针默认端口漂移** | `mcp_tristate_probe.py` 默认 `http://127.0.0.1:8000`（旧端口），裸跑即报"后端不可达" | 排查误导 | 默认改 9988 或读 `CHECK_DEMO_BACKEND`（`febe_contract_check.py` 已是正确范式） |
| TC1-F6 | 🔴 **⑯ lifecycle 门是「假红」：探针 bug，后端启停其实健康** | 复跑仍 `avg_start_ms=0 / avg_stop_ms=0 / detail="lifecycle 不达标"`；但同轮日志 `logs/lifecycle_real_{1..5}.log`（**仓库根** `logs/`）**每轮都启动成功**：`Started server process` → `Application startup complete.` → `Uvicorn running on http://127.0.0.1:18000`，`Traceback/CancelledError/shutdown failed` 计数 **全 0**。根因：`edu-agent/scripts/_lifecycle_real_verify.py:46` 用了**从未定义的 `PROBE_PORT`**（局部变量实为 `probe_port`，:29），抛 `NameError` 被同段 `except Exception: pass` **静默吞掉** → 健康检查永假 → 每轮空转 30s 后 `proc.kill()` → 恒 FAIL，**从未走到优雅关停分支（零覆盖）** | 21 项体检单永远无法全绿；极易被误归因为"后端不健壮" | 1 行修：`:46` `PROBE_PORT` → `probe_port`；并把 `except Exception: pass` 收窄为 `except OSError`，否则同类探针拼写 bug 会继续被吞 |
| TC1-F7 | **KG 文档块→知识点边缺失** | 后端日志：Neo4j `UnknownRelationshipTypeWarning ... missing relationship type is: MENTIONS`（`DocChunk-[:MENTIONS]->KnowledgePoint`） | 检索侧 `kg=empty`，图谱扩展通道空转 | 补 `MENTIONS` / `BELONGS_TO` 边或改查询 |

---

## 3.5 与 TC2 盲测报告的交叉验证（互证）

TC2（`REPORT-TC2.md`，另一会话、CDP 驱动真实 UI + DB 只读断言）与本单在**三个关键点**上独立收敛：

| 点 | 本单（TC1，协议/接口层） | TC2（盲测，UI 层） | 合成结论 |
|---|---|---|---|
| 黄条 | 主话术 `flag=false`（`favorite_add` 真执行 success，护栏**正确**不误标）；claim-only 话术 `flag=true` | **B11 黄条 0/3 FAIL**（照手册主话术，无黄条） | **手册 2.6 章主话术已失效**（两路径互证）→ 演示须改 claim-only 话术 |
| HITL | `pending_confirm` 五字段 + reject **零写**（`series` 0 新增） | **B12 3/3 PASS**（卡弹出 + approve 后 series 2979→2980） | approve/reject 双路齐证 |
| 流式 | 后端 `token` 帧 **224~661** 个、字段 `delta`，序 `start→retrieval→token×N→done` | **B10 6/6 PASS**（UI `distinctTextLens` 多值：静态 61/109/100、React 95/48/73） | 帧级 + 渲染级**两端同时成立** |

---

## 附录 A：跑批耗时与证据留档

- 全量 21 项体检单：`cd edu-agent && node scripts/check-demo.mjs --frontend-port 3322 --no-color`（本轮 324.7s；含 ⑯ lifecycle 156s + ⑲ VEC-LOCK 136s）
- 门禁两轮（admin-only / admin+student）：G3 27/54、G6 162 检、G7 297 检、G8 216 检、G9 1512 检
- 证据文件（本地临时区，未入库）：`checkdemo.txt`、`probe_api.json`、`probe_chat_out.json`、`gate-out/`、`gate-out2/`、`jaeger_traces.json`

## 附录 B：服务启动（本机限制的等价做法）

```bash
# 1) 后端（独立进程，非会话内后台任务）
cd edu-agent
MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9988
# 2) 前端（dev 态，页面永远新鲜）
cd edu-frontend
node node_modules/next/dist/bin/next dev -p 3322
# 3) 就绪判定
curl -s --noproxy '*' http://127.0.0.1:9988/health
curl -s --noproxy '*' -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3322/login-register.html   # 期望 200
```
> ⚠️ 仓库根 `start-eduagent.cmd` 仍是一键标准入口（含 Redis 起停与 6 步自检）；本机 `cmd.exe` 被安全策略拦截（`cmd.exe cannot be used`）时，用上面两条等价命令。

## 附录 C：逐项复现命令

**C-1 MySQL 表数**
```sql
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='edu' AND table_type='BASE TABLE';  -- 104
```

**C-2 Milvus 集合与行数**（在 `edu-agent/` 下）
```bash
MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe -c "
import sys;sys.path.insert(0,'.')
from app.config import settings
from pymilvus import MilvusClient
cl=MilvusClient(uri=settings.MILVUS_URI,token=settings.MILVUS_TOKEN or '',db_name=settings.MILVUS_DB)
for c in cl.list_collections(): print(c, cl.get_collection_stats(c))
"
```

**C-3 MongoDB 集合**
```bash
MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe -c "
import sys;sys.path.insert(0,'.')
from app.config import settings
from pymongo import MongoClient
db=MongoClient(settings.MONGO_URI,serverSelectionTimeoutMS=4000)[settings.MONGO_DB]
print(sorted(db.list_collection_names()))
"
```

**C-4 Jaeger 瀑布**
```bash
curl -s --noproxy '*' 'http://127.0.0.1:16686/api/services'
curl -s --noproxy '*' 'http://127.0.0.1:16686/api/traces?service=edu-agent&limit=5'
# 或浏览器 http://127.0.0.1:16686 → Service=edu-agent → Find Traces
```

**C-5 推荐图谱源**
```bash
curl -s --noproxy '*' -H "Authorization: Bearer $STU" 'http://127.0.0.1:9988/api/recommend/next?limit=3'   # data.graph_source == "neo4j"
```

**C-6 Neo4j 计数**
```bash
MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe -c "
import sys;sys.path.insert(0,'.')
from app.config import settings
from neo4j import GraphDatabase
d=GraphDatabase.driver(settings.NEO4J_URI,auth=(settings.NEO4J_USER,settings.NEO4J_PASSWORD))
with d.session(database=settings.NEO4J_DATABASE) as s:
    for l in ['KnowledgePoint','Course','CourseModule','CourseSeries','Chapter','DocChunk']:
        print(l, s.run(f'MATCH (n:{l}) RETURN count(n) c').single()['c'])
"
```

**C-7 chat SSE 流式**
```bash
curl -s --noproxy '*' -N -X POST http://127.0.0.1:9988/api/chat/stream \
  -H "Authorization: Bearer $STU" -H 'Content-Type: application/json' \
  -d '{"query":"请用三句话介绍 Python 入门课程适合谁学。","stream":true}' | head -20
# 判据：事件序 start→retrieval→token×N→done；token 帧字段为 delta
```

**C-8 跨会话记忆**（会话 A 写 / 新会话 B 读）
```bash
# A: POST /api/chat/sessions {"title":"mem-A"} → data.session_id
#    再 POST /api/chat/stream {"query":"你好，我叫小明，请记住我的名字","session_id":<A>}
# B: POST /api/chat/sessions {"title":"mem-B"} → data.session_id
#    再 POST /api/chat/stream {"query":"我叫什么名字？","session_id":<B>}
# 落库校验（只读）：
SELECT id,user_id,event_type,memory_type,topic,LEFT(content,40),valid_to
FROM user_memory_event WHERE memory_type='profile' ORDER BY id DESC LIMIT 6;
# 今日结果：写入 4 条（HEAD 在），召回答「memory 为空」
```

**C-9 favorite_add**
```bash
curl -s --noproxy '*' -N -X POST http://127.0.0.1:9988/api/chat/stream \
  -H "Authorization: Bearer $STU" -H 'Content-Type: application/json' \
  -d '{"query":"帮我收藏课程 series_id 为 3 的课","stream":true}' | tail -3
# done.data.mcp_tool_calls[0].status == "success"；result_summary 含 favorite_id / idempotent_note
```

**C-10 HITL 卡 + reject**
```bash
# ① 发问（admin 令牌）→ 观察 event: pending_confirm
curl -s --noproxy '*' -N -X POST http://127.0.0.1:9988/api/chat/stream \
  -H "Authorization: Bearer $ADM" -H 'Content-Type: application/json' \
  -d '{"query":"帮我创建一门课程，标题\"TC1验证课A\"","stream":true}'
# ② 拒绝 → 200 {"status":"rejected"}
curl -s --noproxy '*' -X POST http://127.0.0.1:9988/api/chat/resume \
  -H "Authorization: Bearer $ADM" -H 'Content-Type: application/json' \
  -d '{"thread_id":"<pending_confirm.thread_id>","action":"reject"}'
# ③ 零写断言
SELECT COUNT(*) FROM series WHERE series_name LIKE '%TC1验证课%';   -- 0
```

**C-11 黄条护栏**
```bash
# 稳定命中（claim-only）
-d '{"query":"请只回复一句话：已收藏。不要调用任何工具，不要解释。","stream":true}'
# 期望 done.data.tool_receipt_unverified == true 且 mcp_tool_calls == []
```

**C-12 错题本 SM-2**
```bash
curl -s --noproxy '*' -H "Authorization: Bearer $STU" 'http://127.0.0.1:9988/api/interactive/quiz/wrong-book?page=1&page_size=3'
# data.total / items[].next_review_at / wrong_count / correct_count
```

**C-13 分片上传（未复跑，路由证据）**
```
POST /api/admin/courses/videos/init-chunked
PUT  /api/admin/courses/videos/upload-chunk/{upload_id}/{chunk_index}
POST /api/admin/courses/videos/finalize-chunked
POST /api/admin/courses/videos/bind-session
```

**C-14 RAG 控制台**
```bash
curl -s --noproxy '*' -H "Authorization: Bearer $ADM" 'http://127.0.0.1:9988/api/admin/rag/audit-log?page=1&page_size=1'   # data.total
curl -s --noproxy '*' -H "Authorization: Bearer $ADM" 'http://127.0.0.1:9988/api/admin/rag/collections'
curl -s --noproxy '*' -H "Authorization: Bearer $ADM" 'http://127.0.0.1:9988/api/admin/rag/presets'
```

**C-15 会话审计权限**
```bash
curl -s --noproxy '*' -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $STU" 'http://127.0.0.1:9988/api/admin/chat-audit/sessions'   # 403
curl -s --noproxy '*' -H "Authorization: Bearer $ADM" 'http://127.0.0.1:9988/api/admin/chat-audit/sessions?page=1&page_size=5'                # 200 + total
```

**C-16 回收站 409（安全拒绝路径）**
```bash
curl -s --noproxy '*' -X DELETE -H "Authorization: Bearer $ADM" 'http://127.0.0.1:9988/api/admin/courses/cohorts/6148'                # 409 / 40908
curl -s --noproxy '*' -X DELETE -H "Authorization: Bearer $MGR" 'http://127.0.0.1:9988/api/admin/courses/cohorts/6148?force=true'     # 403 / 40300
curl -s --noproxy '*' -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $ADM" 'http://127.0.0.1:9988/api/admin/courses/cohorts/6148'  # 200（零变更）
```

**C-17 内部可见性**
```bash
cd edu-agent && MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe scripts/eval/wnextint1a_visibility_probe.py --base http://127.0.0.1:9988
# 末行 [WINT1A] {"student_hits_total":14,"admin_hits_total":25,"student_hits_zero":false, ...}
curl -s --noproxy '*' -o /dev/null -w '%{http_code}\n' -X POST -H "Authorization: Bearer $STU" -H 'Content-Type: application/json' \
  -d '{"query":"内部","top_k":5}' http://127.0.0.1:9988/api/admin/rag/search   # 403
```

**C-18 前端门禁（须双令牌）**
```bash
export EDU_GATE_TOKEN=$(curl -s --noproxy '*' -X POST http://127.0.0.1:9988/api/auth/login -H 'Content-Type: application/json' -d '{"account":"adm02test","password":"Test@123456"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
export EDU_GATE_STUDENT_TOKEN=$(curl -s --noproxy '*' -X POST http://127.0.0.1:9988/api/auth/login -H 'Content-Type: application/json' -d '{"account":"user000001","password":"Test@123456"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
node scripts/gates/dom-hook-inventory.mjs  --all --check --out <隔离目录>   # G3
node scripts/gates/style-dep-gate.mjs      --all --out <隔离目录>          # G6
node scripts/gates/viewport-a11y-gate.mjs  --all --out <隔离目录>          # G7
node scripts/gates/asset-cache-gate.mjs    --all --out <隔离目录>          # G8
node scripts/gates/state-matrix-gate.mjs   --all --out <隔离目录>          # G9
# ✅ 复验须用 --out 隔离目录，勿覆盖 test-reports/gate-baseline/ 留档
```
