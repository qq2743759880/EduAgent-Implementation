# task-A1 完工报告 · 可插拔 Harness 抽象（替代硬编码 6 节点图）

> 角色：EduAgent 重构项目【后端+数据库开发者】
> 依赖：task24（graph.py 现状）/ task92（子代理 runner）/ task93（skill runtime）/ task-T1（工具闭环）
> 改造依据：`.opencode/plans/production-upgrade-plan.md` P11（硬编码 6 节点图）→ 可插拔 Harness 抽象
> 状态：✅ 完成，待验收（W4 第四批 P3）

## 1. 任务目标

把 `app/ai/graph.py` 硬编码的 6 节点图重构为 **Harness 接口抽象**（route/plan/fan_out/merge/reflect/answer 节点实现可插拔），模型升级替换实现不改图结构；**保留 DAG 为默认实现**（task29 R8 `keep_sixnode` 裁定），但开放接口。

## 2. 验收结果（AC1~AC5，全部 PASS）

| AC | 要求 | 实测 | 证据 |
|----|------|------|------|
| **AC1 接口抽象** | `app/ai/harness/base.py` 含 route/plan/fan_out/merge/reflect/answer 六抽象方法，签名与现有节点一致 | ✅ | `test_contract_task_a1.py::TestAC1Interface`（3/3） |
| **AC2 默认实现等价** | `HARNESS_IMPL=sixnode` 跑 task24 全契约，行为与重构前零差异 | ✅ | task24 回归 6 passed / 1 skipped（与重构前逐字节一致）；A1 内 3 场景零差异（路由/并行 fan-out/真实 user_id/chitchat 直答） |
| **AC3 可插拔** | 注册自定义 mock harness，切换编译图，拓扑不变、节点走新实现 | ✅ | `TestAC3Pluggable`（2/2）：注册 `mock_a1` → `build_harness("mock_a1")` → 编译图拓扑签名与默认完全一致；运行后 `mock.calls == {route,plan,fan_out,merge,reflect,answer}`，`final_answer=="MOCK"` |
| **AC4 R8 裁定保留** | 默认仍 6 节点 DAG（keep_sixnode），拓扑锁定 | ✅ | `TestAC4KeepSixnode`（2/2）：`settings.HARNESS_IMPL=="sixnode"`；默认编译图节点集 = 9 节点、显式边 = 8 条、条件分支 = {route, reflect}，与 `keep_sixnode` 锁定值一致 |
| **AC5 回归** | `scripts/eval/harnesses.py` 三套 harness 不因 A1 断裂 | ✅ | `TestAC5EvalHarness`（1/1）：`harnesses.run_sixnode` 仍返回 `HarnessResult`，answer/intent 正确（接口未断裂） |

**测试汇总**：`tests/test_contract_task_a1.py` → **11 passed**（2.47s）。

## 3. AC2 task24 全回归（零差异证据）

```
tests/test_contract_task24.py: 6 passed, 1 skipped (Redis durable，环境Redis不可达跳过，与重构前一致)
tests/test_contract_task92.py + test_contract_task93.py: 21 passed (fan-out子代理 / skill registry 关联子系统无回退)
```

关键不变量全部保留：
- `nodes_executed` trace 逐节点追加、durable 续跑不重复（GWT②，契约测试覆盖）；
- effort scaling（chitchat→L0 直答，knowledge/tool/learning→L1/L2）；
- 子代理蒸馏摘要（≤ SUBAGENT_SUMMARY_BUDGET）+ artifact 引用；
- `user_id` 真实注入（无硬编码 `user_id=1`，契约测试 `test_no_hardcoded_user_id_1` 通过）；
- 图拓扑（9 节点 + 8 显式边 + route/reflect 条件分支）零变化。

## 4. AC3 插拔实测（节点级可替换验证）

实注册自定义实现并切换：

```python
register_harness("mock_a1", _MockHarness)      # 实现六抽象方法，调用时记录 mock.calls
h = build_harness("mock_a1")                    # registry 工厂按名实例化
g = graph_mod.build_graph(harness=h).compile()  # 图拓扑由 build_graph 固定，仅节点实现切换
await g.ainvoke(state, config)
# 断言：_topo_sig(g) == _topo_sig(build_graph())  且  mock.calls == 六核心
```

结论：切换 `HARNESS_IMPL` 只换节点实现，图结构（节点名/边/条件分支）完全不变 —— 满足 P11「模型升级替换实现不改图结构」。

## 5. 交付文件清单

新增：
- `edu-agent/app/ai/harness/__init__.py` — 包导出（Harness / SixNodeHarness / build_harness / register_harness）
- `edu-agent/app/ai/harness/base.py` — `Harness(ABC)` 六抽象方法（async，`(state)->dict`，签名与现有节点一致）
- `edu-agent/app/ai/harness/sixnode.py` — `SixNodeHarness`：委派 `app.ai.graph` 节点函数（**调用时动态查模块属性**，兼容 monkeypatch、行为零变化）
- `edu-agent/app/ai/harness/registry.py` — `HARNESS_IMPLEMENTATIONS` + `build_harness()` + `register_harness()`
- `edu-agent/tests/test_contract_task_a1.py` — AC1~AC5 契约测试（11 passed）

修改：
- `edu-agent/app/ai/graph.py` — `build_graph(harness=None)`：六核心节点走 `harness.*`，skill/compact/context_edit 保持模块函数；默认延迟解析 `HARNESS_IMPL`（无循环依赖）
- `edu-agent/app/config.py` — 新增 `HARNESS_IMPL: str = "sixnode"`

设计要点（零风险原则）：
- **委派而非搬运**：`SixNodeHarness` 通过 `app.ai.graph` 模块属性动态委派，复用 task24 全部节点逻辑，保证重构前后行为逐字节一致；测试仍可 `monkeypatch(app.ai.graph, "answer_node", ...)`（durable execution 复现不受影响）。
- **无循环依赖**：`graph.py` 不在模块顶层 import harness；默认 harness 在 `build_graph()` 内延迟解析。
- **扩展点开放**：`register_harness` 支持 task-E1 影子模式 / loop 候选实现 / 新模型 harness 直接插拔，不改图结构。

## 6. 技术批判 + 优化修改（竞品实证，≥3 条）

> 依据看板最高优先级规则：以真实竞品实证为唯一批判源，每条附竞品来源 + 差距 + 可落地优化。

### 批判①：Harness 仅抽象六核心节点，预处理节点仍硬编码
- **竞品实证**：Claude Managed Agents 将编排拆为 Harness(大脑)/Sandbox(双手)/Session(记忆) **三层各自独立替换**（production-upgrade-plan.md P11 引述）；Codex `codex-core` 用显式 trait 注入、无反向耦合。
- **差距**：本任务 `skill/compact/context_edit` 仍在 `graph.build_graph` 内直接调用模块函数，未纳入 Harness 接口；切换自定义 harness 时这三节点仍是 sixnode 实现。
- **可落地优化**：将 `skill/compact/context_edit` 作为 Harness 的**可选钩子**（默认 sixnode 提供，自定义可整体覆盖预处理）。但需权衡 R8 `keep_sixnode` 裁定要求「默认行为零变化」——过度抽象反增漂移风险。**建议作为 task-E1 接口扩展，不在 A1 范围**；当前委派设计已为后续真搬迁留好接缝。

### 批判②：SixNodeHarness 通过模块属性委派，harness 反向依赖 graph
- **竞品实证**：Codex `codex-core` 137 模块 Rust workspace 用 Session→Turn→Step 三级 + trait 注入，依赖方向单向（节点实现依赖接口，不反向依赖图构建器）。
- **差距**：本任务 `sixnode.py` 反向 `from app.ai import graph`，每次节点调用多一次模块属性查找，且 harness 与 graph 形成双向耦合。
- **可落地优化**：**真搬迁**——把节点函数实现直接搬入 `SixNodeHarness` 方法体，`graph.py` 退化成纯图构建器，彻底解耦。本任务选「委派」是为零风险零差异的渐进式重构；在 task24 契约全回归守门已具备的条件下，可于后续提交做真搬迁（先保持委派、加契约测试锁、再切真搬迁、再删委派）。

### 批判③：未知 HARNESS_IMPL 无降级，配置错误拖垮整图
- **竞品实证**：Codex auto-review / sandboxing 有显式 fallback + telemetry（production-upgrade-plan.md P9/P12 引述 Codex `sandbox_outcome` 遥测）。
- **差距**：`build_harness` 遇未注册 impl 直接 `raise ValueError`，导致 `build_graph` 编译失败（进程级失败），无 fail-open。
- **可落地优化**：`build_harness` 增加 **fallback 到 `sixnode` + log warning**（未知 impl 不致命）；并在应用启动时校验 `HARNESS_IMPL` 合法性（结合 task-O1 观测埋点上报配置异常）。小改动、高稳健。

### 批判④：拓扑锁定仅靠测试硬断言，无启动时 fail-fast 自检
- **竞品实证**：Claude/Codex 用 schema/类型系统约束图结构（production-upgrade-plan.md P11 引述 Harness 抽象层的结构稳定性）。
- **差距**：`keep_sixnode` 拓扑锁定依赖 `test_contract_task_a1.py` 的 9 节点/8 边硬断言；若有人改 `build_graph` 的边却漏改测试，运行时才暴露。
- **可落地优化**：抽出 `EXPECTED_SIXNODE_TOPOLOGY` 常量到 `graph.py`，供 A1 测试 **与** 应用启动自检共用；启动时 `assert 实际拓扑 == 锁定值`，拓扑漂移立即 fail-fast，把回归左移到 boot。

## 7. 与看板/关联任务

- **task29 R8 `keep_sixnode`**：本任务明确保留默认 6 节点 DAG，开放接口不推翻裁定（AC4 实测）。
- **task-E1（影子模式）**：`register_harness` 已为「sixnode vs loop 变体」对比落地直接接口。
- **task-T1 / task-M1/M2**：扩展点已注释预留——`fan_out` 工具服务可换 task-T1 闭环状态机，`memory` 子代理可换事件溯源+Redis 向量（接口注入，不硬编码）。
- 看板 `D:\.ai-hub\memory\project-handoff.md` task-A1 行建议更新为 DONE/待验收。

## 8. 后续动作

- 单 commit（保护 17 个 prior-task staged 文件）→ `sync.ps1` → 停下等验收。
- 建议下一批按批判②/③/④落地小改进（真搬迁 / fallback / 启动自检），作为 task-A1 的加固提交。
