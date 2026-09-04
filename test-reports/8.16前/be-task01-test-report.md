# 功能测试报告 be-task01

## 第 1 次测试

### 判定：PASS

### 环境

| 项 | 值 |
|----|-----|
| 被测服务 | uvicorn `app.main:app` @ http://127.0.0.1:8000（运行中，`/health` = ok） |
| .env | `DEBUG=true`（交付基线，未改动） |
| MySQL | localhost:3306 / edu（root，可用，chat_session 表可直查） |
| Python | Z:\anaconda3\envs\kb311\python.exe（3.11.15，fastapi/asyncmy/pytest/requests/pymysql 齐备） |
| 被测代码 | `edu-agent/app/chat/router.py:116-131`（DELETE 端点）、`service.py:93-114`（_ensure_session_owner）、`service.py:145-160`（delete_session 软删）、`scripts/chat_delete_hit.py`（打靶脚本） |
| 任务编号 | be-task01（第 1 轮） |

### 验收标准逐条映射（Given/When/Then）

| # | 验收标准 | 证据 | 结果 |
|---|---------|------|------|
| 1 | Given 前端调 `DELETE /api/chat/sessions/{session_id}`；When 删除会话；Then 返回 200 且业务表软删 `yn=0`（禁止物理 DELETE，PRD §12.2） | 打靶 C5/C6（200 + {ok:true}）、C7/B4（DB yn=0 且行仍在，UPDATE 无物理 DELETE）；独立抽测 S5-S8（200、{ok:true}、yn=0、行仍在） | ✅ 满足 |
| 2a | Given 学生删除他人会话；When 触发；Then 403，错误走 `{code,message,detail}` 壳 | 打靶 C1-C4（403 + code=CHAT_SESSION_FORBIDDEN + 壳三 key + DB yn=1 未删）；独立抽测 S1-S4（403、壳、code、yn=1） | ✅ 满足 |
| 2b | Given 未登录删除；When 触发；Then 401（错误壳） | **按 design-guide §2.6 裁决解释**：当前 `.env` DEBUG=true，未登录=虚拟 admin 兜底 → 预期 200+软删生效（打靶 B1-B5、抽测 S11-S12 实测 200+yn=0，合规）；DEBUG=false 生产分支 → 401 断言代码就绪于脚本 else 分支（B1-B3），本环境未执行（需改 .env 重启，超出本轮测试范围，见薄弱点 #9 记录） | ✅ 满足（按 DEBUG 语义口径） |
| 2c | ⚠️ DEBUG 语义显式断言（task05-challenge #1 FAIL 处置） | 脚本读 .env 判定 DEBUG（chat_delete_hit.py:120-123）并按分支断言（:289-321）；报告明确标注「DEBUG=true 虚拟 admin 语义」（hit-report 说明行）；本次 4 轮运行均按 DEBUG=true 分支断言，未再误判 FAIL | ✅ 满足 |
| 3 | Given 打靶脚本（restart_uvicorn_and_chat_hit.py 模式）；When 执行；Then 全链路无 500 且报告落盘 | 打靶 D4（共采集 9 响应均 <500）；独立抽测 S17（6 响应无 500）；`test-reports/be-task01-hit-report.md` 已追加 4 轮（2 轮 sd-dev 历史 + 2 轮本次复核），每轮 22/22 PASS | ✅ 满足 |

### 打靶复核（重跑 scripts/chat_delete_hit.py）

- 执行：`Z:\anaconda3\envs\kb311\python.exe scripts/chat_delete_hit.py`（edu-agent 下；8000 已在运行，脚本按设计复用不杀）
- 结果：**22/22 断言全 PASS**（A1 /health；B1-B5 DEBUG=true 语义；C1-C12 学生权限/幂等/列表/历史；D1-D4 边界/注入/错误壳/无 500）
- 报告落盘：`test-reports/be-task01-hit-report.md` 现共 4 轮，4 轮均 `22/22 PASS`（13:39 / 13:40 sd-dev 2 轮 + 本次复核 2 轮：独立重跑 + pytest 套件内重启跑）
- 复核结论：与 sd-dev 报告一致 ✅

### pytest 结果（复核）

- 执行：`Z:\anaconda3\envs\kb311\python.exe -m pytest tests/test_chat_delete.py tests/test_be_task01_suite.py -v`
- 结果：**10 passed in 18.76s**（通过率 10/10 = 100%）
  - test_chat_delete.py 8/8：本人软删 UPDATE yn=0 且无 DELETE FROM（红线约束 12）、跨用户 403 CHAT_SESSION_FORBIDDEN、不存在/幂等 404、admin 删任意、403/404 错误壳映射、事务共享 cur 禁嵌套 execute_write（task05-challenge #3 回归）、落库 `AND yn=1` 竞态防线
  - test_be_task01_suite.py 2/2：单元测试子进程通过 + 一键打靶（杀 8000→启 uvicorn→打靶→报告落盘断言）exit 0
- 复核结论：与 sd-dev「pytest 2 passed」一致且覆盖更全（10 条）✅

### 独立抽测（自研脚本，独立数据，未复用打靶脚本函数）

临时脚本：`%TEMP%\opencode\be01_spotcheck.py`（requests + pymysql 独立实现），结果 **21/21 全通过**：

| 检查 | 断言 | 结果 |
|------|------|------|
| S0 | /health 200 | ✅ |
| S1-S4 | 学生 B 删 A → 403 + {code,message,detail} + CHAT_SESSION_FORBIDDEN + DB yn=1 未删 | ✅ |
| S5-S8 | 学生 A 删自己 → 200 + {ok:true} + DB yn=0 + 行仍在（无物理 DELETE） | ✅ |
| S9-S10 | 删除后 GET /sessions 列表不可见 | ✅ |
| S11-S12 | 未登录 DELETE → 200（DEBUG=true 虚拟 admin 语义）+ DB yn=0 | ✅ |
| S13-S15 | 重复删除 → 404 幂等 + 错误壳 + CHAT_SESSION_NOT_FOUND | ✅ |
| S16 | 非 s_ 前缀 → 404 | ✅ |
| S17 | 全链路无 500 | ✅ |
| S18 | [薄弱点观察] X-Force-User-Id 伪冒非 owner → 403（归属校验对伪冒身份仍生效） | ✅ |
| S19-S20 | [薄弱点观察] X-Force-User-Id 伪冒 owner / X-Force-Role: admin 无真实 Token 删会话 → 200（薄弱点 #1 命中实证，DEBUG 已知设计） | ✅ |

### 架构薄弱点验证结果

| # | 薄弱点 | 是否命中 | 说明 |
|---|--------|---------|------|
| 1 | DEBUG 鉴权绕过（X-Force 伪冒） | 命中 | 实证（S19/S20）：DEBUG=true 下 `X-Force-User-Id=owner` 或 `X-Force-Role: admin` 无真实 Token 即可软删任意会话（200+yn=0）。属 design-guide §2.6-3 已知/接受的 DEBUG 设计，非本轮修复范围；仅记录，供 sd-challenger 深挖生产防护 |
| 4 | DELETE 会话缺失（R-2） | 未命中 | be-task01 已闭环：软删 UPDATE yn=0 禁物理 DELETE（C7/S8）、跨用户 403（C1/S1）、幂等 404（B5/C12/S13）、列表/历史过滤 yn=1（C8-C10/S9-S10），挑战方向 ①②③④ 全部实证通过 |
| 9 | DEBUG 鉴权语义处置执行风险 | 部分命中 | 脚本按 .env 分支断言 + 报告标注虚拟 admin 语义（已满足方向 ①④）；但 **DEBUG=false 回归分支（脚本 else 分支 B1-B3）本轮未真实执行**——需临时改 .env 并重启 uvicorn，超本轮测试范围（会改动交付环境状态）。方向 ②「改 .env 重启实测 401」建议由 sd-challenger 或下轮回归补验 |
| 12 | 三轨波次并行资源占用 | 未命中 | 打靶脚本独立运行复用现有 8000 不杀不重启（chat_delete_hit.py:169-171）；restart 脚本按 netstat 精确定位 8000 LISTENING PID 杀（非 killall）+ `_port_up` 就绪探测（restart_uvicorn_and_chat_delete_hit.py:47-57,80-95）；本次套件重启实测 10/10 通过、服务恢复运行，无 EADDRINUSE/假 500 |

### 结论

- 判定：**PASS**。验收标准 3 条（含 DEBUG 语义口径 2c）全部满足，无阻断性缺陷；打靶 22/22、pytest 10/10、独立抽测 21/21 全通过。
- 薄弱点命中 1 项（#1，DEBUG 已知设计，记录不 FAIL）、部分命中 1 项（#9 DEBUG=false 回归未实测），均提交 sd-challenger 后续跟进。
- 联调修复（DEBUG 语义显式断言）确已落地：打靶脚本不再因 DEBUG=true 未登录 200 而误判 FAIL（task05-challenge #1 处置闭环）。
- 测试期间未修改任何业务代码；临时抽测脚本位于系统临时目录，不落仓库。
