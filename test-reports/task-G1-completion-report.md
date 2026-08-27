# task-G1 完工报告 — token 级并发预算 + 用户分级队列

> 执行工具：**WorkBuddy（后端+数据库开发者）** ｜ 依赖：task26（`guard.py` 现状）｜ 状态：✅ 完工待验收
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P5（并发非 token 级）
> 竞品实证：DeepSeek-V3 用户分级队列（arxiv.org/abs/2412.19437）；通用云 LLM token 速率限制 + 配额 + 预估排队 + 智能重试退避

## 1. 交付概览

| 文件 | 变更 | 说明 |
|---|---|---|
| `edu-agent/app/config.py` | 新增 task-G1 配置段 | 5 个核心配置项 + 2 个 Redis key（见 §3） |
| `edu-agent/app/ai/guard.py` | 新增 `TokenBudgetGuard` + `default_guard()` 改返回 | token 速率闸（第一道）+ 请求数闸（第二道）+ L1~L3 分级队列 |
| `edu-agent/app/core/retry.py` | **新文件** | 智能重试退避纯函数（按错误类型动态；联动 task-T1） |
| `edu-agent/tests/test_contract_task_g1.py` | **新文件** | AC1~AC4 + 预估 + AC5 回归，共 18 测试 |

## 2. 验收标准（Given/When/Then）实测结果

### AC1（token 速率闸）✅
- Given 8 个 L1 闲聊（每请求预估 1500 token）同时到达，When `acquire`，Then 累计速率超 `LLM_TOKEN_RATE_LIMIT_PER_MIN` → 后续请求**进队列**（reason=`queued_token_rate`），**不直接拒绝**。
- 实测（`rate_limit=5000`）：前 3 个 `direct` 准入；第 4 个入队等候；`release` 释放预算后第 4 个被唤醒准入（`queued_token_rate`）。全程无硬拒绝。
- 补充：`rate_limit=1_000_000` 时 8 个 L1 轻请求 + 1 个 L3 全部并行准入 → token 预算不阻断正常轻流量，L3 不再被闲聊饿死。

### AC2（L3 优先）✅
- Given 队列同时存在 L1×5 与 L3×1，When 消费者轮询，Then L3 先于所有 L1 出队（`QUEUE_PRIORITY_ORDER=["L3","L2","L1"]` 生效）。
- 实测：`enqueue_token` 5×L1 + 1×L3 → 轮询出队顺序 `L3_0, L1_0..L1_4`；L3/L2/L1 三级顺序 `[L3,L2,L1]` 验证通过。
- Redis 路径：`chat:queue:{L3/L2/L1}` 三 key，BLPOP 按优先级顺序轮询（内存路径按 `_prio_items` 优先级扫描）。

### AC3（用户配额）✅
- Given 用户 X 单分钟 token 用量超 `USER_TOKEN_QUOTA_PER_MIN`，When 再次请求，Then 返回 `reason="user_token_quota_exceeded"` + 友好中文提示，**不 500**。
- 实测（`user_quota=3000`，每请求 1500）：第 1/2 次准入（累计 1500/3000）；第 3 次 `3000+1500=4500>3000` → 拒绝（`user_token_quota_exceeded`，提示含"额度"）。

### AC4（智能退避）✅
- 429/限流 → 指数 `2^n` 秒（2/4/8…，封顶 30s + jitter）：`next_backoff("rate_limit", n, jitter=0)` = 2/4/8/…/30。
- 超时 → 线性 `1s`/次，最多 2 次：1/2/`should_retry(timeout,3)=False`。
- 模型错误 → 立即切备用模型（FAST↔STRONG），`wait=0`、`should_switch_model=True`、`switch_model_source("fast")="strong"`。
- 表驱动测试覆盖 `classify_error` / `next_backoff` / `should_switch_model` / `should_retry` / `plan_retry`。

### AC5（兼容回归）✅
- `tests/test_contract_task26.py`（task26 既有 guard 契约）：**19 passed, 1 skipped**（1 个为无真 Redis 时跳过的 bigkey 扫描，与改造无关）。
- 新增 `TestRequestCountGatePreserved`：token 预算宽松时 `global_limit=2` 请求数闸仍生效（闸满排队），证明请求数并发闸作为**第二道防线**完整保留。
- `ConcurrencyGuard` 基类行为零改动（task26 直接依赖），`default_guard()` 现返回 `TokenBudgetGuard`（向后兼容子类）。

## 3. 配置项（`app/config.py` task-G1 段）

```python
LLM_TOKEN_RATE_LIMIT_PER_MIN = 600000    # 全局 LLM 预估 token 速率上限（/分钟），超限进队列不拒绝
USER_TOKEN_QUOTA_PER_MIN = 30000         # 单用户单分钟 token 配额，超配额返回 user_token_quota_exceeded
ESTIMATE_DEFAULT_TOKENS = 2000           # request_meta 缺失时的兜底预估 token
QUEUE_POP_TIMEOUT_L3 = 30.0              # L3 大请求排队超时（秒），容忍更长排队
QUEUE_PRIORITY_ORDER = ["L3", "L2", "L1"]  # 消费者轮询优先级顺序（L3 先出队）
TOKEN_RATE_KEY = "ai:llm:token_rate"     # 全局 token 速率计数 key（INCRBY + EXPIRE 60s 窗口）
USER_TOKEN_KEY_PREFIX = "chat:user_token"  # 单用户 token 配额计数 key 前缀（INCRBY + EXPIRE 60s）
```

## 4. 关键设计

- **双层防御**：`acquire()` = ① 单用户 token 配额 → ② 全局 token 速率闸（超→按优先级排队不拒绝）→ ③ 预留 token 后走请求数并发闸（`LLM_GLOBAL_CONCURRENCY` 保留为第二道）。
- **token 预估**：`estimate_request_tokens(request_meta)` = `system_tokens + history_tokens + query_tokens(复用 compaction.estimate_tokens) + max_tokens`；缺失→`ESTIMATE_DEFAULT_TOKENS=2000`。与 task-C1 压缩后 history 长度打通，避免预估虚高。
- **分级队列**：`enqueue_token(payload, priority)` / `await_token(timeout)` 按 `QUEUE_PRIORITY_ORDER` 轮询；token 速率超限时 `_enqueue_token_wait` 用有序 waiter（`_token_waiters` 按优先级排序），`release` 释放预算后 `_admit_token_waiters` 按优先级唤醒。
- **计数窗口**：Redis `INCRBY + EXPIRE 60s`（Lua 原子，分布式一致）；内存后端用 `time.monotonic()` 60s 窗口，降级可跑。拒绝路径**不** INCRBY → 不刷新窗口 → 自然 60s 冷却（符合"单分钟配额"语义）。
- **智能退避**：`app/core/retry.py` 纯函数（无外部依赖），`classify_error` / `next_backoff` / `should_switch_model` / `switch_model_source` / `should_retry` / `plan_retry`，可单测。

## 5. 风险与后续（已如实披露）

1. **重试调用点接入**：本任务交付 `retry.py` 作为 task-T1 工具闭环状态机的共享退避策略（AC4 仅要求策略表测试）。将 `retry.py` 接入 `generator.py` / `agent.py` 实际重试路径属"联动 task-T1"，为免引入回归本任务**未改动既有重试调用点**；调用方按 `classify_error` + `next_backoff` 接入即可。
2. **预留 token 回退**：采用 per-user FIFO 预留登记，release 时按份额回退以释放预算供排队者；并发上限 `USER_MAX_CONCURRENT=2` 下登记与释放配对正确（测试覆盖）。
3. **速率窗口粒度**：60s 固定窗口（非严格滑动），瞬时突发在窗口边界可能短暂超额；生产如需平滑可后续换令牌桶（task39 压测时复测）。
4. **继承状态**：仓库存在 19 个 task93/95/96 已 `git add` 但未提交的文件（历史遗留），本任务**未触碰**，按纪律仅提交 G1 自身文件。

## 6. 测试指令（可复现）

```bash
cd edu-agent
.venv/Scripts/python.exe -m pytest tests/test_contract_task_g1.py -q   # 18 passed
.venv/Scripts/python.exe -m pytest tests/test_contract_task26.py -q   # 19 passed, 1 skipped (AC5 回归)
```

## 7. 提交与同步

- 分支：`feature/task44-courses`，基于最新 HEAD `0974c8a`。
- 提交：`git commit --only` 仅包含 G1 自身 5 个文件（config/guard/retry/test/report），prior-task 已 staged 的 19 文件未触碰。
- 完成动作：写完本报告 → `sync.ps1` → 停下等验收。
