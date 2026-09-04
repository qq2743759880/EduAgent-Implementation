# Checkpoint 模式批判：断点续跑实现存在 4 个真实缺陷（task06 复核）

> **触发**：task06 验收报告"全部通过"后的严格复核。
> **对象**：`E:\stu\project\stu\edu-data\generate\checkpoint.py` + `main.py` + `layers\base.py` + `layers\layer1~6.py`
> **结论**：正常路径通过 ≠ 生产可用。断电、并发、批中断三个真实场景未覆盖，7 晚方案可能实际变成 14 晚。
> **日期**：2026-08-16 · **状态**：待修复（P0 两项）

---

## 一、验收复核结果（代码级 + 运行级实证）

| 报告声明 | 验证方式 | 结果 |
|---------|---------|------|
| checkpoint.py 断点续跑 | 源码阅读：`is_layer_completed`/`mark_completed`/`mark_failed`/`get_completed_layers` 完整 | ✅ 正常路径成立 |
| 中断后重跑跳过已完成层 | **实跑** `python -m generate.main --profile smoke --layers 1..1` → `Already completed: [1..7]` + `[SKIP]` + `0.0s` | ✅ 正常路径成立 |
| 幂等（两次执行一致） | checkpoint 持久化 + SKIP 分支 | ✅ 正常路径成立 |
| layers 语法 `1..7`/`1..3,5..7`/`1,2,3` | **实跑** `parse_layers_arg` 三种语法 | ✅ |
| batch_size=5000 (full) / 2000 (smoke) | `config.py` L158/L132 | ✅ |
| 7 晚方案文档 | `docs/night-batch-guide.md` 存在，含 7 晚计划表 | ✅ |
| layer1 新增 account/username/status | `layer1.py` L321/322/331 | ✅ |
| 各层 super().__init__ | layer1-6 各 1 次 | ✅ |

**但以下边界场景全部未验证——这是本批判的核心。**

---

## 二、缺陷 1：无原子写 —— 断电会损坏 checkpoint（🔴 致命）

```python
def _write(data):
    _ensure_dir()
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:  # ← 先截断再写
        json.dump(data, f, ensure_ascii=False, indent=2)
```

**问题**：`open(..., "w")` 先截断文件再写入。进程在 `json.dump` 中途崩溃/断电 → checkpoint.json 是半截 JSON → 下次 `_read()` 的 `except (json.JSONDecodeError, OSError)` 返回空 dict → **全部已完成层状态丢失**，从 layer 1 重跑。

**影响**：night-batch-guide 的 7 晚方案中，任何一晚断电都导致该晚及之后进度归零。

**修复**（1 小时）：
```python
def _write(data):
    _ensure_dir()
    tmp = CHECKPOINT_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CHECKPOINT_FILE)  # 原子替换，Windows/POSIX 均支持
```

---

## 三、缺陷 2：粒度是"层"，不是"批次" —— 批中断恢复仍全量重跑（🟠 严重）

**报告声称**"per-layer and per-batch completion state"——**代码里只有 per-layer**：
- `mark_layer_completed(layer, row_counts)` 仅层粒度
- `layer1.py` 的 `run()` 主循环 `for index in range(1, total + 1)`（full profile 约 10 万行）
- checkpoint.py 全文 **无 batch 概念**（grep 确认）

**场景**：layer 1 跑到第 8 万行中断 → checkpoint 该层 `completed: False` → 重跑**从头生成 10 万行**。7 晚方案中"第 1 晚跑 layer 1"若中途断电，第 2 晚从头再来。

**修复**（2 小时）：层内按批次写进度：
```python
# checkpoint.py 新增
def mark_batch_progress(layer, batch_index, rows_done):
    data = _read()
    data["layers"][str(layer)] = {
        "completed": False,
        "batch_index": batch_index,
        "rows_done": rows_done,
        "updated_at": time.time(),
    }
    _write(data)
```
生成器内每 N 批调用一次，`run()` 从 `batch_index` 续跑。

---

## 四、缺陷 3：失败路径未重排 —— init_db 失败时状态误判（🟠 严重）

```python
if args.reset:
    reset_checkpoint()
init_db()                          # ← MySQL 挂掉在此抛异常
with generation_profile(args.profile):
    init_checkpoint(args.profile)  # ← 永远不会执行到
    ...
```

**问题**：`init_db()` 在 `init_checkpoint()` **之前**。若 MySQL 不可用 → `init_db()` 抛异常 → checkpoint 从未初始化。用户以为"断了旧状态"，实际 **full 档的旧 checkpoint 文件还在**，下次启动会误 SKIP 已完成层。

**修复**（半小时）：把 `init_checkpoint` 提到 `init_db` 之前，或在 `init_db` 失败时显式打印 checkpoint 现状提示。

---

## 五、缺陷 4：并发双跑互相覆盖（🔴 致命但被忽略）

两个终端同时跑（或 cron 与手动并发）：`_read()` → `_write()` 是 read-modify-write 非原子。
A 读 → B 读 → A 写 → B 写 = **B 覆盖 A 的完成记录**。night-batch-guide 建议每晚跑一层，但白天手动调试同层就会撞车。

**业界答案**：文件锁（`msvcrt.locking` / `fcntl.flock`）或换 SQLite（WAL 事务）。

---

## 六、架构级问题：为什么不用 SQLite？

Dagster/Airflow/Prefect 的 pipeline 状态全部用**数据库**而非 JSON 文件：

| 维度 | 当前 JSON 实现 | SQLite/DB | 差距 |
|------|---------------|-----------|------|
| 原子性 | ❌ 无 | ✅ 事务 | 致命 |
| 粒度 | 层 | 任务/批 | 严重 |
| 并发安全 | ❌ 无 | ✅ 行级锁 | 致命 |
| 幂等重入 | ✅ 层级 | ✅ 幂等任务 | 部分 |
| 可恢复性 | 层级 | 批级 | 严重 |
| 失败可观测 | ✅ error 记录 | ✅ retry/日志 | OK |

本项目已有 `db.py` 连 MySQL——**checkpoint 状态放 MySQL 一张表，零新依赖，健壮一个数量级**。SQLite 是轻量备选。

---

## 七、修复优先级

| 优先级 | 项 | 工作量 | 消除缺陷 |
|--------|----|--------|---------|
| P0 | 原子写（os.replace） | 1 小时 | 缺陷 1（断电丢状态） |
| P0 | 批级 checkpoint（batch_index 续跑） | 2 小时 | 缺陷 2（批中断全量重跑） |
| P1 | 并发锁或切 SQLite | 半天 | 缺陷 4（双跑覆盖） |
| P1 | init_checkpoint 顺序重排 | 半小时 | 缺陷 3（失败路径误判） |

**验收标准修正**：task06 的"全部通过"仅覆盖 happy path。补测清单：
1. 模拟中断（kill -9 / Ctrl+C）→ 断电场景 → checkpoint.json 内容完整性
2. 双终端并发跑同层 → 完成记录不丢
3. 批中断 → 层内断点续跑行数正确
4. MySQL 不可用时启动 → checkpoint 状态不被误判

---

## 八、对"最优解"的判断

**当前实现不是最优解**，但方向正确（状态持久化 + SKIP 幂等 + 语法解析都是对的）。与业界基线（Airflow/Dagster 的 DB 状态 + 任务粒度）相比，差距集中在**持久化介质（JSON vs DB）**和**粒度（层 vs 批）**两点。在数据量增长到 full 档（数十万行）后，这两点会从"瑕疵"变成"事故"。

**最小改动路径**：先修 P0 两项（3 小时），可立即消除断电丢状态 + 批中断全量重跑两个最高频风险。SQLite 迁移作为 P1 可选，视后续规模决定。
