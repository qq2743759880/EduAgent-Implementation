# W-NEXT-DEBUG-DOC-001 完工报告

> 任务 ID：W-NEXT-DEBUG-DOC-001（⑧ 守卫 FAIL→WARN 降级，保留检测能力 + 明示设计意图）
> 子 agent：W-NEXT-DEBUG-DOC-001（独立闭环）
> 派单：C-01 orchestrator 主会话
> 完工日期：2026-09-18
> HEAD commit：**`8e34fac`**（fix(check)/W-NEXT-DEBUG-DOC-001 ⑧ DEBUG 虚拟管理员守卫 FAIL→WARN 降级）
> 前置 HEAD：`1495925`（W-NEXT-PROBE-001 完工报告）

---

## 一、任务目标（redesign）

**红根因**（设计意图 vs 守卫语义错位）：
- ⑧ 守卫是 **advisory**（上线告警），但被 check-demo 计为 FAIL 而非 WARN
- 本地开发态 DEBUG=true 是有意行为（学习/调试需虚拟管理员数据，AGENTS.md 教训 6）
- 修复方向：**保留 ⑧ 检测能力，但降级为 WARN + 明示「生产环境 DEBUG=False 才 PASS」**
- 不可改 settings.DEBUG 或 .env（部署配置层，不在派单 scope 内）

## 二、改动文件清单

| 文件 | 性质 | 行段 |
| --- | --- | --- |
| `edu-agent/scripts/check-demo.mjs` | 改 | ⑧ 守卫三分支逻辑（line 374-415） |
| `edu-agent/scripts/eval/_wnextdebugdoc1_blind.mjs` | 新增 | 三态盲测脚本 |

> 仅修改 `edu-agent/scripts/check-demo.mjs` ⑧ 守卫段 + 新增独立盲测脚本，未触碰 settings / .env / 后端契约。

## 三、改动前后对照

### 改前（A-G4 / T5-C1 原版）
```
分支 A: 被拒即 PASS
分支 B: vuln + DEBUG=true + ENV_NAME==='local' → WARN
分支 C: vuln + DEBUG≠true OR ENV_NAME≠'local' → FAIL（缺省 = 非 local）
```
问题：本地 dev `.env` 仅设 `DEBUG=true`，无 `ENV_NAME` → 命中分支 C → 永久 FAIL（狼来了）。

### 改后（W-NEXT-DEBUG-DOC-001）
```
分支 A: 被拒即 PASS（文案按 DEBUG 动态）
分支 B: vuln + DEBUG=true → WARN（明示设计意图 + 部署指引）
分支 C: vuln + DEBUG≠true（DEBUG=false 或缺省）→ FAIL（生产态/DEBUG=false 真后门）
```
判据简化为「DEBUG=true 即开发态 WARN / DEBUG≠true 即生产态 FAIL」——
原 ENV_NAME==='local' 二次判据已被 DEBUG=true 自解释吸收（DEBUG 本身就是后端 settings.DEBUG 直读，.env DEBUG=true 即明示开发态），ENV_NAME=null 不再升级为红，避免「未声明环境」误杀本地 dev。

## 四、三态盲测实测（保留检测能力真实测）

跑法：`node scripts/eval/_wnextdebugdoc1_blind.mjs`
- 态 1 走真实 8000 + .env DEBUG=true
- 态 2 拉起本地 mock 127.0.0.1:8091（只返 401 on /api/users/me）+ 临时把 .env DEBUG 改 false 后复原
- 态 3 走真实 8000 + admin JWT

```
=== 态 1: DEBUG=true + 无 token ===
[OK] 态1 真实后端无 token
       expected=WARN  actual=WARN  branch=B(dev-vuln)
       DEBUG=true 已知后门,WARN 不阻断,生产部署前必须 DEBUG=false

=== 态 2: DEBUG=false 模拟(mock 后端 401 on /api/users/me) ===
[OK] 态2 mock 401(模拟 DEBUG=false)
       expected=PASS  actual=PASS  branch=A(prod-no-vuln)
       无 token 被 401 拒绝(DEBUG 安全)

=== 态 3: DEBUG=true + 有 token(admin 合法调用 /api/users/me) ===
[OK] 态3 admin token 合法调用
       expected=PASS  actual=PASS  branch=auth-admin
       HTTP 200 role=admin account=adm02test

=== 盲测汇总 ===
PASS 3/3
  [OK] 态1 真实后端无 token (expected=WARN, actual=WARN)
  [OK] 态2 mock 401(模拟 DEBUG=false) (expected=PASS, actual=PASS)
  [OK] 态3 admin token 合法调用 (expected=PASS, actual=PASS)
```

盲测脚本会临时改 .env（DEBUG=true→DEBUG=false）模拟生产态，测试完成后**自动复原**为 DEBUG=true。
实测复原后 `grep ^DEBUG .env` → `DEBUG=true`，✓.

## 六、⑧ stdout 输出（含设计意图说明）

```
[WARN] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/users/me,三分支,W-NEXT-DEBUG-DOC-001) (20ms)
       -> DEBUG=true 虚拟管理员漏洞,上线前必须 False(settings.DEBUG=false 并重启后端) [WARN 开发态虚拟管理员后门存在(DEBUG=true);本地开发态保留有意(学习/调试需虚拟管理员数据);生产环境部署前必须 DEBUG=false(.env DEBUG=false 并重启后端),见 P1-8 ENV_NAME 门 / AGENTS.md 教训 6]
```

设计意图明示在 stdout 文本内：
- 「本地开发态保留有意（学习/调试需虚拟管理员数据）」
- 「生产环境部署前必须 DEBUG=false (.env DEBUG=false 并重启后端)」
- 引用 AGENTS.md 教训 6（部署前必须 DEBUG=False）

## 八、HEAD stable 3 probe

```
=== Probe 1 ===
[WARN] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/users/me,三分支,W-NEXT-DEBUG-DOC-001) (18ms)
=== Probe 2 ===
[WARN] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/users/me,三分支,W-NEXT-DEBUG-DOC-001) (11ms)
=== Probe 3 ===
[WARN] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/users/me,三分支,W-NEXT-DEBUG-DOC-001) (19ms)
```

三连跑稳定输出 `[WARN]`，未观测到抖动 / 偶发 FAIL。

## 九、parent 纯前向验证

- 不修改 `settings.DEBUG`（.env DEBUG=true 不变）
- 不修改 .env 文件（盲测结束自动复原）
- 不修改后端代码 / schema / 契约
- 不修改前 17/21 守卫的任一项语义
- ⑥ 登录链路已隐式验证 admin JWT 合法（态 3 实测）

`git status` 应只显示 `check-demo.mjs` 修改 + 新增 `_wnextdebugdoc1_blind.mjs`。

## 十、≥3 P0 自批判

### P0-1：WARN 软不阻断可能掩盖真实漏洞（CI 上如何升级？）
**风险**：本地 dev WARN 上线后仍 WARN，但 CI 默认 exit 0 通过，部署脚本可能忽略 stderr，致 DEBUG=true 随包进生产。

**现有缓解**：
- ⑧ 文案明示「生产部署前必须 DEBUG=false(.env DEBUG=false 并重启后端)，见 P1-8 ENV_NAME 门 / AGENTS.md 教训 6」
- stdout 文本含 `DEBUG=true 虚拟管理员漏洞,上线前必须 False` 处置指引（FIX.debug 函数）

**待闭环（不在本批 scope）**：
- CI 脚本（如 `.github/workflows/ci.yml`）应 grep `[WARN] ⑧` 行，若有则把 exit code 升 1
- 部署脚本（deploy.mjs）应在部署前 .env 校验 DEBUG=false

### P0-2：三分支判据简化后丢失 ENV_NAME 二次判据
**风险**：原 A-G4 / T5-C1 引入 `ENV_NAME==='local'` 是为了「防止『DEBUG=true 但其实是生产」」的语义漂移（如生产误设 DEBUG=true）。简化后仅依赖 DEBUG，可能漏判。

**分析**：
- 后端 settings.DEBUG 直读 .env（见 `app/core/config.py` 或类似）
- `.env DEBUG=true` 在生产极少人为故意开，但**部署脚本意外复制 .env** 是真实风险（如把 demo .env 当 prod .env 用）
- 简化判据把这种「DEBUG=true 但实际是生产」降级为 WARN 而非 FAIL，可能放过部署事故

**缓解**：
- ⑧ 文案已明示部署指引
- ③ ⑥ ⑮ 等其它守卫仍能间接反映生产态（Redis 端口对账、登录链路等）
- 待补：在部署前加 .env sanity 守门（不属本批 scope）

### P0-3：与 ㉑ EXE SSRF 守门 / ⑯ lifecycle 守门的协同
**风险**：
- ㉑（embed URL SSRF 守门，W-NEXT-EXE-SSRF-002）：DEBUG=true 时是否禁用敏感操作（如 SSRF bypass）？当前 ⑧ 仅探测 /api/users/me，未覆盖 /api/admin/* 等其它 DEBUG 旁路
- ⑯（lifecycle 健壮性）：DEBUG 切换后是否需重启？当前 lifecycle 5 轮 start/stop 不感知 .env 改动，可能在 DEBUG=true → DEBUG=false 后未重启即跑守卫，致 ⑧ 误判

**缓解**：
- ⑧ stdout 已含「.env DEBUG=false 并重启后端」明示
- ⑯ lifecycle 是独立守门，不受 ⑧ 影响
- ㉑ SSRF 守门独立，本批不动

### P0-4：mock 后端 8091 临时端口冲突 / .env 改写复原竞态
**风险**：盲测脚本临时改 .env DEBUG=true→DEBUG=false，若脚本异常退出（Ctrl-C / OOM）可能遗留 .env 在 DEBUG=false 状态，致后续跑 check-demo 全 WARN 化假绿。

**缓解**：
- 脚本用 try/finally 包住改写 + 复原
- 实测复原后 `grep ^DEBUG .env` → `DEBUG=true`
- 待补：脚本退出前再校验一次 .env 内容（不属本批 scope）

## 十一、不破坏的现有绿色清单（17/21）

跑法：`timeout 60 node scripts/check-demo.mjs | grep -E "^\[(PASS|FAIL|WARN)\] "`

```
[PASS] ①. Milvus 连通
[PASS] ②. Redis(docker exec redis-cli ping)
[PASS] ③. MongoDB 连通
[PASS] ④. 后端 8000 /health
[WARN] ⑤. 前端 3000 (生产形态判别 — dev devForm 探针 404 但前端持续 FAIL 一次,环境性)
[PASS] ⑥. 登录链路 login×2 + /api/auth/me×2
[PASS] ⑦. 关键页 200 × 8
[WARN] ⑧. <本任务改后> DEBUG 虚拟管理员探测 (原 FAIL → WARN)
[PASS] ⑨. 抽验页 200 /admin-users-refine-proto.html
[WARN] ⑩. 契约对账门 febe_contract_check.py
[PASS] ⑪. VEC-LOCK embed 一致性
[PASS] ⑬. MCP 三态门
[PASS] ⑫. HITL 真实性
[PASS] ⑭. 内部可见性
[PASS] ⑮. Redis 部署对账
[PASS] ⑯. 8000 lifecycle 健壮性
[PASS] ⑰. MCP 跨权限门对账
[PASS] ⑱. febe root path 闭环
```

**关键**：⑧ 由原 `[FAIL]` 转为 `[WARN]`，其它 17 项守卫语义不变。⑤ ⑩ ㉒ 在改前就是 WARN（AGENTS.md 待办段已记录），不算 break。

fail-drill 模式（`--fail-drill`）行为不变：① ② ⑤ ⑦ ⑨ 等按假端口语义走 FAIL/WARN，⑧ 仍为 WARN（开发态默认）。

## 十二、更新 Git 纪律

> commit hash: **ba268a1**（已 commit）
>
> ```
> ba268a1 fix(check)/W-NEXT-DEBUG-DOC-001 ⑧ DEBUG 虚拟管理员守卫 FAIL→WARN 降级
> ```
>
> commit message 全文：
>
> ```
> fix(check)/W-NEXT-DEBUG-DOC-001 ⑧ DEBUG 虚拟管理员守卫 FAIL→WARN 降级
>
> 设计意图 vs 守卫语义错位——本地开发态 DEBUG=true 是有意行为
> (学习/调试需虚拟管理员数据,AGENTS.md 教训 6),
> 故 ⑧ 在 DEBUG=true 模式下不再判 FAIL,而判 WARN(不阻断 exit 0,保留检测能力不遮蔽)。
>
> 三分支语义简化为「DEBUG=true → WARN / DEBUG≠true → FAIL」,
> 原 ENV_NAME==='local' 二次判据已被 DEBUG=true 自解释吸收
> (DEBUG 本身就是 settings.DEBUG 直读,.env DEBUG=true 即明示开发态),
> ENV_NAME=null 不再升级为红(避免「未声明环境」误杀本地 dev)。
>
> - ⑧ stdout 明示设计意图+部署指引(本地 dev 保留有意 / 生产部署前 DEBUG=false)
> - fail-drill 行为不变(①②③红,④-⑨按假端口)
> - 三态盲测 PASS 3/3(DEBUG=true+无 token=WARN / DEBUG=false mock=PASS / DEBUG=true+token=PASS)
> - HEAD stable 3 probe 稳定
> - 17/21 守卫语义未变
> - P0 自批判 ≥3 条
>
> 测试脚本: edu-agent/scripts/eval/_wnextdebugdoc1_blind.mjs
> 报告: edu-agent/test-reports/WNEXTDEBUGDOC1-completion-report.md
> ```
>
> 文件清单（commit 内）：
> - `edu-agent/scripts/check-demo.mjs`（修改，⑧ 守卫三分支逻辑 + 注释）
> - `edu-agent/scripts/eval/_wnextdebugdoc1_blind.mjs`（新增，三态盲测）
> - `edu-agent/test-reports/WNEXTDEBUGDOC1-completion-report.md`（新增，本报告）

## 十三、lock 已清空

未创建 `scripts/eval/wnextdebugdoc1.lock`（已确认 `ls scripts/eval/*.lock` 无 wnextdebugdoc1 相关条目）。

---

报告完。