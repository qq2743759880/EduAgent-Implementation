# W-NEXT-MILVUSFLUSH-001 完工报告（C-01 独立实证）

> 任务 ID：W-NEXT-MILVUSFLUSH-001（yy 串行流水线唯一在岗 agent）
> 派单：C-01 编排者（逐断言独立实证验收）
> 完工日期：2026-09-19
> 本批 commit：**`1845744`**（probe/data，`18457444f19d9ae6b9f8fed0c84513de1f671b28`）+ 报告独立 commit（见文首引用）
> lock：`edu-agent/scripts/eval/wnextmilvusflush1.lock` 已于 commit 前 rm+ls 复核删除
> **红线自检：全程仅 describe / list_partitions / get_collection_stats / get_partition_stats / query / get / list_persistent_segments / list_loaded_segments（纯 SELECT/query 语义）；零 flush、零 compaction、零 load/release、零 insert/delete/upsert；未触 app/**、contracts/**、tests/**（探针为 scripts/eval 纯新增只读断言）。**

---

## 一、结论一句话

**3398−3388=10 行差异定性为「同 PK 跨分区双副本」的 Milvus 正常语义差**（10 个 id 每个在 `_default` 与 `user_1` 各存 1 份活副本，整表 query 按 PK reduce 去重只返回 1 份，count(*) 数物理副本，flush 不消除——因为根本没有未 flush 数据）；stats=3399 的 +1 是 `_default` 另有 1 条已删行待 compaction。**非真实数据问题，不报变更单，建议 guard 措辞校准**（§六）。⑪⑲ 瞬态红属**探针运行环境时序**（崩溃/硬杀恢复窗），非数据态写入窗口（§五）。

## 二、两种原语对拍数字（探针 3 轮，2026-09-19 09:2x，Milvus pkg/v2.5.5 @192.168.85.101）

| 口径（原语） | 第 1 轮 | 第 2 轮 | 第 3 轮 | 说明 |
| --- | --- | --- | --- | --- |
| `query(id>=0, limit=16384)` 枚举行数 | 3388 | 3388 | 3388 | R-M2 登记的 query 口径 |
| `query(output_fields=["count(*)"])` | 3398 | 3398 | 3398 | R-M2 登记的 count(*) 口径 |
| `get_collection_stats().row_count` | 3399 | 3399 | 3399 | 第三口径（stats 比 count(*) 多 1） |
| `query(空 filter)` count(*) | 3398 | 3398 | 3398 | 与 `id>=0` 口径一致（排除负 PK 假设） |
| `query(..., ["id","chunk_id"])` 枚举 | 3388 | — | — | 字段 absent 过滤假设**排除** |
| Strong 一致性枚举 | 3388（sha 同 4ed85d1555af） | — | — | Bounded 快照滞后假设**排除** |
| offset 分页拼接（page=1000 走全表） | 3388，id 集与单页完全一致 | — | — | offset 跳行假设**排除**；⑪ 范式不跳行 |
| 分区 count(*) 之和 | 3398 | — | — | =整表 count（口径闭合） |
| 分区枚举之和 | **3398** | — | — | **>整表枚举 3388，+10 全部来自跨分区重复 PK** |
| 段级 persistent（state 求和） | 3399，全部 state=4(Flushed) | 同 | 同 | **无 Growing/Sealed 段，「未 flush 段」假设排除** |
| 段级 loaded（state 求和） | 3399，全部 state=3(Loaded) | 同 | 同 | 同上 |
| 3 轮枚举 id 集 sha256 前 12 位 | 4ed85d1555af（三轮逐位一致） | ← | ← | 并发写窗口假设**排除** |

退出码 1（INCONSISTENT，本批预期态）；产物 `data/wnextmilvusflush1_probe.json`。

## 三、10 行差异逐行定性表（二分定位 + 逐分区归属，count/query/get 三口径对拍）

二分下降 579 次 count 探针定位出 10 个差异 id；每个 id 的三元组 **(count(*)==id, query==id, get==id) = (2, 1, 1)**；逐分区对拍每个 id 在 `_default` 与 `user_1` 各有 1 份副本，**两副本 chunk_id / tenant_id / created_at（微秒级）/ source_file 完全相同**（同批数据写入两个分区，非 PK 碰撞、非软删、非字段 absent）：

| # | id (crc32 PK) | chunk_id（两分区副本同串） | _default 副本 | user_1 副本 | created_at（两副本同值） | source_file | 定性 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 19587845 | user_1:adb078bf3017153b:1 | 1 行 | 1 行 | 2026-09-16T16:06:25 | c56769527306.md | 跨分区双副本 |
| 2 | 145339617 | user_1:4de91c9271c8776e:1 | 1 | 1 | 2026-09-16T15:05:36 | fdc227fb0884.md | 跨分区双副本 |
| 3 | 279813836 | user_1:883a713149a5ffac:1 | 1 | 1 | 2026-09-16T15:05:36 | fdc227fb0884.md | 跨分区双副本 |
| 4 | 816417878 | user_1:5e3af34d5be116a6:1 | 1 | 1 | 2026-09-16T15:05:36 | fdc227fb0884.md | 跨分区双副本 |
| 5 | 1302561580 | user_1:cb08341c978d7b44:1 | 1 | 1 | 2026-09-16T15:05:36 | fdc227fb0884.md | 跨分区双副本 |
| 6 | 1329293447 | user_1:fde38d918b965d8a:1 | 1 | 1 | 2026-09-16T15:05:36 | fdc227fb0884.md | 跨分区双副本 |
| 7 | 1711174363 | user_1:c9d42d9459cdef8c:1 | 1 | 1 | 2026-09-16T16:06:25 | c56769527306.md | 跨分区双副本 |
| 8 | 2409068295 | user_1:46a2087225dadebf:1 | 1 | 1 | 2026-09-16T15:05:36 | fdc227fb0884.md | 跨分区双副本 |
| 9 | 3339387773 | user_1:090d075a32d33ed5:1 | 1 | 1 | 2026-09-16T16:06:25 | c56769527306.md | 跨分区双副本 |
| 10 | 3600661124 | user_1:13b00159ab5de394:1 | 1 | 1 | 2026-09-16T15:05:36 | fdc227fb0884.md | 跨分区双副本 |

10 行均为 doc_chunk / tenant_id=user_1 / visibility=public / internal=False（hex 命名来源文档，即 loader.py W-NEXT-RAG-002 注释点名的 WNEXTRAG1「All 742」批量重置涉及文件）。

**机理**（loader.py:506 `id=zlib.crc32(chunk_id)` 确定性 PK + :581 `upsert(partition_name=...)`）：chunk_id 带 tenant 前缀，同串 chunk_id → 同 crc32 PK。2026-09-16 15:05–16:06 导入窗内，同一批 user_1 chunk 被先后写入 `_default` 与 `user_1` 两个分区；Milvus upsert 只在目标分区内按 PK tombstone 旧版本，**跨分区旧副本不受影响而存活**。整表 query 的 reduce 阶段按 PK 去重返回最新副本（枚举=3388）；count(*) 是逐 segment 聚合的物理行数不去重（3398）；get 是 PK 检索同样去重（=1）。**flush 不消除的直接证据：3 个 persistent 段全部已 Flushed（state=4），无任何 growing 段——差异与 flush 状态无关，是查询语义差。**

**stats−count 的 +1**：`_default` 分区 stats=3374 vs count(*)=3373（分区级 stats−count 之和=1，与整表落差闭合）——1 条已删行待 compaction 回收，属 Milvus num_entities 不含 delete 过滤的已知行为。

**候选假设逐项排除表**（探针 hypothesis_scores 机判输出）：

| 候选（任务书） | 判定 | 机判证据 |
| --- | --- | --- |
| 字段 absent 行（三分类口径差） | **排除** | 枚举多要 chunk_id 行数不变（3388=3388）；差异 id 双副本字段齐全 |
| 软删标记行 | **排除** | 差异 id query_eq=1 且 get_eq=1（全部可读）；`internal != true` 过滤不在探针表达式内 |
| 正在插入的未 flush 段 | **排除** | persistent 全 state=4 Flushed、loaded 全 state=3；3 轮数字/sha 逐位稳定 |
| 查询表达式 vs count(*) 语义差（consistency level） | **成立（本批主结论）** | Strong 口径=3388 同 Bounded；差异=跨分区重复 PK 的 reduce 去重语义，非一致性级别问题 |
| 真实数据问题（count 可见但全不可读的真 ghost） | **排除** | 10/10 三元组 (2,1,1)，无 (n,0,0) |

## 四、复跑方式

```bash
cd edu-agent && .venv/Scripts/python.exe scripts/eval/milvus_count_probe.py --rounds 3
# [WMF1] {status, count_star:3398, enumerate:3388, stats:3399, gap:10, diff_ids[10],
#         attribution(_default:1+user_1:1)×10, paginate_same_set:true, strong:3388, ...}
# 产物 data/wnextmilvusflush1_probe.json（只读，退出码 1=口径不一致预期态 / 0=一致 / 2=不可达）
```

## 五、⑪⑲ 瞬态归因（COMMENT-PURGE 期间偶发红，安静窗转绿）

**红→绿机理一句话：红是探针运行环境时序（09-18 深夜整机崩溃/硬杀序列的恢复窗内 torch/BGE-M3 加载链故障与资源压力），不是向量数据态写入窗口——02:08 红窗前后 ≥2 天无任何 Milvus 新写入，数据口径跨窗逐位稳定，安静窗复跑 4 连绿。**

证据链：

1. **数据态窗口排除（判据：并发写时点的 count 漂移）**：10 条双副本与 _default 1 条已删行的写入窗为 09-16 15:05–16:06（分区 created_at max：user_1=09-16T20:44、user_100003=09-16T22:15、_default≤09-17T00:24），全部远早于红窗 09-19 02:08；且 count/enumerate/stats 三口径在 R-M2 登记（09-18 23:15）、前次探针（09-19 08:52）、本批 3 轮（09:2x）跨 20+ 小时逐位一致（3398/3388/3399，枚举 id 集 sha12=4ed85d1555af 恒定）。
2. **红窗落在恢复不稳窗**：COMMENT-PURGE check-demo（09-19 02:08，164.8s）落在 STABILITY 批登记的 ②09-19 00:07 外部 TerminateProcess 硬杀与 ④09-19 04:52 同型硬杀之间，且在 ①09-18 22:37 整机崩溃（Kernel-Power 41 + **torch_cpu.dll 0xc0000005** WER）之后 3.5 小时——torch/BGE 加载链在该窗有明确故障前科。
3. **对照 veclock_verify 12 维判据**：⑲ 最脆弱维度是 dim0 backend 探测（BGE-M3 mmap 在 Windows 内存压力下 os error 1455 → encode 回退 sha256 伪向量 → 提早退出红；v2 版头注释自证此前科，且 22:37 崩溃 WER 直接点名 torch_cpu.dll）与 dim9/dim11（FLAT 暴力基线取自 query 枚举集，IVF 检索面含全量 loaded 数据，两口径在非安静窗的资源压力/加载时序下错位放大 jaccard 抖动，故 v2 已设 0.7 softPASS 分层）；⑪ 虽不加载 BGE，但其 runPy 子进程 import 链同经 torch/embedder 栈（60s 超时上限），同窗同型脆弱。⑪⑲ 同时红、同窗同转绿，符合共因（进程环境）而非数据维度（两探针判据交集只有 Milvus 元数据，若元数据真坏则安静窗不可能 4 连绿）。
4. **安静窗复现实证**：前任三连（09:19 08:57–09:03，`data/wnextmilvusflush1_evidence/g11_run1-3.out`、`g19_run1-3.out`：⑪ 3388 行 PASS ×3、⑲ 12/12 PASS ×3）+ 本批独立复跑（`g11_c01_run1.out` exit=0、`g19_c01_run1.out` exit=0 12/12 PASS）= **4 连绿**。

**证据缺口（如实登记）**：02:08 红窗的 check-demo 原始 stdout 未存档（COMMENT-PURGE 报告仅记「红 ⑪⑲」），故 ⑲ 具体失败 dim 与 ⑪ 具体失败子项无法从产物直接指认——本报告的 dim 级归因（dim0/dim9/dim11 + import 链）是机理级高置信推断，数据态排除则是机判硬证据。建议后续 check-demo 红项落盘 stdout（见 P0-②）。

## 六、处置建议（不实施）

1. **guard 措辞校准（r03b_verify.py `_read_all_light`，R-M2 被阻断点）**：现行 `if len(rows) != cnt: raise "只读全量不完整"` 把「整表枚举 ≠ count(*)」当漏读，但两者语义本就不等价（枚举=PK reduce 去重视图，count(*)=物理副本数）。校准方案（择一或组合）：
   - **方案 B（推荐，保防漏读强度）**：改为**逐分区对拍**——对每个分区分别 `count(*)` 与枚举，分区级相等仍硬断言（本批实测 3373/3373、19/19、6/6 全闭合）。分区级不等才红（真漏读/同分区重复仍能抓）；整表层 `Σ分区count − 整表枚举 = 跨分区重复 PK 数` 降级为 WARN 并附 `milvus_count_probe.py` 定位指针。
   - 方案 A（最小改）：`len(rows) > cnt` 才红（枚举多于物理=真漏）；`len(rows) < cnt` 时以独立 offset 全走查（本探针 paginate_same_set 范式）证集合完整性后 WARN 放行。
   - 附注写进 guard 注释：`stats ≥ count(*)`（未 compaction 已删行）与 `count(*) ≥ 枚举`（跨分区重复 PK）均为 Milvus 合法语义，不得作为失败条件。
2. **数据卫生（可选变更单，非必需）**：`_default` 中 10 条 user_1 冗余副本可删（PK 清单见 §三/产物 attribution），预计消除 count−枚举差；检索正确性当前不受影响（reduce 返回的副本内容与 user_1 副本逐字段相同，且这些行 tenant=user_1 不会被 _default 租户检索语义命中）。**本批红线未执行任何删除。**
3. **⑪⑲**：无需改 veclock 判据；建议 check-demo 红项时同步落盘探针 stdout/stderr（消除本批遇到的 dim 级证据缺口）。

## 七、P0 自批判（5 条）

1. **⑪⑲ 红窗原始输出未存档，dim 级归因是推断不是实证**：§五第 3 点的 dim0/dim9/dim11 指认依赖 v2 注释前科 + STABILITY WER 时间线旁证，缺 02:08 stdout 直接证据。若当时红的实际是 dim1（如枚举行数瞬时异常）等未列维度，本报告机理结论仍成立（数据态排除是硬证据），但 dim 级表述会被证伪。已用「机理级高置信推断」如实降级表述。
2. **探针 diff 定位依赖「reduce 去重」语义假设，未从 Milvus 官方文档逐字核实该版本行为**：该语义是由 5 组独立机判数据反推闭合（整表 3388/分区和 3398/count 3398/三元组 (2,1,1)/per-partition 1+1），任一组被服务端行为变化打破则定性需重跑。探针已可复跑自证，但阅读者不应把「reduce 去重」当作权威文档结论引用。
3. **`created_at` 是业务层赋值字段，不是 Milvus 服务端插入时间戳**：「02:08 前后无写入」是由 created_at 窗 + 三口径跨 20 小时逐位稳定间接证明的；若存在「业务 created_at 回填旧值但实际新插入」的路径，该证明有洞。更硬的证据是 Milvus 服务端 consistency timestamp，本批未采集（探针未实现，登记为探针改进项）。
4. **前次中断草稿 `milvus_rowdiff_probe.py` 的 v1 假设打分有已证伪缺陷（growing 判据在段级全 sealed 数据上仍误判 true），文件已删除并由 v2 取代**——若有人从旧产物 `wnextmilvusflush1_rowdiff.json` 读到 `dominant_hypothesis="growing 段行只进 count 不进 query 枚举"`，该结论是错的（其自身段级数据即反证）；本批产物 `wnextmilvusflush1_probe.json` 已修正，但旧文件仍在 data/ 未清理（gitignore 外未入库，无传染面，登记不追改）。
5. **二分定位 579 次 count 探针在更大库（>16384 行/更多差异行）会线性膨胀**：dc_probes ≈ ghost×32+32，万级 ghost 将打 30 万+ 次查询，探针不可直接用于放量库；当前 3398 行规模下 4.66s 可接受。跨分区归属逐 id 逐分区查询同理 O(ghost×partitions)。

## 八、批判承接核对

| 来源 | 登记项 | 本批处置 |
| --- | --- | --- |
| R-M2（commit `1b13547`） | 「r03 系脚本被共享 Milvus 数据态阻断（query=3388 vs count=3398, flush 不消除）——外部域，已登记」 | **本批即该登记项的执行**：定量归因完成（§二/§三），定性=跨分区双副本正常语义差（非数据损坏、非未 flush），r03b guard 被阻断原因机判闭合，guard 措辞校准方案已交付（§六-1）；r03 系脚本解除阻断需按 §六实施（授权外未动） |
| R-M2 报告 §登记 | TEST-BASE 报告引用「Milvus 并发稳定窗（query=3388 vs count=3398 属 R-M2 已登记漂移）」2 例 skip | 归因完成后该 skip 理由应改写为「跨分区重复 PK 语义差（MILVUSFLUSH1 已归因）」——措辞属 TEST-BASE 批次权限，本批未越权改 |
| COMMENT-PURGE 报告 §七-5 | 「check-demo ⑪⑲ 红未处置……若 C-01 要求全绿回归需另派后端单」 | **本批承接瞬态归因部分**：⑪⑲ 已 4 连绿实证（§五-4），归因=探针运行环境时序，无需后端修复单；stdout 落盘建议移交 check-demo 维护批次 |
| grep critique tracker（critique-backlog-tracker.md / critique-tracker-v1.md 中 MILVUSFLUSH/3388） | 无其他未闭环承接项 | 已核对，0 命中 |

## 九、资产消费证据

| 资产 | 消费方式 |
| --- | --- |
| `git show 1b13547`（R-M2 commit） | 现象登记原文（query=3388 vs count=3398, flush 不消除）与外部域移交边界 |
| `edu-agent/scripts/eval/r03b_verify.py:70-82` | 防漏读 guard 判据原文（`len(rows)!=count(*)` 即红）＝处置建议对象 |
| `edu-agent/scripts/eval/veclock_verify.py`（v2 头注释+12 维判据） | dim0 mmap 1455 前科 / dim9 softPASS 分层 / Strong 一致读——⑪⑲ 瞬态归因判据来源 |
| `edu-agent/scripts/veclock_health_probe.py` + `check-demo.mjs` ⑪⑲ 段 | 两守卫的探针形态（runPy 子进程/60s 与 600s 超时/汇总行解析） |
| `edu-agent/app/knowledge/importer/loader.py` | PK 派生（crc32(chunk_id)）、upsert 分区语义、chunk_id 契约（C-R-CHUNK）、hex 来源文件前科注释 |
| `test-reports/WNEXTSTABILITY1-completion-report.md` | ①22:37 torch_cpu.dll 崩溃 / ②00:07 / ④04:52 硬杀时间线＝红窗定位 |
| `test-reports/WNEXTCOMMENTPURGE1-completion-report.md` §五 | 红窗时点（02:08）与「红 ⑪⑲」登记 |
| AGENTS.md | 教训 2（独立实证、禁 Playwright）、教训 8（真实契约优先于注释）、Milvus dynamic field 三分类教训（field-absent 假设检验设计）、分支/commit 纪律 |
| 前次中断草稿 `milvus_rowdiff_probe.py`（未入库）+ 产物 `wnextmilvusflush1_rowdiff.json`（08:52） | 本探针 v1 底稿（口径阶梯/二分定位框架继承，假设打分重写）+ 隔日口径旁证 |
| 安静窗证据 `data/wnextmilvusflush1_evidence/g11_run1-3.out、g19_run1-3.out`（08:57–09:03） | ⑪⑲ 3 连绿 + 3388 行枚举口径旁证 |
| 本批新增 | `scripts/eval/milvus_count_probe.py`（只读探针）、`data/wnextmilvusflush1_probe.json`（3 轮全量）、`g11_c01_run1.out/err`、`g19_c01_run1.out/err/json`（本批独立复跑） |

## 十、commit 纪律

- commit 前 `git symbolic-ref HEAD`（feature/opt-waves）+ `git rev-parse HEAD` 先查后提（见下方执行记录）。
- data/ 在 .gitignore 内，产物按 rn2 先例 force-add。
- 本批 commit `1845744`（probe+data，lock 已先删）；报告随独立 commit 入库（报告内引用 `1845744`）。
