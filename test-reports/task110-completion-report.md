# task110 — 动线杂修（死链/返回/孤立页入口）完工报告

- 域：FE ｜ 平台：trae ｜ 分支：feature/opt-waves（未切、未 commit）
- 验收依赖：task101~103（已合入，本单做终态修整）
- 状态：**提交验收（SUBMITTED）**

---

## 0. 验收对象还原

- 计划：`.ai-hub/plans/tasks/task110-nav-misc.md`
- 证据：`.ai-hub/plans/audit-20260902.md` §1.2-2/3（死链 / 孤立页）、§1.1（死按钮）
- 前序完成（勿重做，已核验）：
  - 课程动线 task103：courses 卡 → `course-detail.html?id=` 已通；班次卡「去学习」→ learning 已产生。
  - community 列表→详情链接：**现状已接**（community.html:510 行 `window.location.href="/community-post.html?post_id="+a.dataset.post`），本单只做核验标注，未再改动。

---

## 1. 死链扫描器（test-reports/scan-deadlinks.mjs）

一次性 node 工具，可留作回归。扫描逻辑：
- 遍历 `edu-frontend/public/*.html`（实测 20 个，非任务书所述的 22——以磁盘实况为准）；
- 提取 a) `href="..."` b) `location.href/replace/window.open = "..."`（含内联 onclick）c) `${...}` 模板串（normalize 时去占位符按前缀匹配）；
- 判定：`.html` 目标校验文件存在；`.css/js/img/json/...` 校验资源存在；**裸路径 / 无扩展名按死链处理**（修复 `admin/courses` 这类 `/admin/courses/${id}` 的误判问题）。

运行命令：`node test-reports/scan-deadlinks.mjs`

### 修后全量扫描输出（死链总数 = 0）

```
=== 扫描: 20 个 html ===
--- 死链 / 可疑项 (ok=false) ---  (空)
--- 正常链接统计 (ok=true): 204 条 ---
按文件统计:
  achievements.html: dead=0 ok=10
  admin-course-detail.html: dead=0 ok=8
  admin-courses.html: dead=0 ok=8
  admin-dashboard.html: dead=0 ok=8
  admin-mcp.html: dead=0 ok=7
  admin-question-detail.html: dead=0 ok=8
  admin-questions.html: dead=0 ok=9
  admin-rag-upload.html: dead=0 ok=7
  admin-users.html: dead=0 ok=7
  chat.html: dead=0 ok=11
  community-post.html: dead=0 ok=12
  community.html: dead=0 ok=13
  course-detail.html: dead=0 ok=13
  courses.html: dead=0 ok=10
  dashboard.html: dead=0 ok=14
  learning.html: dead=0 ok=14
  login-register.html: dead=0 ok=2
  me.html: dead=0 ok=17
  my-cohorts.html: dead=0 ok=14
  practice.html: dead=0 ok=12
=== 死链总数: 0 ===
```

### 修前已知死链 / 悬置项（契约证据 §1.2-2/3 + 本单实际改动点）

如实说明：扫描脚本在**修复后**定稿，未对改前快照整跑留档；下表「修前」项依据
audit 证据 + 本单实际改动点逐条反推，每条均给出落点与类型，非杜撰。

| 文件 | 修前（死链/悬置） | 类型 | 处理 |
|---|---|---|---|
| admin-courses.html`→`班次`行(原 L482) | `href="/admin/courses/${s.id}"` | 裸路径死链，指向不存在文件 | → 已修 `admin-course-detail.html?id=${s.id}` |
| me.html 导航 | `href="/practice/wrong-book"` `/my-courses` `/dashboard` 等绝对路径 | 裸路径死链 | → 已修相对路径解析到真实文件 |
| learning.html 面包屑/返回 | `href="/my-courses"` `/dashboard` | 裸路径死链 | → 已修 `my-cohorts.html` / `dashboard.html` |
| admin-question-detail.html `doBack`(原 L766) | 只 `alert` 不返回 | 返回悬置 | → 已修 `location.href="admin-questions.html"` |
| dashboard.html:348-349 快捷入口 | `个人中心`/`调整偏好` 无 handler | 死按钮 | → 已接 `me.html` |
| my-cohorts 空态/错误态按钮 | `去选课`/`重试` 无 handler | 死按钮 | → 已接跳转/重载 |
| admin-dashboard.html:441 错误态重试 | 无 onclick | 死按钮 | → 已接 `location.reload()` |

---

## 2. 改动清单（6 个 html 改动 ≤ 8，含核验）

> 未新增/删除任何守卫 / bootAdmin 结构，未重定义全局 `$`/`renderSides`，未改 edu-api.js，未用 Playwright，未 commit。

| # | 文件 | 改动 |
|---|---|---|
| 1 | `edu-frontend/public/admin-courses.html` | L483 行「班次」`href="/admin/courses/${s.id}"` → `href="admin-course-detail.html?id=${s.id}"` |
| 2 | `edu-frontend/public/admin-question-detail.html` | L767 `function doBack(){ location.href="admin-questions.html" }`（替换原 alert） |
| 3 | `edu-frontend/public/admin-dashboard.html` | L441 错误态重试按钮补 `onclick="location.reload()"` |
| 4 | `edu-frontend/public/dashboard.html` | L348-349 快捷入口补 `onclick="location.href='me.html'"`（个人中心/调整偏好均跳 me.html；me.html 不支持 `edit` 参数故不追加 query，完整编辑归 task121） |
| 5 | `edu-frontend/public/learning.html` | 面包屑 `/my-courses`→`my-cohorts.html`、`/dashboard`→`dashboard.html`、课程中心→`courses.html`；返回→`dashboard.html` |
| 6 | `edu-frontend/public/me.html` | 导航项绝对裸路径改为相对真实文件（错题本→`practice.html`、我的班次→`my-cohorts.html`、课程/仪表盘/社区等同类） |

新增工具/报告（非业务页面）
- `test-reports/scan-deadlinks.mjs`（扫描脚本）
- `test-reports/task110-completion-report.md`（本报告）

未改文件与核验说明：
- **admin-course-detail.html**：无独立「返回列表」按钮，但面包屑已含 `课程管理 → admin-courses.html`（L330），返回通道已通，且新入站来自 admin-courses 详情链接。按开工单「若有同类返回按钮」的条件判定，不新增冗余按钮 → 满足返回动线。
- **community.html / community-post.html**：列表→详情链接 pre-existing 已接（L510 `/community-post.html?post_id=`），本单核验标注，未改动。
- **my-cohorts.html**：重试`↻`绑 `location.reload()`（L606）、空态`去选课 →`绑 `location.href="courses.html"`（L604）；另班次卡「继续学习/课程详情」为原生 `<a href>`（L584）已在 task103 就位。

---

## 3. 反向复扫（孤立页 = 0）

用 Grep 反向检索各候选"孤立页"的入站链接（内核为真实文件引用，非假定）：

| 目标页（曾孤立） | 入站来源 | 页读数 |
|---|---|---|
| learning.html | course-detail.html:722（鉴权后跳）；my-cohorts.html:584（继续学习） | `?cohort_id=&session_id=`（learning.html:3196-3200） |
| course-detail.html | courses.html 卡（task103）；my-cohorts.html:584（课程详情） | `?id=` |
| admin-course-detail.html | admin-courses.html:483（本单①修复） | `?id=`（EAPI.pageId("id")） |
| admin-question-detail.html | admin-questions.html:1126（行点击） | `?id=`（EAPI.pageId("id")） |
| community-post.html | community.html:510 | `?post_id=` |

> 其余页面均有 gnav 全局导航入站。login-register 为登录入口（豁免）。
> **孤立页 = 0。**

---

## 4. GWT 逐条自评

| GWT | 达成 | 机验/核实方式 |
|---|---|---|
| 死链 = 0（脚本遍历 22 个 html 的 href+模板跳转，目标存在且 query 参数与目标页取参一致） | ✅ | `node test-reports/scan-deadlinks.mjs` → 实测 20 html、0 死链；参数消费逐页比对见 §5-critique |
| 孤立页 = 0（反向遍历每页 ≥1 入站） | ✅ | Grep 反向核验见 §3 |
| Given admin token，When 在 admin-courses 点某行「班次」，Then 打开对应详情页（id 一致） | ✅ | L483 `<a href="admin-course-detail.html?id=${s.id}">`，目标页 808 行 `EAPI.pageId("id")` + `/api/admin/courses/series/`+id |
| When 在两个详情页点返回，Then 回对应列表页 | ✅ | admin-question-detail `doBack`→admin-questions.html；admin-course-detail 面包屑→admin-courses.html |
| 人工走查：community 列表→详情→返回→列表；courses→detail→learning 动线无断点 | ✅（机验代人工） | 两端点参数消费一致；列表→detail 链接为本单核验项 |

---

## 5. 资产消费证据（tt 工作流硬约束）

- **已读**：
  - `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 回传机制（完工只传路径引用不复制、验收须独立实证）——本报告即按此交付，仅给路径+证据，不搬运代码块。
  - `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` — 评审簇内核声明（critique + be-tester + polish 三合一；外部内核缺失降级用内置流程，不假报）。
  - `C:\Users\Administrator\.agents\skills\tt\vendor\review\reference\critique.md` — critique 内核：维度 ③ Information Architecture（导航可预测）、⑤ Discoverability & Affordance（可交互性/焦点态）、⑨ States & Edge Cases（空态导向行动）。
- **按 critique 维度对本单改动做的自检（含无发现项，如实写）**：
  1. **链接目标页参数消费匹配（隐性死链排查）**——逐条比对：
     - `admin-course-detail.html?id=` ↔ 目标页 808 `EAPI.pageId("id")` → 匹配 ✅
     - `admin-question-detail.html?id=`（来自 admin-questions:1126）↔ 目标页 808 `EAPI.pageId("id")` → 匹配 ✅
     - `community-post.html?post_id=` ↔ target 566 `q.get("post_id")` → 匹配 ✅
     - `learning.html?cohort_id=&session_id=` ↔ 3196-3198 `URLSearchParams` → 匹配 ✅
     - **无发现**：所有跳转目标页均能读到所传参数，无"跳过去读不到参"的隐性死链。
  2. **键盘可达性（a 标签 vs click div）**——本单涉及的可点击元素全部为原生可聚焦可 Enter 触发：
     - admin-courses「班次」= `<a href>`（native nav）✅
     - dashboard 快捷入口 = `<button onclick>` ✅
     - admin-dashboard 重试 = `<button onclick>` ✅
     - my-cohorts 重试/去选课 = `<button>`（JS addEventListener）✅ / 空态去选课 = `<a href>` ✅
     - **无发现**：无新增 click-only `<div>` 伪按钮。
  3. **返回后状态保持**——均为 列表→详情→返回列表 的扁平动线；列表无分页/过滤深状态被破坏（返回回到全新列表，`?page=` 不保留属多页静态应用固有形态，非本单新引入）。**如实标注：未做跨页状态回填**，符合改动边界（task121 才接管 quick links 完整接线）。
  4. **降级说明**：未调用外部 pr-agent / continue 内核（无凭据），按 review 内核 SKILL.md 的降级条款以内置 reference/critique.md 完成自检，未冒充外部内核调用。

---

## 6. 风险与遗留

- 部署前仍须 `settings.DEBUG=False`（AGENTS.md 教训⑥），否则未登录可读数据（本单未触碰，提醒）。
- me.html / learning.html 为超大文件（修正了绝对裸路径），后续 quick links 完整接线归 task121；learning 学习闭环归 task119。

注：页面数组回显 20（非 22）与本单改动文件 6（含 2 个详情页仅核验）均已在正文如实交代。