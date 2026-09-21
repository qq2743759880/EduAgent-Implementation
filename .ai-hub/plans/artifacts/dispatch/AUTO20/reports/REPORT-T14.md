# REPORT-T14 — Mimosa 全量审计重跑（fail-open 窗口核验 + 排除门全链路验证）

- 派单：AUTO20 T14；执行日期 2026-09-22；执行者=执行子 agent（审计域独占，零业务代码改动）
- 分支核对：开工 `git branch --show-current` = `feature/opt-waves`（HEAD 78f4a63）✅
- 既有披露基线：REPORT-MIMOSA-EXCL.md §3-④（scanner_enobufs fail-open 窗口 + 排除门仅合成自测）；critique-backlog-tracker L679（MIMOSA-EXCL PASS + "全量审计重跑已排程"）

## 1. 扫描结果总览

| 项 | 值 |
|---|---|
| scanId | `scan-2026-09-21T22-09-22.974Z-d91c9227831d` |
| depth | deep（MCP security_scan 同步调用一次成功，未走 start/status 后台通道，未需 enobufs 降级重试） |
| 封印（seal.json digest） | `sha256:6af009bb3e23e152b581e7a1f8e9dd7fc50a7c7e24cb058c72674cdb3d02031b` |
| 产物封印 | findings.json=`sha256:d4a9a58f…4c90`，coverage.json=`sha256:520e1333…72dd`，manifest=`sha256:36f55253…46af` |
| scanDir | `C:\Users\Administrator\.mimosa\security-scans\project-8f039b600b7f291c18a33910\scan-2026-09-21T22-09-22.974Z-d91c9227831d` |
| runStatus | **inconclusive（部分覆盖）** —— 不是 enobufs，是 coverage 缺口：threatModel=partial（entryPoints/principals/authz surfaces=0），findingDiscovery=partial，validation/pathAnalysis/reporting=completed；gaps=["部分分析阶段未能完整覆盖"] |
| 扫描面 | source.selectedFiles=**1219 / parsed=1219 / truncated=false / readFailures=0 / parseFailures=0**（0913 基线 982 → 0921 1219，文件面增长正常） |
| findings | **410**（high 370 / medium 2 / low 38 / info 0 / businessLogic 0）；verdictEffect=none |
| 依赖风险 | 0 受影响包（completion=completed） |

**扫描成功落地，enobufs 未复现**：本次 MCP 通道深扫拿到完整 findings 产物 + seal，无 `scanner_enobufs`、无 bash-discovery/baseline 错误。故派单工序第 2 步的"focusFiles 聚焦 app/** 二次尝试"不触发（该降级仅为 enobufs 预案）。

## 2. 结论一：enobufs fail-open 窗口——MCP 深扫通道已消除；commit-gate 通道待持续观察

分通道说明（fail-open 披露限定在 **commit-gate（git-gate hook）通道**）：

1. **MCP security_scan 深扫通道**（本单主目标）：成功。0913 首次全量审计（scan-…40dcf662e620，262 findings）之后，中间长窗期的 hook 侧 enobufs/inconclusive 未再阻断本次全量重跑。REPORT-MIMOSA-EXCL §3-④"建议尽快重跑完整审计"已执行完毕。
2. **commit-gate 通道**（`.mimosa/history` 的 task-review run）：本单开工前最新记录仍为 `2026-09-21T22:07 inconclusive/partial`（errors=bash-discovery/baseline_missing，非 enobufs；近 40 条 history 中 38 条 inconclusive、仅 0913/0919 两条 completed）。本报告入库 commit 的 gate 实况见 §5 现场记录。**如实登记：commit-gate 的"inconclusive→兼容放行"行为模式仍在，fail-open 窗口不能宣称消除，只能说深扫背书已补齐。**
3. 定性：hook 通道 inconclusive 主因=任务基线（task baseline）不可得（`bash_discovery_incomplete`/`baseline_missing`），与 MCP 独立进程扫描的资源约束不同源；两通道结论不可互替，深扫是更强的独立背书。

## 3. 结论二：排除门全链路核验——真实扫描下未被穿透（P0 排除），但"deny→降级 allow"路径仍未获真实事件背书

### 3.1 被排除文件在真实全量扫描产物中的实证

- `findings.json`（封印版）**全文不含** `auth-client.test` / `login-redirect.test` / `blind-tests` 任一字符串（原始文本级 grep 实证，非仅路径字段过滤）。
- 三文件在工作区真实存在（auth-client.test.ts 4118B、login-redirect.test.tsx 3148B，均含 `user000001`/`Test@123456` 凭据字面量——0921 排除授权针对的事实仍在）。
- 对照组：`edu-agent/scripts/eval/**`（同在 DEFAULT_EXCLUDE_GLOBS，0918 首批授权）在 findings 中**仍有 76 条**。两条排除批次的差异说明：MCP 深扫引擎本身不读排除门配置（payload/dist 内无任何排除 glob 痕迹，grep 实证 0 命中）；**两测试文件不出现=文件面（source.selectedFiles）层已被上游过滤**，而非引擎命中后有人抹除。注意：这与排除门包装器（hooks 通道 PreToolUse/PostToolUse）的机制不同——MCP 深扫的文件集过滤来自扫描器自身（如 vitest 测试文件/前端源的内建范围策略或 git 文件集策略），**排除门包装器对 MCP 深扫通道本就不适用**，两者不能互相证明。
- 对照组反证 `blind-tests/20260920/_internal/**`：同样 0 出现。

### 3.2 ledger/hook 记录侧

- `.mimosa/finding-ledger/v1/**`（events 52 + checkpoints）：0 个文件提及两测试文件——**真实 hook 扫描事件从未为它们生成 finding 记录**，即"未出现被拦记录"。
- `.mimosa/hook-state/`：3 个会话状态文件提到 `auth-client.test.ts`，但仅在 **baseline 文件快照清单**（existed:true + snapshot hash）中，非 finding/拦截记录——即门禁"见过"该文件（作为任务基线的一部分），从未对它产出 deny。
- `hook-status/*.json`（12 条）：9 clear/complete + 3 inconclusive/partial，**0 条与两测试文件相关、0 deny 记录**。

### 3.3 判定

- **P0 预案未触发**：派单预警"若两文件仍出现在 findings=排除门在真实扫描下失效"。实测 0 出现，排除面在真实全量扫描下未被穿透，无需上报失效。
- **诚实边界**：本次全量扫描走 MCP 通道、产出为"0 条与排除文件相关 finding"，没有产生"vendor 先 deny、排除门再降级 allow"的真实事件——REPORT-MIMOSA-EXCL §3-④ 的"真实 deny 场景下走通降级路径"**仍未获实证**（该路径自测 3/3 PASS 的确定性证明不变）。降级路径的真实触发，只能在"某次真实 commit 恰好含排除范围外拦截级 finding"时才可观察，属持续性门禁行为，非本单可人工构造（构造它需要故意提交恶意代码，违反审计纪律）。

## 4. findings 摘要 + 已知项覆盖核对 + 新发现甄别

### 4.1 总体构成（410 条）

绝大多数在一次性验证/文档脚本：`edu-agent/scripts` 145、`test-docs` 57、`项目文档` 30+、`_s2gap_verify*` 11、`test-reports` 12+ 等。类别分布：ssrf 163、path-traversal 100、hardcoded-credential 50（全是 `user000001/Test@123456` 类演示账号与命中脚本）、insecure-randomness 37、other-security 30、command-injection 10、sql-injection 10、code-injection 6、insecure-deserialization 4。`edu-frontend` 0 条。

### 4.2 生产代码（edu-agent/app）15 条逐条核对（与 0913 基线 diff + 源码只读复核）

| # | 位置 | 严重度 | 与既有登记关系 | 判定 |
|---|---|---|---|---|
| 1 | coding/service.py:140 exec | HIGH | = tracker「硬ening ①」**已修**（b661ea2 子进程隔离），140 行是隔离子进程 `_RUNNER_SRC` 内的 exec（`python -I` 隔离+timeout 硬杀），行号随修复后代码漂移 | 已登记已修，非新发现 |
| 2 | coding/service.py:235 exec | HIGH | 同上源的同位变体：回滚开关 `CODING_EXEC_SUBPROCESS=False` 显式保留的旧进程内路径，行内有 `# noqa: S102 -- 回滚开关显式保留的旧路径` 注记 | 已登记（设计保留的回滚面），非新发现 |
| 3 | checkpoint_redis.py:243 pickle.loads | HIGH | = 硬ening ②**已修**（a54fcdf HMAC 签名信封），243 行是**签名校验通过后**的解包分支；行 13 的 LOW 属 docstring 提及 | 已登记已修，非新发现 |
| 4 | artifact_store.py:209/227/365 路径穿越 ×3 | HIGH | **新增**（文件 2026-09-18 2e216e8 引入，晚于 0913 扫描）：209=降级写 `os.path.join(local_dir, flat)`、227=索引记录、365=CLI get 输出路径 | **甄别后降级（见 4.3）** |
| 5 | course_admin/service.py:628 路径穿越 | HIGH | 行 628=`open(final_path)`，final_path 由服务端生成的 `VID-{date}-{uuid}` + 白名单后缀拼出，**非用户可控**；上游 upload_id 已有 `_safe_upload_id` 白名单（f7da572，= 0913 的 543 项修复，行号漂移） | 静态误报（已修项行号漂移+服务端常量拼接），非新发现 |
| 6 | coding/service.py:190 路径穿越 | HIGH | 190 行=临时文件写 `os.path.join(tmpdir, f"u{os.urandom(8).hex()}.py")`，tmpdir/tempfile 随机、文件名服务端随机 | 静态误报，非新发现 |
| 7 | knowledge/routers/upload.py:151 路径穿越 | HIGH | 151 行=`open(dest)`，dest=`_make_upload_basename(uid, _sanitize_filename(...))`（去 `\/:*?"<>|`+Path().name），= 0913 的 107 项已修项行号漂移 | 已登记已修，非新发现 |
| 8 | otel/exporter.py:187 SSRF | HIGH | = 0913 基线同项同行号；endpoint 来自配置（OTLP 导出端点），tracker O1-② 已实证闭环（含不可达降级） | 已登记（配置面端点，非请求参数面），非新发现 |
| 9-15 | insecure-randomness LOW ×5（cache/retry/quiz/loader/checkpoint docstring）+ checkpoint_redis:13 LOW | LOW | = 0913 已登记"random 用于抖动/非密钥，登记不修"（行号漂移 166→185、510→854） | 已登记不修，非新发现 |

### 4.3 唯一增量：artifact_store.py 3×HIGH 路径穿越——登记不修（修复另立项）

- 事实：`save_artifact(name,…)` 入口有 `_sanitize_name`（白名单 `[^A-Za-z0-9._/\-]`→`_` + 剔 `..` 段）+ `_local_flat_name`（`/`→`__` 拉平），本地降级写路径实际受 _sanitize_name+flat 双重约束；**但** `_write_local_copy(local_copy,…)`（365 行 CLI `get` 的输出路径）与 `_index_append` 的 `path` 字段无对应校验，且 `load_artifact` 侧无路径约束——静态结论有真实成分。
- 缓解事实：**生产代码 0 个调用方**（grep 全 app 无 `save_artifact`/artifact_store 引用），当前仅 CLI（运维/实证入口，`_cli` argv）可达；scan-0913 时该文件尚不存在（2e216e8=2026-09-18 "前任 agent 半成品"），属于"已完成 H1d 修复之后新入库"的窗口产物。
- 处置（按铁律 5：只登记不改码）：**登记为待办（P2，建议与 R-M2 artifact store 收口批同做：`_write_local`/`_write_local_copy`/`load_artifact` 统一走 `_sanitize_name`+根目录 realpath 夹逼 + 回归用例）**。此为本次重跑相对 0913 基线的唯一生产代码净新增。

### 4.4 逐项覆盖结论

0913 全量审计的 10 条生产代码发现，在 0921 重跑中：9 条以同性质 finding 复现（行号漂移）或维持登记语义，1 条（course_admin 543）修复后行号漂移为 628 且静态误报成分（见 4.2-⑤）。**无 0913 已修项回归为"未修"状态**；净新增仅 4.3 一处。

## 5. 本报告入库 commit 的门禁现场记录（如实）

- 本 commit 只含本报告文件，git-gate 预扫描结论=**见提交现场 hook 输出**（如再现 inconclusive/兼容放行，即为 §2-2 所述 commit-gate 通道行为模式的又一实例，与本报告披露一致，不构成对报告内容的反证；报告的安全结论以 §1 MCP 深扫封印产物为准）。

## 6. 遗留建议

1. **commit-gate 通道 inconclusive 根因治理**（task baseline 不可得）单独立项：baseline_missing/bash_discovery_incomplete 是 hook 通道 38/40 次 inconclusive 的主因，与 enobufs 同样导致"提交未经完整扫描背书"，值得作为独立工单（非本单范围）。
2. artifact_store 路径约束收口（4.3，P2 登记项）。
3. 排除门"真实 deny→降级 allow"链路：维持合成自测结论 + 日常真实 commit 持续观察；插件 cache 版本更换后需重做排除门（既有约束，重申）。
4. 一次性脚本海面（scripts/test-docs/项目文档 的 ~380 条 exec/eval/ssrf/凭据类）维持"登记不修"既有裁定；若将来打包部署，需先做文件面裁剪。

## 7. 批判自检

- **可能的自我否定①**："排除门全链路核验通过"的口径——严格说本单核验的是"排除文件不出现在扫描产物 + 无拦截记录"，**不是** deny→allow 降级路径本身。已在 §3.3 显式声明该边界，不宣称全链路 100% 实证。
- **可能的自我否定②**：`edu-agent/scripts/eval/**` 在 findings 中仍有 76 条——若排除门对 MCP 通道生效，这 76 条是否矛盾？不矛盾（§3.1 已析）：MCP 深扫不经过 hooks 包装器，其文件集过滤与排除门无关；但这提示**"排除授权"的效力范围=hooks 通道（编辑/提交门），不等于全量审计报告也排除**。本报告如实呈现 76 条，未因授权而隐去，审计口径不受排除授权污染。
- **自我否定③**：4.2 误报甄别（course_admin:628/coding:190）基于只读源码复核，非动态验证；判定"非用户可控/服务端随机"若在调用链上游另有污点源则不成立。已按"静态误报（低置信）"口径登记，未销账——如需销账应走修复批带回归用例证明。
- **流程自查**：零业务代码改动（仅新增本报告文件）；单 commit；未 push；扫描产物在仓库外（.mimosa 用户目录），未污染工作区；findings 中未发现需要 P0 上报的项目（排除门未被穿透）。

—— T14 执行者 2026-09-22
