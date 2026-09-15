# GHOST-pin-rootfix 完成报告（community 置顶帖幽灵重复 — 根治）

- 任务：`.ai-hub/plans/artifacts/kickoff-GHOST-pin-rootfix.md`
- 日期：2026-09-15
- 执行：单写者（锁 `edu-agent/scripts/eval/ghost.lock`，完工删除）
- 结论：**数据（40 行同名种子帖软删）+ 后端点序（补唯一 tiebreaker）双管根治，GWT 9/9 PASS**；
  另有 1 项与 kickoff 假设不符的实锤修正——见 §2。

---

## 0. TL;DR

| 项 | 值 |
|---|---|
| 备份 | `deploy/backups/community_post_20260915_180928.sql`（39,856 B，sha256 `3d8a61816193dc70…3ebd3eb1e`，含清理前 **98** 行完整数据） |
| 清理 | 同名重复组 4 组、**软删 40 行**（`yn=0`）；`community_post` 总行数不变（98），`yn=1` 98 → **58** |
| 置顶 | 同名置顶帖 **14 → 1**（保留最早 `id=1`，2026-08-09 08:36:13） |
| 后端 | `order_by` 三档排序末位补 `P.id DESC`（全序）——响应结构不变，**非契约变更** |
| 首页 | `page_size=10`：页 1 置顶 **10 遍 → 1 遍**；全站同标题重复 **4 组 → 0 组** |
| GWT | **G1~G4 共 9 项断言 9/9 PASS**（G5/G6 见 §5） |

---

## 1. 步骤 1：只读核查（禁写）证据

脚本：`edu-agent/scripts/eval/ghost_audit.py`（纯 SELECT/SHOW/information_schema）
落盘：`edu-agent/scripts/eval/.ghost_tmp/audit.json`

```
rows_total=98  yn=1:98  is_pinned=1 且 yn=1:14
同名置顶帖（title LIKE '%欢迎来到%' AND is_pinned=1）14 条：
  id=1  (2026-08-09 08:36:13, views=129, hot=2.684904)  ← 唯一被更新过（updated_at 08-17）
  id=4,8,12,16,20,24,28,32,36,40,44,48 (2026-08-09 08:36~09:12, views=128, hot=0)
  id=74 (2026-08-14 01:43:17, views=146, hot=2.449121)
```

同标题重复**不止置顶一组**（同一缺陷类的其它表现，`GROUP BY title HAVING COUNT(*)>1`）：

| 组 | 标题 | 条数 | ids | 置顶 |
|---|---|---|---|---|
| A | 👋 欢迎来到 EduAgent 学习社区！ | 14 | 1,4,8,…,48,74 | 是（14/14） |
| B | 📖 英语单词学习经验贴：背单词的 3 条心法 | 14 | 2,5,9,…,49,75 | 否 |
| C | 🐍 Python 新手入门：为什么从 print("Hello World") 到 函数 很重要？ | 14 | 3,6,10,…,50,76 | 否 |
| D | fe-tester 验收帖：社区发帖积分与详情页测试 | 2 | 60,66 | 否 |

**真正来源（根因链）**：`项目文档/patch_community_gamification_tables.sql` L137 用 **裸 `INSERT IGNORE INTO community_post`**，
而 `community_post` **没有 title 唯一键**（`SHOW INDEX`：PRIMARY/idx_board_created/idx_author/idx_hot/idx_board_pin_hot_created，均与 title 无关）
→ `IGNORE` 形同虚设，**每重跑一次补丁就多插 3 行**；本库被重跑 14 轮 → A/B/C 各 14 条。D 组是 2 个不同测试账号（uid 846/894）的同名验收帖。

---

## 2. ⚠️ 对 kickoff「批判根源」的实证修正（trust-but-verify）

kickoff 前批回执称根因含「**后端置顶并入分页逻辑——置顶帖被并入每页结果集**」。**实测不成立**：

1. **代码面**：`app/community/service.py::list_posts` 只有**一条**分页 SQL
   （`SELECT P.* FROM community_post P WHERE P.yn=1 ... ORDER BY P.is_pinned DESC, ... LIMIT %s OFFSET %s`），
   **没有任何**「置顶单独查一次再并入每页」的第二条查询。
2. **HTTP 面**：修复前对 8000 全页扫描 4 轮（`ghost_page_probe.py`）：
   `total=98 fetched=98 distinct=98 cross_page_dup={}` —— **跨页重复一次也未出现**，每条帖子全局只出现一次。
3. **真实现象解释**：首屏「同标题连渲染 N 遍」是**脏数据本身**在页 1 的密集呈现（`page_size=10` → 页 1 前 10 条全是同名置顶）。
   原现象写「连渲染 3 遍」与 `page_size=3` 时的排序前缀一致（旧序首 3 = 48/1/74，均同名置顶）——属推断，非本次实测。

因此本任务**未触碰任何置顶并入逻辑**（本来就不存在），只做「数据清理 + 点序全序化」，避免无谓的契约变更。

**唯一被证实的后端真缺陷是次生风险**：旧 `ORDER BY` 不是全序（`hot_score=0.0` 并列 11+ 行、`created_at` 同秒），
`LIMIT/OFFSET` 下正确性依赖 MySQL filesort 的实现细节——本次未能复现跨页重复，但属**潜在**不重不漏失效点，已加固（§3.3）。

---

## 3. 步骤 2：根治

### 3.1 备份（先备份后清理，脚本强制）

```bash
mysqldump -h127.0.0.1 -P3306 -uroot -p*** --single-transaction --skip-add-locks \
  --default-character-set=utf8mb4 --databases edu --tables community_post \
  > deploy/backups/community_post_20260915_180928.sql
```
- 路径：`E:\stu\project\stu\EduAgent实施手册\deploy\backups\community_post_20260915_180928.sql`
- 大小 39,856 B，含 `CREATE TABLE \`community_post\`` + 98 元组，sha256 `3d8a61816193dc70609e39a3379f36e3bcb4cb23dbbc51dee6eea183ebd3eb1e`
- **脚本级红线**：`ghost_pin_cleanup.py --apply` 必须显式传 `--backup`，且脚本会校验备份含 `CREATE TABLE \`community_post\`` 与数据行，否则 `[ABORT]` 拒绝写库。

### 3.2 数据清理（软删优先，可原样回收）

脚本：`edu-agent/scripts/ghost_pin_cleanup.py`（`--dry-run` / `--apply --backup` / `--check`）
规则：`yn=1` 下同标题组保留 **MIN(id)**（最早），其余 `UPDATE ... SET yn=0, is_pinned=0`（**不 DELETE**）。

| 组 | 标题 | keep | 软删 ids |
|---|---|---|---|
| A | 👋 欢迎来到 EduAgent 学习社区！ | **1** | 4,8,12,16,20,24,28,32,36,40,44,48,74 |
| B | 📖 英语单词学习经验贴… | **2** | 5,9,13,17,21,25,29,33,37,41,45,49,75 |
| C | 🐍 Python 新手入门… | **3** | 6,10,14,18,22,26,30,34,38,42,46,50,76 |
| D | fe-tester 验收帖… | **60** | 66 |

**before / after**

| 指标 | before | 清理当时 after | 收尾复核（跑完 live 契约测试） |
|---|---|---|---|
| `rows_total`（全表） | 98 | 98（软删不减行） | **100**（live 契约测试各新建 1 帖） |
| `yn=1` | 98 | **58** | **60** |
| `yn=0`（软删） | 0 | **40** | **40** |
| `is_pinned=1 且 yn=1` | **14** | **1** | **1** |
| `yn=1` 同标题重复组 | 4 | **0** | **0** |

> 注：`rows_total`/`yn=1` 会随任何 live 契约测试（`POST /api/community/posts`）继续增长，**不是本次清理的回退**；
> 本次清理的净效果看 `yn=0=40`（软删恒为 40）与「同标题重复组 0」「置顶 1」两个不变量。
> 收尾复核：`ghost_pin_cleanup.py --check` → `[check] duplicate_groups=0 -> PASS(无重复)`。

副作用（已核查、无害且可逆）：挂在软删帖上的孤儿 `community_comment` **3** 条、`community_react` **3** 条——这些帖子 `yn=0` 后列表/详情均不可见，关系行保留即「原样可回收」；`gamification` 的 `POST_LIKES_TOTAL` 走 `WHERE yn=1 AND author_id=%s`，admin(uid=1) 的虚拟点赞基数随重复帖一并回落（期望行为）。保留置顶：`id=1, 👋 欢迎来到 EduAgent 学习社区！, view_count=130`。

### 3.3 后端修正：分页点序全序化（响应结构不变）

`edu-agent/app/community/service.py::list_posts`

```python
# BEFORE
"HOT":  "P.is_pinned DESC, P.hot_score DESC, P.created_at DESC"
# AFTER
"HOT":  "P.is_pinned DESC, P.hot_score DESC, P.created_at DESC, P.id DESC"
# NEW / LIKE 同步补 P.id DESC（含 .get 默认档）
```

- 置顶优先键保持首位 → 置顶帖只落在第 1 页首屏；主键 tiebreaker 收尾 → 排序唯一，`LIMIT/OFFSET` **严格不重不漏**。
- **响应壳/字段零变化**（`{total,page,page_size,items,mine_total_posts}` 原样）→ 不触发冻结契约，故 **G6 无需变更单**。
- 前端 T3B 的 `renderPosts` 按 id 去重（`community.html` L405-409 `seen[pid]`）**原样保留**作为兜底，本任务不依赖它：
  后端修复 + 数据清理后，即使无前端去重也不再同标题重复。

### 3.4 复发根治：种子补丁幂等化（额外发现，本地修复）

`项目文档/patch_community_gamification_tables.sql` L137 改为

```sql
INSERT INTO community_post (...)
SELECT * FROM ( ...3 行 UNION ALL... ) AS seed
WHERE NOT EXISTS (SELECT 1 FROM community_post p WHERE p.yn=1 AND p.title = seed.title);
```

- 事务内双向验证：**缺则插 3、重跑插 0**。
- ⚠️ 踩坑：初版守卫漏了 `p.yn=1` → 软删（`yn=0`）的同名旧行会永久阻止种子补插（实测 rowcount 恒为 0）。已修正并复验。
- 重跑 `apply_patch_community_gamification.py`：**14/14 checks PASSED**，且帖子数不变（幂等生效）。
- 说明：`项目文档/` 被其 `.gitignore`（`/*`）忽略，此修复**不进 commit**，属本机防复发；可追踪的复发巡检是 `ghost_pin_cleanup.py --check`（有重复组则 exit 1）。

---

## 4. GHOST-GWT 逐条复现

脚本：`edu-agent/scripts/eval/ghost_verify_gwt.py --base http://127.0.0.1:8010 --backup <dump>`
证据 JSON：`edu-agent/scripts/eval/.ghost_tmp/gwt_results_final.json`（含全量 page1/page2 id 清单与 13 组组合扫描明细）

| GWT | 断言 | 结果 | 数字/证据 |
|---|---|---|---|
| G1 | 备份存在且含清理前完整行 | **PASS** | `deploy/backups/community_post_20260915_180928.sql`，98 行，sha256 `3d8a6181…` |
| G2 | 同名置顶帖 ≤1 条真实保留 | **PASS** | `pinned_same_title_yn1=1`、`pinned_yn1_total=1`；`yn=1` 重复组 `[]` |
| G2 | before/after 计数 | **PASS** | yn=1 98→58，软删 40，全表行数不变 |
| G3 | page1 ∩ page2 = ∅ | **PASS** | page1 `[1,63,77,73,67,51,47,43,39,35]`，page2 `[31,27,23,71,70,69,53,52,68,65]`（交集空） |
| G3 | 首屏置顶仅 1 次 | **PASS** | 页 1 置顶 ids `[1]` |
| G4 | 全页扫描 total == distinct | **PASS** | total=59 / fetched=59 / distinct=59 / dups=[] |
| G4 | 9+ 组合不重不漏 | **PASS** | page_size∈{3,20,100}×sort∈{HOT,NEW,LIKE} + board∈{general,english,math,programming}，13/13 组合全部 `distinct==total`，`dups=[]`，页 1 置顶恒为 `[1]` |
| G5 | 既有 community 测试全绿 + 新增契约测试 | **PASS** | 见 §5 |
| G6 | 是否触及契约 | **N/A** | 未触及（响应结构零变化），无需变更单 |

**修复前基线（8000，旧代码 + 脏数据）**：`page_size=10` 时页 1 置顶 **10** 条同名；全站同标题重复 4 组（14/14/14/2）。
**修复后**：页 1 置顶 1 条；同标题重复 **0** 组；`title_counts` 无任何 >1。

---

## 5. 测试（G5）

| 测试 | 结果 | 说明 |
|---|---|---|
| `tests/test_community_service.py` | **15 passed** | 原 12 条 + **新增 3 条**（`test_list_posts_order_by_is_total_order`，`sort∈{HOT,NEW,LIKE}` 参数化） |
| `tests/test_contract_task15.py`（community 响应壳契约，live） | **20 passed** | 全绿 |
| `tests/test_contract_all_routers.py` | 社区相关用例全绿 | 唯一失败 `TestMiddlewareOrder::test_security_headers_present` 与 community 无关，且原始代码同样失败（预存在） |
| `tests/test_contract_task113.py` | 4 条曾失败 → **逐个隔离复跑 4/4 PASS** | 失败原因全为 `登录失败: 429 {'code':'42900','请求过于频繁'}`——`/api/auth/login` 限流 60s/10 次，被同文件多类用例连续登录打爆；**与本次改动无关**（原始代码同样失败） |

新增契约测试覆盖口径：断言三档排序 SQL 均以 `P.is_pinned DESC` 开头（置顶只落首页）、以 `P.id DESC` 收尾且位于 `LIMIT` 之前（全序 ⇒ 不重不漏）。

---

## 6. 残余 / 未做项（诚实登记）

1. **「置顶只在第一页返回一次」的严格语义未实施**（当前为排序优先语义）。要保持 `total` 与 `items` 一致（G4 要求），
   把置顶彻底从后续页剔除是**不可能**的；可行实现只有「响应新增 `pinned` 独立字段」= **冻结契约变更** → 按 G6 规约停手上浮，
   本任务**未自行改动**。当前 1 条置顶帖场景下页面表现已完全正确；只有当**置顶帖数 > page_size** 时置顶才会溢到后续页。
2. **其它测试残留数据未清理**（超出本任务范围，未动）：`[已更新] P6 打靶学习笔记 <随机id>`、`契约验证帖 <随机id>` 等
   probe 残留帖各自标题唯一（不产生「同标题重复」），但仍是测试垃圾；建议单独立项清理。
3. 孤儿评论/反应 3+3 条（挂在软删帖上）保留，出于「可原样回收」考虑未联动软删。
4. `项目文档/` 目录被 gitignore，种子幂等修复只落在本机（见 §3.4）。

---

## 7. 复跑命令

```bash
cd edu-agent
# 只读核查
.venv/Scripts/python.exe scripts/eval/ghost_audit.py
# 复发巡检（有同标题重复组则 exit 1）
.venv/Scripts/python.exe scripts/ghost_pin_cleanup.py --check
# 清理计划（只读）/ 执行（须先备份）
.venv/Scripts/python.exe scripts/ghost_pin_cleanup.py --dry-run
mysqldump ... > ../deploy/backups/community_post_$(date +%Y%m%d_%H%M%S).sql
.venv/Scripts/python.exe scripts/ghost_pin_cleanup.py --apply --backup ../deploy/backups/community_post_XXX.sql
# 全页重复扫描 / GWT 复现（需一个后端实例，本任务用 8010 临时实例）
.venv/Scripts/python.exe scripts/eval/ghost_page_probe.py http://127.0.0.1:8010 10 3
.venv/Scripts/python.exe scripts/eval/ghost_verify_gwt.py --base http://127.0.0.1:8010 --backup ../deploy/backups/community_post_XXX.sql
```

> 探针注记：本机环境设了 `HTTP_PROXY=http://127.0.0.1:57045`，loopback 请求会被代理吞成 502，
> 探针已内置 `ProxyHandler({})` 绕过；全页扫描请求量大，已内置 429 退避重试。
