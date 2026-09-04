# task-P1L: LLM 档位延迟治理（P95 ≤8s / TTFT ≤3s）

> **类型**：backend（AI 链路优化）｜**执行工具**：Trae｜**阶段**：收尾专项｜**工作量**：L
> **来源**：task39 批判①（P0 遗留）+ task29 批判②（P95 超标历史）
> **依据**：task39 实测 P95 25~32s（目标 8s）/ TTFT P95 17~21s（目标 3s）

## 1. 背景（真实数据）
- task39 压测：L1 P95 25s / L2-tool 26s / L2-learning 32s（目标 ≤8s）；TTFT P95 L1 21s / L2 17.5s（目标 ≤3s）
- **根因**：单次 L1 请求 = **5 次 LLM 串行调用**（fan_out 子代理已并行，串行部分是主链路 5 次调用）；延迟 = 链路深度 × 单次延迟（单次 1.4~5.0s）

## 2. 优化方向（竞品对标）
| 方向 | 竞品实证 | 落点 |
|---|---|---|
| **削减链路深度** | Anthropic Building Effective Agents（workflow vs agent 取舍）| graph.py 主链路调用次数 5→≤2 |
| **prompt cache 降延迟** | Claude prompt caching（cache_read ~10% 费率，命中减延迟）| prompt_cache.py + task-C2 填充已就绪 |
| **流式分段返回** | Codex 流式输出（token 逐次生成，TTFT 即达标）| generator.py generate_stream 首包尽早返回 |
| **子代理并行化** | Anthropic 多智能体并行 | fan_out 子代理真正并行（当前可能串行）|

## 3. 实现规划要点
- 剖析主链路 5 次串行 LLM 调用点，标记可并行/可剪枝/可缓存
- 引入 prompt cache 实测命中降延迟；流式首包提前返回
- 每次改动契约测试 + 窗口内压测复测（P95/TTFT）

## 4. 验收标准（Given/When/Then）
- Given 同一压测脚本，When 优化后窗口内跑，Then L1~L3 P95 ≤8s、TTFT ≤3s
- Given 链路改动，When 回归，Then 现有契约测试全绿，回答质量不降（LLM-as-judge 抽查）

## 5. 交接
- 完工：test-reports\task-P1L-completion-report.md（优化前后 P95/TTFT 对比）→ 停下等验收
- 测试窗口：LLM 压测仅 12:00-14:00/18:00-9:00