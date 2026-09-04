# EduAgent 前后端一致性优化 修改规划 PRD v1.0

> 日期：2026-09-02 ｜ 编制：ZCode 编排会话 ｜ 证据基础：`audit-20260902.md`
> 性质：对**已上线主链路**的缺陷修复与完善，不是新系统建设。上游总计划 = `.opencode/plans/dev-plan.md`（v3.4，100 任务，后端主线已收尾）；本 PRD 只覆盖"8-31 全量接入真实后端后暴露的一致性问题"。

## 1. 背景与问题定义

08-31 commit `3e3817f` 将 fe-html 糖果色静态页全量接入真实 8000 后端后，系统处于"**能打开但不能用**"状态。用户反馈四类问题，审计已全部实锤：

1. **前端交互 bug**：22 页中仅 5 页注入真实有效；2 页脚本语法错误整块失效；4 页选择器不匹配注入成 no-op；chat 页演示/真实双绑定冲突。
2. **前后端接口不匹配**：9 项契约不符（audit §3 X1~X9），含路径级（/api/learning vs /api/study）、字段级（dashboard/me 期望字段后端不返回）、壳级（裸 DTO vs 统一壳、双分页壳）。
3. **功能未完善**：注册假实现、admin-questions 整页无注入、admin CRUD 全是 alert 占位、RAG 上传页核心动作是假的（task61 未实施）、community 点赞/评论未接后端、learning 页从未接入。
4. **跳转逻辑混乱**：课程列表→详情动线完全断裂、死链、4 个孤立页、无登出、管理端无角色守卫、401 回跳缺失。

另发现后端 4 项 P0 安全缺陷（自加积分、支付 mock 回调无权限收敛、quiz 答案泄漏、契约双轨），一并纳入本期。

## 2. 目标（可验收）

| 编号 | 目标 | 验收口径 |
|---|---|---|
| O1 | **动线可用**：登录→学生端五主链路（看课/学习/练习/社区/成就）与管理端入口全部真实数据走通，无死链无孤立页 | 视觉走查 + 结构断言 + curl 实证 |
| O2 | **契约一致**：全站单一响应壳 + 单一分页 DTO + SSE error 事件生效；前端不再出现"字段猜错" | 契约冻结单 + 契约测试回归全绿 |
| O3 | **安全收敛**：gamification award、支付 mock 回调、quiz correct、metrics 鉴权、DEBUG 部署检查单 | 越权请求实测返回 401/403 |
| O4 | **功能完善**：注册/登出/重定向、admin-questions 接入、admin-courses CRUD 接线、task61 RAG 上传、learning/practice/community 真实闭环 | GWT 逐条实证 |
| O5 | **卫生达标**：演示残留/HMR 脚本/假分页/假封面清理，错误可见（不再 catch 静默吞） | grep 机验 = 0 处 |

## 3. 非目标（本期不做）

- 不做框架迁移（fe-html 静态页架构保持，React 主线另行评估）。
- 不含 task35（Neo4j 图谱重建）、task45（搜索）、task78~91 管理端批量页面——沿用既有看板另行派发。
- 不重构后端分层/中间件链（只做定点修复）。
- admin 视频分片上传保持占位（后端 stub 未实现，本期前端明示"占位"不上假数据）。

## 4. 阶段划分（对应 dev-plan 波次）

- **W0 动线阻断修复**（P0，先行）：edu-api.js 加固、2 个语法错误页、课程动线、chat 双绑定。
- **W1 契约对齐与守卫**（P1）：字段级对齐（学生端/管理端）、admin-questions 接入、登录注册/登出/redirect、角色守卫、动线杂修。
- **W2 安全与契约统一**：后端安全包、响应壳统一（契约冻结 C-A）、分页+SSE error 统一（契约冻结 C-B）、系列删除语义（契约冻结 C-C）+ admin-courses CRUD 接线、task61 RAG 上传。
- **W3 功能完善**：community、learning、practice、me/dashboard 交互闭环。
- **W4 卫生与流程收尾**：工程卫生包、task43 核对/commit 归属/测试种子/tracker 同步/DEBUG 部署检查单。

## 5. 关键决策点（需用户确认，未确认前按默认执行）

| # | 决策点 | 默认方案 |
|---|---|---|
| D1 | 响应壳是否全站统一为 `{code,message,data}`（动 recommender/mindmap/interactive/users-me 共 4 域前端消费面） | 统一（长期收益 > 一次性改动）；冻结 C-A 后前端再跟进 |
| D2 | 课程域分页 `{items,page_meta}` 是否并入全站 `{total,page,page_size,items}` | 并入（冻结 C-B）；过渡期前端读 page_meta 兼容 |
| D3 | DELETE series 语义：软删（off_sale）/硬删/回收站 | 维持软删但**响应明示"已下架"且列表默认过滤 off_sale**，文档写清（改 L2 的"假删除"感知） |
| D4 | dashboard 缺失字段（total_questions_attempted/active_courses_count）由后端扩 DashboardOut 还是前端改卡 | 后端扩（数据已有来源），随 C-A 冻结 |
| D5 | 孤儿模块 `app/admin/question_admin/` 删除还是归档 | 归档到 `_archived/`（不参与运行） |

## 6. 风险与回滚

- **契约变更级联**：C-A/C-B 触碰多域 → 冻结单先行 + 前端消费面 grep 普查 + `interface_acceptance_final.py` 回归 + 前端 vitest 491 用例回归；任一红 → 回滚该域 commit（每任务独立 commit，原子可回滚）。
- **分支纪律**：当前分支 feature/task44-courses；本期从 main 拉新分支 `feature/opt-w0`（每波次一分支），避免延续"commit 落错分支"历史问题（L13）。
- **部署安全**：合入主线前跑 task123 的 DEBUG=False 检查单（教训⑥：DEBUG=true 时无 token 即虚拟管理员）。

## 7. 验收纪律

- 接口验收：requests/curl + 既有 pytest 契约测试，**独立实证**，不采信完工报告（AGENTS.md 教训②）；禁 Playwright。
- 前端页面验收：DOM 结构断言（node/grep）+ 真渲染截图视觉验收（judge agent）双轨。
- 每任务完成 → 完工报告（test-reports/taskNN-completion-report.md）→ 测试 agent 独立复现 → 通过才 DONE。
