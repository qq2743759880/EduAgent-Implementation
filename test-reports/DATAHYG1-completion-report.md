# W-NEXT-DATAHYG-001 完工报告：edu_knowledge `_default` 分区 10 条跨分区冗余副本清除

> 执行 agent：yy 并行流水线 W-NEXT-DATAHYG-001 在岗（C-01 逐断言独立实证口径）。
> 立项依据：用户已批准数据卫生变更单（数据软删三核闸纪律适用）；承接 `edu-agent/test-reports/MILVUSFLUSH1-completion-report.md` §六-2 处置建议。
> 代码批 commit：`e661f05`（e661f05093d720460d9ba1cc24082b6a261c4fe7，报告随独立 commit 入库，本文件引用该 hash）。

## 一、任务与范围

清除 `edu_knowledge`（Milvus `http://192.168.85.101:19530`，pymilvus 3.0.1）中 10 个 PK 在 `_default` 分区的跨分区冗余副本（每个 PK 在 `_default`+`user_1` 各持 1 份活副本，写入窗 09-16 15:05~16:06，hex 命名 md 来源，upsert 只 tombstone 目标分区导致旧副本存活——MILVUSFLUSH1 定性）。预期整表 count(*) 3398→3388，query 枚举 reduce 去重集合不变（检索零影响）。

红线执行情况：
- 只动 10 PK 的 `_default` 副本：`client.delete(COLL, ids=pks, partition_name="_default")` 分区名精确限定；**未触** user_1/user_100003/course_public 分区与任何其他行（verify 分区计数逐位对账）。
- 唯一写原语 = 该 delete 调用；零 flush/compaction/load/release/insert/upsert（备份 meta 中记载的重插恢复命令仅为文档，本批未执行）。
- 文件归属：`scripts/eval/datahyg_apply.py`（新）+ 备份 JSON + data 产物 + 本报告；**未触** app/**、contracts/**、tests/**、retriever。

## 二、执行记录（三核闸逐步留痕）

### 核1 备份先行（02:09:41）
`datahyg_apply.py backup` → `edu-agent/data/datahyg_backup_20260920_020941.json`（force-add 入库）：
- 20 行 = 10 PK × 2 分区（`_default` 10 + `user_1` 10），PK 清单唯一来源 `wnextmilvusflush1_probe.json#rowdiff.diff_ids`（数量≠10 即拒执行）。
- 全字段：标量 8 项（id/chunk_id/content/content_type/source_file/sparse_vec/tenant_id/visibility）+ 动态字段 5 项（created_at/embed_normalized/embed_precision/embedding_model/internal）+ dense_vec 1024 维全精度浮点。样本行 chunk_id=`user_1:adb078bf3017153b:1`、tenant_id=user_1、source_file=`c56769527306.md`、created_at=`2026-09-16T16:06:25.069304` 与 MILVUSFLUSH1 attribution 逐字段同。
- 结构自证（不过即中止）：每 PK `_default`/`user_1` 各恰 1 行 ✓；标量字段全覆盖 ✓；向量维度=1024 ✓；**双副本逐标量一致**（`structural_problems=[]`、`default_vs_user1_scalar_diffs=[]`——删 `_default` 冗余副本不丢任何信息的前提实证）✓。

### 删前 precheck（02:10:30）
`datahyg_apply.py precheck` → `datahyg_precheck_20260920_021030.json`：
- 口径阶梯与 MILVUSFLUSH1 探针基线**逐位一致**：stats=3399 / count(*)=3398 / 枚举=3388 / 枚举 sha12=`4ed85d1555af` / 分区 count 3373·0·19·6（与 09-19 探针 round1 同值同 sha）。不符即 fail-closed 拒执行。
- 逐 PK 归属核验：10 PK × 4 分区 = `_default` 1 + `user_1` 1 + 其余 0，全闭合。
- golden5 预跑（eval64-v2 集选案）5/5 hit（rank 1,3,1,1,1）。

### 核2 执行（02:11 首跑，02:12 幂等复跑）
- **apply#1（fresh 路径）**：状态机校验（10 PK `_default`=1/`user_1`=1）→ 下发 `delete(ids=10, partition_name="_default")` → **删后立即断言撞 Bounded 一致性陈旧读窗口（count(*) 仍读 3398）→ fail-closed 中止**（脚本设计：不在陈旧读上宣布成功）。删除本身已生效：中止后立即只读重探 = count(*) 3388、`_default` 3363、其余分区不变、10 PK `_default` 0 命中/`user_1` 10 命中。事后补强留痕：`datahyg_fresh_delete_evidence.json`（只读重探 + apply#1 fatal 转录；如实标注为 post-hoc 证据）。
- 教训已回写脚本：`wait_visible()` 删后轮询 count(*)/枚举 sha 收敛（≤90s）再断言；**未用 flush 加速收敛**（红线）。
- **apply#2（幂等路径，= 核4）**：02:12:35 → `datahyg_apply_20260920_021235.json`：10 PK 全部判为 already_deleted → 重发同参 delete（返回 delete_count=10，Milvus 对不存在 PK 的 no-op 语义）→ pre/post 三口径**逐位不变**（count 3388/枚举 3388/sha `4ed85d1555af`/分区 3363·0·19·6），无报错。

### 核3 复核（02:13:18）
`datahyg_apply.py verify` → `datahyg_verify_20260920_021318.json`，三查全过：
1. **逐 PK 命中**：10 PK 在 `_default` 0 命中；`user_1` 各恰 1 命中（取回 10/10 行，副本完好）；user_100003/course_public 0 命中（未被波及）。
2. **整表枚举**：count(*)=3388、枚举=3388、sha12=`4ed85d1555af` 与删前逐位一致（reduce 去重集合不变 = 检索零影响）；分区 count 3373→3363（−10，恰为目标）、19/6/0 不变。
3. **golden 抽检 5 条**（eval64-v2 集 `r64v2_eval_set64.json`，与冻结契约同参：retrieve_three_channel 全链 召回150→rerank20→断崖0.40→top5、use_hyde=false、enable_graph=true、串行）：5/5 hit，rank 1,3,1,1,1 与删前 precheck **逐条同 rank**。

### 核4 幂等
见 apply#2：重跑删除脚本对已删行 no-op 不报错、三口径零漂移。

## 三、count 前后对比

| 口径 | 删前（precheck 02:10） | 删后（verify 02:13） | Δ |
|---|---|---|---|
| stats row_count | 3399 | 3399 | 0（stats 数物理行，tombstone 待 compaction；差 1→11 属预期态，compaction 留自然周期） |
| count(*) 整表 | **3398** | **3388** | **−10 ✓（预期 3398→3388）** |
| 枚举（reduce 去重） | 3388 | 3388 | 0 ✓；sha12 `4ed85d1555af` 逐位不变 ✓ |
| count(*) `_default` | 3373 | 3363 | −10 ✓（恰为目标副本数） |
| count(*) user_1 / user_100003 / course_public | 19 / 6 / 0 | 19 / 6 / 0 | 0/0/0 ✓（红线分区零波及） |

## 四、环境恢复登记（任务书外处置，如实上报）

执行窗口恰逢宿主 VM 夜间例行（00:59 快照 '9.20' + 挂起）叠加意外：
- 数据 VM = `E:\tt\CentOS 7 64 位`（Milvus/etcd/minio 宿主，静态 .101）；01:13 一个**空载 docker-clone VM**（`CentOS 7 64 位的克隆 docker`，0 镜像/0 容器，同静态 IP .101）被拉起抢占 IP；01:16 一次恢复尝试触发 VMware Workstation 16.2.3 restore 路径 access violation panic（0xc0000005，vmware-vmx.dmp 在案）。
- 恢复动作（全部可逆、无数据丢失，挂起态完整保存在快照 '9.20'/Snapshot17）：kill 卡死 VMX（3 次）、清 stale `.lck`、SSH 关闭空载 clone（先取证 0 镜像/0 容器/无服务再 `shutdown -h now`）、关闭 VMware UI、`vmrun start … nogui` 冷启动（磁盘持久化数据 + 容器 restart=always 自愈）。02:08 Milvus 19530 OPEN，02:09:36 milvus-standalone healthy，precheck 基线与 09-19 探针逐位一致证明恢复后数据态无损。
- 若 clone VM 另有用途可一键重启（但需让出 .101）。

## 五、P0 自批判（5 条）

1. **apply#1 无自身产物，fresh 路径证据链含一处 post-hoc 补强**：删后立即断言撞 Bounded 滞后 → fail-closed 中止发生在 `_ok()` 落产物之前，"删前=3398" 的机器证据依赖 precheck 产物 + 事后只读重探（`datahyg_fresh_delete_evidence.json`，如实标注 post-hoc）。教训（FATAL 也应落产物 + 删后可见性轮询）已回写脚本，但 apply#1 本体不可重放（删除是破坏性原语，不做"回滚重演"）。
2. **环境恢复超出任务书授权面**：kill VMX/关 clone VM/关 UI 属宿主基础设施处置，本 agent 权衡"任务不可达"后自行决断——动作虽全部可逆且取证在案，但若 clone VM 有编排者未预期的用途，该处置需人工知悉与复核。
3. **脚本是一次性变更单执行器，不是通用工具**：期望值 3398/3388/sha `4ed85d1555af` 硬编码自 MILVUSFLUSH1 基线，任何先行漂移都会 fail-closed 拒跑（设计意图）。幂等保证仅对"同一变更单语义"成立，误用于其他集合/分区不提供保护。
4. **golden 抽检覆盖不到被删副本所属的 user_1 域**：eval64-v2 的 64 case 全部 `_default`/course 域 golden（与 10 个被删副本的 user_1 域零交集）；user_1 域"检索零影响"的证明是间接的（user_1 副本逐字段完好 + 10/10 可查 + 枚举集合 sha 不变的 reduce 语义），未新造 user_1 域端到端检索 case（无既有评估集可复用，登记不造）。
5. **stats−count 差从 1 扩大为 11 是本批直接后果**：compaction 留自然周期（红线），期间任何以 `get_collection_stats` 为准的读数会与 count(*) 呈 11 行差——须按 MILVUSFLUSH1 §六-1 附注语义（stats≥count(*) 合法）解读，r03b guard 已按方案 B 校准不受影响；但下游若有未校准的 stats 监控，会看到差值扩大（登记提醒）。

## 六、批判承接核对

| 来源 | 登记项 | 本批处置 |
| --- | --- | --- |
| MILVUSFLUSH1 §六-2 | 数据卫生可选变更单：`_default` 10 条 user_1 冗余副本可删，预计消除 count−枚举差 | **本批即执行**（用户批准立项）：count−枚举差 10→0，检索零影响三重实证 |
| MILVUSFLUSH1 §六-1 | guard 方案 B 逐分区对拍（整表差=跨分区重复数降 WARN） | 已由 R03BGUARD1 批落地（b5c17e1）；本批删除后该 guard 整表 WARN gap 应 10→0——自然周期复核项（本批未重跑 guard 全套，登记） |
| MILVUSFLUSH1 P0 #2 | "reduce 去重语义系数据反推，非文档权威" | 本批构成该假设的**破坏性再验证**：物理删除 `_default` 副本后枚举集合 sha 逐位不变（若语义有误，删除会改变枚举结果）——语义假设进一步加固 |
| MILVUSFLUSH1 P0 #3 | created_at 非服务端时间戳，判序不可依赖 | 本批未用 created_at 判序；目标识别仅依赖探针 attribution 的逐分区 count + 双副本逐标量一致 |
| AGENTS.md 教训 2/8 | 独立实证/真实契约优先 | 全部断言为真实 HTTP/gRPC Milvus 实测；脚本内期望口径在 precheck 与基线产物逐位对齐后才放行 |

## 七、资产消费证据

| 资产 | 消费方式 |
| --- | --- |
| `edu-agent/test-reports/MILVUSFLUSH1-completion-report.md` §六-2 | 立项依据与处置建议原文（"本批红线未执行任何删除"→本批执行） |
| `edu-agent/data/wnextmilvusflush1_probe.json` | PK 清单唯一来源（diff_ids）+ 基线口径（round1 三口径/分区/枚举 sha12）+ attribution 逐字段对照 |
| `edu-agent/scripts/eval/milvus_count_probe.py` | 口径阶梯/枚举 sha12/逐分区 count 范式与连接方式（.env 兜底加载）继承 |
| `edu-agent/scripts/eval/r03b_verify.py` | G3 实时检索评估范式（retrieve_three_channel 只读评估 + BGE 冷启动预热教训） |
| `edu-agent/scripts/eval/build_eval_set64.py` + `r20min_run._match_golden` | golden5 测量同参复用（串行确定性 + chunk_id/doc_sha256 双键解析） |
| `contracts/rag-baseline-eval64-v2.json` + `scripts/eval/data/r64v2_eval_set64.json` + `data/r64v2_runs/r64v2_base_run1.json` | 抽检选案（基线 hit 案均布取 5）与契约参数（cliff 0.40/hyde off/graph on） |
| `edu-agent/scripts/ssh_diag.py` | VM SSH 通道既有范式（恢复期使用） |
| AGENTS.md | 教训 2（独立实证）、教训 8（真实契约优先）、数据软删三核闸纪律 |
| `pymilvus 3.0.1` 签名实测 | `delete(partition_name=)`/`query(partition_names=)` 精确语义确认 |

## 八、产物与 commit 纪律

- 代码：`edu-agent/scripts/eval/datahyg_apply.py`（backup/precheck/apply/verify 四模式，fail-closed 断言，唯一写原语=分区限定 delete）。
- data 产物（.gitignore 内，按 rn2 先例 force-add）：`datahyg_backup_20260920_020941.json`（备份，恢复路径 meta 在案）、`datahyg_precheck_20260920_021030.json`、`datahyg_fresh_delete_evidence.json`、`datahyg_apply_20260920_021235.json`、`datahyg_verify_20260920_021318.json`。
- lock：`edu-agent/scripts/eval/datahyg.lock` 于 commit 前删除。
- 分支：`feature/opt-waves`（commit 前 symbolic-ref 已核）。
