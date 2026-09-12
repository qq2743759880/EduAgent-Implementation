# task19 验收报告——A 批全链路回归 + 渲染矩阵 + 强制技术批判

> 验收 agent:独立收口 agent(编排者派单) | 日期:2026-09-12 | 工作区:`E:\stu\project\stu\EduAgent实施手册`
> 守则遵循:零生产代码改动(本会话仅新增 3 个验收脚本 + 15 张截图 + 2 份批判文档 + 本报告,见 §6 足迹);禁 Playwright(CDP 仅渲染截图/console 收集,接口断言全部 fetch);零写操作(未下单/未发帖/未改数据,订单复验用既有真实订单);未 git commit。
> 判定口径:契约以 curl 实测为准(教训 8);环境红项如实标 ENV_BLOCKED 不伪造 PASS(教训外准则,本次诚实口径)。

---

## ① 环境态(check-demo.mjs 原样输出)

```
=== EduAgent 演示前检查单 check-demo.mjs ===
模式: normal  时间: 2026/9/12 12:44:21

[FAIL] ①. Milvus 连通 192.168.85.101:19530 (3007ms)
       -> 开启 VMware 虚拟机: vmrun start "E:\tt\CentOS 7 64 位 的克隆 docker\CentOS 7 64 位 的克隆 docker.vmx" nogui,等 60s [连接超时(>3000ms),主机不可达]
[FAIL] ②. Redis(docker exec edu-redis-standalone redis-cli ping) (316ms)
       -> docker start edu-redis-standalone(若 docker 引擎未运行,先启动 Docker Desktop)[docker 引擎未运行(Docker Desktop 未启动)]
[FAIL] ③. MongoDB 连通 192.168.85.101:27017 (3003ms)
       -> 开启 VMware 虚拟机: ...(同①) [连接超时(>3000ms),主机不可达]
[PASS] ④. 后端 8000 /health (58ms)  status=ok v0.3.0
[PASS] ⑤. 前端 3000 /login-register.html (17ms)
[PASS] ⑥. 登录链路 login×2 + /api/auth/me×2 (8994ms)  adm02test(role=admin,user_id=100003) + user000001(role=student,user_id=1)
[PASS] ⑦. 关键页 200 × 8 (126ms)  8/8 全 200
[PASS] ⑧. advisory: DEBUG 虚拟管理员探测(无 token /api/admin/users) (13ms)  无 token 被 401 拒绝(DEBUG 安全)

汇总: 绿 5/8,红项 ①、②、③ —— 请按上方指引处置后重跑 (检查耗时 15534ms)
```

**ENV_BLOCKED 清单(环境阻断,非代码缺陷)**

| # | 红项 | 根因 | 受影响链路 | 缺陷定性 |
|---|---|---|---|---|
| 1 | Milvus 192.168.85.101:19530 连接超时 | VMware 虚拟机未开机 | 知识库分区管理(admin-rag-upload 的分区/集合健康)、RAG 上传入库、chat 检索引用(RAG 域) | 环境阻断非代码缺陷 |
| 2 | Redis docker exec 失败 | Docker Desktop 未启动(容器 edu-redis-standalone 未跑) | 限流/缓存/队列增强路径(当前 8000 后端无 Redis 仍全功能可用,本次 E2E 22 项全过即证) | 环境阻断非代码缺陷 |
| 3 | MongoDB 192.168.85.101:27017 连接超时 | 同① VMware 未开机 | Mongo 依赖链路(演示线主链路 0 端点依赖,见 reshape-a 批判 R2/C16) | 环境阻断非代码缺陷 |
| 4 | 8003 验证服务未运行 | 未启动 | 非前端依赖,不阻塞演示与验收 | 不适用 |

> 管理线 `GET /api/knowledge/partitions` 在此环境下返回 HTTP 500 + code 50000(详见 §2 ENV_BLOCKED 行)——是红项 1 的直接传导,定性为环境阻断;但其错误形态本身登记为批判 T19-3/C-18(内部异常串泄漏,代码可改进项)。

---

## ② 双线 E2E(真实 HTTP,只读,脚本 `edu-agent/scripts/_verify_task19_e2e.mjs`)

**汇总:23 步 = 22 PASS + 1 ENV_BLOCKED,0 FAIL**(exit 0)

### 学生线(user000001,13 步全 PASS)

| 步 | 端点 | HTTP | code | 关键断言 | 实测(ms) | 判定 |
|---|---|---|---|---|---|---|
| 1 | POST /api/auth/login | 200 | 0 | access_token 存在;`data.user.role=student`;token_type=Bearer | 2512 | PASS |
| 2 | GET /api/series?page=1&page_size=20 | 200 | 0 | 分页壳 {total,page,page_size,items};items 非空;item 含 id/series_name;**total=2628** | 2087 | PASS |
| 3 | GET /api/series?keyword=信息学&sort=price_asc(筛选组1) | 200 | 0 | keyword 过滤 total≤全量;items 系列名均含关键词 | 2064 | PASS |
| 4 | GET /api/series?category=信息学与编程启蒙&page_size=5(筛选组2) | 200 | 0 | page_size=5 生效(items≤5);category 过滤 total≤全量 | 2049 | PASS |
| 5 | GET /api/series/1 | 200 | 0 | id=1 详情结构完整(**注意耗时,见 §6 遗留 T19-2/C-17**) | 8128 | PASS |
| 6 | GET /api/coupons/templates | 200 | 0 | 可领券模板列表返回 | 2032 | PASS |
| 7 | GET /api/trade/order/6-260906172441-86dcaa(既有真实订单复验,未新下单) | 200 | 0 | order_no 匹配;items 数组存在 | 2048 | PASS |
| 8 | GET /api/enrollments/me/cohorts | 200 | 0 | 我的班次列表(渲染矩阵佐证 2 个真实班次) | 2054 | PASS |
| 9 | GET /api/users/me/learning-summary | 200 | 0 | 学习数据对象非空 | 2056 | PASS |
| 10 | GET /api/progress/dashboard | 200 | 0 | 进度面板非空 | 2052 | PASS |
| 11 | GET /api/gamification/rankings | 200 | 0 | 排行数据存在(4~8s,遗留性能项同上) | 4067 | PASS |
| 12 | GET /api/community/posts?page=1&page_size=10 | 200 | 0 | 帖子分页数据存在 | 2034 | PASS |
| 13 | GET /api/chat/sessions | 200 | 0 | data 数组(渲染矩阵佐证 4 个真实会话) | 2037 | PASS |

### 管理线(adm02test,10 步 = 9 PASS + 1 ENV_BLOCKED)

| 步 | 端点 | HTTP | code | 关键断言 | 实测(ms) | 判定 |
|---|---|---|---|---|---|---|
| 1 | POST /api/auth/login | 200 | 0 | access_token;`data.user.role=admin` | 2436 | PASS |
| 2 | GET /api/auth/me(role 校验) | 200 | 0 | role=admin;user_id=100003 | 2069 | PASS |
| 3 | GET /api/admin/users/dashboard/metrics | 200 | 0 | 7 KPI 键:total_user_count/active_user_count_7d/new_register_count_7d/disabled_user_count/role_breakdown/register_trend_7d/avg_login_days_per_user_30d | 2405 | PASS |
| 4 | GET /api/admin/courses/series?page=1&page_size=10 | 200 | 0 | 分页壳完整 | 2044 | PASS |
| 5 | GET /api/admin/courses/series?**sale_status=off_sale**(回收站参数) | 200 | 0 | **total=62,items 全部 sale_status=off_sale** | 2035 | PASS |
| 6 | GET /api/admin/users?page=1&page_size=10 | 200 | 0 | 用户分页壳完整 | 2183 | PASS |
| 7 | GET /api/admin/questions/types | 200 | 0 | 题型列表存在 | 2059 | PASS |
| 8 | GET /api/knowledge/partitions | **500** | **50000** | message 含 `MilvusException: Fail connecting to server on 192.168.85.101:19530` → Milvus 未运行(§红项1 传导) | 5062 | **ENV_BLOCKED** |
| 9 | GET /api/mcp/servers | 200 | 0 | 服务列表存在 | 2052 | PASS |
| 10 | GET /api/mcp/call-log?page=1&page_size=10 | 200 | 0 | 调用日志存在 | 2048 | PASS |

> 只读复核数据点:回收站 62 条全 off_sale(样例 id 2716/2715 为测试残留系列);metrics 实测值 用户总数 100,034 / 7d 活跃 0 / 7d 新增 1 / 禁用 1 / 角色分布 👑5 🛠3 👩‍🏫3 🎓100,023(截图 09 佐证)。

---

## ③ 契约回归(pytest,edu-agent venv)

```
.venv/Scripts/python.exe -m pytest tests/test_course_admin.py tests/test_course_admin_json_columns.py \
  tests/test_course_admin_restore.py tests/test_task33_mcp_desc_review.py -q
→ ....sssssssssssssss.................                    [100%]
→ 21 passed, 15 skipped in 116.47s (0:01:56)   exit 0
```

0 failed;15 skipped 为既有条件跳过(与历史批次口径一致)。**契约回归绿。**

---

## ④ CDP 渲染矩阵(15 页,截图 `edu-agent/page-verify-task19/`,脚本 `scripts/verify_pages_task19.mjs` + `_retry.mjs`)

方法:CDP(Page/Runtime/Log 域)注入 `edu:auth:token`(学生页=student token,管理页=admin token,login 页=清空 storage),断言 零 console 错误 + h1 存在 + 内容高度≥视口 + 未被守卫重定向 + 截图。轮询至渲染就绪(最长 wait+18s)。

| # | 页面 | h1 | 内容/视口 | 按钮 | console 错误 | 判定 |
|---|---|---|---|---|---|---|
| 01 | login-register.html | 🌈 欢迎回来 | 864/802 | 8 | 0 | PASS |
| 02 | courses.html | 课程中心 | 2814/802 | 26 | 0 | PASS |
| 03 | course-detail.html?id=1 | 通用编程入门班·直播 | 1209/802 | 27 | 0 | PASS(截图见真实班次价格/名额/领券) |
| 04 | dashboard.html | 你好,同学 👋 | 835/802 | 5 | 0 | PASS |
| 05 | learning.html | 加载中…* | 1396/802 | 7 | 0 | PASS(*见注 1:h1=会话播放器区标题,班次选择态下未选中会话属合法;班次列表 2 条真实数据已渲染) |
| 06 | me.html | 慕剑知(用户昵称) | 2011/802 | 12 | 0 | PASS |
| 07 | achievements.html | 成就与成长 | 1590/802 | 12 | 0 | PASS |
| 08 | chat.html | 智能问答 | 802/802 | 16 | 0 | PASS(截图见真实历史会话+引用) |
| 09 | admin-dashboard.html | 平台运营总览 | 1196/802(复采) | 4 | 0 | PASS(见注 2:首采骨架屏竞态,复采 KPI 全加载) |
| 10 | admin-courses.html | 课程管理 | 802/802 | 20 | 0 | PASS |
| 11 | admin-course-detail.html?id=1 | 系列详情 | 802/802 | 21 | 0 | PASS |
| 12 | admin-users.html | 用户管理 | 824/802 | 13 | 0 | PASS |
| 13 | admin-questions.html | 题库管理 | 854/482** | 29 | 0 | PASS(见注 3) |
| 14 | admin-rag-upload.html | RAG 控制台 · 文件上传 | 1743/482** | 11 | 0 | PASS(Milvus 断链下页面本体正常,契约横幅/Tab 渲染) |
| 15 | admin-mcp.html | MCP 控制台 · 工具管理 | 1246/482** | 11 | 0 | PASS |

**汇总:15/15 PASS(0 console 错误,15 张截图齐)**

- 注 1(05-learning):页内 `<h1 id="sessionHeading">` 为会话播放器标题,仅在选中课次后填充;未选班次时停留"加载中…"是选择态的合法形态,下方"选择要继续学习的班次"列表渲染 2 个真实班次(202608期/202601期,0/28 课次)。观感问题登记为遗留观感项(见 §6)。
- 注 2(09-admin-dashboard):首采截图时 KPI 尚在骨架屏(metrics 接口 ~2.4s);以 14s 等待复采,`skeleton=0`,KPI 全真实(100,034 用户/角色分布/7d 注册趋势),截图已覆盖为加载完成态。页面自带诚实横幅:"契约缺口:订单数/营收/热门课程榜——后端当前无管理端全局聚合端点…待 task70~91 后端聚合端点后接线"(登记批判 T19-4/C-19)。mockHint 启发式命中系横幅文字"无 MOCK",非真实演示数据。
- 注 3(13~15):主跑在 13 页遭遇 `ERR_CACHE_READ_FAILURE`(复用旧 CDP 实例的陈旧 profile 缓存,浏览器环境问题非页面缺陷,该页 evaluate 因此未返回);用新 profile 新会话补跑 13/14/15,三页 0 console 错误全过。** 表为补跑会话视口 482px(默认窗口),内容高度仍≥视口,截图齐。

---

## ⑤ 强制技术批判(硬闸门)

产出(承接表见各自文档):
- `.ai-hub/plans/task19-技术批判.md`——4 条(T19-1 演示可交付度/环境单点依赖 P1、T19-2 学生端读路径性能 P1、T19-3 错误契约泄漏 P1、T19-4 双端形态债/B 批未启动 P2),批判对象=A 批重塑后整体形态,全部当日实测支撑。
- `.ai-hub/plans/task19-优化修改方案.md`——逐条承接(修改项/方案/验收指标/落点/执行顺序)。

review-gate 机验输出摘录(从 D 盘真实路径跑):

```
PASS 批判文档存在  4 条
PASS 有效批判≥3（含URL+日期）  有效 4/4
PASS 优化修改方案存在  存在
PASS tracker 已登记  含 task19
REGISTER C-16 … REGISTER C-17 … REGISTER C-18 … REGISTER C-19 …
[OK] task19 批判闸门通过 + 自动登记 4 条 / 生成任务文档 4 份 / 跳过重复 0 条
[URL 真验] 网络可用
  PASS https://supabase.com/blog/openai-embeddings-postgres-vector (200)
  PASS https://httparchive.org/reports/state-of-the-web (200)
  PASS https://docs.stripe.com/api/errors (200)
  PASS https://refine.dev/docs/ (200)
[URL 真验] 有效批判 4 条：真实对标可达 4 / 无效 0
```

登记落点:D:\.ai-hub\skills\tt\plans\critique-backlog-tracker.md 新增 C-16~C-19(⬜ 待落地),任务文档 critique-C-16..19-task.md 已生成。

---

## ⑥ A 批 DONE 判定:**带条件 DONE(演示可交付,附遗留清单)**

**达成面(全部当日独立实证)**
1. 双线 E2E:学生 13 步 + 管理 10 步 = 23 步,22 PASS + 1 ENV_BLOCKED(环境传导),0 FAIL,0 代码缺陷;
2. 契约回归:pytest 4 文件 21 passed / 15 skipped / 0 failed;
3. 渲染矩阵:15/15 页零 console 错误、真实数据渲染、截图齐;
4. 环境检查单(task18 产物)工作正常:5/8 绿,3 红项全部环境依赖且给出可执行处置指引,DEBUG advisory 安全;
5. 强制批判闸门 [OK]:4 条实证批判 + URL 机验 4/4 + tracker 自动登记 C-16~C-19。

**遗留清单(不阻塞 A 批收口,均已登记落点)**

| 遗留 | 证据 | 落点 | 级别 |
|---|---|---|---|
| L1 存储五件套未收敛,演示可用性绑 VMware/Docker 开机率 | check-demo 3 红项;knowledge/partitions ENV_BLOCKED | C 阶段 pgvector 里程碑(C-16);短期降级开关 | P1 |
| L2 series/1 详情 8.1~16.3s、rankings 4~8s,Redis 缓存未用于读路径 | E2E §2 实测 | C-17(缓存热修,建议演示前) | P1 |
| L3 依赖断链错误形态:HTTP 500+50000+内网异常串泄漏 | E2E 管理线步 8 实测报文 | C-18(50301+脱敏,小变更单) | P1 |
| L4 admin 仪表盘订单/营收/热门课程榜为契约缺口占位(页面自注待 task70~91);B0/B3 窄楔子零进展 | 渲染矩阵 09 页面横幅佐证 | C-19(B0 立即并行) | P2 |
| L5 learning 页会话区 h1 未选课时停留"加载中…"(观感,非功能) | 渲染矩阵 05 截图 | 观感项,随 B 批组件化顺带 | P3 |
| L6 环境依赖运行验证(真 Milvus/Redis 下的 RAG 上传链路)本次无法覆盖 | ENV_BLOCKED | 演示前跑 check-demo 七件套全绿后复验 | 条件 |

**DONE 条件**:演示机按 check-demo 指引拉起 VMware+Docker(①②③ 转绿)后,L6 复验 RAG 上传/检索链路;L2/L3 建议在演示窗口前热修(半天级,已有方案)。代码侧 A 批(task02-18 产物)本轮回归无缺陷,判收。

---

## 附:本验收会话足迹(供编排者审后提交)

新增(均为验收工件,非生产代码):
- `edu-agent/scripts/_verify_task19_e2e.mjs`(双线 E2E)
- `edu-agent/scripts/verify_pages_task19.mjs` + `verify_pages_task19_retry.mjs`(渲染矩阵)
- `edu-agent/page-verify-task19/*.png`(15 张)
- `.ai-hub/plans/task19-技术批判.md`、`.ai-hub/plans/task19-优化修改方案.md`、本报告

仓库工作区两处 "M"(admin-rag-upload.html / .opencode/plans/critique-backlog-tracker.md)经核查为**本会话之前**的既有工作树状态(内容 diff 为空 / mtime 2026-09-05~09-09),非本会话产生。skill 侧(D:\.ai-hub\skills\tt)tracker +4 行与 4 份任务文档由 review-gate --auto-register 产生。未执行任何 git commit。
