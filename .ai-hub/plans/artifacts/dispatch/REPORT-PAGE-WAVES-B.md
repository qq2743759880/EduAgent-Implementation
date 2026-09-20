# REPORT-PAGE-WAVES-B — 逐页重塑包 B 完工报告（chat / community / community-post / achievements / coupons / my-cohorts / refund）

> 执行者：ZCode（cef78234）。分支对账：开工前 `git branch --show-current` = `feature/opt-waves`，收工后同（本报告末尾附终态对账输出）。
> 7 页全部完成：每页独立 commit + 六门（G3/G6/G7/G8/G9/G1）全绿（唯一例外：achievements G7 的 aria-title-frozen 为冻结快照与当前 DB 数据的漂移红，重塑前已存在，豁免上报，详见 §5）。
> 门禁运行环境：`EDU_GATE_TOKEN` 注入 student（user000001）真实登录态（curl 登录实测取 token，未写盘）；前端 3322 / 后端 9988 全程在跑。

## 0. 提交清单（每页独立 commit，均未 push）

| 页 | commit | 说明 |
|---|---|---|
| chat | `d5aa3e1` | style(fe)/chat: clay 重塑+门禁绿(PACK-B) |
| chat（补丁） | `52a28d7` | style(fe)/chat: 抽屉关闭态改子元素可见性(保 G6 z层快照一致性+G7 焦点治理)(PACK-B) |
| community | `8f7aa7f` | style(fe)/community: clay 重塑+门禁绿(PACK-B) |
| community-post | `466055a` | style(fe)/community-post: clay 重塑+门禁绿(PACK-B) |
| achievements | `3330fb9` | style(fe)/achievements: clay 重塑+门禁绿(PACK-B) |
| coupons | `743a05d` | style(fe)/coupons: clay 重塑+门禁绿(PACK-B) |
| my-cohorts | `b9e2428` | style(fe)/my-cohorts: clay 重塑+门禁绿(PACK-B) |
| refund | `6759437` | style(fe)/refund: clay 重塑+门禁绿+移除Google Fonts外链(PACK-B) |

复现：`git log --oneline | grep PACK-B`（其中 admin-* / practice / learning 等为 A/C 包并行执行者提交，非本包）。每个 commit 均只含本页 1 个文件，复现：`git show --stat <sha>`。

## 1. 每页门禁结果表（重塑后终态；证据目录 test-reports/page-waves-b/after/<page>/）

| 页 | G3 | G6 | G7 | G8 | G9 | G1(包级) |
|---|---|---|---|---|---|---|
| chat | 2项/0红 | 6项/0红 | 11项/0红 | 8项/0红/1警 | 56项/0红/5警 | 断点=0 |
| community | 2项/0红 | 6项/0红 | 11项/0红 | 8项/0红/1警 | 56项/0红/5警 | 同上 |
| community-post | 2项/0红 | 6项/0红 | 11项/0红 | 8项/0红 | 56项/0红/5警 | 同上 |
| achievements | 2项/0红 | 6项/0红 | 11项/**1红**(aria-title-frozen，见§5) | 8项/0红/1警 | 56项/0红/5警 | 同上 |
| coupons | 2项/0红 | 6项/0红 | 11项/0红 | 8项/0红/1警 | 56项/0红/5警 | 同上 |
| my-cohorts | 2项/0红 | 6项/0红 | 11项/0红 | 8项/0红 | 56项/0红/5警 | 同上 |
| refund | 2项/0红 | 6项/0红 | 11项/0红 | 8项/0红/1警 | 56项/0红/5警 | 同上 |

- 警告均为重塑前既有口径：G8 ×1 警 = 无 `?v=` 的本地样式引用计数；G9 ×5 警 = 注入 500/401/error 态时的 state-console-errors（服务端报错被前端记录属预期）。
- 复现（逐页）：
  ```
  # 取 token（真实 HTTP 登录）
  curl -s -X POST http://127.0.0.1:9988/api/auth/login -H "Content-Type: application/json" -d '{"account":"user000001","password":"Test@123456"}'
  export EDU_GATE_TOKEN=<access_token>
  node scripts/gates/dom-hook-inventory.mjs --page http://127.0.0.1:3322/chat.html --check --out test-reports/page-waves-b/after/chat
  node scripts/gates/style-dep-gate.mjs  --page http://127.0.0.1:3322/chat.html --out test-reports/page-waves-b/after/chat
  node scripts/gates/viewport-a11y-gate.mjs --page http://127.0.0.1:3322/chat.html --out test-reports/page-waves-b/after/chat
  node scripts/gates/asset-cache-gate.mjs  --page http://127.0.0.1:3322/chat.html --out test-reports/page-waves-b/after/chat
  node scripts/gates/state-matrix-gate.mjs --page http://127.0.0.1:3322/chat.html --out test-reports/page-waves-b/after/chat
  ```
  （其余 6 页替换页面名即可；输出摘录示例：`[G6] chat.html: PASS`、`[G7] refund.html: PASS`、`[G9] chat.html: PASS`，JSON 明细在 after/<page>/g*-*.json）
- 内联 JS 语法（G4）：每页全部 `<script>` 块以 `new Function(code)` 编译验证，7 页共 24 块全 OK（无 FAIL 输出）。
- 运行门（G5 代理）：按 `docs/rollback-drill.md` 口径，`verify_pages_cdp.mjs` 已废弃（硬编码 3000/8000），改用 `node edu-agent/scripts/check-demo.mjs --frontend-port 3322`，见 §4；且 G6/G7/G8/G9 四门各自内含 console-errors 检查，7 页全部 0 console 报错。

## 2. 存量债清偿对照（before=同 token 口径塑形前采集，目录 test-reports/page-waves-b/before/<page>/）

| 页 | before 红项 → after | 清偿方式 |
|---|---|---|
| chat | G6 interactive-target-44（15 个 <44px）→ 0红；G7 contrast-4.5+focus-visible+focus-not-obscured+reduced-motion → 0红；G8 theme-version-present+site-theme-version → 0红 | 按钮/汉堡/抽屉关闭钮 44px；muted 令牌化对比度；textarea 焦点环；reduced-motion 落块；接 theme.css?v=7fed87f；关闭抽屉子元素 visibility 隐藏出焦序 |
| community | G6 44px（39 个，含 gnav-user 链 31/26.8px、chips 33px）→ 0红；G7 contrast-4.5+focus-visible → 0红；G8 版本 → 0红 | gnav-user-link min 44×44；chips/pager/like-btn(pm 注入样式) 44px；全站令牌化 |
| community-post | G6 44px（16 个，含 likeBtn 41px）→ 0红；G7 contrast-4.5 → 0红；G8 版本 → 0红 | react-btn/c-like/pager/back/retry ≥44px；占位符/正文令牌化 |
| achievements | G6 44px（11 个）→ 0红；G7 contrast-4.5 → 0红；G8 版本 → 0红 | tabs/pager/retry 44px；r-me/别名补 --page-accent（G7 揪出漏定义，已修） |
| coupons | G6 44px（85 个！含 gnav 40px 项、cp-btn 39px、om-x 34px）→ 0红；G7 contrast-4.5 → 0红；G8 版本 → 0红 | 本页自有 gnav 直接改 44px；全部按钮/输入 ≥44px；pm/om 弹层令牌化 |
| my-cohorts | G6 44px（28 个，含 breadcrumb 链 17px）→ 0红；G7 contrast-4.5+tab-reachable → 0红；G8 版本 → 0红 | breadcrumb 44px 触达；封面浅渐变+深字；SDK tabs 初始 tabindex 0（见§5.3） |
| refund | G6 44px（4 个，输入框 43px）→ 0红；G7 contrast-4.5 → 0红；G8 zero-external-requests（Google Fonts 外链）+版本 → 0红；G9 empty/state-route → 0红 | 输入 ≥44px；**@import Baloo 2 移除→本地字体栈**；placeholder 令牌色（UA 默认灰 4.37:1 不达标）；flash 颜色字面量换安全对比色 |

汇总：before 全 7 页共 42 红（G6×7 + G7×11 + G8×15 + G9×1 + chat G7 多项），after 剩 1 红（§5.2 数据漂移，非新增）。

## 3. 资产消费证据（开工前实读，全部为本包施工依据）

1. `docs/前端风格重塑方案.md` §3.1 黑名单六条 —— 全程执行：状态类(.on/.open/.active/.show/.hitl-busy)显隐语义未动（chat `hitl-busy` 的 `pointer-events:none` 原样保留）、z-index 层级表逐值冻结（#gnav:130 / chat #drawer:80 / refund #flash:2147483001 / coupons toast 2147483000 / om-overlay 150 / FAB 40）、聊天输入区 textarea clamp(44..120) 与 HITL 卡 `.hitl-args{max-height:76px;overflow:auto}` 几何原样、无 pointer-events 改动、无结构选择器依赖改动。
2. `edu-frontend/public/theme.css`（L2 冻结）—— 未改一字节（`git diff 7fed87f -- edu-frontend/public/theme.css` 为空）；7 页均只消费令牌与 `.ic` 组件类，页内派生色全部包在 `:root` 页内别名块（L1）并注释对比度依据；`/icons/icons.svg` 未动。
3. `edu-frontend/_prototypes/clay-gatea/chat-b.html` —— chat 页按批款 B 变体落：AI 气泡 `linear-gradient(145deg,#D9D1FF,var(--clay-lavender))`、用户气泡 `#FFD0C1→#FFB59E`、侧栏 sky 渐变、HITL 卡 lemon 渐变、body 双 radial 打底、composer 内阴影，均与原型同配方。
4. `docs/dom-hooks-frozen.md`（chat 34 钩 / community 48 / community-post 109 / achievements 43 / coupons 31 / my-cohorts 28 / refund 8）—— G3 `--check` 7 页全 PASS（归一化钩子表达式零漂移，仅行号变动属允许）；JS 依赖的 id/class/data-* 未动。
5. `docs/icon-inventory.md` —— 7 页 emoji 按行映射替换为 Phosphor fill sprite（`/assets/icons/icons.svg#ic-*`，本地零外链），头像类（😊🤖🦊🎓🦉🐰🐧🐻🐣🎟️）按「avatars remain content」保留，见 §5.1。
6. `docs/rollback-drill.md` —— 采纳其 G5 代理口径（check-demo 替代已废弃的 verify_pages_cdp）；本包每页单 commit 即 Scenario A 粒度，G10 实演按剧本留待上线前（非执行者范围）。

## 4. 包级收尾门

- **G1**：`CHECK_DEMO_BACKEND=http://127.0.0.1:9988 edu-agent/.venv/Scripts/python.exe edu-agent/scripts/eval/febe_contract_check.py --quiet`
  输出：`[SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=0 to_connect=72 frontend=144 backend=216 contracts=242 malformed=0`，EXIT=0。接口面零变化。
- **check-demo（G2/G5 代理）**：`node edu-agent/scripts/check-demo.mjs --frontend-port 3322` → `汇总: 绿 17/21,红项 ⑯,WARN ⑧、⑩、㉒`。
  ⑯（9988 lifecycle 启停×5）为后端进程级检查：本包 8 个 commit 全部只触碰 `edu-frontend/public/*.html`（`git show --stat` 可复核），与 ⑯ 无因果；且三包并行共用同一 9988，其他包执行者的后端相关操作/门禁与 ⑯ 的 155s 启停窗口存在并发干扰可能。判为本包范围外环境项，如实上报编排者裁量。⑧⑩㉒ 为既有 WARN（与 MEMORY 中已知口径一致）。

## 5. 偏差与豁免上报（逐条如实）

### 5.1 保留的 emoji（非「图标」类，符合 icon-inventory 处置口径）
- 头像/吉祥物（内容）：chat 😊🤖（消息头像）🦊（mascot）；community(-post) 🐣（gnav ava+hero 原型位）；my-cohorts 🎓🦉🐰🐧🐻（页头+卡片吉祥物）；coupons 🎟️（页头 mascot）。
- achievements 徽章 `icon_emoji`：**后端数据字段**（`badgeCard` 渲染 `esc(bd.icon_emoji||"🎖️")`），属接口数据非前端结构图标，前端不替换；前端自有的 🎖️ 统计徽标/🔒 锁标/⬆️⬇️（改 ▲▼ 文本形）/👑🥈🥉（改名次数字+金银铜色牌）均已清除。
- chat ctxTag 的 📎：task07⑥ 起该元素被 JS 永久 `display:none`，且 attach 语义在 30 枚冻结 sprite 中无对应（inventory 口径「勿自造」）→ 保留并在本报告上报，待 sprite 扩展时再换。
- 文本形字符 ➤■✕‹›↻＋ 等：icon-inventory 的 Extended_Pictographic 扫描未将其列入 emoji 清单，且 send 停止态已改 ic-x、发送态改 ic-paper-plane-tilt，其余为文本按钮字符，保留。

### 5.2 achievements G7 aria-title-frozen 1红（豁免上报，重塑前已存在）
- 现象：after 终采 G7 唯一红。丢失的 9 条 aria 全部是 **JS 渲染动态数据**的 aria-label（流水分页按钮「第 5 页」…「第 11 页」「下一页」+ 排行 `rank-no.gold`「第 1 名」）。
- 实证为数据漂移非本包引入：① before（塑形前、同 token）采集同页同红（`before/achievements/g7-viewport-a11y-gate.json` 红=[contrast-4.5, aria-title-frozen]）；② 冻结快照期分页有 13 钮（logs_total≈101-110，11 页），当前实测 `GET /api/gamification/me/points?page=1&page_size=10` 返回 `logs_total":33`（4 页）——THEME-GATE（09-20）之后 DB 数据曾变动（与数据清理/盲测污染治理时段吻合），动态 aria 集合随数据合法变化；③ 静态 aria/title 属性（G7 冻结面中非动态部分）零丢失。
- 处置建议：编排者择机对 achievements 单页 `--update-baseline` 刷新 aria 快照（数据依赖型快照应随数据变更加密刷新），或接受数据漂移豁免口径。执行者不擅自改共享基线。

### 5.3 my-cohorts：SDK tabs 初始 tabindex 改 0
- before G7 tab-reachable 红（2 个非激活 tab `tabindex="-1"` 对纯 Tab 不可达，before 采集即红）。改静态初始值为 0：ARIA APG 允许 tabs 全部入 Tab 序；JS `activate()/selectTab()` 只写不读 tabindex，roving 逻辑不变；G3 零漂移复证。与 A 包 learning 页「roving tabindex 豁免上报」不同路径，本页直接清偿为绿。

### 5.4 行为层 JS 内的视觉串编辑（透明化说明）
- emoji→sprite、注入式 `<style>`（community 的 like-btn/postModal、coupons 的 flash 色、refund 的 flash 色 #ef4444/#16a34a→#C63E4A/#2E7D4F）涉及 JS 字符串字面量的**纯视觉**修改；未触碰任何 id/钩子类/事件绑定/接口路径/逻辑分支，G3 全绿+24 个内联脚本编译全过+四门 console 0 报错背书。

### 5.5 其他
- chat 抽屉 G7/G6 冲突的最终解法为「关闭态仅子元素 visibility:hidden」（抽屉本体保留在 z 层表），补丁 commit `52a28d7`，G3/G6/G7/G8/G9 复跑全绿。
- Mimosa 提交钩子在每次 commit 时提示 scanner_enobufs（兼容策略放行），按其要求不在本报告宣称项目安全结论。
- 门禁基线目录 `test-reports/page-waves-b/{before,after}/` 为本包专属副本（快照复制自 gate-baseline），未污染共享基线 `test-reports/gate-baseline/`。

## 6. 批判承接核对

对照 PACK-B 开工令引用的三份批判承接件（THEME-GATE 验收闭环 19 页实况口径纠偏、WRITE1 C-W1、EVALFREEZE-B1）逐条核对：与本包 7 个静态页视觉重塑无职责重叠项 → **无**。开工令特别铁律（HITL 卡 renderHitlCard 只换 class 与令牌、id/结构/事件绑定禁动）已执行：renderHitlCard 内仅替换 🛡️→ic-warning sprite 与超时文案去 ⏰，`.hitl-confirm/.hitl-reject/.hitl-note/hitlCard/hitlTick` 等全部原样，G3 复证零漂移。

## 7. 终态对账

```
git branch --show-current  →  feature/opt-waves
git status --short -- edu-frontend/public/  →  仅并行包（A/C）在途文件，本包 7 页全部已提交
```
未 push（遵守开工令）。等待编排者逐断言验收。
