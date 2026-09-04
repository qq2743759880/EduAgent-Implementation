# task60 完工报告 — /admin/users 管理端用户

> 执行人：前端开发者（Trae）｜阶段：P6｜并行组：W7｜工作量：M
> 日期：2026-08-24｜类型：frontend｜消费契约⑤(task14) + 响应壳⑬(task15)

## 1. 一页摘要

管理端用户页已按 **HTML 原型 admin-users.html → APPROVED → React** 重写，从 task03 的 slate 灰系改造为 **candy-playful（P17 FROZEN）**，落地契约⑤用户域三条核心链路：

- **DataTable 检索**（GWT①）：关键词搜索**防抖 400ms** + 角色/状态组合查询 + 分页（每页 10）。
- **学习详情 Dialog**（GWT②）：`查看` 打开 UserLearningDialog，GET /api/admin/users/{id}/learning 聚合 **6 指标 + 最近动态**；端点当前后端未注册 → 契约缺口**如实披露**（不写 MOCK）。
- **最后 admin 红线**（GWT③）：列表内有效 admin（role=admin 且 status=1 且 yn=1）仅此 1 个时，行内打「最后admin」徽章，编辑 Dialog 中 **降级/禁用/保存全前端禁用 + 红线条幅**；后端 40303 仍兜底拒绝（onError 显式 toast）。

## 2. 交付物清单

| 类别 | 文件 | 说明 |
|------|------|------|
| 原型 | `test-reports/fe-html/admin-users.html` | 已 APPROVED；DataTable + FilterBar(防抖400ms/组合查询/分页) + 编辑Dialog + 学习详情Dialog + 最后admin红线演示 |
| API 层 | `lib/api/admin/users.ts` | 新增 `AdminUserLearning` / `LearningActivityItem` / `getAdminUserLearning`（GET /{id}/learning，契约缺口实披露注释） |
| 学习详情 | `components/admin/UserLearningDialog.tsx` | 6 StatCard（班次/进度/观看秒→分/作业正确率/考试均分/收藏）+ 最近动态时间线；404→缺口占位 / 其余错误→LearnError 重试，无 MOCK |
| 编辑 | `components/admin/EditUserDialog.tsx` | 角色 NativeSelect + 状态分段(启用/禁用) + reason(≤255) + **最后admin红线**（禁用降级/禁用/保存 + 红线条幅）；403 family onError 显式 toast（全局 MutationCache 对 401/403 早退不弹） |
| 表格 | `components/admin/UserTable.tsx` | candy 行（头像/姓名+最后admin徽章/UID/手机/角色徽章/状态/注册/最近登录）+ 查看/编辑；lastAdmin 集合推导 |
| 页面 | `app/(admin)/admin/users/page.tsx` | 防抖 400ms + 角色/状态组合 + 分页 + 列表三态；candy 风格 |
| 旧件 | `components/admin/UserDetailDialog.tsx` | **删除**（详情入口由「查看=学习详情」取代，避免死代码与 slate 残留） |

## 3. 测试（Vitest，本任务新增 13 例）

| 文件 | 用例 |
|------|------|
| `EditUserDialog.test.tsx`（5） | 渲染默认值；角色切换 POST /role{target_role}；状态禁用 POST /status{status:0,yn:0}；**最后admin红线**（降级/禁用/保存全禁用+红线条幅）；后端 40303 兜底→onError toast.error 提示 |
| `UserTable.test.tsx`（5） | 渲染行/徽章/按钮；唯一有效 admin→「最后admin」徽章；多 admin 不标记；禁用中→「已禁用」；查看打开学习详情→GET /learning 404→契约缺口实披露 |
| `users/page.test.tsx`（3） | 初始渲染；**防抖 400ms**（250ms 窗口期不触发，400ms 后触发 keyword）；角色筛选 role_code + 分页翻页 page 透传 |

## 4. 质量门禁

| 门禁 | 结果 |
|------|------|
| CSS 纪律审计 5 项（hex/内联色/禁闭色/任意字号/灰系） | task60 源文件全 0（唯一 `slate` 命中为 `-translate-y-1/2` 已知误报；语义 token：primary-soft/candy-red/candy-purple/candy-blue 均见 globals.css） |
| Vitest 全量 | **71 文件 485 测试 PASS**（本任务新增 13；旧 users 契约 9 例不受影响） |
| TypeScript `tsc --noEmit` | 0 错误 |
| ESLint | 0 error / 0 warning |
| Next `next build` | 成功，`/admin/users` 路由注册正常（○ Static） |
| 无 MOCK / 契约对齐 | 学习详情 6 指标字段需 GET /{id}/learning 返回；端点未接线 → 缺口占位 + 字段结构预览，绝不伪造数值 |

## 5. 契约缺口 · 实披露

`GET /api/admin/users/{id}/learning`：`user_admin/router.py` 当前**未注册**该端点（现仅 list/role/status/dashboard-metrics）。前端已按 task60 契约定义字段并照常发起请求；后端开放后自动渲染真实聚合（active_cohorts_count / avg_progress_pct / total_watched_seconds / homework_accuracy_pct / exam_avg_score / favorite_count + recent_activities[]）。**待后端接线**。

## 6. 已知边界 / 后续

- **前端最后-admin 判定为 best-effort**：基于当前列表（页码内）有效 admin 计数；跨筛选/跨页的全局判定不可由列表页独立完成，权威红线仍由后端 40303 强制（前端禁用是 UX 兜底，后端拒绝恒成立）。
- **同时变更角色+状态**：保存采用「角色先行、状态随后、末次成功关窗」的串行方案，符合单次保存主导变更的交互预期。
- **忘记 validate 外部回调**：编辑保存成功即关窗并 invalidateQueries 刷新列表；若后端拒绝（非 403）由 EditUserDialog 403 分支或全局 MutationCache toast 提示。

---
> 运行 `D:\.ai-hub\sync.ps1` 分发后，等待编排者 task60=DONE 验收指令，再进入下一任务。