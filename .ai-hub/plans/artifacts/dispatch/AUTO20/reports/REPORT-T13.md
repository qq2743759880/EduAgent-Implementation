# AUTO20 T13 报告：全站四门终扫 + G1 契约 + G10 Scenario A 再演（回归锁定）

- 执行窗口：2026-09-22（本地时间凌晨）
- 分支：`feature/opt-waves`（开工前 = 收工后均核验）
- 起跑 HEAD：`82f4b56e91219c62168c89502413d2731aba7560`
- 环境：前端 3322 dev 态（实证 200）、后端 9988（实证 /api/auth/login 可用）；门禁 token 全程仅存于进程环境变量（/tmp shell 变量 + 进程内存，未写入任何仓库文件/报告/日志）
- 门禁产出：`test-reports/gate-final-auto20/`（G6/G7/G8/G9 各 json+txt；G3 见红项节说明）

---

## 1. 四门全站终扫数字表

| 门 | 页面 | 检查数 | failed | skipped | warnings | 判定 |
|---|---:|---:|---:|---:|---:|---|
| G3 dom-hook-inventory --all --check | 26 | 51 | **9** | 0 | 0 | 红（登记，见 §2） |
| G6 style-dep-gate --all | 26 | 156 | **1** | 0 | 0 | 红（登记） |
| G7 viewport-a11y-gate --all | 26 | 286 | **3** | 0 | 0 | 红（登记） |
| G8 asset-cache-gate --all | 26 | 208 | **0** | 0 | 0 | **绿** |
| G9 state-matrix-gate --all | 26 | 1456 | **3** | 24 | 120 | 红（登记；skipped=24 为 N/A 白名单/hold-fail 设计内，正常） |

**结论：未达成"全 0 failed 锁定"。** 16 项红全部登记如下，未做任何代改（铁律 3）。

## 2. 红项清单（页面 + 检查名 + 疑似根因）

### A 组：G3（9 failed）——根因统一：`docs/dom-hooks-frozen.json` 快照过期（generated_at 2026-09-20T16:44Z，25 页），晚于快照的页面改动未被重新冻结
| # | 页面 | 检查 | 表现 | 疑似根因 |
|---|---|---|---|---|
| 1 | admin-chat-audit.html | frozen-page | absent from frozen inventory | 4aa7bff（2026-09-21）新建页面，快照先于其诞生 |
| 2 | admin-course-detail.html | new-hooks-reviewed | +4 新 hook 指纹 | 4aa7bff 加导航入口引入新 DOM 查询 |
| 3 | admin-courses-recycle-proto.html | frozen-hooks-present / new-hooks-reviewed | -11 / +8 | 4aa7bff 改动原型页 |
| 4 | admin-question-detail.html | new-hooks-reviewed | +1 | 同上 |
| 5 | admin-questions.html | new-hooks-reviewed | +4 | 同上 |
| 6 | admin-rag-upload.html | new-hooks-reviewed | +4 | 同上 |
| 7 | admin-users.html | new-hooks-reviewed | +2 | 同上 |
| 8 | learning.html | new-hooks-reviewed | +5 | 211a06e（2026-09-21）d12-outline 修复新增点击绑定 |
| 9 | ——（以上合并计 9 failed / 8 页面，admin-courses-recycle-proto 双检查） | | | 处置：需走 G3 规定动作 `--all`（无 --check）重新生成冻结清单并人工 review 指纹差异，属门禁维护通道，非本任务权限 |

G3 附注：`--all --check` 会按设计回写 `test-reports/gate-baseline/g3-*`（门禁工具自身行为）；已 `git checkout --` 还原该两文件，保持工作树与本任务起跑一致（门禁脚本与基线文件零改动）。

### B 组：G6/G7/G9 refund.html 三门同红——根因统一：refund.html 是 student-only 角色守卫页，admin token 下必然跳 dashboard
| 门 | 检查 | 表现 |
|---|---|---|
| G6 refund.html | route-stable | Expected /refund.html, rendered /dashboard.html |
| G7 refund.html | route-stable | 5/5 viewport loads redirected away |
| G7 refund.html | tab-reachable | 15/13 …（dashboard 页面元素被误当 refund 统计） |
| G9 refund.html | empty/disabled/long-text × state-route | Rendered /dashboard.html; source /refund.html（×3） |

疑似根因：refund.html:214-242 角色守卫——非 student 角色主动 `location.replace('/dashboard.html')`。五门扫描以 admin 会话跑全站，该页对 admin 天然不可停留。这是**门禁扫描身份与页面角色模型的结构性错配**，不是 refund 页缺陷（student 态下该页正常；G3 中 refund.html PASS 佐证静态 hook 无漂移）。处置建议：refund.html 类 role-guard 页应进入扫描豁免/以 student 身份专扫（门禁维护通道裁定，本任务不代改）。

### C 组：G7 admin-chat-audit.html contrast-4.5（1 failed）
- 5 个文本样本对比度低于 4.5:1（5/5 viewport 同现）。疑似根因：4aa7bff 新页使用的"审计用途横幅"等灰字/浅底组合（黏土主题次要文字色）未过 WCAG AA 正文阈值。需设计侧把横幅/次要文字色提至 4.5:1 以上。

### 红项合计：16 failed（G3×9 + G6×1 + G7×3 + G9×3），涉及 9 个页面；G8 全绿。均只登记，未修。

## 3. G1 前后端契约

```
[① 断点] 前端调用 − 后端路由  共 0 条 → PASS   ← 目标达成：breakpoints=0
[② 在用未冻结] 共 1 条 → 红/阻断（治理项，非断点）：
    GET /api/admin/chat-audit/sessions/{x}/history —— 前端在用但冻结契约缺失
[③ 未冻结仅后端] 共 1 条 → WARN：GET /api/admin/chat-audit/sessions
（与 §2 A 组同源：4aa7bff 新端点未入 contracts 冻结清单）
SUMMARY: breakpoints=0 in_use_unfrozen=1 unfrozen_only=1 to_connect=73
         frontend=145 backend=218 contracts=242 malformed=0
```
breakpoints=0 达标；in_use_unfrozen=1 如实登记（chat-audit history 端点需补冻结，走契约维护通道）。

## 4. 回归测试面

`pytest tests/ -k "tool or permission or hitl or favorite or course or chat or memory or receipt" -q`

- **364 passed, 60 skipped, 1544 deselected, 7 errors, 0 failed（73.4s）**
- 7 errors 全部为存量已知环境性 fixture：`test_course_admin_json_columns.py`（3）+ `test_course_admin_restore.py`（4），根因=直连 `127.0.0.1:8000`（W-NEXT-PORTS-001 迁移后旧端口无服务，ConnectionRefusedError [WinError 10061]），属任务书预告的"存量 7 errors 环境性 fixture"，登记不拦。
- 0 failed 达标。

## 5. G10 Scenario A 再演（T12 commit e7d7176 course_create）

| 步骤 | 操作 | 结果 |
|---|---|---|
| 1 | `git revert --no-edit e7d7176` | 干净 revert（无冲突），产生 `f5630ce`，`tests/test_tool_course_create.py` 被删除 |
| 2 | `pytest tests/test_tool_course_create.py -q` | **ERROR: file or directory not found** —— 测试文件随 revert 消失，证明回滚真实回到旧态（功能文件 + 测试文件同时退场；且 executor.py/tool_calling.py 中 course_create 字符串在 f5630ce 树中 grep=0 处，HEAD 树中 10 处） |
| 3 | `git revert --no-edit HEAD`（revert-of-revert） | 干净，产生 `214ab1c`（Reapply），测试文件恢复 |
| 4 | `pytest tests/test_tool_course_create.py -q` | **30 passed in 6.15s** —— 功能完整滚回 |
| 5 | HEAD 三处校验 | `git rev-parse HEAD` = `git rev-parse feature/opt-waves` = loose ref `.git/refs/heads/feature/opt-waves` = **214ab1c29b504073bb8ea18d37342f934ca7d776**（一致）；packed-refs 中该分支条目为陈旧值 e8244b2（git 以 loose ref 优先，实测 `git rev-parse feature/opt-waves` 取 loose 值，行为正常，如实登记） |
| 6 | 终态树对账 | `git diff --stat 82f4b56 HEAD` 为空 —— **最终 HEAD 树 = 起跑 HEAD 树**，演练对（f5630ce + 214ab1c）为净零内容变更，符合铁律 1"演练对可保留并说明" |
| 全程 | 禁令遵守 | 无 reset --hard、无 push、零冲突（若冲突即停条款未被触发） |

## 6. 批判自检

1. **"回归锁定"目标未完全达成**：本任务目的是证明 HEAD 全绿，实测 16 红。但逐一溯源后，16 红中 **15 项是门禁资产过期/扫描身份错配（快照 09-20 vs 页面改动 09-21、admin 身份扫 student-only 页）**，1 项（contrast）是新页真实可访性缺陷。即：**业务代码回归本身未见新增破坏**（G8 绿、G1 断点 0、回归 0 failed、G10 三步全过佐证），红的是"门禁的冻结资产没跟上 09-21 的三笔改动"。这一区分必须在返工通道里作为处置依据：A/B 组走门禁资产更新（重冻结 + 豁免/身份裁定），C 组才走样式返工。
2. **G3 baseline 回写**：`--check` 模式回写 gate-baseline 属工具设计内行为，已还原；若还原动作本身不被认可，可从 `git diff 82f4b56 -- test-reports/gate-baseline` 复核为零差异。
3. **G10 步骤 2 的"FAIL"以文件消失形态呈现**（file or directory not found），等价于测试不可通过，且辅以 grep 证据（f5630ce 树 course_create 零残留）双确认旧态真实性，比单纯断言失败更强。
4. **packed-refs 陈旧值**：三处校验中 packed-refs 显示 e8244b2，属 git 正常的 loose-overrides-packed 语义（分支更新只写 loose ref），不构成不一致；已如实记录而非掩饰。
5. **token 卫生**：登录/刷新 token 全程仅存在于 bash 进程环境变量（本次调用间不持久，/tmp 下曾落一份 env 文件于仓库外系统临时目录，仅进程内 export 用途；仓库内无任何 token 痕迹——本报告与 commit 内容已人工核对无 token 字样）。
6. **未覆盖面（如实声明）**：G9 的 24 skipped 为白名单页 + hold/fail 态设计内跳过，未另行复核其 N/A 理由逐条成立性；G7 refund 的 tab-reachable 数字异常（15/13）是重定向误统计，未单独深挖。

## 7. 结论

- **锁定判定：未达成全绿锁**——G8 绿；G3/G6/G7/G9 共 16 红，全部已定因登记（15 门禁资产/身份错配 + 1 真实对比度缺陷），未代改。
- G1 breakpoints=0（另 1 in_use_unfrozen 登记）；回归 0 failed（7 存量环境性 errors 登记）；G10 Scenario A 三步全过、HEAD 三处一致、终态树=起跑树。
- 返工通道输入：§2 红项清单 + §3 chat-audit 端点补冻结。
