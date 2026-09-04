# task-R1 — Rerank 独立服务 + 连续批处理

> 执行工具：**Trae** ｜ 依赖：task31（现状）, task34/35（知识库数据） + task-O1 ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P9（Rerank 同进程阻塞）
> 核心定位：把 `bge-reranker-v2-m3` 从主应用同进程拆为 **sidecar 独立服务**（FastAPI 微服务，HTTP 调用，不阻塞事件循环），请求排队**连续批处理**（对齐 vLLM continuous batching），Redis 队列削峰——解决 GPU 计算阻塞事件循环导致 QPS=50 崩。

## 1. 任务卡片

- **类型/工具**：backend（AI 服务化） / Trae
- **依赖**：task31（`app/knowledge/reranker.py` 现状：懒加载单例 + 批次推理 + 降级）、task34/35（知识库数据重建后检索候选充足）；task-O1（rerank 延迟指标埋点）
- **并行组**：W3（第三批 P2，与 task-T1/S1 并行）
- **工作量**：**L**
- **测试窗口纪律**：无 LLM；CUDA 推理随时可测（注意显存占用，避免与 LLM 测试窗口争抢 GPU）

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **vLLM** | continuous batching 将多请求矩阵合并，吞吐 5-10x；支持 MLA 优化 | https://github.com/deepseek-ai/DeepSeek-V3（vLLM 兼容段）|
| **SGLang** | MLA 吞吐优化 + DP Attention + FP8 KV | https://lmsys.org/blog/2024-12-04-sglang-v0-4/ |

## 3. 实现规划要点

### 3.1 独立服务（新增 `app/rerank_service/`）

- 新增 `app/rerank_service/main.py`（FastAPI 独立进程）：
  - `POST /rerank` body `{query, contents: [str], batch_size?}` → `{scores: [float], latency_ms}`；
  - 复用 `app/knowledge/reranker.py` 的 `Reranker` 逻辑（模型加载/批处理/降级返回 None 不变），进程内单例（独立进程天然隔离 GPU 阻塞）；
  - `GET /health` 返回 `{model_loaded, device, gpu_mem_mb}`；
  - 启动方式：`uvicorn app.rerank_service.main:app --port RERANK_SERVICE_PORT(8601)`，主应用与 sidecar 独立部署（systemd/进程管理器各管一个）。
- 主应用改造 `app/chat/retriever.py` `_rerank_docs`：
  - 原 `Reranker.get().rerank()` 直连调用改为 `httpx.AsyncClient` 调 sidecar（`RERANK_SERVICE_URL=http://127.0.0.1:8601`）；
  - **降级链**：sidecar 不可达/超时 → 回退进程内直连（现状路径）→ 再失败 `_rule_rerank` + `degraded_reason`；直连模式保留原单例（平滑切换，无需同时重建）。

### 3.2 连续批处理（对齐 vLLM continuous batching 思路）

- `app/rerank_service/batcher.py`：请求排队合并批处理——
  - 攒批窗口：`RERANK_BATCH_WINDOW_MS=20`（20ms 内到达的请求合并成一批，每批 ≤ `RERANK_MAX_BATCH_PAIRS=64` 对）；
  - 单请求多文档已分批（现有 `batch_size=16`），此处是**跨请求**合并（多个 query×contents 拼接成一个大 batch 一次前向），吞吐提升；
  - 超窗未满批的请求立即处理（延迟上限 `RERANK_MAX_WAIT_MS=50`）；
  - 队满保护：`RERANK_QUEUE_MAX=200`，超限直接返回 503（调用方走降级）。
- 消息队列削峰（可选）：`app/rerank_service/queue_adapter.py` 支持 Redis list 缓冲峰值（LPUSH/BLPOP），默认直连 batcher。

### 3.3 配置项

```python
RERANK_SERVICE_PORT = 8601
RERANK_SERVICE_URL = "http://127.0.0.1:8601"
RERANK_BATCH_WINDOW_MS = 20
RERANK_MAX_BATCH_PAIRS = 64
RERANK_MAX_WAIT_MS = 50
RERANK_QUEUE_MAX = 200
```

### 3.4 测试

- `tests/test_contract_task_r1.py`：sidecar `/rerank` 响应正确性（与进程内直连分数一致）、连续批处理合并数与延迟上限、降级链（sidecar 不可达→直连→规则）、`/health`。
- `scripts/eval/stress.py` 扩展：Rerank QPS 压测（目标：sidecar 模式 QPS 较同进程提升 ≥2x，P95 ≤ 200ms）。

## 4. 验收标准（Given/When/Then）

- **AC1（服务正确性）**：Given sidecar 已启动（CUDA 可用），When `POST /rerank` 同参调用，Then 返回分数与 task31 进程内直连 `Reranker.get().rerank` 结果一致（误差 <1e-4）。
- **AC2（主链路改造）**：Given 主应用发起检索，When 走 `_rerank_docs`，Then 默认经 HTTP 调 sidecar 完成重排，事件循环不被 GPU 推理阻塞（并发请求无事件循环卡顿）。
- **AC3（连续批处理）**：Given 20ms 内到达 5 个 rerank 请求，When batcher 处理，Then 合并为 ≤2 批（跨请求合并），单请求延迟 ≤ `RERANK_MAX_WAIT_MS`，吞吐 ≥ 单请求串行 2x。
- **AC4（降级链）**：Given sidecar 进程停止，When 检索重排，Then 自动回退进程内直连（degraded_reason 标注），直连也失败才 `_rule_rerank`，全程不 500。
- **AC5（压测达标）**：Given `scripts/eval/stress.py` rerank 压测（窗口内），When 对比同进程模式，Then sidecar+批处理模式 QPS ≥ 同进程 2x，P95 ≤ 200ms（或产出差距分析与调参建议）。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-R1-completion-report.md`（服务正确性对比、批处理合并统计、压测 QPS/P95、降级链实测）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"Rerank sidecar 独立服务 + continuous batching；降级链 sidecar→直连→规则"决策。
- **完成动作**：git commit → sync.ps1；部署说明补 `README`（sidecar 启动方式）。

## 6. 批判承接

- **production-upgrade-plan.md P9**（Rerank 同进程阻塞）：GPU 计算阻塞事件循环，QPS=50 崩 → AC2/AC3/AC5 落实。
- **critique-backlog-tracker.md**：task39「task-VEC/31 批判②：BGE-M3/Reranker 冷启动预热」——sidecar 独立进程天然常驻预热（`/health` 提供预热检查），主应用启动不再承担 2.2GB 加载；task32 的 rerank 增益评估（`compare_rerank_vs_rule`）改为调 sidecar 验证。

## 7. 与其他 task 关联

- **联动**：task-O1（rerank 延迟指标 + sidecar 健康事件）；task-E1（影子模式可对 sidecar vs 直连做线上 A/B）；task39（压测含 sidecar 模式）。
- **执行顺序**：W3 第三批；需 task31 的 Reranker 逻辑稳定后拆分，主应用直连路径保留实现平滑切换。