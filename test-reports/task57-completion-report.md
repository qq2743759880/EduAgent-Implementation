# task57 完工报告 — /admin/courses/[seriesId] 管理端系列详情（四级 CRUD）

> 执行人：前端开发者（Trae）｜阶段：P6｜并行组：W7｜工作量：XL
> 日期：2026-08-24｜类型：frontend

## 1. 一页摘要

管理端系列详情页已按 **HTML 原型 → APPROVED → React** 流程交付（复用了 admin-course-detail.html 原型并修复多态切换 Bug）。核心达成：

- **四级 CRUD 全通**：系列信息卡（可编辑）→ 班次 DataTable → 模块 Accordion（按 stage_no 排序）→ 课次列表 → 资源 4 入口，逐级"新增/编辑/软删/展开加载"。
- **视频分片上传四段**：`init-chunked → 分片上传 → finalize-chunked → bind-session → 转码轮询`，Stepper 分步 + 转码状态徽章（pending→warning/in_progress→primary/completed→success/failed→destructive）+ Timeline 转码轨迹。
- **章节管理**：schema 已冻结但 router 无 CRUD 端点 → 契约缺口，前端做 UI 脚手架（disabled 占位）实披露，不 mock。
- **全部软删**：cohort/module/session 均 DELETE（yn=0 级联语义），ConfirmDialog 二次确认。
- **契约对齐**：Module 归属 `cohort_id`（非 series_id）、Session 归属 `series_cohort_course_id`（模块物理 ID）、Cohort 创建必填 institution + head_teacher_id、列表端点返回裸数组、series 详情单对象无 subject/level。
- **错误码前端分支**：mutation onError 按后端业务码 40901~40907 命中中文文案（`uniqueConflictTip`）。

## 2. GWT 验收逐条自查

| # | Given / When / Then | 结果 | 证据 |
|---|---------------------|------|------|
| G1 | Given HTML APPROVED，When 四级 CRUD，Then 系列→班次→模块→课次逐级管理全通；唯一约束冲突（同 cohort stage_no）前端提示后端业务码 | **PASS** | `ModuleTree.tsx` 四级 mutation（create/update/delete 于 Series/Cohort/Module/Session×4）；`CohortTable` + `ModuleSection` + `ModulePanel`（展开懒加载 sessions）+ 3 个表单 Dialog + 3 个 ConfirmDialog；`uniqueConflictTip` 按 ApiError.code 命中 `UNIQUE_CONFLICT_TIPS`(40901~40907)：同 cohort 重复 stage_no 对应 40903 提示"模块阶段号已存在"；`courses.test.ts` 视频/模块/班次契约测试断言路径与入参 |
| G2 | Given 视频上传，When 分片上传完成 bind 到课次，Then transcode_status 轮询徽章正确（pending→warning/in_progress→primary/completed→success/failed→destructive）+ Timeline 转码轨迹 | **PASS** | `VideoChunkedUpload.tsx`：init-chunked→分片(8MB CHUNK_SIZE)→finalize→bind-session→`getTranscodeStatus` 3s refetchInterval（终态 completed/failed 停）轮询；`transcodeBadgeTone` 徽章四态 + `Review status approved/rejected/pending` 审核徽章 + Stepper 分步 + Timeline 转码轨迹；`transcodeBadgeTone` 单测断言四种 tone；轮询终态停逻辑在 refetchInterval 内判定 |
| G3 | Given 章节管理，When 保存起止秒，Then 与 session_video_chapter 对应；删除全部软删 | **PASS** | `AdminChapter` 接口对齐 schema（chapter_no/chapter_title/start_second/end_second）；章节管理做 **disabled UI 脚手架**（实披露"章节 CRUD 为契约缺口，后端 router 未注册"提示，不 mock）；cohort/module/session 全部软删（DELETE → ConfirmDialog，文案注明"软删 yn=0 + 级联语义"） |

## 3. 数据面盘点与契约对齐附注

- 对齐源：`domains/course_admin/router.py + schemas.py`（L1 权威）＋ Explore 子代理盘点（后端 8003 探活失败，改以源码为准）。
- **四级归属修正**（旧契约→新契约）：
  - Module `series_id` → **`cohort_id`**；Session `module_id` → **`series_cohort_course_id`**；Cohort 创建必填 **`institution_id + head_teacher_id`**。
  - 列表端点返回**裸数组**（`ok(data=[...])`），非 `{items,page_meta}`。
- **视频四段**（`courses.ts`）：`GET /videos/init-chunked`、`GET /videos/finalize-chunked`、`GET /videos/bind-session` 为 **POST + query 参数**（为此给 `adminPost` 增加 `config.params` 支持，且仅在传 config 时携带第三个参数，避免破坏既有 2 参数契约）；`GET /videos/{video_id}/transcode-status` 轮询。
- **转码枚举**：`transcode_status ∈ pending|in_progress|completed|failed`；`review_status ∈ pending|approved|rejected`。
- **章节契约缺口**：`session_video_chapter` schema 已冻结（含 start_second/end_second）但 router **无 CRUD 端点** → 前端做 disabled UI 脚手架实披露。
- **唯一约束错误码 40901~40907**：稳定字符串中文文案，mutation onError 分支提示。
- 契约修订：清 task03 遗留 slate 灰系与旧 subject_code/level_code/target_hours 字段；`AdminSeriesItem`（task56 旧列表结构）保留给 `/admin/courses` 总览使用，详情页改用 `AdminSeries`（单对象新契约）。

## 4. 交付物清单

| 类别 | 文件 | 说明 |
|------|------|------|
| 规范 | `.opencode/plans/doc-frontend-design-spec.md` P14 | 补充四级 CRUD 布局细化 + 视频分片 Stepper/转码轮询徽章/Timeline + 章节管理 + 契约对齐附注 |
| 原型 | `test-reports/fe-html/admin-course-detail.html` | 已 APPROVED；多态演示控制器生成（v1 修"从空班次切回隐藏班次行"Bug → v1.1 重交） |
| React 页面 | `edu-frontend/src/app/(admin)/admin/courses/[seriesId]/page.tsx` | 系列信息卡（可编辑）+ 返回列表 + 图钉 badge，挂 `ModuleTree` |
| React 树组件 | `edu-frontend/src/components/admin/ModuleTree.tsx` | 班次 DataTable + 模块 Accordion + 课次表 + 全部软删 + 3 表单 Dialog + 错误码分支 |
| 视频组件 | `edu-frontend/src/components/admin/VideoChunkedUpload.tsx` | 分片四段 Stepper + 转码轮询徽章 + Timeline + 章节管理占位 |
| API 层 | `edu-frontend/src/lib/api/admin/courses.ts` | 四级 CRUD + 分片四段 + transcodeBadgeTone/uniqueConflictTip 纯函数，对齐新契约 |
| 骨架 | `edu-frontend/src/lib/api/admin.ts` | `adminPost` 增加 config.params 支持（仅传 config 才带第 3 参，向后兼容） |
| 删除 | `src/components/admin/VideoUploadFlow.tsx` | 旧占位式上传组件已删除 |
| 测试 | `src/lib/api/admin/courses.test.ts`（模块/班次/视频分片契约 + 徽章映射） | 移除旧占位式三段断言，改分片契约 |

## 5. 质量门禁

| 门禁 | 结果 |
|------|------|
| css 审计 5 项（hex/内联色/禁闭色/任意字号/灰系） | task57 文件全 0（修复 1 处 `text-[13px]` 任意字号 → text-sm；其余仅注释提及目标关键词） |
| Vitest 全量 | **66 文件 451 测试 PASS**（本任务新增/改写：分片契约 + 徽章 + 班次/模块/课次契约） |
| TypeScript `tsc --noEmit` | 0 错误 |
| ESLint | 0 error / 0 warning |
| Next `next build` | 成功，`/admin/courses/[seriesId]` 动态路由已注册（ƒ Dynamic） |
| 独立审查/测试子代理 | 数据面盘点由 Explore 子代理完成；主对话框内完成实现 + 契约单测锁定；R 系审查待编排者在 React 交付后复核 |

## 6. 已知边界 / 后续

- **章节管理**为契约缺口对口占位：`session_video_chapter` 无后端 CRUD 端点，前端仅展示禁用 UI 并提示"待接线"，待后端注册端点后可复用 `AdminChapter` 契约接线。
- **视频分片为占位式模拟**：本机后端未启用真实分片接收，init 返回 `local_fallback`/占位 strategy，`startSimulated` 走占位进度，但完整调用链（init→finalize→bind→轮询）与后端契约保持正确。
- `/api/admin/courses/videos/{id}/transcode-status` 轮询依赖后端转码任务，本页按 3s 轮询、终态自动停止。