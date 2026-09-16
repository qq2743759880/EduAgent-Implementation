# W-NEXT-FE-001 完工报告 — ⑩门拆四档 + 契约 parser 修相对路径

> 任务：kickoff-WNEXTFE1-gate-4tier-parser-fix.md（FE-BE 治理失效修复 P0）
> 执行者：FE-BE 契约工程师（独立单写者）
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 完成时间：2026-09-16
> 分支：`feature/opt-waves`

---

## 0. 一句话结论

**判定：PASS（五步 GWT 全部以实测数字达成）**。

- ⑩ 门由「仅断点红、其余 WARN」升级为**四档**：`断点 / 在用未冻结` 红（CI 阻断），`未冻结仅后端 / 待接` WARN（不阻断）。
- 契约 parser 不再**静默丢弃**相对路径契约：相对路径经 `/api/admin/courses/` 上下文解析入冻结集合，`malformed=0`。
- 新增第四类差集 `in_use_unfrozen`（前端在用但无契约），实测 **40 条**明细落盘，移交 W-NEXT-CONTRACT-001。

### ⚠️ 对 kickoff 估算的实证修正（trust-but-verify）

kickoff 预估「契约 83→113」「in_use_unfrozen 45 条」。实测证据**纠正**了这两个估算：

| 指标 | kickoff 预估 | 实测 | 说明 |
|------|-------------|------|------|
| 相对路径契约数 | 43 条被丢弃 | **9 个相对字符串**（→13 method+path） | 批判报告 P0-2 的「43」本身是高估 |
| 冻结契约数 | 83 → 113 (+30) | **83 → 90 (+7)** | 9 个相对串里 3 个是绝对集合已有副本（init-chunked/finalize-chunked/bind-session），仅 7 条新增 |
| in_use_unfrozen | 45 条 | **strict 基线 46 条 → parser 修复后 40 条** | parser 修复回收了其中 6 条前端在用接口 |

**结论**：kickoff 的「113 / 45」是粗略上界；本报告以一手实测为准。治理效果（门能拦、差集可数）完全达成，数字更精确。

---

## 1. 五步 GWT 验收（逐条实证）

| GWT | 验收点 | 实测 | 结论 |
|-----|--------|------|------|
| **FE1-G1** | ⑩ 拆四档，in_use_unfrozen>0 红阻断 | `check-demo.mjs` ⑩ → `[FAIL] ⑩`：`在用未冻结 40 条（…CI 红/阻断）`；探针退出码 = **1** | ✅ |
| **FE1-G2** | parser 修复，frozen 数升、malformed=0 | 探针 SUMMARY：`contracts=90`（strict 83 +7），`malformed=0` | ✅ |
| **FE1-G3** | in_use_unfrozen 明细落盘 + 移交 | `deploy/backups/wnextfe1_in_use_unfrozen_20260916.json`（40 条 + 6 条回收对照） | ✅ |
| **FE1-G4** | 4 用例单测全绿 | `pytest` → **6 passed**（正常/断点/在用未冻结/parser修复/解析偏好×2） | ✅ |
| **FE1-G5** | check-demo ⑩ 跑通，注入实验 exit=1 | 真实运行 ⑩ 即红（iu=40>0 → exit 1）；单测 `test_in_use_unfrozen_exit_1` 注入 1 条 → exit 1 | ✅ |

### 关键实测数字（探针 `[SUMMARY]`）

```
breakpoints=0  in_use_unfrozen=40  unfrozen_only=106  to_connect=109
frontend=101  backend=210  contracts=90  malformed=0
```

对照（parser 修复前后）：

| 项 | strict 基线（不解析相对路径） | parser 修复后 |
|----|------------------------------|---------------|
| 冻结契约 method+path | 83 | **90** |
| in_use_unfrozen | 46 | **40** |
| malformed | — | **0** |

---

## 2. 步骤1：⑩ 门拆四档

文件：`edu-agent/scripts/check-demo.mjs`（仅 ⑩ 块 + `in_use_unfrozen` 段，未动其它）。

四档矩阵：

| 档 | 条件 | 判定 | 退出码 |
|----|------|------|--------|
| 断点 `bp>0` | 前端调用后端无此路由 | 🔴 FAIL 红 | 1 |
| 在用未冻结 `in_use_unfrozen>0` | 前端在用 ∩ 后端有 ∩ 契约无 | 🔴 FAIL 红（治理压力核心） | 1 |
| 未冻结仅后端 `unfrozen_only>0` | 后端有、前端未用、契约无 | 🟡 WARN（不阻断） | 0 |
| 待接 `to_connect>0` | 后端有、前端未接 | 🟡 WARN（不阻断） | 0 |
| 后端不可达 `code==2` | OpenAPI 拉不到 | 🟡 WARN（以④为准） | 0 |

退出码规则：`bp + in_use_unfrozen` 任一 >0 → **1**；其余 → 0。

GWT：注入实验——探针真实 in_use_unfrozen=40>0 → ⑩ 红、check-demo 整体 exit≠0（见 FE1-G1/G5）。

---

## 3. 步骤2：契约 parser 修相对路径

文件：`edu-agent/scripts/eval/febe_contract_check.py`

改动：
1. 删除 `if not path.startswith("/api/"): return` 的**静默丢弃**。
2. 相对路径改交 `resolve_relative(methods, rel_path, be_routes)` 解析；解析不了才标 `[MALFORMED]`（独立段输出，不再静默）。
3. `re.sub(r"\[.*?\]", "", path)` 现正确处理可选段标记（如 `chapters[/{id}]` 去括号、保留语义）。
4. `load_contracts(be_routes)` 返回 `(endpoints, malformed)`；无后端上下文时相对路径全部进 malformed（显式可见）。

`resolve_relative` 解析优先级（避免误匹配到 `/api/cohorts` 等其它资源）：
1. 已知父上下文 `/api/admin/courses/<rel>`（verified_today_batch1 嵌套资源所在域）——命中即采用，不回退；
2. 裸 `/api/<rel>`；
3. 后缀兜底（优先 `/api/admin/courses/` 候选）；
4. 基路径无方法命中时尝试 `<rel>/{x}` 子路由（处理 `chapters` 这类「集合无 GET/DELETE、仅 {x} 子路由有」的资源）。

实测 9 个相对字符串解析结果：

| 相对路径 | 解析为 | 状态 |
|----------|--------|------|
| cohorts/{id}/modules | /api/admin/courses/cohorts/{x}/modules | 新增契约 |
| modules/{id}/sessions | /api/admin/courses/modules/{x}/sessions | 新增契约 |
| sessions/{id}/assets | /api/admin/courses/sessions/{x}/assets (GET) | 新增契约 |
| videos/init-chunked | /api/admin/courses/videos/init-chunked | 绝对集合已有（副本） |
| videos/upload-chunk/{u}/{i} | /api/admin/courses/videos/upload-chunk/{x}/{x} | 新增契约 |
| videos/finalize-chunked | /api/admin/courses/videos/finalize-chunked | 绝对集合已有（副本） |
| videos/bind-session | /api/admin/courses/videos/bind-session | 绝对集合已有（副本） |
| videos/{id}/transcode-status | /api/admin/courses/videos/{x}/transcode-status | 新增契约 |
| chapters (GET/DELETE) | /api/admin/courses/chapters/{x} (GET,DELETE) | 新增契约（非 video-chapters） |

净新增 **7** 条唯一契约（83→90）。`malformed=0`。

---

## 4. 步骤3：in_use_unfrozen 第四类差集（落盘 + 移交）

定义：`in_use_unfrozen = (前端调用 ∩ 后端路由) − 冻结契约`（method+path）。

实测 **40 条**（前端天在用、但冻结契约缺失，含生产主链路 `POST /api/chat/stream`、`GET /api/chat/sessions/{x}/history`、`POST /api/trade/order` 等）。

落盘：`deploy/backups/wnextfe1_in_use_unfrozen_20260916.json`
- `summary`：四方计数 + strict/修复后契约数对照
- `in_use_unfrozen`：40 条 `{method, path}` 完整清单
- `recovered_by_parser_fix`：6 条因 parser 修复被自动回收的前端在用接口（cohorts/{x}/modules、modules/{x}/sessions、sessions/{x}/assets、videos/{x}/transcode-status、upload-chunk/{x}/{x}、chapters/{x}）
- `notes`：口径与 kickoff 估算修正说明

**移交 W-NEXT-CONTRACT-001**：以该 JSON 的 40 条为补冻结契约优先级清单（按生产链路风险排序）。

---

## 5. 步骤4：回归单测

文件：`edu-agent/tests/test_febe_contract_check.py`（新建）

| 用例 | 内容 | 结果 |
|------|------|------|
| test_normal_exit_0_ok | 无漂移 → run()=0 | ✅ |
| test_breakpoint_exit_1 | 注入 1 断点 → run()=1 | ✅ |
| test_in_use_unfrozen_exit_1 | 注入 1 在用未冻结 → run()=1 | ✅ |
| test_parser_fix_real_backend | 真实后端：契约数上升、malformed=0、关键新契约入集 | ✅（后端不可达时 skip） |
| test_resolve_relative_prefers_admin_courses | `cohorts/{id}/modules` → /api/admin/courses/ 而非 /api/cohorts/ | ✅ |
| test_resolve_relative_chapters_not_video | `chapters` → /api/admin/courses/chapters/{x} 而非 video-chapters | ✅ |

运行：`edu-agent/.venv/Scripts/python.exe -m pytest edu-agent/tests/test_febe_contract_check.py --noconftest` → **6 passed**。

> 注：`--noconftest` 仅为绕过仓库既有 `tests/conftest.py` 对 `app.config` 的环境变量依赖（与本任务无关），本测试自身不依赖任何业务代码/数据库。

---

## 6. 步骤5：⑩ 门集成（真实运行）

`node edu-agent/scripts/check-demo.mjs` 实测：
- `[FAIL] ⑩. 契约对账门 …（断点·在用未冻结 红 / 待接·未冻结 WARN）(946ms)`
- ⑩ 详情：`在用未冻结 40 条（前端实际在用的接口无冻结契约，CI 红/阻断；详见 febe_contract_check.py ② 段，清单移交 W-NEXT-CONTRACT-001）`
- 整体汇总红项含 ⑩（另 ⑤⑦⑧⑨⑪⑬ 为前端 3000 未起/其它基础设施红项，与本任务无关）。

四档各自行数均在探针 `[SUMMARY]` 中体现，⑩ 解析一致。

---

## 7. 红线遵守

| 红线 | 验证 | 结果 |
|------|------|------|
| 单写者锁 | 开工建 `edu-agent/scripts/eval/wnextfe1.lock`，完工删 | ✅ |
| 仅限文件归属 | 改 `febe_contract_check.py` / `check-demo.mjs(⑩)` / 新建 `test_febe_contract_check.py` / `deploy/backups/*.json` / 本报告；**未碰** `app/**`、前端、`contracts/*` | ✅ |
| 服务未重启 | 8000/3000 运行中未重启；验证用既有实例 | ✅ |
| Mimosa 约束 | host 写死 127.0.0.1:8000、DB 参数绑定不适用（纯只读无 DB）、密钥仅环境变量 | ✅ |
| 纯只读 | 探针仅 GET OpenAPI + 读本地 JSON/HTML，无 DB 写入 | ✅ |
| git 纪律 | commit 走路径限定 `git add` + `git commit`（禁 `scripts/p1_commit.py`）；`feature/opt-waves` 分支 | ✅ |

---

## 8. 交付 / 回执

提交（单任务单 commit，commit 后两关校验）：
- `feat(contract): WNEXTFE1 ⑩门拆四档 + 契约 parser 修相对路径`

变更文件：
1. `edu-agent/scripts/eval/febe_contract_check.py`（parser 修复 + in_use_unfrozen 差集 + 四档 SUMMARY + 退出码）
2. `edu-agent/scripts/check-demo.mjs`（⑩ 四档门）
3. `edu-agent/tests/test_febe_contract_check.py`（新建，6 用例）
4. `deploy/backups/wnextfe1_in_use_unfrozen_20260916.json`（新建，40 条明细）
5. `test-reports/WNEXTFE1-completion-report.md`（本报告）

**完工回执**（commit 后补填哈希）：
- commit：`<见末行>`
- 报告：`test-reports/WNEXTFE1-completion-report.md`
- GWT：FE1-G1~G5 全绿（数字见 §1）
- in_use_unfrozen JSON：`deploy/backups/wnextfe1_in_use_unfrozen_20260916.json`（40 条）

---

## 9. 后续（移交）

- **W-NEXT-CONTRACT-001** 领取 `deploy/backups/wnextfe1_in_use_unfrozen_20260916.json` 的 40 条，按生产链路风险（chat 主链路 / 交易 / 社区）优先级补冻结契约。
- 补完后 `in_use_unfrozen` 归零，⑩ 门转绿（exit 0），CI 不再因本批漂移阻断。
