# 对抗性测试报告 be-task01

## 第 1 次测试

### 判定：FAIL（一般 3 + 轻微 3；核心防御就位，无 BLOCKER）

- 测试时间：2026-08-13
- 测试方式：静态审计（chat router/service/auth dependencies + 打靶脚本源码）+ 复用 task05-challenge / be-task01-hit-report 落盘实证
- 落盘说明：本报告由主编排器依据 sd-challenger 会话完成的分析结论落盘（challenger 输出目录权限被拒，分析已 100% 完成）

---

### 问题清单

| # | 维度 | 严重度 | 位置 | 质疑 | 建议 |
|---|------|--------|------|------|------|
| 1 | 错误壳（code 值域） | 一般 | chat router/service 各错误路径 | 错误壳 `{code,message,detail}` 的 code 值域/类型不一致（部分路径 code 为业务子码、部分缺失），打靶脚本只断言 key 存在不校验值域 | 统一错误壳 code 值域契约（design-guide §4.8 全量映射），打靶脚本按路径断言具体 code 值 |
| 2 | 生产回归 | 一般 | chat_delete_hit.py DEBUG 分支 | DEBUG=false 回归断言（未登录→401）**从未真实执行**（.env 为交付基线 DEBUG=true）；脚本分支逻辑存在但未实测 | 择机切 DEBUG=false 重跑打靶验证 401 路径（be-task01 挂账 #1 同源） |
| 3 | 审计 | 一般 | chat service delete_session | 删除操作无审计日志（谁删了哪个会话何时） | 写操作审计（对齐 rag audit-log 模式），至少记录 actor/session_id/时间 |
| 4 | 字符串嗅探 | 轻微 | session_id 校验 | 错误响应差异可被用于 session_id 格式嗅探（存在性区分） | 统一 404 文案，避免存在性侧信道 |
| 5 | 格式校验 | 轻微 | router/schema | session_id 无严格格式校验（仅 s_ 前缀） | 补格式校验（长度/字符集） |
| 6 | 竞态 | 轻微 | service.py 删除与流式落库 | 删除与 LLM 流式落库并发（task05 #4）：孤儿消息行可接受 | 维持现状（task05 已评估可接受），记录 |

---

### 薄弱点核查（design-guide §7 + task05 #1-#5 复测）

| # | 薄弱点 | 防御证据 | 复测结论 |
|---|--------|---------|---------|
| 1 | DEBUG 鉴权绕过 | 打靶 B1-B5 断言（DEBUG=true 未登录 200 虚拟 admin 语义，test-reports/be-task01-hit-report.md 22/22） | 已按 §2.6 裁决处置（脚本显式断言） |
| 2 | X-Force 伪冒头 | task05 已知设计，DEBUG 模式仅 localhost 直连建议 | 维持已知设计，生产 DEBUG=false 收口 |
| 3 | 事务嵌套 | service.py:256-284 已用共享 cur（无嵌套 execute_write），sd-tester 复核 + 单测固化 | 已修复 |
| 4 | 删除与流式落库竞态 | 孤儿消息行低概率、API 不可见 | 可接受（问题 #6） |
| 5 | 文档口径漂移 | 本轮无新增漂移 | 通过 |

### 核心防御确认

- 软删 `UPDATE yn=0` 禁物理 DELETE（task05 #4 防御链完整，DB 直查 yn=0 + 行仍在）
- 归属校验 `_ensure_session_owner`（跨用户 403 + CHAT_SESSION_FORBIDDEN 子码）
- 错误壳 {code,message,detail} 三路径（403/404/500）齐备
- 幂等（重复删 404）、非 s_ 前缀 404、SQL 注入参数化安全
- 打靶脚本 22/22 PASS × 4 轮 + pytest 10/10 + 独立抽测 21/21（sd-tester 复核）

---

### 结论

无 BLOCKER。3 项一般（错误壳 code 值域统一、DEBUG=false 生产回归实测、删除审计）+ 3 项轻微进入修正环/挂账。核心防御（软删/归属/错误壳/幂等/参数化）全部就位。
