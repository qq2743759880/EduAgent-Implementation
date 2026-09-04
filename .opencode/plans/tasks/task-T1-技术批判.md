# task-T1 验收批判（强制技术批判）

> 对象：task-T1 工具调用闭环（Trae，commit cfcc9c3）
> 结论：**验收通过**（AC1~AC5 全绿、状态机纯逻辑可测、竞品对标到位）。

## 实证结果
- commit `cfcc9c3`（8 文件 +2601）；retry_loop.py（纯逻辑状态机）/executor.py 编排交付。
- 契测 **20 passed**（T1 11 + task33 回归 9）实跑确认。
- AC1 四步闭环 normal→rewrite_args→switch_tool→MANUAL_GUIDE；AC2 人工指南 4 字段；AC3 拒绝熔断（Redis TTL=300 降级内存，对齐 Codex auto-review 3 连拒）；AC4 事件埋点（6 字段+trace_id）；AC5 call_tool 原路径不变。

## 批判 1（P2）：DB 枚举 ALTER 未执行，MANUAL_GUIDE/REJECTION_LIMIT 生产落库会告警吞掉
- **问题**：refactor_sql/task-T1-add-status-enum.sql 需目标库发布前执行（报告如实披露为运维待办）。
- **方案**：数据库验收/发布流程纳入 ALTER 执行；本地单测已 mock 验证写入调用。

## 批判 2（P2）：TOOL_FALLBACK_MAP 备用工具可能未注册（calculator/search_knowledge）
- **问题**：备用工具若未在 mcp_tool 注册，第 3 步判失败自然走指南（安全降级，但能力未达预期）。
- **方案**：后续接子代理 search_knowledge 服务做真实降级检索。

## 批判 3（P2）：LLM 改写 args 仅窗口内生效，规则跳级兜底语义弱
- **问题**：TOOL_RETRY_LLM_REWRITE=True 但窗口外回退"原参透传"，改写价值未达（报告披露）。
- **方案**：窗口内补真实 LLM 改写实测；或增强规则改写（参数名映射）减少 LLM 依赖。

**结论**：三条为运维/后续增强项，不阻塞 task-T1。