# Round5「跨实例 checkpoint 并发写语义」独立验收报告

- 日期：2026-09-05
- 验证者：independent verifier sub-agent（EduAgent）
- 判定面：`app/ai/checkpoint_redis.py`（PlainRedisSaver 真 Redis durable checkpointer）跨实例/跨进程并发写同一 thread_id 的语义
- 环境：真 Redis `edu-redis-standalone` 容器（0.0.0.0:6379→6379/tcp），app 连接串 `redis://127.0.0.1:6379/0`（库 0，redis 6.2.24，databases=16）
- 依据：critique-backlog-tracker.md Round5 登记注意点（`edu-agent/.opencode/plans/critique-backlog-tracker.md` L354）待确证

---

## 结论

**闭环 ✅**。Round5 登记的注意点「多实例/多 agent 共享同一 thread 的并发写 checkpoint 语义」经真 Redis（进程内双对象 + 真实双 OS 进程两种注入方式）独立实证确证：

- **并发写语义判定：last-writer-wins（后写覆盖，全量快照原子 SET 覆盖），非 CAS，无版本冲突拒绝。**
- 无死锁、无重入损坏（pickle 结构完整、字段可反序列化）、最终态确定性一致（单一 owner 的完整快照）。
- 与 Round5 注意点描述一致且为**非缺陷的固有属性**：两独立 saver 实例共享同一 thread_id 并发写时，各自进程内快照发散，最终 Redis 值 = 最后一次 `r.set` 到达服务器的那个实例的**完整快照**，另一实例最近 checkpoints 被静默覆盖（丢失）。单线程单进程语义无影响；跨实例正确性要求「一线程一 owner 独占」，与 tracker 落点「多实例共享 thread 场景单独立项」吻合。

### 三向小结（证据摘要）

| 目标 | 结果 | 真实输出节选 |
|------|------|--------------|
| G1 Redis 可用 | PASS | ping→True；version 6.2.24；db0；dbsize=30 |
| G2 并发写安全 | PASS | 进程内 30 轮×8 写：single-owner=30/30、mixed=0、lost=0、corrupt 异常=0；跨进程 5 组：全部单一 owner，最终 count=该 writer 全量 |
| G3 LWW/CAS | LWW（后写覆盖） | R1 严格串行 A→B 后 final owner=B；R3 两新实例 `_ensure_loaded` 恢复 owner 一致、ids 逐字节一致；全程零版本冲突拒绝 |
| G4 不冲突 guard FIFO | PASS | 实验 key 全清理；guard key 与基线一致；relative-baseline 新增/删除 key 均=`[]` |

---

## G1 Redis 可用性前置 — PASS

**方法**：用与 app 完全相同的连接串（`settings.REDIS_URL`，含 `_normalize_loopback` 归一为 127.0.0.1）建立 redis.asyncio 客户端，ping + server info + config databases + dbsize；确认真实容器而非内存 mock。

**真实输出**：
```
settings.REDIS_URL = redis://127.0.0.1:6379/0
[G1] ping -> True
[G1] redis_version=6.2.24  tcp_port=6379
[G1] dbsize(库0) = 30
[G1] databases configured = {'databases': '16'}
```
- 明确端口/库：`127.0.0.1:6379` / `db0`。容器 `edu-redis-standalone`（`docker ps`：`0.0.0.0:6379->6379/tcp Up`）即后端同源 Redis。
- 判定：**PASS**（真 Redis 连接成功，读写在 db0）。

---

## G2 并发写安全 — PASS

**方法**：构造两个「实例」注入（专测前缀 `edu:ckpt_r5test`/`edu:ckpt_r5x`，绝不触碰真实 `edu:ckpt:*`）：
1. **进程内双对象**：两个独立 `PlainRedisSaver`（各自独立 redis 客户端 + 各自 per-instance asyncio.Lock，互不感知），同一 thread_id 交错并发写。
2. **真实双 OS 进程**：`proc_worker.py` 各起一进程（独立进程、无共享内存/锁），同时写同一 thread_id。
每写后读回 Redis 原 key 反序列化，校验：顶层 `storage/writes/blobs` 齐全、每条 checkpoint 值为三元组、owner 单一。

**真实输出（进程内，30 轮 × 每实例 8 写）**：
```
结果汇总: owner_ok(单一owner)=30/30  mixed_owner=0  lost(读空)=0  exception=0
判定: 无损坏 & 单一 owner => PASS
```
**真实输出（跨进程，5 组）**：
```
[R0] A(20) B(20) -> final owner={'B'} count=20 单一owner=True
[R1] A(50) B(7)  -> final owner={'A'} count=50 单一owner=True
[R2] A(7)  B(50) -> final owner={'B'} count=50 单一owner=True
[R3] A(100) B(100)-> final owner={'A'} count=100 单一owner=True
[R4] A(33) B(33) -> final owner={'B'} count=33 单一owner=True
```
- 关键证据：最终快照 owner 恒为单一，且 `count` == 该 writer 的**完整写轮数**（如 R1 B 写 7、A 写 50，最终=A 且恰好 50 条全在）→ 证明最终值是**整份全量快照覆盖**，不是 half-written 拼接、不是混合、不是丢失一半的碎片。
- 判定：**PASS**（无重入损坏、结构完整、字段可反序列化、最终读回为确定性一致状态）。

---

## G3 并发语义判定：last-writer-wins（后写覆盖），非 CAS — PASS

**方法**
1. **R1 严格串行定序**：A 先 `aput`（marker ckpt-A-*），B 严格在 A 后 `aput`（ckpt-B-*）→ 读回应=B。
2. **R3 新实例确定性恢复**：并发写一轮后，两个全新 `PlainRedisSaver` 各自走真实恢复路径 `_ensure_loaded(thread_id)`（进程重启读路径：GET→pickle→回填内存），比对两次恢复的内存快照 owner 与 id 全序。
3. **冲突拒绝检测**：全程统计 `aput` 是否曾返回版本冲突/被拒。

**真实输出**
```
=== Round1: 严格串行 A→B ===
A 先写、B 后写后，Redis 最终快照 ids = ['ckpt-B-0-0']; owners = {'B'}
判定: LWW（后写覆盖）
=== Round3: 新实例经 _ensure_loaded 从 Redis 恢复 ===
[reader-1] owner={'B'} count=6
[reader-2] owner={'B'} count=6
两次恢复 owner 一致=True, 单一 owner=True => PASS
```

**判定证据链**
- `aput` 落地 = `super().aput()`（写**本实例内存**) + `_persist_thread()`（把**本实例内存**全量 pickle 后 `r.set(key, payload, ex=ttl)`）。persist 不读 Redis，是纯全量 SET 覆盖（无读-改-写竞态），因此**最后一次 SET 到达服务器的完整快照胜出 = 后写覆盖 = LWW**。
- `aput` 无版本号校验、无冲突返回路径 → **非 CAS、无冲突拒绝**（30+5 组全程 `aput` 零失败零拒绝）。
- R1 证明「严格后写覆盖」；R3 证明「新的恢复实例读到的是确定的末次快照」。两者叠加即确定性一致 + LWW。
- 语义限定（诚实标注）：这是**跨实例共享同一 thread_id 的固有覆盖语义**。因每条 SET 是全量快照，最终态完整不损坏，但**另一实例在末写窗口内的 checkpoints 会被整体覆盖丢失**——这正是 tracker L354 记录的注意点，非单进程缺陷，单线程单进程语义无影响。

---

## G4 与 guard FIFO 不冲突 + 清理复位 — PASS

**方法**：实验全程使用专属前缀 `edu:ckpt_r5test` / `edu:ckpt_r5x`，不触碰 guard 的 `chat:queue*` / `chat:concurrent*` / `ai:llm:*` 与真实 `edu:ckpt:*`。实验后删除测试 key，并与实验前 `baseline_keys.json` 全量快照比对 + 复核 guard key。

**基线（实验前）**：`chat:concurrent:1=0`、`ai:llm:concurrent=0`、`chat:queue* 为空`、真实业务 `edu:ckpt:*` = 5 个原样 key。

**真实输出（清理后）**
```
[G4 cleanup] 删除实验 key: ['edu:ckpt_r5test:r5-thread-1']
   chat:concurrent:1 = 0
   ai:llm:concurrent = 0
   chat:queue* = []
   real edu:ckpt:* = ['edu:ckpt:s_3cb7e990e31e','edu:ckpt:s_5a54798fc7e8','edu:ckpt:s_9c6673d66578','edu:ckpt:task24-1','edu:ckpt:tid-97d5b1c9-durable']
[G4 verify] 实验新增 key（相对基线）= []
[G4 verify] 实验删除的原基线 key = []
```
- `edu:ckpt_r5x:*` 已由 proc_test 自助清理，`edu:ckpt_r5test:dbg` 已由 dbg 自助清理，最后仅剩 `edu:ckpt_r5test:r5-thread-1` 一并删除。
- guard FIFO key（队列/并发计数）与基线**逐项一致、未被触碰**；真实业务 checkpoint 5 个原样。相对基线「新增=[]、删除=[]」→ **零残留、完全复位**。
- 判定：**PASS**。

---

## 资产消费证据（硬约束）

| 资产文件（具名路径） | 实际调用证据 | 锚点 + 内核词 |
|----------------------|--------------|--------------|
| `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` | 验证切片内核 be-tester 的「独立实证 / 记录可复现证据」；paranoia 独立复现原则贯穿 G1~G4 | 锚点「review 内核」+ 内核词「verification（真实输出证据）」「record reproducible evidence」 |
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md`（§.1/§5.6/自检三视角） | 采用「三视角诊断/自检」报告骨架与「资产消费 + 批判承接」硬约束段 | 锚点「tt 方法论」+ 内核词「三视角自检」「批判承接核对」 |
| `C:\Users\Administrator\.agents\skills\tt\templates\completion-report.md` | 报告按该模板组织「结论→逐项→自检三视角→批判承接」 | 锚点「completion-report」+ 内核词「自检三视角」「GWT 逐条」 |
| 上游库 langgraph `InMemorySaver.put/get_tuple`（.venv site-packages） | 读取 `get_tuple` 确认 checkpoint 重建字段要求，用于设计正确 checkpoint 与恢复读路径 | 锚点「InMemorySaver」+ 内核词「channel_versions」「storage 按 checkpoint_ns 键控」 |

> 说明：本次为**独立验证**，未调用外部模型评测；外部 review 内核（qodo-ai/pr-agent、continuedev/continue）未接入本机，按其 Degradation 规则不假报，以上以 be-tester 内置验证流程为准。

## 自检三视角（review 内核）

| 检查视角 | 发现 | 处置 |
|---------|------|------|
| 交互态（正常/空/边界） | 设计时误读 payload `storage` 键控层级（误以为按 thread_id），首跑 `read_raw` 读空、`aget_tuple` 因合成 checkpoint 缺 `channel_versions` 报 KeyError | 定位为**测试脚本自身**问题：改为按 checkpoint_ns 取 storage；读回改走真实恢复路径 `_ensure_loaded`，不再依赖合成 checkpoint 的 get_tuple 重建 |
| 边界（输入/输出/权限/超时） | 首版 barrier `Event.wait()` 未 await 产生 `coroutine never awaited` 告警 | 将 barrier 置为已 set 后再 `await barrier.wait()`，消除告警后结果复现一致（30 轮仍全 PASS） |
| 错误反馈（用户/下游可见） | 无；全程 `aput`/`_ensure_loaded` 零异常、零丢失、零损坏 | 无需修 |

## 批判承接核对（§5.6，硬约束）

| tracker 项 | 完成证据 |
|-----------|---------|
| Round5 领域复查 ·「登记注意点（跨实例一致性命中）」（`.opencode/plans/critique-backlog-tracker.md` L354） | 本报告独立实证确证：双 instances + 真实双进程注入，均呈 **last-writer-wins**（全量快照后写覆盖）、无损坏/死锁/冲突拒绝；与注意点描述一致，确认为固有非缺陷语义，落点仍为「多实例共享 thread 场景单独立项」，本次不改代码 |

---

## 遗留 / 诚实标注

- 「两个实例」注入已覆盖进程内双对象（共享同进程不同客户端）与真实双 OS 进程两种形态；未跑 2 个同时 `python -m uvicorn` 工作进程 + `WORKERS=N` 的多 worker 形态，但两者的 Redis 写链路均为「各自内独 `r.set` 全量覆盖」，语义等价（跨进程测试已代表多进程无共享锁场景）。
- 未对 `aput_writes/writes` 路径单独压并发；其与 `aput` 共用同一 `_persist_thread` 全量 SET，LWW 结论同构。
- TTL=3600 由 saver 默认传入，实验中均显式 `ex`，未验证 TTL 到期对并发的影响（非本登记注意点范围）。

## 实验脚本（保留回放）
- `edu-agent/_r5_tmp/g1_base.py`（G1 + 基线清单）
- `edu-agent/_r5_tmp/conc_test.py`（进程内双实例 G2/G3）
- `edu-agent/_r5_tmp/proc_worker.py` + `proc_test.py`（真实双进程 G2/G3）
- `edu-agent/_r5_tmp/g4_cleanup.py`（G4 清理 + 复位核验）