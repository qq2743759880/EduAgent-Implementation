# task-E1 — 影子模式 + 对抗采样评估 + 金丝雀

> 执行工具：**Trae** ｜ 依赖：task29, task32（现状评估）+ task34/35（知识库数据） ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P10（评估集标准题）
> 核心定位：解决"离线评估 62.5%，上线崩——评估集与线上脏数据分布不一致"。落地 **影子模式**（新旧检索系统并行跑线上流量只比较不改结果）+ **对抗采样评估集**（错别字/短句/对抗样本）+ **金丝雀发布**（1%→3 天→全量）+ **多维度 Judge**。

## 1. 任务卡片

- **类型/工具**：backend（评估体系） / Trae
- **依赖**：task29（`scripts/eval/harnesses.py` 三套 harness 现状）、task32（`rag_evaluator.py`/`eval_dataset.py` 现状）、task34/35（知识库/图谱数据重建后检索候选充足）
- **并行组**：W4（第四批 P3，与 task-A1/M2 并行）
- **工作量**：**M**
- **测试窗口纪律**：LLM-as-judge 与真实流量对比仅窗口内；影子数据采集/对抗集构造随时可做

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **通用生产实践** | Shadow Testing：新旧系统同时跑线上流量，旧系统返回用户，新系统只比较；金丝雀发布 1%→3 天→全量 | production-upgrade-plan.md P10 引述（canary release + shadow mode） |
| **多智能体评估** | Anthropic：多智能体系统内部评估超单体 90.2% | production-upgrade-plan.md P10 引述 |

## 3. 实现规划要点

### 3.1 影子模式开关（改造 `app/chat/retriever.py` + `app/chat/service.py`）

- 配置 `SHADOW_MODE_ENABLED` / `SHADOW_MODE_RATIO`（默认 1.0 全部流量影子采样）：
  - 线上请求主路径返回不变（旧系统/当前系统结果给用户），影子侧并行跑"新检索系统"（如 rerank 参数/检索 top_k/embedder 变更），仅记录对比结果（top-k 命中差、排序差异、延迟差）落 `otel_event`（task-O1 复用）或 `shadow_diff` 表；
  - 影子失败不阻塞主链路（try/except 全吞 + degraded 标注）。
- 新检索变体注册：`app/chat/retriever.py` 增加 `retrieve_variants` 字典（variant name → 参数覆盖），影子模式按变体并行调用。

### 3.2 对抗采样评估集（改造 `scripts/eval/eval_dataset.py`）

- 扩充评估集三类：
  1. **线上脏数据采样**：从真实线上 query 日志（`chat_message` 表）采错别字/口语/超短句（如 "python怎么装"、"djang和flask哪个好"）；
  2. **对抗样本**：易混淆对（"Java vs JavaScript"、"SQL 注入 vs XSS"）、缺主语短句、长尾专业词；
  3. 保留标准题（task32 现有）作基线对照。
- 新增 `scripts/eval/build_adversarial_set.py` 生成对抗集，输出 `scripts/eval/adversarial_dataset.json`，与现有 `eval_dataset.py` 合并消费。

### 3.3 多维度 Judge（改造 `scripts/eval/llm_judge.py`）

- 单一 0-1 打分升级为 4 维打分：`fact_correctness / completeness / harmlessness / coherence`（每维 0-1 分，LLM-as-judge 输出 JSON）；
- 汇总报告含每维均值 + 分位，按维度触发改进建议（非单一 pass/fail）。

### 3.4 金丝雀发布

- `scripts/eval/canary.py`：金丝雀配置 `CANARY_RATIO=0.01` → 3 天观察 → 全量；观察指标对接 task-O1 5 维指标（回答正确性抽查、延迟 P95、工具成功率），无异常全量，异常自动回滚（配置回滚开关）。

### 3.5 配置项

```python
SHADOW_MODE_ENABLED = False
SHADOW_MODE_RATIO = 1.0
CANARY_RATIO = 0.01
CANARY_DAYS = 3
JUDGE_DIMENSIONS = ["fact_correctness", "completeness", "harmlessness", "coherence"]
```

### 3.6 测试

- `tests/test_contract_task_e1.py`：影子模式主链路不变 + 影子结果落库、对抗集生成、4 维 judge mock、canary 比率分流逻辑。

## 4. 验收标准（Given/When/Then）

- **AC1（影子不变）**：Given `SHADOW_MODE_ENABLED=True`，When 线上请求到达，Then 用户收到的答案与关闭影子时完全一致（主路径不变），影子对比结果异步落库不阻塞应答。
- **AC2（对抗集）**：Given `build_adversarial_set.py` 运行，When 输出数据集，Then 含 ≥20 条线上脏数据（错别字/短句）+ ≥20 条对抗样本，且每条含 ground_truth 标注。
- **AC3（4 维 Judge）**：Given 同一批评估样本，When `llm_judge` 运行，Then 输出每样本 4 维分数（fact_correctness/completeness/harmlessness/coherence），报告含各维均值与分位，不再只给单一 0-1。
- **AC4（金丝雀）**：Given `CANARY_RATIO=0.01`，When 流量接入，Then 1% 流量走新版本、3 天观察窗口内指标（延迟 P95/正确性抽查/工具成功率）无异常、到期自动全量；任一指标异常则自动回滚并记录。
- **AC5（回归）**：Given task29/task32 既有评估脚本，When 影子/对抗集接入后运行，Then 既有标准题评估结果可复现（基线对照不被破坏）。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-E1-completion-report.md`（影子对比样例、对抗集分布、4 维 judge 报告、金丝雀演练）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"评估=标准题基线 + 对抗采样 + 影子模式 + 金丝雀四层"决策。
- **完成动作**：git commit → sync.ps1。

## 6. 批判承接

- **production-upgrade-plan.md P10**（评估集标准题，离线 62.5% 上线崩）：评估集与线上脏数据分布不一致 → AC1/AC2/AC3 落实。
- **critique-backlog-tracker.md**：task32 全部批判项（记忆召回样本不足 ≥30 条、rerank 增益 +15%、真实 LLM 前缀质量、缓存命中实测）——本任务对抗集与 4 维 Judge 承接其评估方法升级；task29 批判②（P95 超标）的观测指标由金丝雀观察窗口承接。

## 7. 与其他 task 关联

- **联动**：task-O1（影子差异/金丝雀指标消费 5 维指标）；task-R1（影子可对 sidecar rerank vs 直连做线上 A/B）；task-A1（harness 变体对比纳入影子模式）。
- **执行顺序**：W4 第四批；需 task34/35 知识库数据就绪（检索候选充足），建议在其后实施。