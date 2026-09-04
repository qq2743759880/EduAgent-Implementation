# Task114 / Task115 契约统一收尾 — 完工报告（响应壳 + 分页 SSE）

> 执行 agent：P2 优先级 ｜ 项目：EduAgent 重构 ｜ 日期：2026-09-04 ｜ 不 commit
> 契约冻结（C-A/C-B）已生效：响应壳 `{code:0,message:"ok",data}`、分页 `{total,page,page_size,items}`、无 `page_meta` 双轨、SSE 两段式错误。

***

## 0. 结论总述（TL;DR）

- **后端** **`edu-agent/app`** **无任何真** **`page_meta`** **残留要删** —— 全量扫描 `rg -n "page_meta" edu-agent/app` 共 9 处命中，逐行核实**全部为注释 / docstring**，无一处是生效的字段定义、DTO 组装或返回体。C2 已真删字段，本任务只需"核实 + 实证"，无需改任何后端代码。

- **前端** **`edu-frontend/public`** **静态页零** **`page_meta`** **消费** —— 无需同步。

- **响应壳无双轨残留** —— 全站达成 `ok(data=...)`；无裸 dict / 双轨壳。

- **SSE 两段式错误模型未回退** —— 连接前 HTTP 错误 + 流中 `event:error` 均完整实现。

- **独立实证通过** —— 4 个分页端点真实 HTTP 返回 `data={total,page,page_size,items}`、无 `page_meta`。

- 本次**代码改动为 0**（`git status edu-agent/app` 干净），因为已无残留可清；强行删注释/删旧脚本属超范围改动，按 ponytail 最小 diff 不执行，落「需决策」清单。

***

## 1. 资产消费证据段

**必须消费的 4 个资产全部加载并实际作用于判定：**

| 资产                                                                  | 消费动作                   | 对本任务的自检发现                                                                                                                                                                                                          |
| ------------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md`           | 全文加载（ladder/rules）     | 按"最小 diff、只清残留、不改已冻结正确契约、Deletion over addition 但**拒绝无谓 churn**"裁决：9 处 `page_meta` 均为准确历史注释，删注释=为删而删的无效 churn → **保留**；旧烟测脚本引用**已失效契约**且有误导/重跑假失败风险 → 标记，交由决策（见 §7），但**不在本任务范围改动**（`重点后端` + `edu-frontend/public`） |
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2（回传机制/契约冻结） | 落实"真实契约为准、验收独立实证不采信报告" | 用**真实 HTTP + 真实回归脉冲**验证契约，而非仅读代码；对报告声称的"残留"逐处独立核实（最终证明是历史行）                                                                                                                                                        |
| `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md`   | 加载 review 簇内核          | `Preserve polish YAGNI and minimum-change` 确认：不新增本任务不需要的工作                                                                                                                                                         |
| `C:\Users\Administrator\.agents\skills\harden\SKILL.md`             | 加载"低估异常/边界"视角          | 对滚动扫描覆盖所有跨域文件（course/market**及全 app**、前端 public+src、tests、scripts）；对 SSE `event:error` 可区分错误码逐段核对；对分页边界 `page/page_size` 白名单、`page_size≤100` 复核                                                                    |

**assetConsumed 指纹**：ponytail / tt §5.2 / review / harden 已消费；`sku` 内核词含 ponytail ladder、tt 验收独立实证、review 最小改动、harden 边界覆盖。

***

## 2. agent × skill × workflow 矩阵

| 层     | agent       | skill                                        | workflow / 纪律             |
| ----- | ----------- | -------------------------------------------- | ------------------------- |
| 编排/纪律 | 主 agent（P2） | `tt` SKILL.md §5.2（独立实证验收）、ponytail（最小 diff） | 真实契约为准；不 commit；只清残留      |
| 评审    | review 簇    | `tt/vendor/review/SKILL.md`（最小改动 YAGNI）      | 交付前按 critique 三视角自检       |
| 加固    | harden      | `harden/SKILL.md`                            | 跨域全量覆盖 + 边界/错误通道核对        |
| 后端    | 本执行 agent   | `rg`+`Read` 静态审计 + `.venv` 真实 HTTP           | 契约冻结 C-A/C-B；私有响应壳 `ok()` |
| 实证    | 本执行 agent   | `.venv` requests + `pytest`                  | **独立实证，不采信报告**；回归脉冲覆盖受影响域 |

***

## 3. page\_meta 残留全表 → 判定 → 删除清单

### 3.1 全量扫描（`rg -n "page_meta" edu-agent/app` 全部命中）

| 文件:行                                | 内容摘要                                            | 判定：真残留 or 注释 | 处理 |
| ----------------------------------- | ----------------------------------------------- | ------------ | -- |
| `app/domains/course/service.py:78`  | docstring `无 page_meta`                         | 注释/历史说明      | 保留 |
| `app/domains/course/service.py:109` | 注释 `page_meta 双轨已删`                             | 注释/历史说明      | 保留 |
| `app/domains/course/service.py:149` | 注释 `无 page_meta`                                | 注释/历史说明      | 保留 |
| `app/domains/course/schemas.py:6`   | 模块 docstring `无 page_meta 双轨，C2 已删`             | 注释           | 保留 |
| `app/domains/course/schemas.py:42`  | `SeriesListData` docstring `C2 已删 page_meta 双轨` | docstring    | 保留 |
| `app/domains/course/schemas.py:101` | `CohortListData` docstring `C2 已删 page_meta 双轨` | docstring    | 保留 |
| `app/domains/course/router.py:70`   | 注释 `C2 删 page_meta，不再是裸列表`                      | 注释/历史说明      | 保留 |
| `app/domains/market/schemas.py:5`   | 模块 docstring `page_meta 不在本域使用`                 | 注释           | 保留 |
| `app/domains/market/schemas.py:57`  | `CouponPage` docstring `非 page_meta`            | docstring    | 保留 |

**核实**：course 域 `SeriesListData`/`CohortListData` 与 market 域 `CouponPage` 的**模型字段都是** **`{total,page,page_size,items}`** **四项**，无 `page_meta`；`svc.list_series`/`list_cohorts`/`list_my_coupons`/`list_favorites` 组装 dict/pydantic 均只含这四项。**无真残留。**

> **结论**：任务说明中点名的 4 文件 9 处均为"历史行"，走"仅核实"分支。**删除清单：空（0 处）**。

***

## 4. 前端 page\_meta 消费同步结论

- `rg -n "page_meta" edu-frontend/public` → **0 命中**。静态页（含 `public/edu-api.js`）**均不消费 page\_meta**，分页统一读外层 `{total,page,page_size,items}`。→ **静态页无需同步**。

- 附带核实：`edu-frontend/src`（Next.js React 冻结实现）：`curriculum.ts:102/217`、`admin/courses.ts:315` 有 `page_meta?:` **可选过渡期兼容类型声明**，且**不再被任何页面消费**（页面读外层 triple，`courses/page.tsx:52` 明确"不再消费 page\_meta 兼容字段"）。属 C-B 冻结前期的显式兼容声明，非消费；非本任务 `public/` 范围，不动。→ 见 §7 需决策。

***

## 5. 响应壳双轨残留修复清单

扫描 `return {"code"…` / 裸 `return` dict / `.body=` ：

- `app/core/resp.py`：`ok()/fail()` 统一 `{code,message,data}`，`Shell[T]`/`RespModel` OpenAPI 壳形态，C1 已建 `openapi_shell.py` 未动（边界内）。

- course 域 router：5 端点全用 `ok(data=...)`（`router.py:52/61/74/83/92`）。

- market 域 router：全用 `ok(data=...)`（`router.py:45/59/62/71/84/93/102`）。

- chat 域 router：非流式用 `ok(...)`；SSE `done` 帧按"契约① SSE 例外"内嵌 `{code:0,message:"ok",data:{...}}`。

- 全局裸 dict 命中仅 `app/_archived/question_admin`（归档代码，非活跃，跳过）与 ai 工具内部 dict（非 HTTP 响应）。

- **双轨残留修复清单：空（0 处）**。

***

## 6. SSE（task115）未回退确认

`app/chat/router.py` 两段式错误模型完整，**未回退**：

- **第一段·建连前**：`service_chat_stream` 初始化抛错 → `_translate_exception` 同步 HTTP 4xx/5xx（`router.py:269-281`）；`get_current_user` 依赖在 `DEBUG=False` 时对无 token 直接 `HTTP 401`（`app/auth/dependencies.py` 规则 3）。

- **第二段·建连后 token 迭代失败** → 流内 `event: error`，code 用 `_map_stream_exception` 映射为可区分码 `LLM_AUTH/LLM_TIMEOUT/LLM_RATE_LIMIT/LLM_UNAVAILABLE/SERVICE_DOWNSTREAM`（`router.py:306-315`），已从固定 50000 提升。

- **第三段·落库失败** → `event: error`（`CHAT_PERSIST_FAIL`）+ 补带 degraded 的 `done` 兜底（`router.py:319-347`）。

- 事件序保持契约：`start → retrieval → token{delta} → done / error`。

**实测**：`POST /api/chat/stream`（body `{query}`，无 token）在**当前运行** **`DEBUG=true`（`.env:4`）** 下返回 200 —— 这是 `get_current_user` 规则 2 的**虚拟管理员降级**（AGENTS.md 关键教训 #6 已知行为），**非本次回退**；代码路径（规则 3）在 `DEBUG=False` 时 401 正确。契约正确性由代码路径 + 关停 DEBUG 后即 401 保障，未动。

***

## 7. 独立实证（真实 HTTP + 回归）

### 7.1 分页端点真实响应（`edu-agent/.venv` requests，登录 student `user000001`）

| 端点                                              | 鉴权     | HTTP | `data` 键集合                     | `page_meta` |
| ----------------------------------------------- | ------ | ---- | ------------------------------ | ----------- |
| `GET /api/series?page=1&page_size=5`            | Bearer | 200  | `{items,page,page_size,total}` | 无 ✅         |
| `GET /api/series/1/cohorts`                     | Bearer | 200  | `{items,page,page_size,total}` | 无 ✅         |
| `GET /api/coupons?page=1&page_size=5`（market）   | Bearer | 200  | `{items,page,page_size,total}` | 无 ✅         |
| `GET /api/favorites?page=1&page_size=5`（market） | Bearer | 200  | `{items,page,page_size,total}` | 无 ✅         |

> 实体已断言 `set(data.keys())=={'total','page','page_size','items'}` 且 `'page_meta' not in data`。外层壳 `GET /api/auth/me` 复验 `code=0 / data` 存在。
> 说明：键序显示 `items` 在前，但**集合相等**于冻结契约 `{total,page,page_size,items}`，无分页元字段缺失。

### 7.2 受影响域回归（`.venv pytest`，工程命令，含 DB）

`tests/test_course_domain.py test_contract_task39.py test_contract_task16.py test_contract_task17.py test_contract_task_c2.py test_chat_stream_error.py`
→ **83 passed / 5 failed / 2 skipped**

**通过项**（本任务权威契约相关）：

- `test_course_domain.py`：series 列表分页 `{total,page,page_size,items}` 形状、排序、分类、详情等全部通过（**本次唯一失败是该文件的 p95 延迟性能断言，见下**，非契约形状）。

- `test_contract_task39.py`：班次分页壳（cohorts `CohortListData`）通过。

- `test_contract_task16.py`：market 优惠券/收藏分页壳通过。

- `test_chat_stream_error.py`：SSE 两段式错误码通过。

**5 个失败均与本任务范围无关（均为既有/环境性，非本次改动引入——本次** **`/edu-agent/app`** **代码改动为 0）**：

| 失败                                                       | 原因                                           | 与 task114/115 关系                                      |
| -------------------------------------------------------- | -------------------------------------------- | ----------------------------------------------------- |
| `test_course_domain::test_p95_latency_under_200ms`       | P95≈2398ms（样本全 \~2000ms，机器负载/环境冷态）           | **性能门**，非契约形状；分页壳形状断言通过                               |
| `test_contract_task17`（3 例）                              | 下单返回 `code 40420`（HTTP 404 映射）；trade 域下单执行链路 | **trade/order 域运行态**，与 course/market 分页 page\_meta 无涉 |
| `test_contract_task_c2::test_expand_schema_returns_full` | `expand_schema("calculator")` 返回 None        | **C2 MCP schema 展开**，独立于分页/壳契约                        |

### 7.3 SSE 无登录签订

见 §6：`DEBUG=true` 虚拟管理员降级返回 200；`DEBUG=False` 路径 401（代码规则 3）。不跑真 LLM（符合任务约束）。

***

## 8. 需决策清单（不进本任务改动，ponytail 最小 diff）

1. **旧一次性烟测脚本**：`edu-agent/scripts/_smoke_task11.py`、`_smoke_task12.py`、`_smoke_full.py`、`_run_full.py`、`_challenge_task11.py` 内仍有针对**已撤销契约** `page_meta` 的硬断言（如 `_smoke_task11.py:74`、`_smoke_full.py:73`）。它们不在 `pytest` 套件内、已被 `test-reports/interface_acceptance_final.py` 取代；**保留会误导未来** **`rg page_meta`** **审计、重跑会假失败**。建议后续单独决定：删除或迁移为读取外层 triple。**本次未动**（历史脚本、非 app 代码、非 `public/` 范围）。
2. **历史准确注释**（§3.1 的 9 处）：保留（准确描述字段已删，防重新引入），不建议为"清零"而删。
3. **前端** **`src/`** **冻结实现的** **`page_meta?:`** **可选兼容类型声明**（`curriculum.ts:102/217`、`admin/courses.ts:315`）：非消费、非 `public/`，属 C-B 前期兼容设计；如需彻底移除可后续在 C-B 前端签收时清理。

***

## 9. 完成度对照任务清单

| # | 任务                       | 结果                                             |
| - | ------------------------ | ---------------------------------------------- |
| 1 | 全量扫描 page\_meta 残留并逐处判定  | ✅ 全 app 列出，均注释，无真残留                            |
| 2 | 删除真残留、统一外层分页             | ✅ 无真残留可删；course/market 分页 DTO 与全站契约一致          |
| 3 | 前端同步                     | ✅ `public/`（含 edu-api.js）零 page\_meta 消费，无需同步  |
| 4 | 响应壳双轨残留                  | ✅ 无裸 DTO/双轨壳（全 `ok(data=...)`）                 |
| 5 | SSE 两段式未回退               | ✅ 完整（连接前 HTTP + 流内 error），`DEBUG=false` 路径 401 |
| 6 | 独立实证分页无 page\_meta + SSE | ✅ 4 端点实测 data 无 page\_meta；SSE 见 §6            |
| 7 | 全量回归                     | ✅ 受控域 83 过；5 败为环境/他域，非本任务                      |

