# task113 — 后端安全加固包

- 域：BE ｜ 平台：claude（备援 cursor）｜ 波次：W2 ｜ 依赖：无（与 task114 无文件交集可并行）
- 契约影响：**移除 quiz correct 字段属对外契约变更**，与前端 task120 组成依赖边（practice 本地判分必须先切后端判分）

## 目标
收敛 4 项 P0 越权/泄漏 + 2 项 P1 鉴权分层缺陷 + 1 项错误码冲突。

## 证据
- B1 `POST /api/gamification/me/award` 任意登录用户可自加积分（gamification/router.py:29-41）。
- B2 支付 mock 回调 `/api/trade/payment/{no}/mock-notify`、`/payment-notifications/mock` 仅登录即可调（domains/trade/payment/router.py:60-79）。
- B3 quiz `Question.correct` 下发 C 端（interactive/quiz/schemas.py:84-86）。
- P1 `/api/metrics/cache-context-dashboard|otel|trace/*` 无鉴权（monitoring/router.py:23,40,55）。
- P1 `/api/memory/admin/dream/run` 未进 AdminAuthMiddleware.ADMIN_PREFIXES（分层不一致）。
- P1 错误码 "40021" 一码两用（common/error_codes.py:81,133）。

## 改动点
1. award 端点加 `require_role([ADMIN, MANAGER])`（管理端调学员才合法）；保留函数但收敛入口。
2. mock-notify 两端点默认拒绝：仅 `settings.DEBUG=true` 或 ADMIN 角色可调（生产模拟回调走内部对账任务，不开 HTTP 入口）。
3. quiz 下发模型去掉 `correct`（及等价判分字段），判分只走 `POST /quiz/submit`；先 grep 前端 `correct` 消费面确认 task120 已切换或同 PR 切换。
4. metrics 三端点加 ADMIN 鉴权（Prometheus 抓取用独立 token 查询参数或保留 /metrics 基础指标、敏感看板收敛）。
5. `api/memory/admin` 前缀加入 ADMIN_PREFIXES。
6. COMMUNITY_REACT_INVALID 改用新码（如 40022），同步 error_codes 注册表与前端映射（前端无消费则仅改注册表）。

## GWT 验收
- Given student token，When `curl -X POST /api/gamification/me/award?delta=100`，Then 403；DB 积分不变。
- When student token 调 mock-notify，Then 403；DEBUG=False 时无角色凭证一律 401/403。
- When `curl GET /api/interactive/quiz/next`，Then 响应 JSON 不含 `correct` 键（jq 断言）。
- When 无 token 访问 /api/metrics/otel，Then 401；When student 调 `/api/memory/admin/dream/run`，Then 403。
- 回归：`python test-reports/interface_acceptance_final.py` 全绿 + 涉及域 pytest 契约测试通过；`pytest -k quiz` 判分路径正常。

## 风险
- correct 移除可能破坏内部测试/第三方消费者：验收含全仓 grep；如发现 React 主线消费，列入 C-A 契约单同步说明。
