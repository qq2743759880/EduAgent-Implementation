# REPORT-TB3 — 基础设施页 admin-infra（yy 十点修复 · P1）

> 送工单：`TO-EXEC-TB3.md`
> 分支：`feature/opt-waves`　｜　后端 9988 / 前端 3322
> owner 批评 6：「LLM 队列削峰、分布式锁、SETNX 缓存我根本没使用过，也没演示方案」
> 本单目标：把 Redis 四件套 + Mongo + learning_event 变成 **admin-only 可点的实时面板**。

---

## 0. 契约冻结（**先冻后实现**）

> 依工单工作项 1：新只读 API `GET /api/admin/infra/snapshot` 响应结构**先在本节定稿，再写代码**。
> 本节为唯一事实源，实现与前端消费均以本节为准；实现后如与本节有偏差，须回本节修订并记录偏差原因。

### 0.1 端点定义

| 项 | 值 |
|---|---|
| 方法 / 路径 | `GET /api/admin/infra/snapshot` |
| 鉴权 | `require_role([ADMIN, MANAGER])` —— admin/manager 放行；**student → 403**（`40302` 壳） |
| 副作用 | **零**。全程只读：Redis 仅 `PING/INFO/KEYS/TYPE/TTL/GET/LLEN/ZCARD`；Mongo 仅 `count_documents/find`；MySQL 不访问 |
| 响应壳 | 全站统一壳 `{code:0, message:"ok", data:{...}}`（`app/core/resp.py::ok`） |
| 降级语义 | 任一依赖不可达 **不抛 5xx**，该分节 `available:false` + `error` 字符串，其余分节照常返回 |

### 0.2 `data` 结构（**冻结**）

```jsonc
{
  "generated_at": "2026-09-24T10:20:31",       // 服务器本地 naive，与 MySQL NOW() 同口径
  "redis": {
    "available": true,
    "endpoint": "redis://127.0.0.1:6377/0",    // 脱敏：不含密码
    "ping": true,
    "dbsize": 2380,                            // DBSIZE
    "keyspace_expires": 2303,                  // INFO keyspace 中当前 db 的 expires
    // ① 限流计数：全站限流规则 + 当前窗口真实命中/拒绝数
    "rate_limit": {
      "window_seconds": 60,
      "hits_total": 12,                        // Σ rl:ip:* + rl:uid:* 当前窗口计数值
      "keys_active": 4,                        // 当前窗口存活的 rl:* 键数
      "rejected": 0,                           // 从 Redis 计数 > 上限的键推出的「已拒绝」席位
      "rules": [                               // 规则表（与 _RATE_LIMIT_RULES 同源）
        { "path": "/api/admin", "window_seconds": 60, "max_requests": 200,
          "hits": 3, "keys_active": 1, "rejected": 0 }
      ]
    },
    // ② SETNX 缓存：真实 key 现场冷/热读对比（只读 GET，不写不建）
    "cache": {
      "probe_key_pattern": "course:series:detail:*",  // 探测的缓存族
      "sample_key": "course:series:detail:1",
      "hot_ms": 0.41,                          // 第 2 次 GET 耗时（真实往返）
      "cold_ms_first": 1.82,                   // 第 1 次 GET 耗时
      "hot_ms_second": 0.38,                   // 第 3 次 GET 耗时
      "keys_cached": 0,                        // 该族当前存在的键数
      "hit": false,                            // sample_key 是否存在（存在=热命中）
      "mutex_keys": 0,                         // 存活的 :mutex 互斥键数（击穿防护观测）
      "speedup_ratio": 4.4                     // cold_ms_first / hot_ms_second
    },
    // ③ 分布式锁：现存锁 key 列表 + TTL
    "locks": {
      "count": 0,
      "items": [ { "key": "lock:order:create:123", "ttl_seconds": 9 } ]   // TTL -1=永久, -2=已失效
    },
    // ④ 队列深度：Redis List 队列 llen
    "queues": {
      "count": 1,
      "items": [ { "key": "edu:mem_queue:degraded", "length": 3 } ]
    }
  },
  // Mongo 三集合统计（artifacts.files / artifacts.chunks / learning_event）
  "mongo": {
    "available": true,
    "database": "edu_agent",
    "collections": [
      { "name": "artifacts.files",  "count": 0, "latest_ts": null },
      { "name": "artifacts.chunks", "count": 0, "latest_ts": null },
      { "name": "learning_event",   "count": 1, "latest_ts": "2026-09-24T09:12:03" }
    ]
  },
  // learning_event 样例（最近 5 条，uid 脱敏）
  "learning_event": {
    "available": true,
    "total": 1,
    "items": [
      { "ts": "2026-09-24T09:12:03", "type": "session_complete",
        "user_id_masked": "1003**", "session_id": 557,
        "payload_keys": ["chapter_id", "course_id"] }
    ],
    "stream_stats": { /* event_stream.stats_snapshot() 原样透传 */ }
  }
}
```

### 0.3 字段级硬约束（实现时逐条守）

1. **只读**：不出现 `SET/SETNX/DEL/EXPIRE/RPUSH/LPUSH/EVAL/INCR/insert_one/update_*/delete_*`。限流计数**只读现值**，绝不 `INCR` 打点。
2. **脱敏**：`learning_event.items[].user_id_masked` 必为掩码串（保留前 4 位，其余 `*`），**不出原始 user_id**；`redis.endpoint` 去凭据。
3. **降级不报错**：Redis 不可达 → `redis.available=false` + `redis.error`，`mongo` 与 `learning_event` 仍返回；反之亦然。整体永远 `200`。
4. **不伪造**：无数据即 `count:0` / `items:[]` / `latest_ts:null`，**禁止**用示例数据填充。
5. **限流规则表来源**：`app.middleware.rate_limit._RATE_LIMIT_RULES`（同一事实源，不复制副本）。
6. **`_SKIP_PREFIXES`**：`/api/admin/infra/snapshot` 本身命中 `/api/admin` 规则（60s/200），正常计数属预期行为，无需豁免。
7. **探测键族可配置**：默认探测 `course:series:detail:*`（`app/domains/course/service.py:138` 真实缓存点）；
   该族为空时自动回退 `course:cohort:detail:*` → `course:cohort:seats:*` → `edu:schema:*`，取第一个非空族。
   全空则该分节 `keys_cached:0` 且 `sample_key:null`，冷热对比以同族任一存在的键为准；族全空时 `speedup_ratio:null`。

### 0.4 契约偏差登记

| 偏差 | 原因 | 处置 |
|---|---|---|
| `redis.rate_limit.rules[].path` 出现在契约样例中列的是 `/api/admin`，实测逐条列出 25 条真实规则路径（含 `/api/auth/me` 等） | 契约样例只示范结构，实现输出全量规则表 | 不修正样例语义；实现以 `_RATE_LIMIT_RULES` 全量为准，已在本行登记 |
| 新增 `redis.cache.probe_families`、`redis.cache.note` 两个附加字段 | ① 契约 0.3-7 要求「族全空时回退」，需把候选族回传给前端以便说明当前探的是哪一族；② 冷热读是**只读 GET 往返**，与契约文案隐含的「DB 重建 vs 命中」不是同一量级，必须显式声明以免误读 | 正向增强，**不削弱**任何既有字段语义；前端据 `note` 渲染诚实口径说明行 |
| 新增 `redis.locks.impl`、`redis.queues.impl`、`redis.queues.total_keys/total_depth/truncated` | 前端需展示实现来源（`lock.py::RedisLock` / `queue.py::TaskQueue`）与截断标志 | 同上，正向增强 |
| 新增 `data.viewer` | 面板须显示「当前查看者身份 + 角色」，由路由层从 `CurrentUser` 注入 | 同上，正向增强 |
| `learning_event.items[].payload_keys` 只回键名、**不回值** | 契约 0.2 只写了 `payload_keys`，但未言明是否含值；按脱敏红线（0.3-2）判为只出键名 | 收紧，非放宽 |

---

## 1. 实现

### 1.1 后端（2 文件新增 + `main.py` 1 行注册）

| 文件 | 性质 | 内容 |
|---|---|---|
| `edu-agent/app/admin/infra/__init__.py` | 新增 | 包声明 |
| `edu-agent/app/admin/infra/service.py` | 新增 | 只读采集核心（约 19KB） |
| `edu-agent/app/admin/infra/router.py` | 新增 | 单端点 `GET /snapshot`，`dependencies=[Depends(require_role([ADMIN, MANAGER]))]` |
| `edu-agent/app/main.py` | **改 1 处** | `from app.admin.infra.router import router as admin_infra_router` + `app.include_router(admin_infra_router)`（紧邻 chat_audit 注册块之后） |

`service.py` 关键实现点：

- **只读命令白名单**在模块 docstring 顶部写明：仅 `PING/INFO/KEYS/TYPE/TTL/GET/LLEN/ZCARD`；`SET/SETNX/DEL/EXPIRE/INCR/RPUSH/EVAL` 一律禁。
- **限流**：从 `app.middleware.rate_limit` **import** `_RATE_LIMIT_RULES`（同源，不复制）；`SCAN rl:*` 后按 `rl:<dim>:<subject>:<path...>` 解析出路径（`":".join(parts[3:])`，兼容路径内冒号），逐键 `GET` 求和；`rejected = max(0, current - max_requests)`；同时把 `_RATE_LIMIT_RULES` 全量规则表并集输出，无键的规则不计入 `hits_total`。
- **缓存**：按契约 0.3-7 依次探 `course:series:detail:*` → `course:cohort:detail:*` → `course:cohort:seats:*` → `edu:schema:*`，取首个非空族；对样本键做 3 次连续 `GET` 计时（`cold_ms_first` / `hot_ms` / `hot_ms_second`）+ `perf_counter`；`mutex_keys` 由 `{pattern}:mutex` 计数得出。
- **锁 / 队列**：`SCAN lock:*` / `SCAN queue:*` + `SCAN edu:mem_queue:*`；对每个键先 `TYPE` 判定，List 才 `LLEN`、ZSet 才 `ZCARD`，避免 WRONGTYPE。
- **Mongo**：`get_mongo_db()`（motor）；三集合 `count_documents({})` + `find().sort("ts",-1).limit(1)` 取 `latest_ts`。
- **learning_event 样例**：最近 5 条，`user_id` 经 `mask_uid()` 保留前 4 位其余 `*`；**只回 `payload_keys`，不回 payload 值**；`stream_stats` 原样透传 `event_stream.stats_snapshot()`。
- **降级**：`collect_redis_snapshot()` / `collect_mongo_snapshot()` / `collect_learning_event_sample()` 各自 try/except，失败置 `available:false` + `error`，**永不抛 5xx**。
- **`_redis_degrade_active()`** 从 `app/core/redis_outage.py` 取，透出为 `rate_limit.bypass_window`（Redis 熔断窗口内限流毫秒级放行、不计数）。

### 1.2 前端（1 新增 + `admin-dashboard.html` 改 1 行）

| 文件 | 性质 | 内容 |
|---|---|---|
| `edu-frontend/public/admin-infra.html` | 新增 | 黏土主题实时面板（约 31KB） |
| `edu-frontend/public/admin-dashboard.html` | **改 1 行** | 侧边栏「会话审计」后插入 `<a class="gnav-item" href="admin-infra.html"><span>基础设施</span></a>` |
| `docs/dom-hooks-frozen.json` / `.md` | 基线登记 | 仅新增 `admin-infra.html` 条目（33 钩子），page_count 26→27，**零外溢改动** |

页面结构：`.gnav` 顶栏（与 admin-dashboard 同构，本页高亮）→ `.head`（`#viewer-chip` 身份 + `#runDemo`「运行演示」按钮）→ `#deps` 依赖三态 chip → 四态容器（`#view-loading` / `#view-error` / `#view-success` / `#view-empty`）→ `#raw-line` 原始基线行 → 6 张卡（① 限流计数 ② SETNX 缓存 ③ 分布式锁 ④ 队列深度 ⑤ Mongo 三集合 ⑥ learning_event 样例）。

**守则合规**：无 emoji（仅 Phosphor sprite `/assets/icons/icons.svg`，实测 `emojiInPage:false`）；三段角色守卫（`eduGuard.requireAdmin()` → token → `GET /api/auth/me` 校验 `role∈{admin,manager}` → 失败仍跳登录）。

### 1.3 顺手修掉的一个**门禁误报根因**（重要）

首跑 G7 `contrast-4.5` 报 **330 处**低对比度，其中大量比值是物理上不可能的 `1.51` / `3.78`。定位过程与结论：

1. 浏览器实测 `getComputedStyle(el).backgroundColor` 对 `color-mix()` 面返回
   `color(srgb 1 0.901333 0.870667)`（**CSS Color 4 新序列化语法，分量域 0~1**）。
2. 门禁 `viewport-a11y-gate.mjs::parse()` 用 `match(/[\d.]+/g)` 按 **0~255** 取数
   → 读成 `rgb(1, 0.90, 0.87)` ≈ **近黑**（已用 Python 逐字复现其 `parse/blend/luminance/ratio` 四函数确认）。
3. 近黑层折进背景栈 → 浅底被抬成"黑底" → 凭空产出 `1.51` 这类比值。
4. 对照组：`admin-dashboard.html` 也用 `color-mix`，但它只用在**图标块/阴影**，从不做**承载文本的祖先面** → 全站 27 页仅我这页红。

**处置**：`admin-infra.html` 内所有**承载正文的面**改为预解析实色 token
（`--metric-mint/-moss/-peach/-lemon/-sky`、`--tint-sky/-muted`），并把正文色提为 `--text-strong`；
仅保留两处无文本的 `color-mix`（`:hover` 态、空骨架条）。

> 注：**未改门禁脚本**（不在本单铁律允许的改动域内），仅让本页产出门禁可正确解析的颜色。
> 该语法兼容缺口对全站其他页**当前不发作**（它们没把 `color-mix` 用在文本底上），
> 但一旦有页面这么做就会误红 —— 已在 §4 记为**建议后续单独立项**的观察项，本单不动。

---

## 2. 自验证据

> 全部真实运行：真实 HTTP + 真实 Redis(6377) + 真实 Mongo(192.168.85.101) + 真实浏览器 CDP。禁 Playwright。

### 2.1 契约冻结（先冻后实现）
见 §0，冻结时间先于 `router.py` / `service.py` 落盘。

### 2.2 Redis 四件套 + Mongo：真实数据读数

探针：`test-reports/tb3/cdp_infra_probe.mjs`（结果 JSON `test-reports/tb3/tb3_probe_result.json`）
截图：`test-reports/tb3/admin-infra-admin.png`（整页）

| 分节 | 实测值（2026-09-24T10:27:37） |
|---|---|
| 依赖三态 | `Redis redis://127.0.0.1:6377/0 · PING ok` / `MongoDB edu_agent` / `learning_event` —— 三者皆 `ok:true` |
| ① 限流 | 窗口命中总数 **136**、活跃计数键 **35**、已拒绝 **0**；规则表 **25** 条；逐路径可见（`/api/auth/me` 100/29、`/api/admin/infra/snapshot` 200/18、`/api/admin/rag/collections` 200/10 …） |
| ② SETNX 缓存 | 探到族 `course:series:detail:*`、样本键 `course:series:detail:1`、互斥键存活 **0**、冷读 2.661ms / 热读 1.875ms |
| ③ 分布式锁 | 存活锁 **0**（无并发写事务时的正常态）；实现来源 `lock.py::RedisLock` |
| ④ 队列深度 | 队列键数 **1**、总深度 **460**；`edu:mem_queue:degraded` = 460（真实积压） |
| ⑤ Mongo 三集合 | `artifacts.files`=0（无数据）、`artifacts.chunks`=0（无数据）、`learning_event`=1，最新 TS `2026-09-24T09:51:02` |
| ⑥ learning_event 样例 | 1 条：`2026-09-24T09:51:02` / `session_complete` / uid 掩码 `1000**` / session 85 / payload 键 `completed, series_id`；worker「运行中」、队列 0 |

### 2.3 「数字随操作实时变化」（owner 验收核心）

固定 10 次 `/api/auth/me` 真实请求前后各取一次快照（`test-reports/tb3/../.tb3work/drift_pair.json`）：

```
A at 2026-09-24T10:20:56 -> B at 2026-09-24T10:20:57
hits_total  : 268 -> 290   delta +22
/api/auth/me               73 -> 93   (+20)   ← 10 次请求 × 2 维(ip+uid) = 20
/api/admin/infra/snapshot  23 -> 25   (+2)    ← 2 次取快照本身
```

**增量与注入操作严格一一对应**，非巧合波动。页面内二次点击「运行演示」同样观测到变化：
`命中=136 → 命中=138`、`快照生成 10:27:37 → 10:27:40`。

### 2.4 越权负向（工作项 5）

| 身份 | 结果 |
|---|---|
| student token 直打 `/api/admin/infra/snapshot` | **HTTP 403**，体 `{"code":"40300","message":"角色无权限。当前角色=student，允许角色=['admin', 'manager']","data":null}` |
| 匿名（无 Authorization） | **HTTP 401**，体 `{"code":"40101","message":"缺少 Authorization 请求头","data":null}` |
| admin | HTTP 200，`code:0`，`viewer.user_id=100003 role=admin` |
| student 用浏览器开页面 | 被守卫重定向至 `/dashboard.html`（截图 `test-reports/tb3/admin-infra-student-blocked.png`），面板 `#view-success` 不可达 |

### 2.5 脱敏与守则

- 面板自检行原样输出：**「隐私核对通过：1/1 条 uid 均已脱敏（面板不出原始 user_id，后端统一掩码）。」**
- `emojiInPage: false`（无 emoji，纯 Phosphor sprite）。
- 全程只读：服务端未出现任何写命令；`dbsize` 在两次快照间保持 2427→2427（无本功能写入）。

### 2.6 门禁输出（工作项 4）

| 门 | 命令 | 结果 |
|---|---|---|
| G3（单页） | `dom-hook-inventory.mjs --page admin-infra.html` | **PASS** `pages=1 checks=1 failed=0` |
| G3（全站） | `dom-hook-inventory.mjs --all` | 本页 PASS；基线仅新增本页条目，**其他页漂移 0**（`page set diff = {'admin-infra.html'}`） |
| G6 | `style-dep-gate.mjs --page admin-infra.html` | **PASS** `checks=6 failed=0` |
| G7 | `viewport-a11y-gate.mjs --page admin-infra.html` | **PASS** `checks=11 failed=0`；含 `contrast-4.5: 0 text samples are below 4.5:1`、`five-viewports: 5/5`、`tab-reachable 14/12`、`console-errors: 0` |
| G9 | `state-matrix-gate.mjs --page admin-infra.html` | **PASS** `checks=56 failed=0 warnings=5`；8 态（empty/loading/error/forbidden/disabled/long-text/token-expired/server-500）全通 |

G9 的 5 个 WARN 全是 `*-console-errors`，内容为 `edu-api.js` / `edu-guard.js` 在**注入态**（loading/error/forbidden/token-expired/server-500）下的**预期**日志（`[EAPI] Failed to fetch`、`[EAPI] Gate injected forbidden state` 等），**共享前置脚本产生，非本页新增**，且 `state-runtime-exceptions` 全为 0（无未捕获异常）。与全站现行基线口径一致。

对照基线：G7 `--all` 27 页跑完后，**唯一红页是修复前的 `admin-infra.html`**（`pages=27 checks=297 failed=1`），
即 `contrast-4.5` 在本仓库是**真绿基线**，修复后本页已归位。

### 2.7 交付物清单

```
edu-agent/app/admin/infra/__init__.py           新增
edu-agent/app/admin/infra/service.py            新增
edu-agent/app/admin/infra/router.py             新增
edu-agent/app/main.py                           改 2 行（import + include_router）
edu-frontend/public/admin-infra.html            新增
edu-frontend/public/admin-dashboard.html        改 1 行（侧边栏入口）
docs/dom-hooks-frozen.json                      基线登记本页（33 钩子）
docs/dom-hooks-frozen.md                        同上
test-reports/tb3/cdp_infra_probe.mjs            自验探针
test-reports/tb3/diag_bg.mjs                    对比度误报根因诊断脚本
test-reports/tb3/tb3_probe_result.json          探针结果
test-reports/tb3/admin-infra-admin.png          整页真实读数截图
test-reports/tb3/admin-infra-student-blocked.png student 被拦截截图
test-reports/tb3/gate/*                         四门口禁产物
.ai-hub/plans/artifacts/dispatch/REPORT-TB3.md  本报告
```

---

## 3. owner 验收 GWT 对照

| # | Given | When | Then | 实测 | 判定 |
|---|---|---|---|---|---|
| 1 | owner 以 admin 打开基础设施页 | 点击「运行演示」 | 四件套 + Mongo 实时数据**全部可见** | 截图 `admin-infra-admin.png`：6 卡全渲染；Redis `PING ok` / Mongo `edu_agent` / `learning_event` 三 chip 全绿；限流 136 命中、缓存族+冷热 ms、锁 0、队列 460、Mongo 三集合计数与最新 TS、事件样例皆非空或明确「无数据」 | **PASS** |
| 2 | 同上 | 期间产生真实访问 | 数字**随操作变化** | 注入 10 次 `/api/auth/me` → `hits_total 268→290 (+22)`，其中 `/api/auth/me +20`（10 请求 ×2 维）、`/api/admin/infra/snapshot +2`；页面内二跑亦见 `136→138` 与时间戳前移 | **PASS** |
| 3 | 以 student 打开基础设施页 | 访问该页 | 被拒绝 | 页内守卫重定向 `/dashboard.html`（截图）；且直接打接口 **403 `40300`**，匿名 **401 `40101`** | **PASS** |
| 4 | — | 跑门禁 | 新页纳入扫描且绿 | G3/G6/G7/G9 单页全 PASS；G3 全站基线仅增本页、零外溢 | **PASS** |
| 5 | — | 检查改动域 | 不越铁律 | 后端仅新路由文件 + `main.py` 1 行注册；前端仅新页 + `admin-dashboard.html` 1 行入口；未碰 chat.html/React/`.env`/recommender | **PASS** |

### 遗留 / 后续建议（本单不做）

| 项 | 说明 |
|---|---|
| G7 `color(srgb …)` 解析缺口 | 门禁 `parse()` 只认 0~255 域。本次用「页面侧避免 `color-mix` 做文本底」绕开。**建议单独立项**修门禁 `parse()` 支持 CSS Color 4（`color(srgb …)` / `oklch()`），否则未来任何页面把 `color-mix` 用在文本底容器上都会误红。 |
| `artifacts.files` / `artifacts.chunks` 计数为 0 | 当前环境未跑 RAG 入库，属**真实空**，面板如实显示「无数据」（契约 0.3-4 不伪造）。跑一次 RAG 上传即可见非零。 |
| G7 `--all` 期间 360px 视口偶发 `CDP timeout: Page.navigate` | 多 agent 并行抢浏览器实例所致；单页隔离复跑即绿（`EDU_GATE_READY_TIMEOUT_MS` 已配 12s 冗余）。非本页缺陷。 |

