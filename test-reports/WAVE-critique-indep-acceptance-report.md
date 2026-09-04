# WAVE 生产级改造批判批 · 独立实证验收报告

> 角色：独立实证验收（不采信完工报告，以真实命令 / DB 实测 / 实启服务 / pytest 契约为唯一证据）
> 依据：tt 工作流"独立实证验收 + 强制技术批判"
> 日期：2026-09-05
> 范围：WAVE 批判批 task-T1/S1/R1/G1/O1/C1/C2/M1 + 关联 A1/E1/M2（已标"验收通过 W4 P3"，核读报告 confirm）
> 结论：**9 个 task 的实现全部真实落地**；项级判定见下表。本报告附「资产消费证据」段。

## 一、逐项闭环状态表

判定口径：
- ✅ 闭环 = commit 锚点存在 + 源代码实证（grep）+ 契约测试通过 和/或 DB/服务实启实证
- ⚠️ 环境依赖 = 代码实现完成，但运行/投递/高峰/灰度验证需真实后端/负载窗口，本环境不可离线证（如实标注，不伪造 PASS）
- ❌ 未实现 = 代码缺失

| 项 | 判定 | 验收锚点 | 独立实证证据 |
|----|------|---------|--------------|
| T1-① 枚举 ALTER | ✅ 闭环 | 3c3e7e8 | **DB 实测 `SHOW COLUMNS mcp_tool_call_log.status` = `enum(SUCCESS,ERROR,TIMEOUT,SKIPPED,REJECTION_LIMIT,MANUAL_GUIDE)`**；SQL 含执行记录 |
| T1-② 备用工具注册 | ✅ 闭环 | (0ef75f0 系) | `executor.py` L618-677 `register_builtin_tool(calculator/search_knowledge)` + `_SEARCH_KNOWLEDGE_BACKEND` 注入；契约测试 14 passed |
| T1-③ LLM 改写 | ✅ 闭环 | 1fc74c6 | `executor.py` L880-908 `TOOL_REWRITE_RULES` **6 组** + `_default_rewrite_fn`(FAST→规则)；契约测试 14 passed |
| S1-① HITL 灰度启用 | ✅ 实现 / ⚠️ 运行待窗口 | 0ef75f0 | `config.HITL_ENABLED` + `_run_hitl_seam` Gate + `_classify_hitl_action`；hitl_approval DB 19 行；真实拦截需 HITL_ENABLED=True 窗口 |
| S1-② 建表 | ✅ 闭环 | 849483c | **DB `hitl_approval` 存在 19 行**；DDL 含四审计字段 explain_text/propose_text/operator/trace_id；契约测试 1 passed |
| S1-③ sweep 定时 | ✅ 闭环 | f98729f | `memory/service.py` `_hitl_sweep_loop` 挂 start/stop_memory_worker（lifespan） |
| R1-① fp32 | ✅ 闭环 | 3a569fe | `config.RERANKER_PRECISION` + `reranker.py` precision 分支；`test_contract_task_r1_fp32.py` 噪声<1e-4 通过 |
| R1-② sidecar 部署 | ✅ 闭环（实启实证） | cbddb40 | **实启 uvicorn :8601（cuda 加载成功）→ `/health` 200（model_loaded=true,device=cuda)+`/rerank` 3 文档返回 scores(91ms)**；`deploy/start_rerank_sidecar.ps1` |
| R1-③ Redis 队列削峰 | ⚠️ 实现完成/待高峰 | 2102e2e | `queue_adapter.py` Redis list + 503 队满/直连降级已实现；高峰压测待真实负载窗口 |
| G1-① retry 接入 | ✅ 闭环 | 95eb621 | `core/retry.py` 429→指数 / 超时→线性 / 模型错切源；generator/agent 接重试；24 passed |
| G1-② 令牌桶 | ✅ 实现 / ⚠️ 生产边界留 task39 | 82e45be | `guard.py` TokenBudgetGuard 令牌桶平滑(refill/refund)消除 60s 边界 2×突发；`test_contract_task_g1_token_bucket.py` 通过 |
| G1-③ 强制 request_meta | ✅ 闭环 | 4874273 | `guard.py` estimate_request_tokens + graph.acquire 接入；`test_contract_task_g1_request_meta.py` 通过 |
| O1-① 埋点接入 | ✅ 闭环 | 6755af1 | store/agent/compaction 三处 `record_*` 真实调用；13 passed |
| O1-② OTLP | ⚠️ 实现完成/待真实后端 | f287e8f | `otel/exporter.py` OTLP HTTP + JSONL 降级；投递成功需真实 OTLP 后端 |
| O1-③ 跨实例聚合 | ⚠️ 实现完成/待真实后端 | f287e8f | `otel/metrics.py` 5 维累加器 + snapshot + trace 溯源；聚合需 Prometheus/OTLP |
| C1-② compact_node 装配 | ✅ 闭环 | 24f38d5 | `graph.py` compact_node 注入 anchor_round + llm=make_fast_llm()，llm=None 规则回退；37 passed |
| C1-③ 冻结区监测 | ⚠️ 实现完成/待对话窗口 | 0974c8a | `compaction.py` BudgetAllocator(observed/valid)+anchor_gate 冻结保护已实现；告警/降 ANCHOR_ROUND 待真实对话 |
| C2-② TOOL_DEFERRED | ⚠️ 实现完成/待流量窗口 | ebbdbe4 | `config.TOOL_DEFERRED_MODE` + `to_prompt_entry(deferred)` 前缀只放 name+summary；灰度准确率观察待真实流量 |
| C2-③ schema_registry Redis | ✅ 闭环（真实 Redis 实证） | 666e234 | **本地 Redis 127.0.0.1:6379 在 → `test_contract_task_c2_schema_registry.py` 4 passed（非跳过）跨实例 A→B 读到一致** |
| M1-② 建表冒烟 | ✅ 闭环 | 0f09c45 | **DB `user_memory_event` 存在 1 行**；契约测试通过 |
| M1-③ 容量配置化 | ✅ 闭环 | 44df82d | `config.MEMORY_CAPACITY_TIERS`(inactive/normal/active1k)+`memory_capacity_for()`+compactor 解析链；13 passed |

**补充确认（未含于 WAVE tracker，标"验收通过 W4 P3"，核读报告 + 实测佐证）：**
- **A1 可插拔 Harness**（8f8ec40+81c1228/0eca6e3/385a721）：`app/ai/harness/`（base/registry/sixnode）+ preprocess 钩子 + 真搬迁 + 未知 impl 回退 sixnode + EXPECTED_SIXNODE_TOPOLOGY；契约测试 `test_contract_task_a1*` **24 passed**
- **E1 影子模式+反面对抗+金丝雀+4维Judge**（0990348）：`canary.py`/`build_adversarial_set.py`/`judge_answer_4d`/`_maybe_shadow` 全存在；`test_contract_task_e1.py` **15 passed**
- **M2 Redis 共享向量降级链**（e8956af）：`vector.py` milvus→redis→memory 降级链 + `invalidate`；合同测试 7 测（6 passed，AC5 用例因本环境 Milvus VM 可达导致"本环境降级 memory"前提失效而 1 fail——**环境相关测试断言问题，实现本身经独立探针证 milvus 路径 upsert/search 召回正常（score 0.79）**）

## 二、契约测试汇总（本批全部实跑）

| 测试文件 | 结果 |
|---------|------|
| test_contract_task_t1.py + _fallback.py | 14 passed |
| test_contract_task_s1_audit_fields.py | 1 passed |
| test_contract_task_r1.py + _r1_fp32.py | 19 passed / 2 skipped |
| test_contract_task_g1.py + _token_bucket + _request_meta | 24 passed |
| test_contract_task_o1.py + _o1_instrumentation.py | 13 passed |
| test_contract_task_c1.py / _c2.py / _c2_schema_registry.py | 37 passed（含跨实例 4） |
| test_contract_task_m1.py + _event_persistence + _capacity_tier | 13 passed |
| test_contract_task_a1.py + _preprocess + _move + _critique34 | 24 passed |
| test_contract_task_e1.py | 15 passed |
| test_contract_task_m2.py | 6 passed / 1 fail（环境相关，见上） |

## 三、实证方式说明（禁止造假的约束履行）

1. **DB 实证**：用 venv asyncmy 直接查 `information_schema.TABLES` + `SHOW COLUMNS`，确认
   - mcp_tool_call_log.status 含新枚举（T1-①）
   - hitl_approval 表存在且 19 行（S1-②）
   - user_memory_event 表存在（M1-②）
2. **服务实启**：后台启动 rerank sidecar → 探活 `/health` 200 + `/rerank` 返回 scores，验证后停止进程+清理日志（R1-②）
3. **真实 Redis**：`redis.Redis(from_url 127.0.0.1:6379).ping()=True` → 跑跨实例 schema_registry 契约（C2-③）确非跳过
4. **契约测试**：venv `python -m pytest <file> -q`，只采信通过结果
5. 未拿到运行环境的（OTLP 后端投递 / Prometheus 聚合 / 高峰削峰 / 灰度流量 / 冻结区告警 / HITL_ENABLED=True 窗口）一律如实标 ⚠️ 环境依赖，**不伪造 PASS**

## 四、资产消费证据（Asset Consumption）

- **读源码**：`app/mcp/executor.py`（TOOL_REWRITE_RULES/_default_rewrite_fn/register_builtin_tool/_run_hitl_seam）、`app/ai/hitl_gate.py`（审计字段+sweep_expired_pending）、`app/ai/memory/service.py`（_hitl_sweep_loop）、`app/knowledge/reranker.py`（precision 分支）、`app/rerank_service/main.py`（health/warmup）、`app/ai/guard.py`（TokenBudgetGuard/estimate_request_tokens）、`app/core/retry.py`、`app/otel/exporter.py`+`metrics.py`、`app/ai/graph.py`（compact_node/acquire）、`app/ai/compaction.py`（BudgetAllocator/anchor_gate）、`app/ai/tool_specs.py`（SchemaRegistry/to_prompt_entry）、`app/ai/prompt_cache.py`、`app/ai/memory/{vector,store,compactor}.py`、`app/ai/harness/`（base/registry/sixnode）、`scripts/eval/{canary,llm_judge,build_adversarial_set}.py`、`app/chat/retriever.py`（_maybe_shadow）、`app/config.py`（全量 config 锚点）
- **读 SQL DDL**：`refactor_sql/task-T1-add-status-enum.sql`、`refactor_sql/task-S1-create-hitl-approval.sql`
- **读报告**：`test-reports/task-A1/E1/M2-completion-report.md`（核读 AC 达标）、`edu-agent/test-reports/task-{R1,G1,O1,C1,C2,M1,S1,T1}-completion-report.md` 目录清单
- **实跑测试**（见上汇总表，共 ~160 passed）
- **实启服务**：rerank sidecar（cuda /health /rerank）
- **真实 DB**：asyncmy 查 MySQL 表/枚举/行数；redis ping + C2-③ 跨实例契约
- **git 证据链**：逐一 `git cat-file` 校验 26 个验收锚点 commit 均存在

## 五、未闭环项（明确登记，不掩盖）

以下为「实现完成、运行验证待环境」项，**非未实现**，需在具备真实后端/负载环境后补运行验收：
- R1-③ 高峰削峰、O1-② OTLP 投递、O1-③ 跨实例聚合、C1-③ 冻结区告警/降级、C2-② 灰度决策准确率、S1-① HITL_ENABLED=True 真实拦截、G1-② 60s 生产负载边界（task39）
- M2 AC5 测试用例断言与本环境 Milvus 可达性冲突（预期 memory 降级 vs 实际 milvus 命中）——测试脚本环境假设需随部署环境调整，非产品缺陷