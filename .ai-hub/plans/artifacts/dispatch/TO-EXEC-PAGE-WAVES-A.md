# TO-EXEC-PAGE-WAVES-A — 逐页重塑包 A：学生端核心 8 页

## 使命（1 天工期主干，Gate A 已批款+底座已验收）

按已批款风格（黏土拟物；login 配色=B 变体、主表面=moss 绿 #B8D8A8）重塑 8 个生产页。**每页独立 commit**（单页可回滚），每页门禁全绿才算完成。

## 你的页面（只许碰这 8 个文件+其引用的公共静态资源）

`edu-frontend/public/` 下：login-register / dashboard / courses / course-detail / learning / favorites / practice / me（.html）

## 必读资产（开工前实读，全部为已验收事实）

1. `docs/前端风格重塑方案.md` §3.1 CSS 禁改黑名单（六条，违反=FAIL）、§7.1 令牌（真身在 theme.css）、Gate A 批款块
2. `edu-frontend/public/theme.css` —— **唯一样式事实源（L2 冻结）**：只用其中的变量与组件类，**本任务禁改 theme.css 本身**；某令牌不适配 → 停手上报变更单，勿私改
3. `edu-frontend/_prototypes/clay-gatea/login-b.html` —— 你这包的风格基准（批款款；注意主表面已按批款换 moss 绿）
4. `docs/dom-hooks-frozen.md` —— 你 8 页的 DOM 钩子冻结清单（**结构层生死线**）
5. `docs/icon-inventory.md` —— 你 8 页的 emoji/图标替换语义表（sprite 30 枚已冻结）
6. `docs/rollback-drill.md` —— 回滚剧本（你的单页 commit 即 Scenario A 粒度）

## 每页工序（8 页同流程）

1. 页头接入 `<link rel="stylesheet" href="/theme.css?v=7fed87f">`（**全站统一版本号**，G8 断言同版本）；页内旧 CSS 按三层分离迁移到令牌/组件类，`.page-<name>` 命名空间包页内私有变量
2. **emoji 图标全换** Phosphor sprite：`<svg class="ic"><use href="/assets/icons/icons.svg#ic-*"/></svg>`（对照 icon-inventory 你页的行；icon-inventory 里没有对应 sprite 名的语义 → 停手上报，勿自造）
3. courses.html / refund.html 特有债：**移除 Google Fonts 外链**（G8 红项，本地字体栈替换）
4. 清偿你页的 G6/G7/G9 存量债：点击区 ≥44×44、文字对比度 ≥4.5:1（用 theme.css 组合不行就加页内修正层，禁改令牌）、reduced-motion、焦点可见、Tab 可达、横向溢出、长文本适配
5. 门禁全跑（绿了才提交）：
   - `node scripts/gates/dom-hook-inventory.mjs --page http://127.0.0.1:3322/<page>.html --check`
   - `node scripts/gates/style-dep-gate.mjs --page ...`（G6）
   - `node scripts/gates/viewport-a11y-gate.mjs --page ...`（G7）
   - `node scripts/gates/asset-cache-gate.mjs --page ...`（G8，须全绿）
   - `node scripts/gates/state-matrix-gate.mjs --page ...`（G9）
   - `node scripts/febe_contract_check.py`（包跑一次，接口面应零变化）+ 内联 JS `node --check` + 既有 CDP console 零报错验证（verify_pages_cdp.mjs 先实读用法）
6. 单页 commit：`style(fe)/<page>: clay 重塑+门禁绿(PACK-A)`

## 铁律（违反任一=返工）

- 结构层（JS 依赖的 id/class 名/data-*）与行为层（script/edu-api.js/接口路径/事件绑定）**一个字符不许动**；只改视觉层
- CSS 禁改黑名单（方案 §3.1）：测量依赖元素布局属性/状态类显隐语义/pointer-events/z-index 层级表/结构选择器依赖/chat 输入区与 HITL 卡几何
- 禁改 theme.css / icons.svg / 其他包页面 / 后端任何文件；不 push
- 开工前后 `git branch --show-current` = feature/opt-waves
- 环境：前端 3322 / 后端 9988 需在跑（health 自查）
- 报告：`.ai-hub/plans/artifacts/dispatch/REPORT-PAGE-WAVES-A.md`——每页一行门禁结果表（G3/G6/G7/G8/G9/G1 各自 checks/failed 数）+ 存量债清偿对照（哪些红项被你清了）+ 资产消费证据 + 批判承接段（无重叠写「无」）
