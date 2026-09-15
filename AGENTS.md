# EduAgent 项目记忆（ZCode）

> 同步自 D:.ai-hub\memory（唯一事实源）：`trae-projects/EduAgent/project_memory.md` + `tgent-project-memory.md`，同步日期 2026-09-03。
> 中心库更新后请重新同步本文件；本文件只保留对开发有约束力的关键事实。

## 当前架构（已稳定）

- **前端 3000** = fe-html 糖果色静态页（`edu-frontend/public/*.html`）+ `public/edu-api.js` 共享客户端（JWT + `{code:0,data}` 壳解包 + 401 跳登录）；根路由 `/` → login-register.html

- **后端 8000** = uvicorn（`edu-agent/.venv`）；8003 是验证服务非前端用

- 前端 api-client.ts 默认连 8000；CORS 3000→8000 正常

- 契约权威：后端 `schemas.py`；错误码 `error_codes.py`；响应壳 `{code:0,message:"ok",data}`；分页裸 DTO `{total,page,page_size,items}`

- fe-html 静态页顶部注释即接口契约来源——"对接后端" = 给静态页补 JS 数据加载，**不改后端契约**

## 测试账号（DB 已验证）

- admin：`adm02test / Test@123456`（另 manager：`mgr01test / Test@123456`）

- student：`user000001 / Test@123456`

## 启动命令

- 后端：`cmd /c start "" /B .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`（在 edu-agent/ 下）

- 前端：`cmd /c start /B node next\dist\bin\next dev -p 3000`

## 关键教训（必读）

1. 改 page.tsx 根路由/静态页后**必须重启 next dev + 删 .next**（dev server 不热重载入口跳转，会造出"页面不可用"假象）
2. **禁用 Playwright**；接口验收用 requests/curl/现有 pytest 契约测试，须独立实证（真实 HTTP + 数据库实测）
3. chat SSE：`POST /api/chat/stream`，body `{query, session_id, stream:true}`（字段是 query 不是 message）；解析 `event: start|retrieval|token|done|error` + `data:` 行，token 事件累加 `j.delta`（task104 curl 实测纠正，原注释写的是 token 字段已弃用）；history 返回 `data` 数组
4. 静态页注入模式：`</body>` 前 `<script src="/edu-api.js">` + IIFE，先判 `EAPI.store.getToken()` 静默降级；避免重定义全局 `$`/`renderSides` 覆盖原脚本
5. 管理端无独立登录页：登录按 `data.user.role` 跳转（admin/manager→admin-dashboard.html）；用户端导航 adminEntry 链接按角色显隐
6. **部署前必须 DEBUG=False**：settings.DEBUG=true 时无 Authorization 头会返回虚拟管理员 user\_id=1（未登录可读用户数据）
7. 向量库 P0 已修：EMBED\_BACKEND=cuda（.env 非 git 跟踪）；查询/入库 embedding 必须同为 BGE-M3
8. **真实契约优先于页面注释**：task104 curl 实测发现 chat SSE token 事件字段是 `delta` 而非注释里的 `token`——契约以 curl 实测为准，页面注释只是初稿
9. **静态页参数提取禁用正则** **`match`**：task102 修复 `match(/(d+)/)` 路径误匹配——一律走 `EAPI.pageId(name)` 包装的 URLSearchParams
10. **admin 角色守卫三段不可少**：无 token 跳登录 → 有 token 校验 `GET /api/auth/me` role∈{admin,manager} → 请求失败仍跳登录（防 DEBUG 模式降级绕过）；数据注入由 `window.bootAdmin()` 守卫通过后调用
11. **记忆落库口径（先查事件表）**：默认 `MEMORY_EVENT_ENABLED=true`（`config.py:373`）→ 事实源是 **`user_memory_event`**（append-only，工厂见 `app/ai/memory/persistence.py:212`）；**当前有效记忆的 HEAD 判据＝`valid_to IS NULL AND event_type <> 'delete'`**（`app/ai/memory/event_persistence.py:68`，新建记录 `event_type='create'`）。`user_memory` 是快照表，**行数少不等于「没落库」**，验收/排查一律先查 `user_memory_event`。实测 2026-09-16：`user_memory_event` 16 行 / `user_memory` 2 行 / HEAD 2 行

## 待办

> ✅ **2026-09-05 收口**：存量待办已全量闭环——task35（Neo4j）已由 61989bb/MySQL 图替代、task61（RAG 上传 Tab）已由 react-batch3 + 静态 admin-rag 落地、task119（learning）已由 React learning 路由实现。本批 8 任务（task33+101~109）已统一 commit。WAVE 生产批（T1/S1/R1/G1/O1/C1/C2/M1 + A1/E1/M2）独立实证闭环（6f6f57c，见 `test-reports/WAVE-critique-indep-acceptance-report.md`）。

- task103/104 降级项：cohort `accessible:true` 路径、chat SSE 登录态真实分页/历史——均已由后续批判批/Season2 实证覆盖（见 critique-backlog-tracker.md）。

- ⚠️ **环境依赖登记（实现完成，运行验证待真实环境，非代码缺口）**：~~R1-③(Redis队列削峰)~~ **已 2026-09-05 真 Redis 实证闭环**（见 `test-reports/critique-R1-3-redis-accept.md`：子 agent 真 Redis 集成 12 任务/4 worker 无丢失+并行≤limit+空队超时降级；并发现/修复 P0 FIFO 语义缺陷——`guard.py` enqueue lpush→rpush，复验 enq==deq [0..7]，registered 进 tracker）；O1-②③(OTLP 真实后端/跨实例聚合)、C1-③(冻结区监测)、C2-②(TOOL_DEFERRED 灰度) 仍待真实窗口；task39 限流/缓存/锁真 Redis 已闭环（`critique-task39-redis-accept.md`：限流 42900、缓存 322.6ms→5.3ms、锁最大同时持有=1）；task29 批判② LLM **非流式** P95(端到端 14.8~19.7s，已 2026-09-05 独立实证收口＝推理模型 deepseek-v4-flash reasoning_tokens 物理下限 + strong 402 余额不足，突破需换非推理模型，见 critique-backlog-tracker.md task29 批判②)；**流式** L1 端到端 P95 6.4s 已达标（用户裁定以流式为准）。可复跑：`edu-agent/scripts/_perf_chat_nonstream.py`、`_perf_fast_vs_strong.py`。

- 前端真实 API 引用以 `test-reports/_frontend_real_api.txt`（93 条）为准，旧的 `_frontend_api.txt` 已过时

- 接口验收报告：`test-reports/interface-acceptance.md`；可重跑脚本 `test-reports/interface_acceptance_final.py`

## TT 工作流（多 Agent 编排）

- 编排方法论 skill `tt`（**v2.6.1**，提交 `1d7e51c`，已 push GitHub `qq2743759880/tt-together-agent`）：资产整合→文档化→拆任务→任务×agent×skill×workflow×MCP 矩阵→并行派单→契约冻结→独立实证验收→强制技术批判→跨平台切换返工→批判反哺。已接入 ZCode 技能目录（junction → `D:\.ai-hub\skills\tt`），需要多平台/多 agent 编排或按"改进→重跑对应层"迭代时加载。

- **TT 9.2 前端质变 M1 质量门已落地**：`scripts/frontend-quality-gate.mjs`（248 行，8 项可机验 + 2 项主观 N/A）+ `scripts/prototype-parity-check.mjs`（184 行，token 对比 + Playwright 截图 diff）+ SKILL.md §6.1 插入 `PARITY_CHECK` 门（`HTML_APPROVED → PARITY_CHECK → REACT_DONE`）。

- **TAT 项目 R4 批次 8/8 全部闭环**（2026-09-02）：team-events / shared-scheduler / mailbox / context-handoff / session-pool / agent-registry / platform-sessions 全装配；R5 规划：R5-01 调研回源 + R5-03 插件兼容并行 → R5-02 可移植性 → R5-04 前端 → R5-05 门禁。

- TT 项目详细记忆（插件体系/能力对比/增量交接等）：`D:\.ai-hub\memory\tgent-project-memory.md`

