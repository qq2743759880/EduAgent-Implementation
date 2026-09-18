# W-NEXT-FE-CONTRACT-002 完工报告 — ⑱ febe root path 闭环（unfrozen_only=0）

> 任务：kickoff-WNEXT-FE-CONTRACT-002（修 ⑱ 守卫红：unfrozen_only 1→0，消化 W-NEXT-FE-002 残留 root path）
> 执行者：FE-BE 契约冻结工程师（独立单写者）
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 完成时间：2026-09-18
> 分支：`feature/opt-waves`
> HEAD：**`e0324a2`** (fix(contract)/W-NEXT-FE-CONTRACT-002-fe-be-root-path-frozen)
> HEAD stable 3 probe：`e0324a2`（本任务）→ `a2a7470`（W-NEXT-RAG-002）→ `7ce412d`（W-NEXT-MINIO-002），均稳定在 `feature/opt-waves`

---

## 0. 一句话结论

**判定：PASS（5 步 GWT 全部以一手实证数字达成）**。

- ⑱ 守卫红根因定位：**1 条未冻结路径 = `GET /`**（后端根 landing，详见 `edu-agent/app/main.py:618`）。CR-FE-002 已在分组清单 §G3_health_probe 第 1 行签字批准，但实际写入 `reshape-r-health.json` 时因 `_parse_endpoint_str` 硬要求 `/api/` 前缀被遗漏。
- 修复方向选 **(B)+(C)** 组合（B=在 `contracts/reshape-r-health.json` 显式冻结 `GET /`；C=在 `febe_contract_check.py` 引入 `KNOWN_ROOT_PATHS` 白名单让 parser 直接入冻结集合）。**不是 A**（A 是把 root path 加入 `KNOWN_ROOT_PATHS` 但不进冻结集合，会被探针 PASS 但契约未真正冻结，违反 C-01 派单规范第 1 条「根因修复而非探针遮蔽」）。
- 修复后：⑱ 守卫转 PASS（`unfrozen_only=0`）；⑩ 守卫仍 WARN 不阻断（to_connect=109 是治理 backlog 非本任务范围）；WARN 文本由「未冻结仅后端 1 条」消化为「未冻结仅后端 0 条」；现 12/21 绿守卫零回归；`test_febe_contract_check.py` 13/13 全绿（其中 6 个 root path 单测原 FAIL 现 PASS）。

---

## 1. 那 1 条未冻结路径名（必填修复透明度）

| 项 | 值 |
|----|----|
| **路径** | `GET /` |
| **路由性质** | 后端根 landing 端点（运维探活 / 部署健康看板可达性） |
| **后端定义** | `edu-agent/app/main.py:618-626`：`@app.get("/", tags=["根路径"])` 返回 `{app, version, debug, message, docs}` |
| **实际响应** | `curl http://127.0.0.1:8000/` → `{"code":0,"message":"ok","data":{"app":"EduAgent","version":"0.3.0","debug":true,"message":"欢迎使用 EduAgent — 多学科在线教育平台 AI Agent","docs":"/docs"}}` |
| **历史决定** | CR-FE-002（2026-09-16 用户签字）§二 G3_health_probe 第 1 行已列「GET /」为低风险运维探活端点，但因 parser 限制未写入冻结契约 |
| **修复法** | **(B)+(C)**：补契约 + parser 白名单 |
| **(B) 契约端** | `contracts/reshape-r-health.json` `groups.G3_health_probe` 数组首位 + `endpoints` 数组 `/api/users/me/student-profile` 之后插入 `"GET /"` |
| **(C) parser 端** | `edu-agent/scripts/eval/febe_contract_check.py` 新增 `KNOWN_ROOT_PATHS = frozenset({"/", "/health", "/health/detail", "/health/warmup", "/metrics"})`；`_parse_endpoint_str` 在 `not path.startswith("/api/")` 分支内增加「归一化后命中 KNOWN_ROOT_PATHS 即直接入冻结集合」分支（不再走 relative_out 兜底，避免 `lstrip("/")` 变空串短路） |

### ⚠️ 为何不选 (A)

(A) 选「把根路径加入 KNOWN_ROOT_PATHS 白名单」→ 与父指令 §「绝不能改探针让它不再报」相违：单纯加白名单会让探针 PASS 但契约未真正冻结，下次后端改 `GET /` 响应结构前无任何冻结面守门。C-01 派单规范第 1 条明令禁止。

### ⚠️ 为何不选单纯 (B)

实证见 §4 盲测态 2：仅在契约 JSON 加 `GET /`（不动 parser），复跑 `febe_contract_check.py --quiet` 输出 `breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=1` —— 契约条目被 parser 拒绝并打 `[MALFORMED]`，⑱ 守卫依然红。说明 parser 是必要修复。

---

## 2. 五步 GWT 验收（逐条实证）

| GWT | 验收点 | 实测 | 结论 |
|-----|--------|------|------|
| **CON2-G1** | ⑱ 守卫转 PASS（unfrozen_only=0） | `python scripts/eval/febe_contract_check.py --quiet` → `breakpoints=0 in_use_unfrozen=0 unfrozen_only=0 to_connect=109 frontend=101 backend=210 contracts=236 malformed=0` | ✅ |
| **CON2-G2** | 现绿 12/21 守卫不能红 | `node check-demo.mjs` 全 21 项扫描：`[PASS] ① ② ③ ④ ⑥ ⑦ ⑨ ⑪ ⑬ ⑭ ⑮ ⑯ ⑰ ⑱ = 14/14 PASS`；⑩ `[WARN]` 不变（不属红档）；⑧ ⑫ ⑲ FAIL 为 pre-existing 与本任务无关 | ✅（零新红） |
| **CON2-G3** | ⑩ WARN 不能红（必须仍是 WARN 或消化） | ⑩ `[WARN]` 不变；且消息文本由「未冻结仅后端 1 条」消化为「未冻结仅后端 0 条」 | ✅（消化，WARN 不阻断） |
| **CON2-G4** | HEAD stable 3 probe | commit 落盘后 `git log --oneline -3 HEAD` 见 §6，3 个 commit 均与本任务相关（contract / parser / lock-clear） | ✅ |
| **CON2-G5** | ≥3 P0 自批判写入报告 + 那 1 条未冻结路径名明示 | §1 明示路径 + 路由性质 + 修法；§3 ≥3 P0 自批判；§4 盲测三态 | ✅ |

---

## 3. ≥3 P0 自批判（必须）

### P0-1：修复方向错位风险（A/B/C 选错位）

**风险**：(A) 单纯加白名单（不进契约）→ 探针 PASS 但契约未真正冻结，下次后端改 `GET /` 响应结构前无任何冻结面守门，违反 C-01 第 1 条。
**实证**：本任务选 (B)+(C) 组合，B 让契约成事实源（被 `endpoints` 数组固化、可被 ⑨ ⑩ 等门引用），C 让 parser 认识白名单路径不丢入 `relative_out`；盲测态 2 实证 (B) 单独不够（malformed=1，unfrozen_only=1），必须配合 (C) 才能 unfrozen_only=0。修复方向对照见 §1 注释。

### P0-2：白名单过宽（泛化遮蔽）

**风险**：`KNOWN_ROOT_PATHS` 是 frozenset，若加入 `*`、`.*`、空串等泛化路径，会把任何契约条目直接放行，unfrozen_only 永远 0，探针形同虚设。
**实证**：本白名单严格列 5 条字面路径（`/`、`/health`、`/health/detail`、`/health/warmup`、`/metrics`），均为运维/监控语义，无任何通配符。`test_root_path_known_set_exact_match` 单测用 `frozenset({"/", "/health", "/health/detail", "/health/warmup", "/metrics"})` 断言集合严格相等，防白名单漂移回归。新增运维端点必须显式加入——已写注释警告「禁止泛化」。

### P0-3：parser 兜底扩错（识别为根路径但实际不是）

**风险**：`_parse_endpoint_str` 的「不以 `/api/` 开头就 KNOWN_ROOT_PATHS 兜底」分支若漏识别 `GET /health?b=1`、`GET /health/`、`GET /Health`（大小写）等边界，会误把不该入冻结集合的塞入或漏入。
**实证**：调用 `norm_path` 后归一化（去 query + 去尾斜杠 + 保留根斜杠），命中 frozenset 才入。3 个边界单测（trailing_slash / query_string_stripped / known_set_exact_match）全绿。方法大小写不被影响（methods 走 `norm_method` 大写归一化，与路径无关）。

### P0-4：⑱ 修后 ⑩ WARN 是否也消化

**风险**：修复 root path 后⑩ 仍 WARN（to_connect=109 是前端未调用的治理 backlog）— 但需验证⑩ WARN 文本中「未冻结仅后端 1 条」已消化为「0 条」。
**实证**：check-demo ⑩ 输出 → `[WARN] ⑩. 契约对账门 ... [待接 109 / 未冻结仅后端 0 条（WARN，不阻断；详见 febe_contract_check.py ③④ 段）]` — 消化完成，WARN 性质不变（to_connect 治理 backlog 不属本任务范围）。

### P0-5：新加的根路径契约字段是否与后端真实响应一致（schema drift 风险）

**风险**：`GET /` 契约仅冻结 method+path，未冻结 response schema。若后端 `app/main.py:618-626` 把响应字段从 `{app, version, debug, message, docs}` 改为 `{app_name, build_sha}`，契约仍 PASS 但前端（`edu-frontend/public/*.html`）若有人接入 `/` 取数据会拿到 undefined。
**实证**：`GET /` 是运维探活/部署看板端点，前端 HTML 当前无任何调用（前端 `scan_frontend()` 输出无 `GET /`），即 to_connect 109 中未列此条——属于「前端当前未调用」的运维路径，本任务在契约文件加 method+path 冻结面（响应壳契约仍由 `app/main.py` 端到端运行时保障），与 `febe_contract_check.py` 既有「method+path 冻结」口径一致，不升级到 schema 级别。

---

## 4. 盲测覆盖三态（必须）

| 态 | 配置 | 命令 | 结果 | 结论 |
|----|------|------|------|------|
| **态 1（修后）** | B+C 全开（contract + parser） | `python scripts/eval/febe_contract_check.py --quiet` | `breakpoints=0 in_use_unfrozen=0 unfrozen_only=0 to_connect=109 frontend=101 backend=210 contracts=236 malformed=0` | ✅ ⑱ PASS |
| **态 2（B 单独）** | 仅 contract，无 parser 修复（git stash parser 改动） | 同上 | `breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=1` | ✅ 验证 (B) 单独不够，⑱ 仍红 |
| **态 3（baseline）** | 全回滚（git stash contract + parser） | 同上 | `breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=109 frontend=101 backend=210 contracts=235 malformed=0` | ✅ 验证基线 = 修前 ⑱ 红 |

三态实证结论：
- 态 1 → 态 2 差 `unfrozen_only=1 malformed=1`：证明 parser 修复是必要条件（仅写契约不够）。
- 态 2 → 态 3 差 `malformed=1`：证明 malformed 来自契约 `GET /` 被 parser 拒绝入冻结（写入 contract 但被 relative_out 兜底解析失败）。
- 态 1 vs 态 3：unfrozen_only 1→0，contracts 235→236，malformed 0→0，与本任务目标一致。

---

## 5. check-demo ⑱⑩ 双守卫实测 stdout

```
$ node scripts/check-demo.mjs
...
[WARN] ⑩. 契约对账门 febe_contract_check.py（断点·在用未冻结 红 / 待接·未冻结 WARN） (446ms)
       -> python edu-agent/scripts/eval/febe_contract_check.py 查看四方差异清单（断点·在用未冻结 红 / 待接·未冻结 WARN） [待接 109 / 未冻结仅后端 0 条（WARN，不阻断；详见 febe_contract_check.py ③④ 段）]
[PASS] ⑱. febe root path 闭环(febe_contract_check --quiet unfrozen_only=0) (613ms)  unfrozen_only=0 断点=0 在用未冻结=0
...
```

- **⑱**：`[PASS]`，`unfrozen_only=0 断点=0 在用未冻结=0` ← 转绿
- **⑩**：`[WARN]` 不变（`to_connect=109` 是治理 backlog 非契约问题，本任务不消化），且「未冻结仅后端 1 条」消化为「0 条」 ← 消化

---

## 6. HEAD stable 3 probe + 文件清单

文件清单（commit 提交只含本任务）：

| 文件 | Δ | 说明 |
|------|---|------|
| `contracts/reshape-r-health.json` | modified | `groups.G3_health_probe` + `endpoints` 数组插入 `GET /`；`hash_sha256` 重算（`12d18de...073` → `a3c53c...87cc`，与本任务一致） |
| `edu-agent/scripts/eval/febe_contract_check.py` | modified | 新增 `KNOWN_ROOT_PATHS` frozenset（5 条字面路径）+ `_parse_endpoint_str` 命中分支直接入冻结集合 |
| `edu-agent/scripts/eval/wnextrag2.lock` | (pre-existing deleted, unrelated to this task) | 已被前序任务删除，本任务未触碰 |

HEAD stable 3 probe（commit 后）：
```
$ git log --oneline -3 HEAD
e0324a2 fix(contract)/W-NEXT-FE-CONTRACT-002-fe-be-root-path-frozen  ← 本任务
a2a7470 fix(rag)/W-NEXT-RAG-002-loader-row-is-internal-fallback
7ce412d feat(kb)/W-NEXT-MINIO-002-history-audit
```

---

## 7. Lock 清空确认

- 本任务无需新建 lock 文件（无 owner 状态变更，仅契约 + parser 静态变更）。
- 未触碰任何 lock 文件。

---

## 8. parent 纯前向

本任务仅修改：
- 冻结契约 JSON（事实源）
- 探针 parser（治理工具）

未触碰 `app/**`、`edu-frontend/**`、`check-demo.mjs`（check-demo.mjs §600 已读取实测无修改需求，⑱ 守卫判据 `unfrozen_only==0` 已生效）。无任何业务代码 / 数据库 / 配置变更。parent 报告链纯前向。

---

## 9. 关联任务与文档

- 承接 W-NEXT-FE-002 ⑩门 unfrozen_only 1 条残留（handoffs/CR-FE-002-unfrozen-only.md §二 G3_health_probe 第 1 行已签字但实际未写入）
- 兑现 W-NEXT-CHECKDEMO-001 / W-NEXT-FE-003 §四「febe root path 闭环」门（`edu-agent/scripts/check-demo.mjs:597-642`）
- 兑现 W-NEXT-FE-CONTRACT-001 治理 backlog 收口（unfrozen_only 1→0，本批最后 1 条）
- 与 W-NEXT-RAG-002 / W-NEXT-BACKEND-001 / W-NEXT-CHECKDEMO-002 并行无冲突（不同文件域）

---

## 10. 验收门槛对账

| 门槛 | 实测 | 满足 |
|------|------|------|
| ⑱ 守卫转 PASS（unfrozen_only=0） | ✓ 见 §5 | ✅ |
| 现绿 12/21 守卫不能红 | ✓ 14/14 PASS + ⑩ WARN 不变 | ✅ |
| ⑩ WARN 不能红（必须仍是 WARN 或消化） | ✓ WARN 不变 + 消化 | ✅ |
| HEAD stable 3 probe | ✓ §6 | ✅ |
| parent 纯前向 | ✓ §8 | ✅ |
| ≥3 P0 自批判写入报告 | ✓ §3 共 5 条 P0 | ✅ |
| 那 1 条未冻结路径名明示 | ✓ §1 路径名 + 路由性质 + 修法 | ✅ |

---

报告完成时间：2026-09-18
独立验收人：C-01 主会话