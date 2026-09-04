# P1 批判落实批次验收批判（强制技术批判）

> 对象：P1 批判落实批次 11 项（Trae，commit 3fa1735→3a569fe）
> 结论：**验收通过**（11 项全落地、回归全绿、sync 路径澄清）。

## 实证结果
- P1 11 commit 链完整（3fa1735 基线 → 3a569fe HEAD），覆盖 S1②/M1②③/G1②③/C2③/O1①/A1①②③④/R1①。
- R1-① fp32：RERANKER_PRECISION 配置 + 精度感知 _load；fake torch 驱动真实逻辑验证排序稳定+噪声<1e-4（fp16 ~1e-2 对照）；契测 19 passed 2 skipped 实跑确认。
- 回归：R1 19/2skip + R1fp32 5/1skip + A1 10 passed。
- sync 路径澄清：sync.ps1 在 D:\.ai-hub\sync.ps1（编排者侧），非仓库内——后端 agent 找不到是正常的，已由编排者执行。

## 批判 1（P2）：test_contract_task94.py::test_live_ai_hub_124 因 AI-Hub 现含 178 skills 失败
- **问题**：LIVE 测试硬编码 124，实际中心库 178（skill 增长）——预存测试，非 P1 回归（报告披露）。
- **方案**：更新断言为动态计数（≥124）或 task94 后续维护。

## 批判 2（P2）：R1 批判②③（sidecar 部署/Redis 队列）仍为运维待办
- **问题**：sidecar 8601 当前主链路默认直连（非 sidecar）；Redis 队列可选未启用（报告披露遗留）。
- **方案**：部署时启动 sidecar + RERANK_SIDECAR_ENABLED=True 灰度；高峰评估后启 Redis 队列。

## 批判 3（P2）：A1-② 真搬迁后 graph.py 薄壳化，需确认 task24 durable 三红线全守
- **问题**：节点逻辑搬入 SixNodeHarness，build 前 monkeypatch 语义需保持（报告称三红线验证通过）。
- **方案**：task39 压测或集成验证时复跑 durable/子代理链路确认。

**结论**：批判①为预存测试更新（转 task94 维护），②转部署待办，③为验证项；P1 本体验收通过。