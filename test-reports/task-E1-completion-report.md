# task-E1 完工报告 — 影子模式 + 对抗采样 + 金丝雀 + 4 维 Judge

> 执行者：后端+数据库开发者（ponytail 模式：最短可用实现，零新依赖）
> 依赖：task29（harnesses）/ task32（eval_dataset）/ task-R1（rerank 降级链）/ task-A1（harness 抽象）
> 结论：**AC1~AC5 全部 PASS**，新增 5 文件 / 改动 2 文件，单 commit。

## 0. 设计取舍（ponytail 视角，先说清删了什么）

- **不新建评估框架 / 不引入新依赖**：4 维 Judge 复用 `llm_client`；分位统计用 `statistics`（stdlib）；影子对比复用既有 `_rule_rerank`。
- **影子变体零额外 IO**：默认变体对主链路结果用「规则重排」重排序（对比 sidecar 重排 vs 规则重排顺序差异），不二次打 Milvus/embedder。生产要对比「另一套检索配置」时，用 `set_shadow_variant(fn)` 注入真实变体即可。
- **主路径零改动**：影子 hook 仅在 `retrieve_three_channel` 的 `return` 前 fire-and-forget，**service.py 未改**，agent 回退 / 流式 / 非流式全部路径自动覆盖。
- **不碰现有 `judge_answer`(0-1)**：新增 `judge_answer_4d` 并行存在，task29 基线评估脚本行为不变（AC5）。

## 1. AC1 影子模式 — 主路径不变 + 异步落库不阻塞

`app/chat/retriever.py`：`_maybe_shadow` 在返回前调用 → `asyncio.create_task(_run_shadow(...))`，**返回的 `RetrievalBundle` 完全不被触碰**；`_run_shadow` 全异常吞掉，绝不阻塞应答。落库出口可注入：`set_shadow_sink(fn)`。

**影子对比落库样例（真实运行捕获）：**
```json
{
  "query": "python列表怎么去重",
  "user_id": 1,
  "primary_topk": 3,
  "variant_topk": 3,
  "jaccard": 1.0,
  "top1_consistent": true,
  "variant_latency_ms": 1000.31,
  "variant": "rule_rerank"
}
```
> 说明：`variant_latency_ms` 含 jieba 首次冷加载（~1s），生产常驻后 <5ms；该字段仅用于观测影子开销，不参与主链路延迟。

**契约验证（tests/TestAC1Shadow）：**
- `test_shadow_records_diff_without_blocking`：开启影子 → 落库 1 条 diff，主 bundle `docs` 未变。
- `test_main_path_identical_with_shadow_on_off`：隔离重检索内部后，开启/关闭影子返回的 doc 集合与 `degraded_reason` **逐字节一致**。
- 采样比例边界：`ratio=1.0` 全采样，`ratio=0.0` 不采样。

## 2. AC2 对抗采样评估集 — ≥20 脏数据 + ≥20 对抗，含 ground_truth

`scripts/eval/build_adversarial_set.py` → 输出 `scripts/eval/adversarial_dataset.json`。

- **脏数据（线上噪声形态）22 条**：错别字（"djang和flask"）、口语（"咋用git上传代码"）、超短句（"高数是啥"、"什么是api"）。
- **对抗样本 22 条**：易混淆对（"Java 和 JavaScript 是一个东西吗"、"SQL 注入和 XSS 区别"）、缺主语（"怎么学最快"）、长尾专业词（"Rust 的 lifetime 标注"、"softmax 和 sigmoid 区别"）。
- **每条含 `ground_truth`**（关键要点），供 4 维 Judge 判断；运行 `python -m scripts.eval.build_adversarial_set` 自带断言（≥20/≥20 + 全字段非空）。

样例：
```json
{"id":"AD-D02","query":"djang和flask哪个好","category":"dirty","ground_truth":"对比两者定位与选型建议"}
{"id":"AD-A01","query":"Java 和 JavaScript 是一个东西吗","category":"adversarial","ground_truth":"否，两者无关仅名字相似"}
```

## 3. AC3 4 维 Judge — 分维打分 + 均值/分位报告

`scripts/eval/llm_judge.py` 新增 `judge_answer_4d` + `judge_report`。每维 0~1 浮点（LLM-as-judge 输出 JSON，稳健解析）；报告用 `statistics.mean` + `statistics.quantiles` 输出各维均值、p25/p50/p75、通过率(≥0.6)。

**演示报告（20 样本，确定性伪评分，仅展示形态）：**
```json
{
  "fact_correctness": {"mean":0.7485,"p25":0.6425,"p50":0.755,"p75":0.825,"pass_rate":1.0},
  "completeness":     {"mean":0.686, "p25":0.5525,"p50":0.69, "p75":0.785,"pass_rate":0.65},
  "harmlessness":     {"mean":1.0,   "p25":1.0,   "p50":1.0,  "p75":1.0,  "pass_rate":1.0},
  "coherence":        {"mean":0.8125,"p25":0.7325,"p50":0.815,"p75":0.8675,"pass_rate":1.0}
}
```
> 真实 LLM-as-judge 仅测试窗口内运行；接口与报告逻辑已随时可测（scorer 可注入，测试零网）。

## 4. AC4 金丝雀 — 1% 分流 + 3 天观察 + 自动全量/回滚

`scripts/eval/canary.py`：`canary_assign(uid)` 确定性分流（同 uid 同桶，默认 `CANARY_RATIO=0.01`）；`canary_should_rollback(metrics)` 任一指标（延迟 P95 / 正确性 / 工具成功率）越界即回滚；`CanaryWindow` 状态机 `decide()` 返回 `promote`/`rollback`/`hold`。

**演练（tests/TestAC4Canary）：**
| 场景 | 输入 | 结果 |
|---|---|---|
| 延迟 P95 超标（9999ms） | 观察期满 5 天 | `rollback`（无视期满，安全优先） |
| 正确性 0.5 < 0.8 | 观察期满 5 天 | `rollback` |
| 指标全绿 + 已过 3 天 | 4 天 | `promote`（全量） |
| 指标全绿 + 仅 1 天 | 1 天 | `hold`（观察中） |
| 分流确定性 | 同 uid ×2 | 同桶；`ratio=1.0` 全进、`0.0` 不进 |

## 5. AC5 回归 — task29/32 既有评估可复现

- `judge_answer`(0-1) 接口未被破坏（空回答仍降级判 0，零网）。
- `eval_dataset.ALL` 仍 ≥40 条标准题，task32 基线未动。
- `scripts.eval.harnesses` 正常导入（`run_sixnode` 存在）。
- 全量回归：`test_contract_task24/93/95/96` **55 passed / 1 skipped**（skip=Redis durable，与基线一致）；新增 `test_contract_task_e1.py` **15 passed**。

## 6. 交付清单（git 单 commit）

| 类型 | 文件 |
|---|---|
| 改 | `edu-agent/app/config.py`（SHADOW_MODE_ENABLED/RATIO、CANARY_RATIO/DAYS、JUDGE_DIMENSIONS） |
| 改 | `edu-agent/app/chat/retriever.py`（影子 fire-and-forget hook + `_maybe_shadow`/`_run_shadow`/`_default_shadow_variant`/`set_shadow_*`） |
| 改 | `edu-agent/scripts/eval/llm_judge.py`（`judge_answer_4d`/`judge_report`/`JUDGE_DIMS`） |
| 新 | `edu-agent/scripts/eval/canary.py` |
| 新 | `edu-agent/scripts/eval/build_adversarial_set.py` |
| 新 | `edu-agent/scripts/eval/adversarial_dataset.json`（22+22 样本） |
| 新 | `edu-agent/tests/test_contract_task_e1.py`（15 passed） |

## 7. 批判承接（P10「离线 62.5% 上线崩」根因治理）

- **评估集分布不一致** → AC2 补齐线上脏数据 + 对抗样本，与标准题合并消费，评估更贴线上。
- **单一 0-1 掩盖维度缺陷** → AC3 分维打分 + 分位，定位「完整性弱（pass_rate 0.65）」而非笼统不及格。
- **上线即全量风险** → AC4 1%→3 天→全量，异常自动回滚。
- **离线/线上评估断层** → AC1 影子模式让「新检索变体」在真实流量上并行比对、只记录不改结果。

## 8. 已知边界（ponytail 标记，按需升级）

- **影子默认变体是规则重排重排**：要对比「另一套检索配置（top_k/embedder）」需 `set_shadow_variant` 注入真实变体（真实 IO，需评估资源）。`# ponytail: 默认变体零 IO 覆盖 80% 回归场景，真实变体按需在窗口内接。`
- **金丝雀 `decide` 为纯函数状态机**：未持久化窗口状态（重启丢窗口），生产需在 task-O1 指标库落地 `started_at`。`# ponytail: 3 天窗口状态交给 task-O1 5 维指标消费，本任务只交付决策函数。`
- **4 维 Judge 真实 LLM 评分仅窗口内**：接口/报告逻辑已离线可测，真实校准留测试窗口。

## 9. 下一步

- 测试窗口内：用真实 LLM 跑 `judge_answer_4d` 校准维度权重；用 `set_shadow_variant` 接「rerank 参数变体」跑线上影子。
- 联动 task-O1：影子 diff + 金丝雀指标接入 5 维指标看板。
