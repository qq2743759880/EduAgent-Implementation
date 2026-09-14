# R20-b 新旧路径双跑探针 · 完工报告（W0）

> 执行 agent 回传 · 2026-09-14 · 只回传路径引用，本报告即机验锚点
> git_rev: `57491e529b183eb87165f40652563bc413c5fa3b`（短 `57491e5`，含 commit `f045416` temp0 注入）
> 样本 seed=20260914 · 100/100 valid · 0 error · 0 unstable

---

## ① 资产消费证据（实读文件 + 发现）

实读（路径引用，未凭印象）：
- `plans/tasks/taskR20b-dualrun-probe.md` v1.1（唯一需求源）
- `plans/dev-plan-reshape-r.md`（W0 节 + 终审五问 A1）
- `plans/audit-edu-chat-langgraph.md`（P2-23/P2-17 出处）
- `app/chat/flows/agent.py`（旧路径 run_agent_turn:218 / decide_agent_plan:73）
- `app/ai/graph.py`（新六节点图 run_agent:775 / build_graph:606）
- `app/ai/harness/sixnode.py`（route:57 规则路由 0-LLM；fan_out knowledge 直连检索:151-215）
- `app/ai/rule_router.py`（classify_intent vs classify_intent_or_default）
- `scripts/eval/build_eval_set32.py`、`scripts/eval/data/rag_eval_set32.json`（R20-min 冻结 32）
- `app/config.py`（LLM_TEMPERATURE=0.0 / RULE_ROUTING_ENABLED=True / USE_AGENT_LOOP=True）

关键发现：
- 两条路径路由均为 **0-LLM 纯正则**（RULE_ROUTING_ENABLED=True），故 intent 分歧天然来自规则，非采样噪声。
- 旧路径检索 `use_hyde=True, top_k=12, final_max_k=5`；新路径 knowledge 直连 `use_hyde=False, top_k=8, final_max_k=5`——**检索参数结构性不同**，这是 docs Jaccard 分歧的主要来源（非 bug，属 P2-23 分歧面）。
- `run_agent` 返回体 `docs` 恒空（audit P1-5）→ 新路径 docs 经 `r20b_hook.py` 进程内 spy 捕获，隔离断言 `flows_binding_is_orig=True` 通过。

## ② 批判承接核对（命令输出如实附）

命令（项目根目录，勿用 `--task-doc` 全文模式）：
```
node D:\.ai-hub\skills\tt\scripts\critique-backlog-next.mjs --task "双跑 R20 chat graph agent"
```
承接判定 = **HIT C-16..C-24**（9 条）。逐条核对 tracker（`.ai-hub/plans/critique-tracker-v1.md`）：C-16 pgvector 收敛、C-17 series/1 慢查询缓存、C-18 Milvus 错误契约脱敏、C-19 React 迁移 B0、C-20 deploy.mjs prod 断言、C-21 进程治理、C-22 security-check 聚合门、C-23 部署组件面、C-24 doctor 子命令——**全部为部署/前端/性能/运维类批判，与 chat 双路径 intent/docs 探针无语义承接关系**（关键词 `chat`/`agent` 命中）。

**本任务承接项 = 无。** （注：首次从 `edu-agent/` 运行时脚本回退到 TT 全局 tracker，误报 C-10/11/12 硬闸；从项目根运行即读本项目 tracker，EXIT 0，无硬闸。）

## ③ 样本构成清单（source 三类，可复现）

100 = eval_set32 32 + chat_history 50 + edge 18（6 chitchat/6 tool/6 knowledge）。逐样本见 `edu-agent/scripts/eval/dualrun_samples.json`（含 source 字段）。

- **① eval_set32（32）**：R20-min 冻结 `rag_eval_set32.json`（built_at=2026-09-14T11:17, seed=20260914, recall_topk=150），全量取 32 条 query。
- **② chat_history（50）** SQL（逐字）：
  ```sql
  SELECT m.session_id, m.user_id, m.content, m.created_at FROM chat_message m
  JOIN chat_session s ON s.session_id = m.session_id
  WHERE m.role='user' AND CHAR_LENGTH(m.content)>=10 AND s.yn=1
  ORDER BY m.created_at DESC LIMIT %s
  ```
  params limit=120；seed=20260914；per_session_cap=3；实测 eligible_total=72、prelimit_rows=72、覆盖会话 49。确定性 = SQL 相对序 + 种子内洗牌（新插入不改已选集）。
- **③ edge 18 条逐字**（6+6+6，见 dualrun_samples.json 与 baseline 报告）：
  - chitchat：你好呀，你叫什么名字？ / 今天天气真不错，适合出去走走。 / 讲个笑话听听吧。 / 你都能做些什么？ / 晚安，明天见。 / 我有点无聊，陪我聊聊天。
  - tool：帮我算一下 128 乘以 46 等于多少。 / 请把 hello 用 python echo 输出一遍。 / 计算 (15+27)*3 的结果。 / 帮我执行一段代码：print(sum(range(10)))。 / 查一下 2 的 20 次方是多少。 / 用工具算出 2024 年有多少天。
  - knowledge：线性代数中特征值和特征向量的几何意义是什么？ / 雅思听力Section 4的常见陷阱有哪些？ / 解释一下光合作用的光反应和暗反应区别。 / 权责发生制和收付实现制在会计确认上的核心差异？ / 考研英语阅读的精读方法应该怎么做？ / Python装饰器的底层实现机制是什么？

## ④ temp=0 自稳定预验结果与不稳定项处置

- 注入：`r20b_temp0.py`（commit ① f045416，可整体 revert）——钉 `settings.LLM_TEMPERATURE=0.0` 并包住唯一 LLM 收口 `_ChatClient.call_chat`，无论调用方传何 temperature 一律覆写 0（含旧路径 HyDE 改写）。
- 每样本同 query 双轮 intent 预验（旧=decide_agent_plan×2；新=route_node×2）：**100/100 双稳，unstable=0**。
- 跨进程复验 `r20b_gwt_verify.py`：抽 10 样本跨进程×时间重跑，**mismatch=0，PASS**（见 `scripts/eval/r20b-gwt3-verify.json`）。
- 处置：无不稳定项，无需冻结/补轮。

## ⑤ 四指标 + 逐样本明细文件路径

逐样本明细：`edu-agent/scripts/eval/dualrun_results.json`（100 条 compare：old/new intent、need_search、doc_ids、Jaccard、TTFT、nodes、retrieval_queries）。汇总：`dualrun-summary.json`。人读：`test-reports/dualrun-baseline.md`。

| 指标 | 实测 |
|---|---|
| **intent 分歧率（门槛）** | **0/100 = 0.0%**（分源全 0） |
| **need_search 分歧率（报告项）** | 0/100 = 0.0% |
| **docs Jaccard（门槛）** | mean=**0.6411**, p50=0.6667, p95=1.0, min=0；=1 共 47、<0.5 共 43、=0 共 7 |
| TTFT 代理 P50/P95 | 旧 3.412 / 4.103 s；新 3.512 / 4.513 s |
| 答案语义 30% 抽检（不入门槛） | done=30, equivalent=27, not_equivalent=1, judge_failed=2 |

Jaccard 分源：eval_set32=0.877、edge_chitchat=0.967、edge_knowledge=0.603、edge_tool=0.500、**chat_history=0.473（最低，真实用户查询分歧最大）**。

## ⑥ 灰度门槛建议值核对（只报实测，不调阈值）

| 五条件 | 推荐值 | 本批实测（W0 初值） |
|---|---|---|
| 样本量 | 千条 | **100 条/批**（千条由 R02-b 灰度期累积） |
| 连续 3 天 | 连续 3 天 | **单日 1 轮**（连续性由灰度期考核） |
| intent 分歧 | <5% | **0.0% ✅** |
| docs Jaccard | >0.9 | **0.6411 ❌ 未达**（43/100 <0.5，真实 chat 仅 0.47） |
| P95 TTFT 容差 | 新 ≤ 旧 P95×1.1 | 旧 4.103s vs 新 4.513s（新 = 旧 1.10×，**贴边**） |

**P2-23 量化结论**：意图/是否检索两规则已完全对齐（0% 分歧）；但**文档重合度仅 0.64**，未达 0.9 门槛——主因是两路径检索参数结构性差异（旧 hyde=on/top_k=12 vs 新 hyde=off/top_k=8）。此即 R02 灰度收敛的初值，不代表新路径错误，而是两条路当前不等价的实证。

## ⑦ git_rev + 环境自证输出

- git_rev: `57491e5`（全量 HEAD `57491e529b183eb87165f40652563bc413c5fa3b`）
- 自证：MySQL localhost:3306 OK；Milvus 192.168.85.101:19530 v2.5.5，`edu_knowledge` 在；chat eligible=72；fast LLM 冒烟无 402（model=minimax-m3，~2.5s）。
- **已知环境偏差（如实登记，非代码缺口）**：strong=deepseek-v4-flash 返回 HTTP 402 Insufficient Balance，answer 节点按设计降级 fast(minimax-m3)；**不影响门控 intent/docs 指标**（门控走规则路由 + Milvus 检索）。
- 过程发现并修复（非正产代码）：先前崩溃运行使 Redis 防过载并发槽 `chat:concurrent:1` 卡在 2，导致新路径全被 `user_concurrent_over_limit` 拒绝（首轮 docs 全空、Jaccard 0.06 的假象）；探针启动已加自动复位，复跑后指标自洽。

## 自检（三视角）

- **边界**：18 条边界全跑通；1 条标注偏差——edge_chitchat「你好呀，你叫什么名字？」因正则要求「你好」后直接接身份询问词、夹了「呀」未命中，两路径一致判为 knowledge（非 chitchat），intent_match 仍为 True，如实记录不误标。
- **错误反馈**：n_error=0；Neo4j `QuestionTag` 类型校验、rerank sidecar 不可达均按设计降级，不影响指标。
- **可复现**：seed/SQL/边界逐字入 samples.json；GWT③ 跨进程 PASS；temp0 注入独立 commit 可 revert。

## 产物路径

- 报告：`test-reports/R20b-completion-report.md`（本件）、`test-reports/dualrun-baseline.md`
- 数据：`edu-agent/scripts/eval/{dualrun_samples,dualrun_results,dualrun-summary}.json`、`r20b-gwt3-verify.json`
- 脚本：`edu-agent/scripts/eval/r20b_{dualrun_probe,hook,temp0,gwt_verify}.py`
