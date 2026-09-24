# TO-EXEC-TB4 — RAG/MCP 控制台 UX（yy 十点修复 · P1）

> 分支 `feature/opt-waves`；前端 3322 dev 态。owner 批评 3："管理端 RAG 调优控制台以及 MCP 管理我实测体验非常差"——RAG 五 tab 与 MCP 页无人引导、看不出能干什么。开工令自包含。

## 背景与现状

TA4 已清理两页遗留数据（现 net：RAG presets 3 / MCP server 1 + tools 4），脏数据因素已除，本单纯 UX。静态页顶部注释即接口契约，**对接=补 JS 数据加载，不改后端契约**。

## 工作项

1. **admin-rag*（五 tab 页）**：每个 tab 加功能说明卡（一句话+示例：这个 tab 调什么、调完看什么效果）；空态给引导文案而非白板；关键操作（如跑一次检索对比/调参保存）给 loading+结果反馈。
2. **admin-mcp.html**：① 顶部功能说明卡；② 「新增 Server」改分步引导表单（步骤条：填 code/名称 → 选 transport → 填连接参数 → 健康检查 → 保存），每步带占位示例；③ 工具列表给健康状态徽标（读 `last_health_ok`）。
3. **风格**：黏土主题一致性（`theme.css` 同版本 `?v=`、`clay-*` 类、Phosphor sprite 禁 emoji）；admin 角色守卫三段不可少。
4. **自验**：G6/G7/G9 单页跑绿（现行基线口径）；G3 `--page` 钩子登记零漂移（新增 hook 走登记流程）；不带 token 打开→跳登录；student token 打开→拒。
5. **可用性自证**：每页录一段「5 秒能说出这页干什么」的自检说明（写进报告即可，不是录屏）。

## 铁律

- 域：`edu-frontend/public/admin-rag*.html`、`admin-mcp.html`、（如需）G3 基线登记。**后端契约零改动**；禁碰 admin-infra（TB3 新页）、chat 相关、`.env`。
- 不 push；单 commit：`feat(fe)/tb4: RAG/MCP 控制台 UX(说明卡+分步引导+健康徽标)`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TB4.md`：每页改造点清单、门禁输出、空态/引导截图。

## owner 验收口径

Given owner 不读任何文档打开两页，Then 5 秒内能说出每页干什么、每个 tab 管什么，且能不靠提示自己完成一次「新增 MCP Server」引导流程。
