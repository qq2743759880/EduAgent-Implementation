# W-NEXT-FEBE-CANON-SYNC-001 完工报告

> 任务：⑱ 红根因闭环——PAY-GATE 新端点 `POST /payment-notifications/channel` 契约面冻结 + febe canonical 桶同步 + tests 侧 overlay 移交清偿。
> 分支：feature/opt-waves　执行日期：2026-09-18（yy 串行流水线 C-01，编排者逐断言独立实证验收）
> 红线遵守：仅触碰 4 个归属文件（contracts/reshape-b.json、edu-agent/scripts/eval/febe_contract_check.py、edu-agent/tests/test_febe_contract_check.py、本报告）；未触 trade/**、app/**、其他契约；lock（edu-agent/scripts/eval/wnextfebecanon1.lock）commit 前已删。

---

## 1. Commit

| 项 | 值 |
|----|-----|
| commit | `（见 git log 首行，W-NEXT-FEBE-CANON-SYNC-001）` |
| 基线（任务起点） | 65b1b81（TEST-BASE），PAY-GATE 端点=062704a |
| 变更文件 | 3 个代码/契约文件 + 本报告，共 4 个 |

```
contracts/reshape-b.json                            | +12 -2（endpoints +1 字符串冻结条目、amendments +1 条、hash 重算）
edu-agent/scripts/eval/febe_contract_check.py       | +1（NEXTJS_OPS_ENDPOINTS 登记 1 条，最小 diff）
edu-agent/tests/test_febe_contract_check.py         | overlay 删除 + expected_ops 回归锁（净 ±注释）
test-reports/WNEXTFEBECANON1-completion-report.md   | 本报告（新增）
```

## 2. Amendment 内容（contracts/reshape-b.json）

机器可解析冻结条目（`endpoints` 数组追加，febe parser 只解析 endpoints/verified_\* 的**字符串**条目，见 §6 P0-3）：

```json
"POST /payment-notifications/channel"
```

provenance amendment（`amendments` 数组追加）：

```json
{
 "id": "PAY-GATE-346",
 "signed": "用户会话授权流水线内冻结(W-NEXT-FEBE-CANON-SYNC-001 canonical 同步,2026-09-18)",
 "method": "POST",
 "path": "/payment-notifications/channel",
 "source": "PAY-GATE commit 062704a 承接 tracker 346(真实支付渠道回调验签闸门)",
 "auth": "闸门三关:验商户+RSA2 验签+分单位验金额(run_channel_gates;缺 key=50301 fail closed,任何一关不过=拒绝+[PAY-GATE-AUDIT] 审计,无旁路)",
 "note": "服务端对服务端回调,前端永不接入(febe ops 桶);mock 渠道走既有 mock-notify 端点,鉴权语义零变化;机器可解析冻结条目=本文件 endpoints 数组的字符串形态(febe parser 只解析 endpoints/verified_* 字符串列表,不解析 amendments)"
}
```

"闸门三关"措辞与 062704a commit message（"新端点 POST /payment-notifications/channel（服务端对服务端，鉴权=闸门三关）"）及 `channel_verify.py::run_channel_gates` docstring（"②商户 → ③签名 → ④金额，三关全过返回 True"）逐字对齐，非转述。

## 3. hash_sha256 重算方法

- **算法（既有，WNEXTFECONTRACT-002 确立）**：`sha256( json.dumps(原JSON去掉hash_sha256键, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") )`。
- **算法溯源实证**：该算法对 `contracts/reshape-r-health.json` 现值精确复现（`a3c53c5c...87cc` MATCH），为仓库内唯一可复现的契约 hash 先例。
- **新值**：`f398d7a9e7faa1654a1b930c8e0ac9c46a4bae8a9ad520dd9c9d4cb546aeba25`（写回后 round-trip 复验 OK）。
- **诚实披露**：reshape-b.json 旧值 `b7b506b7...` 在 75 种序列化变体（sort_keys × ensure_ascii × indent × separators × 原始字节挖除）下均不可复现——疑为 a1891b0 创建时对中间态手算；且 `tests/test_contract_mcp_health_async.py:4` 文档串引用的是更老的 `b6772f8d`。**全仓无任何机器校验该字段**（febe_contract_check.py / tests / CI 均不读 hash_sha256），详见 §6 P0-2。

## 4. 差集清单（openapi vs febe known 集，逐条实测）

实测方法：live 8000 `/openapi.json` → `backend_routes` = 216 条，对比「冻结契约(241) ∪ NEXTJS 四桶 ∪ 前端在用(144 中在用部分)」全集：

| 差集口径 | 修复前 | 修复后 |
|---|---|---|
| `unfrozen_only`（后端−冻结−前端在用） | **1 条：`POST /payment-notifications/channel`** | **0** |
| `uncategorized`（待接−四桶） | 1 条（同上） | 0 |
| FULL DIFF（be − (frozen ∪ buckets ∪ fe_in_use)） | 1 条（同上） | 0 |
| breakpoints | 0 | 0 |
| in_use_unfrozen | 0 | 0 |
| plan_broken | 0 | 0 |
| 待接分类 | — | plan 6 / deferred 28 / ops 7 / unassigned 31 = **72/72 全归类** |

**结论：除本端点外无任何其他后端新增端点漏登记**（KG+Analytics 5 条已于 2026-09-18 入 NEXTJS_UNASSIGNED，PAY-GATE 仅新增此 1 端点，openapi 全量比对实证）。

## 5. ⑱ 转 PASS 与 check-demo 终态输出（真机实测）

修复前基线（本任务首跑）：`[SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=1 to_connect=72 frontend=144 backend=216 contracts=241 malformed=0`。

修复后 `febe_contract_check.py --quiet`：`[SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=0 to_connect=72 frontend=144 backend=216 contracts=242 malformed=0`（contracts 241→242，新冻结条目入集直验 `("POST","/payment-notifications/channel") in contracts == True`，malformed=0）。

check-demo 终态（`node scripts/check-demo.mjs --no-color`，**exit=0**）：

```
[PASS] ⑱. febe root path 闭环(febe_contract_check --quiet unfrozen_only=0) (1298ms)  unfrozen_only=0 断点=0 在用未冻结=0
[WARN] ⑩. 契约对账门 ... [待接 72 / 未冻结仅后端 0 条（WARN，不阻断；详见 febe_contract_check.py ③④ 段）]
汇总: 绿 21/21,WARN ⑧、⑩、㉒ —— 演示环境就绪 (检查耗时 145444ms)
```

**⑱ FAIL→PASS、绿 17/21→21/21、WARN 收敛为预期的 ⑧(DEBUG 开发态后门 advisory)/⑩(待接 72 治理 backlog)/㉒(object_key 历史复用留痕)**，与编排者终验目标完全一致；⑩ 中"未冻结仅后端"由 1→0。live chat 200（⑩⑫⑭ 同轮实测正常）。

## 6. P0 自批判（5 项）

1. **【P0】编排者简报对契约组的归属断言与仓库事实不符**：简报称 reshape-b.json 为"trade/payment 契约组（看 mock_notify 等既有支付端点登记方式）"——实测 reshape-b.json 是 MCP health-scan 契约（planId reshape-b，endpoints 全为 /api/mcp/health-scan 系 dict）；支付回调组实为 **reshape-r-health.json `G3_trade_payment`**（`POST /payment-notifications/mock` 在此，姊妹条目）。按红线"禁碰其他契约"，机器可解析冻结条目按简报落 reshape-b.json endpoints、amendments 注明双登记关系；**语义归属偏差已披露**：channel 的 canonical 语义归宿应为 reshape-r-health.json G3_trade_payment，后续如做契约文件重组需走变更单迁移（febe 判定按全 reshape-\* 扁平并集，文件边界不影响冻结效力，仅影响文档检索）。
2. **【P0】hash_sha256 是"治理幻觉"字段**：全仓零机器校验（parser/tests/CI 均不读），旧值不可复现（75 变体穷举），测试文档串还引用着两代前的旧 hash——契约完整性实际靠 febe 对账而非 hash。本次按唯一可复现先例（WNEXTFECONTRACT-002 算法，reshape-r-health.json 复验一致）重算并 round-trip 验证；**建议**：后续给 febe 加 hash 复验维或显式废弃该字段，避免"以为有校验"。
3. **【P0】"amendments 追加一条"本身不产生冻结效力**：`load_contracts` 只解析 endpoints/verified_read_21/verified_today_batch1 的字符串条目 + resume_endpoint，**amendments 完全不参与冻结判定**——若照简报字面只追加 amendment，unfrozen_only 不会归零、⑱ 仍红（假闭环）。故双登记（endpoints 字符串 + amendments provenance），并直验冻结集命中。
4. **【P0】reshape-b.json endpoints 成为混合类型列表（3 dict + 1 str）**：febe parser 以 `isinstance(e, str)` 容忍混合，当前全仓唯一机器消费者即 febe（26/26 实证），但第三方消费者若假设全 dict 会在该文件上炸——已在 amendment note 注明，重组契约文件时应一并归一。
5. **【P0】冻结解析走 resolve_relative 后缀兜底，后端离线时该条目落 malformed**：`/payment-notifications/channel` 非 /api/ 前缀且不在 KNOWN_ROOT_PATHS（与其姊妹 mock 同型，mock 也走此路径），后端 8000 不可达时 load_contracts(be_routes=None) 会将其计入 malformed（冻结面暂时缩水、⑱ env_blocked WARN 不构成静默漂移）。未扩 KNOWN_ROOT_PATHS 是刻意的：保持该白名单严格 5 条（test_root_path_known_set_exact_match 锁定），不造新豁免宽口径。

## 7. 批判承接核对

| 移交项 | 来源 | 本任务处置 |
|---|---|---|
| febe 桶 R22PAY 登记 tc72 的 tests 侧 overlay → canonical 同步（scripts/eval 属主） | TEST-BASE 65b1b81（commit message "febe桶R22PAY登记tc72…canonical同步列移交清单" + test 文件头 overlay 注释） | **闭环**：canonical `NEXTJS_OPS_ENDPOINTS` 直登 `("POST","/payment-notifications/channel")`（ops 桶语义=支付回调类运维端点前端永不接入，与 mock 同型，非新豁免口径）；tests overlay 判冗余删除；回退保护升级为 `expected_ops` 显式断言（canonical 被回退则套件红） |
| PAY-GATE 062704a 新端点未入冻结契约 → ⑱ 红 | 编排者安静窗终验（⑱ 红，unfrozen_only>0） | **闭环**：契约面冻结（§2）+ hash 重算（§3），⑱ PASS（§5） |

回归保护双保险：`test_nextjs_ops_bucket_includes_known_root_paths`（ops 桶缺 channel 即红）+ `test_nextjs_buckets_cover_full_to_connect_against_real_backend`（expected_tc=72 / uncategorized=0，真实后端实证）。

## 8. 资产消费证据（具名资产 → 实际用法）

| 资产 | 消费方式 |
|---|---|
| `edu-agent/scripts/eval/febe_contract_check.py` | 通读全文：load_contracts 只解析字符串条目（§6 P0-3 依据）、resolve_relative 后缀兜底（§6 P0-5）、NEXTJS_* 四桶语义与 KNOWN_ROOT_PATHS 严格 5 条锁定（禁宽口径依据）；在其 NEXTJS_OPS_ENDPOINTS 做 +1 最小 diff |
| `contracts/reshape-b.json` + 全 contracts/ 目录 | 发现 reshape-b 实为 MCP health-scan 契约、支付组在 reshape-r-health.json（§6 P0-1）；amendments 格式与 hash 字段先例 |
| `edu-agent/tests/test_febe_contract_check.py` | overlay 现状（65b1b81 登记的并集 overlay）→ 判冗余删除 + expected_ops 加固 |
| AGENTS.md | 教训 8（真实契约优先于页面注释：以 openapi/代码实测为准）、教训 2（禁 Playwright，全部 requests/curl/pytest 独立实证） |
| `check-demo.mjs` ⑱ 门 + `febe_health_gate_probe.py` | ⑱ 判据=unfrozen_only==0 解析 [FEBE_HEALTH]/[SUMMARY]，终验复跑 |
| `git show 062704a` | 闸门三关语义逐字核对（commit message + channel_verify.py run_channel_gates）、确认 PAY-GATE 仅新增 1 个端点 |
| `.opencode/plans/critique-backlog-tracker.md:608` | tracker 346 = pay 渠道验签闸门登记缺口，与 amendment source 对齐 |
| WNEXTFECONTRACT-002 报告 + CR-FE-002 handoff | hash 重算算法先例溯源（§3） |

## 9. 测试终态

```
tests/test_febe_contract_check.py   26 passed (6.22s)   ← febe 套件全绿（含 2 个真实后端用例）
tests/test_r22pay_channel_verify.py 34 passed (4.67s)   ← 34 个 pay 相关断言零回退
```

未触碰 tests/test_r22pay_channel_verify.py（PAY-GATE 领地），仅回归复跑证明不回退。
