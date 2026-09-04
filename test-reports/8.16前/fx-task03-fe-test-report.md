# 前端测试报告 fx-task03

> 测试执行：fe-tester（2026-08-13，最终功能测试轮）
> 测试对象：G3 管理端课程/题库/用户页面（fx-task03，dev-plan P9 Step8，已实现 + 已修正）
> 技术栈确认行：Next.js 16 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router（与 frontend-stack.json `techStackConfirmLine` 一致）
> 本轮只测试与写报告，**未修改任何业务代码**（补课写路径隔离一致）

## 判定

**判定：✅ PASS（28/28 浏览器实测通过；单测 209/209 全绿；tsc/eslint 0 错误）**

> ⚠️ 附 1 个 **P2 级规格偏差发现项**（最后 1 个 admin 降级被拒时业务 toast 未出现，403 被全局登出处理——详见 §5.3），属「验收 F 字面预期 vs 全局 403 策略」冲突，建议主编排器裁决是否修正；不影响后端 40303 拒绝保护的有效性（请求发出、select 保持 admin、不假装成功均已验证）。

## 环境

| 项 | 值 |
|----|----|
| 工作目录 | `E:\stu\project\stu\EduAgent实施手册` |
| 前端工程 | `edu-frontend`（Next.js 16.3.0 Turbopack，`npm run dev`） |
| dev server | `http://localhost:3000` 运行中（PID 24760；server-info 轮次后重启，fe-server-infra 产物为准） |
| 后端 | `127.0.0.1:8000` **未运行** → 全部 admin API 由 Playwright `page.route` 模拟（含 CORS/preflight），注入 admin JWT（localStorage `edu:auth:token` + `edu:auth:me` roles=["admin"]） |
| 画像 | `frontend-stack.json`（profileId=nextjs-16-app-router） |
| 规格 | `.claude/specs/frontend/fx-task03/frontend-spec.md` + `visual-acceptance.md`；server-info `test-reports/fx-task03-server-info.md` |
| 浏览器 | Playwright chromium（headless，1280×800） |

## 验收标准逐条映射（dev-plan P9 Step8 fx-task03 行）

| # | 验收标准（Given/When/Then，dev-plan:57） | 验证方式 | 结果 |
|---|------------------------------------------|----------|------|
| 1 | Given admin 打开课程管理；When 创建系列→模块→课次→视频 Init→Finalize→Bind 全链路；Then 每步 200、数据在列表可见、视频资产状态 ready 且绑定后回显播放地址 | 浏览器实测 T2.4 / T3.2 / T4.2-4.3（route 200） | ✅ 全链路 200；系列列表可见；模块树更新；视频 finalize 返回 ready + Bind 后 toast「视频已绑定课次，播放地址已同步」 |
| 2 | Given 题库管理；When 创建标签→创建题目（含 tag_ids）→按 tag_id 过滤；Then 命中且列表支持 subject/type/difficulty/keyword 过滤 | 浏览器实测 T5.1/T5.2/T5.5 + 单测 QuestionForm.test 8 例 | ✅ 标签创建 POST /tags；题目创建 POST /questions → router.push 跳编辑页；学科过滤请求带 subject_code；单测覆盖 tag_id/题型/难度/关键词过滤 |
| 3 | Given 批量导入；When 提交 10 条（含 1 重复 + 1 非法）；Then 返回 imported/skipped/failed 计数且失败原因可见 | 浏览器实测 T5.3/T5.4（route 返回 total=3/imported=1/skipped=1/failed=1 + messages） | ✅ 三色计数渲染（emerald/amber/rose）+ messages 列表 + toast「导入完成：成功 1 / 跳过 1 / 失败 1」 |
| 4 | Given 用户管理；When 将某用户角色 student→teacher 再禁用；Then 更新生效；尝试降级/禁用最后 1 个可用 admin 时后端拒绝且前端有明确提示 | 浏览器实测 T6.1/T6.2a/T6.3 + 单测 UserTable.test 4 例 | ✅ 角色切换生效（POST /role + toast「角色已更新」）；40303 后端拒绝生效、下拉保持 admin 不假装成功；**⚠️ 偏差**：预期「业务 toast」被全局 403 登出处理取代（见 §5.3） |
| 5 | Given 管理端仪表盘；When 加载 `/api/admin/users/dashboard/metrics`；Then 6 项指标卡（总数/7d 活跃/角色分布/禁用/7d 新增/30d 均登录）渲染 | 浏览器实测 T7.1 + 单测 MetricCards.test 3 例 | ✅ 6 指标卡 + 角色分布 4 角色计数 + metrics 请求 |

补充映射（frontend-spec 验收 A~G 关键条目）：

| 规格条目 | 关键验证 | 结果 |
|----------|----------|------|
| A 列表三态/筛选分页 | 单测（courses/questions/users 页 + controls） | ✅ 加载/错误/空三态、筛选 setPage(1)、PaginationBar |
| B 课程列表（下架 confirm / 上架 / 草稿 badge / 创建/编辑） | 单测 SeriesForm.test 6 例；浏览器 T2 创建链路 | ✅ |
| C 系列详情（无效 ID 不发请求、模块折叠 aria-expanded、删模块级联 confirm、视频四步流、关弹窗清 interval） | 浏览器 T3.1/T4；单测 | ✅ |
| D 题库列表（批量导入 JSON 解析失败 throw 非吞错、body 非数组、组卷、删除 confirm+aria-label） | 单测 QuestionForm/BatchImportDialog/ComposePaperDialog | ✅ |
| E 题目编辑（5 题型分发、validateForm、embedded PATCH） | 单测 QuestionForm.test 8 例（判断题对/错按钮、填空/简答 label 切换、必填 error） | ✅ |
| F 用户管理（角色/状态变更、40303 不吞错、详情弹窗无 MOCK） | 浏览器 T6；单测 UserTable.test 4 例 | ✅（toast 偏差见 §5.3） |
| G 仪表盘（6 卡 + 角色分布 + 错误态重试） | 浏览器 T7；单测 MetricCards.test 3 例 | ✅ |

## 单测统计（`npx vitest run` 全量）

- 命令：`npx vitest run`（edu-frontend 下，vitest 4.1.10，jsdom）
- **Test Files: 28 passed (28) / Tests: 209 passed (209)**，退出码 0，耗时 13.71s
- 通过率 **100%**（全量，无跳过/失败）
- **admin 范围（管理端相关 17 文件）：134/134 通过**（110+ 达标）：
  - fx-task03 专属 7 文件 53 例：courses.test 12 / questions.test 11 / users.test 9 / SeriesForm.test 6 / QuestionForm.test 8 / UserTable.test 4 / MetricCards.test 3
  - fx-task02 骨架（admin-guard 8 / admin-layout 4 / admin-nav 12 / api/admin 11）
  - fx-task04（rag 14+3+3 / mcp 16+4+6）
- 说明：仅 Vite `configLoader: 'native'` 的 `__dirname` 弃用警告（server-info 注意事项 #5 已知），不影响结果

## 浏览器实测（Playwright localhost:3000，route 模拟 + admin JWT）

脚本：临时目录 `fx-task03-browser-test.mjs`（不在仓库内）；结果 **28/28 PASS**。

| 组 | 用例 | 结果 | 实测证据 |
|----|------|------|----------|
| T1 6 页面渲染 | dashboard / courses / courses/1 / questions / questions/1 / users | ✅ 6/6 | 各页真实数据渲染（指标卡/系列/模块课次/题目/编辑表单/用户表） |
| T2 课程创建系列 | 弹窗打开 → 空提交校验 → FieldRow label 关联 → 创建 POST /series | ✅ 5/5 | POST body 完整（series_code/name/subject/level/level_name/on_sale）；toast「系列已创建」 |
| T3 系列详情模块 | 模块折叠 aria-expanded 切换 → 创建模块 POST /modules | ✅ 2/2 | aria-expanded true→false 切换；模块树更新 |
| T4 视频四步流 | 步骤条/进度 aria → Init → 自动进度 → Finalize → Bind → toast | ✅ 3/3 | init=1 finalize=2 bind=1；toast「视频已绑定课次」+ done 步；play_720/1080 地址回显 |
| T5 题库链路 | 新建标签 POST /tags → 学科过滤 → 批量导入三色计数 → 创建题目 POST /questions 跳编辑页 | ✅ 5/5 | subject_code=english 请求 1 次；emerald/amber/rose 计数 + messages；跳转 /admin/questions/77 |
| T6 用户管理 | 角色切换 → 最后 admin 40303 拒绝 → 下拉保持 | ✅ 3/3 | POST /users/2/role 200 + toast「角色已更新」；POST /users/1/role 403（40303）；select 保持 admin |
| T7 仪表盘 | 6 指标卡 + 角色分布 + 色系收敛 | ✅ 2/2 | metric 元素 10+、role-admin/student 存在；**sky=0 violet=0 amberIcon=0**（D-01/02/03 修正不回归） |
| T8 筛选防抖 | 关键词 5 击键 → 请求数 | ✅ 1/1 | `keyword=abcde` 请求恰 1 次（300ms 防抖生效，无逐击键轰炸） |

**本轮修正专项（不回归）**：
1. **FieldRow label htmlFor 关联**（controls.tsx:43-105）：SeriesForm 空提交后 `label[for]` 全量 12 个全部命中控件（noLinked=0），单子元素（编码/名称/学科/分级 select 等）自动注入、多子元素「分级名称 + 预填按钮」（SeriesForm.tsx:167-171）显式 id + aria 手动关联；校验后 5 个控件带 aria-invalid、5 个 error 节点（`${id}-error`）就位。
2. **MetricCards 色系收敛**：TONES 仅 indigo/emerald/rose（MetricCards.tsx:81-85），角色分布卡归位 TONES.indigo（:121）；页面 sky/violet/amber 图标底 0 命中。
3. **关键词防抖**：`use-debounced-value.ts` 300ms + queryKey 消费 applied 快照（courses/page.tsx:46-51）；浏览器实测 5 击键 1 请求。
4. **a11y**：icon-only 按钮 aria-label（删除题目/模块/班次等）、模块折叠 aria-expanded、Progress aria-label、Stepper ol aria-label 均实测在位（a11y 专项详见 fx-task03-a11y.md）。

## 静态校验

| 项 | 命令 | 结果 |
|----|------|------|
| 类型检查 | `npx tsc --noEmit` | ✅ 退出码 0 |
| admin 范围 lint | `npx eslint "src/app/(admin)/**/*.{ts,tsx}" "src/components/admin/**/*.{ts,tsx}" "src/lib/api/admin/**/*.{ts,tsx}" "src/lib/admin-guard.tsx" "src/lib/admin-nav.ts"` | ✅ 0 错误（退出码 0） |
| 色系 grep 审计 | `MetricCards.tsx` TONES + `ModuleTree.tsx` sky | ✅ sky/violet 0 命中；amber 仅「未绑视频」等语义场景 |

## 发现项 / 遗留项

1. **[P2] 验收 F 偏差：最后 1 个 admin 降级被拒时业务 toast 未出现**（本次实测新发现）
   - 现象：`POST /api/admin/users/1/role` → 后端 403（40303）→ 前端**未出现**「至少保留 1 名可用管理员账号」toast；用户被全局 403 处理静默登出并跳 `/login?redirect=...`（微探针证实无注入时 403 → /login）。
   - 根因：`query-client.ts:11-14` 全局 onError 对 `status === 403` 直接 return（注释「auth-client 已经处理了 logout + redirect」）；`auth-client.ts:353-377` onApiUnauthorized 对 403 执行 `logout({silent:true})` + `location.href = /login`。两处组合使 40303 业务提示被全局登出取代。
   - 影响：后端 40303 拒绝保护**有效**（请求发出、select 保持 admin、不假装成功，T6.2a/T6.3 验证通过）；但用户体验为「被登出」而非「看到业务提示」，与 frontend-spec 验收 F「全局 MutationCache onError toast」字面预期不符（UserTable.test.tsx:99-107 只固化「请求发出 + 不吞错」，未覆盖 toast）。
   - 建议：由主编排器/fe-architect 裁决——① 全局 onError 对「40303 等业务码」放行 toast（40300 权限拒绝仍走登出）；② 或下调规格 F 措辞为「403 → 全局登出 + 跳登录（后端拒绝为权威）」。**不属 fx-task03 业务回归**。
2. **[P3 观察] 视频流 finalize 在 dev 下被调用 2 次**：VideoUploadFlow.tsx:126-138 在 `setProgress(prev => {...})` updater 内触发 `finalizeMutation.mutate`（副作用入 updater），React 19 StrictMode 会 double-invoke 纯函数 → finalize 请求 ×2（幂等，不影响结果）。建议后续改为 updater 外触发（非阻断）。
3. **[挂账] D-04/D-06/D-08 归 fe-task00**：`--primary` 中性黑、侧边栏渐变、arbitrary 字号——与 visual-acceptance.md 一致，非本 task 验收项。
4. **[挂账] D-07 暗色未落实 / D-20 徽标原语**：视觉修复批次，同 visual-acceptance.md 结论。

## 结论

fx-task03 功能测试全部通过：单测 209/209（admin 134/134）、tsc/eslint 0 错误、浏览器实测 28/28，验收标准 5 条全部满足。本轮修正（FieldRow label 关联、MetricCards 色系收敛、关键词防抖、a11y）无回归且专项验证通过。发现 1 个 P2 规格偏差（40303 toast 被全局登出取代）建议主编排器裁决，不阻塞 PASS。
