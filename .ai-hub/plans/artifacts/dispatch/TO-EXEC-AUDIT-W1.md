# TO-EXEC-AUDIT-W1 — WRITE1（favorite_add 打样）反向审核

> 你是独立验收 agent。编排者亲自执行了 favorite_add 打样（其子 agent 配额阵亡），按纪律其报告必须经独立反向审核。你的唯一输入=完工报告+代码 diff+本文件。**你只做验收，不改任何代码。**

## 项目背景（最小集）

- 仓库：`E:\stu\project\stu\EduAgent实施手册`（Windows），分支必须为 `feature/opt-waves`
- 后端：`edu-agent/`（Python venv 在 `edu-agent/.venv`），端口 9988
- 本任务主体 commit：`4a598b3`（配套 9689a2b 批判登记、501de25 报告）
- 测试账号：student `user000001 / Test@123456`

## 输入（开工前实读）

1. `test-reports/WRITE1-favorite-add-completion.md`（被审报告）
2. `git show 4a598b3 --stat` 与逐文件 diff（`git show 4a598b3 -- <file>`）
3. `contracts/cr-writetools-001.md`（变更单）
4. `.ai-hub/plans/artifacts/kickoff-WRITE1-FAV.md`（原始工单，八条验收断言出处）

## 审核断言清单（逐条给 PASS/FAIL+证据，禁止只写「确认无误」）

1. **注册面**：executor 真实注册 favorite_add 且 write_class=True（`grep -n "favorite_add" edu-agent/app/mcp/executor.py`）
2. **矩阵**：permission_gate 中 TOOL_CLASS_MAP["favorite_add"]="user_write"、`_CLASS_ALLOWED_ROLES["user_write"]`={student,teacher,admin}、CONTRACT_PENDING_TOOLS 已无 favorite_add
3. **单一事实源**：langgraph_agent `_hitl_risk_level` 读 classify_tool_intent；全文件无 ADMIN_WRITE_TOOLS/COURSE_WRITE_TOOLS 的 import
4. **测试实跑**（你必须亲自跑）：`cd edu-agent && .venv\Scripts\python.exe -m pytest tests/test_tool_favorite_add.py tests/test_permission_gate.py tests/test_r11_hitl.py -q` → 应 117+ passed 0 failed
5. **联调复核**（后端若在跑直接用；不在跑则起：`cd edu-agent && .venv\Scripts\python.exe -m uvicorn app.main:app --port 9988` 后台）：登录 student → GET /api/favorites → 断言 items 含 series_id=3（fav_id=30160，打样真实落库证据）；DB 只读复查：`mcp_tool_call_log` 存在 tool_name='favorite_add' 的 SUCCESS 行
6. **HITL 免卡语义**：`_hitl_risk_level("favorite_add") is None`（python -c 实测），且 points_change/order_create=high、course_create=medium 零回归
7. **越权面**：`can_use_tool("manager","favorite_add").allowed is False`（P1 裁定 manager=deny）
8. **报告诚实性**：报告 §② 时间线自述「答案层捏造回执两次」——核对 git log 与 tracker（9689a2b）确有登记，无掩盖

## 交付

- 单 commit：`docs(audit)/AUDIT-W1: WRITE1 反向审核 <总评 PASS|FAIL>`（只含报告文件）
- 报告写 `.ai-hub/plans/artifacts/dispatch/REPORT-AUDIT-W1.md`：逐断言 PASS/FAIL+证据（命令+输出摘录）+ 你发现的新问题（若有，标severity）+ 总评结论
- 禁改：任何 app/ 代码、契约、测试。发现 bug 只登记不改。
