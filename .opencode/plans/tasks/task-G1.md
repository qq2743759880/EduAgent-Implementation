# task-G1 — token 级并发预算 + 用户分级队列

> 执行工具：**Trae** ｜ 依赖：task26（现状） ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P5（并发非 token 级）
> 核心定位：全局 8 并发闸从"请求数"改为 **token 级速率预算**（预估 token 速率 + 用户配额），加 **L1~L3 优先级队列**（L3 大请求优先于 L1 闲聊），智能重试退避按错误类型动态——8 个闲聊不再占满闸门挡 L3 大请求。

## 1. 任务卡片

- **类型/工具**：backend（并发治理） / Trae
- **依赖**：task26（`guard.py` 现状：请求数并发闸 + Redis 分布式计数 + 队列削峰 + ZSET 分片）
- **并行组**：W2（第二批 P1，与 task-C1/O1 并行）
- **工作量**：**M**
- **测试窗口纪律**：真实 token 预估与排队行为无需 LLM，随时可测；压力场景建议错开 LLM 窗口

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **DeepSeek-V3** | MoE 架构级成本优化 + 生产 **prefill/decode 分离 + 用户分级队列** | https://arxiv.org/abs/2412.19437 |
| **通用云 LLM** | token 速率限制 + 用户配额 + 预估 token 排队 + 优先级队列 + 智能重试退避（按错误类型动态） | production-upgrade-plan.md P5 引述 |

## 3. 实现规划要点

### 3.1 token 级预算（改造 `app/ai/guard.py`）

- 新增 `TokenBudgetGuard`（在 `ConcurrencyGuard` 之上，保留既有接口 `acquire/release`）：
  - 预估函数 `estimate_request_tokens(request_meta) -> int`：`system + history + query + max_tokens` 四段求和（复用 `compaction.estimate_tokens`，历史段取调用方传入的预算化长度）；
  - 全局速率上限：`LLM_TOKEN_RATE_LIMIT_PER_MIN`（默认 600_000 token/min），用 Redis `INCRBY` + `EXPIRE` 窗口计数（Lua 原子），超限进队列；
  - 用户配额：`USER_TOKEN_QUOTA_PER_MIN`（默认 30_000 token/min），超配额返回友好提示（reason=`user_token_quota_exceeded`）；
  - **保留请求数并发闸为第二道防线**（`LLM_GLOBAL_CONCURRENCY` 仍生效，防单请求异常大 token 挤占），token 预算为第一道。
- 预估字段透传：`acquire(user_id, request_meta={model, history_tokens, query, max_tokens})`；缺失 `request_meta` 时按 `ESTIMATE_DEFAULT_TOKENS=2000` 兜底。

### 3.2 分级队列（L1~L3）

- 队列键升级：`chat:queue` 拆分为 `chat:queue:{priority}`（priority ∈ L1/L2/L3，按 effort 映射：L1=chitchat 轻请求、L2=knowledge/tool、L3=learning 大请求/strong 模型）；
- 消费者优先取 L3 → L2 → L1（`BLPOP` 轮询三个 key）；`enqueue(payload, priority)` 按 `effort` 定级；
- 排队超时分级提示：L1 沿用 10s，L3 放宽至 `QUEUE_POP_TIMEOUT_L3=30s`（大请求容忍更长排队），超时消息分级别（"当前服务繁忙，已按高优先级处理…"）。
- 配置项：

```python
LLM_TOKEN_RATE_LIMIT_PER_MIN = 600000
USER_TOKEN_QUOTA_PER_MIN = 30000
ESTIMATE_DEFAULT_TOKENS = 2000
QUEUE_POP_TIMEOUT_L3 = 30.0
QUEUE_PRIORITY_ORDER = ["L3", "L2", "L1"]
```

### 3.3 智能重试退避（改造调用方重试逻辑，联动 task-T1）

- `app/chat/generator.py` / `app/chat/flows/agent.py` 的重试路径按错误类型动态退避：
  - 限流（429/rate_limit）→ 指数退避 `min(2^n * 1s, 30s)` + jitter；
  - 超时（timeout）→ 线性退避 1s，最多 2 次；
  - 模型错误（invalid_request/model_error）→ 立即切备用模型（双源：FAST↔STRONG），不重试同模型；
  - 其余 → 1 次重试后进入 task-T1 的工具闭环。
- 退避实现放 `app/core/retry.py`（新文件，纯函数，可单测）。

### 3.4 测试

- `tests/test_contract_task_g1.py`：token 预估求和正确、Redis 速率窗口计数、L3 优先于 L1 出队、分级超时提示、退避策略表驱动测试。

## 4. 验收标准（Given/When/Then）

- **AC1（token 速率闸）**：Given 8 个 L1 闲聊请求（每请求预估 1500 token）同时到达，When `acquire`，Then 若累计速率超 `LLM_TOKEN_RATE_LIMIT_PER_MIN` 则后续请求进队列，不直接拒绝；8 个轻请求不再以请求数占满唯一闸门。
- **AC2（L3 优先）**：Given 队列同时存在 L1 闲聊 ×5 与 L3 大请求 ×1，When 消费者轮询，Then L3 请求先于所有 L1 出队执行（`QUEUE_PRIORITY_ORDER` 生效）。
- **AC3（用户配额）**：Given 用户 X 单分钟 token 用量超 `USER_TOKEN_QUOTA_PER_MIN`，When 再次请求，Then 返回 `reason="user_token_quota_exceeded"` 与友好中文提示，不 500。
- **AC4（智能退避）**：Given LLM 返回 429，When 重试，Then 按指数退避（2s/4s/8s…封顶 30s+jitter）；Given 返回超时，Then 按 1s 线性退避最多 2 次；Given 模型错误，Then 切换备用模型（FAST↔STRONG）而非重试同模型。
- **AC5（兼容回归）**：Given task26 既有 guard 契约测试（请求数并发/单用户并发/队列削峰），When 改造后运行，Then 全 PASS（原有 8 并发闸行为保留为第二道防线）。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-G1-completion-report.md`（token 速率压测、L3 优先实测、退避策略表）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"并发闸=token 速率第一道 + 请求数第二道；L3 优先队列"决策。
- **完成动作**：git commit → sync.ps1。

## 6. 批判承接

- **production-upgrade-plan.md P5**（并发非 token 级）：8 个闲聊占满闸门挡 L3 大请求 → AC1/AC2 落实。
- **critique-backlog-tracker.md**：task39「task29 批判②：P95 严重超标治理（L1 87s/L2 66s/L3 107s vs 8s）」——本任务 L3 优先 + 分级超时是 P95 治理的必要前置（大请求不再被闲聊饿死）；task39 压测验收时以本任务配置为准复测。

## 7. 与其他 task 关联

- **联动**：task-T1（重试退避状态机共用 `app/core/retry.py`）；task-O1（排队超时率指标 + 速率计数埋点）；task-C1（history 段 token 预估复用压缩后长度，避免预估虚高）。
- **执行顺序**：W2 第二批；建议在 task-O1 的 trace_id 基座就绪后实施（速率/排队事件埋点需 trace_id）。