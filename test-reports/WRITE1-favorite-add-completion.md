# W-NEXT-WRITE1 完工报告（编排者亲自执行版——子 agent 配额阵亡后按新规由编排者执行，本报告待独立子 agent 反向审核）

- 执行者：编排者（ZCode 主会话）；子 agent 状况：配额上限阵亡（5 小时限额，19:46 重置），零 WIP 残留（git 对账确认）
- 主体 commit：**4a598b3**（11 文件 +738/-25）+ 发现登记 9689a2b；分支 feature/opt-waves
- 工单：`.ai-hub/plans/artifacts/kickoff-WRITE1-FAV.md`（用户 P1-P6 裁定 2026-09-20）

## ① 交付清单

| # | 断言（kickoff 八条） | 实现 | 编排者复现命令 |
|---|---|---|---|
| 1 | executor 真实注册 | `_favorite_add_handler` + `register_builtin_tool("favorite_add", ..., write_class=True)`（executor.py 收口强属性） | `grep -n "favorite_add" edu-agent/app/mcp/executor.py` |
| 2 | 挂起迁出+矩阵 | `TOOL_CLASS_MAP["favorite_add"]="user_write"`；矩阵 student/teacher/admin=allow、manager/guest=deny（`_CLASS_ALLOWED_ROLES`）；挂起区 9→8、注册面 8→9 | `grep -n "favorite_add" edu-agent/app/ai/permission_gate.py` |
| 3 | HITL 单一事实源 | `_hitl_risk_level` 改读 `classify_tool_intent`（admin_write=high/course_write=medium 语义保持；user_write=None 免卡）；别名 import 零残留 | `grep -n "ADMIN_WRITE_TOOLS" edu-agent/app/chat/flows/langgraph_agent.py`（仅注释提及，无 import） |
| 4 | T1-T6 全绿 | tests/test_tool_favorite_add.py **20 passed**（T1-T6 + 启发式 3 + 图路径审计 + P3/P4 结构断言） | `cd edu-agent && .venv\Scripts\python.exe -m pytest tests/test_tool_favorite_add.py -q` |
| 5 | 既有套件零回归 | 权限门+HITL+子代理+路由合同面 **307 passed, 16 skipped, 0 failed** | `pytest -k "tool or mcp or permission or hitl or favorite or subagent or rule_router or contract_taskP1L"` |
| 6 | 联调真实闭环 | ①user000001 登录 ②建会话 ③chat「收藏 series_id 为 3 的课」→**真实写库 favorites 5→6（fav_id=30160）**+幂等复跑同记录+无 pending_confirm ④GET /api/favorites 含 series 3 | 报告 §③ 时间线（四次迭代全留痕） |
| 7 | 变更单落库 | contracts/cr-writetools-001.md（favorite_add=applied、course_create=planned/batch-2、P3/P4 语义、四不变量） | `cat contracts/cr-writetools-001.md` |
| 8 | 9988 存活 | health 200（写稿时在岗） | `curl http://127.0.0.1:9988/health` |

## ② 联调时间线（为什么打了五发——每发都是真发现）

| 发 | 结果 | 发现 |
|---|---|---|
| 1 | mcp_tool_calls=0，答案称「已收藏」 | **答案层捏造回执**（favorites 无 series3 实证）+ 日志见子代理 exact-pin 拒绝（缺必填字段）→拒绝后答案仍谎报成功 |
| 2 | 同上 | 修①启发式规则后仍 0 调用 → 六节点规则路由把查询判 knowledge 兜底，工具阶段整体跳过 |
| 3 | 同上（但路由已 tool） | 修②rule_router「收藏」意图后 intent=tool，但 tool 子代理 prompt **无工具清单**，LLM 不知 favorite_add 存在（先直呼工具名被白名单拒，后放弃调用） |
| 4 | **真实写库**（fav 30160） | 修③子代理 prompt 补 REGISTERED_TOOLS 同源清单+禁虚构指令后全链通；但 mcp_tool_calls 仍 0（响应体字段仅旧回退路径填充）+ **审计 0 行** |
| 5 | 幂等+审计双绿 | 修④图路径内置分支补 _write_call_log → 复跑同记录返回 + **audit id=684 SUCCESS 35ms** |

## ③ 打样暴露并当场修复的缺口（超出 kickoff 预面，均已登记 tracker C-W1-①~④）

1. **C-W1-①（P0 已修）图路径内置工具零审计**：`call_tool_with_retry → _default_attempt_executor` 内置分支直调 handler 不落审计——W-NEXT-MCP-001 P0-② 只护住了 call_tool 直连路径。已补齐+回归锁。
2. **C-W1-②（P0 部分修）答案层捏造回执**：两次实证「工具零执行但答案称成功」。缓解=路由意图+子代理工具清单+禁虚构指令；**硬化待立项 F-W1-GUARD**（answer 提及工具名而凭据空 → 机检拦截）。
3. **C-W1-③（P1 待修）mcp_tool_calls 六节点路径恒空**：真实执行有 DB/审计双证但响应体零回执，前端拿不到工具凭据。
4. **C-W1-④（P2 观察）读池初始化一次性抖动**。

## ④ 资产消费证据

- kickoff：`.ai-hub/plans/artifacts/kickoff-WRITE1-FAV.md`（逐条执行）
- `docs/时光.md` §一锚点表 §三草图 §A3/A4（**三处草图与现实不符已按实读纠偏**：executor 在 app/mcp 非 app/ai；service 签名是 add_favorite(user_id, series_id, favorite_source) 非 course_id；B3 草图会把 course_write 误升 high 且丢 executor 高危分支——定稿保 medium+保留兜底分支）
- `contracts/reshape-r-hitl.json`（冻结面，五字段帧零回归）
- 实读源码：executor.py（注册/收口/审计三区）、permission_gate.py 全文、langgraph_agent.py 全文、tool_calling.py（规划+描述注册表）、rule_router.py、subagents/{definitions.yaml,runner.py,tool_schemas.py}、market/{service,router}.py、tests/{test_permission_gate,test_r11_hitl}.py

## ⑤ 批判承接核对

- tracker C-W1-①~④ 本批新增并登记（.opencode/plans/critique-backlog-tracker.md，9689a2b）✓
- 前批承接项：无重叠（本单为新增工具面）✓
- 教训登记：「回执数字系统性失真」新形态（答案层回执无工具凭据对账）+ 编排者逐断言复现抓出两次捏造的验收铁律再证 ✓

## ⑥ 移交

- batch-2（course_create）：变更单已登记 planned；底稿 docs/时光.md §四；实施时 HITL_ENABLED 需真实窗口
- F-W1-GUARD 硬化 / C-W1-③ 回执透传：待立项排期
- 反向审核：待配额 19:46 重置后派独立子 agent（本报告 + `git show 4a598b3` 为其唯一输入）
