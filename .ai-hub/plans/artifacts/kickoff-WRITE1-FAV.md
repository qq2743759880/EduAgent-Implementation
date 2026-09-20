# Kickoff: W-NEXT-WRITE1 — favorite_add 写类工具打样（CR-WRITETOOLS-001 第一批）

## 用户裁定（2026-09-20 全批，本单直接执行，不再等批）
- P1：favorite_add 类别 **user_write**；矩阵 **student=allow / teacher=allow / manager=deny / admin=allow / guest=deny**
- P2：course_create 仅 admin（**本批不实现**，仅变更单登记 planned/batch-2）
- P3：HITL 分级单一事实源——`_hitl_risk_level` 改读 `TOOL_CLASS_MAP`（admin_write/course_write→"high"；user_write→None 不弹卡）
- P4：executor 双保险语义——高危工具 handler 首行校验 `ctx["hitl_confirmed"]`，未确认→42201 拒（本批只登记语义进变更单 + 单测锁定接口形状；course_create 实弹属第二批）
- P5/P6：契约变更单按裁定生成；favorite_add 先行打样

## 铁律（违反任一条=返工）
1. **禁 DB 直写**——一切写操作走 service 层 / HTTP API，禁 SQL 直插
2. 契约权威 = 后端 `schemas.py` + `error_codes.py`；响应壳 `{code:0,message:"ok",data}`；分页裸 DTO
3. 文档/注释里的接口描述只是初稿，**以实读后端代码为准**
4. API key 只许存在于 `.env`，禁写入报告/日志/commit/代码字面量
5. 只动本单范围文件；开工前后各跑一次 `git branch --show-current`（必须 = `feature/opt-waves`，不符立即停止上报）
6. 完工报告必须含「资产消费证据」段与「批判承接核对」段；报告里每条断言都要附编排者可复现的命令

## 必读资产（开工前实读）
- `docs/时光.md` §一（现状锚点表）§三（工具 A 完整草图+测试+联调）§四 B3（P3 改造）§六（变更单草案）——本文 kickoff 是它的执行令
- `contracts/reshape-r-hitl.json`（已冻结：resume 五字段帧/40450 语义，禁回归）
- `edu-agent/app/ai/executor.py`（注册区：calculator / search_knowledge / knowledge_import 同区插入）
- `edu-agent/app/ai/permission_gate.py`（TOOL_CLASS_MAP / KNOWN_ROLES / CONTRACT_PENDING_TOOLS）
- `edu-agent/app/chat/flows/langgraph_agent.py:27`（`_hitl_risk_level` 唯一活符号）
- `edu-agent/app/chat/graph_stream.py:223` → `tool_calling.py:443`（on_write_class_pending / 五字段帧）
- `edu-agent/app/domains/favorite/`（service 签名以实读为准，幂等已证）
- `.ai-hub/plans/critique-backlog-tracker.md`（批判承接源）

## 工序（闸 1/2/4 + P3，缺一不可）
1. 实读上面全部锚点，复核 时光.md §一 表格与代码现状一致；不一致处以代码为准并在报告记录
2. **闸 1**：executor 注册 `favorite_add`（arg_schema `additionalProperties:False` exact-pin；`ctx.user_id` 服务端注入，禁从 args 取）
3. **闸 2**：`CONTRACT_PENDING_TOOLS` 删除 `favorite_add`；`TOOL_CLASS_MAP` 新增 `user_write` 类别 + P1 五角色矩阵
4. **P3**：`_hitl_risk_level` 改读 `TOOL_CLASS_MAP`；grep `ADMIN_WRITE_TOOLS|COURSE_WRITE_TOOLS` 全部消费点同步改造，**禁留双源**；既有挂起工具的 pending_confirm 行为逐字段回归（对照 reshape-r-hitl.json）
5. 新增 `edu-agent/tests/test_tool_favorite_add.py`（时光.md §A3 T1-T6 六用例全落）
6. 契约变更单：`contracts/cr-writetools-001.md`（favorite_add=applied 含 P1 矩阵；course_create=planned/batch-2 含 P2/P4 语义；hitl_confirmed ctx 注入语义）。若 `contracts/reshape-r-aci.json` 存在且按仓库算法要求 hash 重算，同步重算
7. 全量测试：新增套件 + 既有 HITL/permission_gate 相关套件（隔离跑，`cd edu-agent && .venv\Scripts\python.exe -m pytest tests/ -k "hitl or permission or favorite or tool" -q` 起步，再跑广域回归面）
8. 联调（真实 HTTP）：重启后端 9988（先杀旧进程：`netstat -ano | findstr :9988` → taskkill，再 `cd edu-agent && .venv\Scripts\python.exe -m uvicorn app.main:app --port 9988` 后台起）→ 时光.md §A4 curl 序列 ①登录 ②建会话 ③chat 触发收藏 ④GET /api/favorites 复核，逐条记录真实输出
9. 单 commit：`feat(tools)/favorite_add: 写类工具打样落地 user_write+HITL单一事实源 (CR-WRITETOOLS-001 第一批)`；完工报告落 `test-reports/WRITE1-favorite-add-completion.md`

## 验收断言（编排者将逐条独立复现，报告按此结构写）
- [ ] favorite_add 在 executor 真实注册（grep name= 且 handler 存在）
- [ ] CONTRACT_PENDING_TOOLS 不再含 favorite_add；TOOL_CLASS_MAP 含 user_write 矩阵 P1 五角色
- [ ] `_hitl_risk_level` 读 TOOL_CLASS_MAP；仓库内无残留双源消费点
- [ ] T1-T6 全绿（编排者复跑）
- [ ] 既有 HITL 套件零回归（五字段帧逐字段）
- [ ] curl ③ answer 含「已收藏」或幂等提示且无 pending_confirm；④ items 出现目标 course
- [ ] 变更单落库且 draft 状态与裁定一致
- [ ] 后端重启后 9988 存活（health 200），留给编排者复验
