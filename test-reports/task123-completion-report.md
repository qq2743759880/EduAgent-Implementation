# task123 — 流程收尾包（跨域）完工报告

- 域：MIX（git/DB/部署/流程）｜执行：traework 独立上下文子 agent｜日期：2026-09-04
- 授权范围：A 种子清理 SQL（只产出不执行）｜ B DEBUG=False 检查单入 deploy/README.md｜ C 只读盘点核对结论
- **未 commit、未执行 DB DELETE、未连 Milvus 写操作、未改 .env**（严格遵守开工单硬性守则）

---

## 1. 改动清单（产出文件 × 行号）

| 文件 | 改动 | 位置 |
|---|---|---|
| `refactor_sql/06_task123_clean_itest.sql` | **新建**：清理 itest-* 种子脚本（备份声明 + 事务 + FK 关闭 + 12 条 DELETE，子→父顺序） | 全文件 |
| `deploy/README.md` | **修改**：新增「DEBUG=False 部署前必跑检查单（task123）」段 + 「venv 依赖清单（pdfplumber）」段 | 新增 65–100 行 |

未改动：`.opencode/plans/critique-backlog-tracker.md`（编排者独占）、`.ai-hub/plans/tasks/plans/critique-backlog-tracker.md`、`project-handoff.md`、`.env`。

---

## 2. 机验输出（只读 SELECT + 语法校验）

### 2.1 itest 种子实证（pymysql 连 localhost edu，全只读）
```
sys_user itest-% accounts     : 1    (id=100019, account=itest-newuser)
series   itest-% rows         : 9    (2629~2635,2648,2653)
series_cohort under itest     : 0
sys_user_auth (itest 关联)    : 1    (id=100043 -> user_id=100019)
```
- itest series 详情：2629 `itest-series-1`(draft)、2630/2631 `itest-sweep-*`(off_sale)、2632 `itest-del-check-*`(off_sale)、2633/2634/2635/2648/2653 `itest-sweep-*`(off_sale)。
- 依赖链实测全空：series_cohort=0 → modules/sessions/assets/videos/chapters=0（脚本对 0 行 DELETE 无副作用）。
- 外部引用实测全 0：series_category_rel / coupon_series_rel / series_exposure_log / series_search_log / series_favorite / series_visit_log；user 侧仅 sys_user_auth=1（user_profile/student_profile/staff_profile=0）。
- **SQL 语法校验**：将 DELETE 全量替换为 `SELECT COUNT(*)` 变换重跑，12 条语句全部 parse 通过，命中数 = 预定期望（1 user / 1 auth / 9 series / 其余 0）。**未实际执行任何 DELETE**。

### 2.2 DEBUG 状态核对
- `edu-agent/.env` 当前 `DEBUG=true`（本地开发态）。→ GWT「生产 DEBUG=False 下 curl 401」需编排者在部署态验证（本次不改 .env、不跑生产态 curl）。

---

## 3. 核对结论

### 3.1 task43 核对（L12）
- **结论**：`test-reports/` 下**无任何 task43 完工报告**，也无 HTML APPROVED/HTML_APPROVED 门槛记录；全仓文档仅 task123 提到 task43，无 task43 实现痕迹。
- **判定**：task43（React dashboard）属 React 前端线待办，**从未实际实现→ 无完工/APPROVED 可补**。本轮优化期已把 fe-html 静态页 dashboard 能力补齐（page-polish/fe-html），与 React 线并存。按 Season2 决策 S2-D1（方案 B：React 线继续），task43 应**重新排期待派**（并入 Season2 React 管理端批次），而非补写完工报告。需编排者在看板（project-handoff）将 task43 状态改为「待排期 React 线」，非「已完成待验收」。

### 3.2 critique-backlog-tracker 核对（L20）
权威 tracker `.opencode/plans/critique-backlog-tracker.md` 逐条对照开工报告与 completion-report，分三类：

**A. 已闭环但未勾选（证据充分，建议编排者勾选）**
| 落点段 | 条目 | 证据 |
|---|---|---|
| task32 | task-VEC批判③（记忆召回样本≥30） | task32-report §4 ✅ 评估集 100≥30 |
| task32 | task31批判①（rerank语义等价量化） | task32-report §4 ✅ MRR+33%/hit@1+533%，degraded=0 |
| task37 | task12批判（死代码清理） | task37-report GWT①（commit d1530d2） |
| task37 | task14/15批判（断言bug） | task37-report GWT②（22fbf64，33 例全 PASS） |
| task37 | 91项预存失败排查 | task37-report GWT③（0 意外生产缺陷失败） |
| task37 | task-VEC批判①（user_memory 512→1024） | task37-report GWT④（5e76971，确认无 512 维脏数据） |
| task-G1 | G1-①/②（retry 接入 + 60s 窗口） | task-G1-report（①接入 generator/agent；②INCRBY+EXPIRE 60s）——**建议编排者对照①③复核后再勾** |
| W1 | C-18（注册两步式登录，task114 讨论项） | task114 默认"不采纳"留档 → 可关闭 |

**B. 真实未做（保持未勾 / 需排期）**
| 落点段 | 条目 | 说明 |
|---|---|---|
| task32 | task30批判②（真实LLM前缀已验证） | task32-report §4 明确「⏭ 未复验」 |
| task32 | task29批判③（多轮相同前缀缓存benchmark） | task32-report 未含 → 真未做 |
| task37 | task59批判①（MarkdownView text-[15px]） | 已写 `handoffs/task37-discrepancy.md` 上浮 TraeWork，**前端修复未做** → 半闭环"已上浮待派" |
| task37 | task60批判②（MutationCache 401/403） | 同上，discrepancy 单上浮，前端修复未做 |
| task39 / task69 | 全段条目 | 无对应 completion-report → 真未做 |
| task98 | CI门禁/口径漂移/91归一 | **`test-reports/task98-completion-report.md` 文件缺失**（next-season 声称存在，实查无此文件）→ 需编排者核实 task98 验收状态 |
| task34 | task30批判①（raw_content 双份增长/VARCHAR(8000)） | task34-report 未见该指标明确闭环声明 |
| task35 / task66 | 图谱重建 / 退款状态机 | next-season 第二类「真未开工」 |
| task-T1/S1/R1/O1 | 全段条目 | 无 completion-report → 未做 |
| task-C1②③ / C2②③ / M1②③ | — | 有 report 但未见批判项明确闭环声明；且 C1-report「opt-in 全关」与 C1-②「真实对话启用」目标存在张力 → 待编排者逐一核对 |
| W1 C-15/C-16（silent-refresh / 守卫抽离） | — | task122-report 未涉 single-flight refresh 与 guard 抽离 → 未闭环 |
| W1 C-17（死链扫描） | — | 落点 task123 检查单 + L4 回归，但本次授权范围未含死链扫描工具（L4 由编排者执行），故 C-17 未在本任务闭环 |

**关键修正**：编排者基线「task32 段 4 项真实未做」**不成立**——实证 4 项中 2 项（VEC批判③、31批判①）已闭环未勾选，仅 2 项（30批判②、29批判③）真未做。

### 3.3 Milvus user_1 分区残留（task61 遗留）
- 残留：`edu_knowledge` collection（settings.MILVUS_COLLECTION 默认 `edu_knowledge`）`user_1` 分区 4 行（task61 分区管理验收文档向量）。
- 已实证：`DELETE /partitions/user_1` → 500，Milvus「partition is loaded，需先 release」。
- 清理说明（**待编排者/生产重建时执行，本次不连 Milvus**，pymilvus 两行）：
```python
from pymilvus import connections, Collection
connections.connect(alias="default", host="127.0.0.1", port="19530")
col = Collection("edu_knowledge")
col.release_partition("user_1")   # 先卸载
col.drop_partition("user_1")      # 后删除
```
- 生产重建种子时另有 task61 备注：用户种子/课程封面 `avatar_url`/`cover_url` 含假域名 `cdn.example.com`，需替换或置空。

---

## 4. 资产消费证据（self-check → security skill）

**消费**：加载 `security` skill（audit/harden/be-security 三合一）。其 SKILL.md 声明执行内核 `scripts/security-scan.mjs` 调用 semgrep+gitleaks，但**该脚本路径不存在**（skill 自身缺陷）→ 按 skill 降级规则如实降级为：
- 直接调起 **semgrep**（`--config=auto` 因需联网取规则集而无可视结果，工具存在但规则获取失败）+ **gitleaks**（真实扫描成功）。
- **gitleaks 实证**：edu-agent/app 历史 132 commits 扫描，8 处发现**全部为良性**（`curl-auth-header`×2 为 plans/handoffs 文档 curl 示例；`generic-api-key`×5 为 test-reports/test_log_sanitizer 测试 JWT 占位 + `.env.example`/`.env.production.example` 的 `MILVUS_TOKEN=` 空占位符、`MILVUS_DB=default`）——无真实泄露密钥。非本任务范围（登记备查）。
- 辅以 **be-security.md 后端专业清单**手核：鉴权/禁用降级/密钥/cors。

**自检发现并修掉 / 登记的问题**：
1. **已修（报告层）**：git 首页盘点时将「/api/metrics 需鉴权」按实际分两类登记——`/api/metrics/cache-context-dashboard` **有** `Depends(require_role([ADMIN,MANAGER]))`；而裸 **`/metrics`（Prometheus 抓取端点，main.py 无 prefix 挂载）当前无 Depends 守护**。task123 检查单要求的「metrics 无 token 401」对 `/api/metrics/cache-context-dashboard` 成立，但对裸 `/metrics` **不成立**（该端点本就面向 Prometheus 抓取）。已在 deploy/README 检查单项 #4 尾部加 ⚠ 实证登记，交编排者确认 task113 是否期望裸 `/metrics` 也鉴权。
2. **报告层登记**：`.env` 当前 DEBUG=true（本地 dev），生产 401 验证在部署态由编排者执行（检查单命令已备）。
3. **review critique 三视角自检**（交互态/边界/错误反馈）：检查单三条 curl 覆盖「无 token（边界）」「垃圾 token（错误反馈）」「X-Force-Role 越权手势（交互态安全）」，均为丢数据不落盘的只读探测，可离线复跑。

---

## 5. 遗留与降级项（如实标注）

- **DB 实证**：GWT `SELECT count(*) ... itest-% = 0` **未达成**（当前 1 user / 9 series 仍在库）。属预期——清理 SQL 仅产出，**执行权在编排者备份后统一执行**。成功后 DB=0 达成。
- **生产 DEBUG=False curl 401**：本任务未执行（当前 .env DEBUG=true，改 .env 属禁止项）；凭证在 deploy/README 检查单，编排者部署态跑。
- **死链扫描（W1-C-17）**：不在本授权范围；编排者 L4 回归时按检查单挂接。
- **security-scan.mjs 缺失**：skill 声明与实存不符已降级为 semgrep/gitleaks + be-security 手核（不伪报扫描结果）。
- **commit 归属（L13）/ 17 个 staged / 根目录杂项**：属编排者改动点 2/6，不在本单授权，未处理。
- **task98-completion-report 文件缺失**：需编排者核实（next-season 引用的验收证据找不到）。

---

## 产出文件清单
- `refactor_sql/06_task123_clean_itest.sql`（新建）
- `deploy/README.md`（修改：+检查单 +pdfplumber）

## SELECT 实证摘要
- itest 残留：`sys_user=1`（id100019）、`series=9`（2629~2635,2648,2653）、`sys_user_auth=1`（关联100019）、itest cohort=0、外部引用=0。
- SQL 语法：12 条语句变换 SELECT 全通过，命中=期望。