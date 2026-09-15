# blind-t6 前端复测报告（真实学生视角盲测）

- **executionSessionId**：`20260915_184700_e0bc38`
- **被测身份**：`user000001 / Test@123456`（student）——对实现零知情
- **环境**：前端 `http://127.0.0.1:3000`（Next dev 静态托管 `edu-frontend/public/*.html`，存量进程未重启）；后端 `http://127.0.0.1:8000`（uvicorn 存量进程）；MySQL `127.0.0.1:3306`
- **时间窗**：2026-09-15 18:47 ~ 19:05（GMT+8）
- **纪律声明**：未读任何历史报告/验收文档；未使用 Playwright；未做任何 DB 写入；未新建测试数据（本次为只读探测，无残留数据需要清理）
- **方法学（三层证据）**：
  1. **真实 HTTP**：`curl --noproxy '*'` / Python `urllib` + `ProxyHandler({})`（HTTP_PROXY 会吞 loopback）
  2. **页面字节静态分析**：标注「可见正文」= 剥离 `<!--注释-->` / `<script>` / `<style>` 后的文本节点
  3. **最小 DOM 仿真宿主**：从 :3000 真实抓取页面字节与 `/edu-api.js`，按**文档顺序**执行页面自身的 JS，记录全部 `fetch` 调用 + `console.error` + 未捕获异常 + 各 DOM 节点最终写入值（源码见附录 A，可原样复跑）
- **标注图例**：`[实测]` 本机亲跑命令的真实输出 ｜ `[代码佐证]` 被测源码行/字节偏移 ｜ `[推演]` 由前两者推导、未直接观测 ｜ `[未验证]` 本轮未覆盖 ｜ `[文档原文]` 被测文件内的注释/文案
- **粒度限制（必读）**：仿真宿主**不是浏览器**——无 CSS 布局引擎、无渲染树。凡「是否被 CSS 隐藏」的结论一律标 `[未验证]`。所有"页面真发请求"的判定基于**脚本执行**而非视觉渲染，这一点对本次核心结论（T3 型假阴性）是充分的，因为死壳的成因是 JS 从未发起请求，而非请求被 CSS 藏起来。

---

## 1. 结论总览

| 页面 | 首屏是否真发 API | 数据真实 vs 假 | 判定 |
|---|---|---|---|
| `dashboard.html` | ✅ **真发 6 个请求**（HTTP 200） | **全真**（与后端响应逐字段一致） | **PASS**（但 body/title 有规格文字泄漏，见 §5） |
| `courses.html` | ❌ 首屏**仅 1 个**旁路请求；列表与 Hero 均**未请求** | ❌ **假**：渲染 15 门硬编码演示课程，Hero 全空 | **FAIL**（见 §3） |
| `community.html` | ✅ 真发 2 个请求 | **全真**（10 帖、6 页、置顶唯一） | **PASS**（但 `<title>` 有规格文字泄漏） |
| `me.html` | ✅ 真发 9 个请求（含 2 组重复） | **全真**（351 分 / Lv.1 · 萌新） | **PASS**（静态骨架有假占位闪现，见 §5.4） |
| `login-register.html` | 未登录前 0 请求（正确）；提交走真实 `/api/auth/login` | — | **PASS**（正文 0 泄漏） |

---

## 2. dashboard 真实加载实证 —— PASS（编排者复验重点）

### 2.1 判定依据：dashboard 是否真的发出 API 请求（6 条）

**A. 排除"陈旧产物"假象** `[实测]`
服务端返回字节与磁盘文件 **md5 完全一致**，5 个页面逐一对齐：

```
srv__dashboard.html      a5a90d1b2c7eba6422f44c220bce9867
public/dashboard.html    a5a90d1b2c7eba6422f44c220bce9867   ← 一致
（courses/community/me/login-register 同样逐字节一致）
```
→ 页面来源可信，后续结论不是 dev server 陈旧产物造成的。

**B. 静态骨架初值全为 `—`，因此真实数字必然来自 API** `[实测]`
`dashboard.html` 各观测点静态初值：`kpi-time`→`—`、`kpi-q`→`—`、`kpi-course`→`—`、`kpi-streak`→`—`、`pointsTotal`→`— 分`、`myrank-big`→`—`、`badgePill`→`…`、`delta1..4`→`—`。
→ **不存在能把真实数字渲染出来的静态路径**，任何真实数字只能来自网络。

**C. 脚本链路完整** `[代码佐证]` + `[实测]`
`dashboard.html` 第 471 行 `<script src="/edu-api.js"></script>`，第 473 行才是数据接线 IIFE；宿主记录执行顺序：
```
scriptOrder = ['src:/edu-api.js OK', 'inline OK', 'inline OK']   ← 顺序正确
```
且 `.venv` 外无关文件 `/edu-api.js` 由 :3000 返回 200（14862 字节）。

**D. 宿主记录到 6 条真实 HTTP 请求，全部 200** `[实测]`
```
GET /api/users/me                                                   -> 200   59ms
GET /api/progress/dashboard?days=14                                 -> 200   82ms
GET /api/users/me/learning-summary                                  -> 200   74ms
GET /api/gamification/me/badges                                     -> 200   94ms
GET /api/gamification/me/points?page=1&page_size=3                   -> 200   87ms
GET /api/gamification/rankings?scope=WEEKLY&dimension=POINTS&top_n=5 -> 200   98ms
```
（另有 1 条由 admin 入口 IIFE 发出的 `/api/users/me`，合计 6 条；代码 `[代码佐证]` 第 660-665 行 `Promise.allSettled([...])` 5 条 + 第 503 行 1 条）

**E. 渲染值 ↔ 后端响应逐字段对齐** `[实测]`（左=页面写入值，右=同 token 直连后端真实响应）

| 页面节点 | 页面渲染值 | 后端字段真值 | 对齐 |
|---|---|---|---|
| `kpi-time` | `111 分钟` | `total_study_seconds=6664` → 111.07 min | ✅ |
| `kpi-q` | `14 道` | `total_questions_attempted=14` | ✅ |
| `delta2` | `正确率 43%` | `overall_correct_rate=0.42857…` | ✅ |
| `kpi-course` | `2 门` | `active_courses_count=2` | ✅ |
| `kpi-streak` | `0 天` | `latest_streak_days=0` | ✅ |
| `delta3` | `在学班次 2 个` | `active_cohorts_count=2` | ✅ |
| `structure-legend` | `📺 视频观看累计 111 分钟` | `total_watched_seconds=6664` | ✅ |
| `pointsTotal` | `351 分` | `total_points=351` | ✅ |
| `pointsTitle` | `💰 积分 · 萌新 Lv.1` | `level_title=萌新`,`level_no=1` | ✅ |
| `pointsLvl` | `距 Lv.2 还需 149 分` | `next_level_min=500`（500−351=149） | ✅ |
| `badgePill` | `3 / 8` | `unlocked_count=3`,`total=8` | ✅ |
| `myrank-big` | `#2` | `my_rank.rank_no=2` | ✅ |
| `myrank-sub` | `我的积分 2 分 · 快照 2026-09-15` | 周榜 `metric_value=2`,`snapshot_date=2026-09-15` | ✅ |
| `ranklist` | 含真实用户名 `Adm02Test` 🥇 | `top[0].user_name` | ✅ |
| `helloName` | `小柚子同学` | `/api/users/me` → `nickname=小柚子同学` | ✅ |

> 注：`helloName=小柚子同学` **不是**静态残留 —— `previous audit` 提到曾硬编码同名昵称，本轮用 `grep` 确认 `dashboard.html` 正文与脚本中**已无该字符串**（仅存于注释/审计日志），且 `/api/users/me` 真实返回该值 `[实测]`。

**F. 非"死壳"判定（四态机真的在切换）** `[实测]`
```
已登录: .v-loading × 3 → hidden=true   （骨架已摘）
        .v-success × 3 → hidden=false  （成功态已亮）
        #trendChart hidden=true, #trendEmpty hidden=false   （近 7 日全 0 → 诚实空态）
        consoleErrors = []  jsErrors = []  （0 报错、0 静默吞异常）
未登录: networkCalls = [] （0 次请求）, #loginGate hidden=false （真实登录引导）
```
静态属性 `[代码佐证]`：`<section id="loginGate" hidden>`、`<section class="v-success" … hidden>`、`<section class="v-loading" data-sec="kpi">`（默认可见）——与运行时切换完全吻合。

### 2.2 dashboard 小节结论
`[实测]` dashboard **不是死壳**：首屏真实发出 6 个 API 请求并渲染出与后端一致的真实数据；加载骨架被正确摘除、成功态被点亮；无任何 console 报错或静默降级。**T3B P0-1 的「果」在 dashboard 上成立。**

### 2.3 遗留（不影响本项判定）
`[实测]` `dashboard.html` **正文**存在 5 处端点/契约字样泄漏（详见 §5.2）；`<title>` 亦泄漏（§5.1）。属"规格文字残留"，与"数据是否活"是两个维度。

---

## 3. courses XP 真实性 —— FAIL

### 3.1 正面结论（原缺陷已修）
- `[实测]` `grep -c "Lv.5\|120 XP\|120XP" courses.html` → **0**：写死的 `Lv.5 / 120 XP` **已不存在**。
- `[实测]` Hero 四要素静态占位全部为破折号：`heroStreak">–`、`heroLevel">–`、`heroXp">– XP`、`heroTotalXp">–`。
- `[实测]` 正文（剥离注释/脚本/样式后 304 字符）对 `task号 / J号 / 契约 / 效果图 / 演示原型 / 端点 / 圈号 / STYLE FROZEN / 验收词` **0 命中**；`<title>` = `课程中心 · EduAgent`（干净）。
  → 任务点名的「效果图 v4 / 契约①」正文残留：**不存在**（相关字样仅出现在 HTML 注释、`<style>` 注释与 JS 注释中，`[实测]` 已逐行确认位置 9/19/195/207/382/443/489/669 行，均非可见正文）。

### 3.2 反面结论（首屏是静默假数据死壳）
`[实测]` 用宿主执行 `courses.html` 自身脚本（**禁用交互模拟**），首屏结果：

```
scriptOrder = ['inline OK', 'inline OK', 'src:/edu-api.js OK', 'inline OK', 'inline OK', 'inline OK']
networkCalls = [ GET /api/users/me -> 200 ]          ← 只有旁路的 admin 入口请求
heroStreak / heroLevel / heroXp / heroTotalXp         ← 从未被写入（保持静态 "–"）
resText = 共 <b>15</b> 门课程
pgInfo  = 共 15 门 · 第 1/1 页
contentArea 渲染 15 张卡片，标题如「通用编程入门班 ×2 / 通用编程项目班 ×2 …」
            链接 course-detail.html?id=1001,1002,1003 …（硬编码 id）
consoleErrors = []   jsErrors = []                    ← 完全静默
```
`[实测]` 同一时刻直连后端真实值：`GET /api/series?page=1&page_size=12` → `total=2628`。
→ **用户首屏看到"共 15 门课程"，真实为 2628 门；Hero 等级/积分/打卡天数三个卡位全部是 `–`。**

### 3.3 根因：`<script src="/edu-api.js">` 位置晚于主脚本的初始化调用
`[代码佐证]`（字节偏移，与宿主执行顺序独立互证）
```
courses.html byte 45320 = refresh();      ← 主脚本末段的初始渲染（第 719 行）
courses.html byte 56504 = loadHero();     ← Hero 真实数据入口（第 741 行）
courses.html byte 57146 = /edu-api.js     ← <script src="/edu-api.js">（第 747 行，全文唯一一处）
=> refresh() 与 loadHero() 均早于 edu-api.js 加载：True
```
主脚本块为第 **454–742** 行一整块，`<script src="/edu-api.js"></script>` 在第 **747** 行 —— 浏览器中普通 `<script src>` 是**阻塞且按文档顺序执行**，因此主脚本运行时 `window.EAPI === undefined`：

- `[代码佐证]` 第 560-566 行：`const hasApi = !!(window.EAPI && EAPI.get); if (!hasApi) { … renderSuccess([...ALL]…) ; return; }` → 走"无 EAPI 时降级演示数据"分支，`ALL` 是第 490 行起的**15 条硬编码课程数组**。
- `[代码佐证]` 第 723 行：`if (!window.EAPI || !EAPI.store || !EAPI.store.getToken()) return;` → Hero 静默返回。

**这是 T3 同型缺陷（静默降级）在 courses 上的复现**：0 报错、0 console 输出、页面看起来"正常"，但展示的是伪造数据。

### 3.4 交互后能自愈（定级依据）
`[实测]` 宿主模拟用户交互（调用页面自身的 `applyState("success")` 与 `loadHero()`，等价于点击任一筛选 chip / 重置按钮）后：
```
新增请求: GET /api/series?page=1&page_size=15 -> 200
         GET /api/gamification/me/points?page=1&page_size=1 -> 200
         GET /api/progress/dashboard?days=14 -> 200
heroStreak = 0     heroLevel = 1     heroXp = 351 XP     heroTotalXp = 351
resText = 共 <b>2628</b> 门课程      pgInfo = 共 2628 门 · 第 1/176 页
```
→ **定级：首屏必现、可自愈、静默**。危害集中在"用户不点任何东西就得到错误信息"（尤其"共 15 门"与真实 2628 差距巨大）。

### 3.5 与「我的」页一致性（任务点）
| 指标 | `courses.html` Hero 首屏 | `courses.html` Hero 交互后 | `me.html` 最终 | 一致？ |
|---|---|---|---|---|
| 等级 | `Lv.–`（空） | `Lv.1` | `Lv.1 · 萌新` | 首屏 ❌ / 交互后 ✅ |
| 积分 | `– XP`（空） | `351 XP` | `351` | 首屏 ❌ / 交互后 ✅ |
| 打卡天数 | `– 天`（空） | `0` | **该页无此字段**（`grep 打卡/签到/天数/连续` = 0 命中） | 无法对照 |

`[实测]` 结论：期望值 `351 分 / Lv.1` 在 courses Hero **首屏未达成**，交互后达成；打卡天数在「我的」页不存在对应字段，无法做一致性对照（`[未验证]`：可能字段在其它页，本轮范围外）。

### 3.6 附带发现：演示数据角标被遮蔽
`[代码佐证]` 第 763-766 行：`(function(){ if(window.EAPI&&window.EAPI.get)return; …显示"演示数据"角标… })()`。
该脚本位于 `edu-api.js`（747）**之后**，此时 `EAPI` 已存在 → **角标恒不显示**；而列表实际已经用了演示数据。即"演示态可见警示"这道兜底被自身时序绕过。

---

## 4. community 置顶帖跨页唯一性（GHOST 下游）—— PASS

### 4.1 API 层全翻页实测 `[实测]`
以页面真实参数 `page_size=10`（`[代码佐证]` 第 488 行 `PAGE_SIZE = 10`）翻完 6 页，另以 `page_size=5` 翻完 12 页交叉验证：
```
page_size=10: page1..6 各 10 条，page7/8 = 0 条；total 恒为 60
              抓取 60 条 → 去重后 60 条 → 跨页重复 post_id：无
              is_pinned=True 的记录：(post_id=1, page=1)   ← 全局仅此一条
page_size=5 : page1..12 共 60 条 → 去重 60 → 跨页重复：无；pinned 同样仅 (1, page=1)
```
→ **同一置顶帖未跨页重复出现，且只在第 1 页出现一次。**

### 4.2 UI 层实测 `[实测]`
宿主执行 `community.html` 自身脚本（无交互）：
```
networkCalls = [ GET /api/users/me 200, GET /api/community/posts?page=1&page_size=10 200 ]
渲染帖子数 = 10
渲染 HTML 中「📌 置顶」出现次数 = 1        ← 恰好一次
post_id 序列 = 1,1,63,63,77,77,73,73,67,67,51,51   （每帖 article 与 like 按钮各带一次 data-post，成对）
分页控件 = 7 个按钮（‹ + 1..6）→ 与 60/10=6 页一致
```
`[代码佐证]` 第 414 行 `var pin = (p.is_pinned || p.pinned) ? '<span class="pin">📌 置顶</span>' : "";`——置顶仅为列表内联徽章，**不存在第二个"置顶区"独立渲染**，故首页也不会有"置顶帖同时出现在置顶区和列表"的重复。
→ **GHOST 修复在 community 上成立（API + UI 双层）。**

---

## 5. 规格文字泄漏扫描（me / login-register 及全域）

### 5.1 `<title>` 泄漏：25 页中 **17 页**中招 `[实测]`
`<title>` 是**浏览器标签页可见文本**，属用户可见面。批量扫描 `public/*.html`：

| 泄漏（17 页） | 例 |
|---|---|
| achievements / admin-course-detail / admin-courses-recycle-proto / admin-courses / admin-dashboard / admin-mcp / admin-questions / admin-rag-upload / chat / community-post / **community** / course-detail / **dashboard** / learning / my-cohorts / practice / refund | `dashboard.html`：`学习仪表盘 · 效果图 v2（task43 /dashboard 契约⑤⑬ candy-playful STYLE FROZEN · 9 大学科水平条形）`；`community.html`：`社区互助 · 效果图 v2（task51 community 列表 · 契约⑬ 壳化 糖果色 candy-playful STYLE FROZEN R2）` |

| 干净（8 页） | admin-question-detail / admin-users-refine-proto / admin-users / coupons / **courses** / favorites / **login-register** / **me** |
|---|---|

→ 任务点名要求"规格文字 0 残留"的三页中，**courses / me / login-register 的 title 均干净**；但 **community 的 title 未干净**，且缺陷是**跨 17 页面**的系统性问题。

### 5.2 `dashboard.html` 正文泄漏 5 处 `[实测]`
剥离注释/脚本/样式后，**正文文本节点**命中：
```
<div class="p-sub">统计每天学习时长，单位分钟；来自 /api/progress/dashboard.recent_days</div>
<div class="p-sub">来自 /api/users/me/learning-summary；分类占比无真实字段，不虚构饼图</div>
<div class="p-sub">来自 /api/gamification/rankings?dimension=POINTS</div>
<div class="p-sub">来自 /api/gamification/me/badges：最近解锁</div>
<div class="p-sub">按学科归并课程完成度（契约缺口：归并端点未冻结，暂无真实数据）</div>
<div class="empty"><p>学科掌握度待按新契约归并后接入，当前暂无数据</p></div>
```
另有 `ZSET 来自 /api/gamification/rankings?...` 含 Redis 实现术语。这些 `.p-sub` 是面板副标题，**始终可见**（非空态/非隐藏态）。

### 5.3 `me.html` / `login-register.html` 正文：**0 命中** `[实测]`
扩展模式（`task\d+ / J\d+ / 契约 / 效果图 / 演示|原型|接线|打靶|兜底 / /api/ / STYLE FROZEN|AUDIT LOG|SUBMITTED / ①-⑮ / 验收|复验|盲测|回归|里程碑`）扫描两页正文：
```
me.html            正文 1031 字符 → 无命中
login-register.html 正文 378 字符 → 无命中
community.html      正文  218 字符 → 无命中
courses.html        正文  304 字符 → 无命中
dashboard.html      正文  726 字符 → {契约×3, /api/×4}   ← 唯一命中的页面
```
`[实测]` `login-register.html` 中 `demo-route` 仅存在于 `<style>` 与 HTML 注释，**不存在** `class="demo-route"` 实体元素；页面无硬编码测试账号（`grep adm02test|Test@123456|user000001|演示账号` 仅命中注释）。
`[代码佐证]` 第 2982 行 `EAPI.post("/api/auth/login", { account: id, password: pwd })` —— 字段名与后端契约一致。

### 5.4 附带发现：`me.html` 静态骨架含假占位，首屏闪现 `[实测]`+`[推演]`
`[实测]` 静态骨架原文：
```
<h1 id="me-name">慕剑知</h1>
<span class="sc-num" id="st-points">1,280</span>  <div class="sc-label">积分</div>
<span class="sc-num" id="st-level">Lv.10</span>   <div class="sc-label">等级 · 学神</div>
⏱️ 68 h 学习时长
```
`[实测]` 接口返回后这些节点被覆盖为真实值：`me-name=小柚子同学`、`st-points=351`、`st-level=Lv.1 · 萌新`、`st-time=2`。接口侧确认 `total_points=351 / level_no=1`。
`[实测]` `me.html` 无 `.v-loading` 类（`visibility.vLoading_hidden = []`）→ **不存在加载骨架遮蔽**。
`[推演]` 因此在接口返回前的窗口期（本机实测单请求 174–356ms），用户会看到 `慕剑知 / 1,280 积分 / Lv.10 等级 · 学神 / 68 h` 的**他人姓名 + 虚高假数据**闪现后被替换。危害为"瞬时假数据 + 陌生人名"，非持续错误。
`[未验证]` 该闪现在真实浏览器中的实际可感知程度（取决于渲染时机），宿主无布局引擎无法测量。

### 5.5 `me.html` 重复请求 `[实测]`
`/api/users/me` 与 `/api/users/me/profile` 各被请求 **2 次**（共 9 条请求，7 条唯一）。功能无影响，属可优化项。

---

## 6. 未验证项与环境限制

1. `[未验证]` **CSS 层面的可见性**：仿真宿主无布局引擎，无法判定某节点是否被 `display:none` / 遮挡 / 折叠隐藏。§5.2 的泄漏判定基于"该 `.p-sub` 无 hidden 属性、无隐藏类"，`[推演]` 应可见。
2. `[未验证]` **真实浏览器执行**：因禁用 Playwright，未做浏览器内验证。但 §3.3 的顺序结论有**字节偏移 + 脚本执行顺序**双重独立互证，`[推演]` 结论稳定（浏览器中 `<script src>` 无 `async/defer` 时按序阻塞执行）。
3. `[未验证]` **community 排序档**：`community.html` 未见明确的 sort 取值来源（`[实测]` `grep data-sort/applySort/setSort` 无命中，仅有 `url += "&sort=" + sort` 传递点）；`sort=hot/latest/like` 未见页面使用，未验证其分页下的置顶唯一性。默认排序（无 sort 参数）已全翻页验证通过。
4. `[未验证]` **根路由 `/` → login-register.html 跳转**：属 Next 路由层，不在仿真宿主能力范围。
5. `[未验证]` 未登录态下 courses/community/me 的降级路径（仅对 dashboard 做了未登录验证）。

---

## 7. 下一位同事最该知道的 3 件事

**① `courses.html` 首屏是"静默假数据死壳"—— 必须把 `<script src="/edu-api.js">` 提到主脚本之前（或把 `renderCats/renderSubs/fbSummary/refresh/loadHero` 的初始化包进 `DOMContentLoaded`）。**
`[代码佐证]` 主脚本 454–742 行内的 `refresh()`（byte 45320，第 719 行）与 `loadHero()`（byte 56504，第 741 行）都早于 `edu-api.js`（byte 57146，第 747 行），导致 `window.EAPI` 未定义 → 第 560-566 行降级分支渲染 15 条硬编码课程、第 723 行静默返回。`[实测]` 首屏 UI 呈现"共 15 门课程"（真实 2628 门）、Hero 三卡全 `–`、**0 报错 0 console**。这不是显示问题，是"用户不交互就拿到错误信息"。顺带：第 763-766 行的"演示数据"角标因同样时序问题**恒不显示**，兜底警示失效。

**② dashboard 已经真的接通了，而且"是否实发请求"有可复跑的判定口径 —— 不要再凭静态代码或 200 状态码下结论。**
`[实测]` dashboard 首屏真实发出 6 个请求（`users/me` + `progress/dashboard` + `learning-summary` + `gamification/me/{badges,points,rankings}`），渲染的每一个数字都能与同 token 直连后端的响应字段对上（351 分 / Lv.1 / 111 分钟 / 14 道 / 43% / 3-of-8 徽章 / 周榜 #2），并且 `.v-loading` 摘除、`.v-success` 点亮、未登录时 0 请求 + 登录引导。**判定死壳的正确姿态是"看脚本有没有发出请求 + 请求的返回值是否真的写进 DOM"，而不是看 HTTP 200。** 复跑方法见附录 A。

**③ "规格文字 0 残留"不成立：`<title>` 在 25 个页面里泄漏了 17 个，dashboard 正文另有 5 处端点/契约字样。**
`[实测]` `courses / me / login-register` 的 title 与正文是干净的（任务点名的三页达标），但 `community` 的 title 带着 `效果图 v2（task51 … 契约⑬ … STYLE FROZEN R2）`，`dashboard` 的 title 与 5 处 `.p-sub`/空态文案带着 `/api/...`、`契约缺口`、`ZSET`。`<title>` 是浏览器标签页文本，属用户可见面。建议按"剥离注释/脚本/样式后的文本节点 + `<title>`"两个口径一起做全站扫描，而不是只盯单页正文。

---

## 附录 A：最小 DOM 仿真宿主源码（可原样复跑）

> 用途：在不使用浏览器/Playwright 的前提下，证明"页面自身是否真的发出 API 请求、请求结果是否真的写进 DOM"。
> 保真点：`<script>` 严格按文档顺序执行（`src` 脚本视作阻塞、按序）；顶层 `function` 声明进入全局（间接 `eval`）；脚本跑完依次派发 `DOMContentLoaded` / `load`；记录全部 `fetch` + `console.error/warn` + 未捕获异常。
> ⚠️ 已知非保真：无 CSS 布局引擎（看不见 `display:none` 之类）；`querySelector` 仅支持简单选择器。

**复跑命令**（Windows / Git Bash）：
```bash
# 0) 拿 token
TOKEN=$(curl -s --noproxy '*' -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"account":"user000001","password":"Test@123456"}' | python -c "import json,sys;print(json.load(sys.stdin)['data']['access_token'])")

# 1) 保存下列源码为 harness2.mjs，然后：
NODE=/c/Users/Administrator/.workbuddy/binaries/node/versions/22.22.2-2/node.exe
NO_INTERACT=1 "$NODE" harness2.mjs /dashboard.html http://127.0.0.1:3000 "$TOKEN"   # 首屏（无交互）
NO_INTERACT=1 "$NODE" harness2.mjs /courses.html   http://127.0.0.1:3000 "$TOKEN"   # 首屏（无交互）
                "$NODE" harness2.mjs /courses.html   http://127.0.0.1:3000 "$TOKEN"   # 含交互模拟
NO_INTERACT=1 "$NODE" harness2.mjs /community.html http://127.0.0.1:3000 "$TOKEN"
NO_INTERACT=1 "$NODE" harness2.mjs /me.html        http://127.0.0.1:3000 "$TOKEN"
```
输出为单行 JSON：`scriptOrder / jsErrors / networkCalls / consoleErrors / globalFns / postInteraction / nodeState / hiddenFlags / visibility`。

```javascript
/* blind-t6 harness v2: 最小 DOM 仿真宿主（不依赖浏览器/Playwright）
 * 用法: node harness2.mjs <pagePath> <refOrigin> [token]
 * 保真要点:
 *  - <script> 严格按文档顺序执行（src 脚本在浏览器中阻塞且按序）
 *  - 顶层 function 声明进入全局（用间接 eval）
 *  - 脚本执行完毕后依次派发 DOMContentLoaded / load
 *  - 记录全部 fetch 调用 + console.error/warn + 未捕获异常(含 stack)
 */
const [page, REF, TOKEN] = process.argv.slice(2);

const calls = [];
const consoleErrors = [];
const jsErrors = [];

function mkEl(id, cls) {
  let _html = null, _text = "";
  const el = {
    id: id || "", tagName: "DIV", hidden: null, _attrs: {}, _cls: new Set(cls || []),
    style: {}, children: [], dataset: {},
    scrollTop: 0, scrollHeight: 1000, clientHeight: 800, offsetWidth: 100, offsetHeight: 40,
    value: "", checked: false, disabled: false, files: [], textAlign: "", title: "", src: "",
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { return c; },
    append(...c) { this.children.push(...c); }, prepend() {},
    insertAdjacentHTML() {}, insertAdjacentElement() { return null; },
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k) ? this._attrs[k] : null; },
    removeAttribute(k) { delete this._attrs[k]; },
    hasAttribute(k) { return Object.prototype.hasOwnProperty.call(this._attrs, k); },
    addEventListener() {}, removeEventListener() {},
    focus() {}, blur() {}, click() {}, scrollIntoView() {}, select() {}, setSelectionRange() {},
    getBoundingClientRect() { return { top: 0, left: 0, right: 100, bottom: 40, width: 100, height: 40, x: 0, y: 0 }; },
    matches() { return false; }, closest() { return null; }, contains() { return false; },
    cloneNode() { return mkEl("", []); },
    getElementsByClassName() { return []; }, getElementsByTagName() { return []; },
    querySelector() { return mkEl("", []); }, querySelectorAll() { return []; },
    getContext() { return { fillRect() {}, clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fill() {}, arc() {}, measureText: () => ({ width: 10 }), fillText() {}, setLineDash() {}, save() {}, restore() {}, translate() {}, scale() {}, closePath() {} }; },
    toDataURL() { return ""; },
    get parentNode() { return null; },
    get firstChild() { return null; }, get lastChild() { return null; },
  };
  el.classList = {
    add: (...c) => c.forEach((x) => el._cls.add(x)),
    remove: (...c) => c.forEach((x) => el._cls.delete(x)),
    contains: (c) => el._cls.has(c),
    toggle: (c, f) => { const on = f === undefined ? !el._cls.has(c) : !!f; on ? el._cls.add(c) : el._cls.delete(c); return on; },
  };
  el.classList.remove = el.classList.remove;
  Object.defineProperty(el, "textContent", {
    get: () => (_text !== "" ? _text : (_html !== null ? _html : "")),
    set: (v) => { _text = v == null ? "" : String(v); _html = null; }, enumerable: true,
  });
  Object.defineProperty(el, "innerHTML", {
    get: () => (_html !== null ? _html : _text),
    set: (v) => { _html = v == null ? "" : String(v); _text = ""; }, enumerable: true,
  });
  Object.defineProperty(el, "innerText", { get: () => el.textContent, set: (v) => { el.textContent = v; }, enumerable: true });
  return el;
}

const realFetch = globalThis.fetch;
const html = await (await realFetch(REF + page)).text();

/* id / class 索引 */
const idMap = new Map();
for (const m of html.matchAll(/\bid="([^"]+)"/g)) if (!idMap.has(m[1])) idMap.set(m[1], mkEl(m[1]));
const classMap = new Map();
for (const m of html.matchAll(/\bclass="([^"]+)"/g))
  for (const c of m[1].split(/\s+/).filter(Boolean)) {
    if (!classMap.has(c)) classMap.set(c, []);
    classMap.get(c).push(mkEl("", [c]));
  }

const domListeners = { DOMContentLoaded: [], load: [], scroll: [], resize: [] };
const def = (k, v) => Object.defineProperty(globalThis, k, { value: v, writable: true, configurable: true, enumerable: true });
def("window", globalThis);

const documentShim = {
  readyState: "loading",
  getElementById: (id) => idMap.get(id) || null,
  createElement: (t) => mkEl("", []),
  createDocumentFragment: () => mkEl("", []),
  createTextNode: (t) => ({ textContent: String(t) }),
  querySelector: (sel) =>
    sel.startsWith("#") ? (idMap.get(sel.slice(1)) || null)
      : sel.startsWith(".") ? ((classMap.get(sel.slice(1)) || [])[0] || null)
      : sel.includes("#") && sel.includes(" ") ? null : null,
  querySelectorAll: (sel) => {
    if (sel.startsWith(".") && !sel.includes(" ")) return classMap.get(sel.slice(1)) || [];
    const out = [];
    for (const m of sel.matchAll(/\.([A-Za-z0-9_-]+)/g)) {
      const a = classMap.get(m[1]); if (a) out.push(...a);
    }
    return out;
  },
  getElementsByClassName: (c) => classMap.get(c) || [],
  getElementsByTagName: () => [],
  addEventListener: (t, fn) => { (domListeners[t] = domListeners[t] || []).push(fn); },
  removeEventListener: () => {},
  body: mkEl("body"), head: mkEl("head"), documentElement: mkEl("html"),
  activeElement: null, cookie: "", title: "",
  execCommand() {}, write() {}, open() {}, close() {},
};
documentShim.body.appendChild = function () {};
def("document", documentShim);

const ls = new Map();
def("localStorage", {
  getItem: (k) => (ls.has(k) ? ls.get(k) : null),
  setItem: (k, v) => ls.set(k, String(v)),
  removeItem: (k) => ls.delete(k),
  clear: () => ls.clear(),
  key: (i) => [...ls.keys()][i],
  get length() { return ls.size; },
});
const ss = new Map();
def("sessionStorage", {
  getItem: (k) => (ss.has(k) ? ss.get(k) : null), setItem: (k, v) => ss.set(k, String(v)),
  removeItem: (k) => ss.delete(k), clear: () => ss.clear(),
});
if (TOKEN) ls.set("edu:auth:token", TOKEN);

const nav = { replaced: [], assigned: [] };
def("location", {
  href: REF + page, origin: REF, pathname: page, search: "", hash: "", protocol: "http:",
  host: REF.replace(/^https?:\/\//, ""), hostname: "127.0.0.1", port: "3000",
  replace(u) { nav.replaced.push(String(u)); }, assign(u) { nav.assigned.push(String(u)); },
  reload() {}, toString() { return REF + page; },
});
def("navigator", { userAgent: "node-harness", language: "zh-CN", languages: ["zh-CN"], onLine: true, clipboard: { writeText: async () => {} } });
def("matchMedia", () => ({ matches: false, media: "", addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
def("requestAnimationFrame", (fn) => setTimeout(() => fn(Date.now()), 0));
def("cancelAnimationFrame", (id) => clearTimeout(id));
def("alert", (m) => calls.push({ synthetic: "alert", msg: String(m) }));
def("confirm", () => true);
def("prompt", () => null);
def("getComputedStyle", () => ({ getPropertyValue: () => "", width: "100px", height: "40px" }));
def("IntersectionObserver", class { observe() {} unobserve() {} disconnect() {} });
def("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
def("MutationObserver", class { observe() {} disconnect() {} takeRecords() { return []; } });
def("URLSearchParams", URLSearchParams);
def("Intl", Intl);
def("chartInstances", []);
def("Chart", class { constructor(c, cfg) { this.config = cfg; globalThis.chartInstances.push(this); } destroy() {} update() {} resize() {} });
def("echarts", { init: () => ({ setOption() {}, resize() {}, dispose() {} }) });
def("hljs", { highlightElement() {}, highlightAll() {} });
def("marked", { parse: (s) => String(s || "") });
def("DOMPurify", { sanitize: (s) => String(s || "") });
def("toast", () => {});
def("showToast", () => {});

globalThis.fetch = async (url, opts = {}) => {
  const rec = { url: String(url), method: (opts.method || "GET").toUpperCase(), status: null, ms: null };
  calls.push(rec);
  const t0 = Date.now();
  try { const r = await realFetch(url, opts); rec.status = r.status; rec.ms = Date.now() - t0; return r; }
  catch (e) { rec.status = "ERR"; rec.ms = Date.now() - t0; rec.err = String(e && e.message); throw e; }
};

const realLog = console.log;
console.error = (...a) => consoleErrors.push(a.map(String).join(" "));
console.warn = (...a) => consoleErrors.push("[warn] " + a.map(String).join(" "));

/* ---- 按文档顺序执行 ---- */
const order = [];
for (const m of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)) {
  const attrs = m[1] || "", body = m[2] || "";
  const srcM = /\bsrc="([^"]+)"/.exec(attrs);
  if (/type="module"/.test(attrs)) { order.push("skip-module"); continue; }
  if (/type="(?!text\/javascript|application\/javascript)/.test(attrs) && /type="/.test(attrs)) { order.push("skip-nonjs"); continue; }
  const code = srcM ? await (await realFetch(REF + srcM[1])).text() : body;
  if (!code.trim()) { order.push("empty"); continue; }
  try { (0, eval)(code + "\n//# sourceURL=" + (srcM ? srcM[1] : "inline")); order.push((srcM ? "src:" + srcM[1] : "inline") + " OK"); }
  catch (e) { order.push((srcM ? "src:" + srcM[1] : "inline") + " THROW " + e.message); jsErrors.push({ which: srcM ? srcM[1] : "inline", msg: String(e && e.message), stack: String(e && e.stack || "").split("\n").slice(0, 4).join(" | ") }); }
}

documentShim.readyState = "interactive";
for (const fn of domListeners.DOMContentLoaded) { try { fn(); } catch (e) { jsErrors.push({ which: "DOMContentLoaded", msg: String(e && e.message), stack: String(e && e.stack || "").split("\n").slice(0, 4).join(" | ") }); } }
documentShim.readyState = "complete";
for (const fn of domListeners.load) { try { fn(); } catch (e) { jsErrors.push({ which: "load", msg: String(e && e.message), stack: String(e && e.stack || "").split("\n").slice(0, 4).join(" | ") }); } }
await new Promise((r) => setTimeout(r, 9000));

/* ---- 模拟用户交互（若页面暴露入口）---- */
const beforeN = calls.length;
const NO_INTERACT = !!process.env.NO_INTERACT;
const globalFns = NO_INTERACT ? [] : ["applyState", "fetchPage", "refresh", "loadHero", "bootAdmin", "loadPosts", "loadList", "init"].filter((f) => typeof globalThis[f] === "function");
const clicked = [];
if (!NO_INTERACT && typeof globalThis.applyState === "function") { try { globalThis.applyState("success"); clicked.push("applyState"); } catch (e) {} }
if (!NO_INTERACT && typeof globalThis.loadPosts === "function") { try { globalThis.loadPosts(1); clicked.push("loadPosts"); } catch (e) {} }
if (!NO_INTERACT && typeof globalThis.loadHero === "function") { try { globalThis.loadHero(); clicked.push("loadHero"); } catch (e) {} }
await new Promise((r) => setTimeout(r, 4000));
const postCalls = calls.slice(beforeN);

/* ---- 快照 ---- */
const snap = {};
for (const [id, el] of idMap) {
  const v = (el.innerHTML || el.textContent || "").replace(/\s+/g, " ").trim();
  if (!v) continue;
  snap[id] = (el.hidden === true ? "[hidden] " : "") + v.slice(0, 20000);
}
const hiddenFlags = {};
for (const id of ["loginGate","loginGateBtn","trendEmpty","structureEmpty","rankEmpty","badgesEmpty","trendChart","ranklist","badgesStrip","adminEntry"]) {
  const el = idMap.get(id);
  hiddenFlags[id] = el ? el.hidden : "<MISSING>";
}
const allPins = (() => {
  const el = idMap.get("postsArea") || idMap.get("listArea") || idMap.get("postList");
  return el ? (el.innerHTML.match(/📌 置顶/g) || []).length : -1;
})();

console.log = realLog;
realLog(JSON.stringify({
  page, refUrl: REF + page, scriptOrder: order, jsErrors,
  networkCalls: calls, consoleErrors,
  globalFns, postInteraction: { clicked, calls: postCalls },
  nodeState: snap, hiddenFlags, pinnedBadgeCountInList: allPins,
  visibility: {
    vLoading_hidden: (classMap.get("v-loading") || []).map((e) => e.hidden),
    vSuccess_hidden: (classMap.get("v-success") || []).map((e) => e.hidden),
    vError_hidden: (classMap.get("v-error") || []).map((e) => e.hidden),
  },
}, null, 1));

```

---

## 附录 B：关键原始输出（宿主 JSON 裁剪）

### B1 `courses.html` 首屏（NO_INTERACT=1）—— 死壳的直接证据
```json
{
 "scriptOrder": [
  "inline OK",
  "inline OK",
  "src:/edu-api.js OK",
  "inline OK",
  "inline OK",
  "inline OK"
 ],
 "jsErrors": [],
 "networkCalls": [
  {
   "url": "http://127.0.0.1:8000/api/users/me",
   "status": 200
  }
 ],
 "consoleErrors": [],
 "resText": "共 <b>15</b> 门课程",
 "pgInfo": "共 15 门 · 第 1/1 页",
 "heroNodesWritten": {
  "heroStreak": "<从未写入>",
  "heroLevel": "<从未写入>",
  "heroXp": "<从未写入>",
  "heroTotalXp": "<从未写入>"
 },
 "courseCardCount": 15,
 "cardTitles": [
  "通用编程入门班",
  "通用编程入门班",
  "通用编程项目班",
  "通用编程项目班",
  "通用编程就业强化班",
  "通用编程就业强化班",
  "系统级编程基础班",
  "系统级编程基础班",
  "系统编程实战班",
  "系统编程实战班",
  "Linux系统开发进阶班",
  "Linux系统开发进阶班",
  "脚本自动化入门班",
  "脚本自动化入门班",
  "办公与运维自动化班"
 ]
}
```

### B2 `courses.html` 交互后自愈
```json
{
 "globalFns": null,
 "postInteraction": null,
 "heroStreak": "0",
 "heroLevel": "1",
 "heroXp": "351 XP",
 "heroTotalXp": "351",
 "resText": "共 <b>2628</b> 门课程",
 "pgInfo": "共 2628 门 · 第 1/176 页"
}
```

### B3 `dashboard.html` 已登录 / 未登录
```json
{
 "authed": {
  "networkCalls": [
   {
    "url": "http://127.0.0.1:8000/api/users/me",
    "status": 200,
    "ms": 76
   },
   {
    "url": "http://127.0.0.1:8000/api/progress/dashboard?days=14",
    "status": 200,
    "ms": 94
   },
   {
    "url": "http://127.0.0.1:8000/api/users/me/learning-summary",
    "status": 200,
    "ms": 85
   },
   {
    "url": "http://127.0.0.1:8000/api/gamification/me/badges",
    "status": 200,
    "ms": 96
   },
   {
    "url": "http://127.0.0.1:8000/api/gamification/me/points?page=1&page_size=3",
    "status": 200,
    "ms": 74
   },
   {
    "url": "http://127.0.0.1:8000/api/gamification/rankings?scope=WEEKLY&dimension=POINTS&top_n=5",
    "status": 200,
    "ms": 84
   }
  ],
  "consoleErrors": [],
  "jsErrors": [],
  "hiddenFlags": {
   "loginGate": null,
   "loginGateBtn": null,
   "trendEmpty": false,
   "structureEmpty": null,
   "rankEmpty": null,
   "badgesEmpty": null,
   "trendChart": true,
   "ranklist": null,
   "badgesStrip": null,
   "adminEntry": null
  },
  "rendered": {
   "kpi-time": "111<small> 分钟</small>",
   "kpi-q": "14<small> 道</small>",
   "kpi-course": "2<small> 门</small>",
   "kpi-streak": "0<small> 天</small>",
   "delta2": "正确率 43%",
   "pointsTotal": "351 分",
   "pointsTitle": "💰 积分 · 萌新 Lv.1",
   "pointsLvl": "距 Lv.2 还需 149 分",
   "badgePill": "3 / 8",
   "myrank-big": "#2",
   "myrank-sub": "我的积分 2 分 · 快照 2026-09-15",
   "helloName": "小柚子同学"
  }
 },
 "anonymous": {
  "networkCalls": [],
  "jsErrors": [],
  "hiddenFlags": {
   "loginGate": false,
   "loginGateBtn": null,
   "trendEmpty": null,
   "structureEmpty": null,
   "rankEmpty": null,
   "badgesEmpty": null,
   "trendChart": null,
   "ranklist": null,
   "badgesStrip": null,
   "adminEntry": null
  }
 }
}
```

### B4 `community.html` 首屏（含置顶计数）
```json
{
 "networkCalls": [
  {
   "url": "http://127.0.0.1:8000/api/users/me",
   "status": 200
  },
  {
   "url": "http://127.0.0.1:8000/api/community/posts?page=1&page_size=10",
   "status": 200
  }
 ],
 "jsErrors": [],
 "renderedPosts": 10,
 "pinnedBadgeCount": 1,
 "postIdSequence": [
  "1",
  "1",
  "63",
  "63",
  "77",
  "77",
  "73",
  "73",
  "67",
  "67",
  "51",
  "51",
  "47",
  "47",
  "43",
  "43",
  "39",
  "39",
  "35",
  "35"
 ],
 "pagerButtons": 7
}
```

### B5 `me.html` / `login-register.html`
```json
{
 "me": {
  "networkCalls": [
   {
    "url": "http://127.0.0.1:8000/api/users/me",
    "status": 200
   },
   {
    "url": "http://127.0.0.1:8000/api/users/me",
    "status": 200
   },
   {
    "url": "http://127.0.0.1:8000/api/users/me/learning-summary",
    "status": 200
   },
   {
    "url": "http://127.0.0.1:8000/api/gamification/me/points",
    "status": 200
   },
   {
    "url": "http://127.0.0.1:8000/api/users/me/profile",
    "status": 200
   },
   {
    "url": "http://127.0.0.1:8000/api/trade/orders?page=1&page_size=5",
    "status": 200
   },
   {
    "url": "http://127.0.0.1:8000/api/coupons?status=unused&page=1&page_size=4",
    "status": 200
   },
   {
    "url": "http://127.0.0.1:8000/api/favorites?page=1&page_size=4",
    "status": 200
   },
   {
    "url": "http://127.0.0.1:8000/api/users/me/profile",
    "status": 200
   }
  ],
  "rendered": {
   "me-name": "小柚子同学",
   "st-points": "351",
   "st-level": "Lv.1 · 萌新",
   "st-time": "2",
   "me-goal": "编程入门,升学备考",
   "odMeta": "共 33 笔订单 · 第 1 / 7 页",
   "cpMeta": "共 96 张未使用 · 第 1 / 24 页",
   "fvMeta": "共 5 个收藏 · 展示最近 4 个"
  },
  "jsErrors": []
 },
 "loginRegister": {
  "networkCalls": [],
  "jsErrors": [],
  "renderedNodes": 0
 }
}
```

### B6 置顶跨页唯一性（API 全翻页）
```
page_size=10:  page1..6 各 10 条, page7/8 = 0 条, total 恒为 60
                抓取 60 → 去重 60 → 跨页重复 post_id = 无
                is_pinned=True 记录 = [(post_id=1, page=1)]   ← 全局唯一
page_size=5 :  page1..12 共 60 → 去重 60 → 跨页重复 = 无 ; pinned 同样仅 (1, page=1)
```

