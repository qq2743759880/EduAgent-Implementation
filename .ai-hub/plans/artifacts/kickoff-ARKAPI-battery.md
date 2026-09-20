# kickoff: W-NEXT-ARKBAT-001 火山方舟 ark-code-latest 实战测试计划（用户已提供大额度 API，已切换为 FAST 档）

> 你是 W-NEXT-ARKBAT-001 执行 agent（yy 并行流水线）。C-01：编排者逐断言独立实证验收。
> 已完成前置：.env 已切 `LLM_MODEL_FAST=ark-code-latest`（BASE_URL=https://ark.cn-beijing.volces.com/api/plan/v3，key 在 .env LLM_FAST_API_KEY，禁外泄）；编排者探活 200/1.8s；**发现该模型为混合推理型（回包带 reasoning_content）——任务 0 先实测 thinking 关闭兼容性**。
> ⚠ Mimosa 约束：DB 参数绑定；LLM 调用走脚本文件（禁中文过 GBK 控制台）。

## 任务 0：thinking 兼容性（先做）
Ark/Doubao 系混合模型支持 `thinking: {"type":"disabled"}` 与否实测：带/不带各 3 次，对比延迟与 reasoning_content。若支持→建议 generator.py 的 thinking 注入分支扩展到 FAST 档（走变更单，本批不实施只建议）；若不支持→FAST 档延迟预算评估如实登记。

## 任务 1：性能基线（对照 deepseek-flash 基线）
非流式 ×30 + 流式 ×30（真实 chat 链路 8011 实例，`LLM_FAST_BASE_URL/MODEL` 进程级注入）：P50/P95 延迟、TTFT、token 速率、失败率。对照组=同脚本把 STRONG 指向 deepseek-flash 各 30 轮。产出对比表。

## 任务 2：稳定性/限流画像
并发 5×10 轮（线程池）测限流触发阈值与 429 退避行为；连续 200 次小请求错误率；长文本（2k tokens 输入）与超短输入各 10 次。产出：限流阈值/退避建议/错误分类表。

## 任务 3：质量抽检（与 deepseek-flash 盲评）
eval64-v2 取 20 条 query，两模型各生成答案 → LLM 盲评（用 STRONG deepseek-flash 当裁判，A/B 随机序防偏）：相关性/事实性/简洁性各 1-5 分，产出胜平负表。**裁判模型与被评模型不同源**（DeepSeek 评 Ark，无自评偏置）。

## 任务 4：故障转移演练
模拟 STRONG（deepseek）不可达（env 注入错误 key）→ 验证自动切 FAST（ark-code-latest）链路 200；再模拟 FAST 不可达→降级行为如实记录。产出：故障转移矩阵。

## 交付
- 脚本 `scripts/eval/ark_battery.py`（子命令式：perf/stress/quality/failover，可复跑）
- 产物 `data/ark_battery/`（全部 JSON）+ 报告 `test-reports/ARKBAT1-completion-report.md`
- 报告含：对比表/限流画像/盲评胜平负/故障矩阵/**「ark-code-latest 是否够格当唯一 FAST 档 + 是否可升级为 STRONG 备选」的结论与证据** / ≥3 P0 自批判 / 批判承接核对（承接用户 API 备用裁定）/ 资产消费证据
- commit + push；lock `arkbat.lock` 用完删

## 红线
禁碰 app/**、config.py 默认值（.env 已由编排者改好，禁再动）、contracts/**、trade/**；key 全程脱敏不入报告/日志/git。执行到底。
