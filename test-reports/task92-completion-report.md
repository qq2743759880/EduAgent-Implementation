# task92 完工报告：R1 子代理独立上下文（修复共享 state 结构性缺陷）

> AI 修订（8 项之 R1）｜agent｜阶段 E｜工作量 XL
> 修订来源：self-critique 维度3 + ai-agent-revision-plan R1 + tech-source-audit §二
> 核心：修复「子代理共享 state、丢失上下文隔离」结构性错误，对齐 Claude Code sub-agents 独立 context window
> 执行：Trae 手动调度（agent 链 sd-dev+be-architect → sd-tester → review-*）

## 0. 交付物（契约冻结⑭ 延伸 R1）
- `app/ai/subagents/runner.py` —— 独立 LLM 会话循环（独立 messages/system prompt/工具集/maxTurns）
- `app/ai/subagents/definitions.yaml` —— 4 内置子代理 frontmatter（name/description/tools/model/maxTurns/memory_scope）
- 内置 4 子代理：**search / tool / learning / memory**
- artifact 写入：完整输出（检索原文/工具结果/全消息）→ Redis artifact（TTL 1h，可降级内存）
- `app/config.py` 新增 `SUBAGENT_ARTIFACT_TTL` / `SUBAGENT_SUMMARY_BUDGET`
- 测试 + 真实 Redis 落库验证

---

## 1. 验收标准逐条核验（GWT 全文）

### ① Given 2 并行子代理，When 执行，Then 各自独立上下文（非共享 state），主 state 仅收 ≤2000 token 蒸馏摘要
**判定：✅ PASS**
- 独立上下文：每个 `run_subagent` **每次调用新建本地 `messages` 数组**（[system+user]），绝不引用/写入共享 state；`asyncio.gather` 各任务在独立会话上跑。
- 测试 `test_parallel_isolated_context`：子代理 A 的工具输出 `A_ONLY_MARKER` **不进 B 上下文**，反之同样——用 fake llm 捕获各自收到的 messages 逐点断言。
- 主 state 只收摘要：`SubagentResult.as_distilled()` 仅含 `{subagent, summary, artifact_ref, summary_tokens}`，无原文/系统 prompt。摘要 token ≤ `SUBAGENT_SUMMARY_BUDGET`(2000)。
```
tests/test_contract_task92.py::TestSubagentIndependence::test_parallel_isolated_context PASSED
main state 只应收蒸馏摘要：set(distilled[0].keys()) == {subagent, summary, artifact_ref, summary_tokens}
A 上下文被 B 污染？ 否（A_ONLY_MARKER in textA and B_ONLY_MARKER not in textA）
```

### ② Given 子代理检索 100 文档，When 完成，Then 原文在 artifact、主上下文只含摘要
**判定：✅ PASS（真实 Redis 落库）**
- `full_tool_outputs` 保留每个工具**完整返回体**（100 篇全量）写入 artifact；messages 内仅保留 ≤4000 字符截断视图（控 LLM 上下文）。
- 真实 Redis 验证（`scripts/_verify_task92_redis.py`，Redis 6379 实测）：
```
[GWT②] 子代理完成: ok=True turns=2 summary_tokens=14
[GWT②] artifact_ref=artifact:cd41...
[GWT②] 真实 Redis artifact 含全量 100 篇，主上下文摘要 14 token → PASS
```
- 测试 `test_100_docs_stay_in_artifact`：100 篇原文在 artifact（含第 100 篇 `"i":99`），摘要 ≤2000、不含 `"y"*150` 原文。

### ③ Given 子代理崩溃，When 重试，Then 不污染主上下文
**判定：✅ PASS（含批级隔离加固）**
- 崩溃重试：`_call_llm_with_retry` 连试 2 次失败 → `ok=False` + 摘要回退 objective，**不向上抛、不携带崩溃堆栈**。
- 测试 `test_crash_retry_no_pollution`：崩溃子代理 `ok=False turns=1`；并行健康子代理不受影响；重试独立起新会话不累积。
- **加固（采纳独立审查建议）**：`run_subagents` 用 `return_exceptions=True` + 每任务 try/except——单子代理意外异常**不取消整批 gather**；未知子代理名返回友好 `ok=False`（不抛裸 KeyError）。测试 `test_unknown_subagent_and_batch_isolation`。

---

## 2. 独立子代理红线审查（R1-R5，全部 PASS + 2 加固采纳）
| 项 | 判定 | 说明 |
|----|------|------|
| R1 独立上下文/隔离 | ✅ PASS | 每次新建 messages；无共享可变全局并发写；as_distilled 只含摘要+引用 |
| R2 正确性 | ✅ PASS | maxTurns 不越界；崩溃重试/工具白名单/_parse_action/_clamp_summary/artifact TTL 正确 |
| R3 契约/健壮性 | ✅ PASS | 崩溃优雅降级；artifact 双栈降级（Redis→内存）；不抛未捕获异常 |
| R4 安全 | ✅ PASS | `yaml.safe_load`；artifact key `uuid4` 不可预测；无敏感原文泄漏 |
| R5 性能/边界 | ✅ PASS | messages 截断 4000 + artifact 全量；摘要 ≤2000；4 内置定义字段完整 |
- 2 项加固已落地：①未知子代理统一 `ok=False`（非裸 KeyError）②gather `return_exceptions=True` 批级隔离。

## 3. 测试与工程质量
- `tests/test_contract_task92.py`：**6/6 通过**（GWT①②③ + 摘要裁剪 + 批隔离加固）
- 回归：`test_contract_task23.py` 6/6 全过；合计 **12/12**
- 真实 Redis artifact 落库：`scripts/_verify_task92_redis.py` PASS
- compileall + 语法诊断：0 错误

## 4. 待编次者验收
全部 GWT 达标、独立审查通过、无回归。固化纪律：未经验收不进入 task24/task93。