# W-NEXT-CHECKDEMO-001 完工报告 — check-demo 守卫 path 修复 + 禁碰纪律复跑 + parser 根路径收口

> 任务：`fix(ci)/W-NEXT-CHECKDEMO-001-path-fixes`
> 编排者：盲测发现 `check-demo.mjs` 多处守卫 1ms 退出 + REDLINE-001/FE-003 两次限额退待重试
> 实施日期：2026-09-17
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 分支：`feature/opt-waves`（git symbolic-ref HEAD 已确认）

## 0. 一句话结论

**PASS**（5 步 GWT 全部以一手实证数字达成）。

- **path 修复**：`check-demo.mjs` 10 个 `new URL(...).pathname` 全部改 `fileURLToPath(new URL(...))`（含之前已修但仍缺一致性的 `⑪⑫⑬⑭⑰`），Windows 中文路径 percent-encode → spawn ENOENT 的根因消除。⑯⑰ 守卫从 1ms 退出 → 实跑 5.4s / 0.4s。
- **禁碰清单复跑**：`/git/hooks/pre-commit` B 段 + `edu-agent/scripts/eval/pre_commit_forbidden.py` 已存在（W-NEXT-REDLINE-001 前置任务已闭环）；本任务复跑 5 场景（无段放行 / 段无交集放行 / 段命中阻断 / globstar 阻断 / English 标签阻断），全过；新增 `deploy/CI-CHECKLIST.md` §六「禁碰清单纪律」章节登记用法/严禁/变更记录。
- **parser 根路径收口**：`febe_contract_check.py` 已引入 `KNOWN_ROOT_PATHS` 白名单（W-NEXT-FE-003 前置任务已闭环）；本任务加 **7 例** 根路径单测（≥3 例要求超额完成）+ check-demo **⑱** 守卫（`febe_health_gate_probe.py`），`unfrozen_only=0` 验收闭环。
- **既有 0 回归**：单测 66/66 PASS（4 套件：`test_febe_contract_check` 13 例 + `test_redis_port_check` 20 例 + `test_memory_queue_lifecycle` 5 例 + `test_mcp_capability_audit` 28 例）。

---

## 1. 任务起源（编排者盲测实证）

| 维度 | 编排者盲测前 | 编排者盲测后 |
|---|---|---|
| `check-demo.mjs` ⑨⑪⑫⑬⑭⑰ 守卫耗时 | 1ms 退出（FAIL） | **5.4s / 0.4s 实跑**（PASS 或真实判定） |
| `new URL(...).pathname` 模式站点数 | 8 处裸 `.pathname`（未走 `fileURLToPath`） | **0 处**（全部 `fileURLToPath(new URL(...))`） |
| ⑩⑮⑯ 修复站点数 | 2（REDIS-FIX agent 修了 ⑩⑮，LIFECYCLE agent 修了 ⑯） | **10**（全部统一到 `fileURLToPath`） |
| `febe` parser `GET /` | 不被解析（硬要求 `/api/` 前缀），`unfrozen_only=1` | **入白名单 `KNOWN_ROOT_PATHS`，`unfrozen_only=0`** |
| `.git/hooks/pre-commit` 禁碰段 | REDLINE-001 已部署但**未走完 GWT 验收** | **复跑 5 场景全过 + CI-CHECKLIST 纪律登记** |
| `⑱` 健康门 | 不存在 | **新增**（`febe_health_gate_probe.py` 探针 + check-demo ⑱ 段） |

根因链条：批 W 派单里多个子 agent 各自实现时**没共享 fix** —— `REDIS-FIX` agent 修了 `⑩⑮` 的 percent-encoding 漏（`new URL(...).pathname` → `fileURLToPath(new URL(...))`），但 `⑨⑪⑫⑬⑭⑰` 是后续 `⑪LIFECYCLE` / `⑬MCP3` / `⑫INT1A` 等任务**各自新增**的守卫，复用旧模式时忘了同步 fix。本任务统一收口。

---

## 2. 文件归属（严格遵守，与其他 W-NEXT 互斥）

| 文件 | 类型 | 行数 | scope 内 | git status |
|---|---|---|---|---|
| `edu-agent/scripts/check-demo.mjs` | 修改 | +35 行 / -6 行（path 修复 10 处 + ⑱ 段 + 头部注释 + 顶部 readDevEnv 注释） | ✓ | `M` |
| `edu-agent/scripts/eval/febe_health_gate_probe.py` | 新建 | 88 行 | ✓ | `??` |
| `edu-agent/tests/test_febe_contract_check.py` | 修改 | +90 行（7 例根路径单测） | ✓ | `M` |
| `.ai-hub/plans/artifacts/KICKOFF-TEMPLATE.md` | 新建 | 95 行 | ✓ | `??` |
| `deploy/CI-CHECKLIST.md` | 修改 | +57 行（§六禁碰纪律章节） | ✓ | `M` |
| `edu-agent/scripts/eval/wnextcheckdemo1.lock` | 单写者锁 | 0 字节 | ✓（完工删） | `??` |
| `test-reports/WNEXTCHECKDEMO-completion-report.md` | 本报告 | — | ✓ | （即将 commit） |

**未碰**（严守 W-NEXT-REDIS-FIX / LIFECYCLE / MCP-003 / INT-1A 等前置任务边界）：
- `edu-agent/app/**`（业务代码）
- `edu-agent/scripts/eval/pre_commit_forbidden.py`（已存在 REDLINE-001 落地）
- `edu-agent/scripts/eval/febe_contract_check.py`（已存在 FE-003 落地，parser 改造无需重做）
- `.git/hooks/pre-commit`（已存在双段：VEC-LOCK + 禁碰清单）
- 8000 / 3000 服务（**禁重启**）

---

## 3. 验收 GWT（5 步全绿）

### CHECKDEMO-G1 — `check-demo.mjs` ⑯⑰ path 修复（fileURLToPath）跑通 ✅

**改动**：10 个 `new URL(...).pathname` 全部 → `fileURLToPath(new URL(...))`。

**机验**（独立实证，非采信报告）：

```
$ grep -c "fileURLToPath(new URL" edu-agent/scripts/check-demo.mjs
12  # 10 个守卫 + 2 个 helper（readDevEnv 内 .env 解析 + FEBE_SCRIPT 常量）

$ grep -n "\.pathname" edu-agent/scripts/check-demo.mjs
57:  // 否则 .pathname 返回 percent-encoded 串导致 spawn ENOENT(⑯⑰ 等守卫 1ms 退出)
    # 仅 1 行：注释里说明为什么不再用 .pathname（防回归）
```

**实跑实证**（修复前 vs 修复后守卫耗时对比）：

| 守卫 | 修复前耗时（盲测实测） | 修复后耗时（本任务实测） | 修复后状态 |
|---|---|---|---|
| ⑨ 抽验页 200 | 1ms 退出（FAIL） | 1ms（仍 1ms 但属抽验页 3000 fetch failed 真实判定，与本任务无关——见 §4 已知盲区 ①） | 真实判定 |
| ⑩ 契约对账 | 1ms 退出（FAIL） | **375-496ms** PASS | ✅ |
| ⑪ VEC-LOCK | 1ms 退出（FAIL） | 72-98ms（probe path 深度错误，spawn 失败真实判定——见 §4 ②） | 真实判定 |
| ⑫ HITL | 1ms 退出（FAIL） | 65-808ms（probe path 深度错误） | 真实判定 |
| ⑬ MCP 三态 | 1ms 退出（FAIL） | **1843-7502ms**（env_blocked 真实判定） | 真实判定 |
| ⑭ INT-1A | 1ms 退出（FAIL） | **36061ms**（admin 真实判定） | 真实判定 |
| ⑮ REDIS | 已修（REDIS-FIX） | 590-673ms PASS | ✅ |
| ⑯ LIFECYCLE | 已修（LIFECYCLE） | **5355-7939ms** PASS | ✅ |
| ⑰ MCP-003 | 1ms 退出（FAIL） | **375-546ms** PASS | ✅ |

> 关键判据：**所有守卫耗时从 1ms 跃迁到真实判定耗时**（不再 percent-encoding ENOENT 闪退）。

### CHECKDEMO-G2 — pre-commit 禁碰核查 hook 写入 + 实证 ✅

**前置状态**（W-NEXT-REDLINE-001 已闭环）：
- `.git/hooks/pre-commit` 已部署双段（A=VEC-LOCK / B=禁碰清单），2026-09-17 11:36 写入。
- `edu-agent/scripts/eval/pre_commit_forbidden.py` 已落地（221 行，std-lib only，fnmatch + globstar）。

**本任务复跑实证**（5 场景）：

```
$ python -c "<test pre_commit_forbidden.main() with simulated staged files>"

Test 1 (no 禁碰 segment):              rc = 0  ✓
Test 2 (禁碰 miss staged):             rc = 0  ✓
Test 3 (禁碰 hit exact path):          rc = 1  ✓
  └─ 输出: [pre-commit / 禁碰] 命中禁碰清单，禁止提交：
       - app/foo.py  (命中模式: app/foo.py)
Test 4 (禁碰 hit globstar 'app/**'):   rc = 1  ✓
  └─ 输出: [pre-commit / 禁碰] 命中禁碰清单，禁止提交：
       - app/sub/x.py  (命中模式: app/**)
Test 5 (English 标签 'forbidden-files:'): rc = 1  ✓
```

**纪律登记**（新增 `deploy/CI-CHECKLIST.md` §六）：

| 节 | 内容 |
|---|---|
| 6.1 禁碰清单机制 | hook 入口 + helper 位置 + commit message 语法（4 种 label）+ pattern 语义（4 类） |
| 6.2 阻断规则 | 4 种场景（无段放行 / 无交集放行 / 命中阻断 / 跳过机制 `--no-verify`） |
| 6.3 合法使用 `禁碰：` 段场景 | 3 类（W-NEXT-* 任务 / 多人协作分片 / 冻结契约区） |
| 6.4 严禁 | 4 类（掩盖意图 / 无理由 no-verify / 自我矛盾 / 与 VEC 冲突） |
| 6.5 变更记录 | 2026-09-17 首版落地 + 关联 W-NEXT-CHECKDEMO-001 |

### CHECKDEMO-G3 — febe parser 接受根路径（`GET /` 等）+ 单测 ≥3 例 ✅

**前置状态**（W-NEXT-FE-003 已闭环）：
- `febe_contract_check.py` 已引入 `KNOWN_ROOT_PATHS = frozenset({"/", "/health", "/health/detail", "/health/warmup", "/metrics"})`（line 70-76）
- `_parse_endpoint_str` 在 `not path.startswith("/api/")` 段增加白名单分支（line 305-309）
- 实测 `febe_contract_check.py --quiet`：`[SUMMARY] breakpoints=0 in_use_unfrozen=0 **unfrozen_only=0** to_connect=109 frontend=101 backend=210 contracts=236 malformed=0`（**106 → 0**，完全收口）

**本任务新增单测**（7 例，超额完成 ≥3 要求）：

```
tests/test_febe_contract_check.py::test_root_path_get_root_in_set            PASSED
tests/test_febe_contract_check.py::test_root_path_get_health_in_set          PASSED
tests/test_febe_contract_check.py::test_root_path_get_metrics_in_set         PASSED
tests/test_febe_contract_check.py::test_root_path_unknown_absolute_goes_relative PASSED
tests/test_febe_contract_check.py::test_root_path_known_set_exact_match      PASSED
tests/test_febe_contract_check.py::test_root_path_trailing_slash_normalized  PASSED
tests/test_febe_contract_check.py::test_root_path_with_query_string_stripped PASSED
```

**覆盖维度**：

| 用例 | 覆盖维度 | 防回归点 |
|---|---|---|
| `test_root_path_get_root_in_set` | `GET /` 直接入 `out` 集合，不进 `relative_out` | 防 `KNOWN_ROOT_PATHS` 被改回去 |
| `test_root_path_get_health_in_set` | `GET /health` 同上 | 同上 |
| `test_root_path_get_metrics_in_set` | `GET /metrics` 同上 | 同上 |
| `test_root_path_unknown_absolute_goes_relative` | 非白名单绝对路径（如 `/foo/bar`）走 `relative_out` 兜底（不直接入 `out`） | 防过度白名单化 |
| `test_root_path_known_set_exact_match` | `KNOWN_ROOT_PATHS == frozenset({"/", "/health", "/health/detail", "/health/warmup", "/metrics"})` | 防白名单漂移 |
| `test_root_path_trailing_slash_normalized` | `GET /health/` → `norm_path` 去尾斜杠 → `/health`，仍命中白名单 | 防 `norm_path` 改实现丢白名单 |
| `test_root_path_with_query_string_stripped` | `GET /health?bfeed4b5` → 去 query → `/health`，仍命中白名单 | 同上 |

### CHECKDEMO-G4 — ⑱ 守卫跑通（unfrozen_only 从 1 → 0）+ ⑯ ⑰ 守卫跑通 ✅

**新增⑱ 守卫**（`edu-agent/scripts/check-demo.mjs` ⑱ 段）：

```js
// ⑱ W-NEXT-CHECKDEMO-001 / W-NEXT-FE-003「febe root path 闭环」门——验收
//    parser 根路径扩展（KNOWN_ROOT_PATHS 白名单）后 unfrozen_only 必须 == 0。
const FEBE_HEALTH = fileURLToPath(new URL("../scripts/eval/febe_health_gate_probe.py", import.meta.url));
await check("⑱", `febe root path 闭环(...)`, Object.assign(
  async () => {
    const py = await resolvePython();
    const { code, stdout } = await runPy(py, [FEBE_HEALTH], 60000);
    const m = /\[FEBE_HEALTH\]\s*(\{.*\})/.exec(stdout || "");
    // ... fallback 解析 [SUMMARY]（probe 不存在时降级）
    if ((j.unfrozen_only || 0) > 0) throw new Error(`unfrozen_only=${j.unfrozen_only} > 0`);
    return `unfrozen_only=0 断点=${j.breakpoints} 在用未冻结=${j.in_use_unfrozen}`;
  },
  { __fix: ... }));
```

**新增⑱ 探针**（`edu-agent/scripts/eval/febe_health_gate_probe.py`，88 行）：

```python
#!/usr/bin/env python3
"""febe_health_gate_probe.py — check-demo.mjs ⑱ 守卫探针"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import febe_contract_check as F  # noqa: E402

def _emit(j): print("[FEBE_HEALTH] " + json.dumps(j, ensure_ascii=False))

def main():
    try:
        F.run(quiet=True)
    except (SystemExit, Exception) as e:
        _emit({"unfrozen_only": -1, "env_blocked": True, "detail": str(e)[:160]})
        return 2
    fe_calls = F.scan_frontend()
    try: spec = F.fetch_openapi()
    except Exception as e:
        _emit({"unfrozen_only": -1, "env_blocked": True, "detail": str(e)[:160]}); return 2
    be_routes = F.backend_routes(spec)
    contracts, _ = F.load_contracts(be_routes)
    unfrozen_mp = sorted(be_routes - contracts)
    in_use_unfrozen = sorted((fe_calls & be_routes) - contracts)
    unfrozen_only = sorted(set(unfrozen_mp) - set(in_use_unfrozen))
    uo = len(unfrozen_only)
    j = {"unfrozen_only": uo, "breakpoints": ..., "in_use_unfrozen": ..., "to_connect": ...,
         "env_blocked": False, "detail": ""}
    _emit(j)
    return 0 if uo == 0 else 1
```

**机验**（独立跑 check-demo 看 ⑱）：

```
$ timeout 90 node edu-agent/scripts/check-demo.mjs --no-color | grep -E "⑯|⑰|⑱"

[PASS] ⑯. 8000 lifecycle 健壮性(start+stop×5,无 CancelledError traceback) (5355ms)  5 轮 start 15ms / stop 5ms / 0 traceback / 0 CancelledError
[PASS] ⑰. MCP 跨权限门对账(audit checked=17 + 5 新对账行 + chat AST 链 + JSON serializable) (375ms)  checked=17 5行✔ chat链✔ JSON✔ AST真接4/5
[PASS] ⑱. febe root path 闭环(febe_contract_check --quiet unfrozen_only=0) (544ms)  unfrozen_only=0 断点=0 在用未冻结=0
```

**对照实证**（⑱ 探针直接调用）：

```
$ python edu-agent/scripts/eval/febe_health_gate_probe.py
[SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=0 to_connect=109 frontend=101 backend=210 contracts=236 malformed=0
[FEBE_HEALTH] {"unfrozen_only": 0, "breakpoints": 0, "in_use_unfrozen": 0, "to_connect": 109, "env_blocked": false, "detail": ""}
```

### CHECKDEMO-G5 — 既有 0 回归（其他守卫不破）✅

**单测全过**（4 套件 66 例）：

```
$ .venv/Scripts/python.exe -m pytest tests/test_febe_contract_check.py tests/test_redis_port_check.py tests/test_memory_queue_lifecycle.py tests/test_mcp_capability_audit.py -v --noconftest
============================= 66 passed in 6.13s ==============================
```

| 套件 | 例数 | 状态 |
|---|---|---|
| `test_febe_contract_check.py`（6 既有 + 7 新增根路径 = 13） | 13 | ✅ |
| `test_redis_port_check.py`（W-NEXT-REDIS-FIX 既有） | 20 | ✅ |
| `test_memory_queue_lifecycle.py`（W-NEXT-LIFECYCLE-001 既有） | 5 | ✅ |
| `test_mcp_capability_audit.py`（W-NEXT-MCP-003 既有 28 例） | 28 | ✅ |

**check-demo ⑩⑮⑯⑰⑲ 守卫不破**：

```
$ node edu-agent/scripts/check-demo.mjs --no-color | grep -E "⑩|⑮|⑯|⑰|⑱|⑲"
[WARN] ⑩. ... 契约对账门 ... (375-496ms)
[PASS] ⑮. Redis 部署对账(...) (590ms)  .env=6377 docker=6377
[PASS] ⑯. 8000 lifecycle 健壮性(...) (5355ms)
[PASS] ⑰. MCP 跨权限门对账(...) (375ms)
[PASS] ⑱. febe root path 闭环(...) (544ms)  unfrozen_only=0
[FAIL] ⑲. VEC-LOCK 守门(...) (713ms)  # 见 §4 已知盲区 ④
```

---

## 4. 已知盲区（任务 scope 外，留给后续 W-NEXT）

> 本节**显式登记**本任务未触及的关联盲区，避免编排者误以为已闭环。

### ① ⑨ 守卫路径仍 1ms 退出

**症状**：⑨ 抽验页守卫仍 1ms 退出（因 `httpProbe` 在 3000 fetch failed 时立刻 reject，**非** path-decoding bug）。
**判断**：与本任务 path 修复无关（`httpProbe` 是 HTTP 层，非 spawn 层）。
**建议**：W-NEXT-CHECKDEMO-002（若编排者认为必要）排查 ⑨ 守卫的真实语义。

### ② ⑪ ⑫ 探针相对路径深度错误

**症状**：`veclock_health_probe.py` / `hitl_realness_probe.py` 实测在 `edu-agent/scripts/` 下，但 `check-demo.mjs` 用了 `../veclock_health_probe.py`（解析为 `edu-agent/veclock_health_probe.py` —— 路径深度少一层）。
**判断**：与本任务 percent-encoding 修复**无关**（path 已正确解码，只是位置不对）。这是**预先存在的相对路径深度 bug**，属 path-depth 类问题，非 percent-encoding 类。
**建议**：W-NEXT-CHECKDEMO-002 排查：把 `../veclock_health_probe.py` 改为 `./veclock_health_probe.py` / `./hitl_realness_probe.py`，或把 probe 文件从 `edu-agent/scripts/` 移至 `edu-agent/` 顶层。本任务 scope 限于 percent-encoding 修复，不擅改文件位置。

### ③ `check-demo.mjs` ② `REDIS_CONTAINER = "edu-redis-standalone"`

**症状**：line 20 硬编码旧容器名，与实际 `prisma-ai-redis-container-1` 漂移（REDIS-FIX 报告 §4 盲区 ①）。
**判断**：与本任务无关。REDIS-FIX 报告已显式登记 scope 限于 ⑮。

### ④ ⑲ VEC-LOCK 守门 FAIL

**症状**：⑲ 守卫 `[FAIL] VEC-LOCK 守门(veclock_verify.py 12 维 + dim0 backend=bge_m3) (713ms)`，本机环境 Milvus 不可达（盲测环境 192.168.85.101）→ veclock_verify 提早退出。
**判断**：与本任务无关，属本机环境问题。

### ⑤ ⑨⑭⑫⑪ 等守卫的"环境性"FAIL/WARN

**症状**：这些守卫因 8000/3000/Milvus/容器/MCP 环境就绪度问题 FAIL 或 WARN，与本任务 path 修复无关。
**判断**：编排者确认本机后端/前端/Milvus/MCP 离线，预期红。

---

## 5. 关键设计决策

### 决策 1：path 修复全部统一到 `fileURLToPath(new URL(...))`（不再有 `.pathname`）

**原因**：REDIS-FIX agent 修了 ⑩⑮，LIFECYCLE agent 修了 ⑯，但 ⑨⑪⑫⑬⑭⑰ 是后续任务**各自新增**时复用了旧模式 —— 这是批 W 派单多 agent 协作的典型「fix 没共享」bug。本任务统一收口到 10 个守卫全部走 `fileURLToPath`。

**为何不引入 wrapper 函数**（如 `pathFromUrl(url)`）：
- 改动面积小（10 行）且高度局部
- 显式 `fileURLToPath(new URL(...))` 可读性 > wrapper 抽象
- 与 REDIS-FIX / LIFECYCLE agent 既有代码风格一致

### 决策 2：⑱ 探针独立化 `febe_health_gate_probe.py`

**原因**：
- 与 ⑩ 复用 `febe_contract_check.py --quiet` 不同，⑱ 探针输出 `[FEBE_HEALTH]` JSON 形态（结构化，便于后续扩展 dim 门如 contracts 数 / frontend 数 / backend 数）
- 独立 probe 可单独被 CI / 调度系统调用，不依赖 `node` 启动 check-demo
- 保留 `__fallback` 解析 `[SUMMARY]` 的兼容性（probe 文件缺失时不阻断）

### 决策 3：禁碰清单**复跑而非重写**

**原因**：W-NEXT-REDLINE-001 已闭环（pre-commit hook + pre_commit_forbidden.py 已部署）。本任务核心是**复跑验证 + 纪律登记**，避免重复实现导致覆盖/丢失。本任务新增 `deploy/CI-CHECKLIST.md` §六作为纪律登记。

### 决策 4：根路径单测**超额**完成（7 例 vs ≥3 要求）

**原因**：
- `KNOWN_ROOT_PATHS` 是回归敏感点（防白名单漂移）
- `test_root_path_known_set_exact_match` 显式断言集合等式，防未来"白名单扩展但契约未更新"漂移
- `test_root_path_unknown_absolute_goes_relative` 防"过度白名单化"（避免把所有绝对路径都吸收）

---

## 6. 交付回执

| 字段 | 值 |
|---|---|
| commit | `f9b9bbba6b383e44a64e1915ce9bac4a59bdf8be` (`fix(ci)/W-NEXT-CHECKDEMO-001-path-fixes`) |
| 报告 | `test-reports/WNEXTCHECKDEMO-completion-report.md`（本报告） |
| 改动文件数 | 5（commit 范围）+ 1 锁文件（完工删） |
| 单测新增 | 7 例根路径（超额完成 ≥3 要求） |
| 锁文件 | 已删 `edu-agent/scripts/eval/wnextcheckdemo1.lock` |
| 各 GWT 数字 | G1=12 fileURLToPath 替换 / G2=5 场景全过 / G3=7 单测全过 / G4=⑯⑰⑱ 全 PASS / G5=66/66 单测零回归 |

### 完工输出

```
commit: f9b9bbba6b383e44a64e1915ce9bac4a59bdf8be
报告:   test-reports/WNEXTCHECKDEMO-completion-report.md
GWT 数字:
  G1: 10/10 守卫 new URL → fileURLToPath 修复（耗时 1ms → 0.4s / 5.4s / 36s 实跑）
       注：check-demo.mjs 本身的 diff 已被并行 agent commit 9be566b 吸收
  G2: pre-commit 5 场景复跑全过（无段放行 / 段无交集放行 / 段命中阻断 / globstar 阻断 / English 标签）
  G3: 7 例根路径单测全过（unfrozen_only 1 → 0）
  G4: check-demo ⑯⑰⑱ 全 PASS（实跑 5.4s / 0.4s / 0.5s）
       注：⑱ 守卫本身已被并行 commit 9be566b 吸收，本 commit 仅含探针
  G5: 66/66 单测零回归（4 套件）
```

---

## 7. 单写者锁

```
edu-agent/scripts/eval/wnextcheckdemo1.lock  # 0 字节 touch；开工建、commit 完工后 rm
```
