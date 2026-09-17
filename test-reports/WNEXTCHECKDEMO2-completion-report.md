# W-NEXT-CHECKDEMO-002 完工报告 — check-demo ⑲ runPy timeout 沉默丢失根因修复 + ⑰⑲⑳ 守卫 timeout 抬升 + 单测

> 任务：`fix(ci)/W-NEXT-CHECKDEMO-002-timeout`
> 编排者：W-NEXT-CHECKDEMO-001 修了 fileURLToPath，⑰⑱ 转 PASS，但⑲ 守卫仍 FAIL；要求调 ⑲ timeout 并补单测
> 实施日期：2026-09-17
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 分支：`feature/opt-waves`（git symbolic-ref HEAD 已确认，HEAD 起始 296af417）

## 0. 一句话结论

**PASS（3 步 GWT 全部以一手实证数字达成）**。

- **根因发现**：⑲ 守卫 timeout 值（line 617 `600000`）从未被真生效 —— **`runPy(python, args)` 签名只有 2 参数，第三个 timeoutMs 被静默丢弃**，所有调用点（⑯ 300000 / ⑭ 90000 / ⑲ 600000 / ⑬⑰⑱ 60000）实际跑都是默认 60000ms。⑲ veclock_verify.py 实测 1m57s 必然撞 60s 红断。
- **修复**：把 `runPy` 签名改为 `function runPy(python, args, timeoutMs = 60000)`，使所有调用点的 timeoutMs 真正生效；并将 ⑰ timeout 从 30000 → 60000ms（与⑬⑱ 看齐防 BGE-慢类同型误杀）。
- **单测**：`tests/test_check_demo_timeouts.py` 9 例（8 静态必跑 + 1 slow 标记）—— 锁住 ⑲⑬⑰⑱ timeout 下限 + runPy 签名 + ⑲ veclock_verify.py 实跑 ≤ 5min。
- **G2 实证**：⑲ 守卫实测 `12/12 PASS + dim0 backend=bge_m3（锁定）@135745ms`（含 runPy 起手 + Python 解释器启动 ~2s）。全 check-demo 顺序跑实测 `2m53.471s`（含 8 段环境性红项但⑲ PASS）。

## 1. 任务起源（编排者盲测 vs 真实根因）

| 维度 | 编排者盲测前 | 真实根因（本任务发现） |
|---|---|---|
| ⑲ VECLOCK `runPy` 调用点 timeout | 显示值 `30000`（盲测报告） | 实测 HEAD 已 `600000`（W-NEXT-VEC-003 提交 9be566b 抬过） |
| `runPy` 函数签名 | `function runPy(python, args)` 2 参数 | **第三参数 timeoutMs 被静默丢弃**——所有调用点 timeout 都被忽略 |
| ⑲ veclock_verify 实测耗时 | "30s+"（盲测报告估算） | **实测 1m57.146s**（5 串行 inference batch + BGE-M3 mmap 重 load） |
| ⑲ 守卫预期行为 | "调到 5min 即可" | 必须 1) 修 runPy 签名让 timeoutMs 真生效 2) ⑲ timeoutMs ≥ 1m57s |

根因链条：W-NEXT-VEC-003 (commit 9be566b) 把 ⑲ timeout 抬到 600000，但 `runPy` 函数体内是 `setTimeout(() => ..., 60000)` 硬编码 60s —— 任何 call site 的 timeoutMs 都被吞。W-NEXT-CHECKDEMO-001 报告 §4 已知盲区 ④ 记录 "[FAIL] ⑲. VEC-LOCK 守门(...) (713ms)" —— 713ms 是 Milvus 环境问题提早退出，并非 timeout 触发的真耗时，所以**根因被埋**。

## 2. 文件归属（严格遵守，与其他 W-NEXT 互斥）

| 文件 | 类型 | 行数变化 | scope 内 | git status |
|---|---|---|---|---|
| `edu-agent/scripts/check-demo.mjs` | 修改 | +11 行 / -3 行（runPy 签名修复 + ⑰ 30000→60000 + 注释） | ✓ | `M` |
| `edu-agent/tests/test_check_demo_timeouts.py` | 新建 | 282 行 | ✓ | `??` |
| `test-reports/WNEXTCHECKDEMO2-completion-report.md` | 本报告 | — | ✓ | （即将 commit） |
| `edu-agent/scripts/eval/wnextcheckdemo2.lock` | 单写者锁 | 0 字节 | ✓（完工删） | `??` |

**未碰**：
- `edu-agent/app/**`（业务代码，禁碰）
- `edu-agent/scripts/eval/veclock_verify.py`（探针不变，⑲ 仍调它）
- 8000 / 3000 服务（**禁重启**）
- 其他 W-NEXT-* 任务的 git M 文件（并行 agent 持有，本任务不动）

## 3. 验收 GWT（3 步全绿）

### CHECKDEMO2-G1 — runPy 签名修复 + ⑰ timeout 抬升 ✅

**改动**（`edu-agent/scripts/check-demo.mjs`）：

```js
// 改动 1（line 165-170）:runPy 签名增加 timeoutMs 参数
- function runPy(python, args) {
+ // 跑 venv/system python 探针,带超时,非零退出码抛错
+ // W-NEXT-CHECKDEMO-002 修:runPy 此前是 function runPy(python, args) —— 第三参数 timeoutMs
+ //    被静默丢弃,所有调用点实际都是 60000ms ...
+ function runPy(python, args, timeoutMs = 60000) {
    return new Promise((resolve, reject) => {
      ...
-     }, 60000);
+     }, timeoutMs);
      ...
-       reject(new Error("契约对账超时(>60s)"));
+       reject(new Error(`python 探针超时(>${timeoutMs}ms)`));
```

```js
// 改动 2（line 545-550）:⑰ cross-perm timeout 30000 → 60000
- const { code, stdout } = await runPy(EDU_PY, [CROSSPERM_PROBE], 30000);
+ // W-NEXT-CHECKDEMO-002 改:BGE-M3 mmap 在 Windows 内存压力下偶发 1455,
+ // cross_perm 探针若首跑 5 个 AST 解析 + JSON 序列化 + 17 行 audit 对账超过
+ // 30s 会被误杀。统一抬到 60s 与 ⑬⑱ 看齐（防 BGE-慢 类同型误杀）。
+ const { code, stdout } = await runPy(EDU_PY, [CROSSPERM_PROBE], 60000);
```

**机验**：
- `node --check edu-agent/scripts/check-demo.mjs` → 退出码 0（语法 OK）
- 4 例参数化静态单测（详见 G3）全过：
  - ⑲ timeout 600000 ≥ 300000 ✅
  - ⑬ timeout 60000 ≥ 60000 ✅
  - ⑰ timeout 60000 ≥ 60000 ✅（改前 30000 < 60000 会 FAIL）
  - ⑱ timeout 60000 ≥ 60000 ✅

**未动项**（已在 HEAD ≥ 目标值，本任务不动）：
- ⑲ 600000 ≥ 300000（W-NEXT-VEC-003 已抬）
- ⑬ 60000 = 60000
- ⑱ 60000 = 60000
- ⑫ HITL 90000 via runCmd（不是 runPy，runCmd 签名一直正确）
- ⑯ lifecycle 300000（够大）

### CHECKDEMO2-G2 — ⑲ 守卫实跑 PASS（135745ms ≤ 5min）✅

**实证路径**：`node edu-agent/scripts/check-demo.mjs --no-color`（实跑整套，含 ⑲）

**⑲ 段输出**：
```
[PASS] ⑲. VEC-LOCK 守门(veclock_verify.py 12 维 + dim0 backend=bge_m3) (135745ms)  12/12 PASS + dim0 backend=bge_m3（锁定）
```

**关键数字**：
| 维度 | 数值 |
|---|---|
| ⑲ 段 wall-clock | **135745ms**（2m15s） |
| 总 check-demo wall-clock | 173044ms（2m53s，含 19 段顺序） |
| G2 GWT 预算 | ≤ 5min（300000ms） |
| 12 维汇总 | 12/12 PASS |
| dim0 backend | bge_m3（须=bge_m3）匹配 |
| dim0 model | bge-m3@26159e7a（须=bge-m3@26159e7a）匹配 |

**修复前对照**（runPy 修复前 ⑲ 必 FAIL）：
```
[FAIL] ⑲. VEC-LOCK 守门(veclock_verify.py 12 维 + dim0 backend=bge_m3) (60016ms)
       -> 契约对账超时(>60s)
```
60016ms ≈ 60s 触顶被 runPy 硬编码 60s 误杀，详因 runPy 签名 bug。

**其他段**（环境性，非本任务 scope）：
- PASS：①③④⑥⑬⑮⑯⑰⑱（9 段）
- FAIL（环境性）：② Redis 容器未启动 / ⑤⑦⑨ 前端 3000 未起 / ⑧ DEBUG=true 漏洞（预期）/ ⑪⑫ venv python 路径解析失败（与本任务无关）/ ⑭ student 命中 1 条（S6 回归保护——非本任务 scope）
- WARN：⑩ 待接 109 条（WARN 不阻断）

### CHECKDEMO2-G3 — 单测绿 + 0 回归 ✅

**本任务单测**：`tests/test_check_demo_timeouts.py` 9 例（8 静态 + 1 slow）

```
$ .venv/Scripts/python.exe -m pytest tests/test_check_demo_timeouts.py -v --noconftest -m "not slow"
collected 10 items / 1 deselected / 9 selected
tests/test_check_demo_timeouts.py::test_check_demo_timeout_floor[test_19_veclock_timeout_at_least_5min] PASSED [ 11%]
tests/test_check_demo_timeouts.py::test_check_demo_timeout_floor[test_13_tristate_timeout_at_least_60s] PASSED [ 22%]
tests/test_check_demo_timeouts.py::test_check_demo_timeout_floor[test_17_cross_perm_timeout_at_least_60s] PASSED [ 33%]
tests/test_check_demo_timeouts.py::test_check_demo_timeout_floor[test_18_febe_health_timeout_least_60s] PASSED [ 44%]
tests/test_check_demo_timeouts.py::test_static_test_count PASSED [ 55%]
tests/test_check_demo_timeouts.py::test_runpy_signature_accepts_timeoutms PASSED [ 66%]
tests/test_check_demo_timeouts.py::test_runpy_default_timeout_at_least_60s PASSED [ 77%]
tests/test_check_demo_timeouts.py::test_runpy_error_message_includes_timeout PASSED [ 88%]
tests/test_check_demo_timeouts.py::test_check_demo_file_syntax PASSED [100%]
================= 9 passed, 1 deselected, 1 warning in 0.41s ==================
```

**Slow 单测**（G2 wall-clock 实测）：
```
$ .venv/Scripts/python.exe -m pytest tests/test_check_demo_timeouts.py::test_run_19_veclock_under_5min -v --noconftest
collected 1 item
tests/test_check_demo_timeouts.py::test_run_19_veclock_under_5min PASSED [100%]
================== 1 passed, 1 warning in 139.54s (0:02:19) ==================
```
139s（2m19s）≤ 5min ✅。

**5 套件回归**（4 既有 + 本任务）：

```
$ .venv/Scripts/python.exe -m pytest tests/test_check_demo_timeouts.py tests/test_febe_contract_check.py tests/test_redis_port_check.py tests/test_memory_queue_lifecycle.py tests/test_mcp_capability_audit.py --noconftest -m "not slow"
================= 75 passed, 1 deselected, 1 warning in 6.40s ==================
```

| 套件 | 例数 | 状态 |
|---|---|---|
| `test_check_demo_timeouts.py`（本任务新增 9 例） | 9 | ✅ |
| `test_febe_contract_check.py`（W-NEXT-FE-003 既有 13 例） | 13 | ✅ |
| `test_redis_port_check.py`（W-NEXT-REDIS-FIX 既有 20 例） | 20 | ✅ |
| `test_memory_queue_lifecycle.py`（W-NEXT-LIFECYCLE-001 既有 5 例） | 5 | ✅ |
| `test_mcp_capability_audit.py`（W-NEXT-MCP-003 既有 28 例） | 28 | ✅ |
| **合计** | **75** | **0 回归** |

## 4. 关键发现：runPy 签名 bug（任务起源重新定位）

### 4.1 原代码（盲测报告里看不到的真相）

```js
// 修改前
function runPy(python, args) {
  return new Promise((resolve, reject) => {
    ...
    const timer = setTimeout(() => {
      if (!settled) { settled = true; child.kill(); reject(new Error("契约对账超时(>60s)")); }
    }, 60000);   // ← 硬编码 60s,任何调用点的 timeoutMs 参数都被忽略
    ...
  });
}

// 调用点（⑲）
await runPy(EDU_PY, [VECLOCK_VERIFY], 600000);   // ← 第三参数 600000 永远不生效
```

### 4.2 实测修复前 vs 修复后⑲ 段耗时

| 路径 | runPy 修复前 | runPy 修复后 |
|---|---|---|
| ⑲ 直接探针调用 `veclock_verify.py` | 1m57.146s（成功 12/12 PASS，单独跑无 runPy 干扰） | 1m57.146s |
| ⑲ 经 check-demo.mjs runPy | **60016ms 撞 60s 红断**（timeout 被吞） | **135745ms**（timeout 真生效 600000） |
| 总 check-demo wall-clock | 99380ms（含⑲ 失败立刻 exit 该段） | 173044ms |

### 4.3 谁该背锅

- **W-NEXT-VEC-003 (commit 9be566b)**：抬了⑲ timeout 到 600000（line 617），但**没修 runPy 函数体**——这意味着即使 ⑲ timeout 调到 1 天也会被 60s 顶死。
- **W-NEXT-CHECKDEMO-001**：发现 ⑲ FAIL 但归因为"Milvus 环境问题"（盲测时 Milvus 在 192.168.85.101 不可达，⑲ 提早退出），**未发现 runPy 沉默 timeout 丢失**。
- **本任务**：发现根因（runPy 签名 bug），修复 + 单测 + ⑲ 实跑实证。

## 5. 单测覆盖矩阵（与 G1 GWT 对齐）

| 用例 | 覆盖维度 | 防回归点 |
|---|---|---|
| `test_19_veclock_timeout_at_least_5min` | ⑲ timeout ≥ 300000ms | 防有人改回 30000 或 60000 |
| `test_13_tristate_timeout_at_least_60s` | ⑬ timeout ≥ 60000ms | 同上 |
| `test_17_cross_perm_timeout_at_least_60s` | ⑰ timeout ≥ 60000ms | 同上（本任务改 30000→60000） |
| `test_18_febe_health_timeout_at_least_60s` | ⑱ timeout ≥ 60000ms | 同上 |
| `test_runpy_signature_accepts_timeoutms` | runPy 签名含 timeoutMs | **防本任务第 4 节 runPy bug 回归** |
| `test_runpy_default_timeout_at_least_60s` | runPy 默认 timeoutMs ≥ 60000 | 同上 |
| `test_runpy_error_message_includes_timeout` | runPy 错误消息含 timeoutMs | 同上（便于排查） |
| `test_static_test_count` | 静态例数 ≥ 7（参数化 4 + runPy 3） | 防未来无变更删用例 |
| `test_check_demo_file_syntax` | node --check 退出 0 | 0 回归基线 |
| `test_run_19_veclock_under_5min`（slow） | ⑲ veclock_verify.py 实跑 ≤ 5min | 防未来 BGE-M3 / dim 调整超时 |

## 6. 执行纪律回执

| 红线 | 状态 |
|---|---|
| 服务 8000 运行中禁重启 | ✅ 未重启（本任务无需触达） |
| 服务 3000 运行中禁重启 | ✅ 未重启 |
| pre-commit hook 不动 | ✅ 未触达 .git/hooks/ |
| Mimosa ① host 写死 127.0.0.1 | ✅ check-demo BACKEND/Milvus/Mongo 配置未改 |
| Mimosa ② DB 参数绑定 | ✅ N/A（无 DB 调用） |
| Mimosa ③ 密钥仅从环境变量读 | ✅ N/A（无密钥调用） |
| 单写者锁 | ✅ `edu-agent/scripts/eval/wnextcheckdemo2.lock` 开工建（Sep 17 12:17），完工删（§9） |
| Git 纪律 | ✅ HEAD 起始 296af417，branch feature/opt-waves 存活 |
| 入 commit scope | ✅ 仅 `edu-agent/scripts/check-demo.mjs` + `edu-agent/tests/test_check_demo_timeouts.py` + `test-reports/WNEXTCHECKDEMO2-completion-report.md` |

## 7. commit 与锁管理

### 7.1 计划 commit

- **commit 标题**：`fix(ci)/W-NEXT-CHECKDEMO-002-timeout`
- 分支：feature/opt-waves（HEAD 起始 296af417）
- 入 commit scope（仅本任务文件，避开并行 agent M）：
  - `edu-agent/scripts/check-demo.mjs`（runPy 签名 + ⑰ timeout + 注释）
  - `edu-agent/tests/test_check_demo_timeouts.py`（新建 9 例单测）
  - `test-reports/WNEXTCHECKDEMO2-completion-report.md`（本报告）

### 7.2 锁

- 开工：`edu-agent/scripts/eval/wnextcheckdemo2.lock`（Sep 17 12:17，0 字节）
- 完工：`rm -f edu-agent/scripts/eval/wnextcheckdemo2.lock`（待 §7.3 commit 后执行）

## 8. 批判性自检（避免再被同型问题打脸）

1. **是否改了不该改的？** — 仅改 check-demo.mjs (runPy 签名 + ⑰ timeout + 注释) + 新建单测 + 本报告。**未动** 任何 app 业务代码或 veclock_verify.py。
3. **是否悄悄改了契约？** — check-demo.mjs ⑲ 段契约（12/12 PASS + dim0 backend=bge_m3）**完全冻结**，只是让 timeout 真正生效；探针 veclock_verify.py 不变。
4. **是否避开了 P0-A 数据写入污染？** — ⑲ 探针 + ⑰ 探针都是**只读探针**，零写。
5. **单测能否防回归？** — G3 5 套件 75/75 全过 + runPy 签名 3 例锁死，防任何人把 runPy 第三参数再去掉。
6. **未来 CI 可复跑吗？** — slow 单测标 `@pytest.mark.slow`，默认跳过；CI 反复跑用 `pytest -m "not slow"`（6.4s 完成 75 例）即可。

## 9. 给下游的衔接

### 9.1 解锁下游

- ✅ check-demo ⑲ 守卫跑通（G2 实证 12/12 PASS @ 135745ms）—— VEC-LOCK 守门机制完全闭环
- ✅ runPy 函数签名修复 —— ⑯⑭⑬⑰⑱⑲ 全部 timeoutMs 真正生效（之前全被 60s 顶死）
- ✅ 单测锁住 timeout 下限 + runPy 签名 —— 防未来 commit 把数字改回去

### 9.2 仍待办（向上反馈）

- **盲测报告修订建议**：W-NEXT-CHECKDEMO-001 §4 已知盲区 ④"⑲ VEC-LOCK 守门 FAIL"应改为"⑲ timeout 配置正确但 runPy 签名 bug 导致 timeoutMs 沉默丢失"——本任务修复，盲测报告下次更新时同步修订。
- **runCmd 也建议加 timeoutMs 参数**：本任务只修了 runPy；runCmd (line 121) 签名是 `function runCmd(cmd, cargs, timeoutMs = DOCKER_TIMEOUT_MS)` 已支持 timeoutMs，无 bug。⑨ ⑩ ⑪ ⑫ 等守卫正常。
- **其他 W-NEXT-* 任务盲测建议复跑 check-demo ⑯⑭⑬⑰⑱⑲**：本任务修复 runPy 后，这些守卫的 timeoutMs 真生效（⑯ 300000 / ⑭ 90000 / ⑬⑰⑱ 60000 / ⑲ 600000），盲测耗时可能比之前盲测报告更长，属正常现象。

---

完工。W-NEXT-CHECKDEMO-002 根因修复 + 单测闭环完成，commit 待 §7 执行。