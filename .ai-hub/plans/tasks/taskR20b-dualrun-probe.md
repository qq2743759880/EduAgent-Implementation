# taskR20b:新旧路径双跑探针(W0,R02 灰度的收敛基准)

> 派单平台:ZCode Agent。必读:dev-plan-reshape-r v1.1 W0/audit-edu-chat-langgraph.md(P2-23 双意图规则/P2-17 TTFT)/app/chat/flows/agent.py 与 app/ai/graph.py 现状。具名资产:无外部 skill;竞品锚点=[LangGraph ToolNode](https://reference.langchain.com/python/langgraph.prebuilt/tool_node/ToolNode)。

## 目标
离线批跑 100 条请求,量化 run_agent_turn(流式现路径)与六节点图的行为分歧,产出 R02 灰度收敛基准。

## 设计要点
1. 样本:100 条(eval_set32 全量+chat 历史真实 query 采样+边界构造:chitchat/工具意图/知识深查),存 scripts/eval/dualrun_samples.json。
2. 双跑:同 query 分别走 run_agent_turn 与 run_agent(非流式图入口),**只取中间层信号**(intent/need_search/retrieved chunk_ids/检索计数)+10% 抽样答案文本;TTFT 代理=start→首检索完成间隔打点。
3. diff 报告:intent 分歧率/need_search 分歧率/docs 重合度(Jaccard)/TTFT 分布对比,落 test-reports/dualrun-baseline.md+JSON。
4. 禁项:禁改两条路径代码(只加打点 hook 允许,单独 commit 可 revert);禁动生产数据;LLM 调用走既有配置。

## GWT(机验)
- Given 100 样本;When 双跑;Then 报告含四指标+逐样本明细;P2-23 的 intent 分歧被量化(预期>0,作为灰度必须收敛的初值)。
- Given 重跑;Then 分歧率波动 <2%(采样确定性)。

## 完工报告
test-reports/R20b-completion-report.md:分歧率数字/样本构成/灰度收敛阈值建议(intent/docs 两指标,交用户裁)。
