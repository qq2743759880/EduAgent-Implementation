# 开工 Prompt：R20-min 评估基线冻结（W0 测量仪，执行 agent 用）

> 生成：2026-09-14 · 编排者派发（派发协议=用户转交本 prompt 给执行 agent）· 平台：任一具备 shell+python 的执行 agent

## 职责
你是开发执行 agent（T3 链：数据/检索域），负责且仅负责 **R20-min 评估基线冻结**（reshape-r W0 波次）。这是后续 R03/R02/R23 一切检索改动的唯一对照测量仪。

## 必读文档（路径引用，开工前逐个实读，禁止凭印象）
- 任务详档（唯一需求源）：`E:\stu\project\stu\EduAgent实施手册\.ai-hub\plans\tasks\taskR20min-eval-baseline.md`（v1.2）
- 波次计划：`.ai-hub\plans\dev-plan-reshape-r.md`（W0 节）+ 调度矩阵 `.ai-hub\plans\task-agent-matrix-reshape-r.md`
- 契约草案（本任务负责将其冻结）：`contracts\reshape-r-eval-draft.json`
- 代码资产（实读全文）：`edu-agent\scripts\eval\build_eval_set32.py`、`edu-agent\app\chat\rag_evaluator.py`、`edu-agent\app\chat\retriever.py`（检索全链所在）、`edu-agent\app\knowledge\importer\loader.py`
- 项目教训：`AGENTS.md`（关键教训 7：查询/入库 embedding 必须同为 BGE-M3，EMBED_BACKEND=cuda）

## 开工前批判承接核对（硬约束，完工报告必附输出）
```
node D:\.ai-hub\skills\tt\scripts\critique-backlog-next.mjs --task "评估基线 R20 检索指标"
```
预期=承接判定 HIT_NONE（无承接项，完工报告「批判承接核对」段如实写"无承接项"并附命令输出）。
注意：勿用 `--task-doc` 全文模式（对叙述型落点会过度命中，误报 C-16..C-24 承接——以精确关键词判定为准）。

## 第 0 步环境自证（失败即停并上报，禁止闷头跑/禁止伪造数据）
1. Milvus：`from app.knowledge.importer.loader import get_milvus_client; get_milvus_client().list_collections()` 通（在 `edu-agent\` 下用 `.venv\Scripts\python.exe`）
2. Embedding 后端=EMBED_BACKEND=cuda 生效（BGE-M3 本地可用；查询 embedding 与库内同为 BGE-M3）
3. `git rev-parse HEAD` 记录基线 git_rev（写入报告）
LLM 配额：本任务纯检索层不经 LLM；若任何步骤需要 LLM 且遇 402/配额不足→立即停手上报，禁止伪造输出。

## 当前任务（GWT 摘要，全量以详档为准）
- 32 条 eval set（`--limit 32`，历史默认 80 禁用），golden=题目 chunk 自身 chunk_id，**双键落盘（chunk_id+doc_sha256）**
- 指标=**实时端到端检索链**（召回 150→rerank 20→断崖截断 5）判定 GT 是否进 top5；**禁止在冻结 candidates 上算指标**
- 输出 hit_rate/mrr（口径对齐 LlamaIndex）+params+per_query+层级 trace 佐证（单 query：召回数→rerank 后→截断后）
- 冻结 `contracts\rag-baseline-eval32.json`；阈值 RAG_EVAL_HIT_RATE_MIN/MRR_MIN=基线-0.02 入配置；脚本 exit 1 逻辑实现但本波只冻结不拦截
- 灵敏度反证：临时 nprobe=1 跑对照（验后还原），指标须可见下降
- 确定性：同配置重跑两次指标一致；固定 seed

## 硬性守则
1. 只做本任务，完工后等验收指令，禁止跳序/连做 R20-b 或其他任务
2. **禁改检索正产代码**（retriever.py/rag_evaluator.py 等只读）；禁 DB 直写（只读+参数绑定）；禁 Playwright
3. 单一 commit：`feat(r)/R20min-eval-baseline`（基线 JSON+脚本调用层+阈值配置+报告）；不 push，不碰他人文件
4. 越界发现写 `.ai-hub\handoffs\R20min-discrepancy.md` 上浮，不自行跨域修
5. 完工前自检：按边界/错误反馈/可复现三视角过一遍自己的脚本与报告；无发现写"自检无发现"

## 完工报告要求
- 写 `test-reports\R20min-completion-report.md`（仓库根 test-reports\），只回传路径引用不贴全文
- **必含段落**：①资产消费证据（实读了上列哪些资产文件+各自发现，无发现写"自检无发现"）②批判承接核对（附上方命令输出）③5 条 golden 抽检对照（query→golden chunk 内容合理性人读判定）④灵敏度实验原始数字 ⑤两次重跑一致性数字 ⑥git_rev+环境自证输出
- 机验锚点：`contracts\rag-baseline-eval32.json` 存在且含双键 golden 字段；报告含"实时端到端"字样及 trace 表
