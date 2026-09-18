# W-NEXT-CHECKDEMO-PROD-001 完成报告（check-demo 部署门加固：①--frontend-port + ②CI 部署门）

> 派单：orchestrator｜执行：W-NEXT-CHECKDEMO-PROD-001 子 agent｜日期：2026-09-18
> 分支：feature/opt-waves｜基线 HEAD：896030f274b6d78f515e42504cee70a01af4ea10
> 验收人：C-01 主会话（独立复跑命令，不采信本报告）

## 0. 一句话

两条尾巴全部闭环：① check-demo.mjs ⑤⑦⑨ 前端端口从硬编码 3000 改为 `--frontend-port <N>`（默认 3000，后端 8000 不动）；② ⑧ 守卫恢复 ENV_NAME 二次判据（P1-8 同口径，显式非 local + DEBUG=true 直接 FAIL）+ `--prod-gate` 旗标（WARN 升级 FAIL）+ 独立部署门 `deploy_env_gate.mjs`（10/10 自测）+ ci.yml `deploy-env-gate` job + deploy/README.md 部署清单行。**终态 check-demo 绿 21/21 + WARN ⑧⑩㉒ exit 0，本机 21/21 基线未破坏。**

## 1. HEAD commit + 文件清单

- 基线 HEAD：`896030f274b6d78f515e42504cee70a01af4ea10`（4 probe t/+3s/+6s/+9s 全一致，见 §6）
- 本任务交付 commit：**`f84eec925f4550ecbde86ae7315d0cff97ec836b`**（parent=896030f，纯前向）；报告 hash 回填 commit：见 §6
- 变更文件（全部在本任务文件域内）：

| 文件 | 状态 | 内容 |
|---|---|---|
| `edu-agent/scripts/check-demo.mjs` | 改 | 尾巴①：`--frontend-port`（cliPort 校验 1-65535，非法 exit 2），FRONTEND 由 FRONTEND_PORT 派生，⑤⑦⑨ 及 FIX.frontend/⑤名/模式行全部改用变量；尾巴②：⑧ 四分支（两级判据+--prod-gate）、FIX.debug 文案、头部注释 |
| `edu-agent/scripts/eval/deploy_env_gate.mjs` | 新 | 独立部署环境门（零依赖 Node≥18），语义见 §3 |
| `edu-agent/scripts/eval/test_deploy_env_gate.mjs` | 新 | gate 自测试 10 例（含真实 .env.example CI 对齐例），os.tmpdir fixture + finally 清理 |
| `.github/workflows/ci.yml` | 改（首次入库） | 追加独立 `deploy-env-gate` job（2 步：.env.example 必须 exit 0 + gate 自测试）；**附带修复先在 YAML 语法错误**（见 §5 P0-5） |
| `deploy/README.md` | 改 | task123 部署前检查单加 0.5) 部署环境门行；§3⑤ 与 §4 ⑧ 行的陈旧语义（DEBUG-DOC-001 之前的"缺省判红"描述）更新为两级判据四分支 |
| `edu-agent/scripts/eval/wnextcheckdemoprod1.lock` | 新→删 | 协调锁，commit 前已删（§6） |

未触碰：`febe_contract_check.py`、`edu-frontend/src`（另一 agent 文件域）、`deploy.mjs`（不在本任务文件域，见 P0-4）。

## 2. 六态盲测实测输出（全部真跑）

### 尾巴① 三态（--frontend-port）

**态1：假前端 3001 + `--frontend-port 3001`**（假服务：所有路径 200、`_next/static/development/*` 404）：

```
=== 非法端口参数（附加证据）===
$ node scripts/check-demo.mjs --frontend-port abc
参数错误: --frontend-port 需 1-65535 整数端口,得到 "abc"
exit=2

=== 态1 ===
模式: normal  前端端口: 3001  时间: 2026/9/18 12:13:06
[PASS] ⑤. 前端 3001 /login-register.html(+生产形态判别) (14ms)  生产 build 形态(_buildManifest dev 探针 404)
[PASS] ⑦. 关键页 200 × 8 (99ms)  8/8 全 200
[PASS] ⑨. 抽验页 200 /admin-users-refine-proto.html(C5-D2) (4ms)
```
→ ⑤⑦⑨ 全部探 3001。W-NEXT-PRODUCTION-BUILD-001 盲测态C（next start failover 3001 误探 3000）根因消除。

**态2：缺省（不带参数）**：

```
模式: normal  前端端口: 3000  时间: 2026/9/18 12:14:29
[PASS] ⑤. 前端 3000 /login-register.html(+生产形态判别) (35ms)  生产 build 形态(_buildManifest dev 探针 404)
[PASS] ⑦. 关键页 200 × 8 (122ms)  8/8 全 200
[WARN] ⑧. advisory: DEBUG 虚拟管理员探测(...两级判据+--prod-gate...) (28ms)
[PASS] ⑨. 抽验页 200 /admin-users-refine-proto.html(C5-D2) (25ms)
```
→ 缺省仍 3000，无回归。

**态3：`--frontend-port 3001` 且 3001 无服务**（先 taskkill 清掉残留监听确认 3001 free）：

```
模式: normal  前端端口: 3001  时间: 2026/9/18 12:15:27
[FAIL] ⑤. 前端 3001 /login-register.html(+生产形态判别) (5ms)
       -> cd edu-frontend && node node_modules/next/dist/bin/next dev -p 3001(验生产形态:...) [fetch failed]
[FAIL] ⑦. 关键页 200 × 8 (11ms)
[FAIL] ⑨. 抽验页 200 /admin-users-refine-proto.html(C5-D2) (2ms)
       -> ...(或 deploy.mjs start 生产形态;--frontend-port 已选 3001) [fetch failed]
```
→ ⑤⑦⑨ 报错清晰（fetch failed + 指引带所选端口）。

### 尾巴② 三态（⑧ 两级判据 + --prod-gate）

前置实测：本机 .env `DEBUG=true`、无 `ENV_NAME` 行；后端 8000 活着且无 token `/api/users/me` = HTTP 200（后门在线，⑧ vuln=true 成立）。

**态A：ENV_NAME 缺省 + DEBUG=true（本机现状）→ WARN（21/21 基线不破坏）**：

```
[WARN] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/users/me,两级判据+--prod-gate,W-NEXT-CHECKDEMO-PROD-001) (15ms)
       -> DEBUG=true 虚拟管理员漏洞,上线前必须 False(settings.DEBUG=false 并重启后端);ENV_NAME 显式非 local 时属生产类环境直接禁止部署(P1-8 两级判据) [WARN 开发态虚拟管理员后门存在(DEBUG=true, ENV_NAME=缺省(=config.py 默认 local));两级判据:ENV_NAME 显式非 local 时直接 FAIL,当前判为本机开发态故 WARN 不阻断;生产部署前必须 DEBUG=false(--prod-gate 旗标可将本 WARN 升级为 FAIL)]
```

**态B：临时注入 `ENV_NAME=prod` + DEBUG=true → FAIL**（cp 备份 .env → append ENV_NAME=prod（grep 确认 95 行注入）→ 跑 → 复原 → 校验：`ENV_NAME lines: 0`、`DEBUG: DEBUG=true`、备份文件已消费）：

```
[FAIL] ⑧. advisory: DEBUG 虚拟管理员探测(...) (22ms)
       -> DEBUG=true 虚拟管理员漏洞,...(P1-8 两级判据) [生产类环境虚拟管理员后门:DEBUG=true 且 ENV_NAME=prod(显式非 local,P1-8 同口径)——生产/预发绝不允许 DEBUG=true(未登录可读用户数据),立即 .env DEBUG=false 并重启后端;后端 P1-8 门禁下该形态本不应能启动]
```
（首跑曾因命令漏了注入步骤而无效，已作废重跑；有效取证以上述为准。）

**态C：--prod-gate + 态A → ⑧ WARN 升级 FAIL**：

```
模式: normal  前端端口: 3000  [prod-gate:⑧ WARN 升级 FAIL(部署门)]  时间: 2026/9/18 12:18:39
[FAIL] ⑧. advisory: DEBUG 虚拟管理员探测(...) (14ms)
       -> DEBUG=true 虚拟管理员漏洞,...(P1-8 两级判据) [--prod-gate 部署门:虚拟管理员后门存在(DEBUG=true, ENV_NAME=缺省(=config.py 默认 local))——WARN 已升级为 FAIL 阻断出包;生产 .env 必须 DEBUG=false]
```

**态C 自然退出码（--prod-gate 全量 21 项跑完，不被截断）**：

```
汇总: 绿 18/21,红项 ⑧,WARN ⑩、㉒ —— 请按上方指引处置后重跑 (检查耗时 137088ms)
PRODGATE_EXIT=1
```
→ 全轮唯一红 = 被升级的 ⑧，其余 18 绿 + ⑩㉒ WARN 与基线一致，exit 1 达成。

## 3. deploy_env_gate.mjs（独立部署门）

- 路径：`edu-agent/scripts/eval/deploy_env_gate.mjs`；用法 `node scripts/eval/deploy_env_gate.mjs [env文件路径]`（缺省 edu-agent/.env）。
- 语义（与后端 P1-8 `_debug_env_gate` config.py:763 同口径 `strip().lower()` ∈ {"", "local"}）：
  - `DEBUG=false`/缺省（config.py 默认 False 同口径）→ **exit 0**；
  - `DEBUG=true` + ENV_NAME 显式非 local → **exit 1**（deny_prod_env_debug_true）；
  - `DEBUG=true` + ENV_NAME 缺省/空/local → **exit 1**（deny_debug_true，deploy 门从严——P0-2 正是「忘设 ENV_NAME 的 DEBUG=true 被当开发态」，部署语境一律不放行；本地开发把关走 check-demo ⑧）；
  - DEBUG 值不可解析 → exit 1（fail-closed）；env 文件缺失 → exit 1（fail-closed）。
- 自测试：`test_deploy_env_gate.mjs` **10/10 PASS**（allow / deny_prod_env_debug_true×3 含大小写 / deny_debug_true×2 / allow_debug_undeclared / deny_debug_unparsable / 真实 .env.example exit 0 / 文件缺失 exit 1）。
- 对真实 .env 实测：`exit=1`，`decision=deny_debug_true`（本机 dev 形态被部署门正确阻断——这正是「部署前对真实 .env 把关」的预期行为）。
- 对 `edu-agent/.env.example` 实测：**exit 0**（DEBUG=false + ENV_NAME=prod → allow），CI 同路径。

## 4. CI 接线（ci.yml）

- 新增独立 job（不嵌入既有 backend/migration/frontend 三 job，零破坏面）：

```yaml
deploy-env-gate:
  name: Deploy env gate (.env.example deploy-safe)
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with: { node-version: "20" }
    - name: Run deploy_env_gate on .env.example (must exit 0)
      run: node edu-agent/scripts/eval/deploy_env_gate.mjs edu-agent/.env.example
    - name: Gate self-test (decision branches)
      run: node edu-agent/scripts/eval/test_deploy_env_gate.mjs
```

- YAML 校验：venv python + pyyaml 全文件 safe_load 通过，`jobs = ['backend','migration','frontend','deploy-env-gate']`。
- **先在问题修复（P0-5）**：ci.yml 在 git 里**从未被跟踪**（`?? .github/workflows/ci.yml`），且存在先在 YAML 语法错误——line 34 `name: Lint (ruff: critical only)` 裸标量含 `: `，pyyaml ScannerError，整个文件不可解析（GitHub Actions 也会拒载）。已最小修复为 `name: "Lint (ruff: critical only)"`（仅加引号，零语义变更），修复后全文件 YAML OK。本次随任务首次入库。

## 5. ≥3 P0 自批判

**P0-1 `--prod-gate` 被遗忘风险**：旗标不传则 ⑧ 退回 WARN，出包流水线若只跑 `check-demo.mjs` 不带旗标，P0-1 等于没修。缓解：真正的出包硬门是**无旗标**的 `deploy_env_gate.mjs`（对 DEBUG=true 一律 exit 1），已接 ci.yml 独立 job + deploy/README.md task123 清单 0.5)；`--prod-gate` 只是 check-demo 侧的第二道带。残余风险：deploy.mjs `runCheckDemoAssert()` spawn 的是裸 check-demo（未带 --prod-gate）——deploy.mjs 不在本任务文件域未动，已在 README 用 deploy_env_gate 兜底；建议后续 W-NEXT 给 deploy.mjs 出包路径接 deploy_env_gate.mjs。

**P0-2 deploy_env_gate 绕过面**：gate 只读指定 env **文件**——①运行时环境变量（`process.env.DEBUG=true`）或 compose `environment:` 可覆盖文件值绕过（README 附录已注明 compose 强制 DEBUG=false，残余风险登记）；②只查 DEBUG/ENV_NAME 两键，API_TOKEN/JWT 默认值类后门归 `_security_guard` 启动门，非本门职责；③DEBUG 缺省 fail-open 依赖 `config.py DEBUG: bool = False` 缺省不再改——若上游改默认为 True，gate 语义静默反转，test case 5（DEBUG 缺省→allow）会在该变更时仍绿，属盲区，已在此登记；④行内注释（`DEBUG=true # x`）会解析失败→fail-closed exit 1，宁误红不漏。

**P0-3 ENV_NAME 判据口径漂移**：⑧ / deploy_env_gate / config.py `_debug_env_gate` 三处各自实现 `strip().lower() ≠ ""/"local"`，未来任何一处改词表（如把 dev 视为 local）都可能漂移。当前三处注释互相同源标注（P1-8 同口径 + config.py:763 行号锚点）；漂移方向若为 check-demo/gate 更严（把某名当生产类）= fail-safe 可接受，反向（后端把 prod 当 local 放行）则 ⑧ 会先红——⑧ 读 .env 与后端同文件，能拦住「后端门被绕过」的场景，反过来后端门兜底「.env 与运行时注入不一致」场景，双向冗余成立。

**P0-4 --frontend-port 与 deploy.mjs 3000 硬编码联动遗漏**：deploy.mjs `FRONTEND_PORT=3000` 常量、start/stop/status 全按 3000 推理；check-demo --frontend-port 只让**探测侧**跟随 failover 端口，deploy.mjs 侧（拉起/停止/recordPid）不会。本任务只闭环「check-demo 探错端口」的根因（实测复现的缺陷），deploy.mjs 改造不在文件域；FIX.frontend 指引已改为带所选端口并附 deploy.mjs start 备选。登记为后续任务。

**P0-5 ci.yml 未入库 + 先在 YAML 错误**（见 §4）：若不修，我的 deploy-env-gate job 永远不会被执行（文件不可解析）——「CI 部署门」交付物形同虚设。按根因修复原则最小修复（加引号）并首次入库。风险：文件首次入库使 PR 面新增 4 个既有 job 的定义（backend/migration/frontend 均为存量内容原样入库，非我新增逻辑）。

**P0-6 环境前置与派单上下文不符**：派单称「3000 前端 next start 生产形态 PID 9892」，实测 PID 9892 是 openclaw gateway，3000 无人监听（curl 000），且 `.next` 无 BUILD_ID（直接 next start 会报 no production build）。已按 deploy.mjs 同构方式拉起（`NEXT_PROD_DIST_DIR=.next-prod npx next start -p 3000`，.next-prod/BUILD_ID 存在无需 rebuild），恢复派单基线。教训：上下文环境断言必须 probe 实证（本次 ⑤⑦⑨ 若直接跑终态会假红）。

**P0-7 中途杀进程的残留污染**：盲测用 `timeout 35` 提前杀 check-demo（避免 ⑯ lifecycle 反复重启后端干扰共享环境），Git Bash `kill` 对 Windows node 子进程不可靠（态3 首测 3001 假服务残留导致假 PASS，taskkill 清理后重测才真实）。流程教训：端口态盲测前必须 `netstat` 断言空口。另态B 首跑因命令漏注入而无效——无效取证一律作废重跑，不混入结论。

## 6. Git 纪律 + lock

- commit 前 4 probe（t / +3s / +6s / +9s）：`896030f274b6d78f515e42504cee70a01af4ea10` 四次全一致（HEAD STABLE）
- 分支确认：`refs/heads/feature/opt-waves`
- 交付 commit：`f84eec925f4550ecbde86ae7315d0cff97ec836b`（6 files, +553/-27）；`git rev-parse HEAD~1` = `896030f...` == probe 稳定 tip → **parent 纯前向，无 merge/无覆盖他 agent 提交**
- 报告 hash 回填：独立 commit（本 commit），仍纯前向
- lock `edu-agent/scripts/eval/wnextcheckdemoprod1.lock`：commit 前 `rm` + `ls` 复核 **absent confirmed**；`git status` 该路径无痕、commit 内容无此文件
- 只 staged 本任务 6 文件（显式 git add 路径清单，未 `git add -A`）；工作区他 agent 变更（wnextrag2.lock 删除、WNEXTDEBUGDOC1 报告、next-env.d.ts 等）未触碰

## 7. 终态 check-demo（无参数全量，21 项真跑）

```
汇总: 绿 21/21,WARN ⑧、⑩、㉒ —— 演示环境就绪 (检查耗时 130453ms)
FINAL_EXIT=0
```
WARN 构成：⑧（本机 dev 态 DEBUG=true 后门，两级判据 WARN，语义保持）⑩（febe 待接/未冻结仅后端）㉒（object_key 历史复用留痕）——与派单基线完全一致。
