# K 系列收尾完成报告（C5 §8 遗留清单：K1-K4 / D2 / D3 / O2）

> 日期：2026-09-13 ｜ 分支：`feature/opt-waves` ｜ 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 验收依据：`test-reports/C5-final-acceptance.md` §8 遗留清单（K1-K4/D2/D3/O2）
> 守则遵守：禁 DB 直写（全程未写库）；冻结契约响应形状零变更（50301 脱敏、壳 `{code,message,data}` 未动）；未用 Playwright；未重启在跑的 8000/3000 服务（验证用 8010 临时实例已关闭）。
> contracts/*.json 未修改。

---

## 0. Commit 列表

| Commit | 任务 | 一句话 |
|---|---|---|
| `83ba660` | K1 | /metrics 可选 METRICS_TOKEN Bearer 门 |
| `cef769c` | K2 | JWT_SECRET_PREVIOUS 轮换窗口期旧密钥 fallback |
| `f261846` | K3 | 500 错误可选 ERROR_WEBHOOK_URL 旁路上报 |
| `bfeff8a` | K4 | refresh_token 轮换 allowlist 最小方案（Redis jti） |
| `9279dce` | D2+D3+O2 | check-demo 第⑨项 + Redis restart 实证 + deploy README 两处待验证收口 |

---

## K1（HIGH）：/metrics 公开无鉴权 → 可选 METRICS_TOKEN 门

- 改动：`app/monitoring/router.py`（SKIP_EXACT_PATHS 放行逻辑上加 Bearer 门，`hmac.compare_digest` 恒定时间比对，401 壳 40101 + `WWW-Authenticate: Bearer`）；`app/config.py` 增 `METRICS_TOKEN`；`.env.example` 同步。
- 语义：未设置 = 维持公开 + 启动 WARN（向后兼容监控抓取）；设置后无头/错头 401、对头 200。
- pytest（`tests/test_k1_metrics_token.py`）：**4 passed**（未设公开放行 / 无头 401 / 错头 401 / 对头 200）；metrics 回归 47 passed（见 K1 commit）。

## K2（MEDIUM）：JWT_SECRET 轮换 fallback

- 改动：`app/auth/service.py decode_token` 先用当前密钥验签，签名不符且配置 `JWT_SECRET_PREVIOUS` 再试旧密钥（过期语义优先：旧密钥签 + 已过期仍判 AUTH_TOKEN_EXPIRED）；签发恒用 `JWT_SECRET`；previous==当前视为未配置。
- pytest（`tests/test_k2_jwt_rotation_fallback.py`）：**6 passed**（旧 token 窗口期可验 / 未配 previous 拒 / 签发恒当前 / 双过期语义 / 自指配置拒）；test_auth_service 回归 23 passed（见 K2 commit）。

## K3（MEDIUM）：500 上报通道

- 改动：新增 `app/common/error_webhook.py`（精简载荷 `{trace_id, time, exception_type, stack 首 2000 字符}`，httpx POST 2s 超时失败静默）；`app/main.py global_exception_handler` fire-and-forget 挂接（`_ERROR_WEBHOOK_TASKS` 可 drain）。
- 语义：非 DEBUG 且设置 `ERROR_WEBHOOK_URL` 才发；DEBUG / 未设置不发。**响应契约零变更**（50301/50000 脱敏判定与形状不动）。
- pytest（`tests/test_k3_error_webhook.py`）：**4 passed**（本地捕获服务收载荷 + 契约形状断言 / 未设置不发 / DEBUG 不发 / 50301 依赖异常形状不变）；50301 契约回归 13 passed（见 K3 commit）。

## K4（MEDIUM-HIGH，行为变更已批）：refresh_token 轮换（Redis allowlist 最小方案）

- 改动：`app/auth/service.py`（refresh_token 带 `jti`=uuid4.hex；Redis `rt:{user_id}:{jti}` TTL=refresh 7 天有效期；刷新成功 Lua `_CONSUME_JTI_LUA` 原子 get+del 消费旧 jti 后登记新 jti；jti 不在 allowlist → 401 `AUTH_TOKEN_INVALID`；Redis 降级 fail-open：未初始化/读写异常跳过校验维持旧行为 + WARN）；`app/auth/schemas.py TokenData.jti`；`app/config.py JWT_REFRESH_ROTATION_ENABLED`（默认开，false=回退轮换前行为）；`.env.example` 同步。
- **行为变更声明**（已批）：
  1. 存量（无 jti 的）refresh_token 在 Redis 可用时一次性作废，用户需重新登录；Redis 降级时 fail-open 放行。
  2. 轮换开启后，每次刷新换发新 refresh_token，旧 refresh_token 立即失效（防重放）；7 天滑动过期契约外观不变（响应形状 `data.access_token/refresh_token` 未动）。
  3. `JWT_REFRESH_ROTATION_ENABLED=false` 一键回退轮换前行为（签发不含 jti、不做 allowlist 校验）。
- pytest（`tests/test_k4_refresh_rotation.py`，真 Redis，复用 H-2/task39 先例；Redis 不可用自动 skip 不造假绿）：**10 passed**
  - 轮换主流程：`test_rotation_replay_old_jti_rejected`（旧 jti 刷新后重放 401）、`test_rotation_new_token_accepted`（新 jti 可继续刷新）、`test_rotation_unknown_jti_rejected`（签名合法但未登记 jti 401）
  - 存量作废：`test_legacy_no_jti_token_invalidated_when_redis_up`
  - 降级 fail-open ×4：未知 jti 放行 / 存量放行 / register 返回 False 不阻断 / consume 返回 True 放行
  - 关轮换回退 ×2：签发无 jti / 刷新不受 allowlist 影响
- 受影响的既有测试：`tests/test_auth_service.py` 既有 refresh 用例依赖 `_get_redis_or_none()` 在单测环境（Redis 池未初始化）抛 RuntimeError → 天然 fail-open，**无需改动**；回归 **43 passed**（test_auth_service + test_k1/k2/k3 + test_metrics 合跑）。
- 契约实证（临时 8010 实例跑新代码，TEST_BASE 覆盖；**用完已关闭**）：
  - `test_contract_task15.py`（auth 登录/注册/refresh 全流程壳契约）**20 passed**
  - `test_contract_task16.py + 17.py`：11 passed 6 skipped
  - `test_contract_task113.py`：**17 passed**
  - `test_contract_task18.py`（4 failed）/ `test_contract_task19.py`（8 failed）：与 8000 旧代码基线**逐项一致**，根因均为「无可用班次」测试数据依赖，非 K4 引入（交叉验证：两文件在 8000 基线同样 4/8 failed）。
  - 备注：对 8000 在跑实例的批量回归曾出现 42900 登录限流级联，系测试自身高频登录触发（Redis 限流计数器跨实例共享），与代码无关；按模块串行 + 间隔重跑即通过。

## D2：check-demo.mjs 关键页扩清单（第 9 项）

- 改动：`edu-agent/scripts/check-demo.mjs` 新增第 ⑨ 项抽验页 `/admin-users-refine-proto.html` HTTP 200（单列第 9 项，不并入 ⑦ 核心故事线 8 页口径；FAIL 指引同前端）。
- 实证：`node scripts/check-demo.mjs --no-color` 实跑 **9/9 全绿**（⑨ 21ms PASS；⑧ DEBUG advisory 亦 PASS：无 token 被 401 拒）。

## D3：Redis 容器 restart 策略实测

- 实证：`docker inspect edu-redis-standalone --format '{{.HostConfig.RestartPolicy.Name}} {{.State.Running}}'` → **`unless-stopped true`**，已是目标策略，**无需 `docker update`**。
- 记录：`deploy/README.md` 巡检第 4 条由「未配置开机自启（待验证）」改为实证结论（容器自动拉起；Docker Desktop 本身需开机自启）；与 `deploy/docker-compose.yml` 全段 `restart: unless-stopped` 口径一致。

## O2：deploy/README.md 两处「待验证」实证收口

1. **venv 安装命令**（§2.1）：核实 `edu-agent/pyproject.toml` `[build-system]` = hatchling（wheel targets: app/services/scripts）。当前 venv 实证为 editable 安装：site-packages 含 `_editable_impl_edu_agent.pth` + `edu_agent-0.3.0.dist-info`，`pip show edu-agent` = 0.3.0。收口结论：`python -m venv .venv` → `python -m pip install -e .`（pip 按 PEP 517 自动拉取 hatchling），已写入 README 并附证据。
2. **快照建库语句**（§3③）：`deploy/backups/edu_snapshot_20260913_preR0.sql`（997,346,147 字节）全文件 grep `CREATE DATABASE` / `^USE ` 均 **0 匹配**（单库模式 dump，头部仅 `-- Database: edu` 注释）→ **不含建库语句**，恢复必须先 `CREATE DATABASE IF NOT EXISTS edu DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci` 再 `mysql -uroot -p edu < 快照`。对照组：方式一 `20260816_task00/edu_full_dump.sql` 第 22/24 行确含 `CREATE DATABASE IF NOT EXISTS edu` + `USE edu`（grep 实证）。两口径均已写入 README，**0 处「待验证」残留**。

---

## 各项 pytest 结果汇总（2026-09-13 实跑）

| 测试文件 | 结果 |
|---|---|
| tests/test_k1_metrics_token.py | 4 passed |
| tests/test_k2_jwt_rotation_fallback.py | 6 passed |
| tests/test_k3_error_webhook.py | 4 passed |
| tests/test_k4_refresh_rotation.py | 10 passed（真 Redis） |
| test_auth_service + k1-k4 + metrics 合跑回归 | 43 passed |
| 50301 契约回归（K3 commit 内） | 13 passed |
| metrics 回归（K1 commit 内） | 47 passed |
| 契约 task15/16/17/113 @8010 新代码 | 20 + 11(6 skip) + 17 passed |
| 契约 task18/19 | 4/8 failed 与 8000 基线一致（数据依赖，非本批引入） |
| check-demo.mjs 实跑 | 9/9 全绿 |

## 行为变更声明清单

1. **K1**：设置 `METRICS_TOKEN` 后 /metrics 从公开变为需 Bearer（不设则维持公开 + 启动 WARN，默认行为不变）。
2. **K2**：无（纯增可选 fallback，未配置 `JWT_SECRET_PREVIOUS` 时行为逐位不变）。
3. **K3**：无响应契约变更（可选旁路上报，默认不发）。
4. **K4**（已批）：存量 refresh_token 一次性失效需重登；刷新后旧 refresh 立即作废（防重放）；Redis 降级 fail-open 维持旧行为；`JWT_REFRESH_ROTATION_ENABLED=false` 可整体回退。
5. **D2**：check-demo 检查项 8→9（新增 ⑨ 全绿才 exit 0，演示机需可访问 admin-users-refine-proto.html）。
6. **D3/O2**：纯文档实证收口，无行为变更。
