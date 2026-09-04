# task22-completion-report · 后端 after_sales/ticket 售后工单域（契约⑫）

> 类型：backend + database ｜ 阶段：P4/W2 ｜ 执行：TraeCode 手动调度（dev-standard 8 阶段）
> 契约依据：**api-request §7 + 前端 tickets.ts（权威裁定）**；非 task22 文档原型（/api/tickets 5 type 废弃）
> 状态：**待编排者验收**（未经验收不开始 task23）

---

## 范围裁定（用户硬性规则④）
task22 以 api-request §7 + 前端 tickets.ts 为权威：**4 端点** `/api/trade/after_sales/ticket...`、`ticket_type ∈ {consult,appeal,refund,other}`、`status ∈ {open,processing,resolved,closed}`、满意度（satisfaction）；**无 follows/survey**。

## 交付内容
| 端点 | 说明 |
|------|------|
| POST `/api/trade/after_sales/ticket` | 创建工单（类型含 appeal 人工申诉） |
| GET `/api/trade/after_sales/tickets` | 我的工单（status/type 过滤 + 分页）→ TicketPage |
| GET `/api/trade/after_sales/ticket/{ticket_id}` | 工单详情（越权 404；管理员可见全部） |
| POST `/api/trade/after_sales/ticket/{ticket_id}/satisfaction` | 满意度评价（1-5 星，幂等） |

## 新增/修改文件
| 文件 | 说明 |
|------|------|
| `edu-agent/app/domains/after_sales/{schemas,repository,service,router,__init__}.py` | after_sales 域 |
| `edu-agent/app/main.py` | 注册 after_sales_router |
| `edu-agent/tests/test_contract_task22.py` | task22 契约测试（in-process ASGI） |
| `edu-frontend/scripts/contract-diff.py` | 追加 Ticket/TicketPage 契约比对条目 |

---

## 验收标准逐条对照

### GWT① 创建 ticket_type=appeal 工单，first_response_at 空
> Given 用户创建 ticket_type=appeal 工单，Then 落库成功且前端文案映射"人工申诉"；first_response_at 为空（等待受理态）。

**实测**：`test_create_appeal_ticket` PASS——POST appeal 工单 → 200、`ticket_type=appeal`、`status=open`；DB 复核 `first_response_at IS NULL`（等待受理态）。`test_create_refund_ticket` PASS。

### GWT② user_id 隔离：A 请求 B 工单 → 404；管理员可见全部
> Given 用户 A 请求用户 B 的工单详情，Then 404（隔离）；管理员可见全部。

**实现**：详情/列表对非本人强制 `st.user_id=%s`；越权 → `40441 工单不存在`（不泄漏存在性）；管理员(admin/manager) → scope_user=None 见全部。

**实测**：`test_cross_user_detail_404` PASS——B GET A 工单 → **404/40441**；`test_own_detail_ok` PASS——A 自己 → 200；`test_list_admin_sees_all` PASS——admin 列表返回跨用户工单。

### GWT③ 满意度落库 + 不可重复评分
> Given 关闭工单后评满意度，Then score 落库且不可重复评分。

**实现**：`service_ticket_satisfaction_survey.ticket_id` 唯一 + service 预查 + 1062 捕获双保险；重复评分返回 `submitted=False` 且不改写。

**实测**：`test_satisfaction_and_not_duplicate` PASS——首次 `submitted=True`(score=5)；再次 `submitted=False`；DB 仅 1 条且 score 仍 5。

### GWT④ 列表按 status/type 过滤 + 分页 → TicketPage
> Given 工单列表，When 按 status/type 过滤 + 分页，Then 返回 TicketPage（对齐前端类型）。

**实测**：`test_list_and_filter` PASS——`ticket_type=appeal` 过滤后 items 全为 appeal；`status=open` 过滤 200。`contract-diff` **Ticket(14 字段)/TicketPage(4 字段) 零差异**。

---

## 契约测试结果
| 套件 | 结果 |
|------|------|
| `tests/test_contract_task22.py`（in-process） | **7/7 通过** |
| `tests/test_contract_task20.py` + `task21.py`（回归） | **15/15 通过** |
| `contract-diff.py --verbose` | **16 对契约零差异**（含 Ticket/TicketPage） |
| 语法诊断（GetDiagnostics） | after_sales 全域 + main + tests 均 0 错误 |

> ⚠️ 环境：外部存储机(192.168.85.101)不可用，uvicorn 起服挂；test 改 in-process ASGI。

## 安全红线（独立子代理 review）
| 红线 | 结论 |
|------|------|
| R1 user_id 隔离（越权 404，不泄漏存在性；管理员全量） | ✅ 通过 |
| R2 满意度幂等（唯一键 + 预查 + 1062 捕获，submitted=False 不改写） | ✅ 通过 |
| R3 列对照（service_ticket/satisfaction_survey 全 NOT NULL 覆盖） | ✅ 通过 |
| R4 首响语义（first_response_at NULL=等待受理；ticket_no 唯一幂等） | ✅ 通过 |
| R5 枚举规整（历史值 complaint/after_sales/pending/in_progress → 前端枚举） | ✅ 通过 |

**审查修复项**：D1（docstring 400→submitted=False）；D5（order_no 错误与无订单区分——40442 vs 40040）；D2（满意度 1062 回查不过滤 yn，幂等取库中真实分）。D3/D4/D6 记录为接受项（低）。

> 说明：`service_ticket` 写入使用前端枚举(open/processing)，与 DB 注释历史枚举(pending/in_progress/closed)并存，读取已 `_norm_status` 归一化自洽（D4 数据治理注意项，非本域缺陷）。

## 验证命令
```bash
.venv\Scripts\python -m pytest tests/test_contract_task22.py -v
(edu-frontend) python scripts/contract-diff.py --verbose
```

## 关键经验留痕
- **契约裁定**：task22 文档原型(/api/tickets 5 type)已废弃，权威 = api-request §7 + 前端 tickets.ts（4 端点 4 type）。
- **列对照（task12 教训）**：service_ticket 全字段 NOT NULL + FK；order_item_id 需从 order_no/最近订单解析；satisfaction_survey.ticket_id 唯一=幂等键。
- **user 隔离**：越权与不存在统一 40441，无侧信道区分存在性。
- **枚举映射**：edu.sql 历史值 vs 前端枚举读取时归一化（D4）。