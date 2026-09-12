# H 热修波汇总报告（H1a/H1b/H1c/H2a/H2b/复验门清单）

> 日期：2026-09-12。执行：独立热修 agent。环境：后端 8000（旧代码进程，未重启）/ 前端 3000 运行中；Redis 容器未跑（降级态，H1a 快断窗生效）；VM 在线（Milvus/Mongo/MinIO/Neo4j ok）。
> 契约约束：`contracts/reshape-a.json` 响应壳 `{code:0,message:"ok",data}` / 分页裸 DTO `{total,page,page_size,items}` 全程未破坏（H1a 附逐值对比证据）。
> Commit 链（feature/opt-waves）：
> - H1a `2553296` fix(hotfix)/H1a-l2-query（前次运行完成，本波复核补证）
> - H1b `c15306b` fix(hotfix)/H1b-debug-gate（前次运行完成，本波复核补证）
> - H1c `ab1e50c` test(hotfix)/H1c-restore-conflicts
> - H2a `ed31f4d` fix(hotfix)/H2a-manager-guard
> - H2b `bed0582` chore(hotfix)/H2b-demo-residue-cleanup
> - 文档（本报告 + 复验门清单）随 docs commit

---

## 1. H1a —— L2 series 详情慢（T19-2）根因修复

**改动**
- `app/core/redis_outage.py`（新增）：进程级 Redis 故障快断窗（30s 冷却）+ 降级保持窗 + 后台探测自愈（探测成本脱离请求路径）。
- `app/middleware/rate_limit.py`：故障态毫秒级降级放行（先于 get_redis）；连接级失败登记窗口、成功清窗；429 壳/限流响应头契约不变。
- `app/core/db_resilience.redis_run`：降级模式毫秒级快断门（DependencyUnavailableError，调用方既有降级路径直通 DB）。
- `app/core/breaker.py`：故障态跳过 hgetall/hset 状态同步（退化本地状态，文档允许语义）。
- `app/domains/course/service.get_series_detail`：学生端装载 SQL **4→2 条**（主行 + 标量子查询聚合 min/max/cohort_count，语义逐一等价）。

**根因结论（重要勘误）**
- 任务书预设「admin get_series_admin 存在 N+1」**不成立**：实读 service/repo，该端点本身是单条主键查询（`SELECT * FROM series WHERE id=%s`）。按教训 8「真实契约优先于页面注释」，以实测为准。
- 真实根因：redis-py 对连接拒绝不快断，单次 incr/get/hgetall 实测 ~2.03s 才失败 → 全站每个 /api/* 请求固定 +2s（限流 1 次）→ 学生端 series/1 缓存路径 3 次 Redis 触点 = +4s，叠加 4 条 SQL 与冷启动池预热 = 8~16s 量级。

**证据 / 数字**
- 前次运行 before/after（commit 2553296 记录，8001 临时实例同 env）：admin series/1 中位 **2.047s → 0.0168s（-99.2%）**；学生 series/1 **4.065s → 0.0129s（-99.7%）**；冷启动 13.6s → 池预热后正常。
- 本波复核（2026-09-12，当前 HEAD 重起 8001 临时实例，验证后即关闭）：
  - 旧代码 8000 基线 ×3：admin series/1 中位 **2.060s**（2.059/2.040/2.080），auth/me 中位 2.057s，`/` 根路由 2.123s —— 全站统一 +2.03s，与 Redis 触点根因吻合；
  - 新代码 8001 ×3：admin series/1 中位 **0.0141s**（首笔 0.208s=快断窗首个真实失败成本，此后 0.0135/0.0141），auth/me ~0.010s，学生 series/1 中位 0.0128s；
  - 响应逐值对比 8000 vs 8001 admin series/1：壳键 `{code,data,message}` 一致、data 全字段**逐值相等**、code=0/message=ok —— 契约形状零变化。
- pytest：`tests/test_redis_outage_fastfail.py` 12 用例 + 既有 breaker/core 59 用例（commit 2553296 记录，71 passed）。
- 预期 <1s 达成（实测 0.014s，余量 70 倍）。

## 2. H1b —— DEBUG 启动硬门禁（P1-8）

**改动**
- `app/config.py`：新增 `ENV_NAME` 字段（默认 `local`，大小写不敏感判定）+ `_debug_env_gate` model_validator：`DEBUG=true 且 ENV_NAME 显式非 local` → ValueError 拒绝启动（对标 Django DEBUG 生产拒启）。`DEBUG=true+local` 放行（本机 .env 照常）；`DEBUG=false` 不受影响。
- 背景：DEBUG=true 且无 Authorization 头时依赖层注入虚拟管理员 user_id=1（P1-8 批判：原仅 WARN）。

**证据 / 数字**
- `tests/test_debug_env_gate.py` 5 用例：DEBUG=true+prod 拒 / DEBUG=true+local 放 / DEBUG=false+prod 放 / ENV_NAME 缺省(=local)+DEBUG=true 放 / 真实 settings 单例(.env)可加载 —— **5 passed**（commit c15306b）。
- live fail-fast：`DEBUG=true ENV_NAME=prod` 启动 → pydantic ValidationError「启动拒绝」，端口永不监听；现有 .env（DEBUG=true，无 ENV_NAME→local）8001 实例正常启动（health 200）。
- 遗留接线：check-demo ⑧ advisory 升 FAIL 语义 → 已登记复验门清单 §五。

## 3. H1c —— restore-40901 / hard-40908 契约测试（P2-13）

**改动**
- 新增 `edu-agent/tests/test_contract_series_restore_conflicts.py`（3 用例，真实 HTTP 直连 8000，夹具沿 test_course_admin 模式：module 级 admin 登录 + 唯一前缀 `h1c{epoch_ms}` + try/finally teardown）。
- 实现复核结论：series 表有 DB 唯一约束 `uk_series_code(institution_id, series_code)` 且软删保留整行、编码不释放 → **restore 内 40901 分支经 HTTP API 不可达**（建 B 在 CREATE 时即 40901；该分支为库外直写数据的纵深防御）。按真实契约断言：
  1. 软删 A(code X) → 建 B(code X) → CREATE 时 409/40901；restore A（编码属主为自身）→ 200 恢复无误伤；恢复后再建 B 仍 40901；
  2. 建班次引用 → `DELETE ?hard=true` → 409/40908（message 含引用计数），系列不被删除；
  3. 对偶：零引用 hard=true → 200「系列已彻底删除」→ GET 404/40400。

**证据 / 数字**
- `pytest tests/test_contract_series_restore_conflicts.py -v` → **3 passed in 52.92s**（8000 live，慢因=旧进程每请求 +2s Redis 开销，非测试本身）。
- 清理登记：40908 用例的班次仅有软删端点（yn=0 仍持 FK），teardown 后残留 2 行（cohort yn=0 + series off_sale）——唯一前缀 `h1c` 可枚举，已由 H2b 一并清理（含本次跑测产生的 h1c1789202005121/h1c1789202007189）。

## 4. H2a —— manager 守卫诚实降级（P1-9，只改 admin-users.html）

**改动**
- `bootAdmin` 加载前复查 `/api/auth/me`：`role!=='admin'` → 诚实横幅「该模块仅 ADMIN 可用（后端权限口径；当前角色 X）」+ 返回仪表盘按钮（→/admin-dashboard.html），**不发列表/指标请求**（此前 manager 过守卫 {admin,manager} 后必吃一个 403 40300 再在错误态展示）；列表区置诚实空态（清骨架屏）。
- auth/me 复查失败 → 与守卫第三段同口径跳登录（不静默发请求）。页面头契约注释同步更新，修正 task109 GWT③ 旧口径。

**证据 / 数字**
- curl 双账号（8000 live）：manager `mgr01test` GET /api/admin/users → **403 `{"code":"40300","message":"角色无权限。当前角色=manager，允许角色=['admin']"}`**；admin `adm02test` → **200 total=100034**。
- jsdom 双角色真报文（加载真实 admin-users.html，stub EAPI 记录请求）：
  - manager：api calls=`["/api/auth/me"]`，**列表请求 0 个**，返回仪表盘按钮=YES，u-error 诚实文案「该模块仅 ADMIN 可用（后端权限口径）；当前登录角色 manager，无权读取用户列表」，渲染行 0；
  - admin：api calls=`[auth/me, metrics, users?page=1]`，渲染 2 行，无横幅无错误。
- `node --check` 内联脚本 4 块全过。

## 5. H2b —— 演示库残留清理（P1-7/P2-14）

**改动**
- 新增 `edu-agent/scripts/cleanup_demo_residues.py`：连接参数读 `edu-agent/.env`；`--dry-run`（默认）打清单不动数据 / `--execute` 真执行+复验清零；五组目标全部先 SELECT 核特征签名，不符即 SKIP 绝不盲删；系列级联前核验 14 张引用表（order_item/consultation/review/risk/attendance/cart/student_rel/compensation/category_rel/coupon_series_rel/favorite/visit/exposure/search）全 0 才删。
- 红线落实：user000001 资料（sys_user/student_profile）零语句；coupon 1/2 种子行及其聚合列不动；真实系列不可能命中「epoch 测试前缀 + off_sale + 名称签名」双闸。

**口径说明**
- 任务清单 4 前缀（rst17886141/jsnn17886141/jsn17886141/t13w1）命中 **6 系列**（含 t13w1=0，幂等）；
- 实测发现同类 epoch 测试家族远超清单（rst17* 九个批次 + jsn/jsnn/jsnu 家族，名称全为「C5 恢复测试/JSON 列测试…」）→ 脚本提供 `--extend-test-family` 扩展口径（前缀家族 + off_sale + 名称含 测试/JSON/C5/H1c 签名），本次按 P2-14 回收站演示观感目标**以扩展口径执行**，全部 54 系列均签名核验通过。

**dry-run 清单（执行前存档，16 步骤）**
```
①community_react(POST 88/89/90/97) → ①community_react(COMMENT，先于评论) → ①community_comment(18)
  → ①community_post 88'task118 测试帖 61744'/89'task118 测试帖 62277'/90'task118 全链验收帖…'/97'task08 契约实测帖 20260906'
②order_item(order_id=80403) → ②`order` 80403 pending → ②coupon_receive_record [51001(订单关联),51122(task16)]
③引用面=0 → ③series_cohort[7890..7900 共10] → ③series[2656..2718 共54, off_sale]
④session_video 205778 → ④session_asset 617332 → ④媒体文件 3145728 bytes
```

**execute / 复验（三段摘要）**
- **执行**：`--execute --extend-test-family` 删 **101 行** + 1 文件 = react 9 + 评论 18 + 帖 4 + order_item 1 + order 1 + 领取记录 2 + 班次 10 + 系列 54 + session_video 1 + session_asset 1 + 媒体文件 3MB；
- **复跑 dry-run**：默认口径与扩展口径均 **0 步骤 / 0 残留**（verify_zero 全绿）；
- **curl 抽验**：`GET /api/community/posts/97` → **404 `{"code":"40410","message":"帖子不存在"}`**；回收站（include_deleted 全量）total **2692 → 2638**，下降 **54 = 删除系列数精确吻合**；off_sale 计数 63 → 9（余 9 行为非测试前缀真实行，红线保留）；媒体文件已不存在。

## 6. 复验门清单（P2-11/P2-15）

**改动**
- 新增 `test-reports/w4-reverify-checklist.md`：定义 5 道复验门（G1 VM ✓ / G2 Docker Desktop→Redis / G3 check-demo 8/8 / G4 L6 RAG ✓已过 / G5 task16/17/06/18 四项 live 复验）、执行步骤、判定总则、当前进度、门上待办（check-demo ⑧ 升 FAIL、G5 打靶脚本落盘）。

**证据 / 数字（当前进度快照）**
- G1 **✓**（2026-09-12 17:05 8001 实例 lifespan：Milvus/Mongo/MinIO/Neo4j 全 ok）；G2 **✗**（Redis 容器未跑）；G3 **✗**（最近记录 5/8，须真实全绿环境重跑）；G4 **✓**（WAVE 批报告）；G5 **✗ 未开始**。
- 两轴 DONE：代码侧 DONE（task19）已达成；**演示侧 DONE 未达成**——G2/G3/G5 过门前不得进 B 批实施。
