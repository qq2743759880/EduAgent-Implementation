# 功能测试报告 Task01

## 第 1 次测试

### 判定：PASS

### 测试环境

- 后端 FastAPI http://127.0.0.1:8000（/health 200，运行中）
- 前端 Next.js dev http://localhost:3000（200，运行中）
- 测试账号：task01test / Test@123456（student）
- 测试时间：2026-08-12

### 验收标准逐条验证

| # | 验收标准（Given/When/Then） | 验证方式 | 结果 |
|---|------------------------------|----------|------|
| 1 | /community 渲染热门帖列表（GET /api/community/posts?sort=HOT）+ 4 学科分版 Tab（english/math/programming/general），无 MOCK | 冒烟：标题「学习社区」可见、tablist 5 个（全部+4 学科）、article 10 条真实渲染；代码审查：queryFn 直连 listPosts 无 MOCK | ✅ 满足 |
| 2 | 填写标题+Markdown 内容 → POST /api/community/posts → 跳转详情页且列表页可见新帖，积分 +5 | 契约脚本：发帖返回 post_id 且 points_awarded=5；PostEditor onSuccess toast +5 → router.push 详情；invalidateQueries 后列表可见（冒烟 article=10 含新帖）；积分流水实测 POST_CREATE delta=5 | ✅ 满足 |
| 3 | 详情页点赞/收藏/回帖 → 计数即时更新（软切换），回帖返回 points:2 | 契约脚本：like active:true→false（软切换）、favorite true；回帖返回 points=2；ReactButtons 以服务端 total_count 回填（单测覆盖）；积分流水实测 COMMENT_CREATE delta=2 | ✅ 满足 |
| 4 | /achievements 徽章（8 枚，未解锁置灰 + next_milestone 进度）、积分流水分页、日/周/月/总排行榜，全部来自真实 API | 冒烟：徽章卡片 aria-label 计数 =8、积分总览可见、排行 4 Tab；契约脚本：BadgeListResp（unlocked_count/next_milestone/progress_pct）、PointsResp（level_progress_pct/recent_logs）、RankingResp（top/my_rank/is_myself）字段全部对齐；grep 确认无 MOCK | ✅ 满足 |
| 5 | 侧边栏出现「社区」「成就中心」2 个新入口 | 冒烟：a[href="/community"]、a[href="/achievements"] 可见；layout.tsx 导航 8 项含两项（L88-98） | ✅ 满足 |

### 前端单元测试（vitest）

`npx vitest run`：5 个测试文件、30 用例全部通过（community.test.ts 12 / PostCard 5 / ReactButtons 5 / BadgeWall 4 / RankingTabs 4）。覆盖 API 参数拼装、写操作失败上抛（不吞错）、点赞计数即时更新、徽章解锁/置灰/进度、排行 Tab 切换请求。

### 契约打靶（verify-task01-contract.mjs）

19 项中 18 项通过、1 项失败——`积分 = 7（发帖5+回帖2）| 实际 14`。经独立核验：该断言假设全新账号，而账号此前已跑过一轮脚本（流水 4 条 = 2×POST_CREATE +5 + 2×COMMENT_CREATE +2 = 14），**+5/+2 契约本身正确**（delta 实测 +5、+2）。属测试脚本非幂等缺陷（重跑叠加积分），非产品缺陷，不构成 FAIL。

### 浏览器冒烟（smoke-task01-ui.mjs）

13/13 全部通过（社区页/分版 Tab/热门帖/侧边栏入口/发帖编辑器/详情页/点赞收藏/回帖表单/成就页 8 徽章/积分总览/排行 Tab）。

### 静态校验

- `npx tsc --noEmit` exit 0。
- grep `MOCK_`：task01 范围（community/achievements 页面与组件）0 命中；命中项全部位于 dashboard/page.tsx（task06 范围，不属于本任务）。

### 架构薄弱点验证结果

| # | 薄弱点 | 是否命中 | 说明 |
|---|--------|---------|------|
| 2 | 前端静默吞错（R-7） | ✅ 未命中 | 发帖失败链：PostEditor useMutation 无 onError 吞错 → 传播至 QueryClient MutationCache 全局 onError → toast.error（401/403 走 auth-client 登出回跳，不吞）；community.ts 写操作零 catch 兜底；列表失败渲染错误态 ErrorState（不渲染假列表）。ReactButtons 失败单测证实计数不更新。CommentSection 评论点赞直接调用分支显式 toast + console.error |
| 5 | 文档口径漂移（R-9） | ⚠️ 部分命中 | 前端类型按后端 schemas.py 实证口径（post_id/summary/content_md、unlocked_count/badge_name、recent_logs、top/is_myself）对齐，非 PRD 旧口径；仅 verify-task01-contract.mjs「积分=7」断言按 PRD 理想值写死，已在上表核验为脚本非幂等，与产品无关 |

### 备注

- verify-task01-contract.mjs 的非幂等断言（积分绝对值 =7）建议改为「较运行前新增 7 分」或相对断言，避免重跑误报——不阻塞验收，记录供 sd-dev 参考。

---

## 第 2 次测试（重测·修正轮回归）

### 判定：PASS

| # | 上次问题（对抗问题 4） | 当前状态 |
|---|------------------------|----------|
| 1 | ReactButtons 闭包陈旧值整体回写（`ReactButtons.tsx:56-76` + `[postId]/page.tsx:133-136`） | ✅ 已修复 |

### 回归验证明细

1. **全量单测回归**：`cd edu-frontend && npx vitest run` → **5 文件 31 用例全部通过**（community.test.ts 12 / PostCard 5 / BadgeWall 4 / RankingTabs 4 / ReactButtons 6），与修复预期一致（ReactButtons 由 5 增至 6 用例）。
2. **ReactButtons 定向更新逻辑**（代码审查 + 定向回归用例）：
   - 组件侧 `ReactButtons.tsx:53-63`：`likeMutation` onSuccess 仅回写 `onCountsChange?.("like", {active, count})`，`favMutation` 仅回写 `"favorite"`；回调不引用兄弟字段闭包值。
   - 消费端 `[postId]/page.tsx:133-140`：按 `target` 分支定向 `setLikeOverride` / `setFavOverride`，互不触碰。
   - 定向回归用例 `ReactButtons.test.tsx:78-104`：点赞成功只调用 `onCountsChange("like", {active:true, count:9})` 且 `toHaveBeenCalledTimes(1)`，无整体覆盖（陈旧值回写路径已消除）。
3. **处置结论确认**：`test-reports/task01-challenge.md` 已追加「处置结论（task01 修正轮）」段落（L74-86），问题 4 标记「已修复（本轮）」，严重问题 1/2/3 判定为既有后端 DEBUG 设计（不修，记入文档，移交生产化治理 explore R-3）。
4. **其余验收项无回归**：本次改动范围仅 ReactButtons.tsx + `[postId]/page.tsx` 消费端 + ReactButtons.test.tsx（+1 用例），未触碰 community.test.ts / PostCard / BadgeWall / RankingTabs / PostEditor / BoardTabs / CommentSection / layout；全量单测覆盖 API 参数拼装、写失败上抛、徽章解锁/置灰、排行切换均通过；`npx tsc --noEmit` exit 0（onCountsChange 新签名全工程类型一致）。上一轮已 PASS 的验收标准 1-5 无回归。
