# task118 — community 交互闭环

- 域：FE ｜ 平台：trae ｜ 波次：W3 ｜ 依赖：task101
- 文件：`community.html`、`community-post.html`

## 目标
社区从"只读 + prompt() 发帖"升级为真实互动闭环：点赞、评论、版块联动。

## 证据
- audit §四-4：community-post.html:314 点赞仅 demo toggle；评论发布（cmtSubmit L413）不发任何请求。
- audit §P2-16：发帖用 `prompt()` 且 board_code 硬编码 "general"（版块 chips 纯视觉）；community-post 依赖 `?post_id=` 但站内无静态链接（task110 已补列表链接）。
- 后端契约（community/router.py）：`POST posts/{id}/like`（点赞/取消）、`POST posts/{id}/comments`、`GET comments`、`POST comments/{id}/like`、`PATCH posts/{id}`；PostCreate.board_code ∈ english/math/programming/general。

## 改动点
1. 发帖弹窗化（替换 prompt()）：标题/版块（chips 联动 board_code）/内容/标签（≤8）；成功后列表头部插入。
2. 列表点赞按钮接 `POST posts/{id}/like`（乐观更新 + 失败回滚）；已点赞态刷新后保持（按返回 like_count/is_liked 实测字段）。
3. 详情页评论发布接 `POST comments`；评论列表渲染 author/content/时间；评论点赞接 `POST comments/{id}/like`。
4. 版块 chips 过滤接 `GET posts?board=xxx`（实测 query 参数名）。
5. 未登录点互动按钮 → 跳登录（带 redirect），不发无效请求。

## GWT 验收
- Given student token，When 发帖（选"编程"版块），Then 列表新帖 board 正确、DB posts 表有记录；When 评论该帖，Then 详情页评论数 +1 且刷新后仍在。
- When 点赞/再点赞，Then like_count +1/-1 且刷新后状态持久。
- When 未登录点赞，Then 跳登录页。
- 机验：`grep -c "prompt(" community*.html` = 0；发帖 board_code 不再硬编码（grep "general" 仅作 chips 默认值出现一次以内）。

## 风险
- like 状态字段（是否返回 is_liked）需实测；若无，前端用 localStorage 记本人点赞态并在契约注释标注缺口（不阻塞）。
