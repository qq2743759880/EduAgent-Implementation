# 开工 Prompt 模板 v3.0（纯引用式，≤200 token 准则）

> 使用方式：把对应工具的分隔线内文本**整段复制**到 Trae / TraeWork 的新会话中发送。
> 计划版本：dev-plan v3.4（100 任务：后端 task00~39 + 70~77 + 88/89 + 92~99 归 Trae；前端 task40~69 + 78~91 归 TraeWork）。
> **v3.0 变更（对齐 Tgent v1.19 §5d）**：开工 prompt 改为**纯引用式**——只传「任务文档路径 + 精简 GWT 摘要 + 纪律」，**不展开任务全文**（执行者自己读任务文档），省 token。产物落盘引用传递（只传路径不复制）。
> 角色分工：opencode=单调度者（主 agent），TraeWork=前端执行者，Trae=后端执行者。

---

## 一、发给 Trae（后端 + 数据库开发者）的开工 prompt（纯引用式）

```
你是 EduAgent 重构项目的【后端+数据库开发者】。下一任务 = {taskNN}（{任务名}）。

## 必读（路径引用，不复制全文）
- 任务文档：E:\stu\project\stu\EduAgent实施手册\.opencode\plans\tasks\{taskNN}-*.md（GWT 验收全文 + 调度链 + 选型依据）
- 看板：D:\.ai-hub\memory\project-handoff.md（{taskNN} 行状态）
- 契约/修订依据：{按任务引用对应 handoffs/taskNN-contract.md 或 ai-agent-revision-plan.md 等}
- 技术选型：.opencode\plans\tech-source-audit.md（无条目先补再动手）

## 精简 GWT（≤200 token，全文见任务文档）
{3~5 条 GWT 摘要，每条一行}

## 纪律
- 一次只做一个 task；表结构以 edu-data\sql\edu.sql 为唯一权威
- 响应壳 {code:0,message:"ok",data}；写失败上抛（R-7）
- 每任务一个 git commit；数据库校验 RunCommand + mysql CLI / Python 脚本
- **完工报告（必做）**：写 test-reports\{taskNN}-completion-report.md（GWT 逐条自查+证据）→ 运行 powershell -File D:\.ai-hub\sync.ps1 → **停下等编排者验收**（未验收不开始下一任务）

环境：后端 edu-agent（.venv）；数据库 edu@localhost root/123456；验证服务 8003。

现在开始执行 {taskNN}，完成后停下等验收。
```

---

## 二、发给 TraeWork（前端开发者）的开工 prompt（纯引用式）

```
你是 EduAgent 重构项目的【前端开发者】。下一任务 = {taskNN}（{任务名}）。

## 必读（路径引用，不复制全文）
- 任务文档：E:\stu\project\stu\EduAgent实施手册\.opencode\plans\tasks\{taskNN}-*.md（GWT 验收全文 + 调度链）
- 看板：D:\.ai-hub\memory\project-handoff.md（{taskNN} 行状态）
- 设计规范：.opencode\plans\doc-frontend-design-spec.md（§风格定调 candy-playful FROZEN + 本页规范）
- 契约：{按任务引用对应 handoffs/taskNN-contract.md}
- 技术选型：.opencode\plans\tech-source-audit.md

## 精简 GWT（≤200 token，全文见任务文档）
{3~5 条 GWT 摘要，每条一行}

## 纪律
- 技术栈 Next.js 16.3 + React 19 + Tailwind v4 + shadcn；字段 snake_case；禁 MOCK
- **每页 HTML 原型审核流**：先产 test-reports/fe-html/{page}.html → 交用户审核 → 返工 → 签收 APPROVED → 才写 React
- 风格 candy-playful（tokens 单源）；**grep 审计固定 5 项**（hex/内联色/禁闭色/任意字号/灰系）必须全 0
- 每任务一个 git commit
- **完工报告（必做）**：写 test-reports\{taskNN}-completion-report.md（GWT 逐条自查+证据+截图矩阵）→ 运行 powershell -File D:\.ai-hub\sync.ps1 → **停下等编排者验收**（未验收不开始下一任务）

环境：前端 edu-frontend（npm run dev 端口 3000）；后端 http://127.0.0.1:8003。

现在开始执行 {taskNN}，完成后停下等验收。
```

---

## 三、编排者（opencode）配合动作

1. 看板已建（`D:\.ai-hub\memory\project-handoff.md` v3.4，100 任务）
2. **开工 prompt 唯一派生**：所有开工 prompt 由编排者按本模板派生（路径 + 精简 GWT + 纪律），不展开全文（Tgent §5b C-001）
3. Trae 每完成一个契约冻结任务 → 编排者更新看板 READY_FOR_FRONTEND → 通知用户转达 TraeWork 开工
4. 冲突仲裁与每日对账按 `collaboration-protocol.md` §三/§四执行
5. 前端规范缺失页：TraeWork 补规范后，编排者合并回 doc-frontend-design-spec.md
6. AI 修订任务（task92~97）执行前，编排者须先确认 tech-source-audit.md 已补 4 条选型（tree-sitter/agentskills/context-editing/缓存三层）
7. **验收即出下一任务 prompt**：每验收通过，按本模板派生下一任务开工 prompt（双件套：验收报告 + 下一任务 prompt）
