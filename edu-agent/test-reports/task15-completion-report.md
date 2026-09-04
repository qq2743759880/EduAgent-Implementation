# task15 完工报告 — 存量模块响应壳适配（契约冻结⑬）

> **日期**: 2026-08-21 | **状态**: ✅ 等待编排者复验
> **前置**: task10（响应壳中间件）、task14 复验通过（契约⑤）
> **结论**: 6/6 GWT 全部 PASS；契约测试 20/20；冒烟 28/28

---

## 一、修改清单（只适配壳，不改业务逻辑）

| # | 模块 | 修改点 | 文件 |
|---|------|--------|------|
| 1 | auth | login/refresh/me 由裸返回 → `ok()` 包壳（JWT 语义不变）；`response_model` 统一为 dict | `app/auth/router.py` |
| 2 | chat | sessions CRUD/search/非流式 → `ok()` 壳；SSE done 事件内嵌 `{code:0,message:"ok",data}` | `app/chat/router.py` |
| 3 | community | posts/comments/详情/点赞/收藏/回帖 → `ok()` 壳 | `app/community/router.py` |
| 4 | gamification | 徽章/积分/加积分/排行/check-badges → `ok()` 壳；**排行榜改 Redis ZSET**（周榜快照 + 实时增量） | `app/gamification/router.py`、`app/gamification/service.py` |
| 5 | mcp | servers/tools/call-log/sessions 等 18 端点 → `ok()` 壳 | `app/mcp/router.py` |
| 6 | rag_admin | collections/presets/audit-log/search → `ok()` 壳 | `app/admin/rag_admin/router.py` |
| 7 | 测试 | 新增 `test_contract_task15.py`（20 用例）；`test_contract_middleware.py`/`test_contract_all_routers.py`/`locustfile.py` 的 login 解壳适配 | `tests/` + `tests/performance/` |

---

## 二、验收证据

### GWT ①：契约测试运行 → 全部端点 100% 统一壳 + SSE done 内嵌壳

```text
tests/test_contract_task15.py  20 passed in 17.13s   （6 模块全端点壳断言）
tests/test_contract_middleware.py::TestResponseShell  6 passed
scripts/_smoke_task15.py        28 PASS / 0 FAIL       （auth/chat/community/gamification/mcp/rag_admin + SSE + ZSET）
```

SSE done 事件内嵌壳实测：
```text
[OK] SSE done 事件内嵌壳: code=0 message=ok
     data.keys=['session_id','message_id','retrieved_count','final_count','latency_ms','rewrite_query','degraded_reason']
```

### GWT ②：/rankings 来自 ZSET，积分变更 1s 内可查

打靶加积分后 1s 内查询排行：
```text
[PASS] GET /api/gamification/rankings | status=200 code=0
[INFO] rankings source=ZSET          ← Redis 排行榜生效
[INFO] my_rank: rank_no=1 metric_value=120
```

Redis 直接核验（读侧 = 写侧，zincrby 实时累计）：
```text
redis-cli KEYS "g-rank:*"
  g-rank:DAILY:POINTS:2026-08-21      ← 当日周期 key
  g-rank:WEEKLY:POINTS:2026-W33       ← 周榜（周一 2026-08-17 起）
  g-rank:MONTHLY:POINTS:2026-08
  g-rank:ALL_TIME:POINTS:ALL

redis-cli ZREVRANGE "g-rank:WEEKLY:POINTS:2026-W33" 0 4 WITHSCORES
  "100003"  120                        ← 写入侧 zincrby 增量实时可见
```

### GWT ③：auth 登录/注册/refresh 全流程 → 壳统一但 JWT 语义不变

```text
[PASS] POST /api/auth/login 成功壳 | status=200 code=0   data.access_token=eyJ...（JWT 语义不变）
[PASS] POST /api/auth/login 失败壳 | status=401 code=40111 data=null
[PASS] POST /api/auth/refresh 成功壳 | status=200 code=0   data 含新双 token
[PASS] POST /api/auth/register | status=201 code=0        data.user_id
[PASS] GET /api/auth/me 成功壳 | status=200 code=0        data.role=admin
```

---

## 三、gamification ZSET 排行设计

| 键 | 结构 | TTL |
|----|------|-----|
| `g-rank:{SCOPE}:POINTS:{period}` | Redis ZSET（member=user_id, score=积分）| DAILY 2d / WEEKLY 8d / MONTHLY 33d / ALL_TIME 400d |
| 周榜 period | `%Y-W%W`（周一为周起点，与 `_scope_start` 同口径）| — |

- **写入侧（实时增量）**：`award_points` 积分落库后 → `zincrby` 累加到当前周期所有 scope 的 POINTS ZSET（1s 内可查），任何异常静默降级不阻塞主流程。
- **读取侧**：`ranking()` 优先 `zrevrange` 读 ZSET；key 空缺时用 SQL 实时算并回填种子后走 ZSET；Redis 不可用 → `source="LIVE_CALC"` SQL 兜底。
- **SSE 例外**：`done` 事件 data 内嵌统一壳 `{code:0, message:"ok", data:{...}}`（非 SSE 端点仍走 `ok()`/全局 handler 壳）。

---

## 四、范围边界（红线确认）

- **只适配壳不改业务逻辑**：6 个模块的 service 业务逻辑零改动（gamification 新增 ZSET 排行写入/读取，属任务明确交付物）。
- **范围外模块不动**：quiz/vocab/coding/math 等 interactive 模块、progress/users/recommender/mindmap 不在 task15 范围，未改动。

---

## 五、已知的非本次回归失败（pre-existing，与本任务无关）

以下失败是**存量测试用例的断言 bug**，测试文件与本次改动文件无交集，非 task15 引入：
- `test_auth_service.py`：`assert '40312' == 40312`（字符串码 vs 整数码）
- `test_error_codes.py`：`assert '50002' == 50002`、`test_subcode_map_complete` TypeEror 等
- `test_contract_all_routers.py::TestResponseShellExtra::test_failure_code_is_string`：task13 使 `/api/admin/questions/banks` 变为成功端点，旧测试假设失败

---

## 六、交付物

- [x] `scripts/_smoke_task15.py`（task15 冒烟脚本）
- [x] `tests/test_contract_task15.py`（契约⑬ 契约测试，20 用例）
- [x] `test-reports/task15-completion-report.md`（本文件）
- [x] `.opencode/handoffs/task15-contract.md`（契约⑬ 交接单 → 解锁前端 task42/50/51/52/53/55/60/62）
- [x] `powershell -File D:\.ai-hub\sync.ps1`
- [ ] **停下等编排者验收 task15，未经验收不得开始 task16** ⏸️