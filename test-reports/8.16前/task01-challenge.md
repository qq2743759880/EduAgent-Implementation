# 对抗性测试报告 Task01

> 被测范围：G1 用户端社区 & 成就中心（前端 `edu-frontend/src/lib/api/community.ts`、`src/components/community/*`、`src/components/achievement/*`、`src/app/(user)/community/**`、`src/app/(user)/achievements/page.tsx`、`src/app/(user)/layout.tsx`）
> 攻击基准：`dev-plan.md` task01 验收标准 · `design-guide.md` §7 薄弱点 1/2/5 · `.claude/specs/explore-architecture.md` R-1~R-10
> 实测环境：后端 `http://127.0.0.1:8000` 运行中（`/health` 200），`edu-agent/.env` 实测 `DEBUG=true`（薄弱点 1 成立前提）

---

## 第 1 次测试

### 判定：FAIL

### 攻击结果汇总

| # | 维度 | 严重度 | 位置 | 攻击用例 | 实测结果 | 可能后果 | 建议 |
|---|------|--------|------|----------|----------|---------|------|
| 1 | 架构级（薄弱点 1：DEBUG 鉴权绕过） | 严重 | `edu-agent/app/auth/dependencies.py:80-127`（`.env DEBUG=true`）；design-guide §4.1 契约「全部路由 require_login，未登录访问 401」 | 无 Authorization 头直接 `GET /api/community/posts?sort=HOT`、`GET /api/gamification/me/badges` | **200 放行**（返回 52 帖 / 8 徽章数据），非契约要求的 401 | 未登录用户（或任何网络侧攻击者）可绕过登录读取/篡改社区与成就数据；task01 验收标准「未登录 401 守卫」API 层未达成（前端 ProtectedRoute 守卫正常，但后端无 401） | 生产部署强制 `DEBUG=false` + 部署校验脚本（explore R-3 建议）；`get_current_user` 在 DEBUG 下对社区/成就写接口至少保持身份隔离 |
| 2 | 架构级（薄弱点 1：跨用户数据读取） | 严重 | 同上；`GET /api/gamification/me/points`、`/me/badges` | `X-Force-Role: student` + `X-Force-User-Id: 2` 伪装他人 | **伪冒成功**：读到 uid=2 真实积分 3150 分 / 34 条流水（uid=1 视角仅 157 分/4 条）、徽章 3/8（uid=1 为 2/8），数据随 User-Id 变化 | 任何人可枚举 `X-Force-User-Id` 读取任意学员积分/流水/徽章进度，用户隐私泄漏；`mine_react_like/mine_react_favorite` 同样以被伪冒用户视角返回 | 同上：DEBUG 特性禁止进生产；或对 `me/*` 类接口强制真实 Token（去掉 DEBUG 兜底） |
| 3 | 架构级（薄弱点 1 延伸） | 严重 | `dependencies.py:117-127` | 无任何头直接 `GET /api/admin/users`、`/api/mcp/servers` | **200 放行**（虚拟 ADMIN） | 管理端 46 端点 + MCP 工具执行全部裸奔，任一局域网客户端可拉取用户列表/MCP 服务器配置（归属 task02-04 范围，但同根因，本轮一并记录） | 部署检查 + 敏感接口二次鉴权（同 #1） |
| 4 | 验收标准盲区 | 轻微 | `src/components/community/ReactButtons.tsx:56-76` + `[postId]/page.tsx:133-136` | 点赞成功回调闭包捕获本次 render 的 fav props 并整体写回两个 override | 无实测异常（按钮 `disabled={busy}` 阻止并行、staleTime 30s 兜底），代码审查发现潜在陈旧值回写路径 | 极端时序下收藏计数短暂回显旧值（软切换以服务端响应为准，最终一致，影响可忽略） | 可改为仅回写被操作项，或 onCountsChange 按 target 定向更新；非阻塞 |
| 5 | 边界攻击 | 轻微 | `router.py:26` `page: int = Query(ge=1)` | `GET /api/community/posts?page=99999` | **200 空列表**（total=52, items=0），非 404/400 | 无实际影响：前端 PaginationBar 以 totalPages 封顶，UI 不可达；仅 API 直连时返回空页 | 可选：page 超过 total_pages 时返回 422 或归一化，非阻塞 |

### 薄弱点核查清单

| design-guide 薄弱点 | 攻击结论 | 防御证据 / 反证 | 结论 |
|---|---|---|---|
| 1 DEBUG 鉴权绕过（`dependencies.py:80-127`） | 攻击成功 | 反证：无头 200、X-Force-User-Id 跨用户读取成功（实测 uid=2 数据）；前端侧 ProtectedRoute（`protected-route.tsx:52-60`）守卫正常，未登录被重定向登录页，前端不背锅但 API 契约 401 未达成 | **未防御**（task01 未引入，属既有环境+后端问题，红线 1 禁止本轮改后端；按对抗判定仍计 FAIL 并上报） |
| 2 前端静默吞错（R-7） | 攻击未成功 | `community.ts` 全文件无 try/catch（grep 仅注释）；QueryClient 全局 QueryCache/MutationCache onError → toast（`query-client.ts:8-24,47-52`）；CommentSection 点赞显式 catch → toast + console.error（`CommentSection.tsx:166-170`）；列表三态 loading/error/empty（`community/page.tsx:89-106`）；发帖失败不跳转（`PostEditor.tsx:91-100`） | **已防御** |
| 5 文档口径漂移（R-9） | 攻击未成功 | 前端 10 个调用路径与后端 router 逐一核对全对齐（posts/详情/like/favorite/comments/comment-like/badges/points/rankings）；TS 类型与后端 schemas 字段逐项一致（PostSummary↔PostListItem、RankingResponse↔RankingResp、BadgeListResponse↔BadgeListResp 等）；rankings 参数 `scope=DAILY\|WEEKLY\|MONTHLY\|ALL_TIME`、`dimension=POINTS\|STUDY_MIN\|BADGE_COUNT`、`top_n=20` 与后端 pattern 完全匹配；前端未调用打靶入口 `/me/award`（grep 零命中） | **已防御**（除薄弱点 1 造成的 401 契约违背外） |

### 各攻击用例实测明细（附原始结果）

**A. 社区/成就列表（无 Authorization 头）**
- `GET /api/community/posts?sort=HOT&page=1&page_size=3` → **200**，`total=52`，返回 52 帖真实数据
- `GET /api/gamification/me/badges` → **200**，`{total:8, unlocked_count:0, items:[BDG-STUDY-1H(progress 150/60→100%), …]}`
- 预期（design-guide §4.1）：未登录访问 → 401；实测 200，**契约违背**

**B. 跨用户数据读取（X-Force 头）**
- `X-Force-User-Id: 2` 单独使用（无 X-Force-Role）→ 不生效，回落虚拟 admin（uid=1）——DEBUG 特性细节：force 分支仅在 `X-Force-Role` 有效时进入（`dependencies.py:81`），且角色枚举值区分大小写（`UserRole.STUDENT="student"`，`schemas.py:30`）
- `X-Force-Role: student` + `X-Force-User-Id: 2` → **伪冒生效**：`me/points` 返回 `user_id=2, points=3150, logs_total=34`；`me/badges` 返回 `unlocked=3/8`。与 uid=1 视角（157 分/4 条/2 徽章）数据差异显著，**跨用户读取成功**

**C. 管理端裸奔（同根因）**
- 无头 `GET /api/admin/users?page=1&page_size=1` → **200**
- 无头 `GET /api/mcp/servers` → **200**

**D. 边界校验（全部符合预期）**
- `board_code=hacker` → **422**（router 显式校验，`community/router.py:29-30`）
- 发帖空标题 → **422**；发帖 20001 字 → **422**（`PostCreate` min2/max20000）
- 回帖空内容 → **422**（`CommentCreate` min_length=1）
- `rankings?scope=YEARLY` → **422**；`top_n=2`（ge=3）→ **422**
- 帖子 999999 详情 → **404**（`{detail:"帖子不存在"}`）
- `page=99999` → **200 空列表**（轻微，见问题 5）

**E. 积分/徽章一致性（发帖 +5 / 回帖 +2 链路实证）**
- 发帖 `POST /api/community/posts` → `{post_id:54, points_awarded:5, badge_unlocked:["BDG-STUDY-1H","BDG-COMMUNITY-STAR"]}`；随后的 `me/points` 流水与 `user_point_log` 完全一致：
  `POST_CREATE +5 balance=5` → `BADGE_BONUS +50 balance=55`（BDG-STUDY-1H）→ `BADGE_BONUS +100 balance=155`（BDG-COMMUNITY-STAR）→ `COMMENT_CREATE +2 balance=157`；`total_points=157` 与 `balance_after=157` 一致
- 回帖 → `{comment_id:11, points:2}` ✅ 与前端 `CreateCommentResponse.points` 契约一致
- 点赞 3 连击 → `active:true/total:1 → false/total:0 → true/total:1`，**重复 toggle 幂等**，服务端软切换（yn=0/1）✅
- 发帖后 `me/badges` → `unlocked_count=2/8`，徽章解锁计数与 items 中 unlocked=true 条目数一致 ✅
- `rankings?scope=ALL_TIME&dimension=BADGE_COUNT&top_n=20` → **200**，`source=LIVE_CALC`（快照降级实时计算，符合 §3.3 契约）

**F. 前端侧核查（静态）**
- `ProtectedRoute` 包裹 community/achievements 两页（未登录 → toast + 重定向 /login?redirect=…）✅ 前端 401 守卫存在
- `(user)/layout.tsx:88-97` 已新增「社区」「成就中心」2 个导航入口 ✅
- 全目录 grep：community/achievement 组件**零 MOCK**、`community.ts` **零 catch 吞错**、前端**零调用 `/me/award`** ✅
- XSS 面：详情/评论 Markdown 渲染用 ReactMarkdown 且未启用 rehypeRaw（HTML 默认转义）✅

### 判定依据

- **FAIL**：薄弱点 1 攻击成功且可被实际利用（未登录 API 放行 + X-Force-User-Id 跨用户读取隐私数据），design-guide §4.1「未登录访问 401」契约未达成，task01 验收标准「未登录访问是否 401 守卫」的 API 层未达标。该缺陷由既有环境（`.env DEBUG=true`）+ 后端 DEBUG 鉴权设计所致，非 task01 前端代码引入；前端侧守卫与错误处理均正确（薄弱点 2/5 已防御）。但按「存在可被利用的架构缺陷即 FAIL」的对抗判定标准，本任务判定为 FAIL 并上报，供主 Agent 决策（建议纳入 task05 联调或独立安全任务修复）。

---

## 处置结论（task01 修正轮）

> 记录对抗测试发现问题的最终处置，供追溯。

| # | 问题 | 处置 | 说明 |
|---|------|------|------|
| 1 | DEBUG 鉴权绕过（`dependencies.py:80-127`，`.env DEBUG=true`） | **不修（记入文档，不改后端）** | 属后端**既有 DEBUG 设计**（无 Token 虚拟 ADMIN + X-Force 头伪冒），非 task01 引入；本轮 dev-plan/design-guide 红线明确"不改后端既有 RBAC 策略"，且所有既有 `*_hit.py` 打靶脚本依赖 DEBUG 免登录。该问题为**生产化治理项**（explore R-3）：上线前必须 `.env DEBUG=false` + 部署校验脚本（校验未登录访问受保护 API 返回 401）。不属于本轮 6 个前端 task 的引入缺陷。 |
| 2 | X-Force-User-Id 跨用户读取（`me/points`、`me/badges` 等，同根因 #1） | **不修（记入文档，不改后端）** | 同 #1：DEBUG 特性禁止进生产；生产化治理项（explore R-3）。 |
| 3 | 管理端裸奔（`/api/admin/*`、`/api/mcp/*` 无头 200，同根因 #1，归属 task02-04 范围） | **不修（记入文档，不改后端）** | 同根因 #1：上线前部署校验脚本须覆盖 `/api/admin/*`、`/api/mcp/*` 未登录 401 校验；同 explore R-3 生产化治理项。 |
| 4 | ReactButtons 闭包陈旧值回写（`ReactButtons.tsx:56-76` + `[postId]/page.tsx:133-136`） | **已修复（本轮）** | 改为 `onCountsChange(target, next)` 按 target 定向回写：like 成功只回写 like 项、favorite 成功只回写 favorite 项，回调不再引用兄弟字段的本次 render 闭包值（陈旧值回写路径消除）。同步更新消费端 `[postId]/page.tsx` 与 `ReactButtons.test.tsx`（新增定向更新回归用例）。`cd edu-frontend && npx vitest run` 全量 5 文件 31 用例通过，`npx tsc --noEmit` 无类型错误。 |
| 5 | `page=99999` 返回 200 空列表（`router.py:26`） | **不修（记入文档）** | 前端 PaginationBar 已以 totalPages 封顶，UI 不可达；后端行为可接受（总页数外返回空页非错误），不改。 |

**结论**：task01 范围内仅轻微问题 4 需修复且已完成；严重问题 1/2/3 为既有后端 DEBUG 设计的生产化治理项（explore R-3），不属本轮 6 个前端 task 引入缺陷，按红线不改后端，移交生产化治理跟进。
