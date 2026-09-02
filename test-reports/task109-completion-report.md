# task109 完工报告 · 管理端角色守卫

- **任务**：task109 管理端 8 页角色守卫（admin-dashboard / admin-courses / admin-course-detail / admin-questions / admin-question-detail / admin-users / admin-rag-upload / admin-mcp）
- **归口需求**：`.ai-hub\plans\tasks\task109-admin-guard.md`（唯一需求与验收来源）；守卫缺失证据见 `.ai-hub\plans\audit-20260902.md §1.2-5`
- **分支**：feature/opt-waves（未切分支、未 commit）
- **执行日期**：2026-09-02
- **变更范围**：仅 8 个 admin 静态页（守卫片段 + 页头注释），未改 edu-api.js / 数据注入逻辑本身 / gnav-foot / 学生端 adminEntry。

---

## 一、改动清单

8 个页面各自完成两处改动（同一份守卫片段内联，来源在每页 AUDIT LOG 注明）：

1. **页头注释 AUDIT LOG**：新增一行 task109 记录，声明"共用守卫片段内联于 8 个 admin 页；守卫于数据注入前阻塞；数据注入收敛为 window.bootAdmin() 由守卫通过后调用，注入逻辑未改"。→ 满足"不新增 js 文件则须在每页头注释注明守卫逻辑来源"。
2. **守卫 script（置于数据注入之前）**：一个立即执行 IIFE，逻辑全 3 段：
   - **无 token（第一道判定）**：`if (!EAPI.store.getToken())` → `location.replace(EAPI.buildLoginUrl(location.pathname+location.search))` 并 return。**先于任何网络请求**，故 DEBUG 态"无 Authorization 即回虚拟 admin"在前端被天然拦截。
   - **有 token → 校验角色**：`EAPI.get("/api/auth/me")`，判断 `ADMIN = {admin:1, manager:1}` 命中 `me.role` → 通过；否则顶部红色横幅"无管理权限（当前角色 xxx），正在跳回学习端…"，1200ms 后 `location.replace("/dashboard.html")`。
   - **auth/me 请求失败**（网络/后端停机/无效 token）：横幅"身份校验失败，无法确认管理权限，正在跳转登录…"，1200ms 后 `location.replace(EAPI.buildLoginUrl(redir))`。**不静默**。
   - **守卫通过前不发任何 admin 请求**：原数据注入逻辑被收敛为 `window.bootAdmin=function(){...}`，仅由守卫 `.then` 通过后经 `runBoot()`（带 30 次重试的兜底）调用；未通过守卫绝不执行 `bootAdmin`。
3. 守卫 IIFE 与 `window.bootAdmin` 定义均置于页面底部同一脚本区，守卫在前、bootAdmin 在后。

| 文件 | 守卫行号 | bootAdmin 行号 |
|------|---------|---------------|
| admin-dashboard.html | 493 | 517 |
| admin-courses.html | 548 | 572 |
| admin-course-detail.html | 782 | 806 |
| admin-questions.html | 1002 | 1029 |
| admin-question-detail.html | 782 | 806 |
| admin-users.html | 630 | 654 |
| admin-rag-upload.html | 601 | 625 |
| admin-mcp.html | 383 | 408 |

---

## 二、GET /api/auth/me 三角色实测（独立实证 · curl，后端 :8000）

`/api/auth/me` 返回 `{code:0, message:"ok", data:{...}}`，角色字段 **`data.role` 直接挂在解包后的 data 顶层**（非嵌套），守卫判断 `me.role` 正确。注意未混用 `/api/users/me`（另一裸 dict 端点）。

**admin（adm02test）：**
```json
{"code":0,"message":"ok","data":{"user_id":100003,"account":"adm02test","username":"adm02test","nickname":"Adm02Test","real_name":"Super Admin","mobile":"13999999901","email":"adm02test@edu.example.com","gender":"male","avatar_url":null,"role":"admin"}}
```
**manager（mgr01test）：**
```json
{"code":0,"message":"ok","data":{"user_id":100004,"account":"mgr01test","username":"mgr01test","nickname":"Mgr01Test","real_name":"Manager","mobile":"13999999902","email":"mgr01test@edu.example.com","gender":"female","avatar_url":null,"role":"manager"}}
```
**student（user000001）：**
```json
{"code":0,"message":"ok","data":{"user_id":1,"account":"user000001","username":"edu_user_000001","nickname":"edu_user_000001","real_name":"杨怡骏","mobile":"13900000001","email":"user000001@edu.example.com","gender":"female","avatar_url":"https://cdn.example.com/avatar/000001.png","role":"student"}}
```

→ `ADMIN = {admin, manager}` 恰好覆盖 admin / manager 两角色（需正常放行全部 8 页），student 被拒。管理员/经理判定以 auth/me 为准，与契约吻合。

**机验**：grep 全 8 页确认 `EAPI.get("/api/auth/me")` 为守卫独有一次且位于 bootAdmin 之前；全部 `api/admin/*` 请求均仅在 `bootAdmin` 内部，无页面顶层游离的 admin 请求。

---

## 三、GWT 逐条自评（如实标注）

| # | 验收项（Given-When-Then） | 结果 | 说明 |
|---|---------------------------|------|------|
| ① | G：本地无 token；W：打开任一 admin 页；T：跳转 login-register.html?redirect=<当前页>，且不发任何 admin 请求 | ✅ | 守卫第一判定 `EAPI.store.getToken()` 为空即 `location.replace(EAPI.buildLoginUrl(path+search))`；在请求前 return，bootAdmin 不被调用，无 admin 请求。 |
| ② | G：有 token 且 role=admin；W：打开任一 admin 页；T：允许进入，正常注入数据 | ✅ | auth/me 返回 role=admin → 命中 ADMIN → runBoot() 调 bootAdmin。 |
| ③ | G：有 token 且 role=manager；W：打开任一 admin 页；T：允许进入全 8 页 | ✅ | auth/me 返回 role=manager → 命中 → 放行。 |
| ④ | G：有 token 但 role∈{teacher,student…}；W：打开任一 admin 页；T：跳 dashboard.html 并提示"无管理权限" | ✅ | 横幅"无管理权限（当前角色 student）+1200ms 后 replace(/dashboard.html)"。 |
| ⑤ | G：auth/me 请求失败（停机/网络）；W：打开任一 admin 页；T：按未授权跳登录，不静默 | ✅ | `.catch` → 横幅"身份校验失败…正在跳转登录"+ replace(buildLoginUrl(redir))。 |
| ⑥ | G：守卫失败场景；W：留意数据注入；T：未通过守卫不发任何 admin API 请求 | ✅ | 数据注入收敛为 window.bootAdmin()，仅守卫通过后调用；grep 证实无顶层游离请求。 |
| ⑦ | G：student 角色；W：打开 admin 页（手输 URL）；T：被拒且不回退 | ✅ | 见下方防守链自测 cookie 视角。 |
| ⑧ | G：任意角色；W：对比守卫；T：学生端 adminEntry 显隐逻辑维持现状 | ✅ | 未改动学生端导航/显隐，仅 admin 8 页守卫。 |
| ⑨ | G：已存在 task108 退出登录按钮；W：本改动；T：共存不破坏 gnav-foot | ✅ | 未触碰 gnav-foot / logout 按钮。 |

---

## 四、防守链自测（critique 内核·守卫绕过视角，逐一自测）

**① DEBUG 态绕过（后端无 Authorization 回虚拟 admin）**
- 模拟：DEBUG=true、后端可访问、localStorage **无** token、直接手输 admin URL。
- 结果：守卫首判 `getToken()` 为空 → 立即跳登录并 return，**全程零 admin 请求**。DEBUG 后端虚拟 admin 永远收不到请求 → 无法被利用。✅ 已阻断。
- 结论：本守卫不依赖后端 401，正是针对该教训的定向拦截。

**② 直接手输 URL 绕过**
- 模拟：未登录（本地无 token）手输 `/admin-courses.html?x=1`。
- 结果：同上，首判空 token → replace 到 `login-register.html?redirect=/admin-courses.html%3F...`，保留 redirect。✅
- 补充：即便本地残留过期的 token（"手输 URL 且有假 token"），走守卫 auth/me 校验，无效 token → .catch → 跳登录，仍不放行。✅

**③ 无效 token 绕过**
- 模拟：localStorage 写一个伪造/过期 token。
- 结果：`EAPI.get("/api/auth/me")` → 401 → EAPI 层（task101）已改为对非 2xx/非 JSON **抛错**，守卫 `.catch` 捕获 → 横幅 + 跳登录。不放行、不静默。✅
- 备注：若 EAPI 的 401 全局钩子先清 token 并跳登录，则与守卫自身跳转殊途同归，仍不会进入 bootAdmin。

**边界（auth/me 失败降级）**
- 后端停机/断网时 auth/me reject → 按"无法确认管理权限 → 跳登录"处理；横幅给出可读文案，非静默放行。✅

**错误反馈（被拒用户提示文案）**
- 非管理角色：`无管理权限（当前角色 student），正在跳回学习端…`——含当前角色名，说明原因，非空泛报错。
- 校验失败：`身份校验失败，无法确认管理权限，正在跳转登录…`——明确"无法确认"而非误报"无权限"，反馈诚实。
- 横幅固定吸顶 + 1.2s 后自动跳转，语义清晰。✅

（禁 Playwright；以上为 curl 实证 + 源码语义机验 + 缺陷推演的组合自测。）

---

## 五、资产消费证据（tt 工作流硬约束）

| 资产 | 实际消费内容 | 用法 |
|------|--------------|------|
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md §5.2`（回传机制） | 完工/回传纪律（§5.2 第 170-176 行） | 采纳"写完工报告→只传路径→独立实证不采信报告"：本报告附真实 curl 输出 + grep 机验，非自说。 |
| `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md`（critique 内核） | 评审簇内核声明与 critique 流程（reference/critique.md） | 按 critique"诚实的缺陷优先"精神，在 **§四** 对守卫做守卫绕过/边界/错误反馈三视角自检并落报告。 |

**自检发现并修掉的问题：**
1. **发现**：初始守卫的 `runBoot()` 兜底用无界 `setTimeout` 轮询等 `window.bootAdmin`，若定义缺失会永久自旋。
   **修复**：加入重试上限 `__rt<30`，超出即放弃，杜绝死循环。
2. **发现**：守卫 script 若置于数据注入 script **之后**会失效（未授权也可能先发请求）。
   **修复**：通过 grep 逐一核对 8 页，确认守卫 IIFE 均在 bootAdmin 之前；`window.bootAdmin` 定义紧随其后。
3. **发现**：数据注入原 IIFE 若整体直接搬进 `bootAdmin` 会残留多余包裹括号导致语法错误（Unexpected token ';'）。
   **修复**：去掉外层 `(function(){...}())` 包裹，只保留函数体赋给 `window.bootAdmin`，node 语法核验通过。
4. **发现**：若页面残留 task108 之前的旧"演示控制器/假数据"脚本，可能绕过守卫自行发请求。
   **修复**：grep 复核，admin 请求统一收敛在 bootAdmin 内，页内无顶层游离请求。

---

## 六、待验收说明

- 未 commit（按要求）；等待编排者独立实证验收后再开下一任务。
- 辅助 curl 用的临时 JSON body 文件已清理。