# EduAgent L4 全量回归报告

- 执行日期：2026-09-04
- 执行范围：后端接口全量回归 + DB 验收门禁 + 前端 vitest + fe-html 静态死链
- 方法：独立实证（真实 HTTP 请求 / MySQL / vitest / 静态解析），trust-but-verify，不采信旧报告
- 后端：127.0.0.1:8000（uvicorn 运行中）｜ DB：本机 MySQL
- 纪律：未改动产品代码、未 commit、未 git add

---

## 1. 证据总表

| # | 关卡 | 命令 | 断言/用例数 | 结果 | exit |
|---|---|---|---|---|---|
| 1 | 后端接口全量回归 | `interface_acceptance_final.py` | 160 请求（OK107+BIZ46+DEBUG4+BARE2+BADCODE1） | ✅ 脚本通过（但见 §2.1 盲区+独立复核） | 0 |
| 2 | DB 验收门禁 | `scripts/verify.py all` | schema 16 表 + counts 17 表(含机构切分) + quality 12 项 | ✅ 全部 PASS，0 差异 | 0 |
| 3 | 前端 vitest | `cd edu-frontend && npm test` | 76 测试文件 / 534 用例 | ✅ 全绿（0 失败） | 0 |
| 4 | 静态死链（兜底） | `test-reports/scan-deadlinks.mjs` | 21 html / 209 有效链接 | ✅ 0 死链 | 0 |

输出原始文件：
- `test-reports/l4-interface-acceptance-out.txt`（接口回归 stdout 捕获）
- `test-reports/l4-frontend-vitest-out.txt`（前端 vitest stdout 捕获）

---

## 2. 后端接口全量回归（关卡 1）

命令：`edu-agent\.venv\Scripts\python.exe -X utf8 test-reports/interface_acceptance_final.py`，输出重定向到 `l4-interface-acceptance-out.txt`。

统计（脚本自身结论）：
- TOTAL_REQUESTS = **160**
- Counter：`OK=107, BIZ=46, DEBUG=4, BARE=2, BADCODE=1`
- 正常（OK+BIZ+BARE）= **155（96.9%）**；HTTP 500 = **0**；DEBUG 降级观察 = 4；其他异常 = 1（`POST /api/admin/rag/presets` 返回 code=**40900(int)**，类型与契约要求的字符串错误码不一致）
- exit 0

生成报告：`test-reports/interface-acceptance.md`（160 个端点的 HTTP/code/判定明细附于其中，本报告不再复述）。

### 2.1 关键异常与盲区（trust-but-verify 复核结论）

**A. 验收脚本存在探测盲区**：
- 脚本对 `DELETE /api/admin/courses/{cohorts|modules|series|sessions}/{id}` 均用**不存在的 ID** 探测 → 命中 404 前置检查返回 `404 BIZ`，未覆盖"目标资源确实存在时的删除路径"。
- 生成报告 `interface-acceptance.md` 内部自相矛盾：§1 概览表格写"HTTP 500 真实缺陷 = 0"，但 §5 区块又称"存在 6 个 HTTP 500 真实缺陷"。复核两份明细表（§2/§3）均为本次真实请求结果且非 500 → 判定 **§5 为旧模板遗留（hardcoded 历史结论），不可采信**；§1 概览与 §2/§3 明细才反映本次实测。

**B. 独立 curl/HTTP 复核（已修复项）**：
| 端点 | 旧报告声称 | 本次独立实测 |
|---|---|---|
| `GET /api/recommend/next` | 500 `H.answers_json` | ✅ 200 code=0 |
| `GET /api/mindmap/me/1` | 500 `H.answers_json` | ✅ 200 code=0 |

**C. 独立立证发现的可复现真实 500（脚本漏检）**：
- `DELETE /api/admin/courses/modules/1`（存在资源）→ **HTTP 500 code="50000" msg="服务内部错误，请稍后重试"**，连续两次均复现。
- 根因线索：与历史 `name 'NotFoundError' is not defined`（未导入异常类）路径一致 —— 只在目标存在、进入删除逻辑后才触发。
- 对比：`DELETE /api/admin/courses/cohorts/1` → **200 code=0 "班次已删除"**（该路径不 500）。
- 提示：本次独立复核对既有种子数据（cohort/1、module/1）发起了真实 DELETE，属测试 DB 可接受风险；应保证重启/重建后数据自洽。

> 结论：批量脚本 exit 0 不代表无 500。至少存在 1 个"存在资源删除路径"的 HTTP 500 缺陷未被其捕获。**接口回归判定需修正为：不通过（1 个可复现 500 + DEBUG 降级风险 + 契约缺口）**。

### 2.2 其他已知非阻塞项（本次实测确认）
- **DEBUG 鉴权降级**（4 项）：无 token 调 `/api/auth/me`、`/api/users/me`、`/api/trade/orders`、`/api/favorites` 均返回 200 且给 DEBUG 虚拟 admin（user_id=1）数据 → 部署越权风险，必须 DEBUG=False（项目记忆关键教训 #6 再次证实）。
- **契约缺口**：前端源码引用但后端 404 共 5 项（`/api/admin/courses/materials/redirect-upload`、`/api/admin/questions`、`/api/admin/questions/batch-import`、`/api/admin/questions/papers/compose`、`/api/admin/questions/tags`）；另 9 项为 URL 基路径引用差异（非真缺）。后端存在但前端未用 99 项。
- 错误码类型混用（int vs str）、POST series 返回 200 非 201、mcp/health-scan 前端 15s 必超时（P3）——均非阻塞。

---

## 3. DB 验收门禁（关卡 2）

命令：`edu-agent\.venv\Scripts\python.exe -X utf8 scripts/verify.py all`

| 阶段 | 覆盖 | 结果 |
|---|---|---|
| schema | 16 表 + 关键列 | ✅ 0 差异 |
| counts | 17 表行数 vs 基线 + 6 机构切分/0 孤儿 | ✅ 0 差异 |
| quality | 12 项不变量（referential 4 + validity 3 + temporal 3 + consistency 1，含订单应付=明细求和一致性） | ✅ 0 违规（期望 0） |

结论：**三段全绿，exit 0，可发布/合并**。

---

## 4. 前端 vitest（关卡 3）

命令：`cd edu-frontend && npm test`（vitest run）
- **76 个测试文件 / 534 个用例，全部通过（0 失败）**，耗时 75s。
- 覆盖：组件（AppShell/社区/课程/quiz/learning/上传/分页/状态徽章等）、管理端（UserTable/用户页/题库/题目/系列表单/RAG/MCP）、lib（api-client 18、dashboard 38、admin、chat 14、query-client 9 等）。
- 非失败告警（stderr，仅提示级）：React `Encountered two children with the same key, "none"`（多组件、无渲染影响）、预期的 toast/query 日志、一条 `dashboard rankings scope mismatch` 日志。
- 结论：**前端单元测试全绿**。

---

## 5. 静态死链（关卡 4，兜底）

命令：`node test-reports/scan-deadlinks.mjs`
- 21 个 html，209 条有效链接，**0 死链**。各页 dead=0。（盲区已由工具注释声明：运行时变量拼接跳转不在静态判定范围，ID 动态跳转页需人工走查。）

---

## 6. 汇总结论

| 关卡 | 判定 |
|---|---|
| DB 验收门禁 | ✅ PASS（schema/counts/quality 全绿） |
| 前端 vitest | ✅ PASS（534/534） |
| 静态死链 | ✅ PASS（0 死链） |
| 后端接口全量回归 | ⚠️ **不通过**（脚本 exit 0 但漏检，独立复核证实 1 个可复现 500 + 4 项 DEBUG 降级风险 + 5 项前端引用缺端点） |

### 阻断项（先修）
1. **`DELETE /api/admin/courses/modules/{存在ID}` → HTTP 500 `code=50000`**（`NotFoundError` 未导入路径），可稳定复现；需代入 DELETE 处理，并排查 series/sessions 同类删除路径是否同根因。
2. **对外部署必须 `settings.DEBUG=False`**：否则无 token 即可读用户级数据（已实测 4 端点）。
3. 前端引用但后端缺失的 5 个端点：`/api/admin/courses/materials/redirect-upload`、`/api/admin/questions`、`/api/admin/questions/batch-import`、`/api/admin/questions/papers/compose`、`/api/admin/questions/tags`。
4. 建议修复 `interface_acceptance_final.py`：DELETE 类探测补充**存在资源**用例，避免再次漏检 500；并清理 `interface-acceptance.md` 中与新模板冲突的遗留 §5。

### 非阻塞待办
错误码统一为字符串（重点 `rag/presets` 40900 int vs 其他 str）、POST series 状态码统一 201、响应壳逐域补齐、mcp/health-scan 异步化或前端超时策略（P3）。

### 环境说明 / 跳过项
- 未做浏览器截图（遵循项目"倾向禁用 Playwright"纪律），以 vitest 单测 + 静态死链作为前端辅助证据；已蕴含 sk入场，不伪造。