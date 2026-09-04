# task-E1 验收批判（强制技术批判）

> 对象：task-E1 影子模式 + 对抗采样 + 金丝雀 + 4 维 Judge（Trae，commit 0990348）
> 结论：**验收通过**（AC1~AC5 全绿、ponytail 简化、批判承接 P10 治理）。

## 实证结果
- commit `0990348`（8 文件 +1006/-1）；retriever 影子 hook + canary + adversarial_set + 4d judge 交付。
- 契测 **70 passed 1 skipped**（E1 15 + task24/93/95/96 回归 55）实跑确认。
- AC1 影子主路径逐字节一致不阻塞；AC2 对抗集 22+22 含 ground_truth；AC3 4 维 Judge 均值/分位；AC4 金丝雀 1%→3 天→全量+异常回滚；AC5 回归。
- 批判承接 P10 四维度（分布/维度/全量/断层）根因治理。

## 批判 1（P2）：影子默认变体是规则重排（零 IO），未接真实检索变体
- **问题**：默认对比 rule_rerank vs sidecar，非"另一套检索配置"（报告披露 set_shadow_variant 待注入）。
- **方案**：窗口内用 set_shadow_variant 接真实 rerank 参数变体跑线上影子。

## 批判 2（P2）：金丝雀窗口状态未持久化（重启丢窗口）
- **问题**：decide 为纯函数状态机，3 天窗口 started_at 未落库（报告披露交 task-O1）。
- **方案**：task-O1 指标库落地窗口状态，生产金丝雀可靠。

## 批判 3（P2）：4 维 Judge 真实 LLM 校准未做（仅确定性伪评分演示）
- **问题**：真实 LLM-as-judge 校准（维度权重）留测试窗口。
- **方案**：窗口内跑真实 judge_answer_4d 校准。

**结论**：三条为后续校准/接入项，转 critique-to-tasks；task-E1 本体验收通过。