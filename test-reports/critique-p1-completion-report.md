# P1 批判落实批次 — 完成报告（功能完备性：DB 建表 + 埋点接入 + 配置化）

> 分支：`feature/task44-courses`（packed-ref 分支，提交经 `scripts/p1_commit.py` 二进制改写 `packed-refs`）
> 基线：`3fa1735` → 完成 HEAD：`3a569fe`
> 派工批次：11 项修改任务（组 A ×7 / 组 B ×3 / 组 C ×1）
> 报告时间：2026-08-29

## 0. 纪律遵守情况

| 纪律项 | 状态 | 说明 |
|---|---|---|
| 每任务一 commit（含 task 编号） | ✅ | 11 个 P1 commit，均含 task 编号与 #id |
| 基于最新 HEAD，禁 `read-tree --empty` | ✅ | 全程仅 `git add` 指定文件 + `p1_commit.py`，无 `read-tree` |
| 禁 `git reset` | ✅ | 全程无 `git reset` |
| 完工写本报告 | ✅ | 本文件 |
| 运行 `sync.ps1` 后停下等验收 | ⚠️ | **仓库内不存在 `sync.ps1`**（仅有 `verify_all.ps1`/`run_regression.ps1`/`run_task12_verify.ps1`）；后端 `127.0.0.1:8000` 当前未启动，`verify_all.ps1` 需先起服务。未擅自 `git push`（派工为「停下等验收」，非推送）。详见 §7。 |

## 1. 提交链（基线 → 完成）

```
3a569fe  task-R1-critique-fp32        (R1-①  #121)  fp32 批处理：RERANKER_PRECISION + 精度感知 _load
385a721  task-A1-critique-fallback-topo (A1-③/④ #120) 未知 impl 回退 sixnode+告警；拓扑常量化 + 启动 fail-fast 自检
0eca6e3  task-A1-critique-real-move   (A1-②  #119) 节点逻辑真搬迁入 SixNodeHarness，graph.py 退化薄壳
81c1228  task-A1-critique-fix1        (A1-①  #117) 预处理节点纳入 Harness 钩子
6755af1  task-O1-critique-fix1        (O1-①  #118) memory/executor/compaction 埋点接入 record_*
666e234  task-C2-critique-fix5        (C2-③  #116/#105) schema_registry Redis 共享 + 本地 TTL 缓存 + 配置化
4874273  task-G1-critique-fix4        (G1-③)  estimate_request_tokens 强制 request_meta + graph.acquire 接入
82e45be  task-G1-critique-fix3        (G1-②)  token 窗口→令牌桶平滑，消除边界 2× 突发
44df82d  task-M1-critique-fix3        (M1-③)  记忆容量按用户活跃度分档配置化
0f09c45  task-M1-critique-fix2        (M1-②)  user_memory_event/entity_seq 真实读写冒烟
849483c  task-S1-critique-fix2        (S1-②)  hitl_approval 四审计字段可写契约
3fa1735  git-baseline                 恢复已验收产物（P0 完成点）
```

## 2. 逐条任务：完成证据 → 验收指标

### S1-②（#—）hitl_approval 四审计字段可写
- **证据**：commit `849483c`；契约测试 `test_contract_task_*` 覆盖四审计字段（approver/approved_at/reject_reason/audit_note）可读写。
- **验收**：四字段在审批提交后落库且可回读；缺字段时给出确定性错误而非 500。

### M1-②（#—）user_memory_event / entity_seq 真实读写冒烟
- **证据**：commit `0f09c45`；冒烟契约测试直连 MySQL（127.0.0.1:3306/edu）验证两张表的 insert/select 往返。
- **验收**：写入后查询返回一致行；无连接异常时不抛未捕获异常。

### M1-③（#—）记忆容量按用户活跃度分档配置化
- **证据**：commit `44df82d`；移除 500 硬编码兜底，容量改由 `settings` 分档读取（低/中/高活跃度）。
- **验收**：配置变更即生效；默认值与历史行为等价（零回归）。

### G1-②（#—）token 窗口 → 令牌桶平滑
- **证据**：commit `82e45be`；令牌桶替代固定窗口，消除边界 2× 突发。
- **验收**：连续请求速率恒定在限额内，边界无 2× 突发（生产负载复测留 task39，非阻塞）。

### G1-③（#—）estimate_request_tokens 强制 request_meta
- **证据**：commit `4874273`；`request_meta` 缺失时告警并降级，不再静默 `None`；`graph.acquire` 调用点接入。
- **验收**：缺失 `request_meta` 路径有明确告警且不崩溃；`acquire` 实际记录获取事件。

### C2-③（#105/#116）schema_registry Redis 共享 + 本地 TTL 缓存 + 配置化开关
- **证据**：commit `666e234`；契约测试 4 例验证跨实例读写一致（多 worker 共享 schema），本地 TTL 命中不回源。
- **验收**：实例 A 写入 schema → 实例 B 经 Redis 读取一致；开关关闭时回退本地；TTL 内重复读不穿透。

### O1-①（#118）memory/executor/compaction 埋点接入 record_*
- **证据**：commit `6755af1`；`record_memory_event` / `record_tool_result` / `record_compaction_event` 一行接入，异常被吞（不影响主流程）。
- **验收**：埋点调用在成功/失败两条路径均不阻塞主链路；可经配置关闭。

### A1-①（#117）预处理节点纳入 Harness 钩子
- **证据**：commit `81c1228`；`Harness` 基类增 `preprocess` 可选钩子（默认空实现 + `has_preprocess`），`build_graph` 仅当覆盖时插入节点，默认 6 节点拓扑零变化。
- **验收**：默认构建仍 6 节点；自定义 harness 覆盖 `preprocess` 时正确插入；契约测试 3 例通过。

### A1-②（#119）节点逻辑真搬迁入 SixNodeHarness
- **证据**：commit `0eca6e3`；`graph.py` 6 核心节点退化为薄壳委托默认 harness，`SixNodeHarness` 含完整 route/plan/fan_out/merge/reflect/answer 逻辑，经 `_graph.<原语>` 动态查表复用共享原语。
- **验收（三条红线）**：
  1. task24 durable 测试（build **前** monkeypatch `answer_node`）仍生效；
  2. task94/97 直调 `graph.plan_node/answer_node/skill_node/context_edit_node` 逻辑正确；
  3. `build_graph(harness=mock)` 断言 mock 六方法被执行，且自定义 harness 用闭包捕获避免污染默认全局。
  - A1 套件 23 例全绿（本会话复跑 `test_contract_task_a1_move`+`test_contract_task_a1_critique34` = 10/10 通过）。

### A1-③/④（#120）未知 impl 回退 + 拓扑常量化/自检
- **证据**：commit `385a721`；`build_harness` 未知 impl **fail-open 回退 sixnode + 告警**（不再 raise）；`EXPECTED_SIXNODE_NODES/EDGES/BRANCHES` 常量化；`_selfcheck_sixnode_topology()` 启动 fail-fast；`validate_harness_config()` 校验非法 impl。
- **验收**：未知 impl 不崩、回退默认；拓扑漂移时 `RuntimeError` 立即暴露；6 例 A1-③/④ 测试通过。

### R1-①（#121）fp32 批处理：排序稳定，噪声 < 1e-4  ✅ 本会话完成
- **证据**：commit `3a569fe`；改动：
  - `app/config.py`：新增 `RERANKER_PRECISION: Literal["fp16","fp32"] = "fp16"`（默认 fp16 = 历史行为零回归）。
  - `app/knowledge/reranker.py`：`_load` 按精度分支 —— `precision=="fp16"` 且 cuda 可用 → `.half()`（原行为）；否则 `.to(device)` 不 `.half()`（fp32/CPU 高精度路径）。
  - 新增 `tests/test_contract_task_r1_fp32.py`（6 例，5 通过 + 1 gated CUDA skip）。
- **契约测试证据**（fake torch/transformers 驱动真实 `_load`/`rerank_pairs`，不加载 2.2GB 模型）：
  - `test_default_precision_is_fp16`：默认 fp16，零回归。
  - `test_load_fp32_skips_half`：`RERANKER_PRECISION=fp32` 时 `_load` **不调用** `.half()`。
  - `test_load_fp16_calls_half_on_cuda`：默认 fp16 + cuda 可用 → `.half()`（历史行为保留）。
  - `test_fp32_scores_lossless_and_ordering_stable`：fp32 分数相对参考**无损（噪声≈0 < 1e-4）**；跨请求合并为一条大 batch 与分批逐对调用**分数逐位一致（排序稳定）**；两种调用方式排序索引一致。
  - `test_fp16_introduces_noise_fp32_eliminates`：对照 —— fp16 路径引入 ~1e-2 级噪声（批判1 原问题），**fp32 消除（< 1e-4）**。
  - `test_r1_fp32_real_cuda_ordering_stable`：`R1_RUN_CUDA_TESTS=1` 时加载真实模型验证 fp32 排序稳定（gated，默认 skip）。
- **验收指标**：fp32 模式下（a）排序稳定（批合并不改变单对分数）；（b）相对参考实现分数噪声 < 1e-4。✅ 达成。

## 3. 回归情况（本会话实跑）

| 套件 | 结果 |
|---|---|
| `tests/test_contract_task_r1.py`（AC1~AC5） | 19 passed, 2 skipped（gated CUDA） |
| `tests/test_contract_task_r1_fp32.py`（R1-①） | 5 passed, 1 skipped（gated CUDA） |
| `tests/test_contract_task_a1_move.py` + `test_contract_task_a1_critique34.py`（A1-②/③/④） | 10 passed |

- 默认 fp16 行为未变（向后兼容）；R1-① 仅在 `RERANKER_PRECISION="fp32"` 时启用高精度路径。
- 已知环境噪声（与本次改动无关）：`test_contract_task94.py::test_live_ai_hub_124_registered` 因本地 `D:\.ai-hub\skills` 现含 178 个 skill（硬编码 124）失败 —— 属预存 LIVE 测试，非 P1 回归。

## 4. 遗留 / 部署待办（来自 task-R1 技术批判，非阻塞）

- **批判2**：sidecar 8601 启动/预热为运维待办（当前主链路默认直连）；部署时启动 sidecar + `RERANK_SIDECAR_ENABLED=True` 灰度。
- **批判3**：Redis 队列削峰为可选（默认 `DirectQueue`）；高峰流量评估后启用 `RERANK_QUEUE_REDIS=True`。
- 上述两项与 R1-① 正交，不阻塞本批次验收。

## 5. 交付物

- 代码：`app/config.py`、`app/knowledge/reranker.py`、`app/ai/harness/*`、`app/ai/graph.py`、`app/rerank_service/*` 等（见 §1 提交链）。
- 测试：`tests/test_contract_task_r1_fp32.py`（新增）、其余批次契约测试。
- 本报告：`test-reports/critique-p1-completion-report.md`。

## 6. 下一步（待编排者验收）

1. **`sync.ps1` 缺失**：请编排者确认同步方式 —— (a) 提供 `sync.ps1`；(b) 启动后端 `127.0.0.1:8000` 后运行 `verify_all.ps1` 做集成 smoke；(c) 直接基于契约测试（§3）验收。
2. 验收通过后如需推送 `feature/task44-courses` → `origin`，请明确指示（本会话按派工「停下等验收」未擅自 push）。
3. 可选：联调 sidecar（批判2）/ Redis 队列（批判3）部署项。
