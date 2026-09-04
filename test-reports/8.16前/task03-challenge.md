# 对抗性测试报告 Task03

## 第 1 次测试

### 判定：FAIL

### 测试环境

- 后端运行中：`http://127.0.0.1:8000/health` → 200；`.env` `DEBUG=true` 确认
- 攻击方式：脚本化 HTTP 打靶（PowerShell + Node UTF-8 body，遵循 L11），含真实注册/登录 student 账号做 RBAC 实测
- 测试数据：对抗用系列/模块/课次/视频/题目已全部清理（Q-BIG-* 1000 条已删净；CHAL-SER-01 已下架；851/852/850/848 状态已恢复）

### 问题清单

| # | 维度 | 严重度 | 位置 | 质疑 | 可能后果 | 建议 |
|---|------|--------|------|------|---------|------|
| 1 | 架构级（薄弱点 1 实证） | 严重 | edu-agent/app/auth/dependencies.py:80-127（.env DEBUG=true） | **无 Authorization 头直接 `GET /api/admin/users` 返回 200 真实数据（total=50）**；`X-Force-Role: admin` 伪冒任意 admin 成功。task03 的课程/题库/用户全部页面数据在 DEBUG 下对任何人裸奔，前端守卫（admin-guard.tsx:68-88 用 token 硬门槛）只能拦浏览器 UI，拦不住直连 API | 任何人可读 46 个管理端点全量数据、改角色/禁用用户/删课程 | 后端已知薄弱点（红线"本轮不改后端"），但验收标准 RBAC 维度不完整——「未登录 401」场景在 DEBUG=true 下全绿是假象；上线硬门槛必须 DEBUG=false + CORS 收紧（main.py 现 `*`）。建议将 DEBUG 绕过列入 task05 联调验收的前置阻塞项 |
| 2 | 契约漂移（薄弱点 5 + 验收盲区） | 一般 | edu-agent/app/admin/question_admin/schemas.py:60（`question_type: str` 裸 str）、service.py:298-325 | **题型枚举非法值直穿后端**：`question_type:"hacker_choice"` 创建 200；批量导入中非法题型被计为 imported 而非 failed（实测 3 条含 1 条 `unknown_type` → total=3 imported=2 skipped=1 failed=0）。`QuestionType` 枚举类（schemas.py:16-21）定义了却未挂到 schema 校验 | 验收标准「10 条含 1 条非法 schema → failed 可见」实际 failed=0、失败原因列表为空——UI 承诺（BatchImportDialog 样例提示"应失败"）与后端行为不符；任意字符串题型入库，用户端按题型分发渲染时可能异常 | 后端 `question_type` 改 `Literal["single_choice","multi_choice","true_false","fill_blank","short_answer"]`（或复用 QuestionType 枚举），批量导入对非法枚举计数 failed；前端 QuestionForm 已只提供 5 种合法值，属正确防御，保留 |
| 3 | 数据一致性（挑战方向 4/5） | 一般 | edu-agent/app/admin/course_admin/service.py:359-362（`DELETE FROM curriculum_session` 物理删）、:309-314（删模块级联物理删 session） | **删除已绑定视频的 session 产生孤儿资产**：实测 DELETE session 77 → 200，`GET /videos?session_id=77` 仍返回 asset V20260812-1E9CD108（status=ready）指向不存在的 session；删除模块同样级联物理删全部课次且不清理 admin_course_video_asset.session_id。违反红线约束 2（业务表软删 yn=1/0） | 视频资产成孤儿无法通过 UI 定位；误删模块=整棵课次树物理消失（不可恢复）；`GET /videos?session_id` 返回幽灵数据 | delete_session/delete_module 改软删（yn=0），删除/级联删除时同步置空 asset.session_id 或标记资产解绑；前端 ModuleTree 删除操作补 confirm 二次确认 |
| 4 | 数据一致性（挑战方向 5） | 一般 | edu-agent/app/auth/service.py:256-272（`_find_user_by_account` WHERE u.yn=1 + login 只查 yn 不查 status） | **仅 status=0 禁用不生效**：实测对 852 只传 `{"status":0}` → 登录 200 成功；yn=0 时才拒绝，但返回 `AUTH_LOGIN_FAILED`「账号或密码错误」而非「已禁用」——`AUTH_USER_DISABLED` 分支是死代码（查询已过滤 yn=1，`if yn != 1` 永不触发） | API 契约（UserStatusRequest.yn 可选）允许只传 status 的调用方禁用失败；禁用用户被提示密码错误（误导性反馈）；用户管理禁用语义半失效 | login 查询去掉 yn 过滤、显式检查 `status/yn` 双字段并区分 AUTH_USER_DISABLED；前端 UserTable 双字段传参（status+yn）为正确防御，保留 |
| 5 | 契约漂移（薄弱点 5） | 一般 | edu-agent/app/admin/course_admin/service.py:222-227 + edu-frontend/src/lib/api/admin/courses.ts:280-289 | **`POST /series/{id}/yn` 死接口 500**：实测 `yn=0` → 500 `Unknown column 'yn' in 'field list'`（curriculum_series 表无 yn 列）。design-guide §3.4 摘要列此接口；前端 courses.ts 封装了 toggleAdminSeriesYn——L13 后无页面调用（改用 sale_status PATCH，正确），但封装仍留库中，未来任何调用必炸。且 500 detail 泄露 SQL 原始错误 | 代码库内存在必炸封装陷阱；错误信息泄露（SQL 细节透出给调用方） | 删除后端死端点或改 `SET sale_status='off_sale'` 语义；前端删除 toggleAdminSeriesYn 封装；500 handler 对 detail 做脱敏 |
| 6 | 非功能/契约 | 轻微 | edu-agent/app/common/exceptions.py:27（AppException 默认 http_status=400）+ admin 各 service 用 BizError(40901/40401/40303) | **重复编码/资源不存在/最后 admin 防护一律 HTTP 400**（实测重复系列 400+code 40901、重复题目 400+code 40901、最后 admin 降级 400+code 40303） | 前端 api-client 解析 body.message → toast 正常（功能 OK），但 REST 语义错位（409 冲突/404 不存在应为对应状态码）；若未来调用方按 status 分支（如 409 才提示冲突）则失效 | 按业务码映射 http_status（40901→409、40401→404、40303→403） |
| 7 | 边界攻击（挑战方向 4） | 轻微 | edu-agent/app/admin/question_admin/router.py:113-118（batch-import 无上限） | 1000 条/242KB payload 直通 200（实测 imported=1000），无条数上限/大小限制；单条失败逐条跳过设计合理，但无 max 校验 | 超大 payload 消耗服务端 CPU/DB 资源（无悬崖，线性），无节流 | 加条数上限（如 ≤500）与 size 校验，超出返回 400 |
| 8 | 非功能/性能 | 轻微 | edu-agent/app/admin/question_admin/service.py:411（`ORDER BY RAND()`） | 组卷按 RAND() 全表扫描排序，题库 10 万级时响应显著退化；expected_question_count 达不到时静默降级为实际数量（前端展示实际数 ✓） | 数据量增大 → 组卷性能悬崖；题量与规格不符无提示 | 改用 `WHERE ... ORDER BY RAND() LIMIT` 优化（仍 O(n) 但可加 id 抽样/缓存）；前端在 selected<expected 时提示「规格不满足，实际选中 N 题」 |
| 9 | UX/数据安全 | 轻微 | edu-frontend/src/components/admin/ModuleTree.tsx:70-92,139-141,176、questions/page.tsx:215、courses/page.tsx:129 | 删除模块/课次/班次/题目、系列下架均无 confirm 二次确认；删除模块后端级联物理删全部课次（问题 3 叠加） | 误点即数据永久丢失（尤其删模块=级联删课次），管理员操作无后悔药 | 删除/级联删除类操作加 confirm 弹窗（如 `window.confirm` 或 shadcn AlertDialog） |

### 薄弱点核查清单（design-guide §7）

| design-guide 薄弱点 | 防御/实证 | 结论 |
|---|---|---|
| 1 DEBUG 鉴权绕过 | 前端 admin-guard.tsx:68-88 token 硬门槛（未登录跳登录，不误放行）；**后端无鉴权实证：无 token GET /api/admin/users → 200**；`X-Force-Role: admin` → 200 伪冒成功 | 前端已防御，后端裸奔（问题 #1） |
| 2 前端静默吞错（R-7） | 全部写操作走 useMutation + 全局 MutationCache onError toast（query-client.ts:50-52）；列表失败 ErrorState 可重试；BatchImportDialog 展示 messages 失败原因；VideoUploadFlow finalize 非 ready → toast.error | 已防御 |
| 5 文档口径漂移（R-9） | 逐条核对：courses/questions/users 前端路径与后端 router 全对（含视频 init/finalize 字段名 origin_file_name/asset_id、batch-import 裸数组、组卷 {spec:{...}} 形态，实测均 200）；**发现 2 处后端侧漂移**：题型枚举无校验（#2）、`/series/{id}/yn` 死接口 500（#5） | 部分漂移（问题 #2/#5） |

### 验收标准盲区（dev-plan task03）

1. 「批量导入 10 条（含 1 条重复编码 + 1 条非法 schema）→ failed 可见」——验收假设后端会拒绝非法 schema，但题型字段无枚举约束，非法 schema 被当成功导入（T7 实证 failed=0）。**验收标准的"非法"样本恰好落在后端不校验的字段上**，标准本身没有定义"非法 schema"的字段范围。
2. 「将某用户角色 student→teacher 再禁用；尝试降级/禁用最后 1 个可用 admin 时后端拒绝（400/403）」——禁用语义只验证了双字段路径（status+yn），未覆盖「仅 status」契约路径（实际禁用失效，问题 #4）。
3. 「视频 Init→Finalize→Bind 全链路」验收未覆盖「删除已绑定 session」后的资产一致性（问题 #3）。
4. RBAC 验收只测了「student/manager 访问被拦」，未覆盖「无 token 直接打 admin API」场景（DEBUG=true 下实证 200，问题 #1）。

### 已验证通过项（防御证据）

| 验证点 | 实证 |
|---|---|
| RBAC：student token 访问 /admin/users、POST /admin/questions、/courses/series、/users/dashboard/metrics | 全部 403（实测） |
| 非法角色 target_role=superuser | 422（实测） |
| 最后 1 个 admin 禁用/降级双重防护（status 与 role 两接口） | 400 被拒（实测 T13a/b/c） |
| batch-import 裸数组契约 + 重复编码 skip + messages 可见 | 200，skip 原因含编码（实测） |
| 组卷 body {spec:{...}} 形态 + 实际题数回显 | 200，selected=实际数量（实测） |
| 视频 init/finalize 字段名（origin_file_name/asset_id/play_720_url）与 bind 后 tree 回显 video_url | 200 + tree 回显 play 地址（实测） |
| 题目 tag_id 过滤与返回 tags 同源一致（service.py:114-116/131-146） | 代码审查确认 |
| 创建系列/题目重复编码提示（code 40901 → 全局 toast） | 400 + message「编码已存在」（实测，HTTP 语义见 #6） |
| XSS：admin 目录 grep 无 dangerouslySetInnerHTML，名称/题干全部 React 文本节点默认转义 | 代码审查确认 |
| 网络错误/超时壳：api-client.ts:86-93 status=0 明确文案，不伪装 500 | 代码审查确认 |

---

报告路径：`test-reports/task03-challenge.md`

---

## 处置结论（task03 修正轮，2026-08-12）

> 修正轮执行者：sd-dev。修复原则：不改变端点契约与 RBAC；后端既有打靶（admin_all_hit.py 19/19、auth_hit.py 4/4、curriculum_hit.py 9/9）回归全部通过；另写 `verify_task03_fix.py` 定向打靶 25/25 全绿。

| # | 严重度 | 处置 | 改动方式 | 验证 |
|---|--------|------|---------|------|
| 1 | 严重 | 不修（记录） | 后端 DEBUG 鉴权绕过属既有设计（task02 已处置），上线硬门槛为 `.env DEBUG=false`（main.py 生产模式 CORS 收敛 `*`→localhost:3000、docs 关闭、detail 脱敏均已有条件分支）；后端不改 | — |
| 2 | 一般 | ✅ 已修 | `question_admin/schemas.py`：新增 `QuestionTypeValues = Literal[...]` 并挂到 `QuestionAdminCreate.question_type`（必填）与 `QuestionAdminUpdate.question_type`（可选）；批量导入中非法题型被 Pydantic 拒绝 → `batch_import_questions` 外层 except 计 `failed`（不再 imported） | 定向打靶 #2a 非法题型创建 422；#2b 批量导入含 1 条 `unknown_type` → failed=1/imported=2 |
| 3 | 一般 | ✅ 已修 | ① 迁移：`patch_curriculum_soft_delete.sql` + `apply_patch_curriculum_soft_delete.py` 为 `curriculum_session`/`curriculum_module` 补 `yn TINYINT DEFAULT 1` + 索引（幂等，已应用）；② `course_admin/service.py`：`delete_session`/`delete_module` 由物理 DELETE 改 `UPDATE SET yn=0`，并在同一事务内先把 `admin_course_video_asset.session_id` 置 NULL（消孤儿资产）；③ 读路径全面补 `yn=1` 过滤：admin tree/list（course_admin）、用户端 tree/list（curriculum）、progress、recommender join、video bind 目标检查 | 定向打靶 #3e/f/g/h/i：删课次后 `GET /videos?session_id` 无幽灵资产、树中课次/模块隐藏；DB 验证 yn=0 |
| 4 | 一般 | ✅ 已修 | `auth/service.py`：`_find_user_by_account` 去掉 `u.yn=1` 过滤并补查 `u.status`；`login_user` 显式检查 `yn/status` 双字段，任一禁用 → `AUTH_USER_DISABLED`（激活死代码分支）。**附带修复**：`auth/router.py` `_translate_validation_error` 原来把数字业务码与字符串子码集合比较（永不命中→全部 400），改为取 `ValidationError.http_status` 单一事实源（AUTH_LOGIN_FAILED→401、AUTH_USER_DISABLED→403、ACCOUNT_EXISTS→409），与前端 LoginForm 文档契约对齐 | 定向打靶 #4c/d：仅 `{"status":0}` 禁用后登录 → 403 + code 40112 +「已禁用」提示；#4f 恢复后登录 200；auth_hit.py 4/4 |
| 5 | 一般 | ✅ 已修 | 后端：删除死端点 `POST /series/{id}/yn`（router+service）与 `list_series_admin` 的 `yn` 过滤参数（curriculum_series 无 yn 列，原实现必 500）；下架语义统一 `PATCH /series/{id} {sale_status}`。前端：删除 `toggleAdminSeriesYn` 封装及对应单测，`listAdminSeries` 不再透传 yn。**500 脱敏**：`main.py` 两个 5xx handler（AppException/HTTPException）生产模式（`DEBUG=false`）把 `detail` 置 None，DatabaseError 不再泄露 SQL | 定向打靶 #5a `POST /series/{id}/yn` → 404（不再 500）；#5b `GET /series?yn=0` → 200；前端 vitest 全绿 |
| 6 | 轻微 | ✅ 已修 | `common/exceptions.py`：`AppException` 增加 `_http_status_for_code` 前缀映射（409xx→409、404xx→404、403xx→403、401xx→401、400xx→400、5xxxx→500），`http_status` 参数改默认 None 由映射推导；特殊类（NotFound/LLM/Database/Validation 字符串子码）仍显式传状态码。grep 确认既有 `*_hit.py` 无对 40901/40401/40303 断言 400 的脚本，无需改脚本 | 定向打靶 #6a/b 重复系列/题目编码 → 409+40901；#6c 不存在题目 → 404+40401；#6d 最后 admin 禁用 → 403+40303 |
| 7 | 轻微 | ✅ 已修 | `question_admin/router.py` 批量导入改读 `request.body()`：raw 长度 >2MB → 400「数据过大（≤2MB）」；JSON 非数组 → 400；条数 >500 → 400「超出上限」；合法数据仍走 service 逐条导入 | 定向打靶 #7a 501 条 → 400+上限 message；#7b 2.1MB body → 400+2MB message |
| 8 | 轻微 | 记录（未修） | `ORDER BY RAND()` 属性能优化项；现行 SQL 已是 `WHERE ... ORDER BY RAND() LIMIT` 形态（task 允许顺手改但须验证组卷正确性，本轮不改以免引入组卷行为风险），留待数据量增长时做 id 抽样/缓存改造 | — |
| 9 | 轻微 | ✅ 已修 | 删除/下架类操作统一加 `window.confirm` 二次确认（全项目统一一种，shadcn AlertDialog 组件不存在于 ui/ 目录故未引入）：`ModuleTree.tsx` 删模块（提示级联删 N 课次）/删课次/删班次、`questions/page.tsx` 删题、`courses/page.tsx` 下架系列（上架为恢复操作不加确认） | 前端 `npx tsc --noEmit` exit 0；`npx vitest run` 18 文件 130/130；改动文件 `npx eslint` 0 错误（仓库另有 30 处既有 lint 错误均在未触碰模块，非本修正轮引入） |

### 回归与验证记录

| 项 | 结果 |
|----|------|
| `admin_all_hit.py`（课程/题库/用户 三模块 19 断言） | ✅ 19/19 通过 |
| `auth_hit.py`（register/login/refresh/me 4 断言） | ✅ 4/4 通过 |
| `curriculum_hit.py`（用户端分级课程 9 断言，验证 yn 过滤后读路径） | ✅ 9/9 通过（清理测试数据后 pristine 种子 11 系列） |
| `verify_task03_fix.py`（本轮新增定向打靶，#2/#3/#4/#5/#6/#7 共 25 断言） | ✅ 25/25 通过 |
| 前端 vitest / tsc / lint（改动文件） | ✅ 130/130 / exit 0 / 0 错误 |

### 测试数据处置

修正轮产生的打靶数据（S-SOFT-*/S-ADMIN-*/TS-*/UI-*/CHAL-SER-01 系列、Q-* 题目、KP-HIT-* 标签、PAPER-* 试卷、V20* 视频资产、alice_*/disabled_*/p7_roleswap_* 测试账号）已由 `cleanup_task03_test_data.py` 全部清理，数据库恢复种子态（11 系列 / 22 模块 / 66 课次 / 2 示例题，保留 user_id=802 作为种子 created_by 引用）。
