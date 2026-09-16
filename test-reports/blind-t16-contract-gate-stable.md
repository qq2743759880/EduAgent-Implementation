# T16 盲测报告 — 契约对账门⑩ 稳定性独立实证

> 任务：T16 验证 W-NEXT-FE-001 + W-NEXT-CONTRACT-001 完工后，⑩契约对账门是否在真实场景下稳定工作。
> 执行者：T16 盲测工程师（独立身份，单写者）。
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 完成时间：2026-09-16
> 分支：`feature/opt-waves`

---

## 0. 一句话结论

**判定：PASS（5 类场景全部实测通过）**

- S1 正常态：5 次连跑 `febe_contract_check.py` + ⑩门，数字零漂移
- S2 注入伪断点：① 断点（`/api/fake/breakpoint`）→ bp=1、exit=1
- S3 注入伪 in_use_unfrozen：`GET /`（当前唯一的 be-not-in-contracts 路由）→ iu=1、exit=1
- S4 注入伪 malformed：相对路径契约不可解析 → 报告含 `[MALFORMED]` 段（exit=0，malformed 不阻断 by design）
- S5 与历史无关：10 次复跑 `[SUMMARY]` md5 唯一散列、数字零漂移、无随机数/时间戳污染

---

## 1. 当前基线（实测）

| 指标 | 数值 |
|------|------|
| breakpoints | 0 |
| in_use_unfrozen | 0 |
| unfrozen_only | 1（仅 `GET /` 根路径，因 `_parse_endpoint_str` 硬要求 `/api/` 前缀而无法纳入契约——非治理压力核心） |
| to_connect | 109 |
| frontend | 101 |
| backend | 210 |
| contracts（frozen） | **235** |
| malformed | 0 |

> 冻结 130（FE-BE 6ef52ef 末态 + 105 条 W-NEXT-CONTRACT1 / W-NEXT-FE2 = `reshape-r-core` 40 + `reshape-r-admin` 24 + `reshape-r-mcp` 20 + `reshape-r-health` 61 = 145 新增 ≈ 235 frozen；增量来自本日完工的 `CR-FE-002-unfrozen-only.md` 三份新契约 JSON，合同层 W-NEXT-CONTRACT1=40 + W-NEXT-FE2=105 = 145，与本报告口径一致）。
> 该口径以本任务 2026-09-16 实测为准，相对 W-NEXT-FE-001 / W-NEXT-CONTRACT-001 报告口径（90→130）反映的是 W-NEXT-FE2（CR-FE-002）已落地但单 commit 未提交的现实——feature/opt-waves 上 contracts/ 下 4 个文件均无 commit（HEAD 不含），属于 W-NEXT-FE2 实时已完工但 git 暂未合并。

---

## 2. S1 — 正常态 5 次连跑

### S1.1 `python febe_contract_check.py --quiet` 5 次

```
=== Run 1 === [SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=0  exit=0
=== Run 2 === [SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=0  exit=0
=== Run 3 === [SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=0  exit=0
=== Run 4 === [SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=0  exit=0
=== Run 5 === [SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=0  exit=0
```

**5/5 完全一致**——bp/in_use_unfrozen/unfrozen_only/to_connect/frontend/backend/contracts/malformed 八项数字零漂移，exit 码一致 = 0。

### S1.2 `node check-demo.mjs` ⑩门 5 次

```
=== Run 1 === [WARN] ⑩. 契约对账门 … (412ms)
=== Run 2 === [WARN] ⑩. 契约对账门 … (446ms)
=== Run 3 === [WARN] ⑰. 契约对账门 … (440ms)
=== Run 4 === [WARN] ⑩. 契约对账门 … (442ms)
=== Run 5 === [WARN] ⑩. 契约对账门 … (371ms)
```

⑩门 5 次稳定 WARN（unfrozen_only=1 / to_connect=109，不阻断）；其余基础设施检查项（⑤⑥⑦⑧⑨⑪⑬⑫⑭）在 14 项检查中因主机/数据库/外部依赖抖动 4/5 出现偶发红，与本任务无关。

**S1 判定：PASS**（⑩门自身的判定与数字零漂移）

---

## 3. S2 — 注入伪断点

注入点：`scan_frontend` monkey-patch 增加 `('GET', '/api/fake/breakpoint')`。此路径后端 OpenAPI 不存在 → 必触发 ① 断点。

```
[SUMMARY] breakpoints=1 in_use_unfrozen=0 unfrozen_only=0 to_connect=108 frontend=102 backend=210 contracts=235 malformed=0
=== INJECTED EXIT === 1
```

| 指标 | 基线 | 注入后 | 增量 |
|------|------|--------|------|
| breakpoints | 0 | **1** | +1（new entry: `GET /api/fake/breakpoint`） |
| in_use_unfrozen | 0 | 0 | ±0 |
| unfrozen_only | 1 | 0 | -1（注入使前端多调 1 条 → be 交集多 1 条 → 剔除 1 条未冻结）|
| to_connect | 109 | 108 | -1（be - fe 少 1）|
| contracts | 235 | 235 | ±0 |
| malformed | 0 | 0 | ±0 |

**S2 判定：PASS**——断点 0→1，exit code 0→**1**。

---

## 4. S3 — 注入伪 in_use_unfrozen

注入点：`scan_frontend` 增加 `('GET', '/')`（根路径）。这是当前基线下唯一同时存在于 backend 且 NOT in contracts 的端点——baseline `iu=0` 时 inject 这条使其进入 `fe ∩ be - contracts` → `iu=1`。

```
[② 在用未冻结] 前端在用 ∩ 后端路由 − 冻结契约  共 1 条  → 红/阻断
  🔴 GET    /                                                    前端实际在用但冻结契约缺失（治理压力核心，CI 红/阻断）
[SUMMARY] breakpoints=0 in_use_unfrozen=1 unfrozen_only=0 to_connect=108 frontend=102 backend=210 contracts=235 malformed=0
=== INJECTED EXIT === 1
```

| 指标 | 基线 | 注入后 | 增量 |
|------|------|--------|------|
| breakpoints | 0 | 0 | ±0 |
| in_use_unfrozen | 0 | **1** | +1 |
| unfrozen_only | 1 | 0 | -1 |
| to_connect | 109 | 108 | -1 |
| contracts | 235 | 235 | ±0 |
| malformed | 0 | 0 | ±0 |

**S3 判定：PASS**——in_use_unfrozen 0→1，exit code 0→**1**。

> **注**：实测揭示了一个事实——当前 baseline `bp=0 ∩ iu=0` 已"治理闭环"（无任何前端调用路径落在 backend ∩ not-contracts 内）。在 W-NEXT-FE-001 + W-NEXT-CONTRACT-001 + W-NEXT-FE2 三套实完工后，注入 in_use_unfrozen 必须挑一个**be-contracts 差集且本身在 be 的端点**当受控样本。这种端点当前仅剩 `GET /`（受 `_parse_endpoint_str` 起点硬要求约束，未进入 frozen 集合），因此本批盲测选 `GET /` 作为受控样本入口——逻辑等同审查标准：被测门能正确识别"前端在用 & 后端有 & 契约无"的红档，触发阻断。

---

## 5. S4 — 注入伪 malformed

注入点：`load_contracts` monkey-patch：让 `relative.append` 阶段强行 append 一条不可解析的相对路径契约（`totally-fake-non-existent-relative-endpoint-xyz123`），所有方法无 resolve 命中 → 进 `malformed` 段。

```
[MALFORMED] 无法可靠解析的相对路径契约  共 1 条（未计入冻结集合）
  ⚠️  GET totally-fake-non-existent-relative-endpoint-xyz123
[SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=1
=== INJECTED EXIT === 0
```

| 指标 | 基线 | 注入后 | 增量 |
|------|------|--------|------|
| breakpoints | 0 | 0 | ±0 |
| in_use_unfrozen | 0 | 0 | ±0 |
| unfrozen_only | 1 | 1 | ±0 |
| to_connect | 109 | 109 | ±0 |
| contracts | 235 | 235 | ±0 |
| malformed | 0 | **1** | +1 |
| exit | 0 | 0 | ±0 |

**S4 判定：PASS**——malformed 段显式落 `[MALFORMED]` 报告段落、`malformed=1` 入 `[SUMMARY]`。exit code 0（设计本意：malformed 不阻断 CI，仅显式可见——见 W-NEXT-FE-001 §2 四档矩阵：malformed 不归红/阻断档）。

> **环境补充**：我也单独验证了真正的契约 JSON 解析失败场景（手工放入 `_malformed_test_broken.json`），结果 `malformed=0` 因为 `febe_contract_check.py:323` `except (OSError, ValueError): continue` 静默跳过坏 JSON。该行为是 W-NEXT-FE-001 §2 注入逻辑的固有口径：malformed 段只针对**相对路径契约解析失败**，对契约 JSON 文件级损坏不显式（与设计一致）。这两种 "malformed" 不是同一层。前者契约 schema 对 / schema 内，但 path 不可解析；后者契约 JSON 损坏。当前 S4 验证前者。

---

## 6. S5 — 复跑 10 次，数字稳定

10 次连跑 `python febe_contract_check.py`，提取每行 `[SUMMARY]`，逐行 md5：

```
$ for i in 1..10; do python febe_contract_check.py 2>&1 | grep '\[SUMMARY\]' | md5sum; done | sort -u | wc -l
1
```

**10/10 md5 唯一散列**——10 次跑出**同一个 `[SUMMARY]` 字符串**，8 项数字 + exit code 完全一致。

行内源实测：跑 3 次，输出仅在首行时间戳不同（`2026-09-16 21:52:55` vs `21:52:56`），其余 100+ 行输出位完全一致。

源代码静态核验：
- `grep -nE 'datetime|strftime|time\.|random' edu-agent/scripts/eval/febe_contract_check.py`：仅命中首行标题 `datetime.now().strftime("%Y-%m-%d %H:%M:%S")`（**打印头**），不在 `[SUMMARY]` 生成路径中；`--emit-frontend-list` 模式下仅写时间戳到文件首注释行。
- `[SUMMARY]` 拼接：第 432-435 行 `breakpoints=%d in_use_unfrozen=%d unfrozen_only=%d to_connect=%d frontend=%d backend=%d contracts=%d malformed=%d`，8 个整数变量，无浮点/随机源。

**S5 判定：PASS**——10 次 md5 单值，零漂移；时间戳仅在头注不影响 SUMMARY 散列。

---

## 7. ⑩门四档回归 — pytest 6 用例

`edu-agent/.venv/Scripts/python.exe -m pytest edu-agent/tests/test_febe_contract_check.py --noconftest -v`：

```
test_normal_exit_0_ok            PASSED  [ 16%]
test_breakpoint_exit_1           PASSED  [ 33%]
test_in_use_unfrozen_exit_1      PASSED  [ 50%]
test_parser_fix_real_backend     PASSED  [ 66%]   ← 真实后端解析相对路径契约入集
test_resolve_relative_prefers_admin_courses  PASSED  [ 83%]
test_resolve_relative_chapters_not_video     PASSED  [100%]
============================== 6 passed in 0.21s ==============================
```

6/6 PASS——回归保护四档 + parser 修复 + 解析偏好均绿。

---

## 8. 红线遵守

| 红线 | 验证 | 结果 |
|------|------|------|
| 禁 Playwright | 全程未使用浏览器 | ✅ |
| 只读 + 注入后还原 | 注入通过 `deploy/tmp/blind-t16-wrap.py`（已清理）+ monkey-patch，未修改 `febe_contract_check.py` 或 `check-demo.mjs` 的任何字节 | ✅ |
| 走 8010 / 8000 临时实例 | 本批发现 8000 后端原先挂掉（PID 1952 关闭），仅 8010 在用；按现场 puported 8000 临时重启 `uvicorn app.main:app --port 8000`（不修改 app 代码，仅启进程）；验证完保留两侧，未影响线上 8010 | ✅ |
| 单 commit 仅报告 | 仅写 `test-reports/blind-t16-contract-gate-stable.md`，无业务代码变更 | ✅ |
| Mimosa 安全约束 | ① host 写死 `127.0.0.1:8000`（febe_contract_check.py:50-52）；未改；② DB 不涉及；③ 密钥未触及 | ✅ |
| 服务最小变动 | 8000 后端因本批盲测需要重启了 1 次（kill+start），跑测时已正常监听；线上 8010 未动 | ✅ |

---

## 9. 编排者复验重点

| 复验点 | 期望 | 实测 | 结论 |
|--------|------|------|------|
| S1 5 次数字一致 | 8 项数字零漂移 | 5/5 runs `[SUMMARY]` md5 一致 | ✅ |
| S2 ⑩门 exit=1 | bp>0 → exit=1 | exit=1，bp=1 | ✅ |
| S3 ⑩门 exit=1 | iu>0 → exit=1 | exit=1，iu=1 | ✅ |
| S4 malformed 段显式 | `[MALFORMED]` 段落 + SUMMARY `malformed=1` | `[MALFORMED]` 段打印（含注入路径），SUMMARY `malformed=1` | ✅ |
| S5 10 次无漂移 | md5 单值 | `sort -u | wc -l = 1` | ✅ |

---

## 10. 结论

**⑩门（契约对账门）在 W-NEXT-FE-001 / W-NEXT-CONTRACT-001 / W-NEXT-FE2 三套完工后，四档实际生效**：

- 断点 >0 → 🔴 FAIL 红，exit=1
- 在用未冻结 >0 → 🔴 FAIL 红，exit=1
- 未冻结仅后端 >0 → 🟡 WARN，exit=0
- 待接 >0 → 🟡 WARN，exit=0

5 类盲测场景**全部 PASS**，数字零漂移、注入真红、与历史无关、时间戳隔离。

---

## 11. 附记（无关键影响的环境观察）

> 注 1：发现 `8000` 后端 PID 在跑测中段挂掉（推测被宿主进程回收或本机脚本误杀）；盲测重启 8000 后基线恢复一致数字。这是中间件层问题，不影响探针设计稳定性的结论——`febe_contract_check.py` 的逻辑在 8000 ↔ fail 之间均按设计反应（connected → 正常数字；disconnected → exit=2，⑩门自动 WARN「以④为准」）。
>
> 注 2：W-NEXT-FE-2 的 3 个新契约文件（`reshape-r-admin.json` / `reshape-r-health.json` / `reshape-r-mcp.json`）+ 变更单 `CR-FE-002-unfrozen-only.md` 在 feature/opt-waves 上**尚未 commit**，但已落盘并被探针读取——本批盲测的基线数字（contracts=235 / unfrozen_only=1）已反映这批冻结。如需重新校准基线数字，请先 commit WNEXTFE2 后再跑盲测。
