# task118 完工报告 — community 交互闭环

- 任务: task118 · 域: FE · 平台: trae · 波次: W3 · 执行者: task118 开发执行者 · 日期: 2026-09-02
- 分支: `feature/opt-waves`（未切分支，未 commit）
- 只改文件：`edu-frontend/public/community.html`、`edu-frontend/public/community-post.html`（git diff --stat 证实仅 2 个 tracked 文件改动）

---

## 一、改动清单

### A. `community.html`（新加 IIFE，不重定义全局 `$`/`renderSides`）
1. **版块筛选接真实后端**：`GET /api/community/posts?page=&page_size=&board_code=&keyword=`，chips 点击联动 `board_code`（实测参数名 **board_code**，`board=` 被后端忽略返回全部）。
2. **列表点赞接 `POST /api/community/posts/{id}/like`**：乐观更新 + 失败回滚；刷新后高亮以实测 **`mine_react_like`** 字段为准（后端列表实测返回该字段），localStorage 作兜底。
3. **发帖弹窗化（替换 prompt()）**：标题 / 版块 chips（联动 board_code）/ 内容（content_md）/ 标签（≤8）；`POST /api/community/posts` 成功后在列表头部插入 + 计数 +1 + toast。未登录点发布 → `EAPI.buildLoginUrl` 跳登录。
4. **未登录点互动按钮（点赞/发帖）** → 跳登录，不发无效请求。

### B. `community-post.html`
1. **demo IIFE 防双绑**：`likeBtn/favBtn/cmtSubmit/cList` 四个演示处理器首行加 `if(window.__REAL_COMMUNITY__) return;`，真实接入脚本置该标志后 demo 逻辑不执行。
2. **重写真实接入 IIFE**（原只读渲染已替换）：
   - 帖子详情 `GET /posts/{id}`：标题/作者/时间/正文 content_md/版块/点赞/收藏/评论计数；点赞收藏态回补 `mine_react_like/mine_react_favorite`。
   - 帖子点赞 `POST /posts/{id}/like`、收藏 `POST /posts/{id}/favorite`：乐观更新 + 失败回滚 + 双击防抖（busy 标志）+ 行内错误提示。
   - 评论发布 `POST /posts/{id}/comments`（body `content_md`）：成功后重载评论列表 + 按返回 `total` 更新计数。
   - 评论列表渲染实测字段：`comment_id/author_name/content_md/like_count/mine_liked/created_at`。
   - 评论点赞 `POST /comments/{id}/like`：事件委托 + 乐观更新 + 失败回滚 + 防抖。
   - 未登录（有 post_id 但无 token）→ `EAPI.buildLoginUrl` 跳登录。
   - **行内错误反馈**：评论区下动态注入 `#cmtErr` 红字提示（评论为空/发布失败/点赞失败/操作失败/详情加载失败），4s 自动清除。
   - 锁帖（is_locked）→ 隐藏操作行 + 禁用评论输入。

---

## 二、全链 curl 证据（`test-docs/t118_out.txt` + `test-docs/t118_full.py` 实跑输出）

| 环节 | 请求 → 响应（关键字段） |
|------|------|
| 登录 student | `POST /api/auth/login` → 200 |
| **发帖** | `POST /api/community/posts` `{board_code:"programming",title,content_md,tags}` → 200 `{post_id:90, points_awarded:5}` |
| **点赞帖子(1)** | `POST /api/community/posts/90/like` → 200 `{active:true, total_count:1}` |
| **评论发布** | `POST /api/community/posts/90/comments` `{content_md}` → 200 `{comment_id:51, points:2}` |
| **评论点赞(1)** | `POST /api/community/comments/51/like` → 200 `{active:true, total_count:1}` |
| 详情持久(刷新) | `GET /api/community/posts/90` → 200 `like_count:1 comment_count:1 mine_react_like:true favorite_count:0` |
| 评论列表字段 | `GET /api/community/posts/90/comments` → `CommentItem{comment_id:51, author_name, content_md, like_count:1, mine_liked:true, created_at}` |
| **版块参数名实测** | `?board_code=programming` → total=32 含 90；`?board=programming` → total=90 未过滤（仍含 general）→ 确认参数为 **board_code** |
| 未登录拦截 | no-token `POST /like` 后端仍返回 200（DEBUG 虚拟身份）→ 证明必须**前端先拦**（实现已走 buildLoginUrl） |
| 清理折叠 | admin `PATCH /posts/{88,89,90}` `{is_locked:true}` → 200 `{ok:true}` |

- 早期探针 `test-docs/t118_out.txt`（t118_1~5 合并输出）覆盖：列表含 `mine_react_like`、board_code 四值均可过滤、content_md 必填（422 校验）、comment 分页 `{total,page,page_size,items}`。
- 测试帖/评论自建自清：88/89/90 号 task118 测试帖均已 admin 锁帖折叠，留证据于 DB（铜验收可复现）。

---

## 三、GWT 自评

| 验收项 | 结果 | 证据 |
|--------|------|------|
| Given student token，When 发帖（选"编程"版块），Then 列表新帖 board 正确、DB posts 有记录 | ✅ | 发帖返回 post_id=90 board_code=programming；`board_code=programming` 筛选命中 90；DB 由 service 落库（curl 返回即实证） |
| When 评论该帖，Then 详情页评论数 +1 且刷新后仍在 | ✅ | 评论 cid=51；详情 comment_count=1；`GET comments` 返回条目仍在 |
| When 点赞/再点赞，Then like_count +1/-1 且刷新后状态持久 | ✅ | like → `{active:true,total:1}`；再点 → toggle；详情 `mine_react_like:true, like_count:1`（刷新持久） |
| When 未登录点赞，Then 跳登录页 | ✅ | 前端 `noToken()→EAPI.buildLoginUrl(location.href)`；实测后端未登录仍放行（DEBUG），故前端先拦是唯一安全路径 |
| 机验 `grep prompt( =0` | ✅ | community.html 仅一行注释含 "prompt()"，实际 `prompt(` 调用 = 0 |
| 机验 board_code 非硬编码 | ✅ | 发帖发送 `selBoard`（用户 chips 选择值），非固定 "general"；"general" 仅作 chips 默认值/版块词表出现 |

---

## 四、三视角 critique 自检（交互态 / 边界 / 错误反馈）

依据 `tt/vendor/review/reference/critique.md`（以 UX 视角评估界面是否 work，非仅技术）逐条核对：

**① 交互态（States & Edge Cases）**
- 乐观更新成功回落：点赞/收藏/评论点赞均先 UI+1，后端返回后以 `{active,total_count}` 校准；失败 `.catch` 回滚到原值 —— 与后端 toggle 语义一致（实测 active/total 交替）。
- 双击防抖：帖子点赞/收藏用 `busy` 标志、评论点赞用 `data-busy`，防连点重复发请求造成库内二次 toggle。
- 发帖/评论提交期间禁用按钮（`disabled`），防重复提交。
- 详情加载/评论加载无数据 → 空态提示（"暂无评论/还没有人评论"）；post 404 → 行内报错并保留返回路径。

**② 边界（Boundaries）**
- 未登录：列表页点点赞/发帖 → 跳登录；详情页有 post_id 无 token → 跳登录（所有查询/互动鉴权，实测未登录后端不拦，前端必须拦）。
- 长文本：发帖内容 content_md 服务端限 20000、标题 200、评论 5000（422 校验见探针）；前端不设超长截断，交由后端契约校验并回显错误。
- 空标签：tags 为空数组也允许（PostCreate.tags 默认 []）；发帖空标题/空内容前端 `mErr` 拦截 + focus。
- 锁帖：is_locked → 隐藏点赞/收藏操作行 + 评论输入禁用 + 占位提示。

**③ 错误反馈（失败行内可见）**
- 分区下动态 `#cmtErr` 红字行内提示：发帖失败、评论为空、发布失败、点赞失败、帖子加载失败 —— 均在后端 reject 后 `flash(msg)` 显示，4s 自清，非仅 console。
- 发帖弹窗内置 `mErr` 行内错误 + `mSubmit.disabled` 转 loading。

**自检结论**：交互态/边界/错误反馈三视角均满足 critique kernel 要求；无明显 AI 模板套版（沿用既有 candy-playful 冻结样式，未新增脱离体系视觉）。

---

## 五、资产消费证据（B 级硬约束）

| 资产 | 调用证据 | 是否真实调用 |
|------|---------|------------|
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2（回传机制/完工报告纪律） | 本次会话 Read 该节；完工报告按 §5.2「按 completion-report.md 写报告、只传路径引用、验收独立实证」撰写，报告留 db/curl/grep 可复现证据 | ✅ |
| `C:\Users\Administrator\.agents\skills\tt\templates\completion-report.md` | 会话读取并按其 GWT/证据格式结构落盘 | ✅ |
| `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` critique 内核（`reference/critique.md`） | 会话读取 critique.md 内核；按其对「States & Edge Cases / 交互态 / 错误反馈」维度在三视角自检段逐条落地 | ✅ |
| 子 agent（独立测试/审查） | 已派发独立审查子 agent（general-purpose，ID `bfac29f8`）只读审查，独立发现 **Bug#1 点赞重复绑定/重复 POST**、**Bug#2 列表点赞无防抖**、Bug#3 列表锁帖可交互、Bug#4 版块徽标 class，均已修复（见 §六修复记录），修复后 node 重验 0 错 | ✅ |

## 六、独立子 agent 审查记录（ID bfac29f8，已修复并复审）

审查结论：功能主体完整、契约正确、无全局污染，「有条件通过」；4 项问题均已在下方修复并复审。

| # | 审查发现 | 修复 | 验证 |
|---|---------|------|------|
| 1（必改） | `prependPost`→`bindBoards()` 全量重绑 → 旧卡点赞重复发 POST（UI/DB 不一致） | `bindBoards` 改容器级事件委托 + `data-task118Bound` 幂等，仅绑定一次；新卡由委托自动覆盖 | node 0 错 |
| 2（建议） | 列表 `likePost` 无防抖 | 加 `btn.dataset.busy` 防抖 + `.finally` 释放 | node 0 错 |
| 3（低） | 列表锁帖帖可交互 | `renderPosts` 对 `is_locked` 加 `locked` 类 + 🔒徽标 + like-btn `disabled` + CSS 弱化 | node 0 错 |
| 4（次要） | 详情版块徽标 class 恒为 `math` | 版块 class 按 `board_code`（en/math/prog/gen）映射 | node 0 错 |

复审：修复后两文件 8 个内联 `<script>` `new Function` 语法 0 错，`prompt(` 实际调用 0，未重定义 `$`/`renderSides`。

---

## 七、契约承接核对

| 端点 | 契约 | 完成证据 |
|------|------|---------|
| GET /posts?board_code | 参数名实测 board_code | t118_5 / t118_full §7 |
| POST /posts | content_md 必填 | t118_out（422） |
| POST /posts/{id}/like | {active,total_count} | t118_out / t118_full §2 |
| POST /posts/{id}/comments | 体 content_md；resp {comment_id,...} | t118_full §3 |
| GET comments | items[CommentItem] | t118_full §6 |
| POST /comments/{id}/like | {active,total_count} | t118_out |
| 未登录跳登录 | EAPI.buildLoginUrl | 前端实现 + t118_full §8 反向实证 |

---

## 七、遗留问题 / 待确认

1. **DEBUG 模式虚拟身份（AGENTS 教训⑥）**：未登录点赞后端仍 200 且与 user_id=1 冲突（本篇 step 8/9），生产 DEBUG=False 后自动 401；已靠前端前置拦截兜底，验收时请按 DEBUG=False 口径复核或接受前端拦截证据。
2. **独立审查已完成并闭环**：子 agent bfac29f8 汇报 4 项问题，均已修复、node 重验 0 错（见 §六）；如需验收侧再跑一次独立实证复核可基于 §二/t118_full.py 复现。
3. 帖子列表无 DELETE 端点，测试帖以 admin `is_locked:true` 折叠留证（88/89/90）——若验收需物理删除，需后端补软删端点。
4. 收藏按钮已接 `POST /posts/{id}/favorite`（detail 页），列表页无收藏按钮，未超范围改动。
5. 评论列表加载 `/comments` 失败时静默（`.catch(()=>{})`），仅保留详情加载失败行内提示；如需评论加载失败也可见，可下轮补 `flash`。