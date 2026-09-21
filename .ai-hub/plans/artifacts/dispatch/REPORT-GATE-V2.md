# REPORT-GATE-V2 — 门禁工具第二批增强 + 基线刷新 + 前提修正（交回报告）

> 执行分支：`feature/opt-waves`（开工前 `git branch --show-current` 核对一致）。
> 执行窗口：2026-09-21。3322 已切 **dev 态**（Next 16.3.0 Turbopack，`next dev -p 3322`）；后端 9988 在岗。
> 本单含并行提交说明：工作项 4/5 的代码实现由并行执行者以 `cc9030a` 提交（与本单工作项 1/2/3 的三个 commit 无文件交集、零冲突）；本单对其实现完成了**逐断言独立验收**（见 §4/§5），并补齐文档与证据。

## 0. 提交清单

| commit | 内容 |
| --- | --- |
| `2c63a14` | W1：G7 tab-reachable 同名 radio 组聚合 + roving tabindex 容器识别 |
| `1e49cf7` | W2：G7 aria-label/title 采集与复验统一 settle + 失配重试 |
| `ea9a97c` | W3：`--update-baseline` 增量合并修复 + achievements 冻结快照刷新 |
| `ba2a3c2` | W6：console 诊断三分类规则 + 豁免清单文档 + verify_pages_cdp 证据 |
| `1fe9623`（并行） | W6 根因修复：G8 诊断根因 = **自身 `Fetch.enable` 插桩伪影**（页内 fetch 整批失败→`[EAPI]`×106/18 页，me=14 精确复现），字体拦截改 `Network.setBlockedURLs`；修复后 G8 --all 0 诊断 |
| `988eb08`（并行） | W6 补强：`assertFreshGateToken` JWT exp 预检（--all 长跑中途 token 过期→守卫页降级假红，coupons 14/68 假红实证）；文档归因更正 |
| `cc9030a`（并行） | W4：G9 N/A 白名单（`--na` + `na-pages.json` + SKIP 语义）；W5：`assertDevBase` fail-fast + `verify_pages_cdp.mjs` 端口环境变量化 |
| `becc2bc` | W3 同型：G6 `--update-baseline` 增量合并修复 + learning 快照刷新 |
| `6a98dfd` | 终验留档 + 本报告 |

铁律遵守：生产页面 `public/*.html` 与 `theme.css` **零触碰**（本单全部改动在 `scripts/gates/**`、`docs/`、`test-reports/` 证据、`edu-agent/scripts/verify_pages_cdp.mjs`（工作项 5 点名授权）；未发现页面真 bug，无停手事项；未 push。

## 1. 工作项 1：G7 tab-reachable 聚合判定 ✅

**修复前（复现，dev 态实测）**
- `admin-question-detail.html?id=1`：`tab-reachable: 31/34`，3 个 unreachable 全部为同名 radio 组成员（`input.radio` ×3，HTML 标准整组一个 Tab 停靠）。
- `learning.html`：`tab-reachable: 26/28`，2 个 unreachable 为 `#tab-hw`/`#tab-exam`（`role=tablist` 容器内 `tabindex=-1`，WAI-ARIA roving tabindex，方向键可达）。

**修法**：A11Y/ACTIVE 两个 CDP 表达式为焦点元素输出 `groupKey`：
- `radio:<name>` —— 同名 radio 组；
- `roving:<role>@<container>` —— 带**显式 tabindex** 且存在 `tablist|listbox|menu|tree|grid|radiogroup` 角色祖先容器的元素。

判定改为：组内任一成员被 Tab 触达 → 整组计达；组内**零成员可达**仍记 unreachable（不弱化）。

**修复后**：admin-question-detail `31/34 (+3 aggregated)` PASS；learning `26/28 (+2 aggregated)` PASS。

**负控（防弱化）**：构造整组无 Tab 入口页（全成员 `tabindex=-1` 的 tablist + radio 组，临时目录 serving，不触碰 public/）：`1/5 … 4 unreachable` FAIL ✅。反向用例（组内 1 成员可达）：`3/5 (+2 aggregated)`，符合 roving 标准语义 ✅。

## 2. 工作项 2：G7 aria-title-frozen settle ✅

- 新增独立 `ATTRS_EXPRESSION` + `settledAttrs()`：快照采集与复验统一在 `EDU_GATE_SETTLE_MS` 之外追加 **`EDU_GATE_ATTRS_SETTLE_MS`（默认 200ms）** 的二次稳定读取；复验失配时再以 3× settle 加长**重试一次**，防慢查询窗口误判。
- **机械验证**（600ms 翻转 demo 页，临时目录）：
  1. 冻结（ATTRS_SETTLE=1000）→ 基线捕获**翻转后**值 ✅
  2. 复验 ATTRS_SETTLE=0（模拟旧单次读法踩慢加载）→ **FAIL** ✅
  3. 复验 ATTRS_SETTLE=200（重试越翻转点）→ **PASS** ✅
- **dashboard 验收**：`dashboard.html` 11/11 全 PASS，`aria-title-frozen: 0 missing`（与冻结基线比对通过）。补记：当前已提交的 dashboard 冻结快照（4 条静态标签）本身干净、无「加载中」残留；本项价值在于把 settle 机制化，消除对运行窗口时序的依赖。

## 3. 工作项 3：achievements 基线刷新（含增量合并修复）✅

- **修复**：`--update-baseline` 原为整文件覆盖（`--page` 单页刷新会抹掉其余 24 页冻结快照、静默弱化全站 aria 冻结），改为**按页合并**。
- **刷新**：`node scripts/gates/viewport-a11y-gate.mjs --page http://127.0.0.1:3322/achievements.html --update-baseline`（带 token）：achievements attrs 23 → **7**（DB 数据清理漂移，非回归）；基线页数刷新前后均 **25**（合并语义生效）。
- **复验**：achievements `aria-title-frozen: 0 missing`，页 PASS ✅。

## 4. 工作项 4：G9 N/A 白名单机制 ✅（实现 `cc9030a`，本单独立验收）

| 断言 | 结果 |
| --- | --- |
| `scripts/gates/na-pages.json` 白名单（3 页各带 reason）+ `--na <page>` 运行时扩展 | ✅ |
| N/A 页 `state-intercepted` 记 **SKIP**（severity=skip，不计 FAIL），`finalizeReport` 增 `skipped` 计数 | ✅ 每页 skipped=8 |
| login-register / admin-users-refine-proto / admin-courses-recycle-proto 三页 G9 | ✅ 均 `PASS, failed=0`（56 检查/页） |
| **负控**：非白名单页 courses.html 的 state-intercepted 仍真实拦截 | ✅ 8 态全 pass 且 intercepted>0，白名单未弱化门禁 |

## 5. 工作项 5：route-stable dev 前提钉死 + 端口修正 ✅（实现 `cc9030a`，本单独立验收）

- **探针选型实证一致**：Next 16 Turbopack 下 `/_next/webpack-hmr` dev 态也 404（本单实测，与该提交注释一致）；采用 `/_next/static/development/_devMiddlewareManifest.json`（dev 200 / prod 404）。
- **fail-fast 实测**：3323 起 prod 态（`NEXT_PROD_DIST_DIR=.next-prod next start`，页面 200 可用）→ G9 运行即抛 `GATE-BASE-MODE: not a Next dev server …`，**Chrome 未启动**，退出码 1 ✅。已接线 G6/G7/G8/G9 四个浏览器门；G3 为纯静态文件分析（不启动浏览器），无需接线。
- **verify_pages_cdp.mjs**：`VERIFY_FE_BASE`/`VERIFY_API_BASE` 环境变量（默认 3322/9988），全文件无 3000/8000 残留 ✅；实跑 12 页全渲染（h1 齐、0 console 问题），截图与 results.json 见 `test-reports/verify-pages-cdp-v2/` ✅。

## 6. 工作项 6：console 诊断逐条分类 ✅（归因经并行工作两轮更正，最终口径如下）

- **根因（最终，`1fe9623` 实证）**：验收窗口的 18 条非阻断诊断**不是环境瞬态、也不是页面缺陷**，而是 G8 门禁自身插桩伪影——`Fetch.enable`（即使 pattern 不匹配）令页内所有 fetch 整批失败，每失败一条产生 `LOG: Failed to load resource` + `CONSOLE: [EAPI] Failed to fetch`（`edu-api.js:116` 统一记录，by design），106 条/18 页可复现，me=14 精确复现。修复：字体拦截改用 `Network.setBlockedURLs`；修复后 G8 --all 0 诊断。
- **本单初判的更正记录**：本单初判「健康窗口 0 诊断 → 环境瞬态」（ba2a3c2），并行执行者以更强复现证据推翻并已更正 `docs/gate-console-diagnostics.md`（988eb08）；C-1 `[EAPI]` 豁免降级为**条件性安全网**（仅当未来出现真实后端故障窗口时适用）。本单采信该更正。
- **分类规则与豁免清单**：`docs/gate-console-diagnostics.md` —— A 静态 404 / B JS 异常 = 修（页面真 bug 停手上报）；C `[EAPI]` API 噪声 = 条件性豁免（仅真实后端故障窗口）。
- **token 前提（`988eb08`）**：`assertFreshGateToken` 本地 JWT exp 预检，token 过期直接拒绝启动，杜绝 --all 长跑中途降级假红。

## 7. 全站终验（修复后，dev 态健康窗口）

| 门 | 结果 |
| --- | --- |
| G6 style-dep --all | **PASS**：25 页 150 检查，failed=0（learning 基线刷新 + dashboard 骨架屏时序实证后终验全绿） |
| G7 viewport-a11y --all | 25 页中 **24 页 PASS**；唯一红 = community-post contrast（页面缺口，停手上报，见 7.2）；courses/my-cohorts 出现过一次瞬态红，单页复跑即绿（见 7.4） |
| G8 asset-cache --all | **PASS**：25 页 200 检查，failed=0，warnings=0，console 诊断=0 |
| G9 state-matrix --all | **PASS**：25 页 1400 检查，failed=0，warnings=110（网络噪声态预期），skipped=24（3 页 N/A × 8 态） |

### 7.1 G6 两红的定性处置

- **learning `layout-blacklist`（1 missing）**：冻结的 z 层 `#transcodeBox`（转码提示框，默认 `hidden`、仅视频转码中渲染）现不存在——数据漂移非回归（与 achievements 同类）。处置：G6 `--update-baseline` 定点刷新 learning 快照。发现 G6 存在与 W3 **同型**的整文件覆盖缺陷，同型修复（commit `becc2bc`：按页合并）；刷新后复验 `0 missing/0 changed` PASS，基线 25 页完整。
- **dashboard `third-party-background`（5/5 透明）**：5 个透明容器全为 `.sk-card > .sk-chart` **骨架屏**——G6 在指标慢查询未返回时采样。实证：`EDU_GATE_SETTLE_MS=3000` 复跑即 `0/0 PASS`。**同族发现移交**：G6 采样与 W2 同受慢查询时序影响，建议后续给 G6 加同款 settle/重试（本单不扩 scope，未代改）。

### 7.2 G7 两红的定性处置

- **admin-dashboard `aria-title-frozen`（2 missing）**：冻结快照里存的正是「近 7 天注册趋势**加载中**」「角色分布**加载中**」——W2 场景的历史坏快照。处置：用新 settle 机制 `--update-baseline` 刷新，现冻结为真实标签（含真实注册/角色数据）；复验 PASS，基线 25 页完整。
- **community-post `contrast-4.5`（5 样本，360~1920 全 viewport）**：`#cmtInput::placeholder`（"写下你的看法…"）4.37:1，UA 默认灰 `rgb(117,117,117)`。页面取证：`community-post.html:349` 的 textarea **未挂 `clay-input` class**（`theme.css:283` 有 `.clay-input::placeholder` 令牌色规则但不命中）。对照 HEAD~5（2026-09-20 提交版）：当时 community-post/admin-dashboard 共 55 条 contrast 红，现仅剩此 1 处——**页面真缺口，按铁律停手上报，不代改**，请编排者裁定（预计一 class 之修）。

### 7.3 瞬态红记录（复跑即绿）

- **courses `reduced-motion`（running animations=25）**与 **my-cohorts `tab-reachable`（14/31, 17 unreachable）**：在 02:15 的 G7 --all 留档跑中出现，单页复跑均 **PASS**。归因讨论：本单初判为页面数据未就绪的时序竞态（骨架屏/卡片未渲染参与判定）；并行工作 `988eb08` 另证一条同症状机制——**token 过期**导致守卫页降级假红（coupons 14/68 实证），并已加 `assertFreshGateToken` 预检封堵。本单 02:15 跑 token 为新签（未过期），故该两例更支持数据就绪竞态；两机制均已记录，后续 --all 假红按「先查 token 预检、再查数据就绪」顺序排查。

### 7.4 终验留档输出

`test-reports/gate-baseline/g6-style-dep-gate.txt`、`g7-viewport-a11y-gate.txt`、`g8-asset-cache-gate.txt`、`g9-state-matrix-gate.txt`（及同名 .json）为最终留档；G9 留档含 3 页 N/A 的 SKIP 语义实证。

## 8. 批判承接

1. **「聚合判定会弱化门禁吗」**：以负控页双向实证——组内零入口仍 FAIL；组内任一成员可达才聚合，且聚合范围仅限同名 radio 与 WAI-ARIA roving 角色容器，普通按钮不受影响。
2. **「settle 200ms 够吗」**：200ms 是统一基线，可经 `EDU_GATE_ATTRS_SETTLE_MS` 调大；复验另有 3× settle 重试兜底；冻结侧演示页证明可用大 settle 冻结到翻转后的真实值。
3. **「基线合并会不会让旧脏快照永生」**：合并只覆盖本次运行到的页；脏页（如曾经的加载中态快照）随该页下次 `--update-baseline` 定点刷新，其余页不受牵连。
4. **「并行提交的信任」**：未盲信——对 cc9030a 逐断言复跑（三页 PASS/skipped=8/courses 负控/prod fail-fast/verify_pages_cdp 实跑）；对 1fe9623 的根因更正，采信其更强复现证据（106 条/me=14 精确复现）而非本单的 0 诊断非复现观察——**「我复现不出」不构成对他人根因结论的反证**，本单初判「环境瞬态」被更正即为元教训。
5. **遗留移交**：① community-post `#cmtInput` 缺 `clay-input`（placeholder 4.37:1）——页面缺口停手上报待裁定；② G6/G7 采样对数据就绪竞态无稳定态探测（连续一致再采），建议后续统一增强；③ Mimosa scanner_enobufs（commit hook 提示）非本单范围，如实披露未宣称扫描结论。
