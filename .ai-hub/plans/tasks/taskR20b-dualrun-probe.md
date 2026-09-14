# taskR20b:新旧路径双跑探针(W0,R02 灰度收敛基准)v1.1

> 派单平台:执行 agent(用户转交)。必读:dev-plan-reshape-r v1.1 W0/audit-edu-chat-langgraph.md(P2-23/P2-17)/app/chat/flows/agent.py 与 app/ai/graph.py。
> v1.1 修正(终审 A1):**LLM 确定性约束+门槛指标收窄**。

## 步骤
1. 样本 100 条,**构成钉死(可复现)**:①eval_set32 全量(32,来源 scripts/eval/data/)②chat 历史真实 query 50 条——表=chat_message(与 chat_session join 取 session),过滤:role=user、content 长度≥10 字符、对应会话 status 正常,按 created_at 倒序取分布(每会话≤3 条防单会话偏置),固定 seed 记录抽样 SQL/参数③边界构造 18 条=手写并入库(6 chitchat/6 工具意图[add/echo/检索类]/6 知识深查),构造清单逐条入报告。全部样本落 dualrun_samples.json(含 source 字段标注三类来源)。
2. **确定性强制**:凡 LLM 参与(decide_agent_plan/图内路由)固定 **temperature=0**(或供应商 deterministic 等价参数;以 monkeypatch 级配置注入,不改正产代码;单独 commit 可 revert)。同 query 双跑两次先验证自身稳定:不稳定则记录并进一步固化(seed/prompt 缓存),**"分歧"必须是路径分歧不是采样噪声**。
3. 双跑:同 query 走 run_agent_turn 与 run_agent,取中间层信号 intent/need_search/retrieved chunk_ids/检索计数;**TTFT 代理=start→首检索完成间隔打点**。
4. **门槛指标只取 intent/docs 两项**(规则+检索决定,可复现);**答案语义不作为灰度门槛**——30% 抽样仅入报告供人读,不入收敛判定(统计上无意义,终审判定成立)。
5. diff 报告:intent 分歧率/need_search 分歧率/docs Jaccard 分布/TTFT P50/P95 对比,落 test-reports/dualrun-baseline.md+JSON。

## 禁项
禁改两条路径正产代码(打点 hook+temp 注入单独 commit);禁动生产数据;禁 Playwright。

## GWT(机验)
①100 样本报告含四指标+逐样本明细+样本构成清单(source 可复现:chat 采样的 SQL/seed/边界构造逐条文本);②temp=0 下同 query 自跑两轮 intent 稳定(不稳定项列表化并处置);③P2-23 分歧被量化为具体数字(灰度收敛初值)。

## 交付
commit `feat(r)/R20b-dualrun-probe`(样本/hook/报告);报告含**灰度门槛建议值核对**:intent 分歧<5%/docs Jaccard>0.9/千条样本/连续 3 天(五条件已写入 C-R-EVAL 草案,执行者只报告数字不调阈值)。
