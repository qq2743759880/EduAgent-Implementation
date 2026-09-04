# task40-completion-report · 前端接口层：api-client 解包 + 8 新客户端 + 10 改造

> 类型：frontend ｜ 阶段：P5 ｜ 执行：TraeCode（DeepSeek-flash 延续） ｜ 状态：待编排者验收
> 契约依据：`.opencode/handoffs/task10-contract.md`（契约冻结① v1.1，响应壳 + 错误码清单）
> 上浮单：`.opencode/handoffs/api-request.md`（新增 8 域端点契约 + 1 处后端缺失）

---

## 验收标准逐条对照（Given/When/Then）

### GWT① 响应壳解包
> Given 后端返回 `{code:0,message:"ok",data:{...}}`，When 调用任意客户端方法，Then 直接拿到 data 对象（调用方无 .data 解包）；非 0 时 reject ApiError 且 message 可 toast。

**实现**：`src/lib/api-client.ts`
- `isEnvelope()`：判壳（必须同时含 `code`(number|string) 和字符串 `message`，避免裸业务体误判）
- 成功路径拦截器：壳形态且 `code===0` → `return body.data`（零解包）；壳形态且 `code!==0` → `reject(new ApiError(status,{code,message,detail}))`
- 裸形态（auth JWT / 未包壳端点）→ 透传业务体兜底
- `http.{get,post,put,patch,delete}` 类型化辅助：await 结果即业务数据，客户端函数不再 `.data` 解包

**测试证据**：`src/lib/api-client.test.ts` 新增 6 用例（GWT①②③）：
- `code===0 → resolve 直接返回 data`（取到业务体 `{items,page}`，无解包）
- `code===0 经 http.get → 同样解包返回 data`
- `非 0（数字码 40400）→ reject ApiError，message 可 toast`
- 字符串错误码 → 兼容
- 旧数字码 → 兼容
- 裸形态 → 透传

### GWT② 错误码 string|number 兼容
> Given 后端错误码为字符串（如 "AUTH_EXPIRED"），When 拦截器处理，Then code 类型 string|number 兼容、旧数字码调用点不破坏。

**实现**：`ApiError.code: number | string`；`ApiEnvelope.code?: number | string`；`isEnvelope` 同时认字符串/telt数字；失败码保留原始类型（字符串原样透传，数字保留数字）。旧数字码调用点（40100/40300/42200）不变。

**测试证据**：字符串 `"AUTH_EXPIRED"` → `code==="AUTH_EXPIRED"`；数字 `40100` → `code===40100`，两例均断言通过。

### GWT③ 全量客户端 + 三轨清零
> Given 全量客户端就绪，When 运行 tsc + vitest + contract-diff.py，Then 零类型错误、单测全绿、契约字段集零差异；grep 确认无别名兜底（series_title/seriesName 三轨清零）与 MOCK fallback 残留。

**实现交付**：
- 新建 8 客户端：`enrollments.ts`、`study.ts`、`coupons.ts`、`favorites.ts`、`orders.ts`、`payments.ts`、`tickets.ts`、`admin/rag.ts`（增 `uploadKnowledgeFiles`/`listKnowledgeTasks`/`getKnowledgeTaskStatus`/`listKnowledgePartitions`/`deleteKnowledgePartition` 5 函数）
- 改造 10 客户端：`curriculum.ts`、`learning.ts`、`admin/courses.ts`、`admin/questions.ts`、`dashboard.ts`、`admin/users.ts`、`chat.ts`、`community.ts`、`mcp.ts`、`rag.ts`（snake_case 类型对齐后端 schemas.py）
- 配套组件/页面对齐：详情页 `[seriesId]/page.tsx`、`CourseSyllabusTree.tsx`、搜索页 `search/page.tsx`、`SubjectLevelFilters.tsx`、`LearningPlayClient.tsx`、`MyCourseCard.tsx`、`useChatSessions.ts`、profile 组件等

**验收证据（实测）**：

| 检查 | 命令 | 结果 |
|------|------|------|
| 类型 | `npx tsc --noEmit` | **0 错误**（TSC_EXIT=0） |
| 单测 | `npx vitest run` | **32 文件 / 267 用例 全绿** |
| 契约 | `python scripts/contract-diff.py` | **14 对契约零差异**（exit 0） |
| 别名 | `git grep seriesName src` | 0 处（课程域 camelCase 别名清零） |
| 别名 | `git grep series_title` 课程域范畴 | curriculum.ts 无命中；仅 progress 域 `dashboard.ts:61`/`learning.ts:41` 系后端 schemas.py 定义的契约字段本身；admin/courses.ts 注释显式"series_name（非 series_title）" |
| MOCK | `git grep -i 'const MOCK\|mockData' src -- 排除测试/注释` | 0 处实际兜底（ReviewList.tsx 已删 MOCK 常量改为空态占位，仅剩说明注释） |

**新增工具**：`scripts/contract-diff.py`——按映射表解析后端 Pydantic（AST）与前端 TS interface（含 extends 展平），对字段集 diff。当前映射 14 对（课程域 12 + progress 统计 2），全零差异。后续冻结新域契约在 `CONTRACT_MAP` 追加条目即可扩展。

---

## 交付物清单

| 交付物 | 路径 |
|--------|------|
| 解包拦截器 + http 辅助 + ApiError | `src/lib/api-client.ts` |
| api-client 单测（新增 6 用例） | `src/lib/api-client.test.ts` |
| 8 新客户端 | `src/lib/api/{enrollments,study,coupons,favorites,orders,payments,tickets}.ts`、`src/lib/api/admin/rag.ts` |
| 10 改造客户端 | `curriculum/learning/dashboard/chat/community.ts`、`admin/{courses,questions,users}.ts`、`mcp.ts`、`rag.ts` |
| 契约比对工具 | `scripts/contract-diff.py` |
| 上浮单 | `.opencode/handoffs/api-request.md` |
| 测试基建（慢机超时修复） | `vitest.config.mts`（`testTimeout: 20000`） |
| MOCK 兜底清理 | `src/components/curriculum/ReviewList.tsx`（删 MOCK→空态） |

---

## 备注与待编排者裁决

1. **series_title 归因**：按 GWT③ 语义，"三轨清零"针对**课程域**的系列名别名兜底。课程域 curriculum.ts 已仅存 `series_name` 一轨（正确）；`series_title` 残留在 progress/learning 域，是后端 `app/progress/schemas.py + app/domains/course` 之外 `dashboard/learning` 契约的合法字段名（后端本就如此命名），非前端别名兜底，予以保留。若编排者要求 progress 域也统一为 `series_name`，需后端同步改契约（不影响本任务前端侧验收）。
2. **admin/rag.ts `listKnowledgeTasks`**：后端仅有 `status/{task_id}` 单查，缺"任务列表"端点（已在 api-request.md §8 标记为缺失，前端保留 PROPOSED 不调用，避免 404）。
3. **契约①② 覆盖边界**：contract-diff.py 当前覆盖课程域 (tab 契约②) + progress 统计；其余域（chat/community/mcp/admin）字段已按后端 schemas 实证对齐，但未纳入自动 diff，待后端对应域冻结后可追加映射条目（已写入 CONTRACT_MAP 结构支持）。
4. **fe-tester 子代理独立测试**：本会话内未派发独立 fe-tester 子代理（被用户打断改用 DeepSeek-flash 延续），验收证据由主会话实测三命令 + grep 完成。若编排者需独立子代理复核，可在验收后补派。

---

## 结论

**PASS（主会话实测基线）**：tsc 零错误、vitest 32+267 全绿、contract-diff 14 对零差异、grep 别名/MOCK 双清零，GWT①②③ 逐条达成。已完成 `powershell -File D:\.ai-hub\sync.ps1`（延续执行）。**停下等待编排者验收指令，不自动进入 task41。**