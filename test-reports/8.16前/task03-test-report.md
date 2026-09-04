# 功能测试报告 Task03

## 第 1 次测试

### 判定：PASS

测试范围：G3 管理端课程/题库/用户页面（前端 `edu-frontend/src/lib/api/admin/{courses,questions,users}.ts`、`src/components/admin/*`、`src/app/(admin)/admin/{courses,courses/[seriesId],questions,questions/[id],users,dashboard}/*`、`scripts/verify-task03-*.mjs`）

环境：后端 8000 健康（`.env` DEBUG=true）；前端 Next.js 16.3.0 dev server 3000 运行中；测试注入真实 JWT（`sub=848` admin，由 JWT_SECRET 本地签发）。

---

### 验收标准逐条验证结果

| # | 验收标准（dev-plan task03） | 结果 | 证据 |
|---|------------------------------|------|------|
| 1 | 课程：创建系列→模块→课次→视频 Init→Finalize→Bind 全链路，每步 200、数据列表可见、视频 ready、tree 回显播放地址 | ✅ 通过 | `verify-task03-ui-chain.mjs` 6/6（UI 真实写操作：POST /series 200→列表回显→模块→课次→上传视频→Init→Finalize→Bind→「已绑视频」）；API 实测 `GET /courses/videos?session_id=` 返回 `transcode_status=ready` + play_720_url，`GET /series/{id}/tree` 回显 `video_url` |
| 2 | 题库：创建标签→创建题目（含 tag_ids）→按 tag_id 过滤命中 + subject/type/difficulty/keyword 过滤 | ✅ 通过 | API 实测：建标签→建 2 题（一含 tag 一不含）→`tag_id` 过滤仅命中含 tag 题；`subject_code/question_type/difficulty_level/keyword` 四路过滤均命中；浏览器 `/admin/questions` 选择 subject 后列表正确过滤 |
| 3 | 批量导入 10 条（含 1 重复编码 + 1 非法 schema）→ 返回 imported/skipped/failed 且失败原因可见 | ✅ 通过 | API 实测：`{total:10, imported:8, skipped:1, failed:1}`，messages 含 `[8] skip 编码重复` 与 `[9] schema invalid: stem_html Field required` |
| 4 | 用户：角色 student→teacher 生效；禁用生效；降级/禁用最后 1 个可用 admin 被后端拒绝且前端有明确提示 | ✅ 通过 | API：847 角色切换生效并恢复、849 禁用 status=0 生效并恢复；构造单 admin 场景后降级 848 → 400 `40303 至少保留 1 名可用管理员账号`（禁用同）；浏览器：toast 提示「至少保留 1 名可用管理员账号」且角色下拉回滚为 admin |
| 5 | dashboard 6 指标卡渲染 | ✅ 通过 | `verify-task03-admin-ui.mjs` 断言 PASS（用户总数/7d 活跃/禁用/7d 新增/30d 人均登录/角色分布 4 角色）；`MetricCards.test.tsx` 单测通过；浏览器实测 dashboard 页 0 个非 2xx API |
| 6 | student 访问任一 admin 页面被守卫拦截（task02 守卫） | ✅ 通过 | 浏览器注入 student 身份访问 `/admin/courses|questions|users|dashboard|courses/21` 5 页全部重定向到用户端 `/dashboard`；后端 `X-Force-Role: student` 访问 `/api/admin/users` → 403 `40300 角色无权限` |

### 运行验证

| 项 | 结果 | 说明 |
|----|------|------|
| `npx vitest run`（全量） | ✅ 18 文件 / 131 用例全部通过 | 含 task03 相关 7 个测试文件（courses 13 / questions 11 / users 9 / MetricCards 3 / UserTable 4 / SeriesForm 6 / QuestionForm 8） |
| `verify-task03-ui-chain.mjs` | ✅ 6/6 通过 | 真实 UI 写操作全链路（见上） |
| `verify-task03-admin-ui.mjs` | ⚠️ 部分通过（dashboard/列表 8/8，详情断言超时） | 见问题清单 #1 |

### 契约漂移核对（design-guide §4 vs 前端调用 vs 后端 router）

| 契约 | 结论 |
|------|------|
| §4.3 视频三连 Init/Finalize/Bind + GET /videos + materials/redirect-upload | ✅ 无漂移（`courses.ts` 全部路径与后端 `course_admin/router.py` + `prefix=/api/admin/courses` 一致；series/modules/sessions/cohorts 增删改查 18 个端点逐一核对一致） |
| §4.4 题库列表/CRUD/批量导入（list[dict]）/组卷 + 标签 | ✅ 无漂移（`questions.ts` 与 `question_admin/router.py` + `prefix=/api/admin/questions` 一致；题型枚举以 `single_choice/…` 后端权威为准，design-guide §4.4 中 `single/multi/judge` 已注明为占位摘要，前端注释已显式标注差异） |
| §4.5 用户列表/角色/状态/metrics | ✅ 无漂移（`users.ts` 与 `user_admin/router.py` + `prefix=/api/admin/users` 一致；列表主键 `user_id`、role/status body 结构、最后 admin 拒绝码 40303 均对齐） |

### 问题清单

| # | 严重度 | 位置 | 原因 | 修改建议 |
|---|--------|------|------|----------|
| 1 | 一般 | `edu-frontend/scripts/verify-task03-admin-ui.mjs` | 脚本硬编码依赖既有数据（`seriesId=21` + `text=验证模块`、`questions/4` + 编码 `Q-20260812194829`、课次须未绑视频才有「上传视频」按钮），与数据库现状不符（系列 21 为早期脚本写入的乱码名、session 已绑视频）导致详情页断言 `waitForSelector` 超时；且超时进入 catch 后最终 `process.exit(failed.length>0?1:0)` 以 exit 0 掩盖了未执行的断言，输出仍显示「8/8 通过」 | 改为自建数据断言（参照 ui-chain.mjs 流程）或将数据依赖参数化，超时/断言缺失时显式非零退出 |

> 注：问题 #1 为交付验证脚本的健壮性问题，**非产品功能缺陷**——系列详情页功能经独立浏览器验证渲染正常（模块树/已绑视频/班次区/课件指引均在），核心链路已由 ui-chain.mjs 6/6 覆盖。

### 架构薄弱点验证结果

| # | 薄弱点（design-guide §7） | 是否命中 | 说明 |
|---|--------------------------|---------|------|
| 1 | DEBUG 鉴权绕过（无 Token 虚拟 ADMIN / X-Force-Role 伪冒） | ⚠️ 命中（供 sd-challenger 深挖） | 实证：无 Authorization 头直接 `GET /api/admin/users` 返回 200（虚拟超级管理员）；`X-Force-Role: student` 访问 `/api/admin/users` 正确 403；`X-Force-Role: admin` 可访问全部管理端端点。`.env` 实测 `DEBUG=true` |
| 2 | 前端静默吞错（R-7） | ✅ 未命中（task03 范围） | 写操作失败经全局 MutationCache onError → toast 实测生效（40303 场景 toast 出现）；courses/dashboard 页浏览器实测 0 个非 2xx API |
| 3 | 聊天路径不匹配（R-1） | — 不适用 | task05 范围 |
| 4 | DELETE 会话缺失（R-2） | — 不适用 | task05 范围 |
| 5 | 文档口径漂移（R-9） | ✅ 未命中（task03 范围） | 三端契约逐条核对一致，见上「契约漂移核对」 |

---

## 测试记录

- 测试方式：Vitest 全量 + Playwright 浏览器（UI 真实写操作 + student 守卫 5 页 + toast 交互 + dashboard/列表 401 排查）+ API 级验收（Python，26/28 断言中 2 项为测试脚本误判：后端以 HTTP 400 + code 40303 拒绝，符合验收标准「400/403」，判为通过）
- 数据影响：测试创建了系列 `UI-*`、题目 `Q-API1/2-*`、标签 `TT-*`、批量导入 `BT-*` 8 条（重复/非法未入库）；用户 847/849/850 已恢复现场（admin 数量恢复为 2）

---

## 第 2 次测试（修正轮复测，2026-08-12）

### 判定：FAIL

复测范围：挑战 #2 题型枚举 / #3 物理删改软删 / #4 登录禁用 / #5 死接口与脱敏 / #6 状态码映射 / #7 batch 上限 / #9 前端 confirm 已修项回归；#1 DEBUG、#8 RAND 记录不修项确认。

### 问题清单

| # | 严重度 | 位置 | 原因 | 修改建议 |
|---|--------|------|------|----------|
| 1 | 一般 | `edu-frontend/src/lib/auth-client.ts:353-374`（`onApiUnauthorized`）+ `api-client.ts:132-138` | 登录失败（401/403）时响应拦截器调用全局 `onApiUnauthorized`，该处理器无条件 `window.location.href = "/login"` 触发页面重载，而 `LoginForm.tsx:70-75` 的 `form.setError("root.server")` 错误横幅在重载后被清空。实测：禁用账号（仅 `status=0`）登录返回 403 + code 40112 + message「该账号已被禁用，请联系管理员」——后端修复正确，但浏览器端**不显示任何提示**；对照错误密码 401 同样无横幅，证实为全局拦截器重载吞掉提示（挑战 #4 修复仅 API 层打靶验证了 #4c/d，未打通前端展示路径） | `onApiUnauthorized` 增加分支：当失败请求为 `POST /api/auth/login`（且当前已在 /login）时跳过 `location.href` 重载，交由 LoginForm 原地渲染 root.server 横幅；仅对非登录接口的 401/403 执行全局登出+跳转 |

### 复测验证记录

| 复测项 | 结果 | 证据 |
|--------|------|------|
| `npx vitest run` 全量 | ✅ 18 文件 / 130 用例通过 | 10.92s，0 失败 |
| 浏览器：ModuleTree 删模块 confirm | ✅ | Playwright 实测弹窗「确定删除模块…将级联删除其下 1 个课次并解绑关联视频，此操作不可恢复」（dismiss 不真删） |
| 浏览器：删课次 confirm | ✅ | 弹窗「确定删除课次…关联视频将自动解绑，此操作不可恢复」 |
| 浏览器：批量导入非法题型计 failed | ✅ | 3 条（2 合法 + 1 `unknown_type`）→ UI 展示「共 3 条 导入 2 跳过 0 失败 1」+ messages 失败原因 |
| 浏览器：禁用后登录返回「已禁用」 | ❌ | 后端 403+40112+「该账号已被禁用，请联系管理员」，但页面重载后横幅消失（问题 #1） |
| 后端：批量导入 3 条含 1 条 unknown_type → failed=1 | ✅ | `verify_task03_fix.py` #2b PASS（imported=2/failed=1） |
| 后端：删已绑视频 session 后 `GET /videos?session_id` 无孤儿资产 | ✅ | #3e/f PASS（items=0，树中课次隐藏） |
| 后端：重复编码创建返回 409（非 400） | ✅ | #6a 系列 409+40901、#6b 题目 409+40901 PASS |
| 后端：其余定向打靶（#3a-d/g-i、#4、#5、#6c-d、#7） | ✅ | `verify_task03_fix.py` 25/25 全绿 |
| `admin_all_hit.py`（课程/题库/用户 19 断言） | ✅ | 19/19 通过（真实 HTTP，端口 18765） |
| `test-reports/task03-challenge.md` 处置结论 | ✅ | 已含 9 项处置：2/3/4/5/6/7/9 已修、1 记录不修（DEBUG）、8 记录不修（RAND）；回归记录 admin_all_hit 19/19、auth_hit 4/4、curriculum_hit 9/9、verify_task03_fix 25/25 |
| 不修项确认 | ✅ | #1 DEBUG=true 仍可 X-Force-Role 伪冒（记录，未修）；#8 `ORDER BY RAND()` 未改（记录） |

### 架构薄弱点验证结果

| # | 薄弱点（design-guide §7） | 是否命中 | 说明 |
|---|--------------------------|---------|------|
| 1 | DEBUG 鉴权绕过 | ⚠️ 命中（记录不修） | `.env` 实测 DEBUG=true，X-Force-Role 伪冒 admin 仍可用；挑战 #1 已记录不修（上线硬门槛 DEBUG=false），本次复测通过打靶脚本依赖该能力，未再改动 |
| 2 | 前端静默吞错（R-7） | ⚠️ 部分命中（复测新发现） | 非 catch 空态，但登录失败 401/403 提示被全局拦截器页面重载吞掉，效果等同错误反馈丢失（问题 #1）；其余写操作 toast 路径（挑战 #4 40303 等）经代码审查仍正确 |
| 3 | 聊天路径不匹配（R-1） | — 不适用 | task05 范围 |
| 4 | DELETE 会话缺失（R-2） | — 不适用 | task05 范围 |
| 5 | 文档口径漂移（R-9） | ✅ 未命中（修正轮范围） | 复测核对 #2 题型枚举挂 Literal、#5 死端点删除、#6 状态码映射、#7 上限校验，前端调用与后端 router 契约一致 |

### 测试记录

- 测试方式：Vitest 全量 + Playwright 浏览器抽查（confirm 弹窗/批量导入/禁用登录）+ API 定向打靶（`verify_task03_fix.py` 25 断言）+ `admin_all_hit.py` 19 断言
- 数据影响：复测创建的系列/题目/标签/试卷/视频/账号（alice_rt*/disabled_rt* 等 9 用户、Q-RT-* 题目、S-RT-* 系列）已由 `cleanup_task03_test_data.py` 清理，DB 恢复种子态（11 系列 / 22 模块 / 66 课次 / 2 示例题）；admin_all_hit.py 自起 18765 端口服务已停止，8000 主服务未受影响

---

## 第 3 次测试（复测 #1 修复验证，2026-08-12）

### 判定：PASS

复测范围：第 2 次测试问题 #1（登录失败 401/403 横幅被全局 `onApiUnauthorized` 页面重载吞掉）修复回归。

### 问题回归清单

| # | 上次问题 | 当前状态 |
|---|---------|---------|
| 1 | 禁用账号/密码错误登录失败提示被全局拦截器 `location.href="/login"` 重载清空，用户看不到失败原因 | ✅ 已修复 |

### 修复落点（代码审查）

| 文件 | 修复 | 评估 |
|------|------|------|
| `edu-frontend/src/lib/api-client.ts:44-47` | 新增 `isAuthEndpoint()`：`/api/auth/(login|register)` 判定为认证类接口 | ✅ 含 query 参数防御（`[?#]` 边界） |
| `edu-frontend/src/lib/api-client.ts:145-156` | 响应拦截器：401/403 时认证类接口**跳过**全局回调（`_onUnauthorized`），仅非认证接口走全局登出+跳转 | ✅ 与修复意图一致 |
| `edu-frontend/src/lib/auth-client.ts:362-365` | `onApiUnauthorized` 兜底：已在 `/login|/register` 页时直接 return，防未来新增认证接口漏判 | ✅ 双保险 |
| `edu-frontend/src/components/auth/LoginForm.tsx:66-75` | `form.setError("root.server")` 原地渲染横幅（rose 边框） | ✅ 保持不变 |

### 运行验证记录

| 复测项 | 结果 | 证据 |
|--------|------|------|
| `npx vitest run` 全量 | ✅ 18 文件 / 139 用例通过 | 11.90s，0 失败；`api-client.test.ts` 新增 6 用例（isAuthEndpoint 4 + 认证接口 401/403 不触发全局回调 + 业务接口仍触发） |
| 浏览器：错误密码登录 | ✅ 显示「账号或密码错误」横幅且**不重载** | Playwright：`window.__marker` 在提交后仍为 `alive`（页面未重载），URL 保持 `/login` |
| 浏览器：禁用账号登录 | ✅ 显示「该账号已被禁用，请联系管理员」横幅且**不重载** | 后端 403+40112 已由第 2 次复测确认；本次注册→改 status=0 构造（user_id=873）后浏览器实测 marker 存活、URL 不变 |
| 浏览器：合法登录 | ✅ 正常跳转 /dashboard | 恢复 status=1 后登录，`waitForURL("**/dashboard**")` 命中 |
| 数据现场 | ✅ 已恢复 | 测试账号 rt1786540401（873）登录验证后恢复 status=1，未影响既有账号 |

### 架构薄弱点验证结果

| # | 薄弱点（design-guide §7） | 是否命中 | 说明 |
|---|--------------------------|---------|------|
| 2 | 前端静默吞错（R-7） | ✅ 已闭环 | 本次修复打通了登录失败提示的前端展示路径，401/403 横幅在浏览器实测可见，不再被重载吞掉 |

### 测试记录

- 测试方式：Vitest 全量 + Playwright 真实浏览器（headless chromium，window marker 重载探针 + 真实 UI 填表提交）
- 环境：后端 8000 健康（`.env` DEBUG=true）；前端 dev server 3000；测试账号 rt1786540401（注册→禁用→恢复）
