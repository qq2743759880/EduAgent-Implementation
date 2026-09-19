# W-NEXT-R03BGUARD-001 完工报告

> 任务 ID：W-NEXT-R03BGUARD-001（yy 串行流水线唯一在岗 agent）
> 派单：C-01 编排者（MILVUSFLUSH-001 归因处置建议落地，方案 B 已获用户裁定）
> 完工日期：2026-09-19
> 本批 commit：**`b5c17e1`**（`b5c17e194b4890e476d486aee27e0aea49e718da`，代码+单测+真跑证据）+ 报告独立 commit（见文首引用）
> lock：`edu-agent/scripts/eval/r03bguard.lock` 已于 commit 前 rm + `ls` 复核不存在
> **红线自检：全程纯只读 Milvus（仅 query/count/list_partitions，零 flush/compaction/load/release/insert/delete/upsert）；文件归属=scripts/eval/r03b_verify.py（+111/−9 最小 diff）+ tests/test_r03b_read_guard.py（新增）+ 本报告 + data/r03bguard1_run.out（force-add 证据，rn2 先例）；未触 app/**、contracts/**、retriever/**；工作区他批在飞改动（probe JSON/r02tail/dualrun-baseline/next-env.d.ts 等）未纳 stalk 未提交。**

---

## 一、结论一句话

`_read_all_light` 防漏读 guard 已按 MILVUSFLUSH-001 处置建议 §六-1 **方案 B** 校准为**逐分区对拍**：4 分区全闭合（_default 3373/3373、course_public 0/0、user_1 19/19、user_100003 6/6）→ 整表差 count(*)=3398 − 枚举=3388 = **10 = 跨分区重复 PK 数** → 判定 **WARN**（附 10 个重复 id 清单，与探针产物 diff_ids 逐位一致），**不再 FAIL**；真漏读（分区 count≠枚举）与对拍不闭合仍硬红 raise。真跑全套：**G3 实时 hit_rate@5=0.9688 / mrr@5=0.9688，与冻结基线零偏差不退化**；新单测 11 例全绿 + eval 相邻回归 51 绿。R-M2 登记的「r03 系脚本被共享 Milvus 数据态阻断」就此**解除**。

## 二、guard diff（commit b5c17e1，+111/−9）

改动面（`edu-agent/scripts/eval/r03b_verify.py`）：

1. **新增纯函数 `_read_guard_verdict(part_ladder, whole_count, whole_enumerate)`**（单测直测，不连 Milvus），三段判据：
   - ① 每分区 `count == 枚举`（分区级相等硬断言——真漏读/同分区重复 PK 在此红，对应旧 guard 的防漏强度）；
   - ② 对拍闭合：`Σ分区 count == 整表 count` 且 `Σ分区枚举 − 跨分区唯一 id 数 == 整表 count − 整表枚举`（整表差无法完全归因于跨分区重复 → 红，防 ghost 漏网）；
   - ③ 跨分区重复 PK > 0 → **WARN** 附 `duplicate_ids` 清单 + 探针定位指针（`scripts/eval/milvus_count_probe.py`）。
2. **`_read_all_light` 改为逐分区对拍**：整表轻量枚举 + 整表 count(*) + `list_partitions` 后逐分区 count(*) 与 `["id"]` 枚举 → 交 `_read_guard_verdict`；FAIL 仍 `raise RuntimeError`（返回类型 `list[dict]` → `tuple[list[dict], dict]`）。
3. **guard 注释写明 Milvus 合法语义**（docstring，引用 `edu-agent/test-reports/MILVUSFLUSH1-completion-report.md`）：口径阶梯 `stats(num_entities)=3399 >= count(*)=3398 >= 整表枚举=3388`；stats−count(*)=已删行待 compaction（num_entities 不含 delete 过滤）合法不作失败条件；count(*)−枚举=跨分区同 PK 双副本（upsert 只 tombstone 目标分区，旧分区活副本存活；整表 query reduce 阶段按 PK 去重返回最新副本，count(*) 逐 segment 聚合不去重；3 个 persistent 段全 Flushed——与 flush 状态无关的查询语义差）。
4. **main 接线**：`rows, guard = _read_all_light(client)`；guard 以 **G0** 步入 `steps` 首位（全量 JSON 输出）；`all_pass` 判定集合 `(PASS, TODO, None)` → `(PASS, WARN, TODO, None)`（guard FAIL 在 `_read_all_light` 内已 raise，不会进 steps）。

## 三、真跑输出（2026-09-19 18:12，cwd=edu-agent，sidecar 8601 UP，wall=33.0s）

原始 stdout 全文：`edu-agent/data/r03bguard1_run.out`（已入库）。关键行：

```
Milvus edu_knowledge 只读全量: 3388 行 (guard=WARN: 跨分区重复 PK（同 PK 双副本，整表枚举按 PK reduce 去重
返回最新副本）: gap=10 dup_ids=10 个——Milvus 正常语义非数据问题（MILVUSFLUSH1 已归因），定位指针
scripts/eval/milvus_count_probe.py)

[G0] verdict=WARN  partitions: _default 3373/3373 closed=true · course_public 0/0 true ·
     user_1 19/19 true · user_100003 6/6 true
     whole_count=3398  whole_enumerate=3388  gap=10  part_count_sum=3398(=整表)  part_enumerate_sum=3398
     duplicate_pk_count=10  redundant_copies=10(=gap 闭合)
     duplicate_ids=[19587845, 145339617, 279813836, 816417878, 1302561580, 1329293447,
                    1711174363, 2409068295, 3339387773, 3600661124]
     ← 与 data/wnextmilvusflush1_probe.json rowdiff.diff_ids 逐位一致（值与顺序）

[G1] verdict=FAIL  new_in_lib=3343/4417（先在漂移，见 §四-1，非本批回归）
[G2] verdict=PASS  canonical_hash_match=3343/3343  doc_sha256_match=3343/3343  seq_bad_groups=0
[G3] mode=realtime_e2e_readonly(retrieve_three_channel 全链 + R03 precomputed dense)
     n=32  hit_rate@5=0.9688  mrr@5=0.9688   ← 冻结基线 0.9688，零偏差
     gt_resolve_via: 31×chunk_id+id_map + 1×miss（=基线已知 1 miss，31/32=0.9688）
[G4] verdict=PASS  dup_chunk_id=0  dup_pk=0（去重视图内唯一性完好）

ALL_PASS=False  wall=33.0s   （False 仅由先在 G1 漂移贡献；G0=WARN 不再贡献失败）
```

### 指标对账（不退化证明链）

| 时点 | 载体 | hit_rate@5 | 说明 |
| --- | --- | --- | --- |
| 2026-09-16 06:03 | `scripts/eval/r03b_verify_result.json`（R03 验收，已入库） | 0.9688（realtime） | 4417 行时代 |
| 2026-09-18 10:49 | `scripts/eval/data/r03b_verify_rm2_live.json`（R-M2 live） | 0.9688（persisted_replay） | 3388 行时代 |
| 2026-09-19 18:12 | 本批 `data/r03bguard1_run.out`（realtime 全链） | **0.9688（realtime）** | guard WARN 放行后首跑，零偏差 |

## 四、G1 FAIL 归因（如实登记，非本批回归）

- G1 逻辑本批**零改动**（diff 不含 step1_idmap）。`new_in_lib=3343/4417` 与 09-18 R-M2 live 产物**逐位相同**——先在于本批，属 R03 冻结 id_map vs 现库的**库演化漂移**（R03 后 WNEXTRAG/R22 等批次重导入致 4417→3388 行）。
- 时序佐证：09-16 产物 G1 PASS（4417/4417）；旧 guard 在 R-M2 登记 count=3398 后根本跑不到 G1（`_read_all_light` 先 raise）——本批 WARN 放行才使 G1 重新可见，同值 FAIL 恰证其先在性。
- 本批红线禁碰数据/迁移资产，未修 G1；处置建议移交编排者（另派数据对账单：重生成 id_map 或按批切分对账窗口）。

## 五、单测结果（commit b5c17e1）

新增 `edu-agent/tests/test_r03b_read_guard.py`（11 例，纯内存不连 Milvus）：

| 用例 | 覆盖 | 结果 |
| --- | --- | --- |
| test_pass_multi_partition_closed_no_dup | 三分区全闭合无重复 → PASS | PASS |
| test_pass_milvusflush_real_shape | MILVUSFLUSH 实证形态缩样（双副本，gap=冗余=1）→ WARN | PASS |
| test_warn_duplicate_ids_listed_not_fail | 重复 PK 附 id 清单且不 FAIL | PASS |
| test_fail_partition_count_mismatch_true_missing | 分区 count≠枚举（真漏读/ghost）→ FAIL | PASS |
| test_fail_unexplained_gap_all_partitions_closed | 分区全闭合但整表差无法归因 → FAIL（防 ghost 漏网） | PASS |
| test_fail_part_count_sum_mismatch | Σ分区 count≠整表 count → FAIL | PASS |
| test_fail_same_partition_duplicate_pk | 同分区重复 PK → FAIL | PASS |
| test_warn_triplicate_pk_gap_two | 同 PK 三副本 gap=2 按冗余副本数归因 → WARN | PASS |
| test_read_all_light_warn_shape_passes_through | 伪客户端接线：WARN 放行返回 (rows, guard) | PASS |
| test_read_all_light_true_missing_raises | 伪客户端接线：真漏读 raise RuntimeError | PASS |
| test_read_all_light_clean_pass | 伪客户端接线：干净态 PASS | PASS |

回归：`pytest tests/test_r03b_read_guard.py tests/test_build_eval_set64.py tests/test_contract_task_e1.py` → **51 passed**（eval 脚本命名空间相邻单测全绿；r03b_verify 此前无专测，本批为首个）。首跑曾 2 夹具口径错误（whole_enumerate 必须等于跨分区去重唯一 id 数）——错误方向均为 guard 正确 fail-closed，已修正夹具并把口径写进 docstring。

## 六、P0 自批判（5 条）

1. **G1 FAIL 未处置（超范围登记）**：本批交付是 guard 校准，不是 r03b 全绿——`all_pass=False`、退出码 1 由先在 G1 库演化漂移贡献。若编排者验收口径是「ALL_PASS=True」，本批不满足，需另派数据对账单（重生成 id_map 或冻结「R03 时代对账窗」）。报告已如实给出三时点对账链，防「guard 绿=G 全绿」误读。
2. **guard 保留 16384 单页上限，未做分页 walk**：单分区或整表 >16384 行时枚举截断 → count≠枚举 → 误红（fail-closed 方向，安全但会阻断放量库）。现库 3398 行远低于阈值 + 最小 diff 约束未实现探针 ⑪ offset 分页范式；放量前必须先改分页。
3. **WARN 放行使 all_pass 语义放宽，且 guard 只对拍数量不对拍内容**：「整表差=跨分区重复 PK 数」即 WARN——若未来出现**内容不同**的双副本（reduce 返回旧副本/字段漂移），guard 仍 WARN 不红。本批 10 id 双副本「逐字段相同」依据的是 MILVUSFLUSH 探针 attribution（09-19 实测），该核验不在 r03b guard 判据内；内容漂移风险需 milvus_count_probe 复核兜底。
4. **「reduce 返回最新副本」是归因推断非 guard 实证**：与 MILVUSFLUSH 报告 P0-② 同源——该语义由 5 组机判数据反推闭合，未逐字核实 Milvus v2.5.5 官方文档；guard 注释引用时已写「正常语义」但读者不应当作权威文档结论。服务端行为变化（reduce 语义改动）只会改变 WARN 的正确性，不会使其变红。
5. **G0 计数口径依赖 `list_partitions` 完整性**：若分区清单因权限/时序缺失某分区，Σ分区 count < 整表 count → 走 FAIL 分支（对拍不闭合）——方向安全，但错误信息只报「Σ分区count != 整表count」，未明确提示「分区清单可能不完整」，排障时需先核 list_partitions。

## 七、批判承接核对

| 来源 | 登记项 | 本批处置 |
| --- | --- | --- |
| MILVUSFLUSH1 报告 §六-1（方案 B，用户裁定） | guard 措辞校准：逐分区对拍，分区级相等硬断言；整表差=跨分区重复 PK 数降级 WARN 附探针定位指针 | **本批即执行**：`_read_guard_verdict` 三段判据 + `_read_all_light` 逐分区 ladder + duplicate_ids 清单 + `milvus_count_probe.py` 指针；真跑 4 分区全闭合（3373/3373、19/19、6/6 + course_public 0/0）与报告 §六-1 预告数字一致 |
| MILVUSFLUSH1 报告 §六-1 附注 | guard 注释写明 `stats ≥ count(*)`（未 compaction 已删行）与 `count(*) ≥ 枚举`（跨分区重复 PK）均为 Milvus 合法语义，不得作为失败条件 | 已写入 `_read_all_light` docstring（口径阶梯 3399≥3398≥3388 + 双副本机理 + 引用 MILVUSFLUSH1 报告） |
| R-M2（commit `1b13547`） | 「r03 系脚本被共享 Milvus 数据态阻断（query=3388 vs count=3398, flush 不消除）」 | **解除阻断**：guard WARN 放行，全套可跑（G0/G2/G3/G4 实证输出）；R-M2 移交闭环 |
| MILVUSFLUSH1 报告 §六-2 | 数据卫生可选变更单（删 _default 10 条 user_1 冗余副本） | **未执行**（本批红线禁写 Milvus；检索正确性不受影响已归因，留待用户裁定） |
| MILVUSFLUSH1 报告 §八（TEST-BASE 措辞改写移交） | 「Milvus 并发稳定窗」skip 理由应改写为「跨分区重复 PK 语义差」 | 不属本批权限（TEST-BASE 批次），未越权改 |
| MILVUSFLUSH1 报告 P0-② | 「reduce 去重」未从官方文档逐字核实 | 承接为 P0-④（guard 注释引用时保留推断属性；guard 数量对拍对该语义变化不敏感的边界已登记） |

## 八、资产消费证据

| 资产 | 消费方式 |
| --- | --- |
| `edu-agent/test-reports/MILVUSFLUSH1-completion-report.md` | §六-1 方案 B 判据原文（实现蓝本）、§三 10 id 表（WARN 清单对照）、§五/P0（注释措辞与自批判边界） |
| `edu-agent/scripts/eval/milvus_count_probe.py` | 口径阶梯与分区对拍法照抄（`_count`/`_enumerate`/`_partition_ladder` 的 partition_names 传参范式、只读原语集合） |
| `edu-agent/data/wnextmilvusflush1_probe.json` | 10 差异 id 清单 + 分区归属（_default+user_1）+ 闭合数字——guard 判据设计输入；本批 G0 输出 dup_ids 与其 diff_ids 逐位一致（资产有效性实证） |
| `edu-agent/scripts/eval/r03b_verify.py`（原版） | `_read_all_light` 旧判据（`len(rows)!=cnt` 即红）=改造对象；G1–G4 结构与 main 接线 |
| `edu-agent/scripts/eval/data/r03b_verify_rm2_live.json` | 09-18 基线：G1 3343/4417 同值 FAIL——先在漂移证据（§四） |
| `edu-agent/scripts/eval/r03b_verify_result.json` | 09-16 R03 验收：4417 行 G1 PASS、G3 realtime 0.9688——hit_rate 不退化对照锚点 |
| `edu-agent/tests/conftest.py` + `test_build_eval_set64.py` | `from scripts.eval import ...` 测试导入范式、autouse fixture 约定 |
| `AGENTS.md` | 教训 2（独立实证：真 HTTP/真库 + pytest，禁 Playwright）、教训 8（真实契约优先于页面注释）、分支/commit/lock 纪律 |
| 本批新增 | `scripts/eval/r03b_verify.py`（guard 校准）、`tests/test_r03b_read_guard.py`（11 例）、`data/r03bguard1_run.out`（真跑 stdout 全文）、本报告 |

## 九、commit 纪律

- commit 前 `git symbolic-ref HEAD`=feature/opt-waves + `git rev-parse HEAD`=3870dc2 先查后提；lock 于 commit 前 rm 且 `ls` 复核不存在。
- 本批 commit `b5c17e1`（r03b_verify.py + test_r03b_read_guard.py + data/r03bguard1_run.out force-add）；报告随独立 commit 入库（报告内引用 `b5c17e1`）。
- 工作区他批在飞改动未纳入本批提交（文件归属红线）。
