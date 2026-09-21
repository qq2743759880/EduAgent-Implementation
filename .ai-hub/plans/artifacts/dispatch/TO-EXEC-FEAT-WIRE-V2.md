# TO-EXEC-FEAT-WIRE-V2 — 新前端 12 缺陷修复 + 全量接线审计（v1 作废，用户裁定：新前端实测为唯一准则）

## 纪律（用户裁定，最高优先）

**一切以新前端界面（127.0.0.1:3322 + `edu-frontend/public/*.html` 黏土主题页）的功能实现情况为唯一准则**。验证证据必须=该 URL 的真实点击截图（黏土主题可见），React 侧（src/app）与任何旧路径的结论一律不采。旧界面结论禁用作"已实现"依据。

## 编排者自批（为何 v1 作废）

v1 四个弱点：①没钉死页面锚（执行者可能跑到 React/旧路径）②泛泛"枚举全部元素"而无 P0 清单 ③验证门（G1/G3）只证"接口一致/钩子存在"，不证"点了有用" ④一刀切禁改后端，但隔离/记忆类缺陷需要后端修。v2 全部修正。

## 工作流 A：用户实测 12 缺陷（P0，逐条修复+逐条实证）

| # | 缺陷（用户实测原话） | 页面 | 修复验收口径 |
|---|---|---|---|
| 1 | 视频上传无入口 | admin-course-detail.html | 会话管理区有「上传视频」入口→走真实分片管线（POST /api/admin/courses/videos/init-chunked→upload-chunk→finalize-chunked→bind-session）→上传一个 ≥1MB 测试文件成功落 /media/videos 且可播放 |
| 2 | 弹窗无法用「×」/返回关闭 | admin-question-detail.html 编辑题目弹窗 | × 与 ESC/遮罩点击均可关闭；关闭后可重开 |
| 3 | 用户管理 查看/编辑/禁用 无弹窗 | admin-users.html | 三按钮各自弹窗弹出：查看(只读详情)/编辑(表单+保存真调接口)/禁用(确认+状态变更真调接口)，CDP 点击证据 |
| 4 | RAG 集合/调参/审计日志/高级检索 无法跳转 | admin-rag-upload.html | 四个 tab 全部可切换且各自渲染真实数据（端点以 openapi.json 为准）；缺端点的 tab 诚实挂「即将上线」占位并在报告登记 |
| 5 | MCP 测试数据应删除 | DB + admin-mcp.html | 「Import 副本×N/dup1/challenge_dup」等测试 server 软删（yn=0，三核闸：备份+行数+幂等）；**硬门：清理后 pytest tests/test_permission_gate.py 与 audit_registry 对账必须全绿**（真实注册面 stdio-echodemo/sse-demo-localhost 两 server 保留）；页面只余真实 server |
| 6 | 课程回收站点击无反应 | admin-courses-recycle-proto.html | 「恢复」「彻底删除」各自真实调接口（软删恢复/硬删含二次确认），列表实时刷新 |
| 7 | 专项练习无习题加载 | practice.html | 选题型→下方复习会话真实加载错题/习题（错题接口真实数据），空数据态诚实显示「暂无错题」 |
| 8 | 管理员对话列表混入他人会话 | chat.html + 后端 | **隔离修复**：会话列表必须按当前 user_id 过滤（后端查询加过滤+测试）；admin 想看全局应另立管理视图（本单不做，登记）；验收=admin 账号 chat 列表只见自己会话，student 同理 |
| 9 | 回答完仍显示「检索知识库并思考中」 | chat.html | SSE done/error 帧后思考指示器必须消失（状态机修复），连续 5 轮问答实测零残留 |
| 10 | 流式输出未实现 | chat.html | 接 POST /api/chat/stream（body {query,session_id,stream:true}，event: start/retrieval/token/done/error，token 累加 j.delta——此契约 AGENTS.md 教训3），验收=打字机式渐进渲染 CDP 实证 |
| 11 | 跨会话记忆不生效 | 后端 memory 链路 | 诊断提取+召回链路（user_memory_event 为事实源，AGENTS 教训11）；验收=会话A说「我叫X」→新建会话B问「我叫什么」→AI 答对 X（CDP 实测截图）；若为提取规则/召回注入缺陷→后端修（授权见工作流 C）+记忆表落库证据 |
| 12 | 课程大纲点击无反应 | learning.html?cohort_id=N | 大纲节点点击展开/收起正常（不依赖「标记完成」）；标记完成仍真实写入；CDP 点击证据 |

## 工作流 B：全量接线矩阵（A 完成后）

同 v1 任务 A/B：25 页全部交互元素→wired/dead/placeholder 三分类→dead 全修/placeholder 诚实化。证据=页×元素×选择器×点击截图。

## 工作流 C：后端修复授权（按需，严格限定）

#8/#11 及矩阵盘点中确认的后端行为缺陷**授权修复**，纪律：契约权威 schemas.py/error_codes.py 不破坏响应壳；每修必配 pytest（新增或扩展）；后端改动与前端改动**分开 commit**（`fix(be)/feat-wire/...` 与 `fix(fe)/feat-wire/...`）；修复后跑 `pytest tests/ -k "chat or session or memory or permission" -q` 零回归。**安全硬约束：服务端发 URL 请求仅 http/https 且先校验 host、拒绝 localhost/环回/私有/保留地址；SQL 一律参数绑定。**

## 铁律

范围=`edu-frontend/public/*.html` + 后端按工作流 C 授权域 + DB 三核闸清理（#5）+ docs/test-reports；theme.css 禁改；不 push；每缺陷独立 commit；报告 `REPORT-FEAT-WIRE-V2.md`（12 缺陷逐条 修复前复现截图→修法→修复后截图 三段式）；3322 dev 态；token 运行时环境变量。
