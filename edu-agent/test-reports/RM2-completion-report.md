# R-M2 完成报告：M-2 大制品归档层（GridFS + 本地降级）

- 日期：2026-09-18（收口 commit hash 见文末）
- 接手背景：前任两次 API 中断，半成品 WIP `2e216e8` → `a23ab48`。本任务按 C-01 编排者纪律完成逐断言独立实证验收（真实 HTTP/DB 基元，非空断言）。
- 方案依据：`.ai-hub/plans/neo4j-mongo-activation-plan.md` §M-2（"eval 运行产物 / R03 id_map 51K 行 JSON 入库教训的反面落地"）。

## 1. 收口 commit

- 本报告随收口 commit 提交（hash 见 commit message 引用本报告处）：改动仅 3 个归属文件
  `app/common/artifact_store.py`、`tests/test_artifact_store.py`、`test-reports/RM2-completion-report.md`。

## 2. 历任半成品处置（逐文件）

| 文件 | WIP 来源 | 处置 | 说明 |
|---|---|---|---|
| `app/common/artifact_store.py` | 2e216e8 新建 364 行 + a23ab48 修 13 行 | **复用 + 修复** | a23ab48 已修 `list_artifacts` 首调用 `_db=None` 误降级、本地 dedup 标志如实上报；本次收口再修 2 个契约缺陷（见 §6 P0-1/P0-2），其余设计（降级链不抛异常、原子替换、BSON 化元数据、CLI）审查通过直接复用 |
| `tests/test_artifact_store.py` | 2e216e8 新建 224 行 + a23ab48 解除 2 处 skip 并修 fixture | **复用 + 补测** | a23ab48 已修前任 skip 根因（module 级 fixture 清库走 `_mongo_config()` 回落生产库的 P0 隐患 → 显式 client 只删 `edu_agent_rm2_test`；模块开始+收尾双清库）；本次收口补 2 个回归测试（metadata 保留字防污染 / local- aid 不触 mongo），16→18 项全绿 |
| `scripts/eval/r03_migrate.py` | 2e216e8 改 16 行 | **复用（已实证审查）** | `write_id_map` 落盘改走 `save_artifact("eval/r03/id_map.json", ..., local_copy=safe_w(ID_MAP_PATH))`，归档失败回退直接落盘不阻断迁移。运行被外部数据态阻断（见 §4.3），接线代码与已实证的 r20min 同构 |
| `scripts/eval/r03b_verify.py` | 2e216e8 改 16 行 | **复用（已实证审查）** | `--result` 写出同构接线 `eval/r03b/verify_result.json`。运行被外部数据态阻断（见 §4.3） |
| `scripts/eval/r20b_dualrun_probe.py` | 2e216e8 改 21 行 | **复用（已实证审查）** | `_dump_results` 同构接线 `eval/r20b/dualrun_results.json`。未复跑：依赖 LLM 双模型（AGENTS.md task29 批判②已实证 strong=402 余额不足），非代码缺口 |
| `scripts/eval/r20min_run.py` | 2e216e8 改 17 行 | **复用 + 真实运行实证** | `run_eval` 接线 `eval/runs/{tag}.json`，真实跑通（见 §4.1） |

前任遗留调试残渣 `test-reports/_rm2dbg_local2/`（降级路径 debug 沙箱）非交付物，未纳入 commit；本次实测产生的临时目录 `_rm2_fallback_live/` 已清理。

## 3. Mongo 连通自证

- `admin.command('ping')` → `{'ok': 1.0}`（192.168.85.101:27017，pymongo serverSelectionTimeoutMS=5000）
- 库清单 `['admin', 'config', 'edu_agent', 'local']`；`settings.MONGO_URI=mongodb://192.168.85.101:27017`、`settings.MONGO_DB=edu_agent`
- 收口前 `artifacts.files` 计数 = **0**（即：前任 eval 接线从未被端到端证明——本次收口补齐该空缺）

## 4. 独立实证证据

### 4.1 真实 eval 脚本产物入 store → 读回 sha256 一致（核心验收）

真实运行 `r20min_run.py --mode eval --tag rm2_artifact_close`（32 query 全链路：Milvus hybrid 召回 150 → BGE rerank → 截断 top5，非冻结候选）：

```
[artifact] backend=mongo aid=6aad53271dc7c6afc8f9f7a7 sha256=80f4002df84ca163 size=27293
[eval:rm2_artifact_close] hit_rate@5=0.9688 mrr@5=0.9688 n=32 wall=132.3s
```

- 指标与冻结基线一致（hit_rate@5=0.9688 = `data/r20min_runs/base_run1.json`），证明接线未扰动评估语义。
- 读回：`load_artifact("6aad53271dc7c6afc8f9f7a7")` = 27293 字节，sha256 = `80f4002df84ca16315dec58ba79a0a4f13880df2ce2808846a9b5f5b67962e2f`；与 local_copy 工作副本 `scripts/eval/data/r20min_runs/rm2_artifact_close.json` **逐字节相同**（BYTE_IDENTICAL: True）；`load_artifact_json` 反序列化正确（hit_rate@5=0.9688）。
- `list_artifacts(prefix="eval/runs/")` 返回该制品，backend=mongo，metadata（kind/tag/n_cases/hit_rate@5/mrr@5）完整。

### 4.2 1.87MB 大制品（M-2 动机场景本体）CLI round-trip

用触发 M-2 立项的历史文件本体（R03 id_map，曾被迫 force-add 进 git 的 51K 行 JSON）走 CLI：

```
archive scripts/eval/data/r03_id_map.json eval/r03/id_map_git_snapshot.json --source rm2_close
→ aid=6aad53d67f087644e32b3571 backend=mongo size=1866921 dedup=false
get 6aad53d67f087644e32b3571 → sha256=aa8e9be6417cedb66649b5e24ca705713a73241614526d764412f90158464ddf
源文件 sha256              = aa8e9be6417cedb66649b5e24ca705713a73241614526d764412f90158464ddf  ← 一致
```

跨 GridFS 255KB chunk 边界（1.87MB ≈ 8 chunks）读回一致；`>1MB` 单测等价覆盖。

### 4.3 r03 系脚本外部阻断记录（非代码缺口）

- `r03b_verify.py` 实跑在制品写入**之前**即抛 `RuntimeError: 只读全量不完整: query=3388 count(*)=3398`；`r03_migrate.py` 的 `read_all_rows` 同 guard。
- 已做 3 次计数探针（稳定 3398）+ `flush('edu_knowledge')` 后复测（仍 3388/3398）——差异在 flush 后持续存在，属共享 Milvus 集合数据态（R03/R-N1 域，疑 upsert 后待 compaction 残留）。**不修该 guard**：它是「防漏读掩盖」的忠实执行，放宽它去凑制品 demo 是错误方向。
- 前任 2026-09-18 18:49 的 `r03b_verify` 存量结果（`data/r03b_verify_rm2_live.json`，row_count=3388，G1 FAIL）佐证脚本本体可跑、失败与制品层无关；且该次运行**未在 GridFS/本地留任何制品痕迹**（收口前 artifacts.files=0、无 artifacts_local），从反面确认端到端实证此前缺失。

### 4.4 降级本地路径实测（真实不可达 URI）

`ARTIFACT_MONGO_URI=mongodb://127.0.0.1:1/`（连接拒绝）+ 独立 `ARTIFACT_LOCAL_DIR`：

- save → `backend=local`，WARN「MongoDB 不可达(ServerSelectionTimeoutError...)，制品 eval/fallback/live.json 降级落本地」落 logger；
- 同名同内容二次 save → 同 aid，`dedup=True`，`_index.jsonl` 保持 1 行（幂等）；
- 读回 sha256=`e518536fb20491e8...` 与描述符一致、JSON 等价；磁盘实物 `eval__fallback__live.json` 存在；
- `list_artifacts` 降级返回本地索引条目；
- 1.2MB 随机字节降级大制品 round-trip sha 一致；
- 双降级（本地目录置于文件之下必败）→ `backend="none"` 留痕不抛异常——由单测 `test_both_stores_fail_returns_none_no_raise` 覆盖。

### 4.5 pytest 全绿

`pytest tests/test_artifact_store.py` → **18 passed**（57~64s，真实 Mongo），含前任曾 skip 的 `test_idempotent_same_name_and_content`、`test_mongo_recovered_after_degradation`（a23ab48 已解除 skip 并修复根因），及本次收口新增 2 项回归（§6 P0-1/P0-2）。测试库 `edu_agent_rm2_test` 模块开始+收尾双清库，不污染生产库。

## 5. 接入点清单（资产消费面）

| 接入点 | 触发位置 | 制品名 | local_copy（下游读者兼容） |
|---|---|---|---|
| `scripts/eval/r03_migrate.py` | `write_id_map()` 末尾 | `eval/r03/id_map.json` | `scripts/eval/data/r03_id_map.json` |
| `scripts/eval/r03b_verify.py` | `main()` 的 `--result` 分支 | `eval/r03b/verify_result.json` | `--result` 指定路径 |
| `scripts/eval/r20b_dualrun_probe.py` | `_dump_results()` | `eval/r20b/dualrun_results.json` | `data/r20b_dualrun_results.json`（OUT_RESULTS） |
| `scripts/eval/r20min_run.py` | `run_eval()` 报告落盘处 | `eval/runs/{tag}.json` | `scripts/eval/data/r20min_runs/{tag}.json`（`r03b_verify._baseline_reference` 等下游读者依赖） |
| 运维/人工 | `python -m app.common.artifact_store archive|get|list` | 任意 | — |

行为契约（全部实测覆盖）：`save_artifact` 绝不因存储故障抛异常（降级链 mongo→local→none）；描述符必含 sha256/size/created_at/source/backend/dedup；同 (name, sha256) 幂等；`load_artifact` 仅真不存在抛 KeyError。

## 6. P0 自批判（≥3，含已修复与登记未修）

1. **[已修复] 调用方 metadata 可污染 GridFS 去重键**：原实现 `metadata={"sha256":…, **(desc["metadata"] or {})}` 展开在最后，调用方传 `{"sha256": "FAKE"}` 即覆盖 `files.metadata.sha256` → 后续同 (name, 真 sha) 的 dedup 查询永久 miss，重复副本静默翻倍，直接违背幂等契约。修复：保留字过滤（`_RESERVED_META_KEYS`）+ 回归测试 `test_metadata_reserved_keys_cannot_poison_dedup`。
2. **[已修复] mongo 健康时读 `local-*` aid 误报基础设施故障**：实测捕获 `WARN 读取不可达(InvalidId: 'local-…' is not a valid ObjectId)`——本地降级制品的常规读取被记成「MongoDB 读取不可达」，故障期间会误导运维判向。修复：`local-` 前缀 aid 直查本地索引（`_load_local`），永不触 mongo + 回归测试 `test_load_local_aid_never_touches_mongo`。
3. **[登记未修] GridFS 幂等为 check-then-put，非原子**：并发双 save 同 (name, sha) 可双双 miss 各 put 一份（files 无 (filename, metadata.sha256) 唯一索引）。当前 eval 场景为单写者串行（各脚本互斥锁文件已隔离），风险为潜伏级；修复需在 `edu_agent` 上建唯一索引或改 put-后二次查询自愈，涉及生产集合 DDL，超出本批文件域，留给真实窗口执行。
4. **[登记未修] 降级两写的分裂脑语义**：mongo 短暂抖动期间写入本地索引的制品，恢复后 `list_artifacts` 只看 GridFS 看不到它们（本地索引不回灌 GridFS）。对「归档审计」语义是洞，但回灌需后台补偿任务，M-2 方案未要求，登记为已知边界（README docstring 已写明降级行为）。
5. **[登记未修] 本地索引 append-only 无并发锁**：多进程同时降级写 `_index.jsonl` 可交错损坏单行（读侧已容忍：warning 跳过坏行）；制品字节文件本身原子替换不受影响。同 3，单写者前提下潜伏。

## 7. 批判承接核对

- `critique-backlog-tracker.md`（`../.ai-hub/plans/tasks/plans/`）全文检索 `R-M2|artifact_store|M-2`：**0 条承接项**。
- `test-reports/` 各 critique 报告中出现的 "artifact"（如 `critique-task39-perf-completion-report.md`）均指 Redis 侧 `app/ai/artifact.py`，与本任务 `app/common/artifact_store.py` 无关。
- 前任 WIP 内遗留的 2 个 skip 已由 a23ab48 承接解除（根因：module 级 fixture 清库回落生产库 + 中断残留脏库），本次实证其修复有效（18/18 含原 skip 两项）。

## 8. 资产消费证据（R-M2 资产被真实消费）

- 真实 eval 主流程消费：`[artifact] backend=mongo aid=6aad53271dc7c6afc8f9f7a7`（§4.1，非 dry-run、非单测，32 query 端到端）。
- GridFS 收口后存量恰为 2 件真实制品（均为本次实证产生）：
  - `eval/runs/rm2_artifact_close.json`（27293B, aid=6aad53271dc7c6afc8f9f7a7）
  - `eval/r03/id_map_git_snapshot.json`（1866921B, aid=6aad53d67f087644e32b3571）
- git 侧零新增大文件：本轮实证产物全部落在 gitignored 的 `scripts/eval/data/` 或 GridFS 本体，M-2「git 只留 <1MB 摘要」目标达成。

## 9. 红线自查

- 只触碰归属文件：`app/common/artifact_store.py`、`tests/test_artifact_store.py`、4 个 eval 脚本（WIP 已含，本轮零改动）、本报告。未触碰 kg/**、analytics/**、check-demo.mjs、deploy.mjs、public/**、tests/ 其他文件及其他未提交改动。
- `scripts/eval/rm2.lock` 已于 commit 前删除（沿用手续）。
