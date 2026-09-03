# React 线批 3 完工报告（管理端运营与向量契约对齐 + FE-M1 门禁）

- 子 agent：React 前端执行 ｜ 归属：tt 工作流 ｜ 平台：Trae
- 范围：`edu-frontend/src/app/(admin)/admin/` 6 组路由 C-A/C-B/C-C + `/admin/rag` 上传 Tab
- 状态：**待验收**（禁 commit）

## 1. 本批交付（改动文档 + tsc + vitest 实证）

| 交付 | 契约 | 文件 |
|---|---|---|
| 系列列表分页迁移到外层 triple | C-B（task115） | `edu-frontend/src/app/(admin)/admin/courses/page.tsx`（总页数/总数改读 `data.total`，弃 `page_meta`） |
| 系列列表响应类型对齐外层 triple | C-B | `edu-frontend/src/lib/api/admin/courses.ts` `AdminSeriesListResponse{total,page,page_size,items; page_meta?兼容}` |
| 系列 C-C 删除语义（软删下架 + 回收站视图 + admin 硬删） | C-C（task116） | `courses/page.tsx` + `courses.ts`（`include_deleted`、`hard=true`）|
| RAG 上传 Tab + 导入任务跟踪 | 契约⑥ task36 | 新增 `src/components/admin/rag/UploadPanel.tsx`，集成进 `rag/page.tsx` |
| RAG 任务列表类型对齐 + 端点启用 | 契约⑥ | `src/lib/api/admin/rag.ts`（`listKnowledgeTasks` → `AdminPage<KnowledgeTaskRecord>`，status 用 `succeeded` 词表） |
| 单测：C-B 外层 triple、C-C include_deleted/hard、任务列表分页 | 契约冻结 | `courses.test.ts`（改 4 处 mock 为外层 triple）、`rag.test.ts`（+2 用例） |

共改动 6 个文件（4 改 1 新增 1 集成）。

## 2. RAG 上传 Tab 消费的客户端函数（任务指定 3 个 + 列表 1 个）
- `uploadKnowledgeFiles` → POST `/api/knowledge/admin/upload`（公共库，target=public）
- `uploadMyKnowledgeFiles` → POST `/api/knowledge/upload`（私有库，target=private，目标范围下拉切换）
- `getKnowledgeTaskStatus` → GET `/api/knowledge/status/{task_id}`（每行「刷新详情」单查）
- `listKnowledgeTasks` → GET `/api/knowledge/tasks`（任务表 5s 轮询，无活跃任务自动停）

上传面板含：拖拽/多选、前端即时校验（扩展名白名单 `.md/.txt/.markdown/.pdf/.docx` + 单文件 ≤200MB + 数量 ≤50）、合法文件计数、写操作 useMutation（L3，失败全局 toast R-7）、上传成功 invalidate `["admin","rag"]`+`["rag","tasks"]`（行数快照闭环 FR-RAG-02）。**全部真实 API，无 MOCK。**

## 3. FE-M1 门禁机验（本批路由）+ tsc + vitest
- **FE-M1（无 MOCK）**：对 `src/app/(admin)/admin/**` 全量扫描 `MOCK|mockData|dummy|空腹|假数据|seedData|sampleData|hardcoded`——命中仅为**测试文件断言名/注释（"无 MOCK"）**，无任一运行时页面硬编码假数据。✅
- **tsc --noEmit**：仅剩 `e2e/*.spec.ts`（Playwright 且 AGENTS 已禁用）的**存量**报错；本批 6 个文件 0 错误。✅
- **vitest run src/lib/api/admin + src/components/admin**：19 文件 / 143 用例全过。✅
- **semgrep（security skill 内核）**：`--config=auto --severity WARNING` 扫本批 5 个改动文件 → **0 findings**。gitleaks 可用（版本正常），前端无密钥面未执行。✅

## 4. 强制 skill 调用证据
- **frontend-browser-testing**：已调用。项目禁 Playwright（AGENTS 教训②），故以 Vitest+Testing Library 落地：UploadPanel/任务表走 UI 断言 + rag 单测补齐状态矩阵（成功/空/分页/缺省）。
- **security（semgrep）**：已调用，真实执行 semgrep SAST，0 发现（见 §3）。
- **review-bugbot**：已调用 skill；当前上下文无子 agent（bugbot）派单工具，退化为**人工自检 diff**——发现并修复 1 处 bug：`UploadPanel.addFiles` 溢出不写真实丢弃数（`overflow+=incoming.length-1` 算法误，改逐条计数）。修复后 tsc+vitest 重跑通过。

## 5. 自检（critique 三视角）
- 交互态：上传中禁用按钮+spinner；任务表活跃 pending/running 5s 轮询自动启停；单任务详情可手动刷新。
- 边界：空文件/非法扩展/超限计数 toast；任务空态/错误态有提示+重试；`page_meta` 过渡兼容不消费。
- 错误反馈：写操作统一全局 toast；单任务查询失败走 MutationCache。

## 6. 诚实披露（降级项）
- review-bugbot 无法派生子 agent（无 Task 工具），以人工 diff 自检替代，已修复 1 处计数 bug。
- e2e tsc 存量报错（Playwright spec）非本批引入，未处理（符合 AGENTS 禁 Playwright）。
- `/admin/rag` 上传 Tab 采用页内 `<section>` 布局（与既有 rag 页一致的堆叠式），未引入全局 Tabs 组件重构，保持低风险。