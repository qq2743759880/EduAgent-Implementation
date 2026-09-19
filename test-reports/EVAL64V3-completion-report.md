# EVAL64V3 完工报告 —— W-NEXT-EVAL64V3-001（yy 并行流水线 C-01）

> 任务：V3=改写问句 query 面（承接 EVAL64V2 P0-①）。64 条 query 逐条 LLM 改写「同义不同形」，
> golden 不变，创造真实 headroom，让检索质量差异可测量。执行 agent：yy（2026-09-20）。
> 变更范围：`build_eval_set64.py` 增 rewritev3/buildv3（最小 diff）+ `data/r64v3_*` + 护栏单测 + 本报告。

## 0. 结论一句话

**V3 集（63 条，去自证 query 面）在现产线（V2 cliff on）上 hit@5=0.9841 / mrr@5=0.9683，
与 V2 尺 shared-63 口径逐位同水位——「子串代理税」假说在 hit@5 上被证伪**：改写后字面重叠
中位数只剩 27%，hit@5 一例未丢（丢的仍是 V2 本来就 miss 的同一条通用题干）。
V2 尺 0.9844 贴天花板不是子串保底造成的乐观，而是该语料+query 分布下检索能力的真实水位。
是否以 V3 冻结新契约，数字已备齐、裁定权交编排者（本任务未建 V3 契约文件）。

- 主提交：**ec48440**（eval(r64v3)/W-NEXT-EVAL64V3-001，7 files +7018；本报告 §9 后补记，基线 HEAD d73540a，测量窗口 HEAD 因并行 DATAHYG 前移至 ce377ab/f378f2e，见 §6.3）

## 1. 改写抽样（5 条人读，覆盖口语/正式/剔除/miss 案例）

| idx | 状态 | 风格 | v2_query（原） | v3_query（改写） | 改写理由（LLM 自述） |
|---|---|---|---|---|---|
| 0 | pass att=1 | 口语化 | 关于回归分析，下列说法正确的是： | 回归分析这块儿，下面哪种说法是对的？ | 换口语化句式与同义词，语义不变 |
| 11 | **violation 剔除** att=3 | 正式 | 什么是拓扑不变量？ | （未采纳） | 回炉 2 次后字面重叠仍 62.50%≥60%（G2）→ 剔除计数，不凑数 |
| 30 | pass att=2 | 口语化 | 哪些错误通常能在编译期尽早发现？ | 一般哪些毛病在编译的时候就能早点查出来？ | 同义替换，语义一致，句式口语化 |
| 41 | pass att=1 | 正式 | NoSQL 一定比关系型数据库更快。 | 关系型数据库的速度是否必然不及 NoSQL？ | 同义改写，否定断言转为疑问，语义完全一致 |
| 62 | pass att=1 | 口语化 | 核心骨干总是来问你怎么做，团队已经开始等你拍板。在这种情况下，最优先的做法是： | 团队里那些顶梁柱老跑来问你该咋办，大伙儿都等着你拿主意，这时候你首先该干的是啥？ | 同义替换骨干、拍板等词，调整语序，意图不变 |

改写模型：deepseek-flash（`model="strong"` 通道，非流式 `call_chat` 统一注入 thinking=disabled，
temperature=0.3）；风格按 idx 奇偶确定性轮换（口语/正式混合）；全程 0 密钥落盘（key 只在进程内 settings）。

## 2. 防退化护栏校验数字（任务②，逐条落账）

护栏实现：`check_rewrite_guardrails`（纯逻辑可单测）+ buildv3 复检 + Milvus 活体 golden 归属检查。

| 环节 | 数字 |
|---|---|
| 改写总量 | 64 条（V2 冻结集全量，idx 对齐） |
| 首改直过 | 56 条 |
| 回炉后过（≤2 次） | 7 条 |
| **回炉后仍违规 → 剔除** | **1 条**（idx 11「拓扑不变量」，G2 重叠 62.50%≥60%，att=3） |
| LLM 调用失败（重试穷尽） | 0 条 |
| **V3 集 final** | **63 条**（剔除不补位；90% 地板=58，63≥58 达标 `below_floor=false`） |
| 护栏① 双键 golden 归属 | 63/63 通过：golden/gt_content 与 V2 集逐位相同（构建时活体 Milvus sha 复核 0 漂移、0 缺块）；`_match_golden` 双键在测量期全部解析（62 hit + 1 miss=golden 不在 final docs，非解析失败，见 §4） |
| 护栏② 字面重叠 <60% | 通过的 63 条：min 5% / 中位 27% / 均值 29% / max 58%；≥50% 仅 5 条；v3==v2 全同 0 条 |
| 护栏③ LLM 自评相关 ≥4/5 | 通过的 63 条全部自评 5/5（1 条 json 解析失败回炉后通过；未出现 4 分以下） |
| 附加约束（任务书） | 长度 ±50%：全部合规（v3 len 13~84 vs v2 9~76）；禁新实体：prompt 硬约束 + 逐条 rationale 留痕 |
| 反向不变量 W3' | 「v3 query 仍是 golden 子串=假改写」0 条命中（63/63 脱离子串保底） |
| 单测 | `tests/test_build_eval_set64.py` 68/68 过（新增 V3 护栏 15 条：G1 归属不变 / G2 阈值边界 50% 过 60% 拒 / G3 相关度地板 / G4 长度 / W3' 假改写拒绝 / V2 双键 W 规则保留 / 解析容错） |

## 3. V3 基线测量（任务③，现产线，V2 cliff on）

口径：与 V2 冻结契约同链同参——`retrieve_three_channel` 实时全链（召回150→rerank20→断崖→top5），
`--mode measure --set scripts/eval/data/r64v3_eval_set64.json`，串行确定性，0-LLM。
产线实况：`RERANK_CLIFF_V2=True quant=0.6`（.env + retriever 日志 `[retrieval-profile] cliff-v2 quant=0.60 floor=0.463 kept=5/20` 逐条留痕）、EMBED_BACKEND=cuda、sidecar 8601 ok、`final_docs dist {5: 63}`。

| 指标 | run1 (r64v3_base_run1) | run2 (r64v3_base_run2) |
|---|---|---|
| n | 63 | 63 |
| **hit@5** | **0.9841**（62/63） | 0.9841（62/63） |
| **mrr@5** | **0.9683** | 0.9683 |
| hit@5 Wilson95 | [0.9154, 0.9972] | 同 |
| mrr@5 bootstrap95 | [0.9286, 1.0] | 同 |
| rank 分布 | rank1=60, rank2=2, miss=1 | 同 |
| 退化判别 | informative（mrr≠hit，有 rank2 命中——非圆环形态） | 同 |
| 逐位四元组指纹 (rank,hit,rr,final_docs) | — | **与 run1 逐位一致** |
| wall | 69.5s | 83.1s |

产物：`edu-agent/scripts/eval/data/r64v3_runs/r64v3_base_run{1,2}.json`（per_query 全量 + artifact store 双写 aid=6aaed1c2…/6aaed29d…）。
唯一 miss：idx 30（v2「简述该场景下的处理顺序。」→ v3「请概述此情形中的处置次序。」），
golden=`_default:482454bc109d453c:1`，`gt_resolve_via=miss`——**与 V2 run 的 miss 是同一条**
（V2 idx 31，同 golden），属指代残缺的通用题干（「该场景」无上下文），非改写敏感案例。

## 4. V2/V3 对照（任务③核心：子串代理税量化）

严格对照口径=**shared-63**（V3 剔除的 idx 11 两边都不计入；golden 逐位同、链路同参）：

| 口径 | V2 尺（query=源块子串保底） | V3 尺（改写面，中位重叠 27%） | 差 |
|---|---|---|---|
| shared-63 hit@5 | 62/63 = 0.9841 | 62/63 = 0.9841 | **0.0000** |
| shared-63 mrr@5 | 0.9405 | 0.9683 | +0.0278 |
| 全集 hit@5（集合不同，仅参考禁直接作差） | 63/64 = 0.9844（n=64） | 62/63 = 0.9841（n=63） | 分母/集合不同 |
| miss 条目 | 1（通用题干，golden 482454bc） | 1（**同一条**） | 换面不改 miss |

rank 迁移（V2 rank → V3 rank，shared-63）：(1→1)×57，(1→2)×1，(3→1)×2，(3→2)×1，(4→1)×1，(miss→miss)×1。

**子串代理税读数：hit@5 上 = 0。** 64 条 query 被改写到与原句字面重叠中位数只剩 27%（人工抽检语义不变），
检索 hit@5 一例未丢，且 miss 与 V2 完全是同一条。结论：V2 尺 0.9844 的贴天花板**不是** golden 取自
query 源块的子串保底造成的测量乐观——BGE-M3 dense+rerank 对「同义不同形」改写在这个语料上是鲁棒的，
0.98 的水位是真实能力而非代理假象。mrr 层面有 +0.028 的收紧（4 条 rank3/4 提到 rank1/2、1 条 rank1 退到 rank2），
但 n=63 下 ±1 条即在 Wilson 区间噪声内，**不构成「改写更好/更差」的因果声明**。
EVAL64V2 P0-① 的动机归因（子串保底→乐观天花板）由此被独立实证**部分证伪**：天花板真实，headroom 依旧只有那 1 条坏例。

## 5. 批判承接核对

| 上游批判 | 本轮承接动作 | 状态 |
|---|---|---|
| EVAL64V2 P0-①（V2 尺 0.9844 贴天花板、headroom 仅 1 miss，根因=golden 取自 query 源块子串保底） | V3 全任务即为此设计：改写 query 面破子串保底（护栏②<60% + W3' 反向不变量机械保证脱保底），golden/golden 双键冻结不动（G1 逐位继承），同链同参测量 + shared-63 严格对照 | ✅ 已实证：headroom 假说证伪，见 §4 |
| R22 Crit-3 / V2 遗产：贴天花板无法区分真回归与噪声 → 需有区分度分布 | V3 rank 分布出现 rank2（2 条）+ miss（1 条），degeneracy=informative；mrr 与 hit 脱钩 | ✅ 部分达成（headroom 仍薄） |
| AGENTS.md 教训②（禁 Playwright，独立实证须真 HTTP/真库） | 全程真 Milvus/真检索链/真 LLM API，无 mock，run 产物+日志留痕 | ✅ |
| AGENTS.md 教训③/⑧（真实契约优先、LLM 调用走脚本文件防 GBK） | 改写/护栏全部落 `build_eval_set64.py --mode rewritev3/buildv3` 脚本化，`-X utf8` + 文件重定向 | ✅ |

## 6. P0 自批判（≥3 条，如实）

### P0-1 核心假说被证伪=上游归因错误，本轮数字的用途必须重新定位
EVAL64V2 P0-① 把「贴天花板」归因为子串保底乐观；V3 以更狠的问法面（中位重叠 27%）证明天花板依旧。
这意味着 V3 集**不是**「去掉代理税后的真实质量」——它测出的是**改写鲁棒性**维度，与 V2 尺在 hit@5 上
同水位。若编排者把 V3 数字当作「更真实的基础命中率」去替代 V2 尺定阈值，是对本轮证据的误用；
两尺关系是「同水位、不同扰动维度」，禁互相换算（延续 V2 报告对两尺禁换算的裁定语义）。

### P0-2 改写质量依赖 LLM 自评，无独立裁判
护栏③的 relevance 是改写者自评（同一模型给自己打分），63 条全 5 分的自评分布本身可疑（无区分度，
等于没拦住任何语义漂移）。语义保真实际只由「prompt 约束 + rationale 人读抽样 5 条 + 检索行为不改 miss」
间接背书。若后续要把 V3 升级为冻结尺，应补一轮独立 judge（换模型或换 prompt 角色二评），
否则「同义」这一前提只有弱证据。

### P0-3 字面重叠（字符 bigram 保留率）是「真改写」的代理，存在双向盲区
bigram 重叠<60% 可放行「换汤不换药」的内容词复用（如 idx 0 保留「回归分析」——这是领域词，
保留反而合理）；也可误伤合法保留的短术语query。该指标只保证「形变了」，不保证「义不变」也不保证
「变得够干净」，与 P0-2 叠加后，改写面的语义等价性证据链是本轮最薄弱环节。

### P0-4 测量窗口与并行 Milvus 清理、VM 断电重启重叠，环境不是 V2 冻结时的环境
测量期间并行 DATAHYG 批次（e661f05）删除了 `_default` 分区 10 条跨分区冗余副本，且 Milvus VM 经历
挂起 panic→冷启动（§6.3）。对本轮数字的 bound：run1==run2 四元组逐位一致 + buildv3 活体 golden
sha 复核 63/63 通过 + DATAHYG 自证 golden 同参逐 rank 同 → **对本 63 条测量零影响**；但
「V2 0.9844 vs V3 0.9841」的跨尺对照隐含了环境漂移（commit 代际 + 语料微清理），严格归因需编排者
知晓此混淆。此外 milvus 数据层在两次 run 之间若再变动，逐位一致即失效——双跑窗口仅隔 ~90s，该证据强度有限。

### P0-5 n=63 的统计功效不足，mrr +0.028 不能读作改进
rank 迁移里 4 升 1 降，mrr 差异由 5 条 case 贡献；bootstrap95 [0.9286,1.0] 与 V2 的区间大面积重叠。
任何基于本轮 mrr 差值的决策（如「改写预处理上线」）都不被本轮证据支持。

### P0-6（次要） Miss 案例的 golden 指代残缺是集内已知坏例
idx 30 query「简述该场景下的处理顺序。」缺场景上下文，任何改写都无法修复指代缺失（改写后依旧 miss，
两代尺一致验证）。该条继续留在集内会长期贡献 1 条结构性 miss（-0.0159 hit@5），建议后续变更单裁定
剔除或补上下文，本轮不动集外契约。

## 7. 资产消费证据

| 资产 | 消费方式 |
|---|---|
| `edu-agent/scripts/eval/data/r64v2_eval_set64.json` | V3 集唯一输入：64 条 query 面 + golden/gt_content/provenance 逐位继承（G1 校验 `golden/gt not bit-identical: 0`） |
| `edu-agent/scripts/eval/build_eval_set64.py` | 原地增量：buildv2/measure/freezev2 行为零改动（V1 缺省路径回归单测 53 条全绿）；新增 rewritev3/buildv3 两模式 + measure 的 `--set` 按 `r64v3*` 前缀路由 r64v3_runs/（V1/V2 路由不变） |
| `edu-agent/scripts/eval/data/r24_runs/r24_r12_semantic_judge.json` | LLM 调用范式参照：model=strong（deepseek-flash）走 `_ChatClient.call_chat` 非流式（自动 thinking=disabled）+ 检查点落盘 + 失败计数不阻塞，本轮同范式复用 |
| `scripts/eval/r20min_run._match_golden` | 测量期双键解析（chunk_id/id_map/doc_sha256）只读复用，1 条 miss 的 `gt_resolve_via=miss` 语义即来自它 |
| `contracts/rag-baseline-eval64-v2.json` | 只读对照（0.9844/0.9414 与 PARAMS 同参核对）；**未触碰**，V3 契约按红线未建 |
| AGENTS.md | 教训②③⑥⑧消费（真库实证/脚本文件 LLM/DEBUG 状态已知/G BK 规避）；`.env` 密钥零落盘 |

## 8. 红线自检

- ✅ 只改 `build_eval_set64.py`（增模式，无既有行为变更）+ 新增 `data/r64v3_*` + `tests/test_build_eval_set64.py` 追加 + 本报告
- ✅ 未碰 V2 既有模式行为（53 条 V1/V2 回归单测全绿）、retriever/app/**、contracts/ 冻结文件、kg_bridge、trade/**
- ✅ lock `edu-agent/scripts/eval/reval64v3.lock` 已于 commit 前删除
- ✅ LLM 调用脱敏：记录/日志/报告零密钥；失败重试≤2 后标 failed（本轮 0 条 failed）

## 9. 环境事件登记（测量窗口，如实）

1. **Milvus VM（192.168.85.101，VMware NAT）开工时完全失联**（ICMP/全端口超时、无 ARP、Tools 请求挂起）。
   恢复过程：soft suspend 挂起卡死（guest 内部 thrash，vmem 8GB→11.7GB）→ hard suspend 成功 → resume 后
   网卡仍死（恢复态续病）→ **最终以 stop hard + 冷启动恢复**（约 01:53 断电，03 分钟后 Milvus 端口 OPEN，
   gRPC READY 再等 3 分钟）。并行 DATAHYG 批次报告独立记录了同一事件（「挂起panic/冷启动」），互证一致。
2. 测量 run1（02:16）/run2（02:19）之间并行批次 commit 前移（ce377ab→f378f2e，含 e661f05 的
   `_default` 10 条冗余副本清理）。对本轮零影响的 bound 证据：双跑逐位一致 + buildv3 活体 golden 复核
   63/63 + DATAHYG 自证 golden 同参 5/5 逐 rank 同（§6.4）。
3. Docker 容器、MySQL（localhost）、rerank sidecar（127.0.0.1:8601）全程未受影响。

## 10. 移交与待裁

- **冻结裁定**：V3 双跑数字已备（确定性逐位一致），是否建 `contracts/rag-baseline-eval64-v3.json`、
  阈值规则（基线-0.02 是否适配 n=63）、V3 尺与 V2 尺的并行/替代关系——编排者裁定（红线约定 V3 契约本轮不建）。
- 若采纳 V3 为尺：先补 P0-2 独立 judge 二评 + P0-6 miss 案例处置变更单。
- 本轮改写记录（`r64v3_rewrite_records.json`）含全部 64 条原始记录（含 1 条剔除证据），可复跑可审计；
  复跑 rewritev3 会复用已有记录（断点续跑设计），如需全新改写面请先归档该文件。
