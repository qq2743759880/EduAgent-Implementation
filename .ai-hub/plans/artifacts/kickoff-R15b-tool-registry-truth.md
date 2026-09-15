# kickoff: R15-b 工具映射表对账实物(批判反哺,消灭虚构工具名)

> 你是 EduAgent 项目的后端图域工程师(独立执行,单写者)。工作区:E:\stu\project\stu\EduAgent实施手册
> 单写者锁:开工建 edu-agent/scripts/eval/r15b.lock,完工删。后端 8000 运行中禁重启;验证用 8010 临时实例(用完关闭)。
> **前置**:R15(920599a)已在分支,你基于其上改;不推翻 R15 权限门架构,只修映射表对账实物。

## 必读
1. AGENTS.md(教训 1-10) 2. contracts/reshape-r-aci.json(冻结契约,**禁改**) 3. edu-agent/app/ai/permission_gate.py(R15 产物,你要修的) 4. edu-agent/app/mcp/executor.py(**只读**——真实工具注册面以此为准) 5. test-reports/R15-completion-report.md(前批背景)

## 批判根源(编排者实锤)
R15 的 17 项映射表里 **10 个写类工具名(course_create/update/delete、question_create/update/delete、favorite_add、points_change、knowledge_import、order_create)全代码搜索零命中,executor 从未注册**——是前批从契约中文语义臆译虚构的。真实注册面只有:
- **内置 2 个**(executor.py L676-677 `register_builtin_tool`):`calculator`、`search_knowledge`
- **MCP 演示 5 个**(DB mcp_tool 表/演示服务):`add`、`echo`、`list_alphabet`、`ping`、`sse_health`
后果:fail-closed 对真实工具面是空防,矩阵与实物脱节。

## 任务
1. **映射表对账实物**:TOOL_CLASS_MAP 改为只含真实注册的工具;写类契约项(收藏写/积分变更/知识库导入/订单创建)**语义保留但标注「无实物工具,映射挂起」**——在 permission_gate.py 以注释+数据结构(如 `CONTRACT_PENDING_TOOLS` 集合)明示这些是契约登记但实物未注册,当前 fail-closed 自然拦截;文档(报告)写清「工具上线时如何补登记」。
2. **单一事实源**:真实工具清单优先从 executor 注册面(`_BUILTIN_TOOL_HANDLERS` keys + mcp_tool 表)生成或核对;若无法自动同步,至少在 permission_gate.py 头部注释写明「与 executor.py L676-677 + mcp_tool 表对账,2026-XX-XX 核」+ 报告附对账证据(grep/SQL 只读)。
3. **矩阵语义不变**:admin=全量、manager=只读+课程/题库写类、student=公开只读、default deny——这些契约矩阵**禁改**,只让映射表对账实物。
4. **G4 补自动化测试(R15 P0-3 反哺)**:角色注入进契约测试——test 文件新增对 `run_agent`/`get_user_info_by_id` 的角色注入自动化断言(可 mock DB 层,断言 user_role 注入逻辑;真实 DB 冒烟仍可在报告记)。

## 验收 GWT(编排者逐条复现)
- R15b-G1:TOOL_CLASS_MAP 中每个工具名在 executor.py 注册面(_BUILTIN_TOOL_HANDLERS 或 mcp_tool)有实物命中——报告附逐名对账表(工具名→注册出处 file:line 或 SQL)。
- R15b-G2:10 个虚构名从 TOOL_CLASS_MAP 移除,转入 CONTRACT_PENDING_TOOLS(契约挂起)并有注释;`can_use_tool(role, "course_create")` 仍 deny(fail-closed 拦截未注册)。
- R15b-G3:既有 R15 矩阵测试不破坏——student/manager/admin 对真实工具的判定全对;`pytest tests/test_permission_gate.py` 全绿(含 G4 新增用例)。
- R15b-G4:角色注入自动化测试存在且绿(test 文件 grep 到 run_agent 或等价注入断言)。
- R15b-G5:executor.py 零改动;报告 test-reports/R15b-completion-report.md(对账表+挂起清单+G4 测试证据)。

## 交付
commits:fix(r)/R15b-tool-registry-truth;报告 test-reports/R15b-completion-report.md。完工回执:commit 列表+报告路径+各 GWT 数字+对账后真实工具全量清单。