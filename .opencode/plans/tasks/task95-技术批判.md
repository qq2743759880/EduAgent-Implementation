# task95 验收批判（强制技术批判）

> 对象：task95 MCP 增强 R3（Trae）
> 结论：**验收通过**（代码质量确认、竞品对标完整；git 提交由编排者补入仓库）。

## 实证结果
- 契测 **20 passed** 实跑确认；deferred/auth/reconnect/dynamic_update/isolation 5 模块交付。
- GWT① deferred 摘要列表 key 稳定（重写描述不破坏前缀）；② 自动重连指数退避 ≤5；③ 子代理 mcpServers 隔离 + per-tool 结果截断；④ OAuth refresh + API key。
- 竞品对标：Claude Code prompt-caching（deferred 保护前缀）/ mcp（OAuth/重连）/ sub-agents（隔离）官方文档逐条引用。
- 测试窗口：零真实 LLM。

## 批判 1（P1，git 纪律）：task93/task95 提交未入库，需编排者补提交
- **问题**：执行者报告"本仓库无 commit + git read-tree --empty"——实际当前仓库有完整历史，task93(335c0e5)/task95(b33d48e) 均未持久化到 refs；代码在磁盘但未入库。
- **处置**：编排者已补提交 d096338（task93）+ e9d4546（task95）。**教训：执行者提交前必须 `git rev-parse --show-toplevel` 确认在正确仓库**。

## 批判 2（P1，长期风险）：edu-agent/ 大量核心代码未跟踪
- **问题**：app/ai/、app/chat/、app/mcp/ 历史任务大部分文件仍是 `??` 未跟踪，仅 task08/09/10/96 等特定文件入库；工作区存在大量未提交源码，误删/冲突会丢。
- **方案**：task37（清理）或新任务做一次全量基线提交（git add -A edu-agent/ 审阅后），建立完整历史锚点。

## 批判 3（P2）：deferred 未接入真实 tool_specs 决策链路
- **问题**：deferred 摘要列表独立实现，未验证与 task27 tool_specs/build_decision_prefix 的实际集成（仅单测验证前缀稳定）。
- **方案**：task97（缓存监控 R5）接入时端到端验证 deferred+tool_specs 协同。

**结论**：批判①已处置（补提交），批判②转 task37，批判③转 task97；task95 本体验收通过。