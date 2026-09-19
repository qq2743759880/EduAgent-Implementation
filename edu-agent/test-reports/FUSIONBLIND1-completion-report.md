# W-NEXT-FUSIONBLIND-001 完成报告（C-01 逐断言独立实证）

- 任务：R20-min 批判 Crit-2「融合层对 dense 故障失明」承接——dense 通道故障（嵌入失败/超时/空转）时融合层静默吃稀疏补偿结果、指标照常产出不报警的可观测性盲区修复。
- 实现提交：**c03fa4a**（full: `c03fa4a2cf34dc0ed7cee8cf8df7fbb38054e4dd`，分支 feature/opt-waves，commit 前 symbolic-ref=refs/heads/feature/opt-waves + rev-parse 复核）
- 日期：2026-09-19。lock `scripts/eval/wnextfusion1.lock` 已于 commit 前删除（现为不存在态）。
- 编排者派单即 kickoff 本体：全仓 grep `FUSIONBLIND` 0 命中（无独立 kickoff 文件），本报告首笔登记。

## 1. 交付清单（3 文件，+500/−9）

| 文件 | 变更 |
|---|---|
| `app/chat/retriever.py` | channel_health 基建（`_CHANNEL_FAIL_STREAK`/`_log_channel_failure`/`_log_channel_recovery`/`_dense_health_from_backend`）；`_milvus_hybrid_search_safe` phase 归因返回 3 元组；超时分支通道归因；`retrieve_three_channel` 组装 channel_health 附入 bundle + profile 行 health 段；RetrievalBundle 新增 `channel_health: dict | None = None` |
| `scripts/eval/r20min_run.py` | `_eval_one` trace 落盘 channel_health；`_channel_summary`（per-channel dense 分层命中率）；report 顶部条件 WARNING；`gate()` dense 全失效强制 FAIL；smoke 打印 channel_health |
| `tests/test_fusionblind1_channel_health.py` | 新增 7 用例（三态注入 + 升级 + 形状 + 定级口径单测） |

## 2. 逐断言验收

### 断言 1 故障可观测 — PASS
- ① `channel_health` 随 `RetrievalBundle` 显式外带，**只增不改**：新增字段（默认 None），`degraded_reason` 组装逻辑与字符串内容原样（注入态 1 实测 `degraded_reason == "Milvus 检索跳过（RuntimeError）"` 逐字保持，见 §3）。键集：`milvus_hybrid/dense/sparse/graph/kg_expand/rerank`。
- ② WARN 带通道名+原因，实测 loguru 捕获：
  ```
  WARNING|Milvus 检索超时（>0.15s），降级返回空 docs
  WARNING|[retriever] channel=dense FAILED（连续 1 次/阈值 3）：milvus_hybrid timeout(>0.15s)
  WARNING|[retriever] channel=dense FAILED（连续 1 次/阈值 3）：dense_embed:RuntimeError: BGE offline + DashScope 429
  ```
- ③ 连续失败升级 ERROR：`RETRIEVER_CHANNEL_FAIL_ERROR_N`（settings 字段优先，模块常量默认 3 供注入）。注入实测阈值=2 时第 1 次 WARN、第 2 次 ERROR、成功后 streak 清零（`test_consecutive_dense_failures_escalate_to_error` PASSED）。
- 三通道状态显式化覆盖：dense（ok/idle 空转/degraded/failed）、sparse（ok/empty/failed/skipped）、graph（ok/empty/failed/disabled）、kg_expand（ok/empty/failed/disabled，仅只读 `kg_merged` 计数——kg_expand 语义零改动）、rerank（ok/empty/failed/degraded）。

### 断言 2 指标护栏 — PASS
- summary 必含 per-channel 命中占比：`channel_summary` 每次评估必产出（`dense_status_counts` / `hit_rate_by_dense_status` / `hit_n_by_dense_status` / `n_by_dense_status` / graph、kg 产出占比）。口径 note 显式标注：Milvus hybrid RRFRanker 融合后无子通道归因 → 以 **dense 健康态分层命中率**呈现（ok/idle/failed 各自 hit_rate）。
- 全 dense 失效：报告**第一个键**即 `WARNING: ALL_DENSE_FAILED: ...`，stdout 在指标行**之前**打印。
- gate 护栏离线实测（stub run_eval，不跑重评估）：
  ```
  [gate] FAIL dense 通道全失效（dense_status_counts={'failed': 3, 'idle': 1, 'ok': 0}）→ 指标为稀疏补偿产物，不具门槛效力（FUSIONBLIND-001）
  [gate] hit_rate@5=0.99 (min=0.9488) mrr@5=0.99 (min=0.9488) → FAIL   # rc=1
  [gate] hit_rate@5=0.99 (min=0.9488) mrr@5=0.99 (min=0.9488) → PASS   # dense ok=4 反例 rc=0 不误伤
  ```
  即 Crit-2 场景复现判定：**指标再高，dense 全失效即 FAIL**。

### 断言 3 回归 — PASS（190 passed, 1 env-skip）
| 套件 | 结果 |
|---|---|
| tests/test_rn2_kg_expand.py（R-N2 22 例） | **22 passed** |
| test_kg_rn1 + test_veclock_verify + test_contract_task_vec + test_rn2（合并批） | 69 passed, 1 skipped（Neo4j 不可达 skipif，环境门控既有行为） |
| test_perf_guard + test_contract_task_e1 + task_r02 + task_r02tail + taskP1L + test_agent_loop | 79 passed |
| test_contract_task31 + test_sse_envelope_contract + test_chat_stream_error + test_chat_flow_args_fix | 35 passed |
| tests/test_fusionblind1_channel_health.py（本批新增） | 7 passed |

- 真实一轮 chat docs 正常：**8011 独立实例**（共享 8000 零接触，全程 200）。SSE 实测：`start → retrieval(5 docs, retrieved_count=141, top1=_default:d57758b9d8c5087e:1 真实完形填空题干) → token×571 → done{code:0}`，latency 14.05s。唯一降级 `rerank_sidecar_unavailable`（8011 无 sidecar 进程，进程内直连兜底，既有设计，非 dense 相关）。**用后即清**：8011 进程已杀（port 复查 000）、token 文件已删；session_id/message_id 均为 null（无会话落库，无需清 DB）。

### 断言 4 注入测试（三态） — PASS（7/7，详见 §3）
在故障真实发生点 mock（`encode_dense_batch_detailed` / `_milvus_hybrid_search`），真实 `_milvus_hybrid_search_safe` 全路径执行，非整段换桩。

## 3. 三态注入实测输出

```
tests/test_fusionblind1_channel_health.py::test_dense_embed_raises_marks_failed_and_no_crash PASSED   # 态1 抛错
tests/test_fusionblind1_channel_health.py::test_dense_timeout_marks_failed PASSED                     # 态2 超时
tests/test_fusionblind1_channel_health.py::test_dense_idle_pseudo_vector_sparse_fallback_usable PASSED # 态3 空转(返回空=伪向量)
tests/test_fusionblind1_channel_health.py::test_hybrid_zero_rows_marks_empty_dense_ok PASSED          # 补充态:hybrid 0 行
tests/test_fusionblind1_channel_health.py::test_consecutive_dense_failures_escalate_to_error PASSED   # WARN→ERROR 升级
tests/test_fusionblind1_channel_health.py::test_all_healthy_channel_health_shape PASSED               # 全健康形状回归防线
tests/test_fusionblind1_channel_health.py::test_dense_health_from_backend_levels PASSED               # 定级口径单测
======================== 7 passed, 1 warning in 7.16s =========================
```

三态断言要点（逐态均验证 channel_health 标记 + WARN + 主链不崩）：
- **态 1 抛错**：`dense=failed(reason=dense_embed:RuntimeError)` + `sparse=skipped` + `milvus_hybrid=failed`；bundle 恒返回、docs=[]、degraded_reason 原文不变；WARN 命中。
- **态 2 超时**：外层 wait_for(0.15s) 触发 → `dense=failed(timeout)` + `sparse=unknown`（失败阶段未知不妄断）+ `milvus_hybrid=failed`；degraded 含「超时」；WARN 命中。
- **态 3 空转（Crit-2 真实形态）**：encoder 退化为 backend=sha256 伪向量 → `dense=idle(reason 含 sha256)` + `sparse=ok` + `milvus_hybrid=ok`；**稀疏兜底结果仍可用**（docs=[s1,s2] 内容完整）；既有 degraded_reason 含 `query_embed_fallback:sha256` 语义原样；WARN 命中。

## 4. channel_health 样例

真实 8011 实例（真实 BGE-M3 + Milvus + chat 全链）一轮检索的 profile 留痕（health 段为本批新增）：
```
[retrieval-profile] pipeline total=6054ms | hyde=0 milvus=3328 graph=0 kg_expand=0 merge=2 rerank=2723 cliff=0 | raw=141 final=5 | health dense=ok sparse=ok graph=empty kg=disabled rerank=degraded
```
（graph=empty 为 R-N2 已知真实形态 kg_sync 子图 MENTIONS=0；rerank=degraded 即 sidecar 不可达进程内直连；dense=ok=嵌入 bge_m3 同空间。）

注入态样例（pytest 断言值）：
```json
{"milvus_hybrid": {"status": "failed", "reason": "dense_embed:RuntimeError: BGE offline + DashScope 429"},
 "dense": {"status": "failed", "reason": "dense_embed:RuntimeError: BGE offline + DashScope 429", "backend": null},
 "sparse": {"status": "skipped", "reason": "dense 嵌入失败，hybrid 通道整体不可用（loader 契约 dense+sparse 成对）"}}
{"dense": {"status": "idle", "reason": "query_embed_fallback:sha256", "backend": "sha256"},
 "sparse": {"status": "ok", "reason": null}, "milvus_hybrid": {"status": "ok", "reason": null}}
```

## 5. 红线自查

- 禁碰清单逐项 grep 复核：`app/ai/kg_bridge.py`（0 diff）、embedding 配置（config.py/.env 0 diff）、kg_expand 逻辑（仅加只读计数 `kg_merged`，RRF 并入/去重/开关判断逐行未动，R-N2 22 例全绿佐证）、`contracts/**`（0 diff，channel_health 不出 API/SSE 契约）、`graph.py`（0 diff）、loader.py（0 diff）。
- 既有字段语义：`degraded_reason` 组装逻辑与全部既有字符串原样；`RetrievalBundle` 既有字段位置未动（新字段尾插带默认值，service/agent/flows 等 5 处构造点 keyword 传参零改动）。
- lock：commit 前 `rm` 并复查不存在。报告中 _fusionblind_* 探针产物留在工作区未入库（含 SSE 全文，作复跑凭证）。

## 6. P0 自批判（5 条）

1. **「per-channel 命中占比」是 dense 健康分层代理，非逐 doc 通道归因**：Milvus hybrid_search 经 RRFRanker 融合后不回传子通道命中，结果级无法判定某 hit 来自 dense 还是 sparse。summary 以 dense 健康态分层命中率（ok/idle/failed 各自 hit_rate）呈现并在 note 显式标注口径——与派单字面「per-channel 命中占比」存在偏差，严格化需 loader 支持分请求回传（本批禁改 loader，未做）。
2. **dense 硬失败时「稀疏兜底」结构性不可达**：loader 契约 dense+sparse 成对建 AnnSearchRequest，嵌入抛错即整个 Milvus 通道不可用（态 1/2 的 docs=[]，稀疏一并丢失）。「结果仍可用（稀疏兜底）」仅对空转态成立（sha256 伪向量仍可跑 hybrid，稀疏补偿承载）。Crit-2 的生产语义=空转态补偿而非硬失败态兜底，本批如实区分、不做掩盖性假兜底；彻底解决需 loader 单稀疏请求支持（登记为 R22 可选扩展）。
3. **cloud 合法模式会被计 streak 升级 ERROR（误报面）**：`_dense_health_from_backend` 把非 bge_m3 且非 sha256 的后端（如显式 EMBED_BACKEND=cloud）标 degraded 并计入连续失败升级。当前生产 VEC-LOCK 钉死 cuda（AGENTS.md 教训 7），风险未激活；若未来合法切 cloud 需同步调整定级口径。
4. **channel_health 未暴露到 API/SSE 契约**（contracts/** 禁碰）：可观测出口=评估 trace + profile 日志 + bundle 内部字段；前端「部分功能降级中」展示需另立契约变更单。gate 护栏仅覆盖 r20min 主链口径，`_run_sensitivity`/冻结候选段等对照通道未加检查（其不产门槛数字，但若被误当基线引用则护栏不覆盖）。
5. **timeout 注入测试依赖时序收口**：to_thread 残留线程须在 monkeypatch 生效窗内跑完，测试以 sleep 0.6s 等待收口（已消除 teardown 后触真实 Milvus 的日志噪声）；极端慢环境（jieba 首载 >0.6s）仍可能残留一次只读 search（无写风险，异常被 safe 函数全吞）。

## 7. 批判承接核对

- **R20-min Crit-2（本轮承接对象）**：tracker `.opencode/plans/critique-backlog-tracker.md` Crit-2 条目已标「✅ 承接闭环 2026-09-19: W-NEXT-FUSIONBLIND-001」并附交付摘要。原处置「登记 R22 扩展项(gate 增 dense-only 探针)」的 gate 侧护栏已由本批直接落地（dense 全失效强制 FAIL）；**残差**：绕过融合直测 dense 召回的独立 dense-only 探针仍可由 R22 做更强隔离（与自批判 1/2 相关），已在 tracker 承接批注与本报告留痕。
- Crit-1/Crit-3 及其他 tracker 登记项：非本轮派单范围，0 触碰。

## 8. 资产消费证据

1. `.opencode/plans/critique-backlog-tracker.md`（L545 Crit-2 原文 + R20-min 验收节：0.9688 失明实证）— 承接依据。
2. `app/chat/retriever.py` 改造前最新版（含 R-N2 kg_expand 段、P1-4 超时、R02-tail 并行）— 最小 diff 基线。
3. `app/ai/kg_bridge.py` — 降级范式参照（degraded_reason 留痕、恒不抛、KGBridgeResult 三元结构）。
4. `app/knowledge/importer/embedder.py` — `encode_dense_batch_detailed` 三级兜底链（bge_m3→cloud→sha256）= 空转机理判定依据；`DenseResult` 字段用于注入桩。
5. `scripts/eval/r20min_run.py` 改造前版 — R20/R22 评估跑法与 gate/freeze 口径。
6. `tests/test_rn2_kg_expand.py` / `test_perf_guard.py` / `test_contract_task_e1.py` / `test_contract_task_r02tail.py` — 既有 2 元组桩形态 = 容忍解包设计依据；回归基线。
7. AGENTS.md — 教训 2（禁 Playwright/独立实证）、教训 8（真实契约优先）、VEC-LOCK cuda 空间约束、测试账号与启动命令。
8. 任务 3 实测复用 chat SSE 契约（`POST /api/chat/stream`，event: start|retrieval|token|done）——首轮 body 字段名踩 `account`（42200 报错即纠正），中文 query 经文件 `--data-binary` 规避控制台编码，两次纠偏均为 curl 实测所得，与教训 8 同范式。
