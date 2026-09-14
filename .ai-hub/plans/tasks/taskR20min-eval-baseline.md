# taskR20min:评估基线冻结(W0,一切检索改动的测量仪)

> 派单平台:ZCode Agent(独立子 agent)。必读:dev-plan-reshape-r.md v1.1 W0 节/audit-edu-rag-mcp.md/scripts/eval/ 现状/app/chat/rag_evaluator.py。具名资产:LlamaIndex metrics 口径([F-C07-001] 卡,HitRate metrics.py:29/MRR :96)。

## 目标
eval_set32 上建立 hit_rate/mrr 基线并冻结入仓库,作为 R02/R03/R23 一切对照的唯一机验基准(替代"手动对照")。

## 设计要点
1. 指标口径对齐 LlamaIndex:hit_rate=命中任一 golden doc 的 query 占比;mrr=首个命中位倒数平均。golden 集从 scripts/eval/build_eval_set32.py 现状核实,不足则补齐 query→期望 chunk 映射。
2. 跑法:直连检索层(不经 LLM,排除生成侧噪声),每 query top_k=5;输出 JSON:{ran_at, git_rev, params(RRF k/nprobe/top_k), per_query:[], hit_rate, mrr}。
3. 冻结:contracts/rag-baseline-eval32.json+阈值入 .env.example(RAG_EVAL_HIT_RATE_MIN/RAG_EVAL_MRR_MIN,初始=基线值-0.02 缓冲);脚本 exit 1 逻辑(低于阈值)实现但 W0 只冻结不拦截。
4. 禁项:禁改检索代码本身;禁 DB 直写(SQL 只读且参数绑定);禁 Playwright。

## GWT(机验)
- Given 当前代码与数据;When 跑脚本;Then 基线 JSON 落盘且含 git_rev;重跑两次指标一致(确定性,固定 seed)。
- Given 人为改坏 nprobe=1 的对照实验(临时,验完还原);Then 指标可见下降——证明测量仪有灵敏度(反证非摆设)。

## 完工报告
test-reports/R20min-completion-report.md:指标值/灵敏度实验输出/基线文件路径。
