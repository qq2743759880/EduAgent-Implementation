# W1 批判 C1+C2 完工报告（agent×skill×workflow）

> 执行 agent：EduAgent W1 批判 C1+C2 子 agent（tt 工作流）
> 承接：C1=edu-api.js 单飞 refresh+重放；C2=管理端守卫 8 页内联 → edu-guard.js 单点化
> 日期：2026-09-04 ｜ 纪律：最小 diff、只改授权文件、不 commit

## 1. 资产消费证据段

| 资产 | 消费方式 | 方法论落点 |
|------|----------|-----------|
| `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md` | Read 全文 | ① 自责梯 rung2「Already in this codebase? reuse it」：C1 复用已有 `apiError`/`gotoLogin`/`onLoginPage`/`buildLoginUrl`，C2 复刻原 `runBoot` 轮询语义，不新建抽象；②「Bug fix = root cause, not symptom」：C2 在共享函数 `edu-guard.js` 单点加守卫（少 diff），而非每页各补；③「Lazy code without its check」：留 `test-reports/selfcheck-singleflight-refresh.mjs`（非框架 assert 自检）；④ 「ponytail:」注释——单飞 refresh 用模块级全局锁，注明升级路径 |
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md` | Read §5.2 §5.4 | ① §5.4「可验证边界」：所有判定给可机验边界——grep 计数（内联=0/引用=8）、单飞自检 `refreshCalls===1`、curl 实测 refresh 返回 `code:0`；② §5.2「资产锚点+方法论内核词」：本报告含「资产消费证据」段；③ §5.3「验收必须独立实证」：refresh 用真实 HTTP curl 独立实证，不采信注释 |
| `C:\Users\Administrator\.agents\skills\harden\SKILL.md` | Read 全文 | ①「Concurrent operations」「race conditions」→ C1 单飞 refresh 防多标签并发 401 重复刷新/重复跳转（模块级 Promise 复用）；②「Error scenarios: 4101」分级：401 先 refresh→重放→仍败才清 token 跳登录（不静默、不误跳）；③「Handle timeout」refresh 独立 AbortController 超时；④「Handle each status code」refresh 非 200 一律降级登录 |

**自检发现并修掉**：写单飞自检时遇到「shim 的 Response 缺 `.ok` 属性」导致 `parseResponse` 误抛「HTTP 200」——修 fetch stub 补 `ok`（这是自检脚本 bug，非产品代码）；另定位出 C2 用 `window.bootAdmin` 定位守卫块会命中守卫内部引用、用 `task109` 正则锚定会命中页头 AUDIT LOG 注释（首条 task109 在 line 517）——改为 `})();\n</script>` 锚定守卫块收尾才精确替换。

## 2. agent × skill × workflow 矩阵

| 层 | 实际取值 | 落点 |
|----|----------|------|
| agent | W1 批判 C1+C2 执行 agent（单 agent，tt 退化模式 §5.0） | 本报告 + edu-api.js/edu-guard.js/8 admin 页 |
| skill | ponytail（最简实现纪律）+ harden（401 重放/并发防护边界）+ tt（完工验收纪律 §5.2/5.4） | C1 主用 harden+ponytail；C2 主用 ponytail；tt 约束报告结构与实证 |
| workflow | W1 批判承接（回传机制 §5.2：具名资产+消费证据+实证边界） | 本报告 |

## 3. W1-C1：edu-api.js 单飞 refresh + 重放

### 3.1 需求对应
1. 401 先单飞 refresh（模块级 `refreshPromise`，多并发复用同一请求）→ 更新 access → **重放原请求一次**
2. 仍失败（无 token / refresh 401 / 重放仍 401）→ 走清 token 跳登录带 redirect
3. store 含 refresh_token；缺失直接跳过 refresh 降级登录跳转
4. 签名向后兼容：`EAPI.get/post/put/patch/del`、`EAPI.store.{getToken,setToken,clear}` 不变

### 3.2 diff 关键片段
```js
// 单飞 promise（request 401 分支进入）
let refreshPromise = null;
function scheduleRefresh() {
  if (!refreshPromise) {
    refreshPromise = new Promise((resolve) => doRefresh(resolve)).then((ok) => {
      refreshPromise = null;           // 完成后复位，供下一轮 401 再进入
      return ok;
    });
  }
  return refreshPromise;
}
// request() 401 路由（替换原「无条件清 token 跳登录」分支）
if (resp.status === 401) {
  if (_replayed) return handleUnauthorized(401, "重新登录后凭证仍无效");
  if (!store.getRefreshToken()) return handleUnauthorized(401);      // 无 refresh_token → 降级登录
  return scheduleRefresh().then((ok) => {
    if (!ok) return handleUnauthorized(401, "登录已过期，请重新登录");
    return request(method, path, body, true); // 用新 access 重放原请求一次
  });
}
```
- `doRefresh` 用 body 携带 refresh_token（不带过期 access，避免 401 死锁），独立 AbortController 超时；成功解析 `{code:0,data:{access_token,refresh_token,...}}` → 更新 store 并滑动续期 refresh。
- `handleUnauthorized` = 原 401 分支逻辑收敛（`store.clear()` + `gotoLogin(currentPathWithQuery())` + 抛 `apiError(401,...)`，复用已有 apiError/buildLoginUrl）。
- store 新增 `getRefreshToken/setRefreshToken`，`clear()` 同时清 access+refresh。
- 配套：`login-register.html` 登录成功后持久化 `data.refresh_token`（否则 C1 永远「无 refresh_token→跳过 refresh」，refresh 为死代码）。
- `// ponytail:` 模块级全局锁，升级路径 = 若需按 tab 隔离可改 per-tab 锁，当前多标签本来就是目标场景所以全局锁正确。

### 3.3 单飞 Promise 复用自检（真实 edu-api.js + node shim）
`test-reports/selfcheck-singleflight-refresh.mjs`（独立脚本，已留存）。加载真实 edu-api.js，用 fetch 门计数真实 `/api/auth/refresh` 网络调用。
```
并发 5 请求全部成功（refresh 后各重放一次拿到 200）: PASS
实际 /api/auth/refresh 调用次数 = 1 (期望 1)          ← 并发 N=5 只发 1 次 refresh
重放后存储 access = NEW_AT (期望 NEW_AT)             ← 滑动续期生效
重放后存储 refresh = NEW_RT (期望 NEW_RT)
无 refresh_token 场景：跳过 refresh(次数不变)、触发跳登录 — PASS
ALL PASS: 单飞 refresh 仅触发 1 次，重放一次并滑动续期，缺 refresh_token 降级跳登录   (exit 0)
```
→ 实证：**N 并发 401 单飞 refresh 仅触发 1 次**。

### 3.4 refresh 端点真实 curl 实测（后端 8000 在线）
- 登录：`POST /api/auth/login {account:adm02test,password:Test@123456}` → `code:0`，data 含 `access_token`+`refresh_token`（7d 滑动）。
- 刷新：`POST /api/auth/refresh {"refresh_token": <rt>}` → `{"code":0,"message":"ok","data":{access_token,refresh_token,...}}`（**换新双 token，滑动续期生效**）。
- 边界：`refresh_token=garbage.invalid.token` → `HTTP=401 {"code":"40101","message":"登录凭证无效"}`（匹配前端 `resp.status!==200 → 降级登录` 分支）。
→ 前端单飞 refresh 依赖的契约冻结成立。

## 4. W1-C2：管理端守卫 8 页内联 → edu-guard.js 单点化

### 4.1 新建 `edu-frontend/public/edu-guard.js`
```js
(function (global) {
  var ADMIN = { admin: 1, manager: 1 };
  function banner(txt) { /* 与 task109 原 banner 一致 */ }
  var __rt = 0;
  function runBoot() {   // 缺省回调：轮询 window.bootAdmin 最多 30 次(3s)兜底竞态
    var fn = global.bootAdmin;
    if (typeof fn === "function") { try { fn(); } catch (e) {} }
    else if (__rt++ < 30) setTimeout(runBoot, 10);
  }
  function requireAdmin(onPass) {
    if (!global.EAPI) return;
    var redir = ...;
    if (!EAPI.store.getToken()) { /* 三段① 跳登录带 redirect */ return; }
    EAPI.get("/api/auth/me").then(function (me) {
      if (me && ADMIN[me.role]) { if (typeof onPass==="function") onPass(); else runBoot(); } // 三段② 通过→boot
      else { /* 无管理权限横幅 + 跳 /dashboard.html */ }
    }).catch(function () { /* 三段③ 校验失败→横幅 + 跳登录 */ });
  }
  global.eduGuard = { requireAdmin: requireAdmin };
})(window);
```
三守卫段（无 token / auth/me role 校验 / 失败降级）在单点收敛，`onPass` 缺省走 `runBoot`（向后兼容原「守卫通过后调 window.bootAdmin()」语义）。

### 4.2 8 页替换清单（页尾 IIFE → 一行引入 + 一行调用）
每页将 task109 内联守卫 `<script> /* ═ task109 …})(); </script>` 替换为：
```html
<script src="/edu-guard.js"></script>
<script>eduGuard.requireAdmin();</script>
```
已替换 8 页：admin-courses / admin-course-detail / admin-mcp / admin-dashboard / admin-questions / admin-question-detail / admin-users / admin-rag-upload。
引入顺序满足静态页注入模式：`edu-api.js`（先，供 EAPI）→ `edu-guard.js`（后）→ `eduGuard.requireAdmin()`（调用）→ 各页原 `window.bootAdmin` 定义脚本（保留不动），避免重定义全局 `$` 覆盖原脚本；`requireAdmin` 缺省轮询 `window.bootAdmin` 兜底 bootAdmin 定义滞后的加载顺序竞态。

### 4.3 grep 证据
```
edu-guard.js include          = 8   （8 个 admin 页 <script src="/edu-guard.js">）
eduGuard.requireAdmin() 调用   = 8
内联守卫 IIFE (var ADMIN )     = 0   （8 页均已移除，仅在 edu-guard.js 出现一次）
EAPI.get("/api/auth/me") 运行时代码 = 0（8 页内除 admin-courses:572 的 getAdminId() 数据缓存助手——非守卫生效，保留）
bootAdmin 定义               = 每页 1（原定义脚本全部保留）
```
> 注：页头 AUDIT LOG 注释里的「管理端角色守卫（内联于 8 个 admin 页）」为历史 changelog 文本，非代码，保留不动。

### 4.4 三角色行为回归说明（登录态下守卫行为与 task109 原语义一致）
1. **student（role=student）**：`/api/auth/me` 返回 role=student ∉{admin,manager} → 横幅「无管理权限…正在跳回学习端」+ 1.2s 后跳 `/dashboard.html`（不进入 bootAdmin）。
2. **admin / manager**：`/api/auth/me` 通过 → `runBoot`（轮询就绪后）调 `window.bootAdmin()` 触发数据注入，与 task109 行为逐字一致。
3. **无 token / 校验失败 / 网络停机**：三段①③ 跳 `login-register.html?redirect=<当前路径>`，不静默降级（兜住 lesson10 防 DEBUG 态虚拟 admin 绕过）。
- 守卫通过前不发任何 admin API 请求：`bootAdmin` 仅由守卫通过后调用，原「数据注入收敛」未破坏。

## 5. 完工自检 / 未做项（ponytail 明示）
- **已做**：edu-api.js 单飞 refresh+重放、store refresh_token 支持、login 持久化 refresh；edu-guard.js 单点守卫 + 8 页替换；自检脚本 curl 实测留存（`test-reports/selfcheck-singleflight-refresh.mjs`）。
- **未做 / 明确跳过**：
  - 未引任何测试框架，自检用 assert + fetch 门（ponytail 自检要求，够用）。
  - 未改后端契约、未改非授权文件；`edu-frontend/public/api-client.ts` 等 React 侧未动（超出 W1 授权）。
  - C1 未做真浏览器端到端 401 回放（仅自检 + 后端 curl 实测；真浏览器 401 回放需 mock 场景，按任务说明降级为单飞逻辑自检）。
- **改动文件**：`edu-frontend/public/edu-api.js`、`login-register.html`、`edu-guard.js`（新增）、8 个 admin-*.html、`test-reports/selfcheck-singleflight-refresh.mjs`（新增）。