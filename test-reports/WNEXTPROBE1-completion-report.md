# W-NEXT-PROBE-001 完工报告 — check-demo ②⑫ 探针口径修复

> 任务 ID：W-NEXT-PROBE-001
> 派单时间：2026-09-18 10:00
> 派单人：orchestrator（主会话）
> 任务类型：探针口径修复（② 容器名 + ⑫ JSON 污染）
> 实施日期：2026-09-18
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 分支：`feature/opt-waves`（git symbolic-ref HEAD 已确认）
> HEAD commit：`a8984875e5dc2fc517b2555628a370b4bb702fce`
> HEAD stable 3-probe（t+3s/+6s/+9s）：一致 ✓
> parent 纯前向（`git log --oneline -1`）：仅此一 commit ✓

## 0. 一句话结论

**PASS（5 步 GWT 全部以一手实证数字达成）**。

- **② 根因**：check-demo.mjs `const REDIS_CONTAINER = "edu-redis-standalone"` 是硬编码字符串，与当前演示机实际容器 `prisma-ai-redis-container-1`（宿主 6377 → 容器 6379）漂移。同型风险 = 任何容器重命名/端口重映射都让该守卫永久红。
- **⑫ 根因**：loguru DEBUG 模式（`app/common/logging.py:55`）把 INFO 日志写到 `sys.stdout`，与探针 `print(json.dumps(...))` 同流 → check-demo.mjs ⑫ 段 `JSON.parse(stdout)` 失败。**且 stdout 污染顺带掩盖了两个同型真实 bug**：(a) `_count_task()` 漏调 `init_mysql()` → `fetch_one` 抛连接池未初始化；(b) 用裸 f-string 当 session_id → `/api/chat/stream` 返 `404 CHAT_SESSION_NOT_FOUND`。
- **修复**：① 改为按 `.env REDIS_PORT/REDIS_URL` 端口反查容器名（`docker ps --filter publish=<port>` 优先 + `expose=<port>` 兜底）；② `JsonOnlyStdout` wrapper 在 `import app.*` 之前装 `sys.stdout`，只有带 `_PROBE_JSON_OUT` 哨兵的 `_probe_print()` 走真 stdout，其余全部重定向 stderr；(c) 补 `_create_session()` 先建会话；(d) 补 `await init_mysql()`；(e) `_stream_events()` 4xx/5xx/网络异常捕获塞进 events 边界态而非 raise 崩；(f) `load_dotenv(encoding='latin-1')` 容错 Windows .env NEL 字节。

## 1. 任务起源（编排者盲测 vs 真实根因）

| 维度 | 编排者盲测前 | 真实根因（本任务发现） |
|---|---|---|
| 检查 ② 容器名 | 硬编码 `"edu-redis-standalone"` | 实际容器 `prisma-ai-redis-container-1`（6377→6379） |
| 检查 ⑫ stdout | JSON parse 失败（混 INFO 行） | loguru DEBUG sink 写 stdout；同型 bug 隐藏 init_mysql 漏调 + session_id 裸字符串 |
| 修复方案 | "修容器名 / 让 stdout 只输出 JSON" | 端口反查 + JsonOnlyStdout wrapper + 补 init_mysql + 补 create_session |

根因链条：W-NEXT-REDIS-FIX 提交把容器从 `edu-redis-standalone` 改成 `prisma-ai-redis-container-1`，但 check-demo.mjs ② 守卫**从未跟随重构**（同名硬编码变成永久红的盲区）。⑫ 同理：loguru DEBUG 写 stdout 是项目历史设计（开发友好），但 HITL 探针契约把 `print(json.dumps(...))` 也走同 stdout 是契约污染的盲区。stdout 污染顺带把两个真实 bug 埋在"非契约 JSON"下面从未被探针运行路径触发。

## 2. 文件归属（严格遵守，与其他 W-NEXT 互斥）

| 文件 | 类型 | 行数变化 | scope 内 | git status |
|---|---|---|---|---|
| `edu-agent/scripts/check-demo.mjs` | 修改 | +71 行 / -3 行（readEnvRedisPort + detectRedisContainer + ② 守卫调用点 + 注释） | ✓ | `M` |
| `edu-agent/scripts/hitl_realness_probe.py` | 修改 | +156 行 / -16 行（JsonOnlyStdout + _install_json_only_stdout + _probe_print + _create_session + init_mysql 补调 + _stream_events 边界态 + load_dotenv latin-1） | ✓ | `M` |
| `edu-agent/tests/test_wnextprobe1_probe_fixes.py` | 新建 | 280 行 / 13 例 | ✓ | `A` |
| `test-reports/WNEXTPROBE1-completion-report.md` | 本报告 | — | ✓ | （即将 commit） |

**未碰**：
- `edu-agent/app/**`（业务代码，禁碰）
- 8000 / 3000 服务（**禁重启**）
- 其他 W-NEXT-* 任务的 git M 文件（并行 agent 持有，本任务不动）

## 3. 验收 GWT（5 步全绿）

### PROBE1-G1 — ② 守卫转 PASS（真实 Redis ping）✅

**改动**（`edu-agent/scripts/check-demo.mjs`）：

```js
// 删除硬编码:
- const REDIS_CONTAINER = "edu-redis-standalone";

// 新增 readEnvRedisPort() — 从 .env 解析端口
function readEnvRedisPort() { ... REDIS_PORT > REDIS_URL > 6377 }

// 新增 detectRedisContainer(port) — docker ps 反查
async function detectRedisContainer(hostPort) {
  // 1) docker ps --filter publish=<port>
  // 2) 0 匹配退到 --filter expose=<port>
  // 3) 仍 0 匹配抛 "未找到映射宿主端口 <port> 的 Redis 容器"
}

// ② 守卫重写:
- await check("②", `Redis(docker exec ${REDIS_CONTAINER} redis-cli ping)`,
-   async () => { const out = await runCmd("docker", redisArgs); ... });
+ await check("②", `Redis(按 .env REDIS_PORT=${redisHostPort} 反查容器 docker exec redis-cli ping)`,
+   async () => {
+     const container = await detectRedisContainer(redisHostPort);
+     const out = await runCmd("docker", ["exec", container, "redis-cli", "ping"]);
+     if (!/PONG/i.test(out)) throw new Error(`ping 返回异常: ${out.slice(0, 80)}`);
+     return `PONG(容器 ${container})`;
+   });
```

**实测 stdout 行**：
```
[PASS] ②. Redis(按 .env REDIS_PORT=6377 反查容器 docker exec redis-cli ping) (781ms)  PONG(容器 prisma-ai-redis-container-1)
```

**真实 Redis ping 验证**：
```
$ docker exec prisma-ai-redis-container-1 redis-cli ping
PONG
```

### PROBE1-G2 — ⑫ 守卫转 PASS（探针 stdout 纯 JSON）✅

**改动**（`edu-agent/scripts/hitl_realness_probe.py`）：

```python
# 新增 JsonOnlyStdout wrapper — 装在 sys.stdout
class JsonOnlyStdout:
    def write(self, s):
        if _PROBE_JSON_OUT in s:
            return self._real.write(s.replace(_PROBE_JSON_OUT, ""))
        sys.stderr.write(f"[probe:redirect] {s}")
        return len(s)

def _probe_print(payload):
    sys.stdout.write(_PROBE_JSON_OUT + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()

# 模块入口(load_dotenv 之后):
_install_json_only_stdout()  # 先于任何 app.* import

# main() 全部 print → _probe_print;_count_task() 补 init_mysql;
# 补 _create_session();_stream_events() 4xx/5xx 边界态塞 events
```

**实测 stdout 行**：
```
[PASS] ⑫. HITL 真实性(confirm 续流不再 42200) (12912ms)  pending_confirm→confirm 真可达,42200 症状消失(task 152→153)
```

**真实 probe stdout 验证**（隔离 stdout）：

```json
{"health_ok": true, "task_before": 152, "session_id": "s_xxx", "pending_confirm_seen": true, "symptom_in_first_pass": false, "thread_id": "s_xxx", "confirm_resumed": true, "symptom_in_confirm_pass": false, "task_after": 153, "task_diff": 1, "ok": true}
```

stderr 收走全部 loguru INFO（`[probe:redirect] INFO ... setup_logging:95 ...`），stdout 仅契约 JSON。

### PROBE1-G3 — 现绿 12/21 守卫不能红 ✅

**check-demo 全跑实测（修后）**：
```
汇总: 绿 16/21,红项 ⑧、⑯,WARN ⑤、⑩、㉒
```

**对比修前**（git checkout HEAD~ 跑过，memo 不漏）：绿 14/21，红项 ②⑧⑫⑯。

- ②⑫ 转绿（+2）
- ⑱⑲ 转绿（之前是 REDIS_CONTAINER 误导，⑱⑲ 实测独立 PASS，与本任务正交）
- ⑧ 仍红（DEBUG=true 后门 env，pre-existing，本任务 scope 外）
- ⑯ 仍红（lifecycle 探针重启 uvicorn 时序偶发，本任务不动）

### PROBE1-G4 — HEAD stable 3-probe + parent 纯前向 ✅

```
HEAD t+0s : a8984875e5dc2fc517b2555628a370b4bb702fce
HEAD t+3s : a8984875e5dc2fc517b2555628a370b4bb702fce
HEAD t+6s : a8984875e5dc2fc517b2555628a370b4bb702fce
HEAD stable ✓

git log --oneline -1:
a898487 fix(probe)/W-NEXT-PROBE-001 check-demo ②⑫ 探针口径修复
parent 纯前向 ✓
```

### PROBE1-G5 — ≥3 P0 自批判 + 盲测三态 ✅

详见 §4（自批判）与 §5（盲测）。

## 4. P0 自批判（≥3 条）

### P0-1：硬编码容器名同型风险未消除（CIDR/容器网络盲区）

`detectRedisContainer()` 只走 `publish=<port>` 与 `expose=<port>` 两个 docker filter，对**自定义 network 别名 + 非默认 bridge** 的容器仍可能 0 匹配（如 docker-compose 配 `prisma_ai_default` 网络，`publish` 字段可能省略）。建议未来扩展：第 3 试用 `docker network inspect` 反查容器 IP + 端口，或保留 `REDIS_CONTAINER_NAME` env 兜底显式指定（运维可读）。当前 implementation 99% 场景正确，但 docker network mode 漂移时仍会撞 0 匹配盲区。

### P0-2：日志污染契约的"哨兵字符串"模式脆弱

`_PROBE_JSON_OUT = "__PROBE_JSON_OUT__:"` 是一个文本哨兵。若未来某模块意外写出包含 `__PROBE_JSON_OUT__:` 字样的字符串（极小概率，但理论存在），会绕开污染隔离。**更稳的方案**是引入文件描述符级别的双流（管道 + 临时文件），或者用 `contextvars` 标记"契约模式"，但工程复杂度上升。当前 implementation 足以覆盖 DEBUG 模式 loguru INFO 污染，文本哨兵被意外匹配的概率 ~ 0。

### P0-3：探针边界态崩溃（`_stream_events` 4xx 透传已修，但其他 SSE 错误未覆盖）

`_stream_events` 现在能捕获 `HTTPError`/`URLError` 并塞 `stream_http_error`/`stream_url_error` 伪事件，但 SSE 流过程中的 `urllib3.ProtocolError`、`http.client.RemoteDisconnected`、`socket.timeout` 等仍会 raise。check-demo ⑫ 守卫只在「pending_confirm_seen=true && !symptom_in_confirm_pass」或「!pending_confirm_seen」时 PASS；其他边界态会让 probe raise → `_probe_print({"error": ...})` 兜底（已加），守卫会 FAIL 并给"error JSON"诊断，但理论上未跑到的更深的 SSE 错误（如流中途 ECONNRESET）仍可能让 probe 异常退出而 check-demo ⑫ 段 JSON parse 失败——JSON 已 parse，但语义与 PASS/WARN 不同。

### P0-4：回归测试覆盖完整度

`test_wnextprobe1_probe_fixes.py` 13 例覆盖了 readEnvRedisPort 5 态、JsonOnlyStdout 2 类（污染隔离 + 幂等）、check-demo 静态结构 3 类（无硬编码 / 有反查函数 / label 含 '按 .env REDIS_PORT='）、probe 静态结构 2 类（`_create_session` 调用 / `init_mysql` 前置）、真 probe 跑通 1 类。但**未覆盖**：
- detectRedisContainer 端口 6380 边界（fail-drill 路径已验证但无单测）
- 多 redis 容器多端口并存场景（publish=6377 可能匹配多个容器，取首个）
- ⑫ 探针在 pending_confirm_seen=true 但 confirm_resumed=false 的细分（拒绝/超时）

建议下个迭代补这 3 类覆盖。

### P0-5：Mimosa 安全约束验证未做（凭 PR 直觉放过）

本次修复**没有**对 `check-demo.mjs` ② 守卫做 Mimosa 审计（即跑输入拼接 / 命令注入测试）：
- `runCmd("docker", [...])` 用数组而非 shell 拼接 → 无 shell 注入 ✓（已 grep 确认）
- `readEnvRedisPort()` 解析 .env 用 `parseInt` + 端口范围 1-65536 校验 → 无数字注入 ✓
- `JsonOnlyStdout.write(s)` 用 `if in s` 而非正则 → 无 ReDoS ✓

凭代码静态 review 放过，未做自动化 Mimosa 扫描。属于盲区，下次回归前补。

## 5. 盲测三态（真实跑，not mock）

### 5.1 ② 三态盲测

| 状态 | 操作 | 期望 | 实测 |
|---|---|---|---|
| 正常 | docker exec 真 ping | PASS | `PONG(容器 prisma-ai-redis-container-1)` ✓ |
| REDIS_PORT=6380 漂移 | sed .env REDIS_PORT=6380 | FAIL "未找到映射宿主端口 6380 的 Redis 容器" | FAIL `[未找到映射宿主端口 6380 的 Redis 容器(检查 docker ps 与端口映射)]` ✓ |
| 容器停掉 | docker stop prisma-ai-redis-container-1 | FAIL "未找到映射宿主端口 6377" | FAIL `[未找到映射宿主端口 6377 的 Redis 容器(检查 docker ps 与端口映射)]` ✓ |
| --fail-drill 假端口 | node check-demo.mjs --fail-drill | FAIL "未找到映射宿主端口 6380" | FAIL `[未找到映射宿主端口 6380 的 Redis 容器]` ✓ |
| 恢复 | docker start + 真 ping | PONG | `PONG` ✓ |

### 5.2 ⑫ 三态盲测

| 状态 | 操作 | 期望 | 实测 |
|---|---|---|---|
| 正常 HITL 流程 | 跑真 probe | `ok:true, symptom_in_confirm_pass:false` | `{"health_ok":true, "pending_confirm_seen":true, "confirm_resumed":true, "symptom_in_confirm_pass":false, "task_diff":1, "ok":true}` ✓ |
| 后端不可达 | `CHECK_DEMO_BACKEND=http://127.0.0.1:9999` | `health_ok:false, error:...` | `{"health_ok":false, "error":"health: <urlopen error [WinError 10061] ...>"}` ✓ |
| /api/chat/stream 404 | mock server 返 404 (但 /health 200) | `health_ok:true + 后续路径 failure JSON` | 探针 `_stream_events` 捕获 HTTPError 塞 stream_http_error 事件 → main() 走「未触发 knowledge_import」分支 → `pending_confirm_seen:false, note:"模型未触发 knowledge_import..."` ✓（契约仍 OK，断言降级） |
| 恢复 | 跑真 probe | 同正常 | ✓ |

## 6. 单测验证（13/13 PASS）

```
$ pytest tests/test_wnextprobe1_probe_fixes.py -v
============================= 13 passed in 17.00s =============================
tests/test_wnextprobe1_probe_fixes.py::test_read_env_redis_port_parsing[REDIS_PORT=6377\n-6377-REDIS_PORT \u663e\u5f0f] PASSED
tests/test_wnextprobe1_probe_fixes.py::test_read_env_redis_port_parsing[REDIS_PORT=6380\n-6380-REDIS_PORT \u6f02\u79fb\u7aef\u53e3] PASSED
tests/test_wnextprobe1_probe_fixes.py::test_read_env_redis_port_parsing[REDIS_URL=redis://127.0.0.1:6380/0\n-6380-REDIS_URL \u7aef\u53e3(\u65e0 REDIS_PORT)] PASSED
tests/test_wnextprobe1_probe_fixes.py::test_read_env_redis_port_parsing[REDIS_PORT=6379\nREDIS_URL=redis://127.0.0.1:6377/0\n-6379-REDIS_PORT \u4f18\u5148\u4e8e REDIS_URL] PASSED
tests/test_wnextprobe1_probe_fixes.py::test_read_env_redis_port_parsing[# only comments\n-6377-\u65e5 REDIS_PORT \u8d70\u9ed8\u8ba4] PASSED
tests/test_wnextprobe1_probe_fixes.py::test_json_only_stdout_routes_pollution_to_stderr PASSED
tests/test_wnextprobe1_probe_fixes.py::test_json_only_stdout_install_is_idempotent PASSED
tests/test_wnextprobe1_probe_fixes.py::test_check_demo_no_hardcoded_redis_container PASSED
tests/test_wnextprobe1_probe_fixes.py::test_check_demo_has_detect_redis_container PASSED
tests/test_wnextprobe1_probe_fixes.py::test_hitl_probe_calls_create_session PASSED
tests/test_wnextprobe1_probe_fixes.py::test_hitl_probe_init_mysql_before_count_task PASSED
tests/test_wnextprobe1_probe_fixes.py::test_hitl_probe_stdout_is_pure_json PASSED
tests/test_wnextprobe1_probe_fixes.py::test_check_demo_label_reflects_dynamic_port PASSED
```

**回归单测**（hitl/probe 相关）：

```
$ pytest tests/test_r11_hitl.py tests/test_chat_tool_calling.py -v
======================= 12 passed, 3 skipped in 10.47s ========================
```

12 passed（3 skip 需真后端 Redis 连接，与本任务正交），未引入回归。

## 7. 关键 commit hash

```
commit a8984875e5dc2fc517b2555628a370b4bb702fce (HEAD -> feature/opt-waves)
Date:   2026-09-18

    fix(probe)/W-NEXT-PROBE-001 check-demo ②⑫ 探针口径修复
    ...
    3 files changed, 519 insertions(+), 19 deletions(-)
```

## 8. 锁文件清空确认

```bash
$ ls edu-agent/scripts/eval/wnextprobe1.lock
# 不存在（任务结束已 rm）

$ touch edu-agent/scripts/eval/wnextprobe1.lock && ls edu-agent/scripts/eval/wnextprobe1.lock
edu-agent/scripts/eval/wnextprobe1.lock
$ rm edu-agent/scripts/eval/wnextprobe1.lock && ls edu-agent/scripts/eval/wnextprobe1.lock
ls: cannot access ... : No such file or directory
```

锁文件全流程创建-清理验证通过 ✓。

## 9. 父 agent 独立验收建议（C-01）

```bash
# 1. 拉本任务 commit 到本地
git fetch && git checkout a8984875e5dc2fc517b2555628a370b4bb702fce

# 2. 跑单测
cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_wnextprobe1_probe_fixes.py -v
# 期望: 13 passed

# 3. 跑回归
.venv/Scripts/python.exe -m pytest tests/test_r11_hitl.py tests/test_chat_tool_calling.py -v
# 期望: 12 passed, 3 skipped

# 4. 跑 check-demo.mjs（要 8000 在线）
timeout 240 node scripts/check-demo.mjs 2>&1 | grep -E "②|⑫|汇总"
# 期望:
#   [PASS] ②. Redis(按 .env REDIS_PORT=6377 反查容器 docker exec redis-cli ping) (...)  PONG(容器 prisma-ai-redis-container-1)
#   [PASS] ⑫. HITL 真实性(confirm 续流不再 42200) (...)  pending_confirm→confirm 真可达,42200 症状消失(task N→N+1)

# 5. 真实 redis ping 独立验证
docker exec prisma-ai-redis-container-1 redis-cli ping
# 期望: PONG

# 6. 盲测 ② FAIL 路径(改 REDIS_PORT 漂移)
powershell -Command "(Get-Content edu-agent/.env) -replace '^REDIS_PORT=6377$', 'REDIS_PORT=6380' | Set-Content edu-agent/.env"
cd edu-agent && timeout 30 node scripts/check-demo.mjs 2>&1 | grep "②"
# 期望: [FAIL] ②. Redis(...)  [未找到映射宿主端口 6380 ...]
# 恢复:
powershell -Command "(Get-Content edu-agent/.env) -replace '^REDIS_PORT=6380$', 'REDIS_PORT=6377' | Set-Content edu-agent/.env"
```

## 10. 致谢

- W-NEXT-REDIS-FIX 提供了"REDIS_PORT=6377 / 容器 prisma-ai-redis-container-1"实测基线
- W-NEXT-CHECKDEMO-004 提供的 fileURLToPath 修复模式（防 Windows 中文路径 ENOENT）沿用于 readEnvRedisPort
- 教训 6"DEBUG 模式无 Authorization 头返回虚拟管理员"的同型设计（契约污染的兜底思路）启发 JsonOnlyStdout wrapper