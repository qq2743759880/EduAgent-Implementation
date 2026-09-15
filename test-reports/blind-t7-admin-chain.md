# blind-t7 · 管理端删除保护链盲测（题库/班次/媒体 404）实测报告

- **executionSessionId**: `20260915_184725_128813`
- **测试身份**: 运营管理员 `adm02test / Test@123456`（附带 `mgr01test` 作角色对照）
- **被测对象**: 后端 `127.0.0.1:8000`（uvicorn，本机 edu-agent 工作副本）
- **测试窗口**: 2026-09-15 18:47 – 19:03 (GMT+8)
- **测试范围**: F8 题库删除保护(40924) / F9 班次删除保护(40908) / F10① `/media` 404 语义 / 误伤回归
- **方法**: 纯 HTTP（curl + httpx，`trust_env=False` 绕过 `HTTP_PROXY` 吞 loopback 问题）；`--noproxy '*'`。
  **未使用 Playwright**；**未做任何 DB 直写**；DB 仅用只读 `SELECT` 取落库态证据。
  测试数据全部自建、用后自清（见 §7）。

## 0. 独立性声明（盲测边界）

- 本会话**未读取**任何历史完工报告/验收文档（`F610-completion-report.md`、`H-independent-reverify.md`、`blind-t4/t5-*.md` 等一律未读）。
- 仅阅读允许材料：被测源码（`app/domains/{question_admin,course_admin}/**`、`app/main.py`、`app/common/error_codes.py`、`app/common/exceptions.py`、`app/domains/*/repository/*.py`）+ `AGENTS.md`。
- **副作用披露**：首轮用 Grep 搜 `40924|40908` 时，搜索命中行**顺带带出**了 `edu-agent/test-reports/F610-completion-report.md` 与 `H-independent-reverify.md` 的若干行片段（含结论性短句）。我**未打开这两个文件**，也**未把其内容作为任何断言的依据**；本报告所有结论均来自①本轮真实 HTTP 响应 ②本轮只读 DB 查询 ③源码行号佐证。

## 1. 结论摘要

| 项 | 判定 | 依据 |
|---|---|---|
| F8 非空题库删除 → 40924 | **PASS** | A3 [实测] |
| F8 force → 级联软删题目、无孤儿 | **PASS** | A5 + A5b/A6 [实测+只读DB] |
| F8 空题库正常删（不误拦） | **PASS** | A8 [实测] |
| F9 含模块班次删除 → 40908 | **PASS** | B2 [实测] |
| F9 force + 模块有课次 → **仍拒绝**、绝不孤儿化 | **PASS** | B3 + B4 混合场景 [实测+只读DB] |
| F9 全零课次才级联删模块 + 软删班次 | **PASS** | B5 [实测+只读DB] |
| F10① `/media` 缺失文件 = 纯文本 404 | **PASS** | C1 [实测] |
| 正常 CRUD 零误伤 | **PASS** | D1–D12 [实测] |
| 保护码语义用对（40924=题库 / 40908=班次&模块） | **PASS** | A3/B2/B3/B4/B6b [实测] |
| **F8 `force` 声称"仅 ADMIN"但未做角色门（F9 有门）** | **FINDING(F-1)** | X1/X2 对照 [实测] |
| 库中存在 3 条**先于本轮**的孤儿题（非本轮产生） | **FINDING(F-2)** | A6 归因 [实测+只读DB] |

> 编排者关注的两条重点——**force 级联不孤儿化**、**保护码语义**、**正常流程零误伤**——均 PASS，且用只读 DB 落库态而不仅是 HTTP 码交叉验证。

## 2. PART C — F10① `/media` 缺失文件 404 语义

| # | 操作 | 实际响应 | 是否符合语义 | 误伤 |
|---|---|---|---|---|
| C1 | `GET /media/videos/NOPE_20260915_184725_128813.mp4` | **404**，`content-type: text/plain; charset=utf-8`，body 恰为 `404 Not Found`（13 字节） | ✅ 是纯文本，**不是** JSON 响应壳 | 无 |
| C2 | `GET /api/admin/courses/cohorts/999999999`（对照组） | **404**，`application/json`，`{"code":"40400","message":"班次不存在：999999999","data":null}` | ✅ API 仍走统一 JSON 壳，未被子类误伤 | 无 |
| C3 | `GET /media/videos/VID-20260915-0FA68A1D.mp4`（正对照） | **200**，`video/mp4`，153083 字节 | ✅ 真实文件正常服务，404 分支未吞掉 200 分支 | 无 |

**边界加固实测（[实测]）**：`/media/`、`/media/videos`、`/media/videos/`（目录请求）均 → 文本 404（**无目录列举**）；
`/media/%2e%2e%2f.env`、`/media/..%2F.env`、`--path-as-is /media/videos/../../.env` 均 → 文本 404（**未穿越出 media 根、未泄露 `.env`**）。

**[代码佐证]** `app/main.py:245-261`：`_MediaStaticFiles(StaticFiles)` 重写 `get_response`，仅捕获 `starlette.HTTPException 404` → 返回 `PlainTextResponse("404 Not Found")`；非 404 原样抛出。这解释了为何 C2 的 API 404 不受影响。

## 3. PART A — F8 题库删除保护（40924）

| # | 操作序列 | 实际响应码 + 响应体（关键字段） | 符合保护语义 | 误伤 |
|---|---|---|---|---|
| A1 | `POST /api/admin/questions/banks`（institution=1, category=1） | **201** `data.id=461, yn=1` | ✅ | 无 |
| A2.1–3 | `POST /api/admin/questions/questions` ×3 | **201 / 201 / 201** `ids=[10551,10552,10553]` | ✅ | 无 |
| A3 | `DELETE /api/admin/questions/banks/461`（无 force） | **HTTP 409**，`{"code":"40924","message":"题库内仍有 3 道有效题目，无法删除（确需连同题目一并删除请加 force=true）","data":null}` | ✅ 非空**不给删**；提示语明确告知可 force | 无 |
| A4a | `GET /banks/461`（被拒后） | **200**，`yn=1` | ✅ 未被静默删除 | 无 |
| A4b | `GET /banks/461/questions`（被拒后） | **200**，`total=3` 全 `yn=1` | ✅ 题目**零静默级联** | 无 |
| A4c | 只读 `SELECT yn FROM question_bank / question` | bank `yn=1`；3 题 `yn=1` | ✅ 与 HTTP 一致，非"壳绿" | 无 |
| A5 | `DELETE /banks/461?force=true` | **200**，`{"deleted":true,"id":461,"forced":true,"questions_removed":3}` | ✅ force 放行并**报告级联数量** | 无 |
| A5b | 只读 SELECT（force 后） | bank `yn=0`；3 题**全部 `yn=0`** | ✅ **软删（可恢复）、非物理删**，→ 无孤儿 | 无 |
| A6 | 只读 `SELECT COUNT(*) question q JOIN bank b ON q.yn=1 AND b.yn=0` | **3**（但**非本轮产生**，见 F-2 归因） | ⚠️ 历史遗留，见 §5 F-2 | 无 |
| A7 | `POST /banks`（新空库，code=BANK2） | **201** `data.id=462, yn=1` | ✅ | 无 |
| A8 | `DELETE /banks/462`（空库、无 force） | **200**，`{"forced":false,"questions_removed":0}` | ✅ **空库不误拦**（`forced:false` 说明未走 force 分支） | 无 |
| A9 | `GET /banks/462` | **404** `{"code":"40400","message":"题库不存在：462"}` | ✅ 软删后详情不可见 | 无 |

**[代码佐证]** `question_admin/service.py:117-137`：`count_active_by_bank()`（`yn=1` 计数，`question_repo.py:117-121`）> 0 且非 force → `ConflictError(code=BANK_IN_USE=40924)`；`question_count>0` 时才 `soft_delete_all_by_bank()`（`UPDATE question SET yn=0 WHERE bank_id=%s AND yn=1`），随后 `soft_delete` 题库。
`error_codes.py:135` `BANK_IN_USE="40924"`；`exceptions.py:86-89` `ConflictError → http_status=409`。

## 4. PART B — F9 班次删除保护（40908）

拓扑：系列 `series` → 班次 `series_cohort`(有 `yn`) → 模块 `series_cohort_course`(无 `yn`，物理删) → 课次 `series_cohort_session`(无 `yn`，物理删)。

### B1 空班次（无模块）→ 正常删
| # | 操作 | 响应 | 判定 |
|---|---|---|---|
| B1 | `DELETE /cohorts/7934`（0 模块） | **200** `"班次已删除"` | ✅ 空班次不误拦 |
| B1b | `GET /cohorts/7934` | **200**，`yn=0` | ✅ 软删生效（详情端点按设计不限 yn，见 §5 F-3 说明，非缺陷） |

### B2 含模块班次（无 force）→ 40908
| # | 操作 | 响应 | 判定 |
|---|---|---|---|
| B2 | `DELETE /cohorts/7935`（1 模块） | **HTTP 409**，`{"code":"40908","message":"班次仍被 1 个模块引用，无法删除（确需连同模块一并删除请加 force=true，且仅 ADMIN 可执行）"}` | ✅ |
| B2b | `GET /cohorts/7935` | **200** `yn=1` | ✅ 未被静默删 |
| B2c | `GET /modules/23667` | **200** | ✅ 模块未被静默级联删 |

### B3 ⭐ force + 模块有课次 → 仍 40908（关键安全不变量）
| # | 操作 | 响应 | 判定 |
|---|---|---|---|
| B3 | `DELETE /cohorts/7935?force=true`（模块下有 1 课次） | **HTTP 409**，`{"code":"40908","message":"模块 23667 仍被 1 个课次引用，无法删除；请先删除该模块下的课次"}` | ✅ **force 也不放行** |
| B3b | `GET /cohorts/7935/sessions` | **200**，课次 `id=205785` 仍在 | ✅ 课次**未被孤儿化** |
| B3c | `GET /modules/23667` | **200** | ✅ 模块仍在 |
| B3d | `GET /cohorts/7935` | **200**，`yn=1` | ✅ 班次仍在 |
| B3e | 只读 SELECT | `session{id:205785, fk:23667}` 行在；`module{23667}` 行在；`cohort yn=1` | ✅ **HTTP 与落库态双证，无孤儿** |

### B4 ⭐ 混合场景：1 个零课次模块 + 1 个有课次模块 → 必须**整体拒绝**（不得部分删除）
| # | 操作 | 响应 | 判定 |
|---|---|---|---|
| B4 | `DELETE /cohorts/7936?force=true`（模块 23668 零课次、23669 有课次） | **HTTP 409 40908**，`"模块 23669 仍被 1 个课次引用…"` | ✅ 整体拒绝 |
| B4b | 只读 SELECT | 零课次模块 `23668` **仍存在**；有课次模块 `23669` 在；`cohort yn=1` | ✅ **零课次模块未被提前删掉 → 无"部分删除"半成品状态** |
| B4c | `GET /modules/23668` | **200** | ✅ 与只读 DB 一致 |

**[代码佐证]** `course_admin/service.py:295-305` 是**两阶段**实现：先 `for m in modules: count_references()` 全部校验，**任一 >0 即 raise**；校验全过后才第二个 `for` 逐个 `hard_delete`。B4 正是对"两阶段"的实证——若误写成单阶段（边查边删），23668 会被先删掉。

### B5 全零课次 → force 级联删模块 + 软删班次
| # | 操作 | 响应 | 判定 |
|---|---|---|---|
| B5a | `DELETE /sessions/205786` | **200** | ✅ 课次无子引用可物理删 |
| B5b | `DELETE /cohorts/7936?force=true` | **200** `"班次已删除"` | ✅ 全零课次才放行 |
| B5c/B5d | `GET /modules/23668`、`/modules/23669` | **404 ×2** `40400` | ✅ 模块**物理删**（与设计一致） |
| B5e | `GET /cohorts/7936` | **200**，`yn=0`，`updated_at` 已刷新 | ✅ 班次**软删**（模块硬删、班次软删，与语义声明一致） |
| B5f | 只读 SELECT | 残留模块 `[]`；`cohort yn=0`；课次残留 `[]` | ✅ **无孤儿、无残留** |

### B6/B7 角色门与恢复路径
| # | 操作 | 响应 | 判定 |
|---|---|---|---|
| B6 | `mgr01test` `DELETE /cohorts/7935?force=true` | **HTTP 403** `{"code":"40300","message":"强制删除操作仅 ADMIN 可执行"}` | ✅ force 角色门有效 |
| B6b | `mgr01test` `DELETE /cohorts/7935`（无 force） | **HTTP 409 40908** | ✅ manager 同样受保护，不能绕过 |
| B7a | `DELETE /sessions/205785` | **200** | ✅ |
| B7b | `DELETE /cohorts/7935?force=true`（清课次后） | **200** | ✅ 阻断是"可恢复的"——删课次后即可正常删除，保护不造成死锁 |

**[代码佐证]** `course_admin/router.py:133-134`：`if force and me.role != UserRole.ADMIN: raise PermissionDeniedError`；`service.py:286-309` 校验顺序为"模块存在→非 force 拒绝→force 时逐模块查课次"。`error_codes.py:127` `SERIES_IN_USE="40908"`（题型复用于"系列/模块/课次被引用"三处，语义一致）。

## 5. 发现项（Findings）

### F-1【MEDIUM】F8 题库 `force` 声称"仅 ADMIN"，但代码**未做角色门**；F9 有门 → 域间不对称

| # | 操作 | 响应 | 结论 |
|---|---|---|---|
| X1 | `mgr01test` `DELETE /api/admin/questions/banks/464?force=true`（**非空**库，含 1 题） | **HTTP 200** `{"deleted":true,"forced":true,"questions_removed":1}` | ❌ manager **成功** force 删除 |
| X3 | 复核 `GET /banks/464` | **404** `题库不存在：464` | ❌ **确认实际生效**（不是壳绿） |
| X2 | `mgr01test` `DELETE /api/admin/courses/cohorts/{id}?force=true`（对照） | **HTTP 403** `40300` | ✅ 同一位 manager 在班次域被正确拒绝 |

- **[代码佐证]** `question_admin/router.py:94-105`：`force: bool = Query(False, description="…（需谨慎，仅 ADMIN）")`，但**函数签名无 `me: CurrentUser`，无 role 判断**；而 `course_admin/router.py:128-136` 的班次删除**显式**做了 `me.role != UserRole.ADMIN → 403`。
  因此 bank 的 `force` 权限**只写在参数描述里，未落到执行路径**（文档与实现不一致）。
- **[推演]** 影响面：`manager` 角色可对**任意非空题库**执行"级联软删全部题目 + 软删题库"。因为是 `yn=0` 软删（可恢复）、且不产生孤儿（已实测 A5b），**不构成数据丢失**，但属于**越权**（跨过了 `course_admin` 域已确立的 ADMIN-only 边界），且违反接口自身的契约描述。
- **建议**（不属本次任务改动）：给 `delete_bank` 增加与 F9 对齐的 `me: CurrentUser = Depends(get_current_user)` + `if force and me.role != ADMIN: 403`；或反过来把 F9 的门放宽，二者择一统一。
- **误伤判定**：不构成误伤（是"漏拦"，不是"错拦"）。

### F-2【LOW / 数据卫生】库中存在 3 条**先于本轮**的孤儿题，非本轮 F8 产生

- **[实测]** A6 全库查询命中 3 条 `question.yn=1` 且 `question_bank.yn=0` 的记录：
  - `id=10537, 10538`（`question_code=LIANQ-IMP-444227-*`，`bank_id=452` `LIANQ-BANK-444227`，`created_at=2026-09-15 11:57:45`）
  - `id=10539`（`question_code=UI-IMP-777222-1`，`bank_id=453` `UI-BANK-777222`，`created_at=2026-09-15 12:21:10`）
- **[实测] 归因（关键：与本轮无关）**：这 3 条的 `id`（10537–10539）**小于**本轮创建的题目 `id`（10551–10554），`created_at`（11:57/12:21）**早于**本轮测试窗口（18:47–19:03），且 `question_code` 前缀为 `LIANQ-`/`UI-`（他轮联调/UI 测试）而非本轮 `BLIND7_`。
- **[实测] 本轮自身零孤儿**：本轮 force 删库后 3 题全部 `yn=0`；本轮结束后 `SELECT … question_code LIKE 'BLIND7_%' AND yn=1` = **0 行**。
- **[推演]** 这 3 条的成因有两种可能，本报告**不判定**（无该时点证据）：①银行 452/453 的软删发生在 F8 守卫上线之前；②由**绕过 API 的直连 SQL**清理产生（联调脚本自清常见做法），使级联分支未执行。可注意：`bank.updated_at=11:58:33` 与 `question.updated_at=11:58:33` 同秒，倾向于"同一次批量操作"。
- **意义**：F8 保护"面向未来"（已实测 A3/A5 有效），但**库内历史数据并未被回填修复**。若下游报表/组卷按 `question.yn=1` 统计，这 3 条仍会被算作有效题目却挂在已删题库上。
- **建议**：属数据治理项，非本次改动范围；如需要，可用一次性只读排查 + 人工确认后清账。

### F-3【INFO / 非缺陷】`cohort` 详情在软删后仍返回 200 + `yn=0`，与 `bank` 软删后 404 不一致——但**是设计意图**

- **[实测]** B1b/B5e：`GET /cohorts/{id}` 在 `yn=0` 后仍 **200**（带 `yn:0`）；A9：`GET /banks/{id}` 在 `yn=0` 后 **404**。
- **[代码佐证]** `cohort_repo.py:14-19` 注释明写"按 ID 查班次（**不限 yn，管理端可见全部**）"；`list_by_series` 默认 `yn_only=True`（`cohort_repo.py:28-34`）保证列表仍只出 `yn=1`。`bank_repo.get_by_id` 则在 service 层 `if not row or row.get("yn")==0: raise NotFoundError`。
- **判定**：**非缺陷、非误伤**，是两域不同的可见性约定（班次为"回收站可见"设计）。仅登记为跨域一致性差异，供前端/QA 知道"删除后详情行为不同"。
- **附带确认**：`series count_references` 把 `yn=0` 的班次也算引用（`series_repo.py:156-175` 注释："`series_cohort` 即使 `yn=0` 仍持有指向 `series` 的外键"）→ 因此软删班次后 `series?hard=true` 仍 **409**。**[实测]** 本轮清理时 12 个系列 hard 删全部 409。这是**有意保守**（避免 FK 冲突/静默放行），**不算误伤**。

### F-4【INFO】`DELETE /cohorts/{id}/sessions/{id}` 路由 summary 与实现不符

- **[代码佐证]** `course_admin/router.py:209` summary 写"管理端·**软删**课次（yn=0）"，但 `service.py:428-443` `delete_session` 实为**物理 DELETE**（`_session_repo.hard_delete`，表 `series_cohort_session` 无 `yn` 列）。
- **[实测]** B5a/B7a 返回 `{"code":0,"message":"课次已删除"}`；随后只读 SELECT 确认课次行**已消失**（`session残留=[]`）→ 物理删，与 summary 不一致。
- **判定**：仅文档性瑕疵（OpenAPI 描述会误导调用方以为可恢复）。不影响保护语义。

## 6. 误伤回归（PART D）

| # | 操作 | 响应 | 误伤判定 |
|---|---|---|---|
| D1 | `PATCH /courses/series/2829` 改名 | **200**，字段已更新 | 无误伤 |
| D2 | `PATCH /courses/cohorts/7937` 改名 | **200** | 无误伤 |
| D3 | `PATCH /courses/modules/23670` 改名 | **200** | 无误伤 |
| D4 | `PATCH /courses/sessions/205787` 改名 | **200** | 无误伤 |
| D5 | `POST /questions/banks` 建库 | **201** | 无误伤 |
| D6 | `POST /questions/questions` 传题 | **201** | 无误伤 |
| D7 | `PATCH /questions/questions/10554` 改题 | **200** | 无误伤 |
| D8 | `DELETE /questions/questions/10554` 单题软删 | **200** | 无误伤（F8 只管"删库"，不拦单题删） |
| — | 只读确认单题软删后库内有效题数 | **0**（`yn=1` 计数） | — |
| D9 | `DELETE /questions/banks/463`（库内已无有效题，**无 force**） | **200**，`forced:false, questions_removed:0` | ✅ **保护逻辑精确按 `yn=1` 计数，不误拦**（若守卫误用 `COUNT(*)` 全表计数，此处会错误 40924） |
| D10 | `GET /courses/series?page=1&page_size=3` | **200** | 无误伤 |
| D11 | `GET /questions/banks?page=1&page_size=3` | **200** | 无误伤 |
| D12 | `GET /questions/types` | **200** | 无误伤 |

**结论：正常 CRUD（建课程/传题/排班次/改名/列表）零误伤。** 保护逻辑没有拦下任何合法操作，包括"D9 清空后再删库"这一最容易被误拦的边界。

## 7. 测试数据自清（自建自清证据）

本轮创建：banks `[461,462,463]`，series `[2826–2829]`，cohorts `[7934–7937]`，modules `[23667–23670]`，sessions `[205785–205787]`，questions `[10551–10554]`。

清理后**终态核验（只读 SELECT）**：

```
BLIND7_% 前缀范围内：
  bank     yn=1 → 0 行
  question yn=1 → 0 行
  cohort   yn=1 → 0 行
  module   残留  → 0 行
  session  残留  → 0 行
  series   sale_status<>'off_sale' → [] (空)
```

- **说明**：题库/题目/班次按 API 语义是**软删**，故 `yn=0` 的物理行按设计保留（可恢复），这是接口契约行为而非清理不彻底；**活跃（`yn=1`）残留为 0**。
- 模块/课次为物理删，残留 **0**。
- 清理过程中还额外获得一条正向证据：`DELETE /modules/23666` 因该模块仍有 1 个课次而返回 **409**（与 `delete_module` 守卫一致，`service.py:362-377`），删课次后即 200。**这同时证明"模块独立删除端点"也受同一保护覆盖。**

## 8. 环境事件（必须登记，影响证据链连续性）

- **首轮 harness 在 D9 步骤被中断**：`httpx.ReadError: [WinError 10054] 远程主机强迫关闭了一个现有的连接`，随后 `curl /docs` → `backend=000`，**后端进程已消失**。
- **[实测] 归因（非本轮测试造成）**：`edu-agent/logs/app.log` 末尾显示同一时段有**第三方 `/api/chat` 请求**在处理（`sixnode.route`、`BGE-M3` 加载、`Milvus 检索超时（>8.0s）`、`retrieval-profile pipeline total=15245ms`），属**并发会话/agent 的流量**；本轮 harness 全程只打 `/api/admin/**` 与 `/media/**`，不触碰 chat。判定为**外部原因导致的后端进程终止**。
- **处置**：以 `MYSQL_HOST=127.0.0.1` 重启后端（`uvicorn app.main:app --host 127.0.0.1 --port 8000`，后台常驻），`/health` 与 `/docs` 恢复 200 后**整轮重跑**。
- **本报告所有表格数据均来自重跑后的单一完整轮次**（`run=185833`，exit=0，18:58–19:00），**无跨轮拼接**。首轮数据仅用于 F-2 的时序归因与 §7 的一次 409 正向证据。

## 9. 下一位同事最该知道的 3 件事

1. **F9 的 `force` 是"两阶段校验"，不是"边查边删"——这是它最值钱的实现细节。** `service.py:295-305` 先把班次下**所有**模块的课次引用校验一遍，任一 >0 就整体 `40908`，全部通过才开始删。我用"1 个零课次模块 + 1 个有课次模块"的混合班次实测（B4）：force 被整体拒绝，且**零课次模块事后仍存在**（只读 DB `[{'id': 23668}]`）。**任何重构都不能把它改成单阶段循环**，否则会产生"模块删了一半"的半成品状态——这是本任务最关键的安全不变量。

2. **F8 和 F9 的 `force` 权限门不对齐：班次有 ADMIN 门，题库只有一句注释。** `manager` 实测可以 `?force=true` **成功**删掉非空题库（X1 → 200 + `questions_removed:1`，X3 复核 404），而同一账号删班次被 403 拦下（X2）。`question_admin/router.py:94-105` 的 `force` 参数只有 `description="…仅 ADMIN"`，函数体里**没有 `me` 参数、没有角色判断**。要动这块代码前请先确认这是"待补的门"还是"有意放开"，别顺手把 F9 的门也拆了。

3. **库里的 `yn` 语义不是全局统一的，做统计/清理前必须逐表确认。** 本轮踩到三处：①`series` 表**没有 `yn` 列**（软删靠 `sale_status='off_sale'`）；②`series_cohort_course`/`series_cohort_session` **没有 `yn` 列**（删除即物理 DELETE，`hard_delete` 会 `DELETE FROM series_cohort_session WHERE series_cohort_course_id=%s`）；③`cohort_repo.get_by_id` **有意不限 `yn`**（注释："管理端可见全部"），所以软删班次后详情仍 200 带 `yn:0`，而软删题库后详情是 404。另外 `series.count_references` **故意把 `yn=0` 的班次也计入引用**，因此软删班次后 `series?hard=true` 仍会 409——这是防 FK 冲突的有意保守，**不是 bug，别当误伤去"修"**。

## 10. 复现附录（编排者逐断言复跑用）

前置：后端在 `127.0.0.1:8000` 监听；`export TOK=$(curl -s --noproxy '*' -X POST http://127.0.0.1:8000/api/auth/login -H 'Content-Type: application/json' -d '{"account":"adm02test","password":"Test@123456"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")`
（`MGR` 同上换成 `mgr01test`。**注意**：`HTTP_PROXY` 会把 loopback 请求吞成 502，务必带 `--noproxy '*'`。）

```bash
# ── F10① /media 404 ──
curl -s --noproxy '*' -i http://127.0.0.1:8000/media/videos/NOPE_x.mp4            # 期望 404 + text/plain + body "404 Not Found"
curl -s --noproxy '*' -i http://127.0.0.1:8000/api/admin/courses/cohorts/999999999 # 对照：404 + application/json {"code":"40400"}

# ── F8 建库传题 → 非空拒删 → force 级联 ──
BID=$(curl -s --noproxy '*' -X POST http://127.0.0.1:8000/api/admin/questions/banks -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"institution_id":1,"category_id":1,"bank_code":"RB1_'"$RANDOM"'","bank_name":"复验库"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
curl -s --noproxy '*' -X POST http://127.0.0.1:8000/api/admin/questions/questions -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' -d '{"bank_id":'"$BID"',"question_code":"RQ1","question_type_id":1,"stem":"题","answer_text":"A"}' 
curl -s --noproxy '*' -X DELETE "http://127.0.0.1:8000/api/admin/questions/banks/$BID" -H "Authorization: Bearer $TOK"
   # 期望 409 {"code":"40924"}
curl -s --noproxy '*' -X DELETE "http://127.0.0.1:8000/api/admin/questions/banks/$BID?force=true" -H "Authorization: Bearer $TOK"
   # 期望 200 {"forced":true,"questions_removed":1}

# ── F1 权限不对称（本报告 F-1）──
# 用上面同样手法建一个非空库，然后改 $MGR 提交：
curl -s --noproxy '*' -X DELETE "http://127.0.0.1:8000/api/admin/questions/banks/$BID?force=true" -H "Authorization: Bearer $MGR"
   # 实测 200（题库域未拦 manager）—— 对照班次域：
curl -s --noproxy '*' -X DELETE "http://127.0.0.1:8000/api/admin/courses/cohorts/$CID?force=true" -H "Authorization: Bearer $MGR"
   # 实测 403 {"code":"40300"}

# ── F9 关键不变量：混合模块 force 必须整体拒绝 ──
# 建 series → cohort → module A(stage1, 零课次) + module B(stage2, 有课次)，然后：
curl -s --noproxy '*' -X DELETE "http://127.0.0.1:8000/api/admin/courses/cohorts/$CID?force=true" -H "Authorization: Bearer $TOK"
   # 期望 409 {"code":"40908","message":"模块 … 仍被 1 个课次引用…"}
curl -s --noproxy '*' http://127.0.0.1:8000/api/admin/courses/modules/$MOD_A -H "Authorization: Bearer $TOK"
   # 期望 200（零课次模块未被提前删除 = 无部分删除）

# ── 落库态（只读，禁写）──
# 在后端工作副本目录下执行（PYTHONPATH=. ），仅 SELECT：
#   SELECT yn FROM question_bank WHERE id=$BID;
#   SELECT id,yn FROM `question` WHERE bank_id=$BID;
#   SELECT id FROM series_cohort_course WHERE cohort_id=$CID;
#   SELECT yn FROM series_cohort WHERE id=$CID;
```

**清理提醒**：`QuestionAdmin`/`Cohort`/`Bank` 删除皆为软删，复跑后会留 `yn=0` 行；`series` 需 `DELETE /courses/series/{id}`（软删 `off_sale`）才从活跃列表消失，`?hard=true` 在仍有班次（**含 `yn=0`**）引用时会 409。
