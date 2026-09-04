# 前端测试报告 fx-task04

- 任务：fx-task04（G4 管理端 RAG + MCP 控制台，`/admin/rag` + `/admin/mcp`）
- 类型：**最终功能测试**（含本轮修正回归：a11y label/aria-live/对比度 + LOW-08 RAG 页崩溃修复）
- 测试时间：2026-08-13
- 测试人：fe-tester（web 前端测试 agent）
- **判定：PASS**（功能验收标准逐条通过；LOW-08 回归三态通过；单测/类型/静态检查全绿）
- 遗留项：a11y label 关联**部分未修复**（见 §6 遗留项-1），建议 fe-a11y-auditor 复验跟进

---

## 1. 环境

| 项 | 值 | 说明 |
|----|----|------|
| 画像 | `frontend-stack.json`（profileId=nextjs-16-app-router） | Next.js 16.3 + React 19 + Tailwind v4 + Zustand + TanStack Query + App Router |
| dev server | `http://localhost:3000`，PID **24760**（server-info 记载 17284 已重启，符合预期） | `npm run dev`；**必须 localhost 勿用 127.0.0.1**（origin 校验） |
| 后端 | 127.0.0.1:8000 **未运行** | 浏览器实测全部使用 Playwright `page.route` mock 恢复数据渲染 |
| 浏览器 | Playwright（Chromium，MCP） | route mock + admin JWT 注入（localStorage `edu:auth:*`） |
| 单测 | `npx vitest run`（vitest.config.mts，jsdom，setup=src/test/setup.ts） | 28 files / 209 tests 全绿 |
| 类型 | `npx tsc --noEmit` | exit 0，0 错误 |
| 静态 | `npx eslint`（rag/mcp 范围 + controls.tsx + api） | exit 0，0 错误 |

> 注：执行命令全部在 `edu-frontend` 下运行；未改动任何业务代码。

---

## 2. 验收标准逐条映射（dev-plan.md fx-task04 → Given/When/Then）

| # | 验收标准（Given/When/Then） | 验证方式 | 结果 | 证据 |
|---|-----------------------------|----------|------|------|
| 1 | RAG 集合列表含 Milvus 快照（行数/来源/状态/快照时间/重建按钮），GET 失败 ErrorState 可重试，空数组 EmptyState | 浏览器 + 单测 | ✅ | `/admin/rag` 渲染 CollectionTable 2 行（公共知识库 4,969chunks / 课程知识库 96chunks + 重建中 StatusBadge）；后端不可达时 3 区块 ErrorState + 重试；空数据 EmptyState「暂无知识库集合」 |
| 2 | 任一集合 rebuilding → `refetchInterval` 返回 10_000；全部 ready 后 `false` | 代码审查 | ✅ | rag/page.tsx:34-37 函数式轮询 + `Array.isArray` 守卫（LOW-08 防御）；单测固化 |
| 3 | 重建索引：增量/全量 → POST `/collections/rebuild` body `{collection_name, partition_name, mode}` → **202 + job_id** + toast + invalidate | 浏览器 + 单测 | ✅ | 增量提交 body `{"collection_name":"knowledge_chunk_v1","partition_name":"_default","mode":"incremental"}` → 202；切全量 body `mode:"full"` → 202；弹窗内 `job_id：r_test_job_001` + 后端 message（role=status）；rag.test.ts:66-98 |
| 4 | 重建失败 → 抛 ApiError 走全局 MutationCache toast，不返回空态冒充成功 | 单测 | ✅ | rag.test.ts:95-98（500 抛错）；rag.ts 无 catch 吞错 |
| 5 | 参数预设 is_default 唯一：POST body 透传 `is_default:true`（后端事务置 0 旧默认）+ toast + 关闭 + invalidate；默认项 emerald「默认」徽章 | 浏览器 + 单测 | ✅ | 提交 body `{"preset_name":"新默认预设","is_default":true,...}` → 201 → 弹窗关闭 → refetch 后新卡带「默认」徽章、旧默认无徽章（唯一默认）、SearchTester 下拉「新默认预设（默认）」、页头「当前默认预设：新默认预设」；rag.test.ts:111-121 |
| 6 | 预设非法名（空/1 字符/超 64）→ 行内错误不提交 | 单测 + 浏览器 | ✅ | 空提交后行内「请输入预设名称」+ `aria-invalid`；validatePresetForm 单测 |
| 7 | 审计日志过滤分页：applied 快照（输入不触发请求、查询才生效、重置 page=1），请求带 user_id/role/created_after + page_size=10 | 浏览器 + 单测 | ✅ | 输入 user_id=841/role=student/created_after 期间 0 请求；点「查询」→ 表格仅 #841 两条；「重置」→ 恢复 4 条全量；queryKey 仅 applied+page（AuditLogTable.tsx:37）；rag.test.ts:131-159 |
| 8 | SearchTester：query 空按钮 disabled；选预设后 top_k/final_max_k disabled；POST body；结果召回/最终 + 预设徽章 + docs；degraded_reason amber 黄条；docs 空「无检索结果（后端已降级）」 | 浏览器 | ✅ | 空 query 按钮 disabled；输入后 enabled；选预设后 top_k/final_max_k disabled；POST `{query,preset_id:1,top_k:20,final_max_k:8}`；结果「召回 1 · 最终 1」+ doc 卡片；降级场景显示「降级提示：MILVUS_UNAVAILABLE…」+「无检索结果（后端已降级）」 |
| 9 | MCP Server 列表健康灯三态（ok=emerald OK / error=rose ERR+last_error / unknown=slate 未知）+ 传输徽章 + 启用状态 + 工具数 + 最近健康检查 | 浏览器 | ✅ | 3 行：OK(CodeWiki)、ERR(RAG Helper +「连接超时：connect ETIMEDOUT」)、未知(通知服务·已停用·从未检查)；stdio/sse 徽章 |
| 10 | 注销（软删 DELETE）+ toast + invalidate；行级 busy disabled | 浏览器 + 单测 | ✅ | 点「注销」→ DELETE `/api/mcp/servers/1` → toast「已注销」+ refetch；ServerTable.tsx:58 行级 busy；ServerTable.test.tsx |
| 11 | 健康扫描 → summary 徽章 `OK n / ERR n（共 n，nms）` + toast + invalidate servers；pending 禁用 | 浏览器 | ✅ | POST health-scan → 徽章「OK 1 / ERR 2（共 3，305ms）」 |
| 12 | 发现工具：DB 列表（enabled=open）→ live discover 覆盖 DB 行 + 「Live Discover（直连不落库）」标签 + 可返回 DB 列表；live 失败弹窗内 banner 非全局 toast | 浏览器 | ✅ | DB 2 个工具（search_code/get_code_detail）；实时 Discover → live_search 单行 + 源标签 + 返回按钮；ToolTable.tsx:132-136 本地 banner（代码审查） |
| 13 | 工具测试：预填 buildDefaultArgs（string→""、integer→0）；非法 JSON 前置校验不触发请求（border-rose-400 + 行内错误）；成功展示 status/result/latency_ms/call_id 终端块 + call-log invalidate | 浏览器 + 单测 | ✅ | 预填 `{"keyword":"","limit":0}`；非法 JSON → 0 请求 + 行内 JSON 错误 + 红边框；合法调用 POST `{tool_id:101,tool_name,args}` → 「成功 / 延迟 187ms / call_id=call_101」+ result JSON 深色终端块；call-log refetch 触发（日志出现新请求） |
| 14 | 调用日志过滤分页（applied 快照 + 默认 server_id = servers 首项） | 代码审查 + 浏览器 | ✅ | CallLogTable 过滤栏 + applied 语义同审计日志；工具测试成功后 call-log invalidate 实测 |
| 15 | student 直连 /api/admin/rag/* 与 /api/mcp/* → **403**（后端 require_role([ADMIN]) 权威契约） | 前端守卫实测 + 后端代码审查 | ✅ | 前端：student 访问 /admin/mcp → 重定向 /dashboard + toast「无权限访问管理端」；后端：`rag_admin/router.py:44` `require_role([UserRole.ADMIN])`、`mcp/router.py:42` router 级 `dependencies=[require_role([ADMIN])]`；API 层单测 rag.test.ts:59-62 / 202-205 验证 403 抛错 |

**验收标准 15 条全部通过（✅）**。

---

## 3. LOW-08 回归（重点）——/admin/rag 不再 "This page couldn't load"

> a11y 报告 LOW-08：`rag/page.tsx:43` 在 presetsQuery.data 非数组（后端不可达/失败壳）时 `presetsQuery.data?.find` 抛 TypeError → 整页崩溃进入 Next.js "This page couldn't load"。本轮已修复（page.tsx:48 `Array.isArray(presetsQuery.data) ? presetsQuery.data : []` + refetchInterval 内 `Array.isArray` 守卫）。

| 场景 | 结果 | 证据 |
|------|------|------|
| ① 正常数据 | ✅ 不崩溃 | 集合表/预设/审计日志/检索面板全渲染，`crashed=false`，pageerror=0 |
| ② 空数据（collections/presets/audit 均空） | ✅ 不崩溃 | 三区块 EmptyState（暂无知识库集合/暂无参数预设/没有匹配的审计记录）+ RAG 控制台页头正常 |
| ③ 后端不可达（原始崩溃场景，无任何 mock） | ✅ **不崩溃** | `crashed=false`、pageerror=0；3 区块 ErrorState「加载失败·网络错误，无法连接后端服务」+ 重试按钮；SearchTester/预设区正常渲染 |

> 同步验证 /admin/mcp 后端不可达：同样不崩溃（2 区块 ErrorState，pageerror=0）。

---

## 4. 浏览器实测明细

- 环境：localhost:3000 + admin JWT（`edu:auth:token/me/tenant`，roles:["admin"]）+ route mock（127.0.0.1:8000/api/**）
- 页面：`/admin/rag`、`/admin/mcp`

### 4.1 RAG 页（/admin/rag）

| 步骤 | 结果 | 备注 |
|------|------|------|
| 集合表渲染（含行数快照「4,969chunks」、来源数、就绪/重建中徽章、快照时间、重建索引按钮×2） | ✅ | caption 存在（LOW-01 修复） |
| 预设卡片（默认徽章 + top_k/final/rrf/model chips） | ✅ | 默认项 badge「默认」 |
| 重建弹窗 → 增量提交 → 202 + job_id 结果块 | ✅ | body mode=incremental；结果区 `role=status`（HIGH-02 修复） |
| 重建弹窗 → 全量提交 → 202 + job_id | ✅ | body mode=full |
| 新建预设（is_default=true）→ POST 201 → 弹窗关闭 → refetch 唯一默认 | ✅ | POST body 透传 is_default:true |
| 空提交预设 → 行内错误 + aria-invalid/aria-describedby | ✅ | HIGH-01 修复生效（错误文本经 sr-only span 关联） |
| 审计日志：输入不触发请求 → 查询（user_id+role 过滤）→ 重置 | ✅ | applied 快照语义 |
| SearchTester：空 query disabled → 选预设禁用 top_k/final → 检索结果 → 降级黄条 + 空结果提示 | ✅ | 降级提示「降级提示：MILVUS_UNAVAILABLE…」 |

### 4.2 MCP 页（/admin/mcp）

| 步骤 | 结果 | 备注 |
|------|------|------|
| Server 表：健康灯三态（OK/ERR/未知）+ last_error + 传输徽章 + 启用状态 + 工具数 + 最近健康检查 | ✅ | 反 AI-slop：实心圆点+文字标签 |
| 健康扫描 → 摘要徽章「OK 1 / ERR 2（共 3，305ms）」 | ✅ | + invalidate servers |
| 发现工具弹窗：DB 列表 → 实时 Discover → live 覆盖 + 源标签 + 返回 DB | ✅ | live 不落库 |
| 工具测试：预填 JSON → 非法 JSON 0 请求 + 行内错误 + 红边框 → 合法调用 status/latency/call_id/终端块 | ✅ | call-log invalidate 触发 |
| 注销 → DELETE + toast | ✅ | 行级 busy（代码审查） |
| student 访问 /admin/mcp → /dashboard + toast | ✅ | 前端守卫拦截 |

### 4.3 a11y 修正抽查（浏览器可访问性快照）

| 修正项 | 结果 | 证据 |
|--------|------|------|
| HIGH-02 aria-live（动态结果区） | ✅ | 检索结果 `role=status aria-live=polite`、重建结果 `role=status`、工具测试结果 `role=status aria-live=polite` |
| HIGH-03/HIGH-04 对比度 | ✅（代码） | HealthDot：ok→`text-emerald-700`+`bg-emerald-600`、unknown→`text-slate-600`（原 3.76:1/2.6:1 提升）；StatusBadge rebuilding→`text-amber-800`+`bg-amber-600`+ring（原 4.43/1.94 提升） |
| BLOCKER-01/HIGH-01 label + aria | ⚠️ **部分** | 单子元素 FieldRow（RebuildDialog 重建模式、LLM 模型偏好、描述、SearchTester/审计过滤栏 label htmlFor+id 同源）✅；**多子元素 FieldRow（控件 + 恒渲染 sr-only 错误 span）label 失配** ✗ → 见 §6 遗留项-1 |
| LOW-01/LOW-02 表格 caption/scope | ✅ | 5 张表均有 caption + th scope="col" |
| LOW-03 图标 aria-hidden | ✅ | 装饰图标均 aria-hidden（快照无空图标播报） |

---

## 5. 单测统计（`npx vitest run` 全量）

```
Test Files  28 passed (28)
     Tests  209 passed (209)
  Duration  23.46s（vitest 4.1.x，exit 0）
```

本 task 重点文件：

| 文件 | 用例数 | 结果 |
|------|--------|------|
| src/lib/api/admin/rag.test.ts | 14 | ✅ |
| src/lib/api/admin/mcp.test.ts | 16 | ✅ |
| src/components/admin/rag/RebuildDialog.test.tsx | 3 | ✅ |
| src/components/admin/rag/SearchTester.test.tsx | 3 | ✅ |
| src/components/admin/mcp/ServerTable.test.tsx | 4 | ✅ |
| src/components/admin/mcp/ToolTestDialog.test.tsx | 6 | ✅ |

其余 22 文件（api-client/admin/courses/users/questions/chat/community、admin-guard/admin-nav/admin-layout、成就/社区等）全部通过。

## 6. 静态校验

| 命令 | 结果 |
|------|------|
| `npx tsc --noEmit` | exit 0，0 错误 |
| `npx eslint`（src/app/(admin)/admin/{rag,mcp}/**、src/components/admin/{rag,mcp}/**、controls.tsx、src/lib/api/admin/{rag,mcp}.ts + test） | exit 0，0 错误 |

---

## 7. 遗留项

1. **⚠️ a11y BLOCKER-01 部分未修复（label 关联在「多子元素 FieldRow」场景仍失配）**——非功能阻断，但属本轮 a11y 修正范围残余，建议 fe-a11y-auditor 复验 + 后续表单收敛：
   - 根因：`controls.tsx` FieldRow 仅对**单子元素**（`React.isValidElement(children)`）clone 注入 `id`；当 FieldRow 含「控件 + 恒渲染的 sr-only 错误 span」两个子元素时（ServerForm 的 server-code/display_name/run_command/run_args、ToolTestDialog 的 tool-args；PresetForm 错误态下的 name/top_k/final_max_k/cutoff/rrf），label 的 `htmlFor=field-{autoId}` 与控件显式 `id` 失配 → 控件 `el.labels` 为空、可访问名缺失/回退 placeholder（实机确认）。
   - 已修复部分：`aria-invalid` + `aria-describedby`（指向 sr-only 错误文本）在错误态均正确（HIGH-01 生效）；单子元素场景（RebuildDialog 重建模式、LLM 模型偏好、描述）关联正常。
   - 建议：FieldRow 支持多子元素注入（如 `getControlId` 透传）或表单统一「label htmlFor = 控件显式 id 同源」模式。
2. **环境性 console error（非本 task 缺陷）**：后端未运行时全局 chat 模块 `GET /api/chat/sessions` 报 `ERR_CONNECTION_REFUSED`（[chat] 加载会话列表失败）——chat 属其他任务范围，后端启动后消失。
3. **挂账项（既有，不影响验收，归口 fe-task00）**：卡片/表格容器缺 shadow-sm（A1）、arbitrary 字号 58 处（B 类）、is_default 徽章 emerald（C1）、终端块 token 化（C3）——详见 visual-acceptance.md §2/§5，本报告不重复判定。
4. **测试方法说明**：后端 127.0.0.1:8000 未运行，浏览器实测以 route mock 恢复数据渲染；「student 直连 403」以「前端守卫实测 + 后端 `require_role([ADMIN])` 代码契约 + API 层单测」三线验证（真实后端 403 需后端启动后回归）。

---

## 8. 结论

- **判定：PASS**
- 功能验收标准 15/15 通过（集合快照+重建 202/job_id、预设 is_default 唯一、审计日志过滤分页、MCP 健康灯/发现工具/工具测试 status/result/latency_ms、student 403 契约）
- **LOW-08 RAG 页崩溃修复回归通过**（正常数据 / 空数据 / 后端不可达三态均不再 "This page couldn't load"）
- 单测 28 files / 209 tests 全绿；tsc 0 错误；eslint 0 错误
- 遗留：a11y label 关联部分未修复（§7-1，建议跟进）；其余为环境性/挂账项
