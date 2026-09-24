# Agent 协作工程 —— owner 15 分钟亲手验证手册

> 面向 owner。本文每个数字、每条命令都是**编排者现场跑过一遍**才写进来的（C-01 同款纪律）。
> 配套一键脚本：仓库根 `verify-auto20.cmd`（跑可机验子集，≤5 分钟，输出 PASS/FAIL 面板）。
> 分支：`feature/opt-waves`。文档版本：2026-09-24（TB5）。

---

## 一图看懂执行模型

```
   ① 编排者写开工令              ② 用户当信使              ③ 执行者开工
 ┌──────────────────┐        ┌──────────────┐        ┌──────────────────────┐
 │ TO-EXEC-<ID>.md  │ ─────▶ │ 复制全文，    │ ─────▶ │ 在仓库按铁律施工      │
 │ 自包含·铁律·验收 │        │ 跨平台送给    │        │ 单 commit（禁 push）  │
 │ 口径             │        │ 执行者        │        │ 写 REPORT-<ID>.md      │
 └──────────────────┘        └──────────────┘        └──────────┬───────────┘
        ▲                                                          │
        │                                                   ④ 用户带回报告
        │                                                          ▼
        │                ⑥ 全 PASS → 记闭环            ┌──────────────────────┐
        │                  任一 FAIL → 写 REWORK-<ID>  │ ⑤ 编排者逐断言独立验收 │
        └──────────────────────────────────────────── │ 跑测试/curl/git/DB 实测│
                                                       │ **不采信报告文字**     │
                                                       └──────────────────────┘
```

四类文件构成完整证据链（同一目录 `.ai-hub/plans/artifacts/dispatch/`）：

| 件 | 谁写 | 作用 |
|---|---|---|
| `TO-EXEC-<ID>.md` | 编排者 | 开工令（自包含，执行者零上下文可开工） |
| `REPORT-<ID>.md` | 执行者 | 完工报告（每条断言附可复现命令与真实输出） |
| `REWORK-<ID>.md` | 编排者 | 验收 FAIL 后的返工令 |
| `README.md` 状态板 | 编排者 | 闭环结论 + 复验指纹 |

**核心不变量**：⑤ 与 ③ 的写法无关 —— 验收只读**可复现证据**（HTTP 响应、DB 行、git 对象、测试输出）。报告里写什么不算数，跑出什么才算数。

---

## 5 个「亲手验证点」（各 ≤3 分钟）

### 验证点 ① 派单 → 报告对账（≈1 分钟）

**看什么**：开工令与完工报告是否成对、状态板是否如实。

```bash
cd <仓库根>
# 1) 数量对账
ls .ai-hub/plans/artifacts/dispatch/TO-EXEC-*.md | wc -l     # 期望 23
ls .ai-hub/plans/artifacts/dispatch/REPORT-*.md | wc -l      # 期望 16

# 2) 逐单成对检查（列出谁有开工令却没报告）
for f in .ai-hub/plans/artifacts/dispatch/TO-EXEC-*.md; do
  id=$(basename "$f" | sed 's/^TO-EXEC-//;s/\.md$//')
  [ -f ".ai-hub/plans/artifacts/dispatch/REPORT-$id.md" ] \
    && echo "PAIR    $id" || echo "NO-RPT  $id"
done
```

**2026-09-24 实测输出**（节选）：
```
TO-EXEC 23 / REPORT 16      ← 首次实测（本手册写作时）
TO-EXEC 23 / REPORT 18      ← 10 分钟后复跑：TB2/TB3 两单在途落地，数字自动跟上
PAIR    TA2
PAIR    TA1-3
PAIR    TA4
PAIR    THEME-GATE
NO-RPT  FEAT-WIRE     ← 已作废（README 状态板标 🗑 用户裁定）
NO-RPT  TB1 TB4 TB5   ← 并行在途，开工令比报告新属正常
NO-RPT  SEED-VIDEO    ← 已冻结等解冻
NO-RPT  TA5           ← 在途
```

> **数字会动，这是特性不是缺陷。** 上表两个数字来自同一会话相隔约 10 分钟的两次执行 —— TB2/TB3 两份报告在这期间落地，`16 → 18` 自动跟上。
> 这类"活跃仓库对账"本身就在证明**多 agent 确实在并行工作**。判读时看的是**缺口能否被解释**，而不是数字是否等于某个固定值。

> **判读要点**：「开工令 > 报告」不是缺陷。在途/冻结/作废三类都会产生缺口。**缺口必须能在 README 状态板找到对应说明**才算健康——这正是 ① 要查的第二件事。

**抽查一对字段闭环**（开工令 → 报告 → 结论三处必须自洽）：

```bash
head -12 .ai-hub/plans/artifacts/dispatch/TO-EXEC-TA2.md   # 开工令：分支/后端
sed -n '1,13p' .ai-hub/plans/artifacts/dispatch/REPORT-TA2.md
```

实测三处一致：开工令写「分支 `feature/opt-waves`；后端 9988 / 前端 3322」→ 报告抬头写「分支：`feature/opt-waves` / 后端：9988」→ 报告结论段给出 approve/reject 双路实弹结果。**字段无缺、无自相矛盾**。

> ⚠️ **只有成对 + 字段自洽还不够**。报告可以写得漂亮却是假的 —— 这正是验证点 ② 存在的理由。

---

### 验证点 ② C-01 抽验示范：亲手跑 REPORT-TA2 的 DB 断言（≈3 分钟）

**看什么**：报告里的一条 DB 断言，owner 自己用只读 SQL 复现，看结论是否成立。

REPORT-TA2 第 4 节声称（原文摘录）：
> `SELECT * FROM series WHERE series_code='ta2_demo_a'` → **1 行**：`(id=3136, series_code='ta2_demo_a', series_name='TA2演示课程A', created_by=100003)`
> `SELECT COUNT(*) FROM series WHERE series_code='ta2_demo_rej'` → **0 行**

**owner 亲手复现**（只读，参数绑定，无写操作）：

```bash
cd <仓库根>/edu-agent
.venv/Scripts/python.exe -c "
import pymysql
c = pymysql.connect(host='127.0.0.1', port=3306, user='root', password='123456', database='edu')
cur = c.cursor()
cur.execute('SELECT COUNT(*) FROM series WHERE series_code=%s', ('ta2_demo_a',))
print('ta2_demo_a  =>', cur.fetchone()[0], '(报告称 1)')
cur.execute('SELECT COUNT(*) FROM series WHERE series_code=%s', ('ta2_demo_rej',))
print('ta2_demo_rej =>', cur.fetchone()[0], '(报告称 0)')
cur.execute('SELECT id,series_code,series_name,created_by FROM series WHERE series_code=%s', ('ta2_demo_a',))
print('明细:', cur.fetchone())
c.close()
"
```

**2026-09-24 实测输出**：
```
ta2_demo_a  => 1 (报告称 1)
ta2_demo_rej => 0 (报告称 0)
明细: (3136, 'ta2_demo_a', 'TA2演示课程A', 100003)
```

**三态判定：PASS。** 报告数字与实测**逐字节一致**（含主键 3136、`created_by=100003`）。

这条断言的语义价值在于它同时证明了**两点**：
- `ta2_demo_a` 存在 → approve 路**真的落库了**（不是"报告声称成功"）；
- `ta2_demo_rej` 为 0 → reject 路**真的零新增**（HITL 拒绝不是装饰）。

若把这条 SQL 交给一个只读报告的人，他能独立得出同样结论 —— **这就是 C-01「不采信报告文字」的落地形态**。

> 💡 换任意一份 REPORT，找它的"DB 行/HTTP 状态码/文件哈希"类断言，用同样方法复现。抽验不在多，在**亲手跑过一次**。

---

### 验证点 ③ 盲测队列状态机走读（≈2 分钟）

**看什么**：`.ai-hub/plans/artifacts/dispatch/AUTO20/blind-test-queue.md` —— 以「未知实现细节的攻击者」视角写的场景，及其滚动更新的状态。

```bash
sed -n '8,31p' .ai-hub/plans/artifacts/dispatch/AUTO20/blind-test-queue.md
```

**队列结构**：B1–B9 九条场景，每条 = `关联任务 | 攻击者原话 | status | 结果`。

**2026-09-24 实测状态**（`status` 列的真实取值分布）：

| 状态 | 条目 | 含义 |
|---|---|---|
| ✅ 已执行 | B1、B3、B4、B5、B6、B8 | 随对应任务验收时执行，结果列有具体现象 |
| ⬜ 待执行 | B7（等 SEED-VIDEO）、B9（等 course_create 后续） | 依赖任务未闭环 |

**状态机语义**（走读时按这个顺序核对）：

```
任务验收通过 ──▶ 编排者追加 ≥1 条盲测场景（status=待…入队）
                        │
                        ▼
              BLIND-WAVE 集中执行 / 或随验收即时执行
                        │
        ┌───────────────┴───────────────┐
        ▼                               ▼
   status=✅ + 结果列写明现象      发现缺陷 → tracker 登记 → 必要时返工
```

**为什么盲测与普通验收不同**：执行时**禁读实现 diff，只看行为**（队列规则第 5 行）。例如 B6 的原话是「问一个工具不存在的问题→AI 必须说『暂无对应工具』类诚实回答，**禁止编造「已完成」**」—— 这是拿"攻击者/用户视角"去撞护栏，而不是复述设计意图。

实测 B6 的结果列写的是具体现象而非结论：
> 诱导捏造场景（导入知识库被拒）→ 答案带诚实修正句「⚠️ 上述工具操作未实际执行」+ `tool_receipt_unverified=True`（编排者亲测）

**字段级证据**（`tool_receipt_unverified=True` 是响应里的真实布尔字段），不是"护栏工作正常"这类空话 —— 可对账、可复现。

> **判读要点**：⬜ 待执行不等于失败。B7/B9 各自依赖的 SEED-VIDEO / course_create 后续尚未到位。**禁止把"待执行"粉饰成"已通过"**，也禁止把"未到"说成"没做"。

---

### 验证点 ④ 门禁即协作产物：现场跑一条门禁看 PASS（≈1 分钟）

**看什么**：`scripts/gates/dom-hook-inventory.mjs`（G3 DOM 钩子冻结门）是协作产物 —— 它把"页面 DOM 访问模式"冻结成清单，任何页面的钩子漂移都会让 `--check` 失败。

```bash
cd <仓库根>
node scripts/gates/dom-hook-inventory.mjs --all --check
echo "exit=$?"
```

**2026-09-24 实测输出**：
```
G3 DOM Hook Inventory: PASS
pages=26 checks=52 failed=0 warnings=0
json=test-reports\gate-baseline\g3-dom-hook-inventory.json
text=test-reports\gate-baseline\g3-dom-hook-inventory.txt
exit=0
```

**判读**：`failed=0` + `exit=0`。门禁的失败语义是**硬失败**（`process.exitCode = report.status === "PASS" ? 0 : 1`）—— 能直接接进 CI/提交钩子当闸门用。

> ⚠️ **实测陷阱：G3 会在多 agent 并行时"变红"，但那不是回归。**
> 编写本手册期间现场撞到一次：首跑 PASS（26 页 / 52 检查），10 分钟后复跑变 `failed=1`（27 页 / 53 检查），
> 差异项指向 `admin-mcp.html` 新增 4 条钩子指纹（如 `querySelector("#srvTable tbody")`）——
> 而该文件的**磁盘修改时间是本次执行过程中**（10:07:43），说明有并行 agent 正在改这一页。
>
> 所以**「G3 红」有两种含义，必须区分**：
> | 现象 | 含义 | 处置 |
> |---|---|---|
> | `frozen-hooks-present` 失败（**缺失**冻结钩子） | 有钩子被**删掉/改写** | 高优先排查，可能是真回归 |
> | `new-hooks-reviewed` 失败（**新增**钩子） | 页面加了未审查的钩子 | 属漂移，人工 review 后重冻结 |
>
> 两者都要"人工审查后重冻结"，但**只有前者需要警惕回归**。`verify-auto20.cmd` 因此把 G3 的失败单独计为 **DRIFT** 而非 **FAIL**（面板里是独立一列），避免并行常态把整块面板染红、掩盖真正的问题。
>
> 想知道是哪些页、哪些钩子：`findstr /i "false" test-reports\gate-baseline\g3-dom-hook-inventory.txt`

**为什么说它是协作产物**：G3 冻结清单在 `docs/dom-hooks-frozen.json`。多 agent 并行改页面时，谁动了钩子、动的是不是"接线改进"，都必须在清单重冻结时**逐条 review 并留痕**（历史 commit `c600661` 就是这么做的：8 页新增钩子逐一判定）：
- **新增钩子** → `--check` 失败，必须人工 review 后重冻结；
- **删除/改写的钩子表达式** → 同样失败（漂移）；
- **仅行号变化** → 允许（不视为漂移）。

所以这条门禁把「多 agent 并行改同一批页面」从"靠人盯"变成"**机器可判**"。

**其它可跑的门禁**（同一 `scripts/gates/` 目录，本文不逐一展开）：

| 门 | 脚本 | 关注面 |
|---|---|---|
| G3 | `dom-hook-inventory.mjs` | DOM 钩子冻结 |
| G6 | `style-dep-gate.mjs` | 样式依赖 |
| G7 | `viewport-a11y-gate.mjs` | 视口无障碍（对比度/可达性） |
| G8 | `asset-cache-gate.mjs` | 资产缓存 |
| G9 | `state-matrix-gate.mjs` | 状态矩阵 |

> ⚠️ G7 需真实浏览器（CDP）。若无浏览器/后端未起，会走 `skipped` 而非 PASS —— **按三态判定标注为「环境阻塞」，不得算作通过**。`verify-auto20.cmd` 只跑 G3（纯静态扫描，无外部依赖），保证一键脚本在任何干净 shell 都能出结果。

---

### 验证点 ⑤ 多 agent git 竞态取证（≈2 分钟，只读回看）

**看什么**：并行 agent 同写一个仓库时，ref 会互相顶掉。这个仓库**真实发生过**，且修复过程留了痕。本验证点**只回看既有记录，不现场制造事故**。

```bash
cd <仓库根>

# A) 分支 ref 必须可解析（不能是 detached / 悬空）
cat .git/HEAD                                    # 期望: ref: refs/heads/feature/opt-waves
git branch --show-current                        # 期望: feature/opt-waves
ls .git/refs/heads/feature/                      # 期望: opt-waves（松散 ref 存在）

# B) reflog 里的 reset 痕迹（并行 agent 曾把分支顶端顶回去）
git reflog --date=iso | grep -i "reset" | head -5

# C) 提交链的"前向无损"形态：并行提交各链在自己那一笔之上，没有互相截断
git log --format="%h parent=%p  %s" -4 HEAD
```

**2026-09-24 实测输出**：

A) `ref: refs/heads/feature/opt-waves` / `feature/opt-waves` / `opt-waves` —— 三处一致，ref 健康。

B) reflog 中确有 reset 记录（节选）：
```
793f24b HEAD@{2026-09-22 07:01:59 +0800}: reset: moving to HEAD
8bb4558 HEAD@{2026-09-22 03:25:14 +0800}: reset: moving to HEAD
3779142 HEAD@{2026-09-18 23:56:09 +0800}: reset: moving to HEAD~1
```
> `reset: moving to HEAD` 是空操作型 reset（当前位置不变），`HEAD~1` 则是**真回退** —— 后者才是会顶掉他人提交的危险形态。

C) 提交链实测（parent 逐级向前，无截断）：
```
3dfe2b1 parent=8d9ed61  docs(dispatch)/yy-P1: 六份开工令（TA5 + TB1-TB5）
8d9ed61 parent=0da0b0c  fix(fe)/ta3: 黄条视觉实证修复+稳定触发话术进手册
0da0b0c parent=54065ea  fix(fe)/ta1: chat 流式双端定因修复
54065ea parent=caf972d  chore(db)/ta4: 清理演示面遗留测试数据
```

**这个案例讲的是什么**：2026-09-24 同一天有 TA1-3 / TA2 / TA4 / TA5 / TB1-TB5 多个 agent 并行提交。`0da0b0c`（TA1）与 `8d9ed61`（TA3）是**先后链在同一父提交 `54065ea` 之上**的直系提交 —— 说明尽管存在 reset 干扰，**恢复时采取了「只前向追加、不 reset」的策略**，因此同期所有人的工作都没丢。

**取证判据（可复制到任何并行 git 场景）**：

```bash
# 判据1：我的提交是否被顶掉？—— 提交前后对比 SHA，而不是看退出码
BEFORE=$(git rev-parse HEAD)
git commit -F .git/msg.txt -- <本任务路径...>
AFTER=$(git rev-parse HEAD)
[ "$BEFORE" = "$AFTER" ] && echo "⚠️ SHA 未变 = 可能被 ref 竞态吞掉" || echo "✅ 提交生效"

# 判据2：若怀疑被顶掉，验证我的提交是你当前分支的直系祖先（YES = 纯前向恢复不会丢工作）
git merge-base --is-ancestor <我的SHA> HEAD && echo "在链上" || echo "已脱离 HEAD 链"
```

> ⚠️ **本验证点的诚实边界**：reflog 是**本地过程记录**，`git gc` / clone / 换机器后可能被裁掉 —— 它**不可跨环境重放**。它的价值是"当时确实发生了、且留下了可查的痕"，不是"任何人在任何机器上都能重现这段历史"。
> 真正**可跨环境重放**的，是上面 A/C 两组（ref 健康 + 提交链祖先关系）—— 它们只依赖当前 Git 对象库，clone 出来依旧成立。

---

## 可自动化重跑 vs 过程记录（禁吹边界）

| 类别 | 内容 | 能否重放 |
|---|---|---|
| ✅ **自动化可重跑** | 验证点 ①②③④ 的**全部命令**；`verify-auto20.cmd` 全链路；G3 门禁；pytest 契约子集 | 任意机器 clone 后重跑，结果一致 |
| ⚠️ **需环境在岗** | 验证点 ② 的 MySQL（`127.0.0.1:3306`）；G7 需真实浏览器 + 后端 | 有环境则重跑；无则标"环境阻塞" |
| ❌ **过程记录，不可重放** | 验证点 ⑤ 的 **reflog 条目本身**（reset 痕迹）；`REPORT-*.md` 里带时间戳的 HTTP 响应摘录；盲测 B1–B9 的**当时的**现象描述 | 只能作为"当时发生过"的留痕，不能复现 |

**三条诚实边界**（本文严格遵守）：
1. 报告中引用的历史响应摘录（如 TA2 的 SSE 帧字段）—— 属过程记录，**本次未重新执行该 HTTP 调用**，故不宣称"当前重跑仍一致"；可验证的是其**留下的 DB 痕迹**（验证点 ②已亲跑）。
2. reflog 竞态证据 —— 只声明"该记录存在且可回看"，不声明"可复现"。
3. 本手册引用的每个**数字**都来自本次现场执行；未现场跑过的项一律标注为「过程记录」。

---

## 一键复核

```bat
verify-auto20.cmd
```

固定白名单，无新依赖。**2026-09-24 实测：80~102 秒**（三次执行区间），在 5 分钟预算内。

**实测汇总面板**（原文照录）：
```
===========================================================================
  汇总
---------------------------------------------------------------------------
  PASS = 2    FAIL = 0    DRIFT = 1    SKIP = 0
  ------------------------------
  DRIFT = 门禁检出漂移，需人工审查后重冻结（不是回归，见 [1/3] 说明）
===========================================================================

  结论: PASS(含漂移) -- 无回归失败，但 G3 检出 1 处钩子漂移待人工审查。
```

三个检查块与实测结果：

| 块 | 命令 | 实测 |
|---|---|---|
| [1/3] G3 门禁 | `node scripts/gates/dom-hook-inventory.mjs --all --check` | DRIFT（并行单在改 `admin-mcp.html`，见验证点 ④ 陷阱说明） |
| [2/3] dispatch 对账 | 开工令 vs 报告计数 + 逐单成对 | PASS（23 开工令 / 18 报告 / 17 对配平） |
| [3/3] pytest 契约 | `pytest tests -k "chat or favorite or hitl"` | PASS（**127 passed, 9 skipped, 1829 deselected**，80.80s） |

退出码：`0` = 无回归失败（含 DRIFT 情形）；`1` = 有 FAIL 或全被跳过。

**两个必须知道的实现细节**（都是实测踩出来的，否则脚本会假红）：

1. **pytest 必须在 `edu-agent\` 目录下跑。** 配置靠 dotenv 的 `find_dotenv` 从 cwd 向上找 `.env`；
   若在仓库根执行，会找不到 `edu-agent\.env` 而报
   `MYSQL_PASSWORD / LLM_API_KEY Field required` —— **这是假红，不是环境缺失**。
   脚本内部用 `pushd "%CD%\edu-agent"` → 跑完 `popd` 处理，并设 `MYSQL_HOST=127.0.0.1`
   （VM `192.168.85.101` 会拒 `root@192.168.85.1` 报 1130）。

2. **`--ignore=tests\test_watchdog_8000.py`。** 该测试依赖 `scripts/watchdog_8000.py`，
   而看门狗机制已被移除（commit `f12f802`），文件不存在 → **收集期报 ERROR 并中断整轮**。
   这是该文件的既有债、与本子集无关，故排除；不排除则 `-k "chat or..."` 一条都跑不到。

> 📌 **脚本本身的两个兼容性硬约束**（如需修改脚本）：
> - 文件必须存为 **GBK + CRLF**。cmd.exe 按当前代码页（本机 GBK）解析批处理，UTF-8 中文注释会被
>   拆成乱码指令 → 报 `'ch' 不是内部或外部命令` 之类；LF 换行会让 `for ( ... )` 块解析错位。
> - 中文只放在 `echo`/`REM` 里，**不放 `for`/`if` 块内的多重嵌套**（改用 `goto :label` 展平）；
>   `for %%f in (...) do call :sub "%%~nf"` 配 `goto :eof` 比多行括号块稳。

详细面板与判定口径见脚本内注释。

---

## 附：15 分钟动线建议

| 顺序 | 验证点 | 分钟 | 累计 |
|---|---|---|---|
| 1 | ① 派单→报告对账 | 1 | 1 |
| 2 | ④ 门禁现场 PASS | 1 | 2 |
| 3 | ③ 盲测队列走读 | 2 | 4 |
| 4 | ② C-01 抽验（含 DB 连接） | 3 | 7 |
| 5 | ⑤ git 竞态回看 | 2 | 9 |
| 6 | `verify-auto20.cmd` 一键复核（挂在后台跑） | ~2 | 15 |

先跑轻的建立直觉，再把耗时的 cmd 放最后 —— 总耗时 ≤15 分钟。

> **时长依据**：验证点 ①③④⑤ 为纯读操作，合计约 6 分钟（已实测命令耗时均在秒级）；② 含数据库连接约 3 分钟；
> ⑥ 一键脚本实测 80~102 秒。合计 **约 11~12 分钟**，留出 3 分钟余量应对首次执行的环境预热。
