# TO-EXEC-EVALFREEZE-B1 — idx31 组命中放宽变更单 + V3 尺契约冻结（用户 2026-09-20 已批）

## 背景（自包含）

RAG 评测双尺体系：V2 内容块尺（contracts/rag-baseline-eval64-v2.json，hit@5=0.9844/mrr=0.9414，已冻结）与 V3 改写面尺（评测集已建、双跑已跑、契约未冻结）。唯一 miss=评测集第 31 行（idx31，泛化题干），用户已批准两件事：①对 idx31 做「组命中」放宽的变更单+实施 ②把 V3 尺契约冻结落库。双跑数字已备齐。

## 项目锚点（开工前实读，一切以代码为准）

- 仓库 `E:\stu\project\stu\EduAgent实施手册`，分支 `feature/opt-waves`（前后对账）
- 评测域代码：`edu-agent/scripts/eval/`；建集器 `build_eval_set64.py`；冻结器先例 `r23_freeze_eval64.py`（V2 契约即由同型流程产出）
- 评测集：`edu-agent/scripts/eval/data/r64v3_eval_set64.json`（64 条，idx31=第 31 行，先读该行确认 golden 形态）；改写记录 `r64v3_rewrite_records.json`
- V3 双跑产物：`edu-agent/scripts/eval/data/r64v3_runs/r64v3_base_run1.json` 与 `r64v3_base_run2.json`（冻结基线取双跑，指纹一致性要断言）
- V2 契约（格式模板+双尺并行先例）：`contracts/rag-baseline-eval64-v2.json`（含 ruler_note 禁换算条款——V3 契约须同款条款）
- 权威 tracker 条目（背景与预估数字出处）：`.opencode/plans/critique-backlog-tracker.md` 末尾「EVAL64V3 + T13 销项登记」段：idx31 放宽预估内容块尺 hit→1.0 / mrr→0.9594

## 工作包 A：idx31 组命中放宽

1. 实读 idx31 行 + 现行打分逻辑（找到 hit/mrr 计算处，grep `hit` 于 scripts/eval/ 相关脚本）
2. 写变更单 `contracts/CO-IDX31-GROUPHIT-001.md`：动机（idx31 泛化题干 golden 形态）、放宽语义定义（**组命中=该题 golden 组内任一成员进 top5 即记 hit**，mrr 取组内最好排名）、影响面（仅 idx31 一条，预估 hit 0.9844→1.0 / mrr 0.9414→0.9594）、不可回溯毒性检查（放宽不得波及其余 63 条——必须给出 63 条分数逐位不变的证明）
3. 实施：打分逻辑加组命中支持（配置化，仅对标记 group 的 golden 生效，默认不影响旧尺 V1/V2 复算）
4. 实跑证明：放宽后 V2 口径全量复跑一次 → 64/64 hit、mrr≈0.9594（与预估偏差>0.005 要解释）；其余 63 条逐位不变 diff 证明

## 工作包 B：V3 尺契约冻结

仿 r23_freeze_eval64.py 与 v2 契约格式，建 `contracts/rag-baseline-eval64-v3.json`：

- baseline 取双跑（run1/run2 逐位一致才可冻结；不一致停手上报）
- thresholds：回归下限=基线-0.02；ruler_note 三尺并行禁换算条款（V1 路由卡 0.0781 / V2 内容块 / V3 改写面）
- idx31 条目：登记组命中放宽的适用与版本（V3 尺是否含放宽要**显式二选一**并在 ruler_note 写明；推荐 V3 冻结含放宽=终版形态，A/B 两包同一 commit 前后衔接）
- `draft: false`（用户已批冻结）

## 铁律

禁 DB 直写；不 push；单 commit：`feat(eval)/EVALFREEZE-B1: idx31 组命中放宽变更单+实施 + V3 尺契约冻结 (用户已批)`；报告写 `.ai-hub/plans/artifacts/dispatch/REPORT-EVALFREEZE-B1.md`（断言逐条附可复现命令；含资产消费证据/批判承接两段；批判承接=无重叠写「无承接项」）。若发现双跑不一致或 golden 形态与背景描述不符，**停手上报**，勿强行冻结。
