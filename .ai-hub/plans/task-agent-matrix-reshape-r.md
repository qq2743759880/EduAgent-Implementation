# task-agent-matrix: reshape-r 调度矩阵 v1.0

> 任务→执行链→并行波次映射。(历史 task-agent-matrix.md 为优化期 v1.3,保留不覆盖。)平台=ZCode Agent 独立子 agent(C-01 派单,编排者逐断言复现);文件所有权互斥=并行判据;契约冻结=开工判据。

## 一、任务×执行链×依赖总表

| 任务 | 链 | 前置依赖 | 契约前置 | 文件所有权(互斥域) | 波次 |
|---|---|---|---|---|---|
| R01 记忆 worker | T2 | — | — | app/main.py + app/ai/memory/ | W1 |
| R02 流式进图 | T3 | — | C-R-SSE(已冻结复用) | app/chat/service+router + graph 适配层 | W1 |
| R03 chunk 唯一化 | T3+T1 | — | **C-R-CHUNK 冻结** | app/knowledge/importer(parser/loader)+迁移脚本 | W1 |
| R04 MCP 调用修复 | T3 | — | C-R-ACI 草案 | app/chat/flows/agent.py + app/mcp/registry.py + 契约测试 | W1 |
| R06 md5 重排修复 | T3 | — | — | retriever.py _rule_rerank 段 | W1 |
| R07 伪向量+IDOR | T2/T3 | — | — | knowledge/routers/upload.py + embedder 兜底段 | W1 |
| R05 死代码清除 | T2/T3 | R02+R04 验收 | — | 仅删除:task95 模块/langgraph_agent.py/execute_tool_plan | W2 |
| R10 状态通道 | T3 | R02 | — | app/ai/graph.py 状态段 | W2 |
| R12 LLM 工具决策 | T3 | R04 | — | flows/agent.py 决策段 + config 默认值 | W2 |
| R14 search_knowledge 统一 | T3 | R04 | — | mcp/executor 内置工具段 + graph.py:425 段 | W2 |
| R11 HITL interrupt | T3 | R02+R10 | **C-R-HITL 冻结** | graph 工具节点 + chat router | W3 |
| R11-F 确认卡前端 | T4 | R11 契约 | 同上 | chat.html(增量 diff gate) | W3 |
| R13 停止条件 | T3 | R10 | — | graph 编排段 | W3 |
| R15 权限门+ACI | T3 | R04 | **C-R-ACI 冻结** | executor 调用前置门 + 错误信封模块 | W3 |
| R20 指标评估器 | T3 | R03 | **C-R-EVAL 冻结** | scripts/eval/ + rag_evaluator 接线 | W3 |
| R21 faithfulness | T3 | R20 | 同上 | scripts/eval/ | W4 |
| R22 评估进 CI | T5 | R20+R21 | 同上 | pytest 标记 + 门禁脚本 | W4 |
| R23 三因子+真 HyDE | T3 | R20 | — | retriever/retriever.py + Milvus schema 探查 | W4 |
| R24 trace JSONL | T5 | R02 | — | trace 模块 + logs 轮转 | W4 |

## 二、并行波次图

```
W1(6 并行,文件互斥): R01 | R02 | R03 | R04 | R06 | R07
W2: R05(待R02+R04) | R10(待R02) | R12(待R04) | R14(待R04)
W3: R11+R11-F(待R02+R10,契约C-R-HITL) | R13(待R10) | R15(待R04,契约C-R-ACI) | R20(待R03,契约C-R-EVAL)
W4: R21→R22(待R20) | R23(待R20) | R24(待R02)
契约闸: C-R-CHUNK→R03 | C-R-ACI→R15(R04 凭草案开工) | C-R-HITL→R11 | C-R-EVAL→R20
```

## 三、调度规则(TT §5.1 依赖二值化)
- **契约依赖**(消费冻结契约即可开工):R02 消费既有 SSE 冻结;R04 凭 ACI 草案。
- **完成依赖**(严格等验收 DONE):R05←R02+R04;R10/R11/R13/R24←R02;R12/R14/R15←R04;R20←R03;R21/R22/R23←R20。
- **互斥判据**:W1 六任务文件所有权零交集(上表第 5 列),满并行派单;同波禁双 agent 触碰同文件。
- 每任务=独立 commit+完工报告;编排者逐断言复现(测试/真实请求/git log)后解锁下游;平台失败按登记表纪律,连续 3 败按 N=1 降级并标"待独立复审"。

## 四、风险热点与护栏
| 热点 | 护栏 |
|---|---|
| R02 动用户唯一聊天入口 | SSE 契约冻结+task104 回归+STREAM_VIA_GRAPH 一键回退;旧路径 R05 之后才删 |
| R03 存量 2631 行迁移 | dry-run 强制先行;向量原地仅重建 PK/scalar;回滚=新旧 ID 共存窗口 |
| W1 满 6 并行遇平台限流 | 按 R02>R03>R04>R01>R07>R06 优先级串行化 |
| R11 HITL 打断体验 | 仅写类/外发类触发+会话级免确认记忆(Design 自审已定) |
