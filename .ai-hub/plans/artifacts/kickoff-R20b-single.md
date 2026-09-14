# kickoff: R20-b 双跑探针·单写者重跑(第 2 次派发)

> 你是 EduAgent 重构批次的执行工程师,**唯一在册执行者**(前一执行会话因并行碰撞已被停止,其污染产物已隔离;你开工前无须也不会有任何同行写者)。
> 工作区:E:\stu\project\stu\EduAgent实施手册

## 硬性守则(逐条遵守)
1. **单写者锁**:开工第一动作=创建 `edu-agent/scripts/eval/r20b.lock`(内容=你的会话标识+时间);完工后删除。发现锁已存在→立即停止并上报,不得继续。
2. 禁 DB 直写;冻结契约禁改;禁 Playwright;禁重启在跑服务(8000/3000 在跑)。
3. 禁改两条被测路径正产代码;打点/temp 注入只进独立文件 `r20b_temp0.py`(已存在,**沿用勿重写**),单独 commit 可 revert。
4. 真实密钥零入库。

## 与上一次竞态的区别(你必须知道的现场)
- 上次两执行者并发共写 `dualrun_results.json`/`dualrun-summary.json` → **这两份已隔离到 .ai-hub/quarantine/r20b-race-20260913/(污染,禁引用)**。
- `dualrun_samples.json`(100 条,来源分布 32/50/6/6/6)已经编排者核验**有效,直接复用,禁重新生成**。
- temp=0 注入模块 `r20b_temp0.py` 已存在(上个会话 f045416 已提交),沿用。

## 任务(与 kickoff-R20b-W0.md 同口径,差异仅上述现场条款)
1. 样本 100 条(dualrun_samples.json,已验:32 eval_set+50 chat_history+6/6/6 边界)。
2. 双跑:同 query 走 run_agent_turn(flows/agent.py:218)与 run_agent(graph.py:775,thread_id 用独立值勿共享),取中间层信号 intent/need_search/retrieved chunk_ids/检索计数;TTFT 代理=start→首检索完成间隔,P50/P95。
3. **已知事实(前次竞态跑的教训,务必规避)**:两路径的检索参数不同(旧路 use_hyde=True/top_k=12 vs 新图 use_hyde=False/top_k=8)且新图存在 docs=[] 硬编码(r20b_hook.py 有 spy 可证)——这些是**要测量的差异本身**,不是你要修的 bug;禁修任何正产代码。
4. 门槛只取 intent/docs 两项(答案语义 30% 抽样仅入报告);temp=0 已强制(上会话 f045416)。
5. 输出:`dualrun_results.json`(逐样本)+`dualrun-baseline.md`(P50/P95+intent 分歧率+docs Jaccard+五条件对照数字)+`dualrun-summary.json`。
6. 单 commit `feat(r)/R20b-dualrun-single`;报告 test-reports/R20b-single-completion-report.md(含:锁机制说明/与污染隔离声明/逐样本明细)。

## 交付
锁创建→100 样本双跑→三产物→锁删除→commit。完工输出:intent 分歧率/docs Jaccard/TTFT P50+P95 三组数字+commit hash+报告路径。报告将交编排者独立复验(含批判性审查),不采信自述。
