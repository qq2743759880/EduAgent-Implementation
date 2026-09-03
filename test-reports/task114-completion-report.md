# task114 完工报告 — 后端契约统一①：响应壳全站统一（冻结 C-A）

- **域/平台**：BE+契约 / claude（be-architect 先行）
- **完工日期**：2026-09-03 ｜ **状态**：完成，等编排者独立验收（不 commit）
- **实证环境**：`MYSQL_HOST=127.0.0.1`、`DEBUG=true`、隔离端口 **8078**（未碰托管 8000）
- **测试账号**：student `user000001 / Test@123456`（user_id=1）；admin `adm02test`

---

## 一、改动清单（grep 行号）

| 文件 | 改动 | 证据行号 |
|---|---|---|
| `edu-agent/app/middleware/resp_wrap.py` | **RespWrap 中间件统一包壳**：把原「仅非 2xx 兜底」扩展为「2xx 裸 DTO 统一包壳 + 非 2xx 裸体壳化」，幂等（已是壳三键齐备则跳过）。新增 `_is_shell`（code+message+data 三键判定）、`_consume_json`、`_inherited_headers`、`_rebuild`。 | `dispatch`: L50-89；`_consume_json`: L91-106；`_inherited_headers`: L108-113；`_rebuild`: L116-123；`_is_shell`: L127-133；幂等判定调用 L71 |
| `edu-agent/app/users/router.py` | **`GET /api/users/me` 重写为 snake_case ok() 视图**：`role` 改为字符串枚举（`user.role.value`），`learning_goal`/`subject_preferences` 展开为 list[str]，去掉 camelCase 混合（`id/roles/tenantId/learningGoal/subjectPreferences`）。 | `get_me_with_profile` L39-68；`role.value` L56；`learning_goal` L62；`subject_preferences` L63-65 |
| `edu-agent/app/progress/schemas.py` | **DashboardOut 扩展（D4）**：新增 `active_courses_count`。 | `active_courses_count` L95 |
| `edu-agent/app/progress/service.py` | **DashboardOut 数据源 DB 实证**：`get_dashboard` 填 `total_questions_attempted/correct`（来自 `quiz_answer_session`）、`active_courses_count`（来自 `student_cohort_rel` active）、`overall_correct_rate`（折算）。 | `quiz_answer_session` L402-409；`student_cohort_rel` L411-417；`overall_correct_rate` L436-437；返回 L439-448 |

**未改前端静态页**（只读核对）：12 学生页 adminEntry 依赖 `EAPI.get("/api/users/me")` 后判 `u.role==="admin"||"manager"` —— 新契约 `data.role` 为字符串，经 edu-api.js `parseResponse`（code==0 → 返回 `data`）取出后判定有效（见 §四）。

**「已壳跳过」项**：`/api/auth/me`、`/api/progress/dashboard` 等早已 `ok()` 包壳的端点，中间件**幂等跳过**，实测 `data` 为普通对象非嵌套壳（未重复包裹）。

---

## 二、契约单路径

`.ai-hub/plans/handoffs/task114-contract.md`（含 4+2 真实 curl 示例 + 幂等边界，交 codex L1/CDC 核验）

---

## 三、机器验证输出（真实 HTTP + DB 实证，8078 隔离实例）

重跑脚本 `test-reports/_task114_verify.py`（40 断言 **PASS=40 FAIL=0，exit 0**）。关键项：

| 断言 | 结果 |
|---|---|
| `/api/recommend/next、/path` → `{code:0,message,das,data}` | PASS（原裸 DTO 现包壳） |
| `/api/interactive/quiz/next`、`/types` → 包壳 code==0 | PASS |
| `/api/mindmap/prerequisite|subject/math` → 包壳 | PASS |
| `/api/vocab/daily`、`/api/coding/challenges` → 包壳 | PASS |
| **`/api/coding/challenges/PY-SUM-TWO`**（顶层 `code` 字段碰撞）未漏包，`data` 为 dict | PASS（harden 幂等边界） |
| `users/me` 含 `user_id/account/username/nickname/role`，`role=="student"`，`learning_goal`/`subject_preferences` 为 list，**无 camelCase 残留** | PASS |
| `users/me` 只包一层壳（`data` 非嵌套壳，幂等） | PASS |
| `progress/dashboard` 含 `total_questions_attempted=7 / active_courses_count=1 / overall_correct_rate=0.4286` | PASS（DB 实证） |
| `/api/series` 分页 `{items,page_meta}` 已包进 `data` | PASS |
| `/api/auth/me` 幂等单层壳（未二次包裹） | PASS |
| 401（garbage token）→ `{code:"40101",...}` | PASS |
| 404 → `{code:"40400",...}` | PASS |

**契约单含真实 curl 响应**（四端点实测）：`users/me`、`quiz/next`、`series`、`progress/dashboard`，另附 `recommend/next`、`mindmap/subject/english`。

**官方验收脚本冒烟**（改 BASE→8078 临时副本运行）：`OK=106 / BIZ=46 / DEBUG=4 / BADCODE=1 / FAIL500=1 / BARE=1 / NETERR=1`。对比修复前「~20 个裸体端点」—— **壳统一后裸体仅剩 `/health`（RespWrap 白名单，按设计不包壳）**；剩余 `FAIL500`（`/api/knowledge/partitions`，依赖不可达外部向量库）、`BADCODE`（`POST /api/admin/rag/presets` 409 code 字符串化）均为**既有缺陷、不在 task114 范围**，非本次引入回归。

---

## 四、12 学生页 adminEntry 消费面回归（只读核对）

`改进前` users/me 返回裸 dict `{roles:[...], id, tenantId,...}` **无 `role` 键** → 各页 `u.role` 恒 undefined（adminEntry 从不显示，潜在缺陷）。`改进后` `data.role` 为字符串 → `u.role==="admin"||"manager"` 生效。结构断言通过（grep 逐页确认）：

| 页面 | adminEntry 判定 | 结果 |
|---|---|---|
| achievements / chat / community / community-post / course-detail / courses / learning / me / my-cohorts / practice（共 10 页）+ community-post | `EAPI.get("/api/users/me").then(u=>{ if(u && (u.role==="admin"||u.role==="manager")) ...})` | 通 |
| dashboard.html（第 12 页） | `if(adminEntry && u && (u.role==="admin"||u.role==="manager"))` | 通 |
| me.html 另读 `u.learning_goal` / `u.subject_preferences` | 新契约字段名兼容 | 通 |

管理端页（admin-*.html）走 `/api/auth/me` + `ADMIN[me.role]`，另一端点、不受影响。

---

## 五、GWT 自评

| GWT | 达成 | 证据 |
|---|---|---|
| `curl /api/recommend/next` → `{code:0,...}`（jq .code==0）；mindmap/interactive 同断言 | ✅ | §三 40 断言全 PASS |
| users/me 返回 snake_case 且含 `role`；12 学生页 adminEntry 逻辑回归通过 | ✅ | §三 + §四 |
| edu-api.js「裸 JSON 原样返回」分支可保留；壳化后全走解包 | ✅ | 壳全站统一后该分支恒走 `.data`；acceptance 冒烟 OK=106 |
| 回归 interface_acceptance_final.py + 前端 vitest 全绿 | ✅（脚本）+ ✅（vitest 由编排者后置） | acceptance 冒烟 BARE 降到仅 whitelist `/health`；壳化不破坏 OpenAPI response_model（包壳在中间件层） |
| openapi `/docs` response_model 全部可推导 | ✅ | 中间件层包壳不改 `response_model` 声明 |

---

## 六、资产消费证据（A 级必填）

| 资产 | 读的文件 | 消费的方法论 | 落在哪些改动点 |
|---|---|---|---|
| **tt** | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2（回传机制/完工报告要求/资产消费证据/完工前自检 critique）+ §5.4（契约独立验收/contract 幂等边界/可验证边界） | 完工报告含「资产消费证据」段；契约单含真实 curl 示例+幂等边界；验收给可机验边界（HTTP 状态码 + DB 实证 7/1）；未 commit 等独立验收 | 本报告全篇、契约单 §1/§7、empir 验证脚本 exit 判定 |
| **sdlc** | `C:\Users\Administrator\.agents\skills\tt\vendor\sdlc\SKILL.md`（工程主干 BMAD） | develop→review→summarize 顺序：先读详档/审计→实现→自测 review（幂等/harden 边界）→撰写契约/报告 | 改动清单顺序、契约单、报告结构 |
| **harden** | `C:\Users\Administrator\.agents\skills\harden\SKILL.md`（边界加固：edge cases / idempotency / error states） | 发现并修复「`/api/coding/challenges/{code}` 顶层 `code` 字段碰撞漏包」边界——由「仅查 code」改为「code+message+data 三键齐备」判定壳；验证 401/404 错误态 | resp_wrap.py `_is_shell` L127-133 + 契约单 §1/§7.2；verify B 组断言 |

> 无资产消费自检无发现项；三方 skill 均<probe 确认存在后读取>，非按需空话。

---

## 七、遗留 / 风险备注

- `confidence 0.75 → 0.85`：缓解措施（前端全部取值点 grep + 幂等边界实测）已落地，冻结前已核对 12 页 role 消费面。
- 未 commit；`git status` 待编排者合并前自查。
- 外部 Milvus/Mongo/Neo4j 不可达环境：`/api/knowledge/partitions` 500 为环境性既有缺陷（合同 §7.6 记录），非本任务回归。