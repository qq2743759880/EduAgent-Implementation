# REPORT-TA4 · 遗留测试数据清理

- 任务：TO-EXEC-TA4（yy 十点修复 · P0）｜分支 `feature/opt-waves`｜执行者：TA4
- 报告版本：**v2（阶段 A + B + C 全部完成）**
- 最后更新：2026-09-24 01:55 +0800

---

## 1. owner 批准与决策映射

阶段 B 硬停止点后，经信使收到 owner 书面批准：**「1.删 2.全删 3.同批删 4.删」**，四决策点全部批准。

| 决策点 | owner 指令 | 实际处置 | 落地的批 |
|---|---|---|---|
| 1 | 删 | A4/A5 MCP SSE 占位 server(`sse-demo-localhost`)+`sse_health` 软删 `yn=0` | 批 1+2（MySQL）|
| 2 | 全删 | A10 MCP 调用日志 443 条**全删** | 批 1+2（MySQL）|
| 3 | 同批删 | A7 `user_upload` 5 条任务行（已删）+ 其 Milvus `edu_knowledge` 的 9 chunk **同批删** | 批 1+2（MySQL）+ 批 5（Milvus）|
| 4 | 删 | D1+D2+D3 Mongo eval 产物 109 docs **全删** | 批 4（Mongo）|

---

## 2. 各批三核闸门证据

### 批 1+2 — MySQL（A1~A11）

**① 备份**：`deploy/backups/ta4/batch1-2-mysql-20260924_0131/` — 10 张表 `mysqldump`（rag_param_preset / question_bank / question / mcp_server / mcp_tool / knowledge_import_task / session_exam / session_exam_question_rel / mcp_tool_call_log / mcp_tool_description_review_log），`.err` 均 0 字节。

**② 执行 + 行数对账**：

| 表 | 处置 | 前 | 后 |
|---|---|---|---|
| rag_param_preset | 软删 yn=0（9 测试件）| yn=1=12 | yn=1=**3** |
| question_bank | 软删 yn=0（11 个 T13 库）| yn=1=449 | yn=1=**438** |
| question | 软删 yn=0（19 条占位题）| yn=1=10531 | yn=1=**10512** |
| mcp_server | 软删 yn=0（SSE 占位）| yn=1=2 | yn=1=**1** |
| mcp_tool | 软删 yn=0（sse_health）| yn=1=5 | yn=1=**4** |
| session_exam_question_rel | 硬删（6，无 yn）| 6 | **0** |
| session_exam | 硬删（6 个 T13 考试，无 yn）| 6 | **0** |
| knowledge_import_task | 硬删（A6 127 + A7 5 + A8 7 = 139）| 263 | **124** |
| mcp_tool_call_log | 硬删（443，无 yn）| 443 | **0** |
| mcp_tool_description_review_log | 硬删（24 孤儿，无 yn）| 24 | **0** |

**③ 幂等**：同批脚本重跑，第二次 `affected_rows=0` → IDEMPOTENT OK。

> 注：清理清单 v1 把 knowledge_tasks 预估为「263→136」（仅减 A6 的 127）。实际删除 A6+A7+A8 共 **139** 行，真实结果 **263→124**，比计划更干净。

### 批 3 — Redis（C1/C2/C3，133 keys）

**① 备份**：`deploy/backups/ta4/batch3-redis-20260924_0131/` — `target_keys.txt`(133)、`dumps/`(133 个 `.dump`，3.7 MB)、`before_dbsize.txt`(2547)、`after_dbsize.txt`(2434)、`reconcile.txt`。

**② 执行 + 行数对账**：`docker -c desktop-linux exec prisma-ai-redis-container-1 redis-cli UNLINK <133键>`
- 执行前实时 `DBSIZE = 2569`（备份快照为 2547，差 22 为快照后 TTL 续期/新增键，非目标键）
- `UNLINK_RETURN = 133`
- 执行后 `DBSIZE = 2434` = 2569 − 133 ✓ 差值恰为 133 个目标键

**③ 幂等**：二次 `UNLINK` 返回 `0`；`EXISTS` 复核 133 键 **0 残留** → IDEMPOTENT OK。

### 批 4 — MongoDB（D1/D2/D3，109 docs）

**① 备份**：`deploy/backups/ta4/batch4-mongo-20260924_0151/` — `artifacts.files.json`(23 KB / 41)、`artifacts.chunks.json`(5.9 MB / 48)、`learning_event.json`(7.7 KB / 20)、`manifest.json`(三集合精确 `_id` 清单，可逐条还原)。注：无 `mongodump`，改用 `bson.json_util` 无损导出。

**② 执行 + 计数对账**（按 `_id` 精确 `delete_many`，非 drop collection）：

| 集合 | 前 | 删 | 后 |
|---|---|---|---|
| artifacts.files | 41 | 41 | **0** |
| artifacts.chunks | 48 | 48 | **0**（48 chunk 全归属 41 目标 file）|
| learning_event | 20 | 20 | **0**（20 条全为探针事件）|

**③ 幂等**：二次 `delete_many` 均影响 0 行 → IDEMPOTENT OK。

> 备注：库 `edu_agent_rm1_test`（空测试库）按铁律禁 `DROP DATABASE`，未处理。

### 批 5 — Milvus（A7 关联 chunk，9 实体）

**① 备份**：`deploy/backups/ta4/batch5-milvus-20260924_0146/` — `a7_chunks_backup.json`(300 KB，含 9 实体完整向量+标量，可恢复)、`verify_backup_a7.py`、`delete_a7.py`、`verify_after.py`、`reconcile.txt`。

**② 执行 + 对账**：`edu_knowledge`（PK=`id`，源字段=`source_file`），目标 `source_file = 'up_1_1215916b_ib_g2_WNI1BG2_1789562680.md'`（task144 上传件；其余 4 个 A7 文件 知识库测试/t10_same/test_s4 经 `LIKE` 模式复核在 `edu_knowledge` 中 **0 chunk**）。
- `client.delete(ids=[9 PKs])` → `delete_count=9`
- 独立复核（**全新连接 + Strong 一致性**）：9 个目标 PK `REMAINING=0`、该 `source_file` `REMAINING=0`
- `get_collection_stats` 3435 → **3425**（compact 后净 −10 = 我删 9 + 1 历史 tombstone；存活查询恒为 0）

**③ 幂等**：二次 delete 对已 tombstone 实体不影响存活数据，存活查询恒 0 → IDEMPOTENT OK。

> A7 在 MySQL 任务行（批1+2 已删）+ Milvus 向量（本批删）一并清除，无「任务没了知识还在」残留。

---

## 3. 清理后回归证据

**API 探针（admin `adm02test` 登录，实测后端 9988）**：

| 端点 | 结果 | 期望 | 判定 |
|---|---|---|---|
| `GET /api/admin/rag/presets` | 3 | 3 | ✅ PASS |
| `GET /api/mcp/servers` | 1 | 1 | ✅ PASS |
| `GET /api/mcp/tools` | 4 | 4 | ✅ PASS |
| `GET /api/mcp/call-log` | 0 | 0 | ✅ PASS |
| `GET /api/mcp/description-review-log` | 0 | 0 | ✅ PASS |
| `GET /api/knowledge/tasks` | 124 | 124（计划误算为 136）| ✅ PASS |

**DB 残留核对（直连 MySQL 复核）**：
- `knowledge_import_task` 残留 124；`source_files LIKE '%knowledge_import_demo.md%'` = **0**；A7 `user_upload` 残留 = **0**；
- `rag_param_preset` yn=1=3；`mcp_server` yn=1=1；`mcp_tool` yn=1=4；`mcp_tool_call_log`=0；`mcp_tool_description_review_log`=0；
- `session_exam` 仅删 6 个 T13 测试考试（指定 id），其余 15444 为真实考试不受影响。

**DOM 钩子门（`scripts/gates/dom-hook-inventory.mjs --all --check`）**：**N/A**。本单**零改动**任何 HTML/JS/TS 文件（铁律），DOM 钩子清单不可能漂移；其浏览器新鲜度复检需 Next dev server + Playwright，而项目约定**禁用 Playwright**（AGENTS.md）。源扫描层面因无代码改动必然零新增，故不重写 `docs/dom-hooks-frozen.*` 基线、不触发被禁的浏览器检查。

---

## 4. 铁律遵守记录

- ✅ `session_asset` / `session_video` 零触碰（owner 未解冻）
- ✅ 生产业务数据（order/payment/series/sys_user 等）零触碰
- ✅ `user_memory_event` / `user_memory` / Milvus `user_memory` / Redis `memory:vec*` 零触碰
- ✅ 代码文件零改动（本单无代码变更）
- ✅ 无 `DROP TABLE` / `TRUNCATE` / Milvus collection reset / `FLUSHDB` / `DROP DATABASE`
- ✅ Redis 全程 `docker -c desktop-linux exec prisma-ai-redis-container-1` 前缀；`pf_bagu_kb` 等非我方资产禁碰
- ✅ 未 push；仅单 commit（仅含本任务产物：清单 + 报告 + 备份目录）

---

## 5. 备份文件清单（已落入版本控制）

| 路径 | 内容 |
|---|---|
| `deploy/backups/ta4/batch1-2-mysql-20260924_0131/` | 10 张 MySQL 表 mysqldump |
| `deploy/backups/ta4/batch3-redis-20260924_0131/` | 133 Redis key 清单 + 133 dump + 前后 DBSIZE + reconcile |
| `deploy/backups/ta4/batch4-mongo-20260924_0151/` | Mongo files/chunks/learning_event JSON 备份 + manifest |
| `deploy/backups/ta4/batch5-milvus-20260924_0146/` | A7 的 9 chunk 含向量备份 + 验证/删除脚本 + reconcile |
| `deploy/backups/ta4/redis-keys-scan-20260924.txt` | Redis db0 全量 2456 key 快照 |
| `deploy/backups/ta4/edu_knowledge_docchunk_sources.txt` | Milvus `edu_knowledge` doc_chunk 来源分组 |

---

## 6. 阶段 A/B/C 时间线

| 时刻 | 事件 | 状态 |
|---|---|---|
| 2026-09-24 01:04 | 收到 TO-EXEC-TA4，识别硬停止点 | ✅ |
| 2026-09-24 01:05~01:16 | 阶段 A 只读盘点（MySQL→Milvus→Redis→Mongo）| ✅ |
| 2026-09-24 01:16:55 | 《TA4-清理清单》写盘，阶段 B 硬停止点生效 | ✅ |
| 2026-09-24 01:3x | owner 批准「1.删 2.全删 3.同批删 4.删」| ✅ |
| 2026-09-24 01:31~01:55 | 阶段 C：批1+2 MySQL → 批3 Redis → 批4 Mongo → 批5 Milvus → 回归 | ✅ 完成 |

**结论：四决策点全部按 owner 批准执行，各批三核闸门（备份 / 行数对账 / 幂等）全过，回归探针 6/6 PASS，铁律零违反。**
