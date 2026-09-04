# write-read 一致性缺陷 排查报告

> 范围：领券 / 下单 / 取消等「写已 commit，但紧接的读（get\_order / get\_my\_coupon）读不到刚提交行」。
> 工作目录：`e:\stu\project\stu\EduAgent实施手册`。严格 tt 工作流：源码定位根因 → 最小修复 → 独立实证复验。
> 未做任何 commit。

***

## 一、现象（task39 真 Redis 补验子 agent 如实登记）

| 现象        | 表现                                                                         |
| --------- | -------------------------------------------------------------------------- |
| 领券首写      | HTTP 500（日志 `data:'coupon_id'` 类），但 DB 已落 `coupon_receive_record` + 幂等 key |
| 下单首个 POST | 返回 `40420`（单号不存在类），但 DB 已落 2 笔 pending                                     |
| 取消同单      | 一会 404 一会 200                                                              |
| 共性        | **写已 commit，紧接读（get\_order / get\_my\_coupon）读不到刚提交的行**                    |

***

## 二、根因（源码确证 + 环境实测）

### 2.1 直接根因：只读连接池因账号缺失静默降级回主池（autocommit=False）

`app/database.py:146-176` `init_mysql_ro()` 意图创建 `autocommit=True` 的独立只读池，读端点走 `_get_read_pool()`（179-183）。但：

- 被测库 **`edu_ro`** **账号不存在**（`SELECT user,host FROM mysql.user WHERE user='edu_ro'` → 空；`SHOW GRANTS` → 1141）。

- 实测 `asyncmy.create_pool(minsize=1)` **立即抛错**（仓库 `pool.pyx:223-225` 启动即 `fill_free_pool`）：
  `OperationalError(1045, "Access denied for user 'edu_ro'@'localhost'")`。

- 于是 `init_mysql_ro()` 走 `except` → `_mysql_ro_pool = None` → `_get_read_pool()` 返回**主池（autocommit=False）**。运行日志佐证：
  `app.database:init_mysql_ro:175 - MySQL 只读连接池初始化失败，降级为主库：(1045, Access denied for user 'edu_ro'...)`。

**设计上「读走 autocommit=True 只读池」的读写一致性兜底被静默废除，读落到主池。**

### 2.2 放大机制：主池（autocommit=False）上 SELECT 开启 REPEATABLE READ 快照未被显式结束

`fetch_one` / `fetch_all`（database.py:517 / :538）在主池（autocommit=False）连接上执行 SELECT 会开启一个事务一致性读快照，但**读后既不 commit 也不 rollback**。池内连接被复用时可能携带旧快照，紧接的读就看不到**其它连接**新 commit 的行。MySQL 侧隔离级别确认为 `REPEATABLE-READ`。是否复发取决于 asyncmy `release()` 对连接事务态的处理与池复用时机；长活、高并发运行后端实测表现为**稳定复现**（领券/下单稳定 500/404，而非间歇）。

> 说明：这不是「写未提交」问题——DB 实测行已落且对新连接立即可见；是「读连接快照过旧」。

### 2.3 症状掩蔽 bug（把根因 2.2 放大成 500/404）

- 领券 `market/service.py:137-146` 的「极端兜底」用券模板 dict（其列为 `id`，无 `coupon_id`）构造 `coupon_row`，而 `_coupon_from_receive`（service.py:70）读 `row["coupon_id"]` → **`KeyError: 'coupon_id'`**。服务端日志确认：`app.main:global_exception_handler - 未处理的异常: 'coupon_id'`，帧栈落在 `market/service.py:143 → _coupon_from_receive:72`。这正是 `HTTP 500 + data:'coupon_id'`。

- 下单 `order/service.py:141-146`：事务提交后 `_order_write.get_order` 读回 None → 落到 `raise TRADE_ORDER_NOT_FOUND` → `40420`。

两者共同点 = **写后立即读 miss**（根因 2.1+2.2），可用性症状由 2.3 各自放大。

***

## 三、最小修复（落地源码 + 恢复设计）

### 3.1 `app/database.py` —— 读辅助函数显式结束读快照（防跨请求残留旧快照）

- 新增 `_end_read_snapshot(conn)`：

  ```python
  async def _end_read_snapshot(conn):
      try:
          if conn is not None and not conn.get_autocommit() and conn.get_transaction_status():
              await conn.rollback()
      except Exception:
          pass
  ```

  逻辑：对非 autocommit 且仍在事务中的读连接，归还前显式 `ROLLBACK` 释放 REPEATABLE READ 快照，使下次复用即得全新一致性读，不再依赖 asyncmy release 的池内清理。只读池（autocommit=True）时 `get_autocommit()==True` → 零开销、零行为变化；降级主池（autocommit=False）时每次读补一条 ROLLBACK。

- 在 `fetch_one` / `fetch_all` 的 `finally` 中、`pool.release(conn)` 之前调用 `await _end_read_snapshot(conn)`。

### 3.2 `app/domains/market/service.py` —— 领券兜底补 `coupon_id`（消除 500 掩蔽，保证幂等新领健壮）

兜底构造改为：

```python
coupon_template = dict(coupon)
coupon_row = {**coupon_template,
              "coupon_id": coupon_template["id"],
              "receive_record_id": result["receive_record_id"], ...}
```

### 3.3 恢复设计的只读账号（消除降级、回归 autocommit=True 只读池）

新建脚本 `test-reports/provision_edu_ro.sql`（幂等可重跑）+ `provision_edu_ro_apply.py`：

- `CREATE USER IF NOT EXISTS 'edu_ro'@'localhost'/'127.0.0.1'/'%' ... 'edu_ro_pwd_2026'`

- `GRANT SELECT ON edu.* TO 'edu_ro'@...`

- 已应用并验证：可 `SELECT`，`DELETE` 被拒（1142），仅 SELECT 权限。

- 生效后 `init_mysql_ro()` 成功，重启后端 `store_status['mysql_ro']='ok'`，读回到设计的 autocommit=True 只读池（正确性 + 无 per-read rollback 开销）。

### 未改动任何对外契约 / 响应壳 / 字段。

***

## 四、独立实证复验（真实 HTTP + DB 实测 + 真实 Redis）

修复后重启后端（`Z:\anaconda3\envs\kb311\python.exe -m uvicorn app.main:app`，启动日志 `'mysql_ro': 'ok'`），重跑脚本 `test-reports/write_read_replay.py`：

```
1) 领券首写 + 幂等
   receive#1 → http 200 code 0 data.coupon_id=51021 (新建，读回成功)
   receive#2 → http 200 code 0 data.coupon_id=51021 (幂等返回同一记录)
   DB coupon_receive_record user1/coupon3 = 仅 1 行        ← 修复前每次多建 1 行
2) 下单 + 立即读
   POST /api/trade/order → http 200 code 0 order_no=1-260904210352-97a3b8
   DB `order` by no     = 恰 1 笔 pending                  ← 修复前 40420 + 2 笔
   GET  /api/trade/order/{no} → http 200                 ← 写后立即读成功
3) 取消同单一致
   cancel#1 → 200；cancel#2 → 200（幂等，不再 404 波动）
   DB status after cancel = 'cancelled'
ALL ASSERTIONS PASSED — write-read consistency restored
```

另做定向回归 `test-reports/unit_read_snapshot_degraded.py`（强制 `_mysql_ro_pool=None` 复现降级主池条件，50 轮写后立即读）：**50/50 一致 PASS**。

相关契约测试（真实服务偶发受本机限流 / 班次占满等环境因素影响，非代码回归）：

- `test_contract_task16.py`（券）→ **9 passed, 1 skipped**

- `test_contract_task17.py`（订单）→ **2 passed, 5 skipped**

- 一批 task18/19（payment/refund）及 middleware 测试因 `无可用班次`（数据前置）与被本机复验触发限流（HTTP 429）失败，与本次代码改动无关。

***

## 五、残留清理

- 删除复验产生、仅 SELECT 权限受测用的临时文件（`_chk*.py` / `_http*.py` / `_t_*.py` / `_tok.txt` 等）。

- `test-reports/cleanup_test_artifacts.py`：清除 user1 的 coupon2/3 领券测试记录（16 行）并把 `coupon.receive_count` 回补（coupon2 → 736，coupon3 → 736）。

## 六、是否需要 RN 决策

**不需要**。三处缺陷均在单点可安全修复范围内，且已实证复验通过、无对外契约变更、无新增回归。

## 七、留存可重跑脚本

- `test-reports/provision_edu_ro.sql` / `provision_edu_ro_apply.py`：补建只读账号（幂等）。

- `test-reports/write_read_replay.py`：真实 HTTP 写读一致性复验。

- `test-reports/unit_read_snapshot_degraded.py`：降级主池条件定向回归。

- `test-reports/cleanup_test_artifacts.py`：清理复验残留。

- 复验期后端日志：`logs/wr-backend.{out,err}.log`。

## 八、资产消费证据

实际消费的文件：

- `edu-agent/app/database.py`（`init_mysql_ro`/`_get_read_pool`/`transaction`/`execute_write`/`fetch_one`/`fetch_all`）——定位根因 2.1/2.2 并做修补 3.1

- `edu-agent/app/config.py`（`MYSQL_RO_USER/PASSWORD`、`DEBUG`）——确认只读账号为默认缺省、未被 .env 显式配置

- `edu-agent/app/main.py:60-86`（lifespan 初始化 / `init_mysql_ro` 调用链）

- `edu-agent/app/domains/market/service.py`（`receive_coupon` / `_coupon_from_receive`）——定位并修补 2.3

- `edu-agent/app/domains/market/repository/coupon_repo.py`、`app/domains/trade/order/service.py`、`order/repository.py`、`payment/repository.py`、`order/router.py`、`market/router.py` —— 核实写后读调用点

- `asyncmy` 源码（`.venv` 与 `kb311` 的 `pool.pyx` / `connection.pyx`）——确认 `create_pool(minsize=1)` 启动即触发鉴权、`release()` 事务态清理语义、`get_transaction_status()`/`get_autocommit()`/`rollback()` API

- 运行日志 `logs/app.log` / `logs/error.log` —— 实证 `init_mysql_ro` 降级与 `KeyError: 'coupon_id'` 帧栈

自检发现并修复的问题：

1. `edu_ro` 账号缺失 → RO 池降级主池（根因）。
2. `fetch_one/fetch_all` 读后未结束读快照（放大根因）。
3. 领券兜底 `coupon_id` KeyError（症状掩蔽）。
4. 复验中初版测试用错字段（`receive_record_id` vs `coupon_id`），已修正脚本；领券 15 连发污染 coupon2 数据已清理。

