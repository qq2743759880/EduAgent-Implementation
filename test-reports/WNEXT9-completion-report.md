# W-NEXT-9 前端修复批 · 完成报告

> 执行者：W-NEXT-9 前端修复工程师（独立执行，单写者）｜工作区 `E:\stu\project\stu\EduAgent实施手册`
> 任务书：`.ai-hub/plans/artifacts/kickoff-WNEXT9-frontend-fixes.md`（批判源 T6-C1/C2/C3/C4 + T9-C3）
> 分支：`feature/opt-waves`｜开工 HEAD：`1b09aff1e18501402742acb9ae23d793916f1648`
> commits：`35e98d7` fix(fe-html)/WNEXT9-courses-order+spec-cleanup（19 个 public/*.html）→ `48c4c8d` chore: 移出误入版本库的 mimosa hook-state 运行时文件 → `677e763` fix(chat)/WNEXT9-T9C3-empty-answer-not-into-memory-window（chat/service.py + ai/memory/service.py）→ `94cd822` docs(reports)/WNEXT9-completion-report
> 单写者锁：`edu-agent/scripts/eval/wnext9.lock`（开工建，完工删）
> 环境：前端 3000 全程运行**未重启**；后端 8000 开工时为「已停止」（netstat 无监听）→ **启动**（非重启）；`/health` 200
> 方法：自建最小 DOM 仿真宿主（口径同 blind-t6 附录 A：按文档顺序 eval `<script>`、记录全部 fetch/console.error/未捕获异常/DOM 写入值），脚本均置于仓库外临时目录；**全程未使用 Playwright**。

---

## 1. 任务一【P0】courses.html `edu-api.js` 加载顺序修复（T6-C1）

### 修法
`<script src="/edu-api.js"></script>` 由原第 747 行（主脚本**之后**）上移至主脚本之前（现第 455 行，主脚本经注释显式标注「共享 API 客户端必须先于主脚本加载」）。未改 `edu-api.js`、未改后端。

### GWT 证据

| GWT | 证据 | 结果 |
|---|---|---|
| 字节顺序：edu-api.js 先于 refresh()/loadHero() | `src="/edu-api.js"` byte=**40790**（全文件唯一 1 处）；主脚本内真实调用 byte=refresh()**[52120, 58728, 58825, 58934, 61499]**、loadHero()**[61704, 62634]**；`function refresh` 在 52111、`function loadHero` 在 61695 | ✅ 真实调用全部晚于客户端加载（注：byte 40736/40746 是同一注释里的文字提及，非调用点） |
| 执行顺序（仿真宿主） | `scriptOrder = ["src:/edu-api.js OK","inline OK"×5]` | ✅ 客户端先于主脚本执行 |
| 首屏真实请求 `/api/series`（非 15 条硬编码） | `GET /api/series?page=1&page_size=15 → 200 (491ms)`；`/api/gamification/me/points?page=1&page_size=1 → 200`、`/api/progress/dashboard?days=14 → 200`、`/api/users/me → 200` | ✅ 4 个真实请求 |
| 首屏数据真实值 | `resText=共 <b>2628</b> 门课程`、`pgInfo=共 2628 门 · 第 1/176 页`、`cardIds=[2628,2627,2626,2625]`（真实系列 id）、`totalInRes=2628` | ✅ 与真实 `/api/series` total=2628 一致，**非** 15 条演示课程 |
| Hero 三卡位真实值 | `heroXp=351 XP`、`heroTotalXp=351`、`heroLevel=1`、`heroStreak=0` | ✅ 非 `–` 空占位 |
| 无 EAPI 时仍可降级 | `NOAPI=1`（模拟 edu-api.js 加载失败）：`scriptOrder=["empty","inline OK"×5]`、`networkCalls=[]`、`resText=共 <b>15</b> 门课程`、`cardIds=[1001,1002,1003,1004]`、Hero 保持空 | ✅ 降级分支按设计生效 |
| 无报错 | `jsErrors=[]`、`consoleErrors=[]`（两个场景均 0） | ✅ |

> T3 同型「静默降级」缺陷已消除：登录态 + EAPI 就绪时首屏走真实请求（原实现首屏恒落 `hasApi=false` 分支渲染伪造数据）。

---

## 2. 任务二【P1】规格文字泄漏系统性清理（T6-C2）

### 修法
17 页 `<title>` 改为纯用户文案（统一「<页面名> · EduAgent」，与既有干净页 courses/me/favorites 一致）；`dashboard.html` 正文 7 处可见节点（`.p-sub` / `.p-title` pill / 空态文案）去掉端点名与 Redis 术语，改用户文案（如「统计每天学习时长（分钟）」「按本周获得积分排名」「按学科归并课程完成度」）；排行榜 `ZSET` pill 删除。
**HTML 顶部注释（含契约/端点说明）按要求全部保留。**

### GWT：grep 前后对比（模式 `效果图|task\d|契约|STYLE FROZEN|/api/|ZSET`）

| 检查项 | 前 | 后 |
|---|---|---|
| `<title>` 命中页数 | **13 / 25**（GWT 模式口径） | **0 / 25** ✅ |
| `dashboard.html` 正文可见节点命中（剥注释/script/style） | **7**（含 5 处 `.p-sub` 端点 + 3 处契约缺口表述 + ZSET pill） | **0** ✅ |

> 口径说明：kickoff GWT 模式在 HEAD 上命中 13 页；批判源 blind-t6 §5.1 用更广口径（含 `taskNN 原型` / `R4` 等 task 号字样）列出 17 页。本批按批判源把 **17 页全部清理**，title 改动清单如下（17/17 页 title 实际变更，逐一核对）：

| # | 页面 | 前（HEAD） | 后 |
|---|---|---|---|
| 1 | achievements.html | 成就中心 · 效果图 v1（task53 achievements · 契约 …STYLE FROZEN） | 成就中心 · EduAgent |
| 2 | admin-course-detail.html | task57 原型 · 管理端系列详情 /admin/courses/[seriesId] | 管理端系列详情 · EduAgent |
| 3 | admin-courses-recycle-proto.html | task13 原型 · 管理端系列回收站 Tab /admin/courses（仅原型不接线） | 管理端系列回收站 · EduAgent |
| 4 | admin-courses.html | 管理端课程管理 /admin/courses（task56 原型 · task13 全量接线） | 管理端课程管理 · EduAgent |
| 5 | admin-dashboard.html | 管理端仪表盘 · 效果图 v1（task55 … STYLE FROZEN） | 管理端仪表盘 · EduAgent |
| 6 | admin-mcp.html | task62 原型 · 管理端 MCP 控制台 /admin/mcp | 管理端 MCP 控制台 · EduAgent |
| 7 | admin-questions.html | task58 原型 · 管理端题库 /admin/questions | 管理端题库 · EduAgent |
| 8 | admin-rag-upload.html | task61 原型 · 管理端 RAG 控制台 /admin/rag | 管理端 RAG 控制台 · EduAgent |
| 9 | chat.html | 智能问答 · 效果图 v2（task50-fix … STYLE FROZEN） | 智能问答 · EduAgent |
| 10 | community-post.html | 帖子详情 · 效果图 v1（task52 … STYLE FROZEN） | 帖子详情 · EduAgent |
| 11 | community.html | 社区互助 · 效果图 v2（task51 … STYLE FROZEN R2） | 社区互助 · EduAgent |
| 12 | course-detail.html | 课程详情 · 效果图（task46 契约② … STYLE FROZEN） | 课程详情 · EduAgent |
| 13 | dashboard.html | 学习仪表盘 · 效果图 v2（task43 契约⑤⑬ … 9 大学科水平条形） | 学习仪表盘 · EduAgent |
| 14 | learning.html | 学习播放 · EduAgent（task06 真实接线：班次→课次→视频→进度） | 学习播放 · EduAgent |
| 15 | my-cohorts.html | 我的班次 · 效果图（task47 契约⑪ … STYLE FROZEN） | 我的班次 · EduAgent |
| 16 | practice.html | 复习中心 · 效果图（task49 … STYLE FROZEN R4） | 复习中心 · EduAgent |
| 17 | refund.html | 退款中心 · EduAgent（task66 真实契约版） | 退款中心 · EduAgent |

### dashboard 正文改动 7 处（前 → 后）
- `统计每天学习时长，单位分钟；来自 /api/progress/dashboard.recent_days` → `统计每天学习时长（分钟）`
- `按学科归并课程完成度（契约缺口：归并端点未冻结，暂无真实数据）` → `按学科归并课程完成度`
- `学科掌握度待按新契约归并后接入，当前暂无数据` → `学科掌握度暂无数据`
- `来自 /api/users/me/learning-summary；分类占比无真实字段，不虚构饼图` → `视频观看、作业与测验的累计情况`
- 排行榜 `…本周排行榜<span class="pill">ZSET</span>` → 去 pill → `本周排行榜`
- `来自 /api/gamification/rankings?dimension=POINTS` → `按本周获得积分排名`
- `来自 /api/gamification/me/badges：最近解锁` → `最近解锁的徽章`

---

## 3. 任务三【P2】me.html 静态骨架假占位改中性（T6-C3）

### 修法
静态骨架写死的「慕剑知 / 1,280 积分 / Lv.10 学神 / 68h」改为中性占位 `—`（`#me-name`、`#st-points`、`#st-level`、`#st-time`），等级标签 `等级 · 学神` → `等级`；真实数据返回后由既有脚本正常覆盖。

### GWT 证据

| 检查项 | 结果 |
|---|---|
| `grep 慕剑知\|1,280\|Lv\.10\|学神\|68h`（me.html 全文） | 前 **4 命中**（慕剑知 / 1,280 / Lv.10 / 学神）→ 后 **0 命中** ✅ |
| 骨架中性占位存在 | `id="me-name">—`、`id="st-time">—`、`id="st-points">—`、`id="st-level">—` 全部 True ✅ |
| 有 token 时真实值覆盖 | 仿真宿主：`me-name=小柚子同学`、`st-points=351`、`st-level=Lv.1 · 萌新`、`st-time=2`、`me-goal=编程入门,升学备考` ✅ |
| 未登录不报错 | 无 token：`networkCalls=[]`、`jsErrors=[]`、`consoleErrors=[]` ✅ |

---

## 4. 任务四【P3】me.html 重复请求去重（T6-C4）

### 修法
- `/api/users/me`：删除独立「admin 角色显示管理后台入口」脚本块，其逻辑并入「对接真实后端（me 个人中心）」IIFE，**复用同一份** `/api/users/me` 结果（admin/manager 才显示入口）。
- `/api/users/me/profile`：首屏只发一次，结果存 `window.__meProfileOnce`，头像区块复用该 Promise（不再二次 GET）。

### GWT 证据：首屏请求清单（仿真宿主，有 token）

| # | 请求 | 状态 |
|---|---|---|
| 1 | `GET /api/users/me` | 200 (672ms) |
| 2 | `GET /api/users/me/learning-summary` | 200 (3100ms) |
| 3 | `GET /api/gamification/me/points` | 200 (343ms) |
| 4 | `GET /api/users/me/profile` | 200 (2325ms) |
| 5 | `GET /api/trade/orders?page=1&page_size=5` | 200 (3381ms) |
| 6 | `GET /api/coupons?status=unused&page=1&page_size=4` | 200 (2980ms) |
| 7 | `GET /api/favorites?page=1&page_size=4` | 200 (1305ms) |

**合计 7 请求 / 7 唯一**（原 9 请求 7 唯一 → 去重后 `/api/users/me` = 1 次、`/api/users/me/profile` = 1 次）✅；`jsErrors=[]`、`consoleErrors=[]`。

---

## 5. 任务五【P2】chat answer 空串根因 + 空 answer 不入记忆窗（T9-C3）

### 5.1 文件冲突裁定：**无冲突，实施**
`kickoff-WNEXT2-write-tool-online.md` 第 19 行明确：「**文件归属（仅限，与其他批互斥）**：…（**chat/service.py、memory/service.py 属 W-NEXT-9**，question_admin/router.py 属 W-NEXT-5，均禁碰）」；`kickoff-WNEXT5-three-p1.md` 第 6 行归属亦不含这两个文件；`edu-agent/scripts/eval/` 下仅有 `wnext8.lock`（与本次文件不重叠）。→ 本任务两文件归 W-NEXT-9，**按实施处理，无冲突上报**。

### 5.2 GWT① 空串根因登记（结论）
**根因 = 生成节点对「空字符串」无兜底，只对「异常」兜底；空串作为合法答案一路传到收束与记忆（degraded_reason 仍为 null）。** 代码链：

1. `app/ai/harness/sixnode.py:382-391`（graph 路径 answer 节点）：`strong` 成功即返回其返回值；仅 `except` 才降级 `fast`，两个都异常才给「抱歉…」兜底 → **若模型返回空串（非异常），`final_answer=""` 且 `degraded_reason=None` 直接返回**。
2. `app/chat/generator.py:531-535`（非流式 legacy 路径）同样：成功分支 `return answer, degraded_reason`，无空串判定。
3. `app/chat/router.py:288`（流式收束）：`answer_text = "".join(buf)` → 模型零 token 时收束得到 `""`，同样无兜底（收束本身不丢已生成 token）。
4. 空串继续流入：落库 assistant 消息 content="" → `make_stream_finalize` / 非流式尾部**照常** `enqueue_turn(..., assistant_reply="")` → 抽取照跑、记忆照写。

**live 复现（2026-09-16 01:25，真实 HTTP，8000 实例）**：`POST /api/chat`（含规则触发词）→ `HTTP 200`、`code=0`、`answer_len=469`、`degraded_reason=null`、耗时 81.8s → **本次未复现空串**。故空串为**间歇性**（模型非确定性输出），与批判源 T9 §6 实测（`answer` 空串、`degraded_reason=null`、`latency_ms=24483`、`retrieved_count=5`，记忆仍落库 4 行）不矛盾：两者共同指向「空串无兜底」这一代码事实。
> 根因**修复**（在 sixnode/generator 增加空串兜底 + degraded 标记）不在本批文件归属（`sixnode.py`/`generator.py`/`router.py` 均非 W-NEXT-9 归属，且 kickoff 任务五仅要求「登记结论」）→ 见第 6 节附带发现，建议另立 task。

### 5.3 GWT② 空 answer 不入记忆窗（实施）
两处落地（单一事实源 + 调用侧短路）：

- `app/ai/memory/service.py::enqueue_turn`（**choke point**）：`assistant_reply is not None and not str(assistant_reply).strip()` → 记 WARNING 日志后 `return 0`，整轮不入记忆窗（防抽取污染）。
- `app/chat/service.py`（非流式 `answer`、流式收束 `final_answer` 两处）：`if answer and answer.strip():` 才 `create_task(enqueue_turn(...))`，空串不再产生空跑任务。

### GWT② 验证（真实函数 + 真实入队载荷断言）

| 入参 | 返回 | 是否入队 |
|---|---|---|
| `assistant_reply=""` | 0 | 否 ✅ |
| `assistant_reply="   "`（纯空白） | 0 | 否 ✅ |
| `assistant_reply=None`（旧行为） | 1 | 是（窗口 `[user]`） |
| `assistant_reply="已为你记录目标"` | 1 | 是（窗口 `[user, assistant]`） |
| `text=None`（空窗） | 0 | 否 ✅ |

日志实测：`WARNING app.ai.memory.service:enqueue_turn:147 - [Memory] 本轮助手回复为空串，跳过入记忆窗（T9-C3，防记忆污染）`；断言 `PASS: T9-C3 空 answer 不入记忆窗 + 既有行为不变`。

### GWT③ 既有 chat/记忆测试不破坏
- `pytest tests/test_contract_task_r01.py tests/test_contract_task_r02tail.py tests/test_chat_stream_error.py tests/test_sse_envelope_contract.py tests/test_contract_task25.py -q` → **42 passed**（33.73s）
- `pytest tests/test_contract_task_r02.py tests/test_chat_delete.py -q` → **25 passed**（11.72s）
- `py_compile app/chat/service.py app/ai/memory/service.py` → OK

### 测试数据自清
live 复现探针在测试账号（`user000001`，user_id=1）写入 4 条记忆事件（id 123–126，「雅思 6.5 / Python 偏好」），已按软删（`event_type='delete'` 追加）清理：清理后该用户有效记忆数 = 1（仅剩 2026-09-15 18:57 的既有 id=109，未触碰）。探针未创建会话（`session_id=None`，无消息落库），无需会话清理。

---

## 6. 附带发现（**超出本批 GWT 范围，未擅自扩改**，建议另立 task）

1. **其余页正文可见节点仍含规格/端点字样**（本批 GWT 仅约束 `<title>` + dashboard 正文）：共 **66 处 / 14 页**，例如 `admin-mcp.html`（13 处：`契约 task33 已冻结`、`POST /api/mcp/health-scan`）、`admin-users-refine-proto.html`（11 处）、`admin-rag-upload.html`（9 处）、`practice.html`（6 处，含错误态文案 `GET /api/interactive/quiz/wrong-book 暂不可达`）、`admin-courses-recycle-proto.html`（5 处）、`admin-dashboard.html`（4 处，`契约⑤/契约缺口/待后端 task70~91`）、`admin-users.html`（4 处）、`admin-question-detail.html`（4 处）、`admin-courses.html`（3 处）、`coupons.html`（3 处）、`course-detail.html`（1 处 `HTML 效果图（task46…STYLE: candy-playful frozen）`）、`favorites.html`（1 处）、`my-cohorts.html`（1 处）、`admin-questions.html`（1 处）。建议立「正文规格文字清理」task（按页归属分批，注意部分为管理端原型页故意披露的契约缺口说明，需逐页判定是否保留）。
2. **空串答案无兜底（T9-C3 根因本体）**：`sixnode.py:382-391` / `generator.py:531-535` / `router.py:288` 三处对空串无兜底 → 用户仍可能看到**空白响应**且 `degraded_reason=null`（记忆侧本批已止血）。建议另立 task：空串（strip 后为空）→ 走既有「抱歉，AI 服务暂时不可用」兜底或规则答案，并记 `degraded_reason="llm_empty_output"`（与 `extract_llm` 的 `llm_empty_output` 口径一致）。
3. **`<title>` 口径差异登记**：kickoff GWT 模式（`效果图|task4|task5|契约|STYLE FROZEN|/api/|ZSET`）在 HEAD 命中 13/25，而批判源 blind-t6 §5.1 用更广口径列 17/25（差 4 页为 `taskNN 原型`/`task06 实接线` 类字样：admin-course-detail / admin-courses-recycle-proto / admin-mcp / admin-rag-upload / learning 中的非 `task4|task5` 项）。本批按批判源 17 页全清，`<title>` 两口径均归零。

---

## 7. 交付物与验收汇总

| 任务 | GWT | 结果 |
|---|---|---|
| 一【P0】courses 加载顺序 | 字节顺序 + 首屏真实请求/Hero 真实值 + 无 EAPI 降级 | ✅ 全通过（2628 门 / Hero 351 XP / 降级 15 门 0 请求） |
| 二【P1】规格泄漏清理 | title 命中 13→0、dashboard 正文 7→0 | ✅ 全通过（17 页 title 清单见 §2） |
| 三【P2】me 骨架中性化 | 假占位 4→0 + 真实值覆盖 | ✅ 全通过 |
| 四【P3】me 去重 | 首屏 7 请求 / 7 唯一 | ✅ 全通过 |
| 五【P2】T9-C3 | 根因登记 + 空 answer 不入窗 + 既有测试不破坏 | ✅ 全通过（42 + 25 passed） |

- 文件归属遵守：仅改 `edu-frontend/public/*.html`（19 个文件）+ `edu-agent/app/chat/service.py` + `edu-agent/app/ai/memory/service.py`（任务五，W-NEXT-2 已明示归属 W-NEXT-9）+ 本报告；**未改** `edu-api.js` / `edu-guard.js` / 契约 / 其他后端域文件 / `tests/`。
- 未重启前端 3000 与后端 8000（后端开工时为停止态，本次为启动）。