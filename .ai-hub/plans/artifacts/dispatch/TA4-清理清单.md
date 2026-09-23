# TA4 · 遗留测试数据清理清单（阶段 A 盘点产物 · 待 owner 批准）

- 任务：TO-EXEC-TA4（yy 十点修复 · P0）
- 分支：`feature/opt-waves`（`cat .git/HEAD` = `ref: refs/heads/feature/opt-waves`，松散 ref 存在）
- 扫描完成时间：**2026-09-24 01:16:55 +0800**
- 当前状态：**阶段 B 硬停止点 — 未执行任何删除/软删，等待 owner 过目批准**
- 扫描性质：**全程只读**（SQL 仅 SELECT；Milvus 仅 list/describe/query；Redis 仅 SCAN/TYPE/TTL/MEMORY；Mongo 仅 find）

---

## 0. 一句话结论

真正的"演示面污染"集中在 **MySQL 侧 5 张表**（RAG 预设 9/12 是测试件、知识导入任务 127 条 `knowledge_import_demo.md` 探针、题库 11 个 T13 验证库、题目 19 条、MCP 调用日志 441 条）。
Milvus 里**没有**可判定的 EduAgent 测试 collection（`pf_bagu_kb` 是别人的，禁碰）；Redis/Mongo 只有 **5 个明确探针 key + 89 个 eval/探针文档**。
另有若干项**建议保留**，理由见 §3（多数是"有 TTL 会自动过期"或"删了会踢人/空页"）。

---

## 1. MySQL（`127.0.0.1:3306`，库 `edu`，共 104 表）

### 1.1 建议软删（表本身有 `yn` 列，与项目既有软删口径一致）

| # | 位置 | 判定为测试残留的依据 | 行数 | 建议处置 | 软删后对演示功能的影响 |
|---|---|---|---|---|---|
| A1 | `edu.rag_param_preset` id ∈ {4,10,13,43,85,86,87,88,89} | 命名命中「调试自定义预设-t<unix 时间戳>」（4/13/43/85/86/87/88）、`tester_default_probe`(10)、`ITest预设`(89，created_by=100003)；与 3 个种子预设（1 平衡-default / 2 高质量-recall / 3 低延迟-speed，`created_by=1`、2026-08-09 09:17 同时入库）形成明显对照 | **9**（表内 yn=1 共 12） | 软删 `yn=0` | **正面**：RAG 调优控制台预设下拉从 12 → 3，`/api/admin/rag/presets` 只剩真实三档。无负面（9 条全非 `is_default`；`rag_audit_log.param_preset_id` 引用面待执行前复核，若命中则改为保留该条） |
| A2 | `edu.question_bank` id ∈ {439…449} | `bank_code` 命中 `T13-VERIFY-BANK` / `T13-VRF-*` / `t13_bank_1|2`，`bank_name` = 「验证题库」「验收题库」「验收题库2」；`institution_id` 全 =1，创建于 2026-08-19 22:45 ~ 08-20 09:35（T13 接线验收窗口）。与 84 个种子库（`*_bank` 命名、分散 6 个 institution）命名体系完全不同 | **11**（yn=1 共 449） | 软删 `yn=0` | **正面**：管理端题库列表/admin-questions.html 少 11 个"验证题库"。⚠️ 其中 6 个库被 6 个 T13 验证考试引用（见 A5），需与 A5 同批处置；未同批会留下"考试引用已删题"悬空 |
| A3 | `edu.question` id ∈ {10513…10528}（16 条，在 A2 的库下）+ {10537,10538,10539}（3 条，在 yn=0 库 452/453 下） | `question_code` = `T13-Q001`(×8) / `T13-BATCH-001` / `T13-BTCH-001` / `q1`；`stem` = 「验证题目：1+1=?」「批量题1」「1+1等于几？」「导入·单选：1+1=?」「UI import single: 2+2=?」；创建于 2026-08-19~20 / 2026-09-15 联调窗口 | **19**（yn=1 共 10531） | 软删 `yn=0` | **正面**：题目列表/搜题页不再出现"1+1=?"这类验收占位题。⚠️ 其中 6 条被 `session_exam_question_rel` 引用（154441~154446，全部来自 T13 验证考试），需与 A5 同批；作业/错题本/答题会话引用均为 0（已实测） |
| A4 | `edu.mcp_server` id=2（`sse-demo-localhost`） | `display_name` = 「SSE 演示站（占位）」，`base_url` = `http://127.0.0.1:9527/sse`（未部署），`enabled=0`，`last_health_ok=0`，`last_error` = 「httpx fail: All connection attempts failed」；描述原文自述"占位……实际部署时把 base_url 指向运行中的 SSE MCP 服务" | **1**（yn=1 共 2） | 软删 `yn=0`（连带 `mcp_tool.yn=0`） | **中性偏正面**：MCP 管理页 server 列表 2 → 1（只剩真实可跑的 `stdio-echodemo`）。⚠️ 若演示要讲"SSE transport 形态"，此行是唯一 SSE 样例 → **需 owner 拍板**（可改为保留） |
| A5 | `edu.mcp_tool` id=5（`sse_health`，server_id=2） | 随 A4；且 `registry.get_tool_by_ref` 只认 `S.enabled=1` 上的工具，该 server enabled=0 → **实际不可用却仍列在工具表**，是"无效数据"典型 | **1**（yn=1 共 5） | 随 A4 软删 | 同上；工具列表 5 → 4，与实际可用工具集（ping/add/echo/list_alphabet）完全对齐 |

### 1.2 建议硬删（表**无 `yn` 列**，软删不可行 → 需 owner 逐项明示同意）

| # | 位置 | 判定依据 | 行数 | 建议处置 | 影响评估 |
|---|---|---|---|---|---|
| A6 | `edu.knowledge_import_task` — `agent_import` 全量 | 127 条中 126 条 `status=pending`、1 条 succeeded，**全部** `source_files` = `knowledge_import_demo.md`（`file_size=0` 的假文件），任务号 `task_1789*_<rand>`；时间窗 2026-09-17 00:25 ~ 2026-09-22 19:45（连续 6 天的重复探针，非真实导入）。这是 RAG 控制台"导入任务"列表最主要的污染源 | **127** | 硬删（无 yn） | **正面**：`/api/knowledge/tasks` 263 → 136。无功能依赖（pending 任务本就不会被消费；succeeded 那条导入的是 0 字节假文件） |
| A7 | `edu.knowledge_import_task` — 5 条 `user_upload` 测试件 | 文件名：乱码「ÖªÊ¶¿â²âÊÔ.md」(=知识库测试.md)、`t10_same.md`、`test_s4.md`×2、`ib_g2_WNI1BG2_1789562680.md` | **5** | 硬删（无 yn） | **中性**：这 5 条是"succeeded"，其 chunk 已进 Milvus `edu_knowledge`（对应 `up_*` 来源，约 30 chunk）。**若只删任务行不删向量，会出现"任务没了但知识还在"** → 建议与 B1 的 doc_chunk 清理同批，否则本项建议保留 |
| A8 | `edu.knowledge_import_task` — 7 条 `failed` system_init | 全部失败于探针文件：`t.docx`(File is not a zip)、`t.pdf`/`知识库测试.pdf`(No module named 'pdfplumber')、`wnextminio1_same_*.md` 读取失败 | **7** | 硬删（无 yn） | **正面**：失败红条不再占屏。无依赖 |
| A9 | `edu.session_exam` id ∈ {15445…15450} + `session_exam_question_rel` id ∈ {154441…154446} | `exam_code` = `T13-EXAM-001`/`T13-EXM-155427`/`155751`/`189213`/`189591`/`189807`，`exam_name` 全为「验证考试」；**`session_id` 全是 1**（真实考试挂在 session 7038/14614/… 等 6 位数班次上，一眼可分）；created_by=1，2026-08-19~20 与 A2/A3 同窗口 | **6 + 6** | 硬删（**`session_exam` 无 yn 列**） | **正面**：清掉 T13 遗留考试。⚠️ 4 条是 `publish_status=published`，但因 `session_id=1` 不属于任何真实班次，学生端取不到。需与 A2/A3 同批，否则互为悬空 |
| A10 | `edu.mcp_tool_call_log` | ① 150 条调用的是**从未注册**的伪工具（`knowledge_import` 127、`favorite_add` 22、`course_create` 1，`server_id=0`）；② 一批日志挂在已软删 server（19/21/23/33）上；③ 时间集中在 2026-09-05~09-22 的盲测窗口，user 集中在 1/100003 | **441** | 硬删（无 yn） | **正面**：MCP 管理页调用日志从 441 条测试噪声变成干净（或空）列表。⚠️ 该表是"工具调用审计"，全删会连真实调用一起清掉 → **建议 owner 二选一：全删 / 只删 `server_id=0` 的 150 条伪工具 + 已软删 server 的孤儿行** |
| A11 | `edu.mcp_tool_description_review_log` | 24 条**全部** `operator_user_id=100003`，`server_id` ∈ {19,21,23,33} —— 这 4 个 server 当前 `yn=0`（T14 已软删）→ 全是孤儿日志 | **24** | 硬删（无 yn） | **正面**：描述复核日志页不再全是孤儿。无依赖 |

### 1.3 建议**保留**（列出即说明已扫过，非遗漏）

| # | 位置 | 行数 | 保留理由 |
|---|---|---|---|
| A12 | `edu.rag_audit_log` | 1436→持续增长（扫描中新增 1 条） | 调参审计留痕，owner 未授权按时间窗清理；且真实用户查询（user 1/894/1017/830…）与测试查询混在同一表，无法用命名模式安全切分。**如需清，请 owner 指定时间窗或 user_id 白名单** |
| A13 | `edu.rag_collection_meta` id=1 `knowledge_chunk_v1` | 1（row_count 字段=4413） | **幽灵集合**：Milvus `default` 库里没有这个 collection（只有 `edu_knowledge`/`pf_bagu_kb`/`user_memory`）。但 `app/admin/rag_admin/service.py:243-266` 已有 F-10② 读侧过滤（Milvus 可达时自动隐藏幽灵集合）→ **前端已经看不见了**，删元数据反而有风险。建议保留 |
| A14 | `edu.rag_collection_meta` id=4 `edu_knowledge` | 1 | **生产在用**（`app/config.py:97 MILVUS_COLLECTION = "edu_knowledge"`）。禁碰 |
| A15 | `edu.mcp_server` id=1 `stdio-echodemo` | 1 | **演示必需**：唯一 `enabled=1` 且 `last_health_ok=1` 的 server，提供 ping/add/echo/list_alphabet 四个真实可跑工具 |
| A16 | `edu.mcp_tool` id 1-4 | 4 | 同上，A15 的真实工具 |
| A17 | `edu._rwtest` | 3 行 `{1,'a'}{2,'b'}{3,'new'}` | 读写连通性自测表。铁律 **禁 DROP TABLE** → 只登记不处理。如需清请 owner 单独授权（且只能 DELETE 行） |
| A18 | `edu.question` 空 `options_json` 4213 条 | 4213 | **误判排除**：按 `question_type_id` 拆分全是简答题(1692)/计算题(732)/编程题(450)/案例分析(438)/情境分析(372)/证明题(144)/公式推导(144)/数据分析(102)/翻译(84)/材料分析(48) —— **非选择题本就无选项**，不是脏数据 |
| A19 | `edu.question_bank` 449 行中"同 `bank_code` 出现 6 次" | 约 365 | **误判排除**：`(bank_code, bank_name, institution_id)` 三元组查重 = **0 组重复**；重复是"同一题库模板按 6 个 institution 各存一份"的种子设计，不是重跑插入的幽灵数据 |

---

## 2. Milvus（`192.168.85.101:19530`，db=`default`，仅 1 个 db）

| # | Collection | 行数 | 判定 | 建议 |
|---|---|---|---|---|
| B1 | `edu_knowledge` | **3435**（实测扫描 3425，stats 3435） | **生产在用**（`MILVUS_COLLECTION` 常量指向它；embedding 均为 `bge-m3@26159e7a`，dim=1024）。构成：question 1751 + course_module 657 + course_intro 219（**种子，必留**）+ **doc_chunk 798**（117 个 `.md`，其中 `internal=True` 745、`internal=False` 53；含 17 个 `up_100003_*` / `up_1_*` 上传件，内容多为 task01/task02/task03 DDL 脚本、验收批判、frontend-framework-critique 等内部过程文档） | **禁 reset collection**。doc_chunk 是否清、清哪些 → 需 owner 定夺：留 = 检索仍能召回过程文档；删 = 检索更"干净"但会丢失唯一的知识库演示语料。**建议本轮不动**（风险/收益不对称），除非 owner 明确要"RAG 检索只留课程+题目" |
| B2 | `pf_bagu_kb` | 5724 | **不是本项目的数据**：schema 完全不同（`role`/`source`/`heading_path`/`seq`/`text`/`dense`，auto_id，无 tenant/visibility），`source` = `ai-agent/大厂AI-Agent面试题大全-2025-2026.pdf`；全仓 `grep -rn "pf_bagu" app/` **零命中** | **禁碰**（与 prisma-ai 共享实例，非我方资产） |
| B3 | `user_memory` | 35 | 内容 `mem-0`/`mem-1`…高度疑似测试，但**铁律明令禁碰 user_memory / user_memory_event** | **禁碰** |

> 补充：Milvus 里**没有**任何 test/demo 命名的 collection，也没有 `knowledge_chunk_v1`（对应 A13 幽灵）。

---

## 3. Redis（`docker exec prisma-ai-redis-container-1`，db0，与 prisma-ai 共享）

`DBSIZE` = 2442（扫描瞬时 2456，含 TTL 抖动）。**本项目自有前缀**已用源码反查确认：`edu:ckpt:`(`app/ai/checkpoint_redis.py:77`)、`rt:{uid}:{jti}`(`app/auth/service.py:229`)、`breaker:`(`app/core/breaker.py:99`)、`rl:ip`/`rl:uid`(`app/middleware/rate_limit.py:191-193`)、`g-rank:`(`app/gamification/service.py:321`)、`ai:llm:*`/`chat:user_token:*`(`app/config.py:320-337`)、`memory:vec*`(`app/config.py:603`)。

| # | Key 前缀 | 数量 | 判定依据 | 建议 |
|---|---|---|---|---|
| C1 | `task26_bigkey_probe` | **1** | 单 key，string，**TTL=-1（永不过期）**，占 **1.31 MB**（`MEMORY USAGE`=1310758）——task26 大 key 探针留下的垃圾，无任何代码引用 | **硬删**（本项目、可 100% 重建、不踢人） |
| C2 | `breaker:test` | **1** | hash，TTL=-1；其余 `breaker:*` 都是真依赖名（`neo4j`/`redis`/`mongo_learning_event`/`mcp-server-1`/`mcp-server-19`/`concurrent`），只有 `test` 是探针名 | **硬删**（熔断状态瞬时可重建） |
| C3 | `edu:ckpt:r20b-*` | **131** | `r20b` = R20 盲测批次命名（`r20b-1789748145735-285a0f8e` 形态，与 `s_*` 真实会话 / `anon-*` 匿名会话 / `hitl-*` 人机协同 三类可清晰切分）；TTL 约 169306s ≈ 2 天 | **硬删**（盲测 checkpoint，丢失只影响无人访问的测试会话续跑）。其余 444 个 `edu:ckpt`（s 161 / anon 179 / hitl 42 / 其他 62）**保留** |
| C4 | `rt:{uid}:{jti}` | **1845** | 刷新令牌（user 100003:1217、1:552、100005:29、915001/915002:20×2…），TTL 剩余 38k~217k 秒，会自然过期 | **建议保留**：① 不出现在任何演示页；② 删了会把当前登录态全部踢下线（含 owner 自己的 admin 会话），收益≈0、风险>0。若 owner 坚持清，需先确认演示账号重新登录可接受 |
| C5 | `rl:*` (9) / `g-rank:*` (6) / `ai:llm:*` (2) / `chat:*` (2) / `breaker:*` 其余 (6) / `edu:ckpt` 其余 (444) | 469 | 限流窗口、排行榜 ZSET、并发计数、熔断状态、真实会话 checkpoint —— 全是运行时状态 | **保留** |
| C6 | `memory:vec*` | 9 | 铁律禁碰 user_memory 体系 | **禁碰** |

---

## 4. MongoDB（`192.168.85.101:27017`，db=`edu_agent`，3 个集合）

| # | 集合 | 数量 | 判定依据 | 建议 |
|---|---|---|---|---|
| D1 | `artifacts.files` | **41** | 全部是 eval/探针产物：`eval/r20b/dualrun_results.json` **×10**（同一文件 10 次递增快照，19KB→236KB，是重跑没清理）、`eval/r22_runs/*.json` ×25、`eval/runs/*.json` ×4、`orchestrator-verify-probe.json`(57B) 与 `orchestrator-verify-probe2.bin`(40B) 两个纯探针 | **硬删候选**（GridFS 必须 files+chunks 成对删）。⚠️ 这些是历史评测留证件——**删除后不可恢复**（除本单备份外）。请 owner 确认"评测留证价值"是否低于"演示面整洁" |
| D2 | `artifacts.chunks` | **48** | D1 的 GridFS chunk 伴生数据 | 随 D1 |
| D3 | `learning_event` | **20** | 全是探针事件：user=1 在 2026-09-18 23:21 的 **3 秒内灌了 6 条** `video_heartbeat`+`quiz_submit`（`custom_code` 恒为 `Q-EN-SINGLE-THE`）；user=100132 刷题探针 5 条；3 条 `session_complete` 且 `completed:False` | **硬删**（无真实学习行为语义）。注意：`breaker:mongo_learning_event` 熔断状态不受影响 |
| D4 | 库 `edu_agent_rm1_test`（`learning_event` 0 条） | 0 | 空测试库，命名自带 `_test` | 铁律 **禁 DROP DATABASE** → 只登记，不处理 |

---

## 5. 处置汇总（供 owner 勾选）

| 批次 | 项 | 规模 | 三核闸要求 |
|---|---|---|---|
| **批 1（软删·MySQL）** | A1 预设 9 / A2 题库 11 / A3 题目 19 / A4+A5 MCP server+tool 各 1 | 41 行 | mysqldump 单表备份 → `UPDATE ... SET yn=0` → 行数核对 → 重跑幂等 |
| **批 2（硬删·MySQL，需明示）** | A6 导入任务 127 / A7 user_upload 5 / A8 failed 7 / A9 考试 6+6 / A10 调用日志 441（或只删子集）/ A11 复核日志 24 | 610~616 行 | 同上 + 逐行 DELETE（参数绑定），**禁 TRUNCATE** |
| **批 3（硬删·Redis，需明示）** | C1 1 key / C2 1 key / C3 131 keys | 133 keys | `redis-cli --scan` 导出 RDB 片段 + key 清单落盘 → `UNLINK`（非 FLUSHDB）→ DBSIZE 核对 → 幂等复跑 |
| **批 4（硬删·Mongo，需明示）** | D1+D2 41 files/48 chunks / D3 20 docs | 109 docs | `mongodump` 导出 → delete_many → 计数核对 → 幂等复跑 |
| **保留** | A12~A19 / B1~B3 / C4~C6 / D4 | — | 不触碰 |

---

## 6. 禁碰确认（已逐条遵守）

- ✅ `session_asset` / `session_video` 占位域：**本单零触碰**（owner 未解冻）
- ✅ 生产业务数据（order/payment/series/sys_user 等）：**零触碰**
- ✅ `user_memory_event` / `user_memory`（MySQL + Milvus `user_memory` + Redis `memory:vec*`）：**零触碰**
- ✅ 代码文件：**零改动**（本单无代码变更）
- ✅ 无 `DROP TABLE` / 无 `TRUNCATE` / 无 Milvus collection reset / 无 `FLUSHDB`
- ✅ Redis 全程 `docker -c desktop-linux exec prisma-ai-redis-container-1` 前缀，只列本项目前缀，未动 `pf_bagu_kb` 等非我方资产

---

## 7. 证据文件（阶段 A 只读产物，已落盘）

| 路径 | 内容 |
|---|---|
| `deploy/backups/ta4/redis-keys-scan-20260924.txt` | Redis db0 全量 2456 key 快照（97.9 KB） |
| `deploy/backups/ta4/edu_knowledge_docchunk_sources.txt` | Milvus `edu_knowledge` 798 条 doc_chunk 按 (source_file, internal) 分组（122 组） |

阶段 C 执行时，备份将统一落 `deploy/backups/ta4/batch<N>-<时间戳>/` 并在 `REPORT-TA4.md` 登记路径 + 字节数。

---

## 8. 待 owner 拍板的 4 个决策点

1. **A4/A5（MCP SSE 占位 server + `sse_health`）** —— 删则 MCP 页只剩 1 server/4 tool（干净）；留则保住唯一 SSE 形态样例。**owner 是否还要讲 SSE transport？**
2. **A10（MCP 调用日志 441）** —— 全删 / 只删伪工具 150 条 + 孤儿行 / 全留？
3. **A7 + B1（user_upload 任务行与其在 Milvus 的 chunk）** —— 只删任务行会不一致；这决定 RAG 检索是否保留"过程文档"语料。
4. **D1（Mongo 41 个 eval 产物）** —— 它们是历史评测留证件，删了只靠本单备份可恢复。**是否接受？**

---

**⛔ 阶段 C 未启动。以上清单未经 owner 书面批准前，不执行任何 DELETE / UPDATE / UNLINK / delete_many / collection 操作。**
