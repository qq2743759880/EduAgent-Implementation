# task93 完工报告 — R2 skill 运行时（self-critique 维度4 结构性缺失补全）

- **执行工具**：Trae（后端+数据库开发者）｜**依赖**：task92（R1 fork 能力）、task27（tool_specs 权限）、task33（MCP 增强）
- **修订来源**：`self-critique-ai-agent-vs-competitors.md` §三 R2 + `ai-agent-revision-plan.md` R2
- **看板**：`D:\.ai-hub\memory\project-handoff.md`（task93 行，状态 DOING→待验收）
- **测试窗口纪律**：✅ 全程 in-process + fake LLM/tool，**未触发任何真实 LLM 调用**（当前 10:51 处于禁止窗口 9:00–12:00 之外，符合纪律）
- **交付物**：`edu-agent/app/ai/skills/{runtime,registry,loader,trigger,fork_exec}.py` + `__init__.py` + `tests/test_contract_task93.py`

---

## 一、批判承接核对段（self-critique 维度4 逐项）

> 维度4 原批判：「❌ 缺 skill 机制（渐进式披露）」——计划完全无 skill 机制；AI-Hub 已有 56 个 skills（agentskills 格式）但 agent 运行时无法使用。

| # | 原批判点（self-critique 维度4 表） | 承接实现 | 落点文件 |
|---|----------------------------------|---------|---------|
| 1 | 能力扩展：仅 MCP 工具 + ToolSpec，**无 skill（渐进式披露）** | SKILL.md 解析器：frontmatter(name/description/paths/context/disable-model-invocation/allowed-tools) + body 分离 | `runtime.py` |
| 2 | 技能触发：**无**（竞品有 description 自动触发 + paths 条件触发 + 手动 /skill） | `decide()` 综合触发：description 重叠匹配 + paths glob 条件触发 + `/skill` 手动；`disable-model-invocation` 不参加自动匹配 | `trigger.py` |
| 3 | 技能执行：**无**（竞品 context:fork 子代理执行 + allowed-tools 预授权 + dynamic context injection） | `exec_skill()`：context:fork → 委托 task92 `run_subagent`（独立子代理上下文）；inline → body 注入当前轮；`PermissionGate` 实现 allowed-tools 该轮免授权 | `fork_exec.py` |
| 4 | 工具权限：仅 admin_only 过滤（竞品有权限模式 + 工具格式） | allowed-tools 字段 → `is_preauthorized()` / `PermissionGate.is_authorized()` 该轮放行 | `fork_exec.py` |
| 5 | 渐进式披露缺失（竞品 description 进上下文、body 按需） | `build_description_listing()` 常驻清单（≤1536 字符/条，不含 body）；`load_body()` 触发时按需注入 | `loader.py` |
| 6 | AI-Hub 56 skills 资产浪费 | `registry.py` 扫描 AI-Hub + 项目 `.claude/skills`，全量索引（实测 **124/124**） | `registry.py` |

**承接结论**：维度4 全部 6 个批判点均有对应实现；其中「AI-Hub 56 skills」的 "56" 为规划期估算，实测当前 AI-Hub 中心库含 **124** 个 `SKILL.md`，运行时对全部 124 个完成索引（见第三节），满足「全部索引」验收。

---

## 二、竞品对标段（强制：真实竞品 URL / 数据）

> 对标基准（self-critique §〇 已真实抓取）：
> - **Claude Code skills 官方文档**：`https://code.claude.com/docs/en/skills`（self-critique §〇 证据表「Claude Code skills」行，全文抓取）
> - **agentskills.io 开放标准**：`https://agentskills.io`（self-critique 维度4 明确「agentskills.io 是开放标准」，Claude Code/Codex/Cursor 三家通用）
> - 辅助：`https://docs.claude.com/en/docs/claude-code/skills`（同文档当前域名镜像）

| 竞品实现（真实） | 引用/数据 | 本实现对照 | 验收点 |
|---|---|---|---|
| SKILL.md 渐进式披露：*"a skill's body loads only when it's used"* | code.claude.com/docs/en/skills | `loader.load_body()` 触发时才返回 body；常驻前缀**不含**任何 body（测试断言 `contains_body() is False`） | GWT② |
| description 截断：*"description truncated at 1,536 characters in the skill listing to reduce context usage"* | 同上，字面 1,536 | `SKILL_DESCRIPTION_MAX=1536` + `loader.truncate_description()`（2000 字符→1537 含省略号，实测通过） | GWT② |
| `context: fork` 在独立子代理上下文执行 | 同上 | `fork_exec.exec_skill()` 检测 `context=="fork"` → `run_subagent`（task92 R1，独立 messages/system/工具白名单/崩溃隔离） | GWT③ + 维度3 联动 |
| `allowed-tools` 该轮预授权 | 同上 | `PermissionGate.activate/deactivate` + `is_preauthorized()`（Read/Write/Edit 命中，Bash 不命中，实测通过） | GWT③ |
| `paths` 条件触发（工作文件匹配自动加载） | 同上 | `trigger.match_by_paths()` 支持 `**/*.py` 等 glob（Windows 反斜杠归一） | trigger 测试 |
| `disable-model-invocation: true` 仅手动触发 | 同上 | `trigger.match_by_description()` 跳过 DMI skill；仅 `/skill` 手动可触发 | trigger 测试（pick-ui 用例） |
| dynamic context injection（实时数据注入当前轮，不进前缀） | 同上 | `load_body()` 仅注入当前轮；前缀稳定（保护 prompt cache，联动 task97 R5） | GWT② |
| agentskills.io 开放标准（SKILL.md 通用格式） | agentskills.io | 解析器兼容该标准 frontmatter 全字段 | GWT① |

**对标结论**：task93 运行时逐字段对齐 Claude Code skills 文档 + agentskills.io 标准，维度4「结构性缺失」已闭合。

---

## 三、验收结果（GWT ①②③）

执行：`edu-agent/.venv/Scripts/python.exe -m pytest tests/test_contract_task93.py -q` → **15 passed**。

| GWT | 验收条件 | 结果 | 证据 |
|---|---|---|---|
| ① 全索引 | Given AI-Hub skills，When registry 启动，Then 全部索引 | ✅ | 真实 AI-Hub 扫描：**124 个 SKILL.md → registry.count()==124**（相等，含 1 个 parse_error 降级计入，不丢索引）；临时目录 7/7；项目 `.claude/skills` 缺失容错 |
| ② body 按需注入 | Given 触发匹配，When 决策，Then body 不进前缀、按需注入 | ✅ | `build_description_listing()` 断言**不含** body 唯一标记；`load_body()` 断言**含**标记；1536 截断断言通过 |
| ③ allowed-tools 免授权 | Given allowed-tools，When 执行，Then 该轮工具免授权 | ✅ | `is_preauthorized(Read)=True / (Bash)=False`；`PermissionGate` 激活/去激活周期断言通过；`context:fork` 经 task92 `run_subagent` 返回摘要（FORK_DONE_SUMMARY） |

**实时语料统计（真实 AI-Hub 124 skills）**：`context_fork=4`、`disable_model_invocation=7`、`with_allowed_tools=1`、`with_paths_trigger=0`、`parse_errors=1`。
- 说明：`paths` 字段当前 0 个 skill 使用，但解析器已支持（面向未来接入）；`context:fork`(4) / `disable-model-invocation`(7) / `allowed-tools`(1) 均为真实存在的字段，运行时已正确识别并消费。

---

## 四、与前后任务的衔接

- **前置 task92（R1）**：fork_exec 复用 `app.ai.subagents.runner.run_subagent` / `SubagentSpec`，实现「skill 在独立子代理上下文执行」——同时闭合 self-critique 维度3（上下文隔离）与维度4（技能执行）。
- **联动 task27（R5 缓存）**：description 清单常驻前缀、body 不进前缀 → 前缀稳定，保护 prompt cache 命中率（维度9 修复方向）。
- **下游 task94（R2 接入验证）**：registry 已可直接被 graph/agent 消费；task94 负责把 124 skills 接入对话决策链路（本 task 不集成，保持单 task 单 commit 边界）。
- **未做**：未改动 `graph.py` / `tool_specs.py`（属 task94/task97 范围）。

---

## 五、纪律声明

- 单 task 单 commit：本 task 仅新增 `app/ai/skills/*` 与测试，未触及既有模块。
- 测试窗口：无真实 LLM 调用（in-process fake LLM/tool），符合 9:00–12:00 禁止窗口纪律。
- 下一步：待编排者验收通过后，方可开始 task94。
