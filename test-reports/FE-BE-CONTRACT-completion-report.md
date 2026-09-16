# FE-BE-CONTRACT 前后端契约联调门 — 完成报告

> 生成时间：2026-09-16 14:51:13  |  任务：kickoff-FE-BE-CONTRACT.md（纯只读三方对账门）
> 范围：edu-frontend/public 静态页  ↔  后端 127.0.0.1:8000 OpenAPI  ↔  contracts/reshape-* 冻结契约

## 一、三步 GWT 验收

| GWT | 验收点 | 结果 |
|-----|--------|------|
| FB-G1 | `_frontend_real_api.txt` 刷新（≥93 条、含 W-NEXT 新端点、零断点） | ✅ 101 条，零断点 |
| FB-G2 | `febe_contract_check.py` 三类差异输出；断点=0；路径拼接不误截 | ✅ 断点=0；`/videos/init-chunked`、`upload-chunk/{u}/{i}` 完整匹配 |
| FB-G3 | check-demo 契约对账子断言生效（断点红/待接 WARN） | ✅ ⑩ 跑通，WARN（to_connect/unfrozen>0 非阻断） |
| FB-G4 | 待接清单（rag/collections/rebuild 等）登记「待前端接入」 | ✅ 见 §四 |
| FB-G5 | host 校验写死 127.0.0.1:8000；纯只读零写库 | ✅ 非本地 host 全部拒绝；无 DB 写入 |

## 二、关键数字

- 前端调用（method+path）：**101**
- 后端路由（OpenAPI route-methods）：**210**
- 冻结契约覆盖：**83** unique method+path（覆盖路径约 58 个）
- **断点（前端−后端）：0**
- **待接（后端−前端）：109**
- **未冻结（后端−冻结契约，按路径）：150**

## 三、分步说明

### 步骤1：前端契约权威清单刷新

扫描 `edu-api.js` + `public/*.html` 的 `EAPI.get/post/put/patch/del`、`fetch`、`xhr.open`，
归一化路径参数→`{x}`、去 query、排序去重，刷新 `test-reports/_frontend_real_api.txt`。

- 旧清单 93 条（8-30）→ 新清单 **101** 条。
- 确认纳入 W-NEXT 新端点：`POST /api/chat/resume`、`POST /api/admin/courses/videos/init-chunked`、
  `PUT /api/admin/courses/videos/upload-chunk/{x}/{x}`、`POST /api/admin/courses/videos/finalize-chunked`、
  `GET /api/admin/users/dashboard/metrics`。
- 每条均在后端 OpenAPI 路由内 → **零断点**（关键：正确识别 `/videos/init-chunked` 完整路径、
  `upload-chunk/{u}/{i}` 双参数，未误截为 `/videos`）。

### 步骤2：三方自动对账探针 `febe_contract_check.py`

纯只读；host 写死 `127.0.0.1:8000` 并拒绝其他 host；`ProxyHandler({})` 绕过 loopback 代理；无 DB 写入。

运行：`python edu-agent/scripts/eval/febe_contract_check.py`

#### ① 断点（前端−后端）：**0**

前端所有调用均能在后端 OpenAPI 找到对应 method+path，零断点。

#### ② 待接（后端−前端）：**109**

| 分类 | 数量 |
|------|------|
| 其它 | 29 |
| 管理端(admin) | 26 |
| 智能体/知识(RAG/MCP) | 17 |
| 交易/订单/优惠券 | 16 |
| 学习互动/练习 | 9 |
| 用户/社区/鉴权 | 6 |
| 学习/课程域 | 6 |

逐条裁定：`/api/admin/rag/collections/rebuild` 标记为「后端先行·待前端接入」；其余为前端当前未调用（内部管理/次要端点，按需接入）。完整清单见附录 A。

#### ③ 未冻结（后端−冻结契约，按路径）：**150**

| 分类 | 数量 |
|------|------|
| 管理端(admin) | 50 |
| 其它 | 29 |
| 智能体/知识(RAG/MCP) | 18 |
| 交易/订单/优惠券 | 18 |
| 学习/课程域 | 14 |
| 学习互动/练习 | 11 |
| 用户/社区/鉴权 | 10 |

说明：冻结契约仅覆盖约 58 个路径；未冻结多为尚未纳入冻结契约的端点，属契约治理待办（WARN，不阻断）。完整清单见附录 B。

### 步骤3：对账门进 check-demo

`check-demo.mjs` 新增 **⑩「契约对账门」** 子断言：跑 `febe_contract_check.py` 并解析 `[SUMMARY]`；
断点>0 → FAIL（红）；待接/未冻结>0 → WARN（不阻断）；后端不可达(exit 2) → WARN（以④为准）。

实测：⑩ 跑通（~1.1s），因 to_connect=109 / unfrozen=150 触发 **WARN**（非阻断），断点=0 不红。
（本次环境 ②⑤⑦⑧⑨ 为基础设施缺失红项，与契约门无关。）

## 四、待接清单（待前端接入）

- **POST `/api/admin/rag/collections/rebuild`** —— 后端已提供，前端未接入（唯一确认「后端先行·待前端接入」项，登记 tracker「待前端接入」）。
- 其余 108 条为前端当前未调用的管理/内部端点，按需接入（裁定见附录 A）。

## 五、长效价值

此后：后端新增/改端点 → 对账门立刻抓「前端未接/契约未覆盖」；前端要新接口 → 立刻抓「后端没有」。
「连不上后端」从「人肉发现」变「机验拦截」。

## 附录 A：待接清单（109，含裁定）

| # | method | path | 裁定 |
|---|--------|------|------|
| 1 | DELETE | /api/admin/reviews/{x} | 管理端端点·前端当前未调用 |
| 2 | DELETE | /api/favorites/{x} | 前端当前未调用（按需接入） |
| 3 | DELETE | /api/mcp/sessions/{x} | 智能体/内部端点·前端当前未调用 |
| 4 | GET | / | 前端当前未调用（按需接入） |
| 5 | GET | /api/admin/courses/chapters/{x} | 管理端端点·前端当前未调用 |
| 6 | GET | /api/admin/courses/cohorts/{x} | 管理端端点·前端当前未调用 |
| 7 | GET | /api/admin/courses/cohorts/{x}/sessions | 管理端端点·前端当前未调用 |
| 8 | GET | /api/admin/courses/modules/{x} | 管理端端点·前端当前未调用 |
| 9 | GET | /api/admin/courses/sessions/{x} | 管理端端点·前端当前未调用 |
| 10 | GET | /api/admin/questions/banks | 管理端端点·前端当前未调用 |
| 11 | GET | /api/admin/questions/banks/{x}/questions | 管理端端点·前端当前未调用 |
| 12 | GET | /api/admin/questions/exams | 管理端端点·前端当前未调用 |
| 13 | GET | /api/admin/questions/exams/{x} | 管理端端点·前端当前未调用 |
| 14 | GET | /api/admin/rag/audit-log | 管理端端点·前端当前未调用 |
| 15 | GET | /api/admin/rag/presets | 管理端端点·前端当前未调用 |
| 16 | GET | /api/admin/refunds | 管理端端点·前端当前未调用 |
| 17 | GET | /api/admin/reviews | 管理端端点·前端当前未调用 |
| 18 | GET | /api/admin/trade/overview | 管理端端点·前端当前未调用 |
| 19 | GET | /api/admin/users | 管理端端点·前端当前未调用 |
| 20 | GET | /api/coding/challenges | 前端当前未调用（按需接入） |
| 21 | GET | /api/coding/challenges/{x} | 前端当前未调用（按需接入） |
| 22 | GET | /api/cohorts/{x} | 前端当前未调用（按需接入） |
| 23 | GET | /api/cohorts/{x}/modules | 前端当前未调用（按需接入） |
| 24 | GET | /api/community/posts | 前端当前未调用（按需接入） |
| 25 | GET | /api/enrollments/me/cohorts/{x} | 前端当前未调用（按需接入） |
| 26 | GET | /api/enrollments/me/cohorts/{x}/progress | 前端当前未调用（按需接入） |
| 27 | GET | /api/enrollments/me/cohorts/{x}/status | 前端当前未调用（按需接入） |
| 28 | GET | /api/interactive/quiz/types | 前端当前未调用（按需接入） |
| 29 | GET | /api/interactive/quiz/wrong-next | 前端当前未调用（按需接入） |
| 30 | GET | /api/knowledge/status/{x} | 智能体/内部端点·前端当前未调用 |
| 31 | GET | /api/math/practice | 前端当前未调用（按需接入） |
| 32 | GET | /api/mcp/call-log/{x} | 智能体/内部端点·前端当前未调用 |
| 33 | GET | /api/mcp/description-review-log | 智能体/内部端点·前端当前未调用 |
| 34 | GET | /api/mcp/health-scan/{x} | 智能体/内部端点·前端当前未调用 |
| 35 | GET | /api/mcp/servers/{x} | 智能体/内部端点·前端当前未调用 |
| 36 | GET | /api/mcp/servers/{x}/discover-live | 智能体/内部端点·前端当前未调用 |
| 37 | GET | /api/mcp/servers/{x}/tools | 智能体/内部端点·前端当前未调用 |
| 38 | GET | /api/mcp/sessions | 智能体/内部端点·前端当前未调用 |
| 39 | GET | /api/mcp/sessions/{x} | 智能体/内部端点·前端当前未调用 |
| 40 | GET | /api/memory/history/{x} | 前端当前未调用（按需接入） |
| 41 | GET | /api/metrics/cache-context-dashboard | 前端当前未调用（按需接入） |
| 42 | GET | /api/metrics/otel | 前端当前未调用（按需接入） |
| 43 | GET | /api/metrics/trace/{x} | 前端当前未调用（按需接入） |
| 44 | GET | /api/mindmap/course/{x} | 前端当前未调用（按需接入） |
| 45 | GET | /api/mindmap/me/{x} | 前端当前未调用（按需接入） |
| 46 | GET | /api/mindmap/prerequisite | 前端当前未调用（按需接入） |
| 47 | GET | /api/mindmap/subject/{x} | 前端当前未调用（按需接入） |
| 48 | GET | /api/progress/courses | 前端当前未调用（按需接入） |
| 49 | GET | /api/recommend/next | 前端当前未调用（按需接入） |
| 50 | GET | /api/recommend/path | 前端当前未调用（按需接入） |
| 51 | GET | /api/refunds | 前端当前未调用（按需接入） |
| 52 | GET | /api/trade/after_sales/ticket/{x} | 交易/订单端点·前端当前未调用 |
| 53 | GET | /api/trade/after_sales/tickets | 交易/订单端点·前端当前未调用 |
| 54 | GET | /api/trade/order/{x} | 交易/订单端点·前端当前未调用 |
| 55 | GET | /api/trade/orders | 交易/订单端点·前端当前未调用 |
| 56 | GET | /api/trade/payment/{x} | 交易/订单端点·前端当前未调用 |
| 57 | GET | /api/trade/payments | 交易/订单端点·前端当前未调用 |
| 58 | GET | /api/trade/payments/reconcile | 交易/订单端点·前端当前未调用 |
| 59 | GET | /api/users/me/student-profile | 前端当前未调用（按需接入） |
| 60 | GET | /health | 前端当前未调用（按需接入） |
| 61 | GET | /health/detail | 前端当前未调用（按需接入） |
| 62 | GET | /health/warmup | 前端当前未调用（按需接入） |
| 63 | GET | /metrics | 前端当前未调用（按需接入） |
| 64 | PATCH | /api/admin/courses/chapters/{x} | 管理端端点·前端当前未调用 |
| 65 | PATCH | /api/admin/questions/exams/{x} | 管理端端点·前端当前未调用 |
| 66 | PATCH | /api/community/posts/{x} | 前端当前未调用（按需接入） |
| 67 | POST | /api/admin/questions/exams | 管理端端点·前端当前未调用 |
| 68 | POST | /api/admin/questions/exams/{x}/publish | 管理端端点·前端当前未调用 |
| 69 | POST | /api/admin/rag/collections/rebuild | 后端先行·待前端接入 |
| 70 | POST | /api/admin/rag/presets | 管理端端点·前端当前未调用 |
| 71 | POST | /api/admin/rag/search | 管理端端点·前端当前未调用 |
| 72 | POST | /api/admin/refunds/{x}/approve | 管理端端点·前端当前未调用 |
| 73 | POST | /api/admin/refunds/{x}/reject | 管理端端点·前端当前未调用 |
| 74 | POST | /api/auth/refresh | 前端当前未调用（按需接入） |
| 75 | POST | /api/chat | 前端当前未调用（按需接入） |
| 76 | POST | /api/chat/search | 前端当前未调用（按需接入） |
| 77 | POST | /api/coding/hint | 前端当前未调用（按需接入） |
| 78 | POST | /api/coding/run | 前端当前未调用（按需接入） |
| 79 | POST | /api/coding/submit | 前端当前未调用（按需接入） |
| 80 | POST | /api/community/posts/{x}/favorite | 前端当前未调用（按需接入） |
| 81 | POST | /api/gamification/me/award | 前端当前未调用（按需接入） |
| 82 | POST | /api/gamification/me/check-badges | 前端当前未调用（按需接入） |
| 83 | POST | /api/knowledge/upload | 智能体/内部端点·前端当前未调用 |
| 84 | POST | /api/math/explain | 前端当前未调用（按需接入） |
| 85 | POST | /api/math/step-check | 前端当前未调用（按需接入） |
| 86 | POST | /api/mcp/description-review | 智能体/内部端点·前端当前未调用 |
| 87 | POST | /api/mcp/health-scan-async | 智能体/内部端点·前端当前未调用 |
| 88 | POST | /api/mcp/servers/import-url | 智能体/内部端点·前端当前未调用 |
| 89 | POST | /api/mcp/servers/{x}/raw-rpc | 智能体/内部端点·前端当前未调用 |
| 90 | POST | /api/mcp/sessions | 智能体/内部端点·前端当前未调用 |
| 91 | POST | /api/mcp/sessions/{x}/touch | 智能体/内部端点·前端当前未调用 |
| 92 | POST | /api/memory/admin/dream/run | 管理端端点·前端当前未调用 |
| 93 | POST | /api/memory/rewind | 前端当前未调用（按需接入） |
| 94 | POST | /api/progress/exam/submit | 前端当前未调用（按需接入） |
| 95 | POST | /api/progress/homework/submit | 前端当前未调用（按需接入） |
| 96 | POST | /api/progress/video/tick-batch | 前端当前未调用（按需接入） |
| 97 | POST | /api/recommend/feedback | 前端当前未调用（按需接入） |
| 98 | POST | /api/refunds | 前端当前未调用（按需接入） |
| 99 | POST | /api/refunds/{x}/cancel | 前端当前未调用（按需接入） |
| 100 | POST | /api/study/sessions/{x}/complete | 前端当前未调用（按需接入） |
| 101 | POST | /api/trade/after_sales/ticket | 交易/订单端点·前端当前未调用 |
| 102 | POST | /api/trade/after_sales/ticket/{x}/satisfaction | 交易/订单端点·前端当前未调用 |
| 103 | POST | /api/trade/order/{x}/cancel | 交易/订单端点·前端当前未调用 |
| 104 | POST | /api/trade/payment/{x} | 交易/订单端点·前端当前未调用 |
| 105 | POST | /api/trade/payment/{x}/cancel | 交易/订单端点·前端当前未调用 |
| 106 | POST | /api/trade/payment/{x}/mock-notify | 交易/订单端点·前端当前未调用 |
| 107 | POST | /api/trade/payment/{x}/retry | 交易/订单端点·前端当前未调用 |
| 108 | POST | /api/trade/payments/reconcile | 交易/订单端点·前端当前未调用 |
| 109 | POST | /payment-notifications/mock | 交易/订单端点·前端当前未调用 |

## 附录 B：未冻结清单（150，含裁定）

| # | method | path | 裁定 |
|---|--------|------|------|
| 1 | DELETE | /api/admin/courses/chapters/{x} | 管理端端点未纳入冻结契约 |
| 2 | DELETE | /api/admin/courses/cohorts/{x} | 管理端端点未纳入冻结契约 |
| 3 | DELETE | /api/admin/courses/modules/{x} | 管理端端点未纳入冻结契约 |
| 4 | DELETE | /api/admin/courses/series/{x} | 管理端端点未纳入冻结契约 |
| 5 | DELETE | /api/admin/courses/sessions/{x} | 管理端端点未纳入冻结契约 |
| 6 | DELETE | /api/admin/questions/banks/{x} | 管理端端点未纳入冻结契约 |
| 7 | DELETE | /api/admin/questions/questions/{x} | 管理端端点未纳入冻结契约 |
| 8 | DELETE | /api/admin/reviews/{x} | 管理端端点未纳入冻结契约 |
| 9 | DELETE | /api/chat/sessions/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 10 | DELETE | /api/favorites/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 11 | DELETE | /api/knowledge/partitions/{x} | 智能体/内部端点未纳入冻结契约 |
| 12 | DELETE | /api/mcp/sessions/{x} | 智能体/内部端点未纳入冻结契约 |
| 13 | GET | / | 未纳入任何冻结契约（需补契约或变更单） |
| 14 | GET | /api/admin/courses/chapters/{x} | 管理端端点未纳入冻结契约 |
| 15 | GET | /api/admin/courses/cohorts/{x} | 管理端端点未纳入冻结契约 |
| 16 | GET | /api/admin/courses/cohorts/{x}/modules | 管理端端点未纳入冻结契约 |
| 17 | GET | /api/admin/courses/cohorts/{x}/sessions | 管理端端点未纳入冻结契约 |
| 18 | GET | /api/admin/courses/modules/{x} | 管理端端点未纳入冻结契约 |
| 19 | GET | /api/admin/courses/modules/{x}/sessions | 管理端端点未纳入冻结契约 |
| 20 | GET | /api/admin/courses/series/{x} | 管理端端点未纳入冻结契约 |
| 21 | GET | /api/admin/courses/series/{x}/cohorts | 管理端端点未纳入冻结契约 |
| 22 | GET | /api/admin/courses/sessions/{x} | 管理端端点未纳入冻结契约 |
| 23 | GET | /api/admin/courses/sessions/{x}/assets | 管理端端点未纳入冻结契约 |
| 24 | GET | /api/admin/courses/videos/{x}/chapters | 管理端端点未纳入冻结契约 |
| 25 | GET | /api/admin/courses/videos/{x}/transcode-status | 管理端端点未纳入冻结契约 |
| 26 | GET | /api/admin/questions/banks/{x} | 管理端端点未纳入冻结契约 |
| 27 | GET | /api/admin/questions/banks/{x}/questions | 管理端端点未纳入冻结契约 |
| 28 | GET | /api/admin/questions/exams | 管理端端点未纳入冻结契约 |
| 29 | GET | /api/admin/questions/exams/{x} | 管理端端点未纳入冻结契约 |
| 30 | GET | /api/admin/questions/questions/{x} | 管理端端点未纳入冻结契约 |
| 31 | GET | /api/admin/rag/audit-log | 管理端端点未纳入冻结契约 |
| 32 | GET | /api/admin/rag/presets | 管理端端点未纳入冻结契约 |
| 33 | GET | /api/admin/refunds | 管理端端点未纳入冻结契约 |
| 34 | GET | /api/admin/reviews | 管理端端点未纳入冻结契约 |
| 35 | GET | /api/admin/trade/overview | 管理端端点未纳入冻结契约 |
| 36 | GET | /api/chat/sessions/{x}/history | 未纳入任何冻结契约（需补契约或变更单） |
| 37 | GET | /api/coding/challenges | 未纳入任何冻结契约（需补契约或变更单） |
| 38 | GET | /api/coding/challenges/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 39 | GET | /api/cohorts/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 40 | GET | /api/cohorts/{x}/modules | 未纳入任何冻结契约（需补契约或变更单） |
| 41 | GET | /api/community/posts/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 42 | GET | /api/community/posts/{x}/comments | 未纳入任何冻结契约（需补契约或变更单） |
| 43 | GET | /api/coupons/templates | 未纳入任何冻结契约（需补契约或变更单） |
| 44 | GET | /api/courses/{x}/reviews | 未纳入任何冻结契约（需补契约或变更单） |
| 45 | GET | /api/enrollments/me/cohorts/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 46 | GET | /api/enrollments/me/cohorts/{x}/progress | 未纳入任何冻结契约（需补契约或变更单） |
| 47 | GET | /api/enrollments/me/cohorts/{x}/status | 未纳入任何冻结契约（需补契约或变更单） |
| 48 | GET | /api/interactive/quiz/question/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 49 | GET | /api/interactive/quiz/types | 未纳入任何冻结契约（需补契约或变更单） |
| 50 | GET | /api/interactive/quiz/wrong-next | 未纳入任何冻结契约（需补契约或变更单） |
| 51 | GET | /api/knowledge/status/{x} | 智能体/内部端点未纳入冻结契约 |
| 52 | GET | /api/math/practice | 未纳入任何冻结契约（需补契约或变更单） |
| 53 | GET | /api/mcp/call-log/{x} | 智能体/内部端点未纳入冻结契约 |
| 54 | GET | /api/mcp/description-review-log | 智能体/内部端点未纳入冻结契约 |
| 55 | GET | /api/mcp/health-scan/{x} | 智能体/内部端点未纳入冻结契约 |
| 56 | GET | /api/mcp/servers/{x}/discover-live | 智能体/内部端点未纳入冻结契约 |
| 57 | GET | /api/mcp/servers/{x}/tools | 智能体/内部端点未纳入冻结契约 |
| 58 | GET | /api/mcp/sessions | 智能体/内部端点未纳入冻结契约 |
| 59 | GET | /api/mcp/sessions/{x} | 智能体/内部端点未纳入冻结契约 |
| 60 | GET | /api/memory/history/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 61 | GET | /api/metrics/cache-context-dashboard | 未纳入任何冻结契约（需补契约或变更单） |
| 62 | GET | /api/metrics/otel | 未纳入任何冻结契约（需补契约或变更单） |
| 63 | GET | /api/metrics/trace/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 64 | GET | /api/mindmap/course/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 65 | GET | /api/mindmap/me/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 66 | GET | /api/mindmap/prerequisite | 未纳入任何冻结契约（需补契约或变更单） |
| 67 | GET | /api/mindmap/subject/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 68 | GET | /api/progress/courses | 未纳入任何冻结契约（需补契约或变更单） |
| 69 | GET | /api/recommend/next | 未纳入任何冻结契约（需补契约或变更单） |
| 70 | GET | /api/recommend/path | 未纳入任何冻结契约（需补契约或变更单） |
| 71 | GET | /api/refunds | 未纳入任何冻结契约（需补契约或变更单） |
| 72 | GET | /api/series/{x}/cohorts | 未纳入任何冻结契约（需补契约或变更单） |
| 73 | GET | /api/study/courses/{x}/access | 未纳入任何冻结契约（需补契约或变更单） |
| 74 | GET | /api/study/courses/{x}/outline | 未纳入任何冻结契约（需补契约或变更单） |
| 75 | GET | /api/study/sessions/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 76 | GET | /api/trade/after_sales/ticket/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 77 | GET | /api/trade/after_sales/tickets | 未纳入任何冻结契约（需补契约或变更单） |
| 78 | GET | /api/trade/order/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 79 | GET | /api/trade/orders | 未纳入任何冻结契约（需补契约或变更单） |
| 80 | GET | /api/trade/payment/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 81 | GET | /api/trade/payments | 未纳入任何冻结契约（需补契约或变更单） |
| 82 | GET | /api/trade/payments/reconcile | 未纳入任何冻结契约（需补契约或变更单） |
| 83 | GET | /api/users/me/student-profile | 未纳入任何冻结契约（需补契约或变更单） |
| 84 | GET | /health | 未纳入任何冻结契约（需补契约或变更单） |
| 85 | GET | /health/detail | 未纳入任何冻结契约（需补契约或变更单） |
| 86 | GET | /health/warmup | 未纳入任何冻结契约（需补契约或变更单） |
| 87 | GET | /metrics | 未纳入任何冻结契约（需补契约或变更单） |
| 88 | PATCH | /api/admin/courses/chapters/{x} | 管理端端点未纳入冻结契约 |
| 89 | PATCH | /api/admin/courses/cohorts/{x} | 管理端端点未纳入冻结契约 |
| 90 | PATCH | /api/admin/courses/modules/{x} | 管理端端点未纳入冻结契约 |
| 91 | PATCH | /api/admin/courses/series/{x} | 管理端端点未纳入冻结契约 |
| 92 | PATCH | /api/admin/courses/sessions/{x} | 管理端端点未纳入冻结契约 |
| 93 | PATCH | /api/admin/questions/banks/{x} | 管理端端点未纳入冻结契约 |
| 94 | PATCH | /api/admin/questions/exams/{x} | 管理端端点未纳入冻结契约 |
| 95 | PATCH | /api/admin/questions/questions/{x} | 管理端端点未纳入冻结契约 |
| 96 | PATCH | /api/community/posts/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 97 | POST | /api/admin/courses/series/{x}/restore | 管理端端点未纳入冻结契约 |
| 98 | POST | /api/admin/questions/exams | 管理端端点未纳入冻结契约 |
| 99 | POST | /api/admin/questions/exams/{x}/publish | 管理端端点未纳入冻结契约 |
| 100 | POST | /api/admin/rag/collections/rebuild | 管理端端点未纳入冻结契约 |
| 101 | POST | /api/admin/rag/presets | 管理端端点未纳入冻结契约 |
| 102 | POST | /api/admin/rag/search | 管理端端点未纳入冻结契约 |
| 103 | POST | /api/admin/refunds/{x}/approve | 管理端端点未纳入冻结契约 |
| 104 | POST | /api/admin/refunds/{x}/reject | 管理端端点未纳入冻结契约 |
| 105 | POST | /api/admin/users/{x}/role | 管理端端点未纳入冻结契约 |
| 106 | POST | /api/admin/users/{x}/status | 管理端端点未纳入冻结契约 |
| 107 | POST | /api/auth/refresh | 未纳入任何冻结契约（需补契约或变更单） |
| 108 | POST | /api/chat | 未纳入任何冻结契约（需补契约或变更单） |
| 109 | POST | /api/chat/search | 未纳入任何冻结契约（需补契约或变更单） |
| 110 | POST | /api/chat/stream | 未纳入任何冻结契约（需补契约或变更单） |
| 111 | POST | /api/coding/hint | 未纳入任何冻结契约（需补契约或变更单） |
| 112 | POST | /api/coding/run | 未纳入任何冻结契约（需补契约或变更单） |
| 113 | POST | /api/coding/submit | 未纳入任何冻结契约（需补契约或变更单） |
| 114 | POST | /api/community/comments/{x}/like | 未纳入任何冻结契约（需补契约或变更单） |
| 115 | POST | /api/community/posts/{x}/comments | 未纳入任何冻结契约（需补契约或变更单） |
| 116 | POST | /api/community/posts/{x}/favorite | 未纳入任何冻结契约（需补契约或变更单） |
| 117 | POST | /api/community/posts/{x}/like | 未纳入任何冻结契约（需补契约或变更单） |
| 118 | POST | /api/courses/{x}/reviews | 未纳入任何冻结契约（需补契约或变更单） |
| 119 | POST | /api/gamification/me/award | 未纳入任何冻结契约（需补契约或变更单） |
| 120 | POST | /api/gamification/me/check-badges | 未纳入任何冻结契约（需补契约或变更单） |
| 121 | POST | /api/knowledge/upload | 智能体/内部端点未纳入冻结契约 |
| 122 | POST | /api/math/explain | 未纳入任何冻结契约（需补契约或变更单） |
| 123 | POST | /api/math/step-check | 未纳入任何冻结契约（需补契约或变更单） |
| 124 | POST | /api/mcp/description-review | 智能体/内部端点未纳入冻结契约 |
| 125 | POST | /api/mcp/health-scan-async | 智能体/内部端点未纳入冻结契约 |
| 126 | POST | /api/mcp/servers/import-url | 智能体/内部端点未纳入冻结契约 |
| 127 | POST | /api/mcp/servers/{x}/discover | 智能体/内部端点未纳入冻结契约 |
| 128 | POST | /api/mcp/servers/{x}/raw-rpc | 智能体/内部端点未纳入冻结契约 |
| 129 | POST | /api/mcp/sessions | 智能体/内部端点未纳入冻结契约 |
| 130 | POST | /api/mcp/sessions/{x}/touch | 智能体/内部端点未纳入冻结契约 |
| 131 | POST | /api/memory/admin/dream/run | 管理端端点未纳入冻结契约 |
| 132 | POST | /api/memory/rewind | 未纳入任何冻结契约（需补契约或变更单） |
| 133 | POST | /api/progress/exam/submit | 未纳入任何冻结契约（需补契约或变更单） |
| 134 | POST | /api/progress/homework/submit | 未纳入任何冻结契约（需补契约或变更单） |
| 135 | POST | /api/progress/video/tick-batch | 未纳入任何冻结契约（需补契约或变更单） |
| 136 | POST | /api/recommend/feedback | 未纳入任何冻结契约（需补契约或变更单） |
| 137 | POST | /api/refunds | 未纳入任何冻结契约（需补契约或变更单） |
| 138 | POST | /api/refunds/{x}/cancel | 未纳入任何冻结契约（需补契约或变更单） |
| 139 | POST | /api/study/sessions/{x}/complete | 未纳入任何冻结契约（需补契约或变更单） |
| 140 | POST | /api/trade/after_sales/ticket | 未纳入任何冻结契约（需补契约或变更单） |
| 141 | POST | /api/trade/after_sales/ticket/{x}/satisfaction | 未纳入任何冻结契约（需补契约或变更单） |
| 142 | POST | /api/trade/order | 未纳入任何冻结契约（需补契约或变更单） |
| 143 | POST | /api/trade/order/{x}/cancel | 未纳入任何冻结契约（需补契约或变更单） |
| 144 | POST | /api/trade/payment/{x} | 未纳入任何冻结契约（需补契约或变更单） |
| 145 | POST | /api/trade/payment/{x}/cancel | 未纳入任何冻结契约（需补契约或变更单） |
| 146 | POST | /api/trade/payment/{x}/mock-notify | 未纳入任何冻结契约（需补契约或变更单） |
| 147 | POST | /api/trade/payment/{x}/retry | 未纳入任何冻结契约（需补契约或变更单） |
| 148 | POST | /api/trade/payments/reconcile | 未纳入任何冻结契约（需补契约或变更单） |
| 149 | POST | /payment-notifications/mock | 未纳入任何冻结契约（需补契约或变更单） |
| 150 | PUT | /api/admin/courses/videos/upload-chunk/{x}/{x} | 管理端端点未纳入冻结契约 |

