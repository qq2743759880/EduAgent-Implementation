# REPORT-FIX-CMTINPUT — community-post `#cmtInput` 补挂 `clay-input`（交回报告）

> 执行分支：`feature/opt-waves`（开工 `cat .git/HEAD` = `ref: refs/heads/feature/opt-waves`，`git branch --show-current` 一致）。
> 执行窗口：2026-09-21。3322 = Next dev 态（探针 `/_next/static/development/_devMiddlewareManifest.json` → **200**）；后端 9988 在岗。
> 本单为 GATE-V2 全站终验唯一余红的定点微修；**未 push**。

## 0. 提交清单

| commit | 内容 |
| --- | --- |
| `fix(fe)/community-post: #cmtInput 补挂 clay-input(G7 contrast 唯一余红清零)` | 生产页 1 文件 1 处 1 个 class + 本报告 + 证据目录 |

**改动面（严格受铁律约束）**：生产代码只改 `edu-frontend/public/community-post.html` 的**一行一处**；`theme.css` 零触碰；未另造样式；未新增页面私有修正层（不需要，见 §2 级联分析）。

```diff
@@ -346,7 +346,7 @@ (community-post.html:349)
     <!-- 评论输入（CommentComposer） -->
     <div class="composer" id="composer">
-      <textarea id="cmtInput" placeholder="写下你的看法…（Markdown 支持）" aria-label="评论内容"></textarea>
+      <textarea id="cmtInput" class="clay-input" placeholder="写下你的看法…（Markdown 支持）" aria-label="评论内容"></textarea>
```

`git diff --stat`：`1 file changed, 1 insertion(+), 1 deletion(-)`。元素原本无 `class` 属性，属**纯追加**，未替换任何既有功能类（`dom-hooks-frozen.md` 该页节 109 条钩子中，`#cmtInput` 只有 `getElementById('cmtInput')` 一种取用方式，无 class 选择器依赖 → 挂 class 不可能破坏 JS）。

## 1. 工作项 1：实读元素与 class 用法

- 元素现状（修复前 `community-post.html:349`）：`<textarea id="cmtInput" placeholder=… aria-label="评论内容">`，位于 `<div class="composer" id="composer">` 内，**无 class**。
- 页内同类输入框：本页只有这一个输入控件；全站 `edu-frontend/public/*.html` 中 `clay-input` **此前零页面使用**（`theme.css:271/283/288` 有定义但无命中）。管理端各页走的是各自的 `.admin-html-page input::placeholder{color:var(--text-muted)}` 私有规则，故此前只有 community-post 这一处漏网。
- 依赖核对（`docs/dom-hooks-frozen.md` → `## community-post.html`，Total hooks 109）：`#cmtInput` 相关钩子全部为 `getElementById('cmtInput')`（行 380/459/…）；无 `querySelector('.clay-*')`、无 `closest`、无 `classList` 作用于该元素。→ 追加 class **无选择器副作用**。

## 2. 级联分析（为什么"挂 class"不会改布局）

`theme.css` 的 `.clay-input` 与页面既有 `.composer textarea`（`community-post.html:110`）几乎逐条等价。特异性上 `.composer textarea` = (0,1,1) **高于** `.clay-input` = (0,1,0)，且页面 `<style>` 在 theme.css 之后：

| 属性 | `.clay-input`（theme） | `.composer textarea`（页，胜出） | 结果 |
| --- | --- | --- | --- |
| border / padding / min-height / border-radius | `0` / `12px 16px` / `54px` / `16px` | `2px solid transparent` / `10px 12px` / `64px` / `16px` | 页规则胜出，**不变** |
| font-size / line-height | `inherit` / `inherit` | `14px` / `1.5` | 页规则胜出，**不变** |
| background / color / box-shadow | `--bg-input` / `--text-strong` / `--clay-shadow-input` | 同值 | 同值，**不变** |
| `width:100%` | 有 | 无 | 新增，但 `.composer` 为 `display:flex;flex-direction:column` 已拉伸，且全局 `*{box-sizing:border-box}` → 无害 |
| **`::placeholder`** | `color:var(--text-muted);opacity:1` | **无规则**（缺口本体） | **本单唯一语义变化：令牌色生效** |
| `:focus-visible` | `outline:2px` + `--clay-shadow-input-focus` | 页面 `*:focus-visible` 为 `outline:3px` | 见 §6 诚实披露（微差，非几何） |

## 3. 工作项 2：修复前后 G7 对比（同一 URL / 同一 token / 同一窗口）

**前提纠正（重要）**：派单原文给的命令 `--page http://127.0.0.1:3322/community-post.html` **不带查询串**，会得到**假绿**——该页 `EAPI.pageId("post_id")` 取不到 `post_id` 时 `return`，真实数据链路不启动，`#comments` 保持内联 `visibility:hidden`，`#cmtInput` 根本不参与 G7 采样（实测 `contrastChecked` 仅 25–26，composer `visible:false`）。门禁自身 `--all` 走 `routeForPage()` 是带 `?post_id=96` 的（`_shared.mjs:17`）。本单全程使用 **`?post_id=96`**，与 GATE-V2 留档同一形态。

### 3.1 修复前（`g7-before`）→ FAIL

```
[G7] community-post.html: FAIL
G7 Viewport and Accessibility Gate: FAIL   pages=1 checks=11 failed=1 warnings=0   (exit 1)

  OK  five-viewports / route-stable / no-horizontal-overflow / tab-reachable(17/17)
  OK  focus-visible / focus-not-obscured / icon-control-name / aria-title-frozen
  OK  reduced-motion / console-errors
  FAIL contrast-4.5 : 5 text samples are below 4.5:1.
```

| viewport | selector | ratio | 前景色 | 背景 |
| --- | --- | --- | --- | --- |
| 360 / 768 / 1280 / 1440 / 1920 | `#cmtInput::placeholder` | **4.37** | `rgb(117,117,117)`（UA 默认灰） | `[247,250,244,1]` = `--bg-input` |

`contrastChecked` = 42 / 41 / 41 / 41 / 41 —— 与 GATE-V2 §7.2 的 5 样本 4.37:1 完全一致（复现成功）。

### 3.2 修复后（`g7-after`）→ PASS

```
[G7] community-post.html: PASS
G7 Viewport and Accessibility Gate: PASS   pages=1 checks=11 failed=0 warnings=0   (exit 0)

  OK  contrast-4.5 : 0 text samples are below 4.5:1.
  OK  其余 10 项全 PASS，aria-title-frozen 0 missing（仍与冻结基线比对）
```

**关键反证**：`contrastChecked` = **42 / 41 / 41 / 41 / 41（与修复前逐 viewport 完全一致）**，`tab-reachable` 仍 17/17。→ 采样覆盖度未变、元素未被隐藏或漏采，绿色来自**令牌色真实生效**，不是"少采了一个样本"。

### 3.3 独立 A/B 探针（同一次页面加载内挂/摘 class）

`test-reports/fix-cmtinput/probe-cmtinput-placeholder.mjs`（复用门禁同一套 Chrome 驱动 + 同一套 WCAG 算法，输出 `probe-cmtinput-placeholder.out.txt`）：

| | 挂 `clay-input` | 摘掉 `clay-input` |
| --- | --- | --- |
| `::placeholder` 计算色 | `rgb(107, 101, 128)` = `--text-muted` `#6B6580` | `rgb(117, 117, 117)` UA 默认 |
| 对比度 | **5.25** ✅ | **4.37** ❌ |
| `#comments` | visible | visible |
| `visible` / `disabled` | true / false | true / false |
| 几何 | 1120×66, padding `10px 12px`, border `2px solid transparent`, radius `16px`, min-height `64px`, font-size `14px`, line-height `21px` | **逐项完全相同** |

→ 同一窗口、同一元素、同一数值算法下双向差 0.88，且**几何零变化**；绿/红只由 class 决定。

## 4. 工作项 2 连带：G6 / G9 单页零回归 + G3 全站钩子零漂移

| 门 | 修复前 | 修复后 | 结论 |
| --- | --- | --- | --- |
| **G6** style-dep 单页 | PASS · 6 checks · 0 failed | PASS · 6 checks · 0 failed | 零回归 |
| **G9** state-matrix 单页 | PASS · 56 checks · 0 failed · 5 warnings | PASS · 56 checks · 0 failed · 5 warnings | 零回归（warnings 数完全一致） |
| **G3** dom-hook `--all --check` | — | **PASS · 25 页 50 checks · 0 failed** | 钩子零漂移 |

**G6 逐元素几何比对（机验，非目测）**：`interactive` 列表 before/after 皆 17 项，**selector 集合完全相同、changed entries = 0**；`#cmtInput` = `{width:1120, height:66, disabled:false}` **两次一致**；`zLayers` / `geometry` / `thirdParty` / `drift` / `tooSmall` 全部与修复前逐字节同构。→ "clay-input 挂上后布局异常触发 G6 红"这一铁律预设的停手条件**未出现**。

**G3 该页细项**：`community-post.html` total hooks **109**（与冻结文档 109 一致），`drift = {missing: [], added: []}`。→ 一处 class 追加未新增/移除任何被冻结的钩子指纹。

## 5. 全站终验（G7 `--all`）+ 一次采样瞬态

| 跑次 | 结果 | community-post 采样 |
| --- | --- | --- |
| **run 2（终验）** | **PASS · 25 页 275 checks · failed=0 warnings=0**；25/25 页 `aria-title-frozen` 与冻结基线比对 0 missing；**全站 contrastFailures = 0** | 5/5 viewport 均采到 `#cmtInput`（`contrastChecked` = 42/41/41/41/41，与修复前一致），failures 0 |
| run 1 | PASS · 25 页 275 checks · failed=0 warnings=0 | 仅 360px 采到 composer（42）；768–1920 为 21 且 `#cmtInput` 不在 focusable |

**run 1 的 768–1920 是什么**：该窗口 community-post 未完成真实数据揭示，停在"初始绘制态"——截图（`screenshots-community-post/all-run1-1280-notrendered.jpg`）显示内容区**整片空白**，`#comments` 仍 `visibility:hidden`，而 `#pager` 因内联 `style="visibility:visible"` 反向覆盖而在 `visibility` 继承下仍可见（故 3 个 pager 按钮进了 focusable）；同窗口 `#adminEntry`（依赖 `/api/users/me`）、`#likeBtn`/`#favBtn`（`.actions` 未揭示）一并缺席。即**页面 JS 数据链未就绪**，不是页面缺陷、更不是本单引入（一个 class 属性不可能阻止 JS 执行）；run 2 同参数复跑即 5/5 viewport 正常参与采样。**定性：瞬态数据就绪竞态，与 GATE-V2 §7.3（courses/my-cohorts 复跑即绿）同族**，如实留档不掩盖。

## 6. 诚实披露（本单遗留 / 微差）

1. **`:focus-visible` 微差（已确认，未修）**：挂上 class 后 `.clay-input:focus-visible` (0,2,0) 胜出页面 `*:focus-visible` (0,1,0)，该控件键盘聚焦环由 `3px` 变 `2px` 并加 `--clay-shadow-input-focus`。**非几何变化**（outline 不参与布局），G7 `focus-visible` 检查（要求环可见）仍 PASS；铁律禁止改 `theme.css`，也禁止另造样式，故按派单口径保留并登记。若编排者要消除此微差，最小替代方案是**不加 class、只在本页 `.page-` 私有层补一条 `#cmtInput::placeholder{color:var(--text-muted);opacity:1}`**——但那会让"令牌色唯源"从 theme.css 逸出到页面层，与 CLAY 令牌纪律相悖，本单未擅自替换。
2. **派单命令的假绿陷阱（已实测，见 §3 前提纠正）**：`--page` 命令必须带 `?post_id=96`，否则得假绿。留档证据：`g7-before-settle5k/`（不带查询串 → PASS，`contrastChecked` 25-26）+ `probe-cmtinput-placeholder.noquery.out.txt`（`visible:false`）。**建议**：后续派单/复核凡涉及带 `ROUTE_QUERY` 的页面，一律以 `--all` 或带查询串的单页命令为准。
3. **G6/G7 采样对"数据就绪"仍无稳定态探测**（连续一致再采）——本单 run 1 即为新证据，属 GATE-V2 §8.5② 的同一遗留，未扩 scope。
4. **G3 留档复位说明**：执行期一次"修复前 G3 --all --check"误用了默认 `--out`（`test-reports/gate-baseline/`），覆盖了该处已提交的单页留档；已 `git checkout --` 原样复位、未进本 commit；本单 G3 证据统一落在隔离目录 `test-reports/fix-cmtinput/g3-after/`。**未触碰其它任何留档**（G7/G6/G9 全部使用隔离 `--out`）。
5. **并行提交**：本单工作期间工作树存在他人 `??`/`M` 文件（`.ai-hub/**`、`edu-agent/scripts/eval/**` 等），**一律未 unstage、未 reset**，提交采用路径限定方式。
6. **未做**：未 push；未改 `theme.css`；未改 `scripts/gates/**`；未跑 G8（派单未要求）。

## 7. 复现命令

```bash
# 0) token（仅运行时环境变量，禁落盘）
export EDU_GATE_TOKEN=$(curl -s --noproxy '*' -X POST http://127.0.0.1:9988/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"account":"adm02test","password":"Test@123456"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")

# 1) G7 单页（必须带 ?post_id=96；隔离 out + 拷冻结基线以保留 aria-freeze 比对）
mkdir -p /tmp/g7 && cp test-reports/gate-baseline/viewport-a11y-snapshot.json /tmp/g7/
node scripts/gates/viewport-a11y-gate.mjs --page "http://127.0.0.1:3322/community-post.html?post_id=96" --out /tmp/g7

# 2) G6 / G9 单页；G3 全站
node scripts/gates/style-dep-gate.mjs    --page "http://127.0.0.1:3322/community-post.html?post_id=96" --out /tmp/g6
node scripts/gates/state-matrix-gate.mjs --page "http://127.0.0.1:3322/community-post.html?post_id=96" --out /tmp/g9
node scripts/gates/dom-hook-inventory.mjs --all --check --out /tmp/g3

# 3) 全站终验
node scripts/gates/viewport-a11y-gate.mjs --all --out /tmp/g7all

# 4) 独立 A/B 探针
node test-reports/fix-cmtinput/probe-cmtinput-placeholder.mjs
```

## 8. 证据目录

`test-reports/fix-cmtinput/`（30 文件 / 7.7MB）

| 路径 | 内容 |
| --- | --- |
| `g7-before/` `g7-after/` | 修复前后 G7 单页 JSON+TXT（FAIL/PASS 对比） |
| `g7-before-settle5k/` | **假绿陷阱**证据（不带 `?post_id=96` 的 PASS） |
| `g7-all-after/` `g7-all-after2/` | 全站 `--all` 两次（run1 采样瞬态 / run2 终验全绿）+ stdout |
| `g6-before/` `g6-after/` `g9-before/` `g9-after/` | 零回归 before/after |
| `g3-after/` | G3 全站 25 页钩子零漂移 |
| `probe-cmtinput-placeholder.mjs` + 2 个 `.out.txt` | 独立 A/B 探针（挂/摘 class）与 no-query 反证 |
| `screenshots-community-post/` | before-1280 / after-1280 / all-run1-1280（未渲染空白）/ all-run2-360 / all-run2-1280 |

## 9. 结论

**唯一余红已清零且可复现**：`#cmtInput` 补挂 `clay-input` → `::placeholder` 由 UA `rgb(117,117,117)`（4.37:1）切换为令牌 `--text-muted`（`#6B6580`，**5.25:1**）；G7 全站 25 页 275 checks 全绿、全站 contrast 失败数 0；G6/G9 单页与 G3 全站均零回归；改动面 = 1 文件 1 行 1 class，`theme.css` 零触碰。
