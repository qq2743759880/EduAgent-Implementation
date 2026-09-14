# taskR20min:评估基线冻结(W0,一切检索改动的测量仪)v1.1

> 派单平台:执行 agent(用户转交)。必读:dev-plan-reshape-r.md v1.1 W0 节/scripts/eval/build_eval_set32.py(全文)/app/chat/rag_evaluator.py。具名资产口径:[F-C07-001] LlamaIndex(HitRate/MRR 定义)。
> v1.1 修正(终审 A2+编排者核实):**eval_set32.json 不存在**(生成器从未产出落盘,2026-09-13 实证)——首步=跑生成器;golden=题目 chunk 自身 chunk_id(脚本 :8 设计,自动生成,无需手工标注,但需逐条抽检合理性)。

## 步骤
0. **环境自证(首步,失败即停)**:`from app.knowledge.importer.loader import get_milvus_client; get_milvus_client().list_collections()` 不通→直接报错退出,不闷头跑。
1. **golden 产出(钉死口径)**:`build_eval_set32.py --limit 32`(**W0 冻结=32 条**,历史名 task32 但默认 80 禁用)——该脚本仅产出 **query+golden(chunk_id+content 哈希) 映射**,其冻结 candidates 段**不用于算指标**。
2. **指标=实时端到端检索**(终审问题 1 承接):每条 query 走 retriever.py 完整链路(召回 150→rerank 20→断崖截断 5),判定 GT 是否在最终 top5——**禁止在冻结 candidates 上算 hit_rate/mrr**(那漏掉召回层与截断层,数字虚高)。
2. **ID 稳定性设计(新洞承接)**:基线 JSON 的 golden 同时存 chunk_id 与 doc_sha256 双键——**R03 迁移后 chunk_id 变更时,评估 harness 优先按 sha256 解析目标块**(迁移脚本须输出 old→new id_map 落盘,见 C-R-CHUNK),杜绝"迁移后基线全量假阴性"。
3. **指标**:hit_rate/mrr(口径对齐 LlamaIndex),直连检索层(不经 LLM),top_k=5,固定 seed;输出 {ran_at, git_rev, params(RRF k/nprobe/top_k), per_query, hit_rate, mrr}。
4. **冻结**:contracts/rag-baseline-eval32.json;阈值 RAG_EVAL_HIT_RATE_MIN/MRR_MIN=基线-0.02;脚本 exit 1 逻辑实现但 W0 只冻结不拦截。
5. **灵敏度反证**:临时 nprobe=1 跑对照(验后还原),指标须可见下降——证明测量仪非摆设。

## 禁项
禁改检索代码;禁 DB 直写(只读参数绑定);禁 Playwright;确定性要求——凡涉及 LLM 的环节(无,本任务纯检索层)不适用;生成器如需 LLM 抽检辅助,temp=0。

## GWT(机验)
①eval_set32(32 条)产出且含双键 golden;②重跑两次指标一致;③nprobe=1 灵敏度实验指标下降;④基线+阈值文件入库;⑤指标判定基于实时端到端链路(retriever.py 全链),报告须附单条 query 的 层级trace(召回数→rerank后→截断后) 佐证。

## 交付
commit `feat(r)/R20min-eval-baseline`(基线 JSON+脚本修正+阈值配置+报告 test-reports/R20min-completion-report.md 含 5 条抽检对照与灵敏度输出)。
