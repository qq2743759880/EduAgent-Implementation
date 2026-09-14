# taskR20b 双跑基线报告（W0 · R02 灰度收敛基准）

- ran_at: 2026-09-15T02:07:00  |  git_rev: `332b8a5`  |  seed: 20260914
- 样本 100/100（eval_set32 切片 32 + chat 真采 50 + 边界 18）｜valid 100｜error 0｜unstable 0
- 探针身份: user_id=1（检索租户按 UserRole.STUDENT（对齐生产非 admin 租户范围））
- 生产默认参数: use_hyde=True, top_k=12, final_max_k=5, cutoff=0.4, enable_graph=True
- hook 隔离校验: {"module_attr_is_spy": true, "flows_binding_is_orig": true}

## 门槛指标（仅此两项入灰度门槛，详档 v1.2 终审 A1）

- **intent 分歧率**: 0/100 = **0%**（五条件参考 <5%）
  - 分源: {"chat_history": {"n": 50, "diverge": 0}, "edge_chitchat": {"n": 6, "diverge": 0}, "edge_knowledge": {"n": 6, "diverge": 0}, "edge_tool": {"n": 6, "diverge": 0}, "eval_set32": {"n": 32, "diverge": 0}}
- **docs Jaccard**: mean=0.8533, p50=1.0, p95=1.0, min=0.0, max=1.0（五条件参考 mean>0.9；=1 共 82 条，<0.5 共 18 条，=0 共 8 条）
- need_search 分歧率（报告项，非门槛）: 0/100 = 0%｜分源: {"chat_history": {"n": 50, "diverge": 0}, "edge_chitchat": {"n": 6, "diverge": 0}, "edge_knowledge": {"n": 6, "diverge": 0}, "edge_tool": {"n": 6, "diverge": 0}, "eval_set32": {"n": 32, "diverge": 0}}

## TTFT 代理（start→首检索完成，P2-17 承接）

| 路径 | n | P50(s) | P95(s) | min | max |
|---|---|---|---|---|---|
| 旧 run_agent_turn | 100 | 3.401 | 4.017 | 0.158 | 15.579 |
| 新 run_agent(图) | 100 | 3.466 | 4.52 | 0.28 | 9.303 |

- P95 容差对照（五条件参考：新 ≤ 旧 P95 × 1.1）: 旧 4.017s vs 新 4.52s

## 确定性设计（详档 v1.2 A1 承接）

- RULE_ROUTING_ENABLED=True / LLM_TEMPERATURE=0.0 / USE_AGENT_LOOP=True 启动断言通过（路由 0-LLM 纯正则；temp0 注入强制所有 LLM 收口含旧路径 HyDE 改写 temperature=0.0）。
- 每样本同 query 双轮 intent 预验（旧=decide_agent_plan；新=route_node 单节点）；不稳定样本 0 条。
- 答案语义 30% 抽检（仅入报告）：n_done=30, equivalent=27, not_equivalent=3, judge_failed=0

## 样本构成（可复现）

- eval_set32: rag_eval_set32.json（R20-min 冻结，builder=r20min_run.py --mode build (query 提取复用 build_eval_set32._extract_query), built_at=2026-09-14T11:17:03.951108+00:00, seed=20260914, n_cases=32, recall_topk=150）；本探针全量取 32 条 query。
- chat 采样 SQL: `SELECT m.session_id AS session_id, m.user_id AS user_id, m.content AS content, m.created_at AS created_at FROM chat_message m JOIN chat_session s ON s.session_id = m.session_id WHERE m.role = 'user' AND CHAR_LENGTH(m.content) >= 10 AND s.yn = 1 ORDER BY m.created_at DESC LIMIT %s`（params={'limit': 120}, seed=20260914, eligible=72, 会话数=49）
- SQL 相对序=created_at 倒序 LIMIT 120；确定性=python 种子内洗牌（新插入数据不改已选集，仅 eligible_total 漂移），会话配额≤3 防单会话偏置
- 边界 18 条逐字:
  - (chitchat) 你好呀，你叫什么名字？
  - (chitchat) 今天天气真不错，适合出去走走。
  - (chitchat) 讲个笑话听听吧。
  - (chitchat) 你都能做些什么？
  - (chitchat) 晚安，明天见。
  - (chitchat) 我有点无聊，陪我聊聊天。
  - (tool) 帮我算一下 128 乘以 46 等于多少。
  - (tool) 请把 hello 用 python echo 输出一遍。
  - (tool) 计算 (15+27)*3 的结果。
  - (tool) 帮我执行一段代码：print(sum(range(10)))。
  - (tool) 查一下 2 的 20 次方是多少。
  - (tool) 用工具算出 2024 年有多少天。
  - (knowledge) 线性代数中特征值和特征向量的几何意义是什么？
  - (knowledge) 雅思听力Section 4的常见陷阱有哪些？
  - (knowledge) 解释一下光合作用的光反应和暗反应区别。
  - (knowledge) 权责发生制和收付实现制在会计确认上的核心差异？
  - (knowledge) 考研英语阅读的精读方法应该怎么做？
  - (knowledge) Python装饰器的底层实现机制是什么？

## 五条件门槛对照（只报数，阈值裁定属用户/编排者）

| 条件 | 当前值 |
|---|---|
| 千条样本 | {"当前值": "100 条/批（W0 初值；千条由 R02-b 灰度期累积）"} |
| 连续3天 | {"当前值": "单日 1 轮（连续性由 R02-b 灰度期考核）"} |
| intent分歧<5% | {"当前值": "0.0%"} |
| docsJaccard>0.9 | {"当前值": 0.8533} |
| P95TTFT容差 | {"旧P95_s": 4.017, "新P95_s": 4.52, "阈值说明": "旧路径实测 P95 + 10%；阈值裁定属用户/编排者，本探针只报数"} |

## 已知口径与偏差（批判性审查输入）

1. eval_set32 来源=R20-min 冻结产物 rag_eval_set32.json（n_cases=32, seed=20260914, recall_topk=150, built_at=2026-09-14T11:17），本探针全量取其 32 条 query（未用历史 task32_eval_set.json 切片）。
2. chat 采样确定性=「SQL 相对序（created_at DESC LIMIT 120）+ 种子内洗牌 + 会话配额」——新插入数据不改已选集，仅 eligible_total 漂移；SQL/参数/seed 逐字存 dualrun_samples.json。
3. 新路径 docs 由 r20b_hook 进程内 spy 捕获（run_agent 返回体 docs 恒空，P1-5）；旧路径绑定原函数不受影响（隔离断言写入 summary.hooks）。
4. 新路径 tool/learning 意图走子代理编排（KNOWLEDGE_DIRECT_RETRIEVAL 仅覆盖 knowledge），检索参数与旧路径「统一 top_k=12」结构性不同——该差异属 P2-23 分歧面，如实计入指标，不做归一化。
5. 新路径检索硬编码 use_hyde=False（sixnode.fan_out），旧路径按生产默认 True——查询改写差异计入 docs 分歧；逐样本检索 query 见 results 的 new_retrieval_queries / old_query_rewrite。
6. TTFT 代理口径：两路径事件源不同（旧=决策完成→检索完成；新=start→hook 首检索完成），近似对比；chitchat 直连样本双方均无检索（None 不计入）。
7. 答案语义对比中，旧路径答案=generate_answer 真实生成（fast，temp=0），新路径答案=同轮 run_agent 的 final_answer；两者 prompt 结构/上下文天然不同，judge 结果仅供人读。

## 复跑命令

```bash
cd edu-agent
.venv/Scripts/python.exe scripts/eval/r20b_dualrun_probe.py            # 全量 100
.venv/Scripts/python.exe scripts/eval/r20b_dualrun_probe.py --limit 5  # 冒烟
```

产物: scripts/eval/dualrun_samples.json / dualrun_results.json / dualrun-summary.json / 本报告
