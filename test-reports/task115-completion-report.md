# task115 完工报告（C-B：分页统一 + SSE error 事件）

- 域：BE+契约 ｜ 平台：claude ｜ 状态：**待验收**（独立复验归编排者，禁 commit）
- 前置已满足：task114（C-A 壳统一）已合入，resp_wrap 幂等包壳生效，本轮未重复包壳。
- 契约单：`.ai-hub/plans/handoffs/task115-contract.md`

## 1. 改动清单（grep 行号实证）
| 文件 | 改动 | 行号 |
|---|---|---|
| `edu-agent/app/domains/course/schemas.py` | `SeriesListData` 增权威 `total/page/page_size` + 保留 `page_meta` 兼容字段 + 契约注释 | 52-64 |
| 同 | `CohortListData` 同步 | 117-124 |
| `edu-agent/app/domains/course/service.py` | `list_series` 返回权威 `{total,page,page_size,items}` + `page_meta`（同源派生） | 121-129 |
| 同 | `list_cohorts` 返回 `CohortListData(total,page,page_size,...)` + `page_meta` | 170-178 |
| `edu-agent/app/chat/router.py` | 导入 `INTERNAL_ERROR`；生成器 token 迭代异常不再静默转 done，改为发 `event: error`+`data{code,message}` 后安全收束 | 46 / 243-255 / 259 |

未改：`resp_wrap.py`、`users/router.py`、progress、schemas.py 无关域、前端静态页。

## 2. 机器验证输出（8078 隔离端口真实 curl）
- 分页统一（`/api/series?page=1&page_size=3`）：`data:{total:2628,page:1,page_size:3,items:[...],page_meta:{...}}`
  断言 `outer.total==page_meta.total`、`outer.page==page_meta.page`、`outer.page_size==page_meta.page_size` → **全 True**。
- 分页统一（`/api/series/2628/cohorts`）：`data:{total:3,page:1,page_size:3,items,page_meta}`。✅
- 多页一致性（`page=2&page_size=20`）：外层与 page_meta `page/page_size/total` 一致（True），`has_more=True,total_pages=132`。
- 非分页详情 `/api/series/2628` 回归：`code=0`，未受影响。✅
- C-A 壳完整：外层 `{code:0,message:"ok",data:{...}}`，未重复包壳、未漏壳。✅

### SSE error 实证（两段式）
- **第一段（连接前失败）**：`Authorization: Bearer garbage` → `HTTP 401 {"code":"40101",...}`，**非 SSE**。✅
- **第二段（流中失败，真实 ASGI HTTP 打到 router 生成器）抓包**：
  ```
  HTTP 200
  event: start
  event: retrieval
  event: token / data: {"delta":"部"}
  event: token / data: {"delta":"分内容"}
  event: error / data: {"code": "50000", "message": "答案生成失败：RuntimeError"}
  ```
  断言 `contains_error=True`、`contains_code(50000)=True`、`contains_done=False`，连接在 error 后正常收束。✅
- **token 字段保持 `delta`、done 保持嵌套壳**：真实 curl 落地 token 事件均 `data:{"delta":...}`（degraded 规则兜底流式冒烟）；done 仍为内嵌壳 `{code:0,data:{...}}`，未回退（AGENTS 教训③）。✅

## 3. GWT 自评
| GWT | 依据 | 结果 |
|---|---|---|
| `GET /api/series?page=1&page_size=12` → `.total>=0 && .page==1 && items 数组`；page_meta 兼容期并存且数值一致 | §2 断言 | ✅ |
| 流中后端报错 → 前端收 `event:error` + UI 错误气泡 + 连接正常关闭不悬挂 | 抓包 error 事件后无 done、HTTP 200 终止 | ✅ |
| 回归：interface_acceptance_final + vitest + chat 流式冒烟（token 正常） | 见 §5（部分归编排者 8000） | 部分边学 |

## 4. 需要编排者注意（诚实记录）
- `generate_stream`（`app/chat/generator.py:516`）自带 LLM 失败 → 规则兜底降级（自吞异常），故**常规请求下 token_aiter 不会抛**；
  本次 router error 分支是**逃逸异常的安全网**（防未捕获异常导致连接悬挂）。GWT 目标"断 LLM key 发 error"在当前 generate_stream
  自吞设计的现实路径里不会触发 error，而是降级 done——本任务按详档把 router 层的 error 分支补齐为可发（实证已发），
  若需"断 key 即 error"需改 generate_stream 策略（超范围，未改）。已在契约单 §2.4 注明触发为模拟逃逸异常。
- `interface_acceptance_final.py` 硬编码 `BASE=127.0.0.1:8000`，我未碰 8000；回归归编排者验收复验。
- 前端 vitest 未跑（任务权限聚焦 BE，禁 Playwright）；FE 仅只读核对。

## 5. 前端消费面核对（只读，未改 FE）
- courses.html:597-599 / admin-courses.html:643-662：兼容期读 `page_meta`，我的 page_meta 同源保留 → 不坏。
- chat.html:741(`delta`)、742(done 嵌套壳)、747(error→`er.message`)：与后端新契约完全对齐，error 分支现真实可达。

## 6. 兼容窗口字段
有：**`page_meta`**（本迭代保留，同源派生，权威读外层 `{total,page,page_size,items}`）。
弃用时间表已写入契约单 §3（前端 task103 切换完成后下一迭代删除，不留双源）。

## 7. 资产消费证据（A 级必填）
已调用即读文件 + 用在哪：
- **读** `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2（回传机制/独立实证/契约先行）：用在本任务"改动→独立 curl 实证→写契约单→写完工报告"纪律落地，接受验收方独立复现而非采信报告。
- **读** `C:\Users\Administrator\.agents\skills\tt\vendor\sdlc\SKILL.md`（BMAD-METHOD plan/develop/review）：用在本任务 develop（分页/SSE 改动）→ review（本报告实证）分相推进。
- **读** `C:\Users\Administrator\.agents\skills\harden\SKILL.md`（错误处理/错误码一致性）：用在本任务 SSE error 事件 `code` 复用注册表 `INTERNAL_ERROR="50000"` 而非新造野码，避免错误反馈歧义（自检修复：初稿拟用字符串常量 CHAT_STREAM_ERROR，比对 harden"错误码一致性"原则后改复用 INTERNAL_ERROR，不扩注册表）。

## 8. 自检（critique 三视角）
- 交互态：分页双字段并存不歧义（page_meta 恒同源派生）；error 事件后安全收束不悬挂。✅
- 边界：total=0/page_size 全集填充语义（cohorts page_size=total）保留；token/done 契约未回退。✅
- 错误反馈：SSE error 带可读 message + 注册表 code；第一段失败仍是普通 HTTP——两段式边界清晰。✅