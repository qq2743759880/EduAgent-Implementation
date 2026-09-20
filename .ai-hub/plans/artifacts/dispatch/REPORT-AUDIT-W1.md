# REPORT-AUDIT-W1 — WRITE1（favorite_add 打样）独立反向审核

- 审核人：独立验收 agent（MainAgent 会话）；审核对象 = 编排者亲执行的 favorite_add 打样（主体 commit `4a598b3`，配套 9689a2b 批判登记、501de25 完工报告）
- 分支：`feature/opt-waves`（开工前 `git branch --show-current` 已核对）
- 审核纪律：只验收不改码；未改任何 app/ 代码、契约、测试；全程只读 DB（SELECT/SHOW）
- 审核时间：2026-09-20（UTC+8）

## 总评结论：**PASS**（8/8 断言实质通过；1 处 dispatch 侧计数口径偏差已标注，非交付物缺陷；2 处观察项登记不改）

---

## 逐断言 PASS/FAIL + 证据

### ① 注册面 — PASS
证据：`grep -n "favorite_add" edu-agent/app/mcp/executor.py`
```
1198:async def _favorite_add_handler(args: dict) -> str:
1249:register_builtin_tool("favorite_add", _favorite_add_handler, write_class=True)
```
`write_class=True` 收口强属性在位（1249 行）。handler 做了 exact-pin（仅 series_id(int)，多余键/布尔/非 int 均拒）+ user_id 从 `_EXEC_CONTEXT.operator_user_id` 服务端注入（不从 args 取）+ 业务错结构化回传（`ok:False` + 错误码），与变更单安全不变量一致。

### ② 矩阵 — PASS
证据：`permission_gate.py` 实读
- L146 `TOOL_CLASS_MAP["favorite_add"] = "user_write"` ✓
- L225 `"user_write": frozenset({"student","teacher","admin"})` ✓（manager/guest 不在内）
- L164-179 `CONTRACT_PENDING_TOOLS` 字面量仅剩 8 项（course_*×6 + points_change/order_create），favorite_add 仅在 L175-176 注释中说明已迁出，**字面量已无 favorite_add**（挂起区 9→8、注册面 8→9 与报告一致）。
- can_use_tool 五角色实测见断言⑦，矩阵行为正确。

### ③ 单一事实源 — PASS
证据：`langgraph_agent.py`
- L39 `from app.ai.permission_gate import classify_tool_intent`；L44 `cls = classify_tool_intent(n)`
- 全文件对 `ADMIN_WRITE_TOOLS|COURSE_WRITE_TOOLS` 仅 L32 docstring 提及，**无 import**（test_tool_favorite_add.py:196-197 还专门机锁了这两条 not-in 断言）。
- 备注（观察项，非 FAIL）：旧别名 `ADMIN_WRITE_TOOLS/COURSE_WRITE_TOOLS` 仍在 permission_gate.py L203-207 定义为 `CONTRACT_PENDING_* ∪ REGISTERED_*` 的**派生投影**，生产代码零消费，仅 test_permission_gate.py / test_r11_hitl.py 用于回归锁定其组成。因其由同一事实源现算、不存在独立维护的第二份清单，不构成「双源漂移」。若 kickoff P3「禁留双源」从严解读可在后续批次删除别名本身，本单不改。

### ④ 测试实跑 — PASS（附计数口径备注）
命令（本审核亲自执行）：
```
cd edu-agent && .venv\Scripts\python.exe -m pytest tests/test_tool_favorite_add.py tests/test_permission_gate.py tests/test_r11_hitl.py -q
```
输出：`111 passed, 1 warning in 13.95s`，**0 failed**。
分文件实数：
- test_tool_favorite_add.py = **20 passed**（与报告一致，含 T1-T6 + 启发式 + 图路径审计 + P3 结构断言）
- test_permission_gate.py = **81 passed**
- test_r11_hitl.py = **10 passed**
- 合计 111，无 skip 无 error。

> 口径备注：dispatch 断言写「应 117+ passed 0 failed」。实测 111，比 dispatch 预期少 6。这是 **dispatch 侧计数估计偏差**（三个文件实际可收集用例就是 20+81+10=111，无被 deselect 的用例、无 skip），不是交付物缺测试——交付物自述的 favorite_add=20 准确，更宽回归面报告为 307 passed/16 skipped/0 failed。硬门槛「0 failed」满足。本断言按实质 PASS 记。

### ⑤ 联调复核 — PASS
后端在跑（`GET /health` → 200 `{"status":"ok"}`），未重启。
- 登录 student：`POST /api/auth/login {account:user000001,password:...}` → 200，`code=0 role=student user_id=1`。
- `GET /api/favorites?page=1&page_size=50`（带 Bearer）→ `code=0 total=6`，items 含：
  ```
  fav_id=30160  series_id=3   ...   ← 打样真实落库证据
  fav_id=30073  series_id=2628
  fav_id=30072  series_id=1005
  fav_id=30014  series_id=2
  fav_id=30012  series_id=2618
  fav_id=30010  series_id=1
  ```
  total=6（报告称 favorites 5→6）、fav_id=30160/series_id=3 命中。
- DB 只读复查 `mcp_tool_call_log`（MySQL edu）：
  ```
  favorite_add rows: 1
  (684, 'favorite_add', 'SUCCESS', 1, 35, '2026-09-20 17:04:20')
  status counts: ('SUCCESS', 1)
  ```
  与报告「audit id=684 SUCCESS 35ms」逐字段吻合。仅 1 行也自洽：前 3 发零调用、第 4 发写库时审计分支尚缺（0 行）、第 5 发幂等复跑时审计已补 → 唯一落库行即 id=684。

### ⑥ HITL 免卡语义 — PASS
`python -c` 实测 `_hitl_risk_level`：
```
favorite_add     -> None        ← 免弹卡（user_write）
points_change    -> 'high'
order_create     -> 'high'
course_create    -> 'medium'
knowledge_import -> 'high'      ← admin_write 实物零回归
```
`classify_tool_intent` 旁证：favorite_add→user_write、points_change→admin_write、course_create→course_write、knowledge_import→admin_write。既有挂起工具 high/medium 语义零回归。

### ⑦ 越权面 — PASS
`can_use_tool(role,"favorite_add")` 实测：
```
manager allowed=False   ← P1 裁定 manager=deny ✓
guest   allowed=False   ← fail-closed ✓
student allowed=True
teacher allowed=True
admin   allowed=True
```

### ⑧ 报告诚实性 — PASS
- `git log --oneline` 实见：`4a598b3`（主体）→ `9689a2b`（W1-findings 四发现登记）→ `501de25`（完工报告），顺序与报告自述一致。
- tracker `.opencode/plans/critique-backlog-tracker.md` L645-649 实见 C-W1-①~④：
  - C-W1-②（P0 部分修）明文：「**答案层捏造工具回执**：工具阶段未命中时答案 LLM 捏造『已收藏/已提交』成功回执（**两次实证**……）」，并登记硬化项 F-W1-GUARD。
  - 与报告 §② 时间线「答案层捏造回执两次」自述一致，无掩盖。

---

## 审核中新发现的问题（登记不改）

1. **[INFO / dispatch 侧] 断言④计数口径**：dispatch 写「117+」，实测 111。建议 dispatch 模板把预期数改为「0 failed」为准、或按实际文件用例数回填；不影响本批交付质量。
2. **[P3 / 观察] 旧写类别名仍在**：`ADMIN_WRITE_TOOLS/COURSE_WRITE_TOOLS` 作为派生投影保留在 permission_gate.py，仅测试消费。非双源漂移，但与 kickoff P3「禁留双源」从严解读有距离，可在 course_create（batch-2）落地时一并清理。
3. **[P2 / 环境观察，非本批引入] DEBUG 模式在岗**：审核期间后端启动打印「[安全] DEBUG 模式使用公开 JWT_SECRET」。本审核均带 student 真实 token 访问，结论不受影响；但 AGENTS.md 教训#6 重申部署前必须 DEBUG=False，登记提醒。
4. **[P1 / 承接项复核] 报告自述的 C-W1-③（mcp_tool_calls 六节点路径恒空）与 C-W1-②（答案层捏造待硬化）确为 open 项**：本审核未复跑 chat SSE 端到端（dispatch 未要求），仅确认其已如实登记 tracker，不重复判定。

## 审核边界声明
- 未复跑 chat SSE 全链（dispatch 断言⑤只要求登录→GET /api/favorites + DB 审计行，已满足）。
- 未改任何代码/契约/测试；临时查询脚本已删除，工作区未留审核产物。
- 本报告即唯一交付物，单 commit 提交。
