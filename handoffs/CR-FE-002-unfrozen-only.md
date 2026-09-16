# 变更单 CR-FE-002：补冻结 105 条 unfrozen_only 契约（W-NEXT-FE-002）

> 状态：**APPROVED — 用户已签字批准新冻结（2026-09-16）**
> 提出：FE-BE 契约冻结工程师（承接 W-NEXT-FE-001 ⑩门「未冻结仅后端」差集 + critique-FE-BE-CONTRACT P0-3 治理压力）
> 日期 2026-09-16
> 变更对象：新建 `contracts/reshape-r-admin.json`（G1 管理端 24 条）+ 新建 `contracts/reshape-r-mcp.json`（G2 智能体/MCP/诊断/指标 20 条）+ 新建 `contracts/reshape-r-health.json`（G3 健康检查/兜底路径 61 条）。共 3 个文件，**105 条契约**（1 条 `GET /` 因 parser 限制未计入，详见 §二注）。
> 依据：`test-reports/FE-BE-CONTRACT-completion-report.md`（baseline unfrozen_only=106）+ `test-reports/critique-FE-BE-CONTRACT.md` P0-3 治理压力建议 + 本批 `febe_contract_check.py` 复跑。
> 权限边界：本单**只补契约**（method+path 冻结面），不碰 `app/**`、前端、`febe_contract_check.py`、`check-demo.mjs`（W-NEXT-FE-001 领地已闭环）。本批 ⑩ 门仍 WARN——治理 backlog 全部消化，unfrozen_only 106 → 1（剩余 1 条 root path 见注）。

## 一、问题（为什么要改）

W-NEXT-CONTRACT-001 已冻 40 条 in_use_unfrozen，但 `unfrozen_only`（后端有、前端未用、契约无）仍有 106 条——这些是「**后端改了前端不知道**」的核心场景：

- W-NEXT-FE-001 已锁 ⑩ 门红档 = `in_use_unfrozen`，但 `unfrozen_only` 仅 WARN（治理 backlog）；
- 当前 backend=210 / frontend=101 / contracts=130 / unfrozen_only=106 / to_connect=109 / in_use_unfrozen=0；
- 106 条中含 admin 管理端（30+ 条，权限变更可影响前端表单）、智能体/MCP（25 条，模型可能触发但前端未调）、交易/支付（13 条，mock/payment 是 P0 安全面）、健康检查（5 条，运维可见但缺契约）。

本批把这 106 条按风险分组落入冻结集合，unfrozen_only 由 106 → 1（仅 root path 因 parser 限制无法纳入），⑩ 门四档仅余 to_connect WARN（前端未调用 = 正常 backlog，非契约问题）。**to_connect=109 仍保留**（这是前端未调用但后端有的——非契约问题，不在 W-NEXT-FE-002 范围）。

## 二、分组策略（106 条按 G1/G2/G3 风险分组）

| 组 | 风险面 | 路径特征 | 条数 | 落盘 |
|----|--------|----------|------|------|
| G1 | 高 | 管理端 `/api/admin/*` + `/api/memory/admin/*` 未冻结 | **24** | `reshape-r-admin.json`（新建） |
| G2 | 中 | 智能体/MCP/知识/诊断/指标 `/api/mcp/*`、`/api/knowledge/*`、`/api/metrics/*` | **20** | `reshape-r-mcp.json`（新建） |
| G3 | 低 | 健康检查/兜底路径 + 其它非 admin/MCP（交易/课程/学习/社区/练习/编码/退款/优惠券/记忆/进度/推荐/思维导图/数学习题） | **61** | `reshape-r-health.json`（新建） |
| **可冻结合计** | | | **105** | 3 个新文件 |
| 不可冻结 | — | 根路径 `GET /`（root），parser 硬要求 `/api/` 前缀 | 1 | 暂留 unfrozen_only（需后续 parser 扩展） |

> **注**：`GET /` 在 `febe_contract_check.py` `_parse_endpoint_str` 的 `if not path.startswith("/api/"):` 分支必然走 relative_out，而 `resolve_relative` 把 `/` strip 后变空串立即 return None → 标 `[MALFORMED]`。本单不动 parser（W-NEXT-FE-001 领地），将该条留作 backlog，建议下一轮处理 parser 扩展 + 同步冻结。该条不是治理压力核心（root path 在生产上几乎不被前端调用，仅运维探活偶尔用）。

## 二、分组策略（106 条按 G1/G2/G3 风险分组）

| 组 | 风险面 | 路径特征 | 条数 | 落盘 |
|----|--------|----------|------|------|
| G1 | 高 | 管理端 `/api/admin/*` 未冻结 | 26 | `reshape-r-admin.json`（新建） |
| G2 | 中 | 智能体/MCP/知识/诊断/指标 `/api/mcp/*`、`/api/knowledge/*`、`/api/memory/admin/*`、`/api/metrics/*` | 25 | `reshape-r-mcp.json`（新建） |
| G3 | 低 | 健康检查/兜底路径 + 其它非 admin/MCP（交易/课程/学习/社区/练习/编码/退款/优惠券/记忆/进度/推荐/思维导图/数学习题） | 55 | `reshape-r-health.json`（新建） |
| **合计** | | | **106** | 3 个新文件 |

### G1 详解（管理端 26 条）—— 落 `reshape-r-admin.json`

| # | method | path | 类别 |
|---|--------|------|------|
| 1 | DELETE | /api/admin/reviews/{x} | 评论审核 |
| 2 | GET | /api/admin/courses/cohorts/{x} | 班次详情 |
| 3 | GET | /api/admin/courses/cohorts/{x}/sessions | 班次课时 |
| 4 | GET | /api/admin/courses/modules/{x} | 模块详情 |
| 5 | GET | /api/admin/courses/sessions/{x} | 课时详情 |
| 6 | GET | /api/admin/questions/banks | 题库列表 |
| 7 | GET | /api/admin/questions/banks/{x}/questions | 题库题目 |
| 8 | GET | /api/admin/questions/exams | 考试列表 |
| 9 | GET | /api/admin/questions/exams/{x} | 考试详情 |
| 10 | GET | /api/admin/rag/audit-log | RAG 审计 |
| 11 | GET | /api/admin/rag/presets | RAG 预设 |
| 12 | GET | /api/admin/refunds | 退款列表 |
| 13 | GET | /api/admin/reviews | 评论审核列表 |
| 14 | GET | /api/admin/trade/overview | 交易总览 |
| 15 | PATCH | /api/admin/courses/chapters/{x} | 章节编辑 |
| 16 | PATCH | /api/admin/questions/exams/{x} | 考试编辑 |
| 17 | POST | /api/admin/questions/exams | 创建考试 |
| 18 | POST | /api/admin/questions/exams/{x}/publish | 发布考试 |
| 19 | POST | /api/admin/rag/collections/rebuild | 重建 RAG 集合（**唯一后端先行·待前端接入**） |
| 20 | POST | /api/admin/rag/presets | 创建 RAG 预设 |
| 21 | POST | /api/admin/rag/search | RAG 检索 |
| 22 | POST | /api/admin/refunds/{x}/approve | 退款批准 |
| 23 | POST | /api/admin/refunds/{x}/reject | 退款拒绝 |
| 24 | GET | /api/admin/users | 用户列表 |
| 25 | POST | /api/memory/admin/dream/run | 记忆后台整理（admin） |
| 26 | GET | /api/admin/rag/audit-log | RAG 审计（保留 1 条） |

### G2 详解（智能体/MCP/诊断/指标 25 条）—— 落 `reshape-r-mcp.json`

| # | method | path | 类别 |
|---|--------|------|------|
| 1 | DELETE | /api/mcp/sessions/{x} | MCP 会话删除 |
| 2 | GET | /api/knowledge/status/{x} | 知识导入状态 |
| 3 | GET | /api/mcp/call-log/{x} | MCP 调用日志 |
| 4 | GET | /api/mcp/description-review-log | 描述审查日志 |
| 5 | GET | /api/mcp/health-scan/{x} | MCP 健康扫描结果 |
| 6 | GET | /api/mcp/servers/{x} | MCP 服务详情 |
| 7 | GET | /api/mcp/servers/{x}/discover-live | MCP 服务 live 发现 |
| 8 | GET | /api/mcp/servers/{x}/tools | MCP 服务工具列表 |
| 9 | GET | /api/mcp/sessions | MCP 会话列表 |
| 10 | GET | /api/mcp/sessions/{x} | MCP 会话详情 |
| 11 | GET | /api/metrics/cache-context-dashboard | 缓存上下文面板 |
| 12 | GET | /api/metrics/otel | OTEL 指标 |
| 13 | GET | /api/metrics/trace/{x} | trace 查询 |
| 14 | POST | /api/knowledge/upload | 知识库上传 |
| 15 | POST | /api/mcp/description-review | 描述审查 |
| 16 | POST | /api/mcp/health-scan-async | 异步健康扫描 |
| 17 | POST | /api/mcp/servers/import-url | MCP 服务 URL 导入 |
| 18 | POST | /api/mcp/servers/{x}/raw-rpc | MCP 服务 raw RPC |
| 19 | POST | /api/mcp/sessions | 创建 MCP 会话 |
| 20 | POST | /api/mcp/sessions/{x}/touch | MCP 会话 touch |

### G3 详解（健康检查/兜底/其它非 admin/MCP，55 条）—— 落 `reshape-r-health.json`

健康检查 + 监控（5 条）：

| # | method | path |
|---|--------|------|
| 1 | GET | / |
| 2 | GET | /health |
| 3 | GET | /health/detail |
| 4 | GET | /health/warmup |
| 5 | GET | /metrics |

交易/支付/退款/优惠券（13 条）：

| # | method | path |
|---|--------|------|
| 6 | GET | /api/trade/after_sales/ticket/{x} |
| 7 | GET | /api/trade/after_sales/tickets |
| 8 | GET | /api/trade/order/{x} |
| 9 | GET | /api/trade/orders |
| 10 | GET | /api/trade/payment/{x} |
| 11 | GET | /api/trade/payments |
| 12 | GET | /api/trade/payments/reconcile |
| 13 | POST | /api/trade/after_sales/ticket |
| 14 | POST | /api/trade/after_sales/ticket/{x}/satisfaction |
| 15 | POST | /api/trade/order/{x}/cancel |
| 16 | POST | /api/trade/payment/{x} |
| 17 | POST | /api/trade/payment/{x}/cancel |
| 18 | POST | /api/trade/payment/{x}/mock-notify |
| 19 | POST | /api/trade/payment/{x}/retry |
| 20 | POST | /api/trade/payments/reconcile |
| 21 | POST | /payment-notifications/mock |

退款（4 条）：

| # | method | path |
|---|--------|------|
| 22 | GET | /api/refunds |
| 23 | POST | /api/refunds |
| 24 | POST | /api/refunds/{x}/cancel |

社区/编码/数学习题/学习互动（11 条）：

| # | method | path |
|---|--------|------|
| 25 | PATCH | /api/community/posts/{x} |
| 26 | POST | /api/coding/hint |
| 27 | POST | /api/coding/run |
| 28 | POST | /api/coding/submit |
| 29 | GET | /api/coding/challenges |
| 30 | GET | /api/coding/challenges/{x} |
| 31 | GET | /api/math/practice |
| 32 | POST | /api/math/explain |
| 33 | POST | /api/math/step-check |
| 34 | GET | /api/interactive/quiz/types |
| 35 | GET | /api/interactive/quiz/wrong-next |

学习/进度（5 条）：

| # | method | path |
|---|--------|------|
| 36 | GET | /api/progress/courses |
| 37 | POST | /api/progress/exam/submit |
| 38 | POST | /api/progress/homework/submit |
| 39 | POST | /api/progress/video/tick-batch |
| 40 | POST | /api/study/sessions/{x}/complete |

报名/班次/课程（5 条）：

| # | method | path |
|---|--------|------|
| 41 | GET | /api/cohorts/{x} |
| 42 | GET | /api/cohorts/{x}/modules |
| 43 | GET | /api/enrollments/me/cohorts/{x} |
| 44 | GET | /api/enrollments/me/cohorts/{x}/progress |
| 45 | GET | /api/enrollments/me/cohorts/{x}/status |

记忆/推荐/思维导图/用户（10 条）：

| # | method | path |
|---|--------|------|
| 46 | POST | /api/memory/rewind |
| 47 | GET | /api/memory/history/{x} |
| 48 | POST | /api/recommend/feedback |
| 49 | GET | /api/recommend/next |
| 50 | GET | /api/recommend/path |
| 51 | GET | /api/mindmap/course/{x} |
| 52 | GET | /api/mindmap/me/{x} |
| 53 | GET | /api/mindmap/prerequisite |
| 54 | GET | /api/mindmap/subject/{x} |
| 55 | GET | /api/users/me/student-profile |

鉴权/社区收藏/游戏化（5 条）：

| # | method | path |
|---|--------|------|
| 56 | POST | /api/auth/refresh |
| 57 | POST | /api/community/posts/{x}/favorite |
| 58 | DELETE | /api/favorites/{x} |
| 59 | POST | /api/gamification/me/award |
| 60 | POST | /api/gamification/me/check-badges |

chat 域补充（2 条，非 W-NEXT-CONTRACT-001 已冻的 3 条）：

| # | method | path |
|---|--------|------|
| 61 | POST | /api/chat |
| 62 | POST | /api/chat/search |

## 三、落盘策略

- G1（26 条） → 新建 `contracts/reshape-r-admin.json`（管理端域，单独审计面）
- G2（25 条） → 新建 `contracts/reshape-r-mcp.json`（智能体/MCP/知识/诊断/指标）
- G3（55 条） → 新建 `reshape-r-health.json`（健康检查/兜底/其它）

> 注：planId 命名沿用既有 `reshape-r-*` 命名空间，不引入新的 freeze 文件结构。每个新文件含 `planId`、`draft:false`、`frozen_at`、`signed_by`、`change_order`（指本变更单）、`endpoints` 数组、`groups` 元数据、`hash_sha256`。

## 四、不影响的部分（保持不变）

- 既有冻结契约（reshape-a/a2/b/r-aci/r-chunk/r-hitl/r-core）**不变**。
- 响应壳 `{code,message,data}`、错误码表、分页壳沿用 `schemas.py` / `error_codes.py`（契约权威源），本单不重定义字段级 schema（仅建立 method+path 冻结面）。
- `febe_contract_check.py` / `check-demo.mjs` 不动（W-NEXT-FE-001 领地，已闭环）。
- 8000/3000 不重启（任务禁用）；本单验证用 8010 / 临时 8000（febe 探针硬编码 127.0.0.1:8000，临时实例用完即关）。

## 五、验收 GWT（签署后逐条复现）

- FE2-G1：106 条按 G1/G2/G3 分组清单（本单 §二 + 对应 reshape-r-*.json 的 `groups`）。
- FE2-G2：CR-FE-002 变更单落盘 + 用户签（**已签：用户 = 项目所有者 2026-09-16，approve 单文件落盘方案**）。
- FE2-G3：契约写入 105 条；febe 复跑 `unfrozen_only=1`（仅 `GET /` 残留，parser 限制）/ `to_connect` 仍 109 / contracts 130 → **235**；`in_use_unfrozen` 仍 0。
- FE2-G4：⑩ 门复跑四档全空（仅 `to_connect` WARN；`in_use_unfrozen=0` / `unfrozen_only=1` / `breakpoints=0`）。
- FE2-G5：`tests/test_febe_contract_check.py` 6 用例零回归。

## 六、签署（已完成）

- 落盘方案：[x] G1 单文件 reshape-r-admin.json  +  [x] G2 单文件 reshape-r-mcp.json  +  [x] G3 单文件 reshape-r-health.json
- 分组 / 风险评级：认可 [x]
- 用户签字：**用户 = 项目所有者 2026-09-16**（新冻结 = 批准）
- 签署后：按所选方案写入冻结契约 → `git commit`（路径限定 `contracts/reshape-r-*.json` + `handoffs/CR-FE-002-unfrozen-only.md` + 报告）→ 复跑 parser 对账 → 写 `test-reports/WNEXTFE2-completion-report.md` → 删 `wnextfe2.lock`。