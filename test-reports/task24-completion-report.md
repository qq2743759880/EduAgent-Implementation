# task24 完工报告：AI 助手 LangGraph 图重构（route→plan→fan-out→merge→reflect→answer）+ Redis durable execution + effort scaling

> 后端+数据库｜阶段 P4.5｜并行组 W3｜类型 agent｜执行 Trae 手动调度（dev-standard.mjs 8 阶段）
> 前置：task09/10/23（Redis 缓存/慢查询）｜后置：task25~28、前端 task50
> 交付物：`app/ai/graph.py` + `app/ai/checkpoint_redis.py` + 图拓扑 + pytest（见 §6）

---

## 1. 背景与核心决策

task92 已验收（R1 子代理独立上下文）→ 本任务把**多 agent 编排**组装为 LangGraph 图，并落地 durable execution。

**关键环境发现**：本环境 Redis(6379) 为**原生 Redis，无 RediSearch/RedisJSON 模块**。LangGraph 自带 `AsyncRedisSaver` 依赖 redisvl 向量索引（`FT.INFO`/`FT.CREATE`），在原生 Redis 上 **asetup() 抛 `RedisSearchError: unknown command FT.INFO`**（已在测试中实证复现）。

**裁决**：为满足 GWT②「中途 kill 后同 thread_id 恢复、Redis checkpoint durable execution」且兼容真实环境，新增自定义 `PlainRedisSaver`（[checkpoint_redis.py](file:///E:/stu/project/stu/EduAgent实施手册/edu-agent/app/ai/checkpoint_redis.py)）：
- 继承 `InMemorySaver`（**复用其完整 blob/write/版本号语义**，channel delta、pending writes 一致）。
- 叠加「逐线程快照 → pickle 落 Redis `edu:ckpt:{thread_id}`」：`aput`/`aput_writes` 后持久化，`aget_tuple`/`alist` 前从 Redis 回填。
- 仅依赖 `aioredis` 的 `set/get/ping`，**无 search 索引依赖**。
- 进程 kill 后新 saver 实例以同一 Redis 重建该线程内存 state，`aget_tuple` 返回最近 checkpoint，LangGraph 从该点续跑，**不重复已持久化的已完成节点**。

图拓扑（[task24-graph-topology.md](file:///E:/stu/project/stu/EduAgent实施手册/.opencode/plans/tasks/task24-graph-topology.md) 含 mermaid）：
`START → route → (chitchat 直连) answer`｜`route → plan → fan_out → merge → reflect → answer`（reflect 不足回 plan，≤MAX_REFLECT=2）。

---

## 2. 验收标准逐条核验（GWT 全文）

### ① Given 四类意图样本，When 逐一请求，Then 路由正确分发；chitchat 直连 answer_node（1 次 fast 调用）；knowledge 走 plan→fan-out→merge→reflect→answer
**判定：✅ PASS**

| 用例 | 期望 | 实测 |
|------|------|------|
| chitchat（你好） | 直连 answer，节点仅 route+answer | `route,answer`（无 plan/fan_out）✅ |
| knowledge（现在完成时…） | plan→fan_out→merge→reflect→answer | 六节点全经 ✅，产出 subagent_results ✅ |
| tool（计算 123+456） | 路由到 tool | intent=tool ✅ |
| learning（怎么学好英语） | 路由到 learning | intent=learning ✅ |

证据：`tests/test_contract_task24.py::TestIntentRouting`（chitchat 断言 `"plan" not in executed`；knowledge 断言六节点全在）3 用例全过。

### ② Given 图中途进程崩溃（注入 kill），When 同 thread_id 重新 ainvoke，Then 从最近 Redis checkpoint 恢复继续执行（durable execution），不重复已完成节点
**判定：✅ PASS（真实 Redis 集成验证）**

- **契约测试**（`TestDurableExecution`，真实 Redis 6379 + `PlainRedisSaver`）：首轮注入 `boom_answer` 截断 → **全新 saver 实例**（模拟进程重启）+ 同 thread_id 续跑 → `final_answer == "FINAL_ANSWER"` 且 `route/plan/fan_out/merge/reflect` **各仅执行 1 次**（checkpoint 恢复不重复）。
- **运行时脚本**（`scripts/_verify_task24_durable.py`，独立于 pytest）：
```
[task24-verify] 恢复后 state.v = 2 (期望 2，由最近 checkpoint 续跑)
[task24-verify] redis 持久化 key = ['edu:ckpt:t24-verify']
[task24-verify] PASS: Redis durable execution 恢复正确
```

### ③ Given 多任务 plan（2 个独立子代理任务），When 执行，Then 并行完成（asyncio.gather，总耗时 ≈ max 而非 sum）；state 中 user_id 为真实用户（grep 无 user_id=1）
**判定：✅ PASS**

- **并行性**：`TestParallelFanoutAndRealUser` 实测 2 子代理各 delay 0.35s → `elapsed < 0.7s`（≈max 非 sum）；knowledge→effort=L1 ✅。
- **真实 user_id**：state.user_id=5555，`SubagentTask.user_id == 5555`、`thread_id == "sess-9"` ✅；源扫描 `app/ai/` 下 **无 `user_id=1` 硬编码** ✅。

---

## 3. 独立子代理红线审查（R1-R5，独立上下文审查后修复 1 处）

| 项 | 判定 | 核心证据 |
|----|------|------|
| R1 独立上下文/隔离 | ✅ PASS | fan-out 走 task92 `run_subagents`（`runner.py:269-273` 每子代理独立新 messages）；工具服务 `_build_tool_services` 每请求闭包绑定 user_id/thread_id 不清号（`graph.py:252-288`） |
| R2 正确性 | ✅ PASS | 四类路由、chitchat 直连、knowledge 全管线、checkpoint 不重复、effort 保守（L1=2/L2=3，不超文档上限） |
| R3 契约/健壮性 | ✅ PASS | route/reflect/answer 均有 try/except 降级；Redis 不可用降级无 checkpoint；plain Redis 无 search 模块可用；gather `return_exceptions=True` 不取消整批 |
| R4 安全 | ✅ PASS（修复后） | **修复**：`graph.py:293` 原 `state.get("user_id", 1)` 兜底默认 1 → 改为 `int(state["user_id"])` 显式取值（缺失即报错，根除降级越权风险）；artifact key `uuid4().hex` 不可预测；主 state 仅收 ≤2000 token 蒸馏摘要，原文落 Redis artifact |
| R5 性能/边界 | ✅ PASS | asyncio.gather 并行 ≈max；摘要 ≤SUBAGENT_SUMMARY_BUDGET；reflect ≤MAX_REFLECT_ITERATIONS 防死循环；空 tasks/空 LLM 输出兜底 |

**采纳的非阻断建议（记录，未越界实现）**：
- `run_agent` 返回的 `docs/graph_entities/tool_results` 当前为空列表（真实检索在子代理内、原文进 artifact）。属引用回传回归点，需前端 task50 联调/后续任务把蒸馏摘要或 artifact 引用映射回 `docs` —— 非本任务红线，如实记录待联调。
- `chat_stream` 流式仍走旧 `run_agent_turn`，本次仅接非流式；流式接线留后续（非红线）。

---

## 4. 测试与工程质量

- `tests/test_contract_task24.py`：**7/7 通过**（GWT① 3 + GWT② durable 1 + GWT③ 3，含真实 Redis durable execution）。
- task92 回归：`tests/test_contract_task92.py` **6/6 通过**。合计 **13/13**。
- `scripts/_verify_task24_durable.py`：真实 Redis durable execution 独立验证 PASS（key=`edu:ckpt:t24-verify`）。
- `compileall` + 语法诊断：0 错误；`app.ai.graph` / `app.ai.checkpoint_redis` / `app.chat.service` 导入链路正常（`imports OK`）。
- grep 审计：`app/ai/` 无 `user_id=1`；`grep -rn "user_id=1"` 其余命中为 `auth/dependencies.py`(虚拟管理员) 与 `admin/rag_admin/service.py`(显式 ADMIN 虚拟) —— 均属既有管理者虚拟身份，非 AI 助手用户路径。

> 全量回归说明：`pytest -q` 91 failed 均分布在 trade/refund/breaker/course-domain/error-codes/after-sales 等**未改模块**（与 task24 无 import 依赖，`grep` 验证这些测试未引用本任务模块）；属既有环境/基础设施回归，非本任务引入，如实记录待后续编排处理。

---

## 5. 数据库校验

任务无 MySQL 数据模型变更（纯编排层）；Redis durable execution 已用 RunCommand + Python（集成 pytest + 独立脚本）真实校验，非 MOCK。

---

## 6. 交付物清单

| 产物 | 路径 |
|------|------|
| LangGraph 图实现 | `edu-agent/app/ai/graph.py` |
| 原生 Redis durable checkpointer（新增） | `edu-agent/app/ai/checkpoint_redis.py` |
| 契约测试 | `edu-agent/tests/test_contract_task24.py` |
| 运行时验证脚本（新增） | `edu-agent/scripts/_verify_task24_durable.py` |
| 图拓扑说明（mermaid） | `.opencode/plans/tasks/task24-graph-topology.md` |
| 接线 | `edu-agent/app/chat/service.py`（import 改 `app.ai.graph`）、`edu-agent/app/config.py`（`MAX_REFLECT_ITERATIONS=2`） |

## 7. 交接与记忆

- 看板 task24 → 编次者验收（未验收不进入 task25）。
- sync.ps1 已运行；本任务新增文件无将产物写回 AI-Hub（AI 助手代码属项目，不走 .ai-hub 资产中心）。

**固化纪律**：依据 task92/24 经验——凡涉及 Redis 持久化需先核实 RediSearch 模块可用性；本机原生 Redis 用 `PlainRedisSaver`，已验证 durable execution 恢复正确（不重复已完成节点）。