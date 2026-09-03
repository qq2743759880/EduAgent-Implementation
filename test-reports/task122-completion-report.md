# task122 — 工程卫生包（前端）完工报告

- 域：FE ｜ 平台：trae ｜ 状态：完工待验收（**未 commit**，遵守硬性守则）
- 口径：O5 卫生达标——演示残留清零、错误可见、非法 HTML 修复，站点由"演示态"过渡到"产品态"

---

## 1. 改动清单（文件 × 行号 × 改动内容，grep 实证）

### 1.1 移除全部 HMR 残留模块脚本（`import('/@vite/client')`）
三文件初值合计 16 处，全部整块删除（含 `try{...}catch{}` 外壳，仅保留相邻 `<style>`）。改后 `rg /@vite/client` 全站 = 0。

| 文件 | 改前 /@vite/client 计数 | 删除的 HMR 块（改前行号） |
|---|---|---|
| `public/me.html` | 8 | 172–177、510–515、848–853、2390–2395、2728–2733、3066–3071、3404–3409、3742–3747 |
| `public/learning.html` | 4 | 245–251、583–589、921–927、1259–1265 |
| `public/login-register.html` | 4 | 132–138、470–476、808–814、1146–1152 |

grep 实证：`rg -l "/@vite/client" *.html` → 无输出（=0）。

### 1.2 移除/条件化演示控制器与演示状态条（保留无 token 演示态）
- `public/chat.html`：
  - L423（原 429–446）`<div class="respbar">…` 演示状态条（状态/视口切换审核工具）整块删除。
  - L594 `if(!__logon){ .respbar button[data-w]/[data-s] … }` 视口切换 + 状态演示绑定块删除（属开发工具）；`__logon` 保留用于是否渲染演示会话。
  - L535 `draw()` 内 `.respbar button[data-s]` 状态高亮行删除（按钮已不存在）。
  - L47 `.respbar{…}` CSS 块删除；L267 死选择器 `.respbar` 剔除（保留 `[role="toolbar"]`）。
  - 无 token 演示态保留：L607 `if(!__logon){ renderSides(); draw("history"); }` 原样。
- `public/login-register.html`：头注已声明 demo-ctrl/演示状态机在 R3 移除；L2799 `.demo-route` 演示条已为空注释，**无需改动**（核实无残留）。
- `public/achievements.html`（审计外同模式补充清理）：L275 演示控制 respbar 工具条删除、L680 绑定 IIFE 删除、L45 `.respbar` CSS 删除、L239 死选择器剔除；body `data-st="ok"` 默认成功态保留（无 token 演示数据仍渲染）。

### 1.3 body 重复 class 属性合并为单个
`<body class="admin-html-page" class="admin-html-page" … ×8>` → `<body class="admin-html-page">`，波及 8 个管理页（审计仅列 admin-rag-upload，实际为模板整页复制，全部一并修复）：

| 文件 | 行号（改后） |
|---|---|
| admin-rag-upload.html | 285 |
| admin-dashboard.html | 261 |
| admin-users.html | 277 |
| admin-courses.html | 253 |
| admin-questions.html | 325 |
| admin-mcp.html | 291 |
| admin-course-detail.html | 310 |
| admin-question-detail.html | 286 |

### 1.4 错误可见性：页面级静默 catch 全部接 onError → 统一 toast
- `public/edu-api.js` L195–227：新增 **默认 onError 消费** —— 在 `emitOnce` 基础上追加统一 toast（`id="eapi-toast-root"` 固定容器，`aria-live=assertive`，3s 自动消失 + `opacity/transform` 过渡，`prefers-reduced-motion` 下直接移除），`console.error("[EAPI]",…)` 由 `emitOnce` 统一输出。**签名未动**（仅"加 onError 消费"，符合授权）。
- `public/admin-dashboard.html` L518：唯一精确 `catch(function(){})` 改为带说明的 `catch(function(){ /* 指标获取失败：错误已由 EAPI.onError 统一 toast 提示 */ })`（错误可见性由中央 onError 保证）。
- 效果：全站 `.catch(function () {})`（带空格）等静默吞错块错误仍会被中央 onError toast 抛出，后端停机打开 dashboard/community 等页出现 toast 而非无声失败。

### 1.5 演示数据兜底统一加"演示数据"角标（未登录可见区块）
固定左上角 `position:fixed` 角标，仅无登录/无 EAPI 时注入（登录态不显示），避免真实/演示混淆。经 design 自检调整配色为 `#b45309`（琥珀深）保证对比度。

| 文件 | 行号 | 触发条件 |
|---|---|---|
| practice.html | 1310 | 未登录演示态（该页未登录保留演示数据、不跳登录） |
| learning.html | 3467 | 未登录演示态 |
| my-cohorts.html | 629 | 未登录演示数据 |
| achievements.html | 831 | 未登录演示数据（默认 ok 态） |
| courses.html | 790 | 无 EAPI（静态降级演示） |

（dashboard/community/course-detail/me/chat 等页未登录会 401→跳登录，无"未登录可见区块"，不注入角标。）

### 1.6 杂项
- `<html lang>`：全站 20 页均已 `lang="zh-CN"`，无缺失。
- 重复 id：机验全站 0（剥除 script/style 内容后仅审计真实 DOM 的 ` id="` 属性；`data-id`／JS 模板占位符剔除）。
- 演示态保留回归口径：无 token 打开每页不报错且显示演示数据 + 角标（practice/learning/my-cohorts/achievements/courses)，其余页按守卫跳登录。

---

## 2. 机验输出

- **node 语法解析全页 0 SyntaxError**：对 20 页全部内联 `<script>`（`src=` 外部脚本跳过）逐段 `new Function(code)` 校验 → `DONE. files=20 passed=20 failed=0`；另 `node --check edu-api.js` → 语法 OK。
- grep 全 0：
  - `rg -l "/@vite/client"` → 无输出
  - `rg -l "catch(function(){})"` → 无输出
  - 全站 `<body … 多 class>`（`class=` 出现次数 >1）→ 0
  - 重复 id（剥离 script/style）→ 全 0
  - `<html lang>` 缺失 → 0
- 元组检查通过清单：20 页 `[ OK ]`（achievements、admin-*、chat、community、courses、dashboard、learning、login-register、me、my-cohorts、practice 等全部通过）。

---

## 3. 边界 / 错误反馈自检（critique 三视角）

**交互态（loading/success/error/empty）**
- 移除 respbar 后 chat/achievements 无 token 演示态仍由脚本兜底渲染成功态，`__logon`/`data-st=ok` 默认值保持，无死绑定指向已删节点（`querySelectorAll` 无匹配即 no-op，不抛错）。
- 空态/错误态按钮（chat composer 状态文案、admin 重试）未被本次改动触碰，保持原逻辑。

**边界（无 token / 后端停机 / 静态降级）**
- 无 token：demo 兜底页（practice/learning/my-cohorts/achievements）显示演示数据 + 角标；受守卫页 401→跳登录并清 token，登录页自身不重复跳转。
- 后端停机（已登录）：EAPI.get 失败 → `emitOnce` → 统一 toast（3s），dashboard/community 等页不再无声失败；401 单独跳过 toast（因已跳转）。
- 静态降级：courses `!hasApi` 演示数据加角标。

**错误反馈**
- 统一 toast：`role=status` + `aria-live=assertive`（屏幕阅读器可感知）、3s 自动消失、`pointer-events` 不挡操作、底部居中不遮头部导航；`prefers-reduced-motion` 下零动画。
- 设计自检发现并修复两处：① "演示数据"角标琥珀 `#f59e0b`+白字 11px 对比度不足 → 加深为 `#b45309`；② toast 动画未尊重 `prefers-reduced-motion` → 已加 `matchMedia` 守卫。

---

## 4. 资产消费证据段

- 实际读取资产：**frontend-design skill**（`C:\Users\Administrator\.agents\skills\frontend-design`）。以其审美/可及性/交互规则对本次新增的错误 toast 与演示角标做完工前自检。
- 自检发现并修掉的问题：
  1. 演示角标 `#f59e0b`/白字 11px 对比度不足（design color/contrast 准则）→ 加深为 `#b45309`。
  2. toast 过渡未考虑 `prefers-reduced-motion`（design motion/可及性）→ 加 `matchMedia` 守卫，降动效时直接移除。
- 说明：本批未再次调用 tt 编排 skill / 其它审计 skill（本次为单 agent 本地卫生包，无跨平台编排需求）；按开工单"如无对应 skill 被上下文暴露…通用前端卫生原则兜底"，上述 2 项为 skill 实际消费产物。

---

## 5. 遗留与降级项（如实标注）

1. **其它页面仍存在同类 respbar 演示工具条**：dashboard.html:309、me.html:4163、community.html:282、community-post.html（含 `.respbar` CSS 与绑定），admin-dashboard 等亦见（已在 body class 修复时邻见）。这些**不在本任务 audit §P2 枚举范围**，本次未改动，仅 chat.html/achievements.html 两处已清；建议后续任务统一清理（与 W1 守卫抽离可合并）。
2. **接口真实 HTTP 实测**：本次为纯前端卫生包，未起后端跑 curl/requests；toast 行为建议验收时按 GWT「后端停机→dashboard/community 出 toast」实测一次。
3. 未使用 Playwright（遵守守则）；渲染走查建议验收阶段对 22 页做视觉截图补充。
4. 开工单改动点 2 提到的 login-register.html:2904 演示控制器经核实已在 R3 移除（该行现为 `<script src="/edu-api.js">`），无残留可清。

**禁止 commit 已遵守；本次仅改动授权目录 `edu-frontend/` 下文件（含 `public/*.html` 与 `public/edu-api.js`，edu-api.js 仅加 onError 消费、签名未动）。**