# W4 回归门禁完工报告（防复生）

- 任务：EduAgent 优化期遗留项 2 —— W4 回归门禁（C2 page\_meta 双轨 / C4 respbar 演示残留）

- 执行 agent：TRAE 子 agent（遗留项 2 承接者）

- workflow：TT 编排者侧义务「W4 回归门禁」阶段

- 日期：2026-09-04

- 状态：**已实现 + 已实测通过（GATE\_RESULT=OK）→ 等验收，未 commit**

***

## 1. 资产消费证据段

| 资产                  | 路径                                                                 | 消费方式                   | 方法论落点                                               | <br />                    | <br />                                                                                                                                                                       |
| ------------------- | ------------------------------------------------------------------ | ---------------------- | --------------------------------------------------- | :------------------------ | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| <br />              | <br />                                                             | **tt skill §5.2/§5.4** | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` | Read                      | §5.2「验收必须独立实证，不采信报告……grep 审计」→ 门禁必须给「可机验客观边界」；§5.4「可验证边界：所有判定给可机验客观边界，禁止仅凭主观」→ 门禁以「主动命中=0」为 PASS 判据，并输出逐行命中列表可复现；一键回归纪律（`regression-all`）→ 把本门禁接入既有 `run_regression.ps1` 入口。 |
| **tt 现有 gate 风格参考** | `C:\Users\Administrator\.agents\skills\tt\scripts\review-gate.mjs` | Read（未改动）              | 复用其风格约定：顶层 \`GATE\_RESULT=OK                        | VIOLATION ` 式机器可读尾部、`PASS | FAIL + 命中行列表`、`process.exitCode = ok?0:1\`、纯 node 无第三方依赖、顶部注释声明用途/判据/用法。                                                                                                     |

自检发现并修复：`<!-- -->` 块注释解析曾因「2 字符切片与 4 字符串比较」漏判导致 HTML 注释 `<!-- respbar…-->` 被误判为主动命中（假 FAIL）；已改为按 4 字符切片识别 `<!--`、3 字符识别 `-->` 后复测转 PASS。该问题说明「先真实数据自检，不依赖直觉」。

***

## 2. agent×skill×workflow 矩阵

| 维度       | 取值                                              |
| -------- | ----------------------------------------------- |
| agent    | TRAE 子 agent（遗留项 2 执行者）                         |
| skill    | `tt`（consumed 其 §5.2/§5.4 + review-gate.mjs 风格） |
| workflow | W4 回归门禁（C2 + C4 防复生，接入 `run_regression.ps1`）    |

***

## 3. 脚本关键逻辑 + 实测输出

### 3.1 产物

- 脚本：`scripts/gate-w4-critique.mjs`（纯 node，无第三方依赖）

- 接入：`run_regression.ps1` 末尾新增「W4 门禁」段（`=== W4_GATE ===`）。先 `Get-Command node` 探测，缺 node 输出 `W4_GATE_SKIPPED` 不中断回归；有 node 则 `& node <脚本> | Select-Object -Last 40`，并打印 `W4_GATE_EXIT`，后接 `=== ALL_DONE_W4 ===`。

### 3.2 关键逻辑

1. **CLI**：`node scripts/gate-w4-critique.mjs [--root <仓库根>] [--with-src] [--debug]`。默认 `--root` = 脚本上级（仓库根）。`--with-src` 为**可选**增强：把 `edu-frontend/src` 纳入 page\_meta 扫描、src 递归纳入 respbar 扫描。
2. **扫描边界**：

   - \[C2] `page_meta`：默认 `edu-agent/app` + `edu-frontend/public`；`--with-src` 加 `edu-frontend/src`。

   - \[C4] `respbar`：默认 `edu-frontend/public/*.html`；`--with-src` 加 src 递归。
3. **「主动 vs 注释」区分**：状态机逐行去注释/去字符串，保留等长空格维持行列定位——

   - py：`#` 行注释、`"""`/`'''` 文档串（跨行状态）、单/双引号字符串。

   - html/js/ts/css：`<!-- -->`、`/* */`（跨行状态）、`//` 行注释、单/双引号/模板字符串；并保护 `http://` 型 `://` 中的 `//` 不被误判为注释。

   - 去注释后的「代码清洗串」若仍含关键词 → 主动命中（ACTIVE）；否则仅注释命中（comment）。
4. **判定**：`主动命中=0` → `[PASS]`（且列出全部注释命中行便于审计）；否则 `[FAIL] ACTIVE` 列出行。尾部 `GATE_RESULT=OK|VIOLATION`，退出码 `0|1`。

### 3.3 实测输出（本机 node v24.18.0，默认参数）

```
[PASS] [C2] page_meta 双轨清零
  主动命中(非注释/文档字符串)=0  ✓ 判定：主动命中=0
    (comment) edu-agent\app\domains\course\router.py:70  # （外层 {total,page,page_size,items}，C2 删 page_meta）...
    (comment) edu-agent\app\domains\course\schemas.py:6    ...（C-B 全站权威，无 page_meta 双轨，C2 已删）
    (comment) edu-agent\app\domains\course\schemas.py:42   """系列列表分页 DTO（... C2 已删 page_meta 双轨）。"""
    (comment) edu-agent\app\domains\course\schemas.py:101  """班次列表分页 DTO（... C2 已删 page_meta 双轨）。"""
    (comment) edu-agent\app\domains\course\service.py:78   ...（C2：外层 triple 唯一，无 page_meta）
    (comment) edu-agent\app\domains\course\service.py:109  # C2: task115 C-B 权威外层 ...（page_meta 双轨已删）
    (comment) edu-agent\app\domains\course\service.py:149  ...（C2：外层 {...}，无 page_meta）。
    (comment) edu-agent\app\domains\market\schemas.py:5   - CouponPage 分页壳 {...}（page_meta 不在本域使用）
    (comment) edu-agent\app\domains\market\schemas.py:57  """我的券分页（... 非 page_meta）。"""

[PASS] [C4] respbar 演示残留清零
  主动命中(非注释/文档字符串)=0  ✓ 判定：主动命中=0
    (comment) edu-frontend\public\achievements.html:45 / :275 / :680
    (comment) edu-frontend\public\admin-dashboard.html:55 / :257 / :439
    (comment) edu-frontend\public\chat.html:47 / :423 / :594
    (comment) edu-frontend\public\community-post.html:47 / :251 / :354 / :503
    (comment) edu-frontend\public\community.html:59 / :275 / :363
    (comment) edu-frontend\public\courses.html:215 / :720
    (comment) edu-frontend\public\dashboard.html:302 / :505
    (comment) edu-frontend\public\me.html:50 / :4156 / :4256
    (comment) edu-frontend\public\practice.html:385
    （全部为 /* */、<!-- -->、// 注释，含 `已移除(critique C4)` 说明）

GATE_RESULT=OK
```

- 退出码验证：`node scripts/gate-w4-critique.mjs` → `$LASTEXITCODE=0`（PASS）。

- `run_regression.ps1` W4 段独立模拟：`GATE_RESULT=OK` / `W4_GATE_EXIT=0` / 缺 node 时 `W4_GATE_SKIPPED` 且不中断（测试通过）。

- 负向验证（`--with-src`）：能正确把 `edu-frontend/src` 里**主动过渡兼容类型字段** `page_meta?: {...}`（curriculum.ts:102/217、admin/courses.ts:315）判为 `ACTIVE` → `[FAIL][C2]`、`GATE_RESULT=VIOLATION`/exit 1。证明门禁既能放行注释、也能抓住主动引用，判定可被打破（非恒 PASS）。

### 3.4 说明（判据解释）

默认扫描集（`edu-agent/app` + `edu-frontend/public`）即 W2 修复落点，现全为注释命中 → PASS。`edu-frontend/src` 内 `page_meta?:` 是**有意保留的过渡期兼容类型字段**（页面不再消费，标注 `不再消费 page_meta 兼容字段`），因任务明确 `--with-src` 为可选，故默认不纳入；需验证 src 时用 `--with-src` 会如实暴露（VIOLATION），符合「不伪造 PASS」。

***

## 4. 验收要点（供测试 agent 独立复现）

1. `node scripts/gate-w4-critique.mjs` → `GATE_RESULT=OK`、exit 0。
2. `node scripts/gate-w4-critique.mjs --with-src` → `GATE_RESULT=VIOLATION`、exit 1（证明主动命中判定有效）。
3. `run_regression.ps1` 末尾含 `=== W4_GATE ===` 段，缺 node 走 `W4_GATE_SKIPPED` 不中断。
4. 自检先修 `<!-- -->` 切片 bug，复测已转 PASS。

