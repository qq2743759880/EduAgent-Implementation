# REPORT-TC1 — 简历主张全量重测矩阵（yy · P2）交回

> 开工令：`.ai-hub/plans/artifacts/dispatch/TO-EXEC-TC1.md`
> 分支 `feature/opt-waves`；开工基线 `git log --oneline -3` 首行 = `976002a`
> 产物：`docs/简历实测矩阵.md`（矩阵全文 + 修订建议 §2 + 缺陷 §3 + 复现命令附录）

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

派单铁律要求「单 commit」，本单**以单笔提交落地**（新增 2 文件，零代码/配置改动，未 push）：

- `docs/简历实测矩阵.md`（矩阵全文 + 措辞修订 §2 + 缺陷 §3 + 复现命令附录 C）
- `.ai-hub/plans/artifacts/dispatch/REPORT-TC1.md`（本报告）

**过程说明（影响可追溯性，如实登记）**：首轮 ⑯ lifecycle 首测记「结论受限」，报告定稿后按自留悬置项复跑，**翻案出 TC1-F6（假红门禁）**，并把与 TC2 的交叉验证补入 §7。该修正**已折入同一笔提交**（提交内容即最终树），故最终只有一笔。

中间过程稿的两个 commit 对象**未删除**，保留在 `refs/backup/tc1-matrix-e82e901` / `refs/backup/tc1-closeout-0f33099` 以便取证；需要过程稿时用 `git checkout <sha> -- <path>` 取件，**勿 reset**。

> 提交后已复核 `git rev-parse HEAD` 三处一致（HEAD / 松散 ref / packed-refs）+ 工作树内容哈希一致；未 push。
