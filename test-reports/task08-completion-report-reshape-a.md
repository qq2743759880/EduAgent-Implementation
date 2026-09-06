# task08 完成报告 —— community.html + community-post.html 社区（reshape-a）

- 执行 agent：fe-html 接线工程师（独立开发）
- 日期：2026-09-06
- 改动文件：`edu-frontend/public/community.html`、`edu-frontend/public/community-post.html`（仅此两个；后端/contracts/edu-api.js 零改动）
- GWT 来源：`.ai-hub/plans/dev-plan-reshape-a.md` task08「发帖/回帖/反应全真实，分页壳一致；写路径漂移按实测回填走变更单（决策点④）」；契约权威 `contracts/reshape-a.json`（hash 30aeddbe）
- 前置说明：列表/详情主链路 task118 已接；本任务按派单补全 ①pageId 取参 ②评论 ③反应实测 ④三态/分页齐全

---

## 1. curl 实测证据（2026-09-06，学生 user000001 真实 token）

### 1.1 列表 GET /api/community/posts?page=1&page_size=3&sort=NEW
```
data keys: [items, mine_total_posts, page, page_size, total]   total:96 page:1 page_size:3
item keys: [author_id,author_name,board_code,comment_count,created_at,favorite_count,hot_score,
            is_locked,is_pinned,like_count,mine_react_favorite,mine_react_like,post_id,summary,tags,
            title,updated_at,view_count]
```
→ 裸分页壳（无 code 壳内嵌套）；`mine_react_like/mine_react_favorite` 列表即返回（task118 注释「列表不返回 is_liked→localStorage 回补」已过时——**漂移登记①**）。

### 1.2 详情/评论/反应
```
GET  /posts/74        → PostDetail + content_md（view_count 自增：143→145，每次详情 +1 属预期）
GET  /posts/74/comments?page=1&page_size=2 → {total,page,page_size,items}
POST /posts/74/like   → {"target_type":"POST","target_id":74,"react_type":"LIKE","active":true,"total_count":1,"points_awarded":0}
POST /posts/74/like(再) → active:false,total_count:0（toggle 语义确认，DB 状态已还原）
POST /posts/74/favorite ×2 → 同构 ReactToggleResp
POST /comments/52/like ×2 → {"target_type":"COMMENT",...}（同构）
POST /posts/999999          → 404 {"code":"40410","message":"帖子不存在"}
POST /posts/90(锁定帖)/comments → 403 {"code":"40310","message":"帖子已锁定，不可评论"}
POST /comments/999999/like  → 404 {"code":"40411","message":"评论不存在"}
POST /posts（发帖,UTF-8 body） → {"post_id":97,"points_awarded":5,"badge_unlocked":[]}
POST /posts/97/comments      → {"comment_id":52,"created_at":"2026-09-06T17:26:19","points":2}
```
→ 错误码 code 为字符串（"40410"/"40310"）——**漂移登记②**。

### 1.3 写路径漂移实测（决策点④要求，后端数据一致性缺陷，前端不可修，建议变更单）

| # | 漂移 | 实测证据 |
|---|---|---|
| D3 | **post.comment_count ≠ 评论端点 total（含软删评论）**：帖 74 count=2/total=0；帖 48 count=3/total=1；扫 15 帖全部不符 | §1.2 + 批量扫描 |
| D4 | **post.like_count/favorite_count ≠ 在线 react 总数（含软删 react）**：帖 74 like_count=5，toggle 后服务端 total_count=0→1→0 | §1.2 + toggle 后 GET 复测 |
| D5 | 评论排序 `parent_id IS NULL DESC, created_at ASC`（父帖优先+时间正序）→ 新评论出现在列表尾部而非头部 | service.py + /comments 实测 |

前端处置：D3→评论计数一律以评论端点 `total` 为准；D4→初始展示行计数，toggle 后以响应 `total_count`（在线真值）回填，数字回落为诚实表现；D5→评论发布成功后跳末页（让用户看到自己的评论）。

## 2. 补全内容（对照派单 4 项）

### community.html
1. **真实分页**：`page/page_size=10` 动态 pager（‹/页码窗 5/›/共 N 条），prev/next 边界 disabled；筛选/排序/搜索切换均回第 1 页。
2. **三态齐全**：loading 骨架（.sk 复用）→ success/empty（暂无帖子）；失败渲染 `role=alert` 错误态 + 🔄 重试按钮（原 `.catch(function(){})` 静默吞 → 登录态空白页不诚实）。
3. **mine_total_posts** 接「🎒 我的帖子」徽标（原静态假值 3；实测学生=47）。
4. **移除 prependPost MOCK**：发帖成功后回第 1 页真实重载（原用 0 计数伪造卡片且 HOT 排序下位置失真），flashNote 带真实 `points_awarded`（实测发帖 +5 积分）。

### community-post.html
1. **取参统一 `EAPI.pageId("post_id")`**（替换裸 URLSearchParams；全页无 match 取参——教训 9）。
2. **评论列表真实分页**：page_size=10 动态 pager；计数以端点 total 为准（D3）；评论加载失败渲染错误态+重试。
3. **反应真实端点**：帖子 like/favorite、评论 like 全走 toggle 响应 `{active,total_count}`，aria-pressed 同步（CDP 实证）；bindReact 增加无 token 拦截跳登录（与列表页一致）。
4. **三态**：真实 loading 骨架（原静态 visibility:hidden 白屏）；**404 → 「帖子不存在」+「← 返回列表」CTA**（GWT③，原仅行内 flash，页面停留假空白）；其他错误 → 可重试错误态；评论发布成功跳末页 + 「+2 积分」行内反馈（实测 points=2）。
5. 详情 meta 补 view_count 真实渲染（原静态 1283）。

## 3. 独立实证（CDP，非 Playwright；脚本 `test-reports/_task08_cdp_verify.mjs`，结果 `task08-cdp-result.json`）

headless Chrome（CDP 9230）+ 学生 token 真实加载，**22/22 全绿（ALL PASS）**：

**community.html（10 项）**：真实列表 10 卡｜pager 共 97 条｜我的帖子=47（真实字段）｜next→p2（首帖 id 变 48→16）→prev 回 p1｜英语版块筛选 5 卡全=英语且回 p1｜搜索无结果→诚实空态+pager 隐藏｜BASE 不可达→错误态 role=alert｜重试恢复 10 卡｜列表点赞 toggle（aria-pressed false→true）+还原｜**点赞计数 7→3 实录 D4 漂移（行计数→在线真值回落）**。

**community-post.html（11 项）**：详情标题/正文渲染｜评论总数=端点 total（14 条，不采信 comment_count——D3）｜page1=10 条｜pager 第 2 页=4 条（14-10 动态吻合）｜评论点赞 toggle + aria-pressed + 还原｜帖子点赞 toggle + 还原｜UI 发评论→跳末页(15 条/pg2)→「评论成功（+2 积分）」｜post_id=999999→「帖子不存在」+返回列表 CTA。

**共性**：全程无真实 JS 异常（3 条预期日志：1×错误态测试网络失败、2×404 页导航）；8 个内联 script 全过 `node --check`。

**测试脚本缺陷记录**（诚实登记，非页面缺陷）：期间 2 轮 FAIL 均为验证脚本自身问题——①CDP Runtime.evaluate 全局共享作用域，`const i` 二次声明抛 SyntaxError（改 IIFE 包裹）；②测试未清搜索关键词→重试后是**正确的**诚实空态（误判为恢复失败）；③评论 fixture 计数跨次运行漂移（改动态补足+动态断言）。页面代码零回滚。

## 4. 资产消费证据

- `edu-api.js`（禁改未改）：EAPI.get/post、**EAPI.pageId**（详情取参）、EAPI.buildLoginUrl（未登录拦截）、401 单飞 refresh、全局错误 toast。
- 既有 CSS 资产复用：`.sk` 骨架/`.state` 四态/`.pager-btn`/`.retry`/`.back-list`/`.c-like.on`——零新增样式块（只修不增）。
- 糖果 tokens 未动，视觉冻结基线无 diff（纯 JS 接线）。

## 5. 批判承接核对

- 派单③「页面注释与后端有漂移风险，以实测为准并在报告登记」→ 已登记 5 条（§1.3 + §1.1/§1.2），其中 task118 注释漂移①已按实测回填（优先 mine_react_like）。
- 决策点④「写路径漂移按实测回填走变更单」→ D3/D4/D5 属后端数据/契约缺陷，本任务只做前端诚实降级，**变更单建议已列入 §6**。
- 教训 2（无 Playwright，CDP+curl 实证）/教训 9（禁 match 取参）/教训 8（实测优先）逐条核对遵守。

## 6. 遗留与变更单建议

1. **D3/D4（计数含软删）**：建议 `community_post.comment_count/like_count/favorite_count` 改为在线计数（或接口返回 live 计数），否则详情页点赞后数字回落必被演示质疑。
2. **D5（评论排序）**：如需「新评论在前」体验需契约变更（当前前端以跳末页承接）。
3. 测试残留登记：自有实测帖 `post_id=97`（「task08 契约实测帖 20260906」）+ 其下 15 条标注「task08…实测（可忽略）」评论——社区无删除端点，同 task118 残留先例；点赞/收藏/评论赞均已 toggle 还原（各响应 total_count=0 复核）。

## 7. 三视角自检

- **Eng**：分页器纯函数式渲染（窗口计算边界安全 min/max）；事件绑定容器委托+dataset.busy 防抖；无全局污染（未重定义 $/renderSides）；`node --check` 8/8。
- **Data/契约**：所有写路径（发帖/评论/点赞/收藏/评论赞）均有 curl 200 实证；分页壳 `{total,page,page_size,items}` 与契约一致；未造任何 MOCK（反移除了 task118 的 prependPost 伪卡片）。
- **UX/演示**：三态×两页全齐（loading/empty/error+重试/404 CTA）；操作反馈可见（积分 flash/aria-pressed/计数即时回填）；演示故事线（浏览列表→筛选→翻页→进详情→点赞→评论→翻页看新评论→404 容错）CDP 全链实证可跑。
