# EduAgent 项目进度汇总（2026-08-31 重新调度基线）

> 维护者：opencode（编排者）｜依据：project-handoff.md v3.5 + 项目记忆 v3 + 独立测试实证
> 用途：tt 工作流重新调度的当前状态快照；每验收一次更新

## 1. 当前运行环境

| 项 | 值 | 状态 |
|---|---|---|
| 后端 | edu-agent，.venv，uvicorn | 8000 在线（EMBED_BACKEND=cuda） |
| 前端 | edu-frontend（Next.js），**fe-html 糖果色静态页**为入口 | 3000 在线 |
| 数据库 | MySQL edu@localhost root/123456 | OK |
| Redis | 本机 6379 可达（degraded 模式） | OK |
| VM 192.168.85.101 | Milvus/MongoDB/MinIO/Neo4j | OK |
| 8003 | 验证服务 | 未监听（非前端用，task15 测试 skip 因故） |

## 2. 前端架构（用户 2026-08-31 裁定：保持 fe-html 静态页，改后端对接）

- **入口**：根路由 `/` → `login-register.html`（糖果色静态页）；登录后按角色跳转（admin→admin-dashboard.html / student→dashboard.html）
- **对接方式**：`public/edu-api.js` 共享客户端（JWT + 壳解包 + 401 跳登录）；19 页全部注入真实数据加载（失败静默保留演示值）
- **账号**：admin=`adm02test`/`Test@123456`；student=`user000001`/`Test@123456`
- **已功能可用**：登录/看板KPI/AI助手(SSE流式)/社区列表+发帖/个人中心/课程中心/我的班次/成就/管理端6页
- **注意**：改 page.tsx/静态页后必须重启 next dev + 清 .next（dev server 不热重载入口）

## 3. 任务状态总览

### 后端（Trae）—— 主线基本收尾
**已验收 DONE**：task00~37、task92~99、task-VEC、task-P1C、task-P1L、生产级改造12项（M1/C1/C2/G1/O1/T1/S1/R1/A1/E1/M2）、P0/P1批判批次

**待办**：
- `task35`（FR-KB-03 图谱重建，Neo4j 清空后重建）← **下一后端任务**
- `task70~91`（管理端补全，部分与前端管理端页对应）

### 前端（TraeWork）
**已验收 DONE**：task40~42、44、46~60、task-NAV、page-polish、task69

**待办**：
- `task61`（/admin/rag RAG 控制台上传 Tab）：契约⑥已冻结，HTML 原型已保存，READY
- `task43`（dashboard）：React 已实现（0 MOCK），但缺完工报告/HTML APPROVED 记录——**需核对**
- `task45`（搜索）、`task78~91`（管理端页面）
- `task-FE-M1`（个人中心记忆历史/回滚）、`task-FE-O1`（管理端观测面板）

## 4. 已闭环的重大事项（近3天）

1. **task69 E2E 验收通过**（52/52）+ 前端基线入库（592c926，历史14 commit 恢复）
2. **前端替换为糖果色静态页**（e69dbde）→ 用户裁定改回 fe-html 对接后端（3e3817f）
3. **P1 接口缺陷修复**（b36e1aa）：DELETE 500→404、recommend/mindmap 500→200、死契约清理
4. **P0 检索通道修复**（EMBED_BACKEND=cuda）：dense 查询与库同用 BGE-M3，4学科召回精准命中
5. **管理端入口修复**（73dd03b）：登录按角色跳转 + 用户端导航加管理后台入口
6. **独立测试子 agent 迭代验收**：P1回归3/3、P0检索4/4、全接口冒烟27请求0 500、前端491/491

## 5. 已知遗留问题（P2/P3，非阻断）

| 问题 | 影响 | 处置 |
|---|---|---|
| DEBUG 鉴权降级（settings.DEBUG=true 无token可读用户数据） | 安全 | **部署前必须 DEBUG=False** |
| task15 契约测试 20 失败（连 8003 被拒） | 测试环境 | 起 8003 验证服务或改测试端口 |
| 前端 e2e/probe spec 11 处 tsc 预存错 | 前端 | 低优先 |
| task43 无完工报告 | 流程 | 核对是否另一会话验收 |
| task35 图谱重建未做（Neo4j 空） | RAG 图谱扩展 | **下一后端任务** |

## 6. 关键文档索引（无变化，README.md 为准）

- 看板：`D:\.ai-hub\memory\project-handoff.md`
- 计划：`.opencode/plans/dev-plan.md`（v3.4，100 任务）+ README.md
- 契约：`.opencode/handoffs/taskNN-contract.md`（①~⑭ 全生效）
- 项目记忆：`D:\.ai-hub\memory\trae-projects\EduAgent\project_memory.md`

## 7. 重新调度建议（下次派单）

1. **后端**：派 `task35`（Neo4j 图谱重建）→ 依赖 task34（已 DONE）+ Neo4j 空库
2. **前端**：派 `task61`（RAG 控制台上传 Tab，契约⑥已冻结）；或先核对 task43 状态
3. 派单前确认 8000/3000 在线；后端任务完工走 test-reports + sync.ps1
