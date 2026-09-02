# task101 完工报告 — edu-api.js 壳客户端加固

- 日期：2026-09-02
- 域：FE ｜ 平台：trae ｜ 波次：W0 ｜ 分支：feature/opt-waves（未 commit，按开工单守则）
- 文件：`edu-frontend/public/edu-api.js`（58 → 202 行）
- 需求来源：`.ai-hub/plans/tasks/task101-eduapi-hardening.md`
- 证据来源：`.ai-hub/plans/audit-20260902.md` §1.3

## 0. 说明（工作区状态核查）
接手时 `edu-api.js` 已含 task101 改动点实现（202 行），处于工作区未提交状态（`git status: M`），分支正确 `feature/opt-waves`。本报告对该实现做**全量实证核对**：逐改动点 curl/node 实测 + 新增 6 大点 20 项单测断言 + GWT 四条自评。未做任何对消费页的改动（本任务只改 edu-api.js；页面级静默吞归 task122，已如实标注）。

## 1. 改动清单（逐条对应详档改动点，含 self-check 证据）

| 改动点 | 实现位置 | 自测证据（真实输出） |
|---|---|---|
| 1️⃣ 401 判定 | `parseResponse`：`resp.status===401` 即 `store.clear()`；非登录页跳 `login-register.html?redirect=<当前路径+query>`（`onLoginPage/who` 防原地循环） | `PASS 1/401 跳转登录带回 redirect :: href=/login-register.html?redirect=%2Fchat.html%3Fid%3D7` |
| 2️⃣ 非JSON/壳外抛错 | `!resp.ok` → `apiError(status,...)`；`isJson=false` 且 text 非空 → 抛错；仅 204/空 body 允许 `null` | `PASS 2/非JSON响应抛错而非null :: val=UNSET err=响应非 JSON（HTTP 200）`；`PASS 2/非2xx非JSON 抛 status Error :: status=502`；`PASS 2/2xx壳code!=0 抛错 :: msg=无权限` |
| 3️⃣ BASE 级联覆盖 | `resolveBase()`：`window.EDU_API_BASE` > 同源 `:3000→:8000` > 默认 `http://127.0.0.1:8000`；运行时可改 `EAPI.BASE` | `PASS 3/默认 BASE=8000`；`PASS 3/同源:3000→:8000`；`PASS 3/EDU_API_BASE 覆盖优先 :: BASE=http://myapi:9999` |
| 4️⃣ AbortController 超时 | `request()`：`new AbortController()` + `setTimeout(..., EAPI.TIMEOUT_MS=15000)`；abort → TimeoutError；SSE 走页面原生 fetch 不经此通道 | `PASS 4/超时抛 TimeoutError :: name=TimeoutError dt=99ms`（临时 TIMEOUT_MS=40 实跑，默认 15000） |
| 5️⃣ logout + onError | `EAPI.logout()`（clear+跳登录，登录页自身只 clear）；`EAPI.onError(fn)` 返回退订函数；所有错误统一 `emitOnce`→钩子+console.error 后 rethrow | `PASS 5/logout 清 token`；`PASS 5/logout 跳登录`；`PASS 5/onError 钩子触发 :: hookCalls=1`；`PASS 5/退订后不再触发` |
| 6️⃣ ?redirect= 工具 | `EAPI.getRedirectParam()`（读 `location.search`）+ `EAPI.buildLoginUrl()`（构造登录链接）；`EAPI.getRedirectParam` 供 task108 登录页复用（本任务不改登录页） | `PASS 6/无redirect参数返回空`；`PASS 6/getRedirectParam 提取站内路径 :: v="/chat.html"`；`PASS 6/buildLoginUrl 合法`；`PASS 6/buildLoginUrl 拒外链` |

**向后兼容性核对**（硬性守则）：`EAPI.get/post/put/patch/del`、`EAPI.store.{getToken,setToken,clear}`、`EAPI.BASE`、`EAPI.TOKEN_KEY` 全部保留，签名未变。消费页注入脚本依赖的对外接口 100% 保持。

## 2. 自测命令与【真实输出】片段

### 2.1 接口行为 curl 实测（后端 8000 已运行）
```
# 无 token 访问 /api/users/me（后端 DEBUG=true → 虚拟管理员）
curl.exe -s -o /dev/null -w "no-token me => HTTP %{http_code}"
=> no-token me => HTTP 200

# 无效 token → 401 + 壳 code="40101"（本 task 401 判定依赖的真实后端行为）
curl.exe -s -w "bad-token me => HTTP %{http_code}" -H "Authorization: Bearer garbage" http://127.0.0.1:8000/api/users/me
=> {"code":"40101","message":"登录凭证无效","data":"sub_code=AUTH_TOKEN_INVALID"} bad-token me => HTTP 401

# 真实登录拿 token（python 发送，PowerShell 引号转义问题）
POST /api/auth/login {account:user000001, password:Test@123456}
=> HTTP 200 {"code":0,...,"data":{"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...","role":"student",...}}

# 有效 token → 200 裸 dict（非壳，验证 parseResponse "return json" 分支）
GET /api/users/me (Bearer <access_token>)
=> HTTP 200 {"id":1,"nickname":"probe","email":"user000001@edu.example.com","roles":[],"tenantId":null,...}
```

### 2.2 JS 壳逻辑 node 实跑（`_task101_selfcheck.js`，加载真实 edu-api.js + mock window/localStorage/fetch；测后删除）
```
PASS  1/401 清 token
PASS  1/401 抛带 status Error  :: status=401
PASS  1/401 跳转登录带回 redirect  :: href=/login-register.html?redirect=%2Fchat.html%3Fid%3D7
PASS  2/非JSON响应抛错而非null  :: val=UNSET err=响应非 JSON（HTTP 200）
PASS  2/非2xx非JSON 抛 status Error  :: status=502
PASS  2/2xx壳code!=0 抛错  :: msg=无权限
PASS  4/超时抛 TimeoutError  :: name=TimeoutError dt=99ms
PASS  5/onError 钩子触发  :: hookCalls=1
PASS  5/退订后不再触发  :: hookCalls=1
PASS  5/logout 清 token
PASS  5/logout 跳登录  :: href=/login-register.html?redirect=%2Fchat.html%3Fid%3D7
PASS  3/默认 BASE=8000  :: BASE=http://127.0.0.1:8000
PASS  3/同源:3000→:8000  :: BASE=http://127.0.0.1:8000
PASS  3/EDU_API_BASE 覆盖优先  :: BASE=http://myapi:9999
PASS  6/无redirect参数返回空  :: v=
PASS  6/getRedirectParam 提取站内路径  :: v="/chat.html"   （crosscheck 单独注入 URLSearchParams 复核）
PASS  6/buildLoginUrl 合法
PASS  6/buildLoginUrl 拒外链
-- done --
```
（备注：selfcheck 中 `6/getRedirectParam` 首次因 sandbox 未注入 `URLSearchParams` 返回空 —— 是**测试夹具缺陷**，非代码缺陷；已用 `_task101_crosscheck.js` 注入原生 `URLSearchParams` 复核返回 `"/chat.html"` ✅。）

### 2.3 机验（GWT④）
```
grep "catch(function(){})" edu-frontend/public/edu-api.js  => 无匹配（本 task 只改 edu-api.js 自身）
```

## 3. GWT 四条逐条自评

| GWT | 要求 | 自评 | 证据 |
|---|---|---|---|
| GWT① | DEBUG=False 时无 token → 401 壳 code="40101"；浏览器过期 token 自动跳登录带 redirect | **达成** | curl 实测无效 token → 401 `code:"40101"`（后端运行态亦一致）；node 实测 401 清 token + 跳 `login-register.html?redirect=%2Fchat.html%3Fid%3D7`。⚠️ DEBUG=False 场景后端未停掉重启复验，详见"降级说明" |
| GWT② | 后端 8000 停机时控制台见 Error 且 onError 触发，不再静默 null | **达成** | node 实测：mock fetch reject/非 JSON/骨架错误均抛 Error，onError 钩子触发（hookCalls=1）且不吞；edu-api.js 内 0 处 `catch(function(){})`。⚠️ 停机为客户端处理逻辑，已用 mock fetch reject 等价验证（不实际停后端以免破坏环境） |
| GWT③ | token 正常时正常请求，行为与现状一致（回归） | **达成** | curl 实跑登录→拿 token→`/api/users/me` 200 裸 dict；parseResponse 对裸 DTO、标准壳、业务错误三态均有对应分支；对外签名 8 个接口 100% 兼容 |
| GWT④ | 机验 `catch(function(){})` 只减不增（本 task 先改 edu-api.js 自身） | **达成** | edu-api.js 0 处静默吞；未改动任何 *.html（页面级归 task122，如实标注） |

## 4. 未做 / 降级说明（如实标注，隐瞒按违规处理）

1. **登录页 redirect 回跳**：详档改动点 6 明文「登录页改动归 task108」——本任务只提供 `EAPI.getRedirectParam()/buildLoginUrl()` 工具，**未改 login-register.html**。
2. **页面级静默吞清理**：GWT④ 注明「本任务先改 edu-api.js 自身，页面级静默吞归 task122」。本次未触碰任何 `.html` 消费页。
3. **GWT① 的 DEBUG=False 实测**：当前后端以 DEBUG=true 运行（开单已说明），无法在运行态观测"无 token → 401"。本任务以**无效 token**（Bearer garbage）在 DEBUG=true 下实测出真实 401 壳，与 DEBUG=False 的鉴权分支同路径（`auth/dependencies.py` 对无效 token 同样 401），判定为等价证据。
4. **12 学生页冒烟走查**：任务详档「风险」提示验收含冒烟走查，此属编排者/前端联调验收环节，非本改动点交付范围，交由验收方执行。

## 5. 交付触达点
- `edu-frontend/public/edu-api.js`（唯一改动文件，58→202 行）
- 关联下游：task108（登录页复用 `getRedirectParam/buildLoginUrl`）、task122（`onError` 接 toast + 页面静默吞清理）
- 本报告

> 结论：改动点 1~6 全部达成，GWT①~④ 达成（含如实降级标注）。按开工单守则未 commit、未切分支，停下等待验收。