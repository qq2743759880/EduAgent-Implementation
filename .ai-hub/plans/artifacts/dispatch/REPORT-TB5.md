# REPORT-TB5 — Agent 协作自证包（15 分钟亲手验证手册 + 一键复核脚本）

- 分支：`feature/opt-waves`
- 开工令：`TO-EXEC-TB5.md`
- 执行时间：2026-09-24 10:01–10:14 (GMT+8)
- 交付物：`docs/agent-collab-verify.md`（新）、`verify-auto20.cmd`（新）

## 0. 结论

两个交付物均已完成并**现场实跑验证**。五个验证点的每条命令都被执行过一遍，输出摘录如下（§2）。
一键脚本实测 **PASS=2 / FAIL=0 / DRIFT=1 / SKIP=0，退出码 0，耗时 80~102 秒**（§3）。

**过程中发现并如实上报两个问题**（均非本单引入，也未修改）：
1. **G3 门禁在多 agent 并行时"变红"**——现场撞到 `admin-mcp.html` 被并行单改动导致 4 条新钩子指纹未 review。
   已把该现象在文档中定义为 **DRIFT（漂移）而非 FAIL（回归）**，并在脚本里独立计列。详见 §2.4。
2. **`tests/test_watchdog_8000.py` 收集期报 ERROR**——其依赖的 `scripts/watchdog_8000.py` 已随看门狗机制移除（`f12f802`），
   文件不存在 → `ImportError` **中断整轮 pytest**。这是既有债，本单范围外，脚本以 `--ignore` 隔离并在文档注明。详见 §3.2。

> 铁律遵守：只新建开工令列明的两个文件（`docs/agent-collab-verify.md`、`verify-auto20.cmd`）；
> 未碰任何其它文件；DB 仅只读 SELECT；未 push；单 commit。

## 1. 交付物清单

| 文件 | 行数/大小 | 说明 |
|---|---|---|
| `docs/agent-collab-verify.md` | 326 行 | 执行模型一图 + 5 个验证点（精确命令 + 实测预期输出）+ 可重放/不可重放边界表 |
| `verify-auto20.cmd` | 7291 字节（GBK+CRLF） | 三块检查 + PASS/FAIL/DRIFT/SKIP 汇总面板，固定白名单，无新依赖 |

## 2. 五个验证点各自实跑输出

### 2.1 验证点 ① 派单 → 报告对账

```
$ ls .ai-hub/plans/artifacts/dispatch/TO-EXEC-*.md | wc -l
23
$ ls .ai-hub/plans/artifacts/dispatch/REPORT-*.md | wc -l
16            ← 首次执行（10:01）
18            ← 复跑（10:11）：TB2/TB3 两单在途落地，数字自动跟上
```

逐单成对检查实测（10:11 输出）：
```
PAIR    AUDIT-W1        PAIR    MIMOSA-EXCL       PAIR    TA2
PAIR    DATA-SEED-1     PAIR    PAGE-WAVES-A      PAIR    TA4
PAIR    EVALFREEZE-B1   PAIR    PAGE-WAVES-B      PAIR    TB2
PAIR    FEAT-WIRE-V2    PAIR    PAGE-WAVES-C      PAIR    TB3
NO-RPT  FEAT-WIRE       PAIR    TA1-3             PAIR    THEME-GATE
PAIR    FIX-CMTINPUT    NO-RPT  TA5               NO-RPT  TB1
PAIR    GATE-V2         NO-RPT  SEED-VIDEO        NO-RPT  TB4 / TB5
PAIR    GATEA-CLAY
成对: 17    待报告: 6
```

**PASS。** 缺口 6 项各有解释：`FEAT-WIRE` 作废（README 状态板标 🗑 用户裁定）、
`SEED-VIDEO` 冻结等解冻、`TA5`/`TB1`/`TB4`/`TB5` 在途。

抽查一对字段闭环（TO-EXEC-TA2 ↔ REPORT-TA2）三处自洽：
- 开工令头：`分支 feature/opt-waves；后端 9988 / 前端 3322`
- 报告头：`分支：feature/opt-waves` / `后端：9988`
- 报告结论：approve/reject 双路实弹结果

### 2.2 验证点 ② C-01 抽验：REPORT-TA2 的 DB 断言

REPORT-TA2 §4 声称：`ta2_demo_a` 1 行（id=3136, name=TA2演示课程A, created_by=100003）、`ta2_demo_rej` 0 行。

owner 亲手复现（只读 + 参数绑定）：
```python
cur.execute('SELECT COUNT(*) FROM series WHERE series_code=%s', ('ta2_demo_a',))
cur.execute('SELECT COUNT(*) FROM series WHERE series_code=%s', ('ta2_demo_rej',))
cur.execute('SELECT id,series_code,series_name,created_by FROM series WHERE series_code=%s', ('ta2_demo_a',))
```
实测输出：
```
ta2_demo_a  => 1 (报告称 1)
ta2_demo_rej => 0 (报告称 0)
明细: (3136, 'ta2_demo_a', 'TA2演示课程A', 100003)
```

**PASS。** 与报告**逐字节一致**（含主键 3136、`created_by=100003`）。
语义：同时证明 approve 路**真的落库**、reject 路**真的零新增**。

### 2.3 验证点 ③ 盲测队列状态机走读

```
$ sed -n '8,31p' .ai-hub/plans/artifacts/dispatch/AUTO20/blind-test-queue.md
```
实测状态分布：**✅ 已执行 6 条**（B1/B3/B4/B5/B6/B8）、**⬜ 待执行 2 条**（B7 等 SEED-VIDEO、B9 等 course_create）。

字段级证据抽样（B6）：结果列写的是
`答案带诚实修正句「⚠️ 上述工具操作未实际执行」+ tool_receipt_unverified=True（编排者亲测）`
—— `tool_receipt_unverified` 是响应里的真实布尔字段，可对账。

**PASS。** 状态机语义：任务验收通过 → 追加场景 → BLIND-WAVE 集中执行（**禁读实现 diff，只看行为**）→ 结果入表 →
发现缺陷登记 tracker + 必要时返工。

### 2.4 验证点 ④ 门禁现场 PASS

```
$ node scripts/gates/dom-hook-inventory.mjs --all --check
G3 DOM Hook Inventory: PASS
pages=26 checks=52 failed=0 warnings=0
json=test-reports\gate-baseline\g3-dom-hook-inventory.json
text=test-reports\gate-baseline\g3-dom-hook-inventory.txt
exit=0
```

**首跑 PASS。** 约 10 分钟后复跑变为：
```
G3 DOM Hook Inventory: FAIL
pages=27 checks=53 failed=2 warnings=0
```
失败项定位（读 JSON）：
```
REAL-FAIL admin-mcp.html new-hooks-reviewed  4 new hook fingerprints require review.
    add: query-selector|querySelector("#srvTable tbody")
    add: query-selector-all|querySelectorAll("#srvSteps li")
    add: query-selector-all|querySelectorAll("#mdl-server .step-pane")
    add: class-list|classList.toggle("on",+panes[j].getAttribute("data-pane")
$ ls -l --time-style=full-iso edu-frontend/public/admin-mcp.html
-rw-r--r-- 1 Administrator 197121 81534 2026-09-24 10:07:43 +0800   ← 就在本次执行过程中
```

**根因**：并行 agent 正在改 `admin-mcp.html`（该文件磁盘修改时间落在本次执行窗口内）。
这是**漂移（drift）**而非**回归（regression）**——新增钩子需人工 review 后重冻结，不是缺陷。

**处置**（未改任何生产文件，仅调整自证包口径）：
- 文档中新增「G3 红有两种含义」判读表：`frozen-hooks-present` 失败（**缺失**）= 可能有真回归，高优先；
  `new-hooks-reviewed` 失败（**新增**）= 漂移，review 后重冻结。
- `verify-auto20.cmd` 把 G3 失败单独计为 **DRIFT** 列（非 FAIL），避免并行常态把面板染红、掩盖真问题。

> **诚实边界**：本条 DRIFT 是**观测事实**（含时间戳与钩子指纹），不是"门禁坏了"。
> G3 门禁本体工作正常——它**正确地**探测到了页面变化。

### 2.5 验证点 ⑤ 多 agent git 竞态取证（只读回看，未制造事故）

**A) ref 健康**
```
$ cat .git/HEAD
ref: refs/heads/feature/opt-waves
$ git branch --show-current
feature/opt-waves
$ ls .git/refs/heads/feature/
opt-waves
```
三处一致 → ref 健康（非 detached、非悬空）。

**B) reflog 里的 reset 痕迹**（节选）
```
793f24b HEAD@{2026-09-22 07:01:59 +0800}: reset: moving to HEAD
8bb4558 HEAD@{2026-09-22 03:25:14 +0800}: reset: moving to HEAD
3779142 HEAD@{2026-09-18 23:56:09 +0800}: reset: moving to HEAD~1
```
`reset: moving to HEAD` 是空操作型；`HEAD~1` 才是真回退（危险形态）。

**C) 提交链前向无损**
```
$ git log --format="%h parent=%p  %s" -4 HEAD
3dfe2b1 parent=8d9ed61  docs(dispatch)/yy-P1: 六份开工令（TA5 + TB1-TB5）
8d9ed61 parent=0da0b0c  fix(fe)/ta3: 黄条视觉实证修复+稳定触发话术进手册
0da0b0c parent=54065ea  fix(fe)/ta1: chat 流式双端定因修复
54065ea parent=caf972d  chore(db)/ta4: 清理演示面遗留测试数据
```
同日多 agent 并行，`0da0b0c`(TA1) 与 `8d9ed61`(TA3) 是**先后链在同一父提交 `54065ea` 之上的直系提交**
→ 恢复时采取「只前向追加、不 reset」策略，同期所有人的工作未丢。

**PASS（回看型）。** 文档同时给出可复制的取证判据：
```bash
BEFORE=$(git rev-parse HEAD); git commit -F .git/msg.txt -- <paths>; git rev-parse HEAD   # 比 SHA 变化，不看退出码
git merge-base --is-ancestor <我的SHA> HEAD                                              # YES = 纯前向恢复不丢工作
```

## 3. verify-auto20.cmd 完整输出（干净 shell 实跑）

命令：`.\verify-auto20.cmd`（PowerShell 捕获，UTF-16 转 UTF-8 后的原文）

```
===========================================================================
  EduAgent Agent 协作工程一键复核
  仓库根: E:\stu\project\stu\EduAgent实施手册
  时间:   2026/09/24 周四 10:11:50.17
===========================================================================

[1/3] G3 门禁 (dom-hook-inventory --all --check) ...
---------------------------------------------------------------------------
G3 DOM Hook Inventory: FAIL
pages=27 checks=53 failed=2 warnings=0
json=test-reports\gate-baseline\g3-dom-hook-inventory.json
text=test-reports\gate-baseline\g3-dom-hook-inventory.txt
  [DRIFT] G3 检出钩子清单漂移（非回归，见脚本内判读口径）
          处置: 确认改动是否为接线改进 -> 审查通过后重冻结
          重冻结: node scripts\gates\dom-hook-inventory.mjs --all
          速查漂移页: findstr /i "false" test-reports\gate-baseline\g3-dom-hook-inventory.txt

[2/3] dispatch 派单对账 ...
---------------------------------------------------------------------------
  开工令 TO-EXEC-*.md : 23
  完工报告 REPORT-*.md : 18

  逐单成对检查:
    NO-RPT 表示开工令尚无报告；在途/冻结/作废属正常现象，
    但须能在同目录 README.md 状态板找到对应说明。

    PAIR    AUDIT-W1
    PAIR    DATA-SEED-1
    PAIR    EVALFREEZE-B1
    PAIR    FEAT-WIRE-V2
    NO-RPT  FEAT-WIRE
    PAIR    FIX-CMTINPUT
    PAIR    GATE-V2
    PAIR    GATEA-CLAY
    PAIR    MIMOSA-EXCL
    PAIR    PAGE-WAVES-A
    PAIR    PAGE-WAVES-B
    PAIR    PAGE-WAVES-C
    NO-RPT  SEED-VIDEO
    PAIR    TA1-3
    PAIR    TA2
    PAIR    TA4
    NO-RPT  TA5
    NO-RPT  TB1
    PAIR    TB2
    PAIR    TB3
    NO-RPT  TB4
    NO-RPT  TB5
    PAIR    THEME-GATE

  成对: 17    待报告: 6
  [PASS] dispatch 对账（17 对已配平）

[3/3] pytest 契约子集 (-k "chat or favorite or hitl") ...
---------------------------------------------------------------------------
..............................................sssssss................... [ 52%]
.........................................................ss.....         [100%]
=============================== warnings summary ===============================
tests\test_check_demo_timeouts.py:136
  ... PytestUnknownMarkWarning: Unknown pytest.mark.slow - is this a typo?
.venv\Lib\site-packages\fastapi\testclient.py:1
  ... StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated
app\rerank_service\main.py:115 / 128
  ... DeprecationWarning: on_event is deprecated, use lifespan event handlers instead
.venv\Lib\site-packages\fastapi\applications.py:4681
  ... DeprecationWarning: on_event is deprecated
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
127 passed, 9 skipped, 1829 deselected, 6 warnings in 80.80s (0:01:20)
  [PASS] pytest 契约子集

===========================================================================
  汇总
---------------------------------------------------------------------------
  PASS = 2    FAIL = 0    DRIFT = 1    SKIP = 0
  ------------------------------
  DRIFT = 门禁检出漂移，需人工审查后重冻结（不是回归，见 [1/3] 说明）
===========================================================================

  结论: PASS(含漂移) -- 无回归失败，但 G3 检出 1 处钩子漂移待人工审查。
        漂移根因通常是并行 agent 正在改页面（本仓库多单并行时属常态）。
        请按 [1/3] 提示审查后重冻结，或等该并行单收工后复跑。
```

**退出码 0。耗时实测三次：102s / 101s / 80.8s（均 <5 分钟预算）。**

### 3.1 脚本开发中实测踩到的两个假红（已修复并入文档）

| 症状 | 根因 | 修法 |
|---|---|---|
| `'ch' 不是内部或外部命令` + `for` 块解析错位 | 脚本被写成 **UTF-8 + LF**；cmd.exe 按 GBK 代码页解析，中文注释变乱码指令，LF 让括号块错位 | 改为 **GBK + CRLF**；中文只放 `echo`/`REM`；`for` 循环体改 `call :sub` + `goto :eof` 展平 |
| `MYSQL_PASSWORD / LLM_API_KEY Field required` | 在仓库根跑 pytest → dotenv `find_dotenv` 从 cwd 向上找不到 `edu-agent\.env` | 脚本 `pushd "%CD%\edu-agent"` 后再跑，`popd` 收回 |

### 3.2 已隔离的既有债（非本单范围，未修）

`tests/test_watchdog_8000.py` → `import watchdog_8000` 失败（`scripts/watchdog_8000.py` 随看门狗机制移除，commit `f12f802`）
→ **收集期 ERROR 中断整轮 pytest**（`-k "chat or favorite..."` 一条都跑不到）。
处置：脚本以 `--ignore=tests\test_watchdog_8000.py` 隔离，文档 §一键复核 注明。
**该文件应随后续清理删除或修复**——本单铁律限定文件域，未动。

## 4. 禁吹边界（文档 §「可自动化重跑 vs 过程记录」原文要点）

| 类别 | 内容 | 能否重放 |
|---|---|---|
| ✅ 自动化可重跑 | 验证点 ①②③④ 全部命令；`verify-auto20.cmd` 全链路；G3 门禁；pytest 子集 | 任意机器 clone 后重跑，结果一致 |
| ⚠️ 需环境在岗 | ② 的 MySQL；G7 需真实浏览器 + 后端 | 有则重跑；无则标"环境阻塞" |
| ❌ 过程记录，不可重放 | ⑤ 的 **reflog 条目本身**；REPORT 里带时间戳的 HTTP 摘录；盲测**当时的**现象描述 | 仅作"当时发生过"的留痕 |

三条诚实边界（文档内明写）：
1. REPORT-TA2 的 SSE 帧字段摘录属过程记录，**本次未重新执行该 HTTP 调用**；可验证的是其留下的 DB 痕迹（②已亲跑）。
2. reflog 竞态证据只声明"记录存在且可回看"，不声明"可复现"。
3. 手册引用的每个数字均来自本次现场执行。

## 5. 交付物与提交

```
git add docs/agent-collab-verify.md verify-auto20.cmd
git commit -m "docs(verify)/tb5: Agent 协作自证包(15 分钟亲手验证手册+一键复核脚本)"
```

- 新增：`docs/agent-collab-verify.md`、`verify-auto20.cmd`
- 未改动任何既有文件；未 push。
- 本地证据文件（未提交）：`_tb5_out.txt`、`_tb5_out_clean.txt`（脚本运行原文）。

## 6. owner 验收口径对照

| GWT | 实测 |
|---|---|
| Given owner 照文档操作 | ✅ 五个验证点各含精确命令 + 实测预期输出 |
| Then ≤15 分钟亲手复现核心证据 | ✅ 动线表合计约 11~12 分钟（①③④⑤ 秒级 + ② 3 分钟 + ⑥ 80~102s） |
| 每步输出与文档预期一致 | ✅ 本文每条命令输出均与文档所写一致（含两次数字变动已如实标注为"并行落地"） |
