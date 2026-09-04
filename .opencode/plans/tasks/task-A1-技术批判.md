# task-A1 验收批判（强制技术批判）

> 对象：task-A1 可插拔 Harness 抽象（Trae，commit 8f8ec40）
> 结论：**验收通过**（AC1~AC5 全绿、委派设计零风险、竞品对标完整）。

## 实证结果
- commit `8f8ec40`（7 文件 +536/-7）；harness/{base,sixnode,registry} 交付。
- 契测 **38 passed 1 skipped**（A1 11 + task24 6 + task92/93 21）实跑确认。
- AC1 六抽象方法签名一致；AC2 默认等价 task24 逐字节；AC3 mock 插拔拓扑不变节点走新实现；AC4 keep_sixnode 保留；AC5 eval harness 不裂。
- 4 条技术批判含竞品实证 + 可落地优化。

## 批判 1（P2）：预处理节点（skill/compact/context_edit）未纳入 Harness 接口
- **问题**：切换自定义 harness 时这三节点仍是 sixnode 实现。
- **竞品对标**：Claude Managed Agents 三层各自独立替换；Codex trait 注入。
- **方案**：作为 task-E1 接口扩展（报告建议），当前委派留好接缝。

## 批判 2（P2）：SixNodeHarness 反向依赖 graph（委派模式）
- **问题**：反向 import graph，每次调用多一次模块属性查找，双向耦合。
- **竞品对标**：Codex codex-core 单向依赖（节点依赖接口）。
- **方案**：真搬迁——节点函数搬入 SixNodeHarness 方法体，graph.py 退化为纯构建器（先加契约锁再切）。

## 批判 3（P2）：未知 HARNESS_IMPL 无 fallback，配置错误拖垮整图
- **问题**：build_harness 遇未注册 impl 直接 raise，进程级失败。
- **方案**：fallback 到 sixnode + log warning；启动校验 HARNESS_IMPL 合法性。

## 批判 4（P3）：拓扑锁定仅靠测试硬断言
- **问题**：keep_sixnode 拓扑依赖测试硬断言，改边漏改测试运行时才暴露。
- **方案**：抽 EXPECTED_SIXNODE_TOPOLOGY 常量，启动 fail-fast 自检。

**结论**：四条为加固/后续项，转 critique-to-tasks 落实；task-A1 本体验收通过。