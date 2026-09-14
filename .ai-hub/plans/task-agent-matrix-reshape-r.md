# task-agent-matrix: reshape-r 调度矩阵 v1.1(终审批判承接版)

> v1.0→v1.1:W0 测量仪前置/R02 移出 W1 单独成波+双跑灰度门/R05 收敛前置/R23 降级实验/新增 R01-b/R02-c/R02-d/R04-b/R08。(历史 task-agent-matrix.md 优化期 v1.3 保留。)

## 一、任务×链×依赖总表

| 任务 | 链 | 前置依赖 | 契约前置 | 文件所有权 | 波次 |
|---|---|---|---|---|---|
| R20-min 基线 | T3 | — | **C-R-EVAL 冻结** | scripts/eval/+contracts | **W0** |
| R20-b 双跑探针 | T3 | — | — | 打点 hook+scripts/eval | **W0** |
| R01(+b) 记忆通电+输入侧 | T2 | — | — | main.py+ai/memory/ | W1 |
| R04(+b) 调用修复+脱敏 | T3 | — | C-R-ACI 草案 | flows/agent.py+mcp/registry+契约测试 | W1 |
| R06 md5 / R07 伪向量+IDOR | T3 | — | — | retriever 段 / upload.py+embedder 段 | W1 |
| R08 skill 路径可移植 | T2 | — | — | ai/skills/registry.py | W1 |
| R03 chunk 唯一化+迁移 | T3+T1 | **W0 基线冻结** | **C-R-CHUNK** | knowledge/importer+迁移脚本 | W1(尾) |
| R02(+c/d) 流式进图+thread_id+TTFT | T3 | W0 探针+R01/R04 验收 | C-R-SSE 复用 | chat/service+router+graph 适配 | **W2 单波** |
| R02-b 灰度双跑 | T3 | R02 | 同上 | 旁路模块+灰度报告 | W2 起,收敛门 |
| R05 删旧路径 | T2/T3 | **灰度收敛<5%** | — | 仅删除 | W3 |
| R10 通道 / R11(+F) HITL / R13 停止 | T3(+T4) | R02 / R02+R10 / R10 | C-R-HITL | graph 各段+chat.html | W3 |
| R12 决策接管+超时预算 | T3 | R04 | — | flows 决策段+config | W3 |
| R15 权限门+ACI(五层防御) | T3 | R04 | C-R-ACI 冻结 | executor 前置门+信封模块 | W3 |
| R21/R22/R24 | T3/T5 | R20 系 | C-R-EVAL | scripts/eval+CI+trace | W4 |
| R23 三因子+真 HyDE(实验) | T3 | R20 基线 | — | retriever+schema 探查 | W4(实验) |

## 二、波次图

```
W0: R20-min | R20-b  (与 W1 互不依赖可同发,但 R02/R03 的解锁闸在 W0)
W1: R01 | R04 | R06 | R07 | R08 | R03(尾,前置=基线)
W2: R02(+c thread_id/d TTFT) → R02-b 灰度(收敛门:intent/docs/答案 三指标<5%,持续至达标)
W3: R05(收敛后) | R10 | R11+F | R13 | R12(超时预算) | R15(五层防御)
W4: R21→R22 | R24 | R23(A/B 实验,无收益不默认开)
```

## 三、调度规则
- 契约依赖:R20-min 消费 C-R-EVAL(本波冻结);R02 消费 SSE 冻结;R04 凭 ACI 草案。
- 完成依赖:R03←W0 基线;R02←W0 探针+R01+R04;R05←**灰度收敛**(非 R02 验收);R21/22/23←R20;R24←R02。
- W1 六任务+R03 文件互斥(见所有权列);W2 严禁并行其他任务(R02 触碰面最大)。
- 每任务派单前置=独立详档 tasks/taskRxx-*.md 存在(TT §3);平台连续 3 败按 N=1 降级+待复审标记。

## 四、风险热点与护栏
| 热点 | 护栏 |
|---|---|
| W0 测量仪自身失灵 | 灵敏度反证实验(改坏 nprobe 必须看到指标下降)入 GWT |
| R02-b 旁路双倍 LLM 配额 | 旁路只跑到 intent+docs 层,答案抽检 10%;配额护栏入灰度配置 |
| R03 锁定窗口业务停写 | 窗口分钟级+提前公告;上传 API 返回明确"维护窗口"错误码(参数绑定校验) |
| R02 TTFT 劣化 | 阈值=旧路径实测 P50/P95+10% 容差,超阈值先优化图内快路径再灰度 |
| dynamic field 过滤性能 | W1 探查步含性能基准(对 R20 基线),不达标升级重建评估 |
