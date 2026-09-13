# H 加固批完成报告（HARDening-completion）

> 阶段：C 阶段加固批（独立加固 agent）
> 日期：2026-09-13（commit 时间戳 2026-09-13 17:44 +0800）
> 来源：Mimosa 安全扫描登记（`.opencode/plans/critique-backlog-tracker.md` 末尾「登记待办(硬ening 批次)」①②，2026-09-12 扫描 237H+25L）
> 守则遵守：禁 DB 直写（未写库，判题 INSERT 走既有 `execute_write` 只读/写业务路径，行为不变）；契约响应形状零改动；未用 Playwright；未重启任何在跑服务（验证用 8010 临时实例，用完即关）；每项独立 commit。

---

## 交付索引

| 任务 | Commit | 改动文件 | pytest | 回滚开关 |
|---|---|---|---|---|
| H-1 coding exec 子进程隔离 | `b661ea2` | `edu-agent/app/interactive/coding/service.py`、`edu-agent/app/config.py`、`edu-agent/tests/test_hard1_exec_isolate.py`（新增）、`.env.example` | **14 passed**（5.0s） | `CODING_EXEC_SUBPROCESS`（默认开） |
| H-2 checkpoint pickle HMAC 签名 | `a54fcdf` | `edu-agent/app/ai/checkpoint_redis.py`、`edu-agent/tests/test_hard2_checkpoint_hmac.py`（新增） | **7 passed**（0.8s）+ 回归 task24/26/39 **48 passed / 1 skipped** | `CHECKPOINT_SIGN`（默认开） |
| 报告 + tracker 登记 | 本 commit | 本报告 + tracker | — | — |

> 说明：两个任务的 4 个配置开关（`CODING_EXEC_SUBPROCESS` / `CHECKPOINT_SIGN` / `CHECKPOINT_HMAC_KEY`）同属 `app/config.py` 一个新增配置段，随 H-1 commit `b661ea2` 一并落库（H-2 commit 内 config.py 已无 diff），特此注明。

---

## H-1：coding 判题 exec 进程隔离（HIGH）

### 改动（`app/interactive/coding/service.py`）

- **现状（修复前）**：`_run_mock` Python 分支 `exec(compile(code, "<code>", "exec"), ns)` 在 **后端进程内**直接执行用户提交代码——用户代码可 `import os` 读环境变量、读写文件、起线程做任意事（Mimosa HIGH ①）。
- **修复后**：默认走新增 `_run_python_subprocess()`：
  1. 用户代码写入 `mkdtemp(prefix="edu_judge_")` 下的**随机名**临时文件；
  2. `subprocess.run([sys.executable, "-I", "-c", <判题引导器>, <用户代码文件>], input=stdin, capture_output=True, text=True, timeout=3.0, cwd=tmpdir)`——同 venv 独立 python、`-I` isolated mode（忽略 `PYTHON*` 环境变量、不加用户 site、隔离 sys.path）、stdin 喂参数、stdout 捕获；
  3. `subprocess.TimeoutExpired` → 硬杀返回 RuntimeError（时长约束沿用现状 3s，与 Piston 路径同源）；
  4. `finally` 中 `shutil.rmtree` **临时文件用后即删**；
  5. 父进程只保留 `ast.parse`（纯语法分析、无代码执行）→ CompileError 语义保持；
  6. 判题引导器退出码约定：0=Pass（stdout=函数返回值）、3=RuntimeError（ExecError / No target function / RunError 逐分支对齐旧语义）；
  7. 子进程执行放 `asyncio.to_thread`，不阻塞事件循环。
- **响应契约不变**：仍返回 `(output, error, status)` 三元组；`CompileError` / `RuntimeError` / `PartialFail` 聚合逻辑零改动；`force_status` 测试钩子行为保持；`RunSubmitOut`/`CaseResult` 形状零改动（contracts/*.json 未触碰）。
- **回滚开关**：`CODING_EXEC_SUBPROCESS`（默认开）。置 false → 原进程内 `exec` 路径原样保留（显式标注 noqa S102，仅供应急回滚）。
- **资源限制按平台尽力**：Windows 无 `resource` 模块（RLIMIT_CPU/RLIMIT_AS 不可用），本层以 timeout 硬杀兜底；源码 ponytail 注释已登记"容器级隔离（cgroups/jobs 限额 + 只读 FS + 网络禁用）归 C 全量部署批处理"。

### pytest 实证（tests/test_hard1_exec_isolate.py，14 passed）

```
test_h1_normal_judging[add/3 4→7][reverse/abcde→edcba][fib/7→13]  3 PASSED   正常判题
test_h1_syntax_error_compileerror                                 PASSED     SyntaxError → CompileError 语义保持
test_h1_exec_error_runtimeerror / test_h1_run_error_runtimeerror  PASSED     ExecError/RunError → RuntimeError 语义保持
test_h1_no_target_function                                        PASSED
test_h1_infinite_loop_timeout_kill                                PASSED     死循环 1s timeout 硬杀（TimeoutError 描述）
test_h1_isolation_pid_differs_from_parent                         PASSED     隔离实证（见下）
test_h1_isolation_cannot_read_parent_env_secret                   PASSED
test_h1_temp_files_cleaned_up                                     PASSED     edu_judge_* 临时目录用后即删
test_h1_rollback_switch_inproc_path                               PASSED     开关关闭 → 旧 exec 路径行为保持（含同 pid 语义）
test_h1_force_status_hook_preserved[CompileError/RuntimeError]    2 PASSED   测试钩子保持
============================= 14 passed in 4.98s ==============================
```

### 隔离实证（pid 对比）

- **pytest 层**：用户代码 `import os; def add(a,b): return os.getpid()` 经 `_run_mock` 执行，返回子进程 pid ≠ 测试进程 pid（`test_h1_isolation_pid_differs_from_parent`）；回滚开关关闭时同 pid（旧路径语义对照）。
- **HTTP 层（8010 临时实例，backend PID=14940）**：

```
POST /api/coding/run  {"challenge_code":"PY-SUM-TWO","lang_code":"python",
                       "code_text":"import os\ndef add(a, b):\n    return os.getpid()\n"}
→ code=0, status=Pass, provider=LOCAL_MOCK, results[0].stdout = 8332
→ 判题输出 pid(8332) ≠ 后端进程 pid(14940)：用户代码确在独立子进程执行
POST /api/coding/run  语法错误代码 → status=CompileError, stderr="SyntaxError: invalid syntax line 1"（契约不变）
POST /api/coding/run  raise ValueError("boom") → status=PartialFail, stderr="RunError: ValueError: boom"（聚合语义与旧实现一致）
POST /api/coding/run  正常 add → status=Pass 2/2, provider=LOCAL_MOCK（RunSubmitOut 响应形状零改动）
```

验证后 8010 实例已 `taskkill` 关闭（netstat 复核 `8010 closed`）。

---

## H-2：checkpoint pickle 签名校验（HIGH）

### 改动（`app/ai/checkpoint_redis.py`）

- **现状（修复前）**：`_persist_thread` 把线程快照 `pickle.dumps` 后直写 Redis；`_ensure_loaded` 读时 `pickle.loads(raw)` 直反序列化——Redis 被写入即等于 RCE（恶意 pickle payload）（Mimosa HIGH ②）。
- **修复后（HMAC 签名最小方案）**：
  - **写**：`payload = pickle.dumps({...})` → 信封 `{"v":1, "hmac": hex, "payload": b64(payload)}`（JSON bytes），`hmac = HMAC-SHA256(key, payload)`；key = `CHECKPOINT_HMAC_KEY` env，缺省回退 `JWT_SECRET` 并**首次使用时 WARN**（`_hmac_fallback_warned` 单次防刷屏）；密钥每次读写动态读取（支持测试/灰度运行时切换）。
  - **读**：先 json 解析信封 → `hmac.compare_digest` **恒定时间比较** → 不过/旧无签名裸 pickle/结构异常（v≠1、缺字段、b64 非法）→ **丢弃该快照 + WARN + 走重建路径**（内存从空开始，等价"快照不存在"，不抛 500）。
  - **兼容（一次性影响声明）**：升级部署后，Redis 中存量**无签名**快照按"无签名 = 不可信"全部拒收，相应线程首次 resume 时不再恢复旧中断态、走重建（图从头部重跑）——一次性影响，仅波及升级时刻仍在 Redis TTL 内的 checkpoint 线程，无数据正确性风险（拒收优先于反序列化）。
  - **回滚开关**：`CHECKPOINT_SIGN`（默认开）。置 false → 写回旧裸 pickle、读直接 `pickle.loads`（仅应急；开启期间写的信封在关闭后读会走异常重建路径）。
- **响应契约不变**：saver 对外接口（aput/aput_writes/aget_tuple/alist/asetup）签名与行为零改动，task39 并发锁加固逻辑未触碰；不涉 HTTP 响应。

### pytest 实证（tests/test_hard2_checkpoint_hmac.py，真 Redis 127.0.0.1:6379，7 passed）

```
test_h2_roundtrip_sign_envelope              PASSED   写入→跨实例读出 roundtrip（落盘为信封 JSON；新实例=模拟进程重启恢复成功）
test_h2_tamper_rejected_rebuild[payload]     PASSED   篡改 payload（位翻转）→ 拒收 → 重建（aget_tuple=None，不抛 500）
test_h2_tamper_rejected_rebuild[hmac]        PASSED   篡改 hmac → 同上
test_h2_legacy_unsigned_pickle_rejected      PASSED   旧无签名裸 pickle → 拒收走重建 + WARN 日志实证（一次性影响）
test_h2_hmac_key_fallback_jwt_secret_warn    PASSED   CHECKPOINT_HMAC_KEY 缺省回退 JWT_SECRET + WARN 触发；不同密钥实例互不认签（密钥隔离）
test_h2_sign_off_rollback                    PASSED   开关关闭 → 落盘为裸 pickle、可读回（旧行为）
test_h2_hmac_algorithm_selfcheck             PASSED   独立复算 HMAC-SHA256 与信封 hmac compare_digest 相等（算法自证）
============================== 7 passed in 0.84s ==============================
```

### 回归（签名开启默认态下既有 durable execution 路径）

```
.venv/Scripts/python.exe -m pytest tests/test_contract_task24.py tests/test_contract_task26.py tests/test_contract_task39.py
→ 48 passed, 1 skipped in 24.91s（含 task24 GWT② 真 Redis durable 恢复路径——签名开启后恢复行为不变）
```

---

## 复跑方式

```bash
cd edu-agent
.venv/Scripts/python.exe -m pytest tests/test_hard1_exec_isolate.py -v          # H-1：14 passed
.venv/Scripts/python.exe -m pytest tests/test_hard2_checkpoint_hmac.py -v       # H-2：7 passed（需本机 Redis 6379）
.venv/Scripts/python.exe -m pytest tests/test_contract_task24.py tests/test_contract_task26.py tests/test_contract_task39.py -q   # 回归
```

回滚开关（edu-agent/.env 或环境变量）：

```ini
CODING_EXEC_SUBPROCESS=false   # H-1 回退旧进程内 exec（RCE 面回归，仅应急）
CHECKPOINT_SIGN=false          # H-2 回退旧裸 pickle（RCE 面回归，仅应急）
CHECKPOINT_HMAC_KEY=<独立强随机密钥>   # 生产建议配置；留空回退 JWT_SECRET（WARN）
```

## 遗留登记

- H-1 资源限制：Windows 平台无 `resource` 模块，仅 timeout 硬杀；容器级隔离（cgroups/jobs 限额、只读 FS、网络禁用）→ 归 C 全量部署批处理（源码 ponytail 注释已标注）。
- Mimosa 登记项 ③（4 处 insecure-randomness，LOW，用于抖动/非密钥）：维持"登记不修"不变。
- 一次性影响（H-2）：升级后存量无签名 checkpoint 快照全部拒收走重建（见上），无需数据迁移。
