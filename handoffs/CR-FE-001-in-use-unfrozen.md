# 变更单 CR-FE-001：补冻结 40 条前端在用但未冻结契约（W-NEXT-CONTRACT-001）

> 状态：**draft（待用户签字）**｜提出：后端契约工程师（承接 W-NEXT-FE-001 ⑩门红档差集）｜日期 2026-09-16
> 变更对象：新增 `contracts/reshape-r-core.json`（非 draft，冻结）；现有 reshape-r-*.json 不动（除非用户选「拆分落盘」方案）。
> 依据：FE-BE 子 agent 实测 `deploy/backups/wnextfe1_in_use_unfrozen_20260916.json`（40 条）+ `test-reports/WNEXTFE1-completion-report.md`。
> 权限边界：本单**只补契约**（method+path 冻结面），不碰 `app/**`、前端、`febe_contract_check.py`（W-NEXT-FE-001 领地）。

## 一、问题（为什么要改）

W-NEXT-FE-001 把 ⑩ 契约对账门拆成四档后，实测 `in_use_unfrozen = 40` 条——**前端实际在调用、后端 OpenAPI 确有路由、但冻结契约里没有**。含生产主链路：

- `POST /api/chat/stream`（对话主入口）
- `GET /api/chat/sessions/{x}/history`（历史）
- `POST /api/trade/order`（下单）
- `POST /api/community/posts/{x}/like` / `comments`（社区互动）
- `POST /api/courses/{x}/reviews`（课程评价）

这正是 FE-BE 批判报告担心的「**后端改这些端点、前端不知道**」场景——无冻结契约 = 无变更单防线 = 后端私自改动可直达生产前端。本单把这 40 条纳入冻结集合，⑩ 红档归零。

> 注：kickoff 预估「45 条 / 冻结 83→128」，但 W-NEXT-FE-001 实测纠正为 **40 条 / 冻结 90→130**（含 parser 修复回收的 6 条前端在用接口）。本单以一手实测为准。

## 二、变更内容（按风险面分组，共 40 条）

每条格式与 parser 口径一致：`METHOD /api/path`（路径参数归一化为 `{x}`，去尾斜杠）。冻结后 parser 把每条 `(method, norm_path)` 纳入冻结集合。

### G1 生产主链路（P0，11 条）—— chat / 社区 / 课程评价 / 收藏
| # | method | path | 说明 |
|---|--------|------|------|
| 1 | POST | /api/chat/stream | 对话主入口（SSE） |
| 2 | DELETE | /api/chat/sessions/{x} | 删会话 |
| 3 | GET | /api/chat/sessions/{x}/history | 会话历史 |
| 4 | POST | /api/community/posts/{x}/like | 帖子点赞 |
| 5 | POST | /api/community/posts/{x}/comments | 发评论 |
| 6 | POST | /api/community/comments/{x}/like | 评论点赞 |
| 7 | GET | /api/community/posts/{x} | 帖子详情 |
| 8 | GET | /api/community/posts/{x}/comments | 评论列表 |
| 9 | POST | /api/courses/{x}/reviews | 写评价 |
| 10 | GET | /api/courses/{x}/reviews | 评价列表 |
| 11 | POST | /api/favorites | 收藏 |

### G2 教学 / 课程域（P0，6 条）—— 学习面用户端
| # | method | path | 说明 |
|---|--------|------|------|
| 12 | GET | /api/coupons/templates | 优惠券模板 |
| 13 | GET | /api/interactive/quiz/question/{x} | 题目详情 |
| 14 | GET | /api/series/{x}/cohorts | 系列班次 |
| 15 | GET | /api/study/courses/{x}/access | 学习权限 |
| 16 | GET | /api/study/courses/{x}/outline | 课程大纲 |
| 17 | GET | /api/study/sessions/{x} | 学习会话 |

### G3 交易 / 订单 / 退款（P1，1 条）
| # | method | path | 说明 |
|---|--------|------|------|
| 18 | POST | /api/trade/order | 下单（业务边界，最敏感） |

> 本批 in_use_unfrozen 中交易域仅 `trade/order` 1 条；退款域（`/api/refunds*`）前端当前未调用，不在差集内，后续走待接裁定。

### G4 智能体 / MCP 域（P1，1 条）
| # | method | path | 说明 |
|---|--------|------|------|
| 19 | POST | /api/mcp/servers/{x}/discover | MCP 服务发现 |

### G5 管理端 / 知识库（P2，21 条）—— 后台 CRUD
**课程管理（12）**：
| # | method | path |
|---|--------|------|
| 20 | DELETE | /api/admin/courses/cohorts/{x} |
| 21 | DELETE | /api/admin/courses/modules/{x} |
| 22 | DELETE | /api/admin/courses/series/{x} |
| 23 | DELETE | /api/admin/courses/sessions/{x} |
| 24 | GET | /api/admin/courses/series/{x} |
| 25 | GET | /api/admin/courses/series/{x}/cohorts |
| 26 | GET | /api/admin/courses/videos/{x}/chapters |
| 27 | PATCH | /api/admin/courses/cohorts/{x} |
| 28 | PATCH | /api/admin/courses/modules/{x} |
| 29 | PATCH | /api/admin/courses/series/{x} |
| 30 | PATCH | /api/admin/courses/sessions/{x} |
| 31 | POST | /api/admin/courses/series/{x}/restore |

**题库管理（6）**：
| # | method | path |
|---|--------|------|
| 32 | DELETE | /api/admin/questions/banks/{x} |
| 33 | DELETE | /api/admin/questions/questions/{x} |
| 34 | GET | /api/admin/questions/banks/{x} |
| 35 | GET | /api/admin/questions/questions/{x} |
| 36 | PATCH | /api/admin/questions/banks/{x} |
| 37 | PATCH | /api/admin/questions/questions/{x} |

**用户管理（2）**：
| # | method | path |
|---|--------|------|
| 38 | POST | /api/admin/users/{x}/role |
| 39 | POST | /api/admin/users/{x}/status |

**知识库（1）**：
| # | method | path |
|---|--------|------|
| 40 | DELETE | /api/knowledge/partitions/{x} |

## 三、落盘策略（待用户裁决，见 §六）

- **方案 A（推荐）**：40 条全部写入**新建单一文件** `contracts/reshape-r-core.json` 的 `endpoints` 数组，附 `groups` 元数据记 G1–G5 分组。单一审计面、零跨文件合并风险、parser 计数一次性 90→130。
- **方案 B（拆分）**：chat 域 3 条（POST /api/chat/stream、DELETE /api/chat/sessions/{x}、GET /api/chat/sessions/{x}/history）作为 amendment 并入 `reshape-r-hitl.json`，其余 37 条入新建 `reshape-r-core.json`。更贴近 kickoff「补 amendment」措辞，但需改 2 个文件、合并风险略高。

两种方案对 ⑩ 门效果等价（parser 读所有 reshape-r* 非 draft 文件），仅治理归类不同。

## 四、不影响的部分（保持不变）

- 既有冻结契约（reshape-a/a2/b/r-aci/r-chunk/r-hitl）**不变**（方案 A 完全不动；方案 B 仅给 r-hitl 追加 3 条 endpoints）。
- 响应壳 `{code,message,data}`、错误码表、分页壳沿用 `schemas.py` / `error_codes.py`（契约权威源），本单不重定义字段级 schema（仅建立 method+path 冻结面，杜绝「后端私改无人知」）。
- `febe_contract_check.py` / `check-demo.mjs` 不动（W-NEXT-FE-001 领地）。

## 五、验收 GWT（签署后逐条复现）

- CT-G1：40 条分组表 + 风险评级（本单 §二）。
- CT-G2：变更单落盘 + 标注待签（本文件）。
- CT-G3：用户签后冻结 40 条，`contracts` 由 90 → **130**；parser `in_use_unfrozen` 由 40 → **0**。
- CT-G4：复跑 `febe_contract_check.py`：`breakpoints=0 in_use_unfrozen=0 unfrozen_only=? to_connect=? frontend=101 backend=210 contracts=130 malformed=0`；⑩ 门转绿（exit 0）。
- CT-G5：契约相关单测全绿（`tests/test_febe_contract_check.py` 6 passed 不受影响）；冻结文件留痕 sha256。

## 六、签署（待用户裁决 + 签字）

- 落盘方案：[ ] A 单文件 reshape-r-core.json  [ ] B 拆分（r-hitl + r-core）
- 分组 / 风险评级：认可 [ ] / 调整 [ ]
- 用户签字：__________ 日期：__________
- 签署后：按所选方案写入冻结契约 → `git commit`（路径限定 `contracts/reshape-r-core.json` + `handoffs/CR-FE-001-in-use-unfrozen.md` + 报告）→ 复跑 parser 对账 → 写 `test-reports/WNEXTCONTRACT1-completion-report.md` → 删 `wnextcontract1.lock`。
