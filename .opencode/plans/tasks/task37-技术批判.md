# task37 验收批判（强制技术批判）

> 对象：task37 清理遗留代码 + 测试修复（Trae，commit d1530d2→c8e99d8）
> 结论：**验收通过**（GWT①~④ 全达成、批判承接 6 项核对、回归分类诚实）。

## 实证结果
- commit 链完整（d1530d2 GWT①/22fbf64 GWT②/3a91f7d+0a28a71+c8e99d8 GWT③/5e76971 GWT④，HEAD=c8e99d8）。
- GWT① 死代码：app/admin/course_admin 删除，curriculum_ 61→22（存活全为 308 层有意保留）。
- GWT② 断言：test_auth/error_codes 统一字符串码，33 例 PASS，生产零改动。
- GWT③ 91 项：源头拦截 conftest（8000/8001/8003 skip）+ 4 处真实失配修复（reranker async/agent_loop/task23 污染/perf_guard async fake）。
- GWT④ 前端项 discrepancy 上浮 TraeWork。
- 回归：586 passed/140 skip/2 failed/7 errors，**0 个意外生产缺陷**；test_task22 event-loop 隔离 7/7 全过。

## 批判 1（P2）：test_contract_task22 event-loop 隔离脆弱性未修（定性不修）
- **问题**：模块级全局 event loop 与 pytest-asyncio 冲突 → 7 ERROR（隔离 7/7 全过，无生产缺陷，报告诚实披露）。
- **方案**：后续专项改 pytest-asyncio 托管 loop（改写风险高，合理留待）。

## 批判 2（P2）：test_live_ai_hub_124 断言 124 vs LIVE 178 失败
- **问题**：LIVE skills 增长到 178，契约测试断言硬编码 124（env-expected）。
- **方案**：更新基线为动态计数（≥124）或 178。

## 批判 3（P2）：前端两项（MarkdownView/MutationCache）仅上浮未修
- **问题**：discrepancy 单就绪，实际修复待 TraeWork（边界正确）。
- **方案**：派单 TraeWork 落实。

## 批判 4（P3）：curriculum_ 残留 22 处（308 层有意保留），tracker"grep=0"口径冲突
- **问题**：critique-backlog 的「grep curriculum_=0」与 308 重定向层冲突（报告诚实说明按任务文档口径）。
- **方案**：更新 tracker 口径为"死代码归零"（非全 grep=0）。

**结论**：四条均为后续/口径项，不阻塞 task37；前端两项转 TraeWork 派单。