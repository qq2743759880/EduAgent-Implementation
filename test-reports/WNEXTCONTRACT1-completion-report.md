# W-NEXT-CONTRACT-001 完工报告 — 补冻结 40 条前端在用未冻结契约

> 任务：kickoff-WNEXTCONTRACT1-in-use-unfrozen-freeze.md（FE-BE 治理压力 P0）
> 执行者：后端契约工程师（独立单写者）
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 完成时间：2026-09-16
> 分支：`feature/opt-waves`

---

## 0. 一句话结论

**判定：PASS（五步 GWT 全部以实测数字达成）**。

- 承接 W-NEXT-FE-001 ⑩门红档差集（40 条 `in_use_unfrozen`），新建 `contracts/reshape-r-core.json` 全部冻结。
- 复跑 `febe_contract_check.py`：`in_use_unfrozen` **40 → 0**，⑩门转绿（exit 0），`contracts` **90 → 130**。
- 变更单 `handoffs/CR-FE-001-in-use-unfrozen.md` 用户签字（方案 A 单文件）后落地。

### 对 kickoff 估算的实证修正（trust-but-verify）

kickoff 预估「45 条 / 冻结 83→128」。W-NEXT-FE-001 实测纠正为 **40 条 / 冻结 90→130**（parser 修复回收 6 条前端在用接口 + 7 条相对路径契约入集）。本报告以一手实测为准。

---

## 1. 五步 GWT 验收（逐条实证）

| GWT | 验收点 | 实测 | 结论 |
|-----|--------|------|------|
| **CT-G1** | 40 条分组表 + 风险评级 | 见 §2：G1(11,P0)/G2(6,P0)/G3(1,P1)/G4(1,P1)/G5(21,P2) | ✅ |
| **CT-G2** | 变更单落盘 + 标注待签 | `handoffs/CR-FE-001-in-use-unfrozen.md`（draft→签字） | ✅ |
| **CT-G3** | 用户签后冻结 40 条，frozen 90→130 | 新建 `reshape-r-core.json`（40 条 endpoints，sha256 `2f08cb4a…`） | ✅ |
| **CT-G4** | febe 复跑对账 in_use_unfrozen→0 | `[SUMMARY] …in_use_unfrozen=0… contracts=130 … malformed=0`；exit 0 | ✅ |
| **CT-G5** | 契约相关测试全绿（零回归） | `pytest tests/test_febe_contract_check.py --noconftest` → **6 passed** | ✅ |

### 关键实测数字（冻结前后探针 `[SUMMARY]` 对照）

| 项 | 冻结前（W-NEXT-FE-001 末态） | 冻结后（本单） |
|----|------------------------------|----------------|
| breakpoints | 0 | 0 |
| **in_use_unfrozen** | **40** | **0** |
| unfrozen_only | 106 | 106（不变，WARN 不阻断） |
| to_connect | 109 | 109（不变，WARN 不阻断） |
| frontend | 101 | 101 |
| backend | 210 | 210 |
| **contracts（冻结契约数）** | **90** | **130**（+40） |
| malformed | 0 | 0 |

> 注：`unfrozen_only`(106) 与 `to_connect`(109) 属 WARN 档（后端有、前端未用 / 前端未接），不在本单治理范围，不阻断 CI。

---

## 2. 步骤1：40 条分组（按风险面）

| 组 | 风险 | 条数 | 覆盖 |
|----|------|------|------|
| G1 生产主链路 | P0 | 11 | chat(stream/history/del) / 社区(点赞·评论·详情) / 课程评价 / 收藏 |
| G2 教学·课程域 | P0 | 6 | coupons / quiz / series·cohorts / study(access·outline·sessions) |
| G3 交易·订单 | P1 | 1 | trade/order（业务边界最敏感） |
| G4 智能体·MCP | P1 | 1 | mcp/servers/{x}/discover |
| G5 管理端·知识库 | P2 | 21 | 课程 CRUD(12) / 题库 CRUD(6) / 用户(role·status)(2) / 知识库 partitions(1) |

完整 40 条 method+path 见 `contracts/reshape-r-core.json` 的 `endpoints` 数组与 `groups` 元数据。

---

## 3. 步骤2/3：变更单 + 落地冻结

- 变更单：`handoffs/CR-FE-001-in-use-unfrozen.md`（G1–G5 分组、落盘策略 A/B、签署区）。
- 用户签（AskUserQuestion）：**方案 A（单文件 `reshape-r-core.json`）+ 签字落地冻结**。
- 落地：40 条写入 `contracts/reshape-r-core.json` 的 `endpoints`，附 `groups` 元数据；`hash_sha256` 留痕。
- 既有 reshape-r-aci/r-chunk/r-hitl **未改动**（方案 A 不触碰）。

---

## 4. 步骤4：febe 复跑对账

命令：`python edu-agent/scripts/eval/febe_contract_check.py`
- ⑩门：`[② 在用未冻结] 共 0 条 → PASS`，整体 exit=0（绿）。
- `[SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=106 to_connect=109 frontend=101 backend=210 contracts=130 malformed=0`

---

## 5. 步骤5：契约补全回归

`edu-agent/.venv/Scripts/python.exe -m pytest edu-agent/tests/test_febe_contract_check.py --noconftest`
- 6 passed（正常 / 断点 / 在用未冻结 / parser修复 / 解析偏好×2）。零回归。
- 既有 7 批判不改契约本身，仅补充冻结面（本单职责）。

---

## 6. 红线遵守

| 红线 | 验证 | 结果 |
|------|------|------|
| 单写者锁 | 开工建 `edu-agent/scripts/eval/wnextcontract1.lock`，完工删 | ✅ |
| 仅限文件归属 | 新增 `contracts/reshape-r-core.json` + `handoffs/CR-FE-001-in-use-unfrozen.md` + 本报告；**未碰** `app/**`、前端、`febe_contract_check.py` | ✅ |
| 服务未重启 | 8000/3000 运行中未重启；验证用既有实例 | ✅ |
| Mimosa 约束 | 契约为静态 JSON（无 host/DB/密钥） | ✅ |
| git 纪律 | 路径限定 `git add` + `git commit`（禁 `scripts/p1_commit.py`）；`feature/opt-waves` 分支；commit 后 `git rev-parse HEAD` 校验 | ✅ |

---

## 7. 交付 / 回执

提交（单任务单 commit）：`feat(contract): WNEXTCONTRACT1 补冻结 40 条 in_use_unfrozen 契约`

变更文件：
1. `contracts/reshape-r-core.json`（新建，40 条 endpoints + groups + sha256 `2f08cb4a…`）
2. `handoffs/CR-FE-001-in-use-unfrozen.md`（新建，变更单，已签）
3. `test-reports/WNEXTCONTRACT1-completion-report.md`（本报告）

**完工回执**：
- 契约文件：`contracts/reshape-r-core.json`（sha256 `2f08cb4a57ee373f2a8478eb1f98842a257d83ac42c3175bcffee851993870bf`）
- 变更单：`handoffs/CR-FE-001-in-use-unfrozen.md`
- 报告：`test-reports/WNEXTCONTRACT1-completion-report.md`
- GWT：CT-G1~G5 全绿（数字见 §1）
- 冻结前后：`in_use_unfrozen 40→0`，`contracts 90→130`，`malformed 0`，⑩门 exit 0

---

## 8. 后续

- W-NEXT-FE-001 ⑩门复跑已归零（红档清空）；CI 不再因本批「前端无契约在用」漂移阻断。
- 盲测衔接 T16：冻结后 febe 复跑一致 + 后端改 40 条里任一条触发变更单流程。
- `unfrozen_only`(106) / `to_connect`(109) 仍 WARN，按需走后续补契约或待接裁定（非本单范围）。
