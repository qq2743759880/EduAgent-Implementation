# 开工 Prompt：R20-b 新旧路径双跑探针（W0，执行 agent 用）

> 生成：2026-09-14 · 编排者派发（派发协议=用户转交本 prompt 给执行 agent）· 平台：任一具备 shell+python+LLM 配额的执行 agent

## 职责
你是开发执行 agent（T3 链：chat 双路径域），负责且仅负责 **R20-b 新旧路径双跑探针**（reshape-r W0）。产出是 R02 灰度收敛的量化基准（P2-23 双规则分歧的初值）。

## 必读文档（路径引用，开工前逐个实读）
- 任务详档（唯一需求源）：`E:\stu\project\stu\EduAgent实施手册\.ai-hub\plans\tasks\taskR20b-dualrun-probe.md`（v1.1）
- 波次计划：`.ai-hub\plans\dev-plan-reshape-r.md`（W0 节 + 终审五问闭环 A1 条）+ 调度矩阵
- 审计病灶（P2-23/P2-17 出处）：`.ai-hub\plans\audit-edu-chat-langgraph.md`
- 代码资产（实读）：`edu-agent\app\chat\flows\agent.py`（旧路径 run_agent_turn）、`edu-agent\app\ai\graph.py`（新六节点图 run_agent）、`edu-agent\scripts\eval\build_eval_set32.py`、`edu-agent\scripts\eval\data\`（eval 样本）
- 项目教训：`AGENTS.md`（教训 3：chat SSE 事件解析、教训 8：真实契约优先）

## 开工前批判承接核对（硬约束，完工报告必附输出）
```
node D:\.ai-hub\skills\tt\scripts\critique-backlog-next.mjs --task "双跑 R20 chat graph agent"
```
预期=承接判定 HIT_NONE（完工报告如实写"无承接项"并附命令输出）。勿用 `--task-doc` 全文模式（过度命中误报）。

## 第 0 步环境自证（失败即停上报，禁止伪造）
1. Milvus 通（同 R20-min 自证）；chat_message 表可只读查询
2. **LLM 配额可用**（DeepSeek 余额）：先 1 条真实 query 双跑冒烟，402/超限→立即停手上报
3. `git rev-parse HEAD` 记录进报告

## 当前任务（GWT 摘要，全量以详档为准）
- 100 样本构成钉死可复现：eval_set32 全量 32 + chat_message 真实 user query 50（role=user、content≥10 字、每会话≤3、按 created_at 倒序、固定 seed、SQL 记入报告）+ 边界构造 18（6 chitchat/6 工具意图/6 知识深查，逐条文本入报告）；全部落 `dualrun_samples.json` 含 source 三类标注
- **确定性强制**：decide_agent_plan/图内路由 LLM temp=0（monkeypatch 级配置注入，**不改正产代码**，单独 commit 可 revert）；同 query 自跑两轮先验自身稳定，不稳定项列表化处置——"分歧"必须是路径分歧不是采样噪声
- 双跑取中间层信号：intent/need_search/retrieved chunk_ids/检索计数；TTFT 代理=start→首检索完成间隔
- **门槛指标只取 intent/docs 两项**；答案语义 30% 抽样仅入报告不入门槛
- diff 报告落 `test-reports\dualrun-baseline.md` + JSON：intent 分歧率/need_search 分歧率/docs Jaccard 分布/TTFT P50 P95 对比
- 旁路双跑只跑到 intent+docs 层，不重复生成答案（配额护栏）；旁路异常静默计数不进主响应

## 硬性守则
1. 只做本任务，完工等验收，禁止连做 R20-min/R02
2. **禁改两条路径正产代码**；打点 hook+temp 注入单独 commit（可 revert）；禁动生产数据（chat 采样只读）；禁 Playwright
3. commit 拆分：①`feat(r)/R20b-temp0-injection`（确定性注入，可 revert）②`feat(r)/R20b-dualrun-probe`（样本/报告）
4. 越界发现写 `.ai-hub\handoffs\R20b-discrepancy.md` 上浮
5. 完工前自检：边界/错误反馈/可复现三视角；无发现写"自检无发现"

## 完工报告要求
- 写 `test-reports\R20b-completion-report.md`，只回传路径引用
- **必含段落**：①资产消费证据（实读文件+发现，无则"自检无发现"）②批判承接核对（附命令输出）③样本构成清单（source/SQL/seed/18 条边界逐条文本）④temp=0 自稳定预验结果与不稳定项处置 ⑤四指标+逐样本明细文件路径 ⑥灰度门槛建议值核对段（intent 分歧<5%/docs Jaccard>0.9/千条/连续 3 天——执行者只报告实测数字，**不得调阈值**）⑦git_rev+环境自证输出
- 机验锚点：`dualrun_samples.json` 含 100 条与 source 字段；报告含 "temp=0"、"intent 分歧率"、"Jaccard" 字样
