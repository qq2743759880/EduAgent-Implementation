# task20-completion-report · 后端 enrollment 报名域（契约⑪ 前段）

> 类型：backend + database ｜ 阶段：P4/W2 ｜ 执行：TraeCode 手动调度（dev-standard 8 阶段）
> 契约依据：`plans/tasks/task20-enrollment.md` + `api-request.md §1` + 前端 `enrollments.ts`（EnrolledCohort 权威）
> 状态：**待编排者验收**（未经验收不开始 task21）

---

## 交付范围

- **4 只读端点**（对齐前端 `/api/enrollments/me/cohorts`，解锁 task47 /my-courses）：
  - GET `/api/enrollments/me/cohorts?status=&series_id=` 我的班次列表（进度聚合 EnrolledCohort[]）
  - GET `/api/enrollments/me/cohorts/{cohort_id}` 报名详情
  - GET `/api/enrollments/me/cohorts/{cohort_id}/progress` 进度快照（模块/课次明细）
  - GET `/api/enrollments/me/cohorts/{cohort_id}/status` 报名状态查询
- **满班并发控制**：由既有下单路径（task17 `occupy_seat` 条件更新）承载，DB 层脚本并发攻防实证（GWT①）
- **进度聚合真实（无 MOCK）**：series_cohort_course（模块）+ series_cohort_session（课次）+ session_homework_submission（提交表判已完）
- **enroll_status 枚举**：`active/completed/cancelled/refunded`；refunded 自动进入「已退款」（含退款单聚合）

## 判定（用户裁定）
student_cohort_rel.order_item_id NOT NULL+FK 使手动报名无法独立创建 enrollment，且前端只消费 GET /me/cohorts → **只做读端点**；满班控制由下单路径承载（GWT① 以脚本实证）。

## 新增/修改文件

| 文件 | 说明 |
|------|------|
| `edu-agent/app/domains/enrollment/{schemas,repository,service,router,__init__}.py` | enrollment 域（只读 4 端点） |
| `edu-agent/app/main.py` | 注册 enrollment_router |
| `edu-agent/tests/test_contract_task20.py` | task20 契约测试（in-process ASGI） |
| `edu-agent/scripts/_probe_task20.py` / `_verify_task20_full.py` | 数据探测 / 满班并发攻防证据 |

---

## 验收标准逐条对照（Given/When/Then）

### GWT① 满班并发控制（条件更新 + 受影响行数）
> Given 班次余位 1，When 2 个并发报名请求，Then 仅 1 成功，另一返回 409"班次已满"。

**机制**：`UPDATE series_cohort SET current_student_count=current_student_count+1 WHERE id=%s AND current_student_count < max_student_count`（受影响行数 0 = 满班）。与 task17 `occupy_seat` 逐字同构，下单路径对满班返回 `40920`。

**实测（DB 层 8 并发攻防，scripts/_verify_task20_full.py）**：
```
[GWT①] 余位1 8 并发 → 成功=1, 满班拦截=7（期望 1/7）
[GWT①] 最终 current=50, max=50（期望 current==max 不再放行）
[GWT①] 已恢复 current_student_count 原值
  满班并发控制（条件更新+受影响行数）[OK]
```
断言：成功=1、current==max（无超卖）、数据恢复。

### GWT② /me/cohorts?status=active + 进度聚合 + refunded tab
> Given 报名 active 用户，When 请求 /me/cohorts?status=active，Then 返回班次 + 模块/课次完成率聚合（供前端进度条），退款后 enroll_status=refunded 自动移入"已退款"tab。

**实测**：`test_list_active_with_progress` PASS——active 列表含夹具班次，`session_total>=1`/`module_total>=1`/`overall_ratio` 数值、`enrollment_id`/`series_id` 正确。`refunded` 态经 `enroll_status=='refunded'` 过滤 + 退款单聚合（refund_no/refund_amount/refunded_at）自动入「已退款」。

### GWT③ 支付回调触发报名 → 记录正确 + 余位递减
**机制**：task18 `settle_payment` 回调成功单事务已写 student_cohort_rel(active) + order paid + 券 used；本域只读正确展示该记录（报名记录/进度/状态）。task18 已验证三表原子一致，本域不做重复写。

---

## 进度聚合真实性（R3 红线，修复后）

**真实来源**：session_total/module_total = series_cohort_course + series_cohort_session（排除 cancelled）；session_done = session_homework_submission `submit_status='submitted'` 该生已提交 session 数；module_done = 「模块内全部 session 均已提交」的模块数。

**P1 修复（独立子代理 R3）**：列表原用 `COUNT(DISTINCT ccc.id)` 判 module_done（有 ≥1 提交即算完成）→ 高估 overall。改为**逐模块全 session 提交判定**（SQL per-module 比较 module_sessions==module_done_sessions），与进度快照语义一致。

---

## 契约测试结果

| 套件 | 结果 |
|------|------|
| `tests/test_contract_task20.py`（in-process ASGI） | **7/7 通过** |
| GWT① 满班并发脚本 | 成功=1/拦截=7、current==max、数据恢复 |
| 语法诊断（GetDiagnostics） | enrollment 全域 + main 均 0 错误 |

> ⚠️ 环境说明：外部存储机（192.168.85.101）网络不可用，uvicorn 起服卡在 MinIO/Neo4j 初始化；task20 测试改用 **in-process httpx ASGITransport**（不跑 lifespan），绕过起服挂起。task17/18/19 的 HTTP 契约套件依赖 8003 起服，在环境恢复前无法在线复跑（此前已验）；本域改动不影响其代码。

---

## 验证命令
```bash
# task20 契约（in-process）
.venv\Scripts\python -m pytest tests/test_contract_task20.py -v
# 满班并发攻防（DB 层）
.venv\Scripts\python scripts\_verify_task20_full.py
```

## 关键经验留痕
- **列对照修正（task12/20 教训）**：student_cohort_rel **无 yn 列**（状态仅 enroll_status）；series_cohort_course **无 series_id**（只有 cohort_id）。初版 SQL 引用了这两个不存在的列，probe 运行即暴露 1054，已修复。
- **外部存储机不可用**：起服挂起 → 测试改 in-process ASGI，规避 lifespan 中 Milvus/MinIO/Neo4j 连接超时。
- **进度聚合真实**：module_done 必须与快照语义一致（全 session 提交才算完成），否则整体完成度高估。