# TO-EXEC-TA2 — HITL demo 默认开（yy 十点修复 · P0）

> 分支 `feature/opt-waves`；后端 9988 / 前端 3322（dev 态）在岗。本开工令自包含，勿依赖会话外上下文。

## 背景

owner 从未成功见过 HITL 确认卡。编排者已定位开关层根因：`edu-agent/.env` 第 93 行附近，`HITL_ENABLED=True` **与上方中文注释粘连成同一行**（形如 `……真实拦截。HITL_ENABLED=True`），dotenv 按首个 `=` 切分后 key 不匹配 → 不生效 → 回落 `app/config.py:538` 默认 `HITL_ENABLED: bool = False`。链路本体（`app/ai/permission_gate.py` ToolClass 四枚举 + 挂起区/注册面 + `course_create` write_class=True + `app/mcp/executor.py` handlers）已由 T12 E2E 六场景临时开窗实证完整，缺的只是这行配置。

## 工作项

1. **修 .env 粘连行**：把粘连行拆开——注释行归注释行，`HITL_ENABLED=True` 独立成行。编辑纪律（硬性）：python `open('.env','r',encoding='utf-8',errors='surrogateescape')` 读、`newline=''` 写回，**禁用 sed/echo 追加**（本次粘连行就是历史 echo 事故现场）。改完用同样方法回读，断言 `HITL_ENABLED` 是独立行且首字符非 `#`。
2. **确认其余三行独立生效**：`HITL_PENDING_TTL_S=600`、`HITL_AI_REVIEW=False`、`HITL_RISK_THRESHOLD`（如 .env 无此行则维持 config.py 默认，不新增）。
3. **重启后端**（uvicorn 9988）：`cmd /c start "" /B .venv\Scripts\python.exe -m uvicorn app.main:app --port 9988`（edu-agent/ 下）。重启窗口在报告中记录起止时间（≤2 分钟）。重启后先探活 `GET http://127.0.0.1:9988/api/health`（或 docs 接口文档里的健康端点）再继续。
4. **实弹双场景（C-01 口径，真实 HTTP + 真实 DB）**，账号 admin `adm02test / Test@123456`（登录字段是 `account`）：
   - ① approve 路：chat 会话触发建课（course_create 属 write_class，风险 high 必过 Gate）→ 断言返回的是 HITL 确认卡帧（explain/propose 结构）而非直接执行 → 走 approve → 断言 `course` 表真实新增一行 + `tool_receipts`/audit 有凭据。
   - ② reject 路：再次触发建课（换课程名）→ reject → 断言 `course` 表**零新增**、无 SKIPPED 之外的执行痕迹。
5. **README 不动；改两处文档口径**：`docs/用户使用手册.md` 与 `docs/面试演示-逐步点击手册.md` 各加/改一节「HITL 确认卡演示」（触发话术原句 + approve/reject 两条路的现象描述），并标注「生产可经 .env 关闭」。
6. **开关复原禁令**：本次为 demo 默认开（owner 已裁定），验收后**不复原 False**。

## 铁律

- 只许改：`edu-agent/.env`（仅拆粘连行）、`docs/用户使用手册.md`、`docs/面试演示-逐步点击手册.md`。禁碰 chat.html、React 路由、permission_gate/executor 代码（TA1-3 串行链在改 chat.html）。
- 禁 DB 直写（①②断言只读查询）；SQL 一律参数绑定；API key 禁入报告/日志/commit。
- 不 push；单 commit：`fix(config)/ta2: 修复 .env HITL_ENABLED 粘连行致开关失效 + HITL demo 默认开 + 双手册演示节`。
- 与并行单 TA4/TA1-3 无文件交集；后端重启窗口若撞上其他单的 HTTP 验收，报告里如实记时间戳。

## 报告

`.ai-hub/plans/artifacts/dispatch/REPORT-TA2.md`：粘连行修复前后原文对照（脱敏）、approve/reject 两路断言的 HTTP 响应关键字段 + DB 行证据（行数/主键，禁贴敏感值）、重启窗口、手册 diff 摘要。编排者将逐断言独立复现。

## owner 验收口径（GWT）

Given demo 环境且开关已修，When owner 在 admin 界面对话要求建一门课，Then 看到确认卡；点同意→课程真实出现；点拒绝→不出现。全程 owner 亲手操作，不看报告。
