# 数据库体检报告 — MySQL 主库（2026-08-15）

> 体检人：开发本人（AI 教练陪同） | 目标库：edu（105 表，MySQL 8.0.12 本机）
> 目的：量化主库健康度，产出索引/参数修复清单，积累面试可讲的数据库运维经验

---

## 1. 基线快照

| 指标 | 当前值 | 企业参考标准 | 判定 |
|------|--------|-------------|------|
| 版本 | MySQL 8.0.12 | — | ⚠️ 偏旧（建议 8.0.35+，含更多 bug 修复） |
| `innodb_buffer_pool_size` | 128MB（8.0 默认值） | 物理内存 50~70% | ❌ 未按机器调优 |
| `long_query_time` | 10s | 1s（教育平台常 500ms） | ❌ 太松，慢查询会漏 |
| `max_connections` | 151（默认） | 按连接池规模 + 冗余 | ⚠️ 默认值 |
| QPS（Questions/Uptime） | 4252 / 40660s ≈ 0.1 | 教育平台峰值上千 | ⚠️ 玩具负载，慢日志无参考性 |
| Buffer Pool 命中率 | 1336/1361519 = 99.9% | ≥99% | ✅（数据小，假性健康） |
| `Slow_queries` | 0 | — | 负载太低，无意义 |
| performance_schema | ON | ON | ✅ |
| sys schema | 已装 | 已装 | ✅（白嫖的审计工具） |

**结论**：实例能跑，但全部参数停留在"装完即用"状态。面试官问"你们 MySQL 调过什么参数"，目前答不出来。

---

## 2. 索引审计发现（sys schema 白嫖审计）

### F1 · 冗余索引 ×4（最左前缀原则违规）

| 表 | 冗余索引 | 覆盖它的索引 |
|----|---------|------------|
| admin_exam_paper_item | idx_admin_exam_paper_item_paper(paper_id) | uk_admin_exam_paper_item_question(paper_id,question_id) / uk_..._sort(paper_id,sort_no) |
| curriculum_session | idx_curriculum_session_module(module_id) | uk_curriculum_session_no(module_id,session_no) / idx_..._module_yn(module_id,yn) |

- 原理：联合索引按左起列排序，单独建前缀列索引=重复维护 B+ 树，白白拖慢 INSERT。
- 修复：DROP（生产流程：先 `ALTER TABLE ... ALTER INDEX x INVISIBLE` 观察一周再删）。

### F2 · 索引比数据大的过索引表

| 表 | 数据 | 索引 | 说明 |
|----|------|------|------|
| session_homework_question_rel | 2.5MB | 4.5MB | 关系表被索引淹没 |
| session_teacher_rel | 1.5MB | 3.0MB | 同上 |
| session_exam_question_rel | 1.5MB | 3.4MB | 同上 |

- 关系表通常只需 (左外键, 右外键) 联合唯一索引 + 右外键单列索引，其余多为冗余。

### F3 · 零使用索引（count_star=0，自上次重启以来）

- admin_course_video_asset / admin_exam_paper / admin_question 等 admin_* 系列表全部索引零使用。
- 原因：管理端新表建好但功能未上线使用。
- 教训：**索引跟着查询走，不是建表时批量堆**。

### F4 · 业务真实查询 EXPLAIN 证据

| 查询 | 执行计划 | 问题 |
|------|---------|------|
| `admin_question_bank WHERE yn=1 AND subject_code='math' ORDER BY id DESC` | type=index（全索引扫描）possible_keys=NULL | idx_admin_question_type_subject 最左列是 question_type，单独按 subject_code 过滤用不上（最左前缀） |
| `question WHERE yn=1 AND stem LIKE '%函数%'` | **type=ALL，10044 行全表扫描** | 前导通配符 `%x%` 无法用 B-Tree；stem 是 TEXT，每行大字段读取 |
| `community_post WHERE board_code='math' ORDER BY is_pinned,hot_score,created_at` | type=ref + **Using filesort** | idx_board_created(board_code,created_at) 无法满足 HOT 排序（is_pinned/hot_score 不在索引中） |
| `chat_message WHERE session_id=? ORDER BY created_at,message_id` | 走 idx_chat_message_session_created | ✅ 设计正确 |
| `chat_session WHERE user_id=? ORDER BY last_message_at` | 走 idx_chat_session_user_lastmsg | ✅ 设计正确 |
| `question WHERE question_type_id=3` | type=ref，1410 行 | ✅ 但无 yn 复合，回表取 yn 过滤 |

### F5 · 数据架构异常（面试必须自圆其说）

- 管理端题库表 `admin_question_bank` 仅 18 行，真实题库 `question` 10512 行 —— 管理端操作的是**另一套题库**。
- 风险：面试官问"管理端上架的题，用户为什么刷不到"→ 现答案：两套表未打通。
- 建议：明确两表职责（admin 侧=草稿/审核流，question=发布库）并写进文档，这本身是"题库审核工作流"的加分设计。

### F6 · 参数配置

- `long_query_time=10` → 调 1（会话级 SET GLOBAL 教学 + my.ini 持久化教学）
- `innodb_buffer_pool_size=128M` → 本机数据总量 ~70MB 其实够用（**数据量小时不盲目调大，这是判断力**）；生产部署原则要会：物理内存 50-70%
- `max_connections=151` → 与后端连接池配合说明（asyncmy pool size 默认？待查）

---

### F7 · Redis 代码已备、服务缺失（下一阶段伏笔）

- `database.py §6`：Redis 异步连接池（init_redis/get_redis）已写好
- `common/rate_limit.py`：滑动窗口限流中间件已写好（登录 10/min、AI 问答 20/min、管理端 200/min，对标作业帮/猿辅导阈值）
- 但 Redis 服务器不存在（localhost:6379 / VM 6379 均不通）→ 中间件每请求走"降级放行"分支
- **结论**：Q2 阶段 = 装 Redis → 激活限流 → 热点缓存落地

## 3. 修复计划（按优先级）

| 编号 | 动作 | 教学点 | 状态 |
|------|------|--------|------|
| R1 | long_query_time 1s（SET GLOBAL + 持久化方式讲解） | 会话级 vs 持久化配置 | ✅ 会话级已生效；my.ini 持久化与 R6 一并记录 |
| R2 | 删 4 条冗余索引（走 Alembic 迁移，先 INVISIBLE 后 DROP 的稳妥流程演示） | 最左前缀 + 迁移工作流 | ✅ 迁移 d1e2f3a4b5c6，upgrade→downgrade→re-upgrade 闭环验证，schema_redundant_indexes 归零 |
| R3 | question.stem 加 FULLTEXT ngram 索引（中文分词），验证 EXPLAIN 变化 | 中文全文检索方案选型 | ✅ 迁移 e2f3a4b5c6d7，EXPLAIN type=ALL(10044行)→type=fulltext(rows=1)，'函数'命中 360 题 |
| R4 | community_post 加 (board_code, is_pinned, hot_score, created_at) 复合索引 | 排序索引设计 | ✅ 迁移 f3a4b5c6d7e8，Using filesort 消除 → Backward index scan |
| R5 | admin_question_bank 补索引 | 判断力：数据量小不建索引 | ✅ **决策：不建**。18 行表全表扫描是正确的执行计划；等数据量上来再按查询模式补 |
| R6 | 后端连接池参数审计 | 连接池 vs 最大连接数 | ✅ PASS：pool_size=10 + 只读池 5 ≪ max_connections=151，配比健康；已有并发闸+超时+重试防挂死（task04 修复遗产） |

**R2 过程中的环境债修复**：alembic 原只装在 anaconda base（无 pymysql），kb311（无 alembic）跑不了迁移——已 `pip install alembic` 进 kb311，确立 kb311 为唯一事实源。原 P2-A 的迁移实际是用 base 环境跑的，此为环境不一致历史债，现已修复。

## 4. 面试话术素材（本次体检可直接讲的故事）

1. "我用 sys.schema_redundant_indexes 做了一次索引审计，抓到 4 条违反最左前缀原则的冗余索引，删除后 INSERT 少维护 4 棵树。"
2. "题干关键字检索 LIKE '%kw%' 全表扫描，我评估了三种方案：MySQL FULLTEXT ngram / ES / 复用现有 Milvus RAG，最终选 X，理由是……"
3. "数据量小时我刻意不做激进优化（buffer pool 128M 够用），但我知道生产怎么配——这是判断力。"
4. "DDL 全部走 Alembic 迁移，因为手敲 SQL 无法回滚、无法进 CI、无法审计。"
