# B2 完工报告:Refine 数据层骨架(共享 queryClient + 401 single-flight interceptor + dataProvider 骨架)

> 派单:`.ai-hub/plans/dispatch-plan-reshape-b.md` §四-B2(B0 §5 修订定义)
> 选型依据:`.ai-hub/plans/tech-source-audit.md`(B0 冻结:Refine v5 headless,@refinedev/core@5.0.12)
> 执行:B 批次前端数据层 agent(独立开发) · 日期 2026-09-12 · 平台 ZCode Agent
> **范围红线**:不接任何业务页面;edu-api.js 只读未改;public/*.html 未触碰;契约冻结未改;零 DB 直写。

---

## 0. 结论先行

| 项 | 结果 |
|---|---|
| 交付物 | `edu-frontend/refine-layer/`(5 文件,**590 行**;prod 直接依赖 **2 个**,lockfile 39 包) |
| npm 可用性 | 可用(registry PONG 916ms,2026-09-12 实测)→ **无 SPIKE_DEFERRED** |
| scratch 验证 | **5/5 tests · 3/3 files 全过**(vitest+jsdom,系统临时目录,不入 git) |
| **401 并发硬验收** | **并发 5 个 401 → refresh 恰 1 次**(list_calls=10 = 首轮 5×401 + 重放 5×200;token 滑动更新;零跳登录) |
| 零手写轮询 | refetchInterval=100ms 时 700ms 内框架自动 refetch 7 次;交付物源码扫描 **0 处 setInterval** |
| 类型自检 | `tsc --noEmit` 零错误(strict) |

---

## 1. 现状自证(开工前逐条实测)

| 核对项 | 实测结果 |
|---|---|
| refine-layer/ 是否已存在 | 不存在(全新建) ✅ |
| node/npm | v24.18.0 / 11.16.0;`npm ping` PONG 916ms ✅ |
| @refinedev/core latest | 5.0.12(与 B0 审计快照一致,2026-09-12 `npm view` 实测) ✅ |
| edu-frontend 既有栈 | next 16.3.0 / react 19.2.8 / @tanstack/react-query ^5.101.4(package.json 实测) ✅ |
| 分页契约参数名 | 请求 `?page=&page_size=`、响应裸 DTO `{total,page,page_size,items}`(admin-users.html:556 真实调用实测) ✅ |
| B0 spike 遗留 | Temp 已清理,scratch 全新搭建 ✅ |
| 契约冻结 | contracts/reshape-b.json(health-scan 域)未触碰;本任务无契约变更点 ✅ |

## 2. 交付物清单(验证对象=交付物本体)

```
edu-frontend/refine-layer/
├── package.json          # @edu/refine-layer;deps: @refinedev/core@^5.0.12 + @tanstack/react-query@^5.101.4
├── tsconfig.json         # strict
└── src/
    ├── http.ts           338 行  # fetch 封装:壳解包{code:0} + 超时 + 401 single-flight interceptor(核心)
    ├── data-provider.ts   94 行  # Refine DataProvider 骨架:分页映射+CRUD;filters/sorters 传入即明确报错(不臆造)
    ├── auth-store.ts      76 行  # token 存取;键名与 edu-api 完全一致(fe-html 与 Refine 侧共享凭证)
    ├── index.tsx          47 行  # 统一出口 + EduRefineProvider(B3 挂接入口)
    └── query-client.ts    35 行  # TanStack Query v5 QueryClient 单例(4xx 不重试/写路径零重试)
                           ────
                      合计 590 行   # 供 B3 C15 判据(≤214 行)基数参照:B2 骨架不计入 B3 业务页面行数
```

依赖计数:prod 直接依赖 **2**(@refinedev/core、@tanstack/react-query),dev 2(typescript、@types/react),lockfile 39 包。react 为 peerDependency(复用宿主 edu-frontend 的 19.2.8,不引入第二份)。

## 3. 关键技术事实(全部实测,不臆造)

1. **queryClient 注入方式**:Refine v5 **没有** `<Refine queryClient>` prop;v5 注入点 = `options.reactQuery.clientConfig`(contexts/refine/types.d.mts:77)。且 dist/index.mjs 内部实测:`if (clientConfig instanceof QueryClient) return clientConfig;` —— 传 QueryClient **实例**时 Refine 零新建、直接复用。即:
   `<Refine options={{ reactQuery: { clientConfig: getEduQueryClient() } }}>` 实现全应用单例(V1-EVIDENCE 已证 useList 的 query 缓存落在该单例:cache key 含 "users")。
2. **useList v5 返回形状改版**:返回 `{query, result, overtime}`,数据在 `result = {data, total}`(V1 实测;v4 文档的 `{data,total}` 直取写法已失效)——B0 审计"文档滞后于 v5"模式的又一实例,**B3 接页面时按 `result` 取数**。
3. **Pagination 字段改名**:v5 为 `currentPage`(types.d.mts:166),v4 的 `current` 不存在(tsc 实证)。
4. **getApiUrl() = base + "/api"**:后端全部业务端点挂 /api 前缀(edu-api.js 各页调用实测),Refine 约定 URL = getApiUrl()+resource → B3 的 resource 用相对路径(如 `"admin/users"`)。
5. **单飞复位语义**:refreshPromise 完成即复位(edu-api 等价),下一轮 401 可再进入。

## 4. scratch 验证(系统临时目录 `C:\Users\Administrator\AppData\Local\Temp\b2-scratch\`,不入 git)

方式:vitest+jsdom;vitest alias 直接命中交付物 TS 源码(`@edu/refine-layer` → refine-layer/src/index.tsx),**验证对象=交付物本体,零拷贝**。mock fetch 全局拦截,记录每次调用的 path/Authorization/body。

### 4.1 验证1:列表查询(壳解包+分页映射+共享 queryClient)✅
- React 挂载 `EduRefineProvider` + `useList({resource:"users", pagination:{currentPage:2, pageSize:5}})`;
- UI 渲染 user001/user002,total=42;请求 URL 实测 `/users?page=2&page_size=5` + `Bearer at-ok`;
- 共享 queryClient 证据:`qc.getQueryCache()` 中出现 refine 的 users query key(单例承载框架数据层)。

### 4.2 验证2(硬验收):401 并发 single-flight ✅
```
[V2-EVIDENCE-HARD] concurrent=5, refresh_calls=1, list_calls=10 (5 first-round 401 + 5 replay),
                   redirected=0, token_after=at-new
[V2-EVIDENCE-NEG1] refresh_fail: refresh_calls=1, rejected=5/5 (401), redirects=5,
                   store_cleared=true, redirect_url=/login-register.html?redirect=%2F
[V2-EVIDENCE-NEG2] no_refresh_token: refresh_calls=0, rejected=1(401), redirected=true, store_cleared=true
```
- 正例:5 个并发请求全部首击 401 → 单飞只发 **1 次** `/api/auth/refresh`(请求体仅含 refresh_token,不带 Authorization——防 401 死锁)→ 5 个请求各自重放恰一次 → 全部 200;access 更新为 at-new,refresh 滑动续期 rt-new;不跳登录。
- 负例1(refresh 401):单飞仍只 1 次 refresh;5 请求全部 reject `ApiError(401)`;store 清空;每失败请求各自跳登录 ×5。
- 负例2(无 refresh_token):不发 refresh,直接清 token+跳登录+reject 401。
- **诚实登记**:并发失败时跳登录触发 5 次——这是对 edu-api `handleUnauthorized` 的逐请求等价复刻(每次失败各自 clear+gotoLogin),**未做去重优化**(去重属于行为变更,超出"等价迁移"授权;B3 如需去重应走变更单)。

### 4.3 验证3:零手写轮询 ✅
```
[V3-EVIDENCE] refetchInterval=100ms, 700ms 内 fetch 次数=7, UI tick=7,
              手写轮询扫描=auth-store.ts,data-provider.ts,http.ts,index.tsx,query-client.ts → 无 setInterval
```
轮询由 TanStack Query 的 `queryOptions.refetchInterval` 声明式驱动(初始 1 次 + 自动 refetch 6 次,UI 跟随最新一轮),交付物源码零定时器代码。

### 4.4 401 语义与 edu-api 等价性对照(逐条)

| edu-api.js(W1-C1) | refine-layer/http.ts | 等价 |
|---|---|---|
| 401 且已重放 → 清 token+跳登录+抛错("重新登录后凭证仍无效") | 同 | ✅ |
| 401 且无 refresh_token → 清 token+跳登录+抛错 | 同 | ✅ |
| scheduleRefresh 模块级单飞,并发复用同一 Promise | 同 | ✅(硬验收 refresh_calls=1) |
| refresh 成功 → setToken+滑动续期+重放恰一次 | 同 | ✅(list_calls=10) |
| refresh 失败/网络挂 → 清 token+跳登录+抛错 | 同 | ✅ |
| refresh 请求不带过期 access、独立超时 | 同 | ✅ |
| 壳:{code:0}→data;code≠0→抛;裸 DTO 原样;空 body→null;非 JSON 非空→抛 | 同 | ✅ |
| 键名 edu:auth:token / edu:auth:refresh;BASE 级联 EDU_API_BASE > :3000→:8000 > 127.0.0.1:8000 | 同 | ✅ |
| 15s AbortController 超时,TimeoutError 标记 | 同 | ✅ |
| onError 全局错误钩子(注册返回退订函数)+emitOnce | 同形(默认 console.error) | ✅ |
| 差异 | 登录页/跳转动作改为可注入 `configureHttp({loginPage, onRedirect})`,默认值 `/login-register.html`+location.href 与 edu-api 相同 | 设计差异(可测性),默认行为等价 |

## 5. 批判承接核对

| 来源条目 | 承接 |
|---|---|
| B0 §5"taskB2 范围修订提示" | 按修订定义实现:Refine 注入**共享 queryClient**(单例经 clientConfig 实测注入,零双轨)+ 401 收敛为 interceptor(http.ts) |
| tech-source-audit §4-3 壳适配判据(≤30 行/资源) | getList 分页映射+壳解包 ~12 行 ✅ |
| tech-source-audit §3 卡点1(routerProvider default 导出) | 本任务未用 router 绑定;EduRefineProvider 留 `routerProvider` 透传 prop,注释已标注"B3 传入 @refinedev/nextjs-router 的 **default 导出**" |
| B0 esbuild postinstall allow-scripts 拦截 | 本轮复现(scratch esbuild@0.28.2 被拦,vitest 正常工作)——环境注意项维持登记 |
| W1-C1 场景 | 并发 401 用例沿用其语义,硬验收通过(§4.2) |
| C17(消灭手写客户端) | B3 起页面数据一律走共享 queryClient+dataProvider,本骨架即收敛点 |

## 6. 三视角自检

**实现者视角**:5 模块 590 行,strict tsc 零错;401 语义逐条对照 edu-api 复刻;全部关键 API 形状(Pagination.currentPage/useList 形状/clientConfig)以包内 d.ts+dist 实测定案,零臆造。

**验收者视角**:三组验证可重跑(scratch 在 Temp,重跑命令 `cd %TEMP%\b2-scratch && npx vitest run`);硬验收数字(refresh_calls=1/concurrent=5)由 mock 计数器断言,非目测;完整 vitest 输出存 `%TEMP%\b2-scratch\vitest-final-output.log`(5/5 passed,EXIT=0)。

**批判者视角(诚实边界)**:
1. scratch 为 vitest+jsdom 逻辑环境,**未在真实浏览器/Next.js 宿主渲染**(守则禁 Playwright);EduRefineProvider 的真实挂载属 B3 开工单范围。
2. mock fetch 模拟后端,**未打真实 8000 后端**(401 单飞逻辑与后端无关,数据形状契约有 admin-users.html:556 实测背书;B3 接真实端点时复核)。
3. filters/sorters 传入即抛"未映射"错误——骨架边界故意如此(不臆造各端点筛选参数名),B3 按端点实测补齐。
4. 写路径(create/update/deleteOne)未在 scratch 实测(验证范围=任务书三项);其壳解包与 getList 同源(http.ts),风险低。
5. 跳登录 5 次不去重是"等价优先"的裁定,不是遗漏(§4.2 诚实登记)。

## 7. 交付边界确认

- 交付物**不含任何业务页面代码**(5 文件均为数据层模块,B3 挂接入口 `EduRefineProvider` 除外,其本身无业务逻辑);
- edu-api.js、public/*.html:零改动(git diff 可证);contracts/:零改动;DB:零直连;
- scratch 位于系统临时目录,不入 git;refine-layer/node_modules 由根 .gitignore(`node_modules/`)排除。

## 8. Commit

- `feat(b)/B2-query-layer`:仅含 `edu-frontend/refine-layer/` 与本报告(见 commit hash 于会话输出)。
