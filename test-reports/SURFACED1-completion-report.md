# SURFACED1-FIX 完工报告（HITL 第 4 道防线闭环 P0）

- 日期：2026-09-16
- 工程师：后端图域工程师（独立执行，单写者）
- 分支：`feature/opt-waves`（提交前 `git symbolic-ref HEAD` 已确认；提交后 `git rev-parse HEAD` 三处一致校验）
- 派单：`kickoff-SURFACED1-FIX.md`
- 对应批判：`test-reports/critique-HITL-FIX.md`（结论 FAIL，根因 = SURFACED-1：chat 路径内置写工具缺 `tool_name`） + `blind-t11-write-tool-e2e.md`

---

## 一句话结论

**P0 主链路阻断已修复并单元实证闭环**。根因 `tool_calling.py` 调 `executor.call_tool` 仅传
`tool_id=0` 不传 `tool_name` → `_resolve_builtin_name` 返回空串 → 跳过内置分支落到
`registry.get_tool_by_ref(0, None, None)` → 抛 42200「必须提供 tool_id」→ admin confirm 后
knowledge_import **零落库**。修复 = 补传 `tool_name` + executor 守卫 fail-fast +
生产上线守卫。SF-G1/G2/G3 已由**单元 + 配置级实证**一手复现通过；SF-G4（⑫ 健康门）/SF-G5 的
真实 HTTP 端到端受**测试窗口(12-14/18-next9) + 8000 门禁**约束，已交付可运行脚本与断言骨架，
待窗口内一手跑通。

---

## 关键修复（4 文件 + 1 单测 + 2 脚本）

| 文件 | 改动 | 归属 |
|---|---|---|
| `app/chat/tool_calling.py:417` | `call_tool` 调点补 `tool_name=plan.tool.tool_name` + H1 闭环注释 | kickoff 允许 |
| `app/mcp/executor.py` `_resolve_builtin_name` | `tool_id==0` 且缺 `tool_name` → 抛 42200 `AppException`（fail-fast，不再静默吞空串） | 仅该段 |
| `app/config.py` `HITL_ENABLED` 段 | 新增 `HITL_ENABLED_REQUIRED: bool = True` + `_hitl_prod_guard` 上线守卫（model_validator） | 仅该段 |
| `scripts/check-demo.mjs` | 新增 ⑫「HITL 真实性」健康门（驱动探针） | 仅 ⑫ |
| `tests/test_chat_tool_calling.py` | 新建：5 例单测 | 新建 |
| `scripts/hitl_realness_probe.py` | 新建：⑫ 探针（真实 HTTP + 只读 SQL 取证） | ⑫ 支撑 |
| `scripts/t11_surfaced1_retest.py` | 新建：T11 四场景重测脚本 | step5 支撑 |

**文件归属纪律遵守**：未触碰 `graph_stream.py` / `permission_gate.py` / R15/R15b 链。
**单写者锁** `edu-agent/scripts/eval/surfaced1.lock` 开工建、完工删。
**服务 8000 未重启**（仅用单元 + 配置级实证，未启 8010 临时实例——因其依赖真实 LLM 流式 HITL，属测试窗口门禁范畴）。

### 纪律偏差说明（HITL 上线守卫落点）
kickoff step3 写「main.py lifespan 启动检查」，但**文件归属互斥清单未含 main.py**（与其他 4 kickoff 共享，
单写者禁碰）。为尊重互斥且无损语义，守卫改落 **`config.py` 的 `_hitl_prod_guard` model_validator**
（与既有 `_debug_env_gate` 同源 fail-fast 模式，import 即拦截）。效果等价：生产环境
`ENV_NAME in (prod,production)` 且 `HITL_ENABLED=False` → `RuntimeError` 启动硬拒，无法绕开。
已在报告显式登记此偏差。

---

## 验收 GWT（编排者逐条一手复现）

### SF-G1：tool_calling 补 tool_name + 流式 confirm 真闭环（单元实证 ✅）
- 单测 `test_builtin_must_pass_tool_name`：`run_chat_tool_calls` 触发 calculator（内置 tool_id=0），
  mock executor 断言调用入参 `tool_id==0` 且 `tool_name=="calculator"` → 通过。
- 单测 `test_write_builtin_passes_tool_name`：admin 放行 knowledge_import（内置 tool_id=0），
  mock executor 断言 `tool_name=="knowledge_import"` 且 summary status=success → 通过。
- **结论**：修复后内置工具必带 `tool_name`，不再触发 42200 根因。
- 真落行（`knowledge_import_task +1`）的端到端实证见 SF-G4 / SF-G5（测试窗口门禁）。

### SF-G2：_resolve_builtin_name 缺 tool_name → 42200（单元实证 ✅）
- 单测 `test_resolve_builtin_name_raises_on_missing_tool_name`：
  `_resolve_builtin_name(0, None, None)` → `AppException` code==42200，msg 含 "tool_name" → 通过。
- 单测 `test_call_tool_builtin_requires_tool_name_surfaced1_regression`：
  `executor.call_tool(tool_id=0, tool_name=None, ...)`（旧 tool_calling 行为）→ 42200 → 通过。
- 回归防护 `test_resolve_builtin_name_real_tool_no_false_positive`：
  真实 DB 工具 `tool_id=5` / 非内置名 `add` 仍返回 `""`（不误伤）；`knowledge_import`/`calculator` 按名解析正常 → 通过。

### SF-G3：HITL_ENABLED 上线守卫（配置级实证 ✅）
用 `Settings(init kwargs)` 隔离构造验证（绕开模块级单例与 .env）：
- `ENV_NAME=prod` + `HITL_ENABLED=False` → **`RuntimeError` 启动硬拒**（msg：生产环境必须启用 HITL_ENABLED=True）→ 通过。
- `ENV_NAME=prod` + `HITL_ENABLED=True` → 正常构造，且打印 W-NEXT-2 写类告警（确认门已生效）→ 通过。
- `ENV_NAME=local` + `HITL_ENABLED=False` → 正常（本机开发体验不变）→ 通过。
- `HITL_ENABLED_REQUIRED` 默认值 = `True`。
- **本机 `.env` 登记**：`HITL_ENABLED=True`（灰度），`ENV_NAME` 缺省=local；生产部署必须显式 `HITL_ENABLED=True`，
  否则 ⑫ 健康门 / 启动守卫会 fail-fast。

### SF-G4：⑫ 健康门跑通（代码交付 ✅ / 真实运行受测试窗口门禁）
- `scripts/hitl_realness_probe.py` + `check-demo.mjs` ⑫ 已实现并语法校验通过（`node --check` / `py_compile`）。
- ⑫ 逻辑：`/health` 200 → admin 登录 → `/api/chat/stream` 触发 knowledge_import 拿 `pending_confirm`
  → `/api/chat/resume action=confirm` → 同 thread 续流 → **断言续流不再出现 42200 症状**（回归红线）。
- 模型本轮未触发 knowledge_import 时降级为 WARN（不阻断 exit，单测已覆盖修复）。
- **真实运行**：需测试窗口 + 8000 + HITL_ENABLED=True，本次未跑（窗口外）。

### SF-G5：T11 四场景重测 + 既有契约测试零回归（部分实证 ✅）
- 既有契约测试零回归（一手跑通）：
  - `tests/test_chat_tool_calling.py` + `tests/test_wnext2_write_tools.py` → **32 passed**
  - `tests/test_permission_gate.py` → **97 passed**
  - 合计 **129 passed, 0 failed**（本批改动未引入回归）。
- T11 四场景重测脚本 `scripts/t11_surfaced1_retest.py` 已交付，`--fake` 骨架跑通（1/1）；
  真实四场景（student/manager 越权零执行、admin confirm 真落行 +1、reject 零执行）受测试窗口门禁，
  待窗口内一手跑通并摘录。

---

## 批判承接核对（对照 critique-HITL-FIX.md）

| 批判点 | 本批处置 |
|---|---|
| SURFACED-1 P0 主链路阻断（tool_calling 缺 tool_name） | ✅ Step1 修复 + Step2 守卫 + 单测覆盖 |
| P0-2 HITL_ENABLED 默认 False 致写类静默失败 | ✅ Step3 上线守卫（prod+HITL=False 启动硬拒）+ ⑫ 健康门 |
| HF-G1 "confirm 真执行" 判定口径失真（call_log 而非真落行） | ✅ 单测 + T11 脚本改以 `knowledge_import_task +1` 为业务判据 |
| HF-G5 数字不实（226 vs 204） | ✅ 本报告仅列一手跑通数字（129 passed），不拼印象数 |

> 注：critique 其余 P0（P0-1 args 脱敏 / P0-3 reject 上下文进 prompt / P0-4/5 TTL 统一）属
> W-NEXT-2 后续 batch，不在本 SURFACED-1 派单范围（未触碰 graph_stream.py 等禁碰文件）。

---

## 交付物

- 代码：4 文件改动（tool_calling.py / executor.py / config.py / check-demo.mjs）
- 单测：`tests/test_chat_tool_calling.py`（5 例）
- 脚本：`scripts/hitl_realness_probe.py`（⑫ 探针）、`scripts/t11_surfaced1_retest.py`（T11 重测）
- 报告：`test-reports/SURFACED1-completion-report.md`
- 提交：路径限定 `git commit`（feature/opt-waves），`git rev-parse HEAD` 三处一致

## 待办（窗口内一手实证，非代码缺口）

1. 测试窗口内跑 `scripts/t11_surfaced1_retest.py` 真四场景，摘录 S1-S4 数字（尤其 S3 task +1）。
2. 测试窗口内跑 `node scripts/check-demo.mjs` 验证 ⑫ 绿（pending_confirm→confirm 真实可达）。
3. 上述两者通过即裁定 HITL-FIX 验收（critique 下游解锁条件满足）。
