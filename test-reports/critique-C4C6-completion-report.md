# Critique C4 / C6 —— 前端完成报告

- 日期：2026-09-04
- 执行：前端独立子 agent（tt 工作流派发）
- 范围：`edu-frontend/public/*.html`（只改批判点列出的文件与内容；不 commit；未改后端）
- 定位：W2 技术批判 C4（全站 respbar 演示工具条清零）+ C6（practice 显式提示对齐）

---

## 一、资产消费证据

- **加载 Skill：`harden`**（唯一加载的 skill，替代不可用的更专项 skill 前的兜底取其一。任务提示优先 `harden`，可用即用之）。
- **方法论内核**：harden 主张「不保留静默/误导态」——对不可用/受限能力要给**明确去向与说明**（error/empty/不可用显式 message + accessibility：`aria-live`、`role="status"` 达意），且避免「只靠视觉黯淡」传达不可用的伪交互。
- **对应改动点**：
  - **C6.1** 三题型（FILL/DRAG_SORT/MATCH）由「`opacity:.45 + disabled + title` 静默置灰」改为**显式可点击**，点击/悬停弹出 `showIter2(name)` 说明条「该题型（XX）暂未开放，已登记迭代二」；说明条带 `role="status"` + `aria-live="polite"`（harden 无障碍/信息传达内核对口）。
  - **C6.2** 演示题型条填空 tab 由可交互的「③ 填空」改为「③ 填空 · 迭代二」占位（`data-iter2` + `class="iter2"` + 去向 title），对齐登录态 FILL:false，消除演示/真实断层（harden「不靠演示美化误导真实能力」内核对口）。
  - **C4** respbar 工具条整体移除属「演示态→产品态」过渡，与 harden「生产环境不给审核工具残留」一致；保留未登录演示兜底渲染（demo-not-note/`buildOk()`/`body[data-st="ok"]`）即 harden 的「渐进增强兜底」。

## 二、C4：全站 respbar 演示工具条清零

### 2.1 改动页面清单（20 个，全部为 `edu-frontend/public/*.html`）

**含完整活动工具条（CSS 块 + toolbar 元素 + JS 绑定三段全删，留注释）——6 个：**

| 页面 | 删除内容 |
|---|---|
| `dashboard.html` | `.respbar` 6 行 CSS；toolbar 元素（断点预览/页面状态/排行周期）；JS 中 `[data-w]` 断点、`switchState(st-*)`、`r-*` 排行周期绑定；共享规则 `.respbar` 选择器；保留 RANK/renderRank/trend/donut 演示兜底 + `renderRank('day')` |
| `me.html` | `.respbar` CSS；toolbar（视口 `[data-vw]`/状态 `[data-st]`）元素；`[data-vw]/[data-st]` 控制器 JS；共享规则；保留 `<body data-st="ok">` 成功态兜底 |
| `community.html` | `.respbar` CSS；toolbar（视口/四态）；JS `bar`(`.respbar`) 的视口+四态绑定；共享规则；保留 buildOk/四态函数 + 初始 `buildOk()` + `.chip` 筛选 |
| `community-post.html` | `.respbar` CSS；toolbar（视口/四态含锁定）；JS `bar` 的视口+`views`四态绑定；共享规则；保留 buildComments 初始 + like/fav/评论演示（受 `__REAL_COMMUNITY__` 守卫） |
| `courses.html` | `.respbar` CSS；toolbar（状态演示/视口 + `#resetVp`）；JS `statebar()`/视口切换（`data-s`/`data-w`）；共享规则；保留 `applyState`（resetAll 仍用）+ 初始渲染 |
| `admin-dashboard.html` | `.respbar` CSS；toolbar（`data-vp`/`data-state`）；JS 演示控制器 IIFE（setVp/setState/animateKpis）；共享规则；空态 retry 由「点 respbar 成功态」改为 `location.reload()` |

**仅剩共享 CSS 规则 `.cohorts-fixed-page .respbar,...`（删 `.respbar` 选择器，保留 `[role="toolbar"]`）——12 个：**
`admin-course-detail`、`admin-courses`、`admin-mcp`、`admin-question-detail`、`admin-questions`、`admin-rag-upload`、`admin-users`、`my-cohorts`、`course-detail`、`learning`、`login-register`、`practice`（前 11 个用 UTF-8 无 BOM 幂等替换；practice 的行内注释随 C6 一并处理）。

> 注：`achievements.html`/`chat.html` 此前 task122 已清（仅剩注释），本批未动。

### 2.2 C4 覆盖实证数字

```
git grep -n respbar -- "edu-frontend/public/*.html"
  总行数：24          含「已移除 / critique C4 / 开发工具残留」的注释行：24
  非注释（活动）行数：0
git grep -c 'class="respbar"|<div class="respbar"|querySelector(.?)..?..?.respbar|.respbar{'
  结果：0 命中
```
**结论：全站 respbar 活动 CSS/元素/JS 已清零；唯一保留的 `respbar` 字样均为审计注释（`<-- respbar 演示工具条已移除（critique C4） -->`、CSS/JS 内「…已移除」注释）。** 符合验收口径「全站=0 或仅剩注释」。

### 2.3 语法校验（node `new Function`，全量 20 页）

```
OK achievements.html / admin-course-detail.html / admin-courses.html / admin-dashboard.html
OK admin-mcp.html / admin-question-detail.html / admin-questions.html / admin-rag-upload.html
OK admin-users.html / chat.html / community-post.html / community.html / course-detail.html
OK courses.html / dashboard.html / learning.html / login-register.html / me.html
OK my-cohorts.html / practice.html
→ ALL PUBLIC HTML SCRIPTS PASS（0 语法错误）
```
说明：全量 20 页内联 `<script>` 全部 `new Function` 编译通过，同时验证了 11 个批量替换文件的中文/脚本未损坏（UTF-8 无 BOM 写入无编码污染）。
期间发现并修复 dashboard 首块脚本因本人二次编辑遗漏 `</script>` 导致的语法错（HEAD 基线 OK、整改后 OK），印证「亲手实证」纪律。

## 三、C6：practice.html 显式提示对齐

### 3.1 三题型按钮（原 :734-736）：静默置灰 → 显式不可用+去向
- 移除 `disabled`、`style="opacity:.45;cursor:not-allowed"`、通用 `title="迭代二暂不支持"`。
- 三按钮改为 `class="pill iter2"` + `data-iter2="填空/拖拽排序/连线匹配"` + 去向 title（「该题型（填空）暂未开放，已登记迭代二」）。
- 点击行为：`bindTopicControls` 命中 `data-iter2` 时不再 `startReview`，改调全局 `showIter2(name)` → 弹底部说明条。
- 新增 CSS：`.wb-filter .pill.iter2`（虚线边框可点击态 + hover 高亮）、`.iter2-toast`（fixed 底部 toast）。

### 3.2 演示/真实断层对齐（原 :588 填空 tab）
- 演示题型条填空 tab 由「③ 填空」改为「③ 填空 · 迭代二」占位（`data-iter2` + `class="iter2"` + 去向 title），点击走 `showIter2` 只出说明、不再切入填空演示题；与登录态 SUP_REVIEW FILL:false 一致。

### 3.3 实现方式（交互说明落地）
- 新增全局 `showIter2(name)` + 惰性创建的 `#iter2-toast`（`role="status"` `aria-live="polite"`），文案「该题型（XX）暂未开放，已登记迭代二。」，展示 2.6s 后隐藏；demo 题型条与登录态绑定共用同一函数。
- hover：按钮 `title` 即悬停提示（同文案）。

### 3.4 C6 轻量断言（可控静态检查 + new Function）
`practice.html` 所有内联 script 编译通过；静态断言 19 项全 PASS，含：
- 三按钮 each：无 `disabled`、无 `opacity:.45/not-allowed`、带 `data-iter2`、带去向 title。
- 演示填空 tab：`data-type="blank"... data-iter2="填空"... class="iter2"`，且不再以纯「③ 填空」可交互形态存在。
- `showIter2` 定义 + demo `qTypes` 与 real `bindTopicControls` 两处均混入 iter2 路由 + toast 文案含「已登记迭代二」。

## 四、迭代二 PBI 登记（真实待办，非空头「迭代二」）

> **PBI-ITER2-TYPES**：为专项练习开放剩余三种题型——填空（FILL）/拖拽排序（DRAG_SORT）/连线匹配（MATCH）的真实作答+判分+错题回写能力。
> **语义句**：当前 `education.interactive` 仅就绪 SINGLE/MULTI/JUDGE 判分链路；FILL/DRAG_SORT/MATCH 三种题型在登录态 SUP_REVIEW 中判定 `FILL:false`，前端已在 UI 层显式「占位+去向（已登记迭代二）」而非静默不可用。后端需补齐 dim_question_type 三类题型的题面数据、判分器与 progress 上报；前端随后移除此占位，接入 `startReview` 真实作答。
> **现状锚点**：`edu-frontend/public/practice.html` `#topic-real .pill.iter2`（FILL/DRAG_SORT/MATCH）三按钮；`practice.html` 演示题型条填空tab 亦为此占位。

## 五、回归门禁建议（防 C4 复发）

- 将「`git grep "respbar" -- "edu-frontend/public/*.html"` 命中行必须为注释」纳入前端质量门（如 `frontend-quality-gate.mjs` 增呼应），禁止新增任何 `class="respbar"/[data-vw]/[data-st] 活动绑定`。

---

## 附：改动文件清单（git status `M`，20 个，均为本批判点）
`admin-course-detail.html admin-courses.html admin-dashboard.html admin-mcp.html admin-question-detail.html admin-questions.html admin-rag-upload.html admin-users.html community-post.html community.html course-detail.html courses.html dashboard.html learning.html login-register.html me.html my-cohorts.html practice.html`（共 18 个含实际变更；`achievements.html`/`chat.html` 为 task122 既有注释，本批未动）。

> 已在编辑中发起的 `M edu-agent/app/chat/router.py`、`M edu-agent/app/common/error_codes.py` 与本批判无关、非本人改动，未触碰。