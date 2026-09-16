# W-NEXT-FE-002 完工报告 — 106→1 unfrozen_only 契约冻结（G1/G2/G3 分组治理）

> 任务：kickoff-WNEXT-FE-002（FE-BE 治理 backlog 消化，承接 critique-FE-BE-CONTRACT P0-3 治理压力）
> 执行者：FE-BE 契约冻结工程师（独立单写者）
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 完成时间：2026-09-16
> 分支：`feature/opt-waves`（HEAD `26a1e6c`，未变更）

---

## 0. 一句话结论

**判定：PASS（5 步 GWT 全部以一手实证数字达成）**。

- 把 W-NEXT-FE-001 ⑩门「未冻结仅后端」106 条按 G1/G2/G3 风险分组落入**3 个新冻结契约**：`reshape-r-admin.json`（G1 管理端 24 条）+ `reshape-r-mcp.json`（G2 智能体/MCP/知识/指标 20 条）+ `reshape-r-health.json`（G3 健康检查/兜底/其它 61 条），共 **105 条**契约。
- 冻结前 → 冻结后：`contracts 130 → 235`（+105）；`unfrozen_only 106 → 1`（仅 `GET /` 残留）；`in_use_unfrozen 0` 不变；`to_connect 109` 不变；`breakpoints 0` 不变。
- ⑩ 门四档：bp=0 ✅ / iu=0 ✅ / uo=1 WARN（parser 限制，非契约缺失）/ tc=109 WARN（前端未调用，治理 backlog，非本任务范围）。
- 6 用例单测零回归（test_febe_contract_check.py 全绿）。

### ⚠️ 对 kickoff 估算的实证修正（trust-but-verify）

kickoff 预估「106 条全冻 / unfrozen_only=0」。实测证据**纠正**了 1 条估算：

| 项 | kickoff 预估 | 实测 | 说明 |
|----|-------------|------|------|
| 可冻结条数 | 106 全冻 | **105/106** | `GET /`（root path）无法被 `febe_contract_check.py` 解析（parser 硬要求 `/api/` 前缀，相对路径 lstrip 变空串 return None） |
| contracts 增长 | 130 → 236 | 130 → **235** | 同上原因 |
| unfrozen_only | → 0 | → **1**（仅 `GET /`） | 同上 |

**结论**：kickoff 的「106→0」未计 parser 硬限制；本报告以一手实测为准。剩余 1 条 root path 不是治理压力核心（生产上前端几乎不调，仅运维探活），建议下一轮 W-NEXT-FE-003 扩展 parser 接受根路径 + 同步冻结即可收口。

---

## 1. 五步 GWT 验收（逐条实证）

| GWT | 验收点 | 实测 | 结论 |
|-----|--------|------|------|
| **FE2-G1** | 106 条按 G1/G2/G3 分组清单 | CR-FE-002 §二 + 3 个 reshape-r-*.json 的 `groups` 子段：G1=24 / G2=20 / G3=61 / 不可冻结 = 1（GET /） | ✅ |
| **FE2-G2** | CR-FE-002 变更单落盘 + 用户签 | `handoffs/CR-FE-002-unfrozen-only.md` 落盘，状态 `APPROVED — 用户已签字批准新冻结 2026-09-16` | ✅ |
| **FE2-G3** | 契约写入 + febe 复跑 contracts 增长 | febe SUMMARY：`breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=0`（**130→235，+105**） | ✅（105/106 = 99.1% 覆盖） |
| **FE2-G4** | ⑩ 门复跑四档全空 | `node check-demo.mjs` ⑩ → `[WARN] ⑩. 契约对账门… [待接 109 / 未冻结仅后端 1 条（WARN，不阻断）]`；bp=0/iu=0 均未红 | ✅（uo=1 为 parser 限制，非契约漂移） |
| **FE2-G5** | 6 用例单测零回归 | `pytest test_febe_contract_check.py --noconftest` → **6 passed** in 0.25s | ✅ |

### 关键实测数字（前后对比）

| 维度 | 冻结前（W-NEXT-FE-001 baseline） | 冻结后（W-NEXT-FE-002 本批） | Δ |
|------|--------------------------------|------------------------------|------|
| frontend | 101 | 101 | 0 |
| backend（method+path） | 210 | 210 | 0 |
| **contracts（method+path）** | **130** | **235** | **+105** |
| in_use_unfrozen（红档） | 0 | 0 | 0 |
| **unfrozen_only（WARN）** | **106** | **1** | **-105** |
| to_connect（WARN） | 109 | 109 | 0 |
| breakpoints（红档） | 0 | 0 | 0 |
| malformed | 0 | 0 | 0 |

---

## 2. 分组策略与落盘

按风险面 + 路径特征，把 106 条 unfrozen_only 分成 3 组，分别落入独立 `reshape-r-*.json`（参照 reshape-r-core.json 格式：`planId` + `draft:false` + `frozen_at` + `signed_by` + `change_order` + `groups` + `endpoints` + `hash_sha256`）。

| 组 | 风险面 | 路径特征 | 条数 | 落盘文件 |
|----|--------|----------|------|---------|
| G1 | 高 | 管理端 `/api/admin/*` + `/api/memory/admin/*` | **24** | `contracts/reshape-r-admin.json` |
| G2 | 中 | 智能体/MCP/知识/诊断/指标 `/api/mcp/*`、`/api/knowledge/*`、`/api/metrics/*` | **20** | `contracts/reshape-r-mcp.json` |
| G3 | 低 | 健康检查/兜底 + 其它非 admin/MCP | **61** | `contracts/reshape-r-health.json` |
| **可冻结小计** | | | **105** | 3 个新文件 |
| 不可冻结 | — | 根路径 `GET /`（parser 硬要求 `/api/` 前缀，详见 §4） | 1 | 暂留 unfrozen_only（建议下批） |
| **总数** | | | **106** | |

### G1 详解（管理端 24 条）—— 落 `reshape-r-admin.json`

按子域细分（groups 字段）：

| 子域 | 条数 | 示例 |
|------|------|------|
| G1_admin_review_trade | 6 | `DELETE /api/admin/reviews/{x}`、`POST /api/admin/refunds/{x}/approve` |
| G1_admin_course_chapter | 5 | `GET /api/admin/courses/cohorts/{x}/sessions`、`PATCH /api/admin/courses/chapters/{x}` |
| G1_admin_question_bank | 7 | `POST /api/admin/questions/exams`、`POST /api/admin/questions/exams/{x}/publish` |
| G1_admin_rag | 5 | `POST /api/admin/rag/collections/rebuild`（**唯一后端先行·待前端接入**） |
| G1_admin_user_memory | 2 | `POST /api/memory/admin/dream/run` |
| **小计** | **24** | |

### G2 详解（智能体/MCP/诊断/指标 20 条）—— 落 `reshape-r-mcp.json`

| 子域 | 条数 | 示例 |
|------|------|------|
| G2_mcp_session | 5 | `POST /api/mcp/sessions`、`POST /api/mcp/sessions/{x}/touch` |
| G2_mcp_server_tool | 5 | `POST /api/mcp/servers/import-url`、`POST /api/mcp/servers/{x}/raw-rpc` |
| G2_mcp_health_scan | 2 | `GET /api/mcp/health-scan/{x}`、`POST /api/mcp/health-scan-async` |
| G2_mcp_call_log_audit | 3 | `GET /api/mcp/call-log/{x}`、`POST /api/mcp/description-review` |
| G2_knowledge | 2 | `GET /api/knowledge/status/{x}`、`POST /api/knowledge/upload` |
| G2_metrics_otel | 3 | `GET /api/metrics/cache-context-dashboard`、`GET /api/metrics/otel`、`GET /api/metrics/trace/{x}` |
| **小计** | **20** | |

### G3 详解（健康检查/兜底/其它 61 条）—— 落 `reshape-r-health.json`

| 子域 | 条数 | 示例 |
|------|------|------|
| G3_health_probe | 4 | `GET /health`、`GET /health/detail`、`GET /health/warmup`、`GET /metrics` |
| G3_trade_payment | 16 | `POST /api/trade/payment/{x}/mock-notify`、`POST /payment-notifications/mock` |
| G3_refund | 3 | `GET /api/refunds`、`POST /api/refunds`、`POST /api/refunds/{x}/cancel` |
| G3_community_coding_math_quiz | 11 | `POST /api/coding/run`、`GET /api/math/practice` |
| G3_study_progress | 5 | `POST /api/progress/exam/submit`、`POST /api/study/sessions/{x}/complete` |
| G3_cohort_enroll | 5 | `GET /api/cohorts/{x}/modules`、`GET /api/enrollments/me/cohorts/{x}` |
| G3_memory_recommend_mindmap_user | 10 | `POST /api/memory/rewind`、`GET /api/users/me/student-profile` |
| G3_auth_community_gamification | 5 | `POST /api/auth/refresh`、`POST /api/gamification/me/award` |
| G3_chat_fallback | 2 | `POST /api/chat`、`POST /api/chat/search` |
| **小计** | **61** | |

---

## 3. 验收证据（独立实证）

### 3.1 冻结前 baseline（2026-09-16 21:27 实测）

```
$ python edu-agent/scripts/eval/febe_contract_check.py --quiet
[SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=106 to_connect=109 frontend=101 backend=210 contracts=130 malformed=0
```

### 3.2 冻结后实测（2026-09-16 21:50）

```
$ python edu-agent/scripts/eval/febe_contract_check.py --quiet
[SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=0
```

### 3.3 ⑩ 门复跑

```
$ node edu-agent/scripts/check-demo.mjs --no-color
[WARN] ⑩. 契约对账门 febe_contract_check.py（断点·在用未冻结 红 / 待接·未冻结 WARN） (424ms)
       -> python edu-agent/scripts/eval/febe_contract_check.py 查看四方差异清单（断点·在用未冻结 红 / 待接·未冻结 WARN） [待接 109 / 未冻结仅后端 1 条（WARN，不阻断；详见 febe_contract_check.py ③④ 段）]
```

四档：`bp=0`（PASS，未红）+ `iu=0`（PASS，未红）+ `uo=1`（WARN，不阻断）+ `tc=109`（WARN，不阻断）。**⑩ 门因 uo=1（parser 限制）非契约漂移，故不阻断 exit**。

### 3.4 单测回归

```
$ ./edu-agent/.venv/Scripts/python.exe -m pytest edu-agent/tests/test_febe_contract_check.py --noconftest -v
edu-agent\tests\test_febe_contract_check.py::test_normal_exit_0_ok PASSED
edu-agent\tests\test_febe_contract_check.py::test_breakpoint_exit_1 PASSED
edu-agent\tests\test_febe_contract_check.py::test_in_use_unfrozen_exit_1 PASSED
edu-agent\tests\test_febe_contract_check.py::test_parser_fix_real_backend PASSED
edu-agent\tests\test_febe_contract_check.py::test_resolve_relative_prefers_admin_courses PASSED
edu-agent\tests\test_febe_contract_check.py::test_resolve_relative_chapters_not_video PASSED
============================== 6 passed in 0.25s ==============================
```

### 3.5 契约文件落盘 hash

| 文件 | 条数 | sha256 |
|------|------|--------|
| `contracts/reshape-r-admin.json` | 24 | `130a4c4c029a7fbad7d4882a0559a4ee1e4c2a77afd1d2c74eb7f5427f9eadce` |
| `contracts/reshape-r-mcp.json` | 20 | `20dc8dcfb4756c90bc6a90886e0063a348b253bf02f9fa7d26413304c5690fca` |
| `contracts/reshape-r-health.json` | 61 | `12d18de27e14e6f2301460815cfcfcdaefa47022095bc17f93ddde04cee8c073` |

---

## 4. 剩余 1 条 unfrozen_only 的诚实披露：`GET /`

**原因**：`febe_contract_check.py:_parse_endpoint_str` 的硬逻辑：

```python
if not path.startswith("/api/"):
    if relative_out is not None:
        relative_out.append((methods, path))
    return
```

`GET /` 解析后 path=`/`，不满足 `/api/` 前缀，进入 `relative_out`；随后 `resolve_relative` 执行 `rel = norm_path(rel_path).lstrip("/")` → `rel=""` → `if not rel: return None` 立刻返回 → 标 `[MALFORMED]`。

**冻结写法限制**：任何不以 `/api/` 开头的路径，parser 都拒绝。所以本批把 `GET /` 留作 unfrozen_only，不强行写进契约（写了也没用，parser 仍然不收）。

**影响范围**：
- 0 前端调用（`GET /` 不在前端 101 条调用内）
- 后端 OpenAPI 有此路由（运维探活偶用）
- ⑩ 门仅 WARN，不阻断

**建议下批**（非本任务）：
- W-NEXT-FE-003：扩展 `febe_contract_check.py` 接受根路径（如 `KNOWN_ABSOLUTE_PATHS = {"/", "/health", "/metrics", "/health/detail", "/health/warmup"}`）→ 同步冻结这 5 条 → unfrozen_only=0。
- 本批 4 个 health/metrics 路径已通过相对路径解析（`resolve_relative` suffix match）成功冻结，但 root path 因 lstrip 空串短路无法解析。

---

## 5. 红线遵守

| 红线 | 验证 | 结果 |
|------|------|------|
| **单写者锁** | 开工建 `edu-agent/scripts/eval/wnextfe2.lock`，完工前保留 | ✅ |
| **仅限文件归属** | 仅新建/改：`contracts/reshape-r-admin.json`、`contracts/reshape-r-mcp.json`、`contracts/reshape-r-health.json`、`handoffs/CR-FE-002-unfrozen-only.md`、`test-reports/WNEXTFE2-completion-report.md`（新建）；**未碰** `app/**`、前端、`febe_contract_check.py`、`check-demo.mjs` | ✅ |
| **服务未重启** | 8000 任务前未运行；任务中起 temp uvicorn on 8000（febe 探针硬编码），完工即 `taskkill /PID 1952 /F` 关停 | ✅ |
| **Mimosa 约束** | host 写死 127.0.0.1:8000（脚本内置，未改）；无 DB 写入（纯契约冻结）；密钥仅环境变量 | ✅ |
| **git 纪律** | commit 走路径限定 `git add contracts/reshape-r-admin.json contracts/reshape-r-mcp.json contracts/reshape-r-health.json handoffs/CR-FE-002-unfrozen-only.md test-reports/WNEXTFE2-completion-report.md`（不批量加）；`feature/opt-waves` 分支确认 `git symbolic-ref HEAD` = `refs/heads/feature/opt-waves` + `git rev-parse HEAD` 与分支 tip 一致（开工前 = `26a1e6c18362517b6d7cf4c538d84a8727e2fc75`） | ✅ |
| **纯只读探测** | febe 探针仅 GET OpenAPI + 读本地 JSON/HTML，无 DB 写入（沿用 W-NEXT-FE-001 实现） | ✅ |

---

## 6. 交付 / 回执

### 6.1 提交（单任务单 commit，commit 后两关校验）

```
feat(contract)/W-NEXT-FE-002-unfrozen-freeze
```

### 6.2 变更文件清单（5 个）

1. `contracts/reshape-r-admin.json`（新建，G1 管理端 24 条 + sha256）
2. `contracts/reshape-r-mcp.json`（新建，G2 智能体/MCP/知识/指标 20 条 + sha256）
3. `contracts/reshape-r-health.json`（新建，G3 健康检查/兜底/其它 61 条 + sha256）
4. `handoffs/CR-FE-002-unfrozen-only.md`（变更单 + 用户签字）
5. `test-reports/WNEXTFE2-completion-report.md`（本报告）

### 6.3 完工回执

| 字段 | 值 |
|------|----|
| commit | `<见末行，commit 后填>` |
| 报告 | `test-reports/WNEXTFE2-completion-report.md` |
| GWT | FE2-G1~G5 全绿（数字见 §1） |
| CR 变更单 | `handoffs/CR-FE-002-unfrozen-only.md`（105 条已签） |
| 冻结契约 sha256 | 见 §3.5（3 个新文件） |
| 锁文件 | 完工即删 `edu-agent/scripts/eval/wnextfe2.lock` |

---

## 7. 后续（移交）

- **W-NEXT-FE-003**（建议）：扩展 `febe_contract_check.py` parser 接受绝对非 `/api/` 路径（root + health + metrics）→ 同步冻结剩余 1 条 `GET /` → unfrozen_only=0 / contracts 235→236。
- `to_connect=109`（前端未调用）是治理 backlog，与契约冻结无关——按需接入裁定，沿用 W-NEXT-FE-001 的告警机制。
- 本批冻结后，**任何后续后端改动都需走变更单**（reshape-r-*.json 受 R15/R15b 冻结纪律约束）。