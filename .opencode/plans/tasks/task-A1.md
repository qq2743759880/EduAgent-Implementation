# task-A1 — 可插拔 Harness 抽象（替代硬编码 6 节点图）

> 执行工具：**Trae** ｜ 依赖：task24（现状 graph.py）, task92/93（子代理 runner） + task-T1 ｜ 状态：TODO
> 修订来源：`.opencode/plans/production-upgrade-plan.md` P11（硬编码 6 节点图）
> 核心定位：把 `app/ai/graph.py` 的 6 节点图硬编码重构为 **Harness 接口抽象**（route/plan/fan_out/merge/reflect/answer 各节点实现可插拔），模型升级替换实现不改图结构；**保留 DAG 为默认实现**（task29 R8 keep_sixnode 已裁定），但开放接口。

## 1. 任务卡片

- **类型/工具**：backend（AI 编排抽象） / Trae
- **依赖**：task24（`graph.py` 现状：6 节点 + PlainRedisSaver + effort scaling）、task92（子代理 runner）、task93（skill runtime 渐进式披露）、task-T1（工具闭环状态机作为 tool 节点实现）
- **并行组**：W4（第四批 P3，与 task-E1/M2 并行）
- **工作量**：**L**
- **测试窗口纪律**：接口/图拓扑/默认实现逻辑随时可测；新实现（自定义 harness）真实 LLM 验证仅窗口内

## 2. 选型依据（竞品实证，引用 production-upgrade-plan.md）

| 竞品 | 做法 | 参考 URL |
|---|---|---|
| **Claude Managed Agents** | Harness(大脑)/Sandbox(双手)/Session(记忆) 三可独立替换抽象层 | production-upgrade-plan.md P11 引述 |
| **Codex** | codex-core 137 模块 Rust workspace，Session→Turn→Step 三级模型 | production-upgrade-plan.md P11 引述 |

## 3. 实现规划要点

### 3.1 Harness 接口（新增 `app/ai/harness/`）

- 新增 `app/ai/harness/base.py` 定义抽象基类：

```python
class Harness(ABC):
    """可插拔编排抽象：节点级实现可替换，图结构不变。"""
    @abstractmethod
    async def route(self, state) -> dict: ...
    @abstractmethod
    async def plan(self, state) -> dict: ...
    @abstractmethod
    async def fan_out(self, state) -> dict: ...
    @abstractmethod
    async def merge(self, state) -> dict: ...
    @abstractmethod
    async def reflect(self, state) -> dict: ...
    @abstractmethod
    async def answer(self, state) -> dict: ...
```

- 新增 `app/ai/harness/sixnode.py`：`SixNodeHarness`——把现有 `graph.py` 的 `route_node/plan_node/fan_out_node/merge_node/reflect_node/answer_node` 包装为实现类（**行为零变化**，默认实现）；
- 新增 `app/ai/harness/registry.py`：`HARNESS_IMPLEMENTATIONS = {"sixnode": SixNodeHarness}`，配置 `HARNESS_IMPL=sixnode` 选择；`build_harness()` 工厂按配置实例化。
- 图构建改造：`graph.py build_graph()` 改为消费 `Harness` 实例的方法引用（`workflow.add_node("route", harness.route)` 等），**图拓扑不变**，节点实现按配置切换；模型升级替换实现（如 `loop` harness 或新自定义实现）不改图结构。

### 3.2 节点默认实现保留（task29 R8 裁定）

- `SixNodeHarness` 即现有实现搬运，`MAX_REFLECT_ITERATIONS`/effort scaling/Redis checkpointer/子代理蒸馏摘要全部保留；
- `scripts/eval/harnesses.py` 三套 harness（sixnode/baseline/loop）继续可用，作为"默认 vs 变体"对比（对接 task-E1 影子模式）。

### 3.3 扩展点

- 工具节点：`fan_out` 内部 `call_tool` 服务可替换为 task-T1 的闭环状态机（`executor.call_tool_with_retry`）；
- 记忆节点：`memory` 子代理服务可替换为 task-M1/M2 事件溯源 + Redis 共享向量（接口注入，不硬编码）；
- skill 注入：`plan` 节点可消费 task93 skill runtime 的渐进式披露（description 列表 → body 按需加载）。

### 3.4 配置项

```python
HARNESS_IMPL = "sixnode"       # 可插拔实现选择
HARNESS_REGISTRY = {"sixnode": "app.ai.harness.sixnode.SixNodeHarness"}
```

### 3.5 测试

- `tests/test_contract_task_a1.py`：接口齐全、默认实现与旧行为一致（跑 task24 契约测试回归）、`build_harness()` 按配置切换、自定义 mock harness 可注入且图拓扑不变。

## 4. 验收标准（Given/When/Then）

- **AC1（接口抽象）**：Given `app/ai/harness/base.py`，When 检查，Then 含 route/plan/fan_out/merge/reflect/answer 六个抽象方法且签名与现有节点一致。
- **AC2（默认实现等价）**：Given `HARNESS_IMPL=sixnode`，When 运行 task24 全部契约测试（图拓扑/effort scaling/checkpointer/子代理蒸馏），Then 全 PASS，行为与重构前零差异。
- **AC3（可插拔）**：Given 注册一个自定义 harness（mock），When `HARNESS_IMPL` 切换并编译图，Then 图拓扑不变（节点名/边不变），节点执行走新实现。
- **AC4（R8 裁定保留）**：Given 默认配置，When 编译生产图，Then 仍为 6 节点 DAG（route→compact→plan→fan_out→merge→reflect→answer），`keep_sixnode` 裁定不被推翻。
- **AC5（回归）**：Given `scripts/eval/harnesses.py` 三套 harness，When task-A1 改造后运行，Then sixnode/loop 结果与 task29 基线一致（无行为漂移）。

## 5. 交接与记忆

- **完工报告**：`test-reports/task-A1-completion-report.md`（接口清单、默认实现等价回归、可插拔切换实测）。
- **记忆写入**：AI-Hub `trae-projects/EduAgent/project_memory.md` 追加"Harness 接口抽象：6 节点 DAG 为默认实现，节点级可替换"决策（对齐 task29 R8 裁定）。
- **完成动作**：git commit → sync.ps1。

## 6. 批判承接

- **production-upgrade-plan.md P11**（硬编码 6 节点图）：模型升级后 reflect 节点成负担无法替换 → AC1/AC3 落实。
- **critique-backlog-tracker.md / ai-agent-revision-plan.md R8**：harness 简化评估（6 节点图 vs 循环）——本任务保留默认 6 节点并开放接口，R8 的对比结论可由 `HARNESS_IMPL` 切换直接落地（loop harness 作为候选实现注册）。

## 7. 与其他 task 关联

- **联动**：task-T1（工具节点替换为闭环状态机）；task-M1/M2（记忆节点替换为事件溯源 + Redis 向量）；task-E1（harness 变体进影子模式对比）；task-O1（harness 事件埋点）。
- **执行顺序**：W4 第四批；需 task24 稳定 + task-T1 就绪（工具节点替换依赖闭环状态机）。