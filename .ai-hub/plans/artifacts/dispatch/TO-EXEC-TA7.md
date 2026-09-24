# TO-EXEC-TA7 — 凭据语义真化 + 记忆召回修复（P2 验收发现的三个真缺陷 · 返工单）

> 分支 `feature/opt-waves`（开工前 `git log --oneline -3` 记基线）。**服务重启只准用仓库根 `start-eduagent.cmd`；禁在会话内 run_in_background 起服务（随会话被杀=无声死亡）。** 开工令自包含。

## 定因（编排者已亲测复现，执行者复核后动手）

TC2 盲测 B11 黄条 0/3 与 TC1-F1 记忆失效，编排者逐一定因如下（与 TC2/TC3 报告的诊断不同，以本令为准）：

### D1（P0）· 内置工具业务失败被记成 SUCCESS → 护栏零触发

实测（真实 HTTP，user000002）：问"帮我把《量子物理导论第七版完全不存在版》加入收藏"→ `mcp_tool_call_log` 落行 **status=SUCCESS**，但 `result_json.content_text` 明明白白是 `{"ok":false,"code":"40400","message":"未找到课程…","need_clarify":true}`；SSE `mcp_tool_calls` 同样 `status:"success"`。后果：receipt_guard 看到 success 凭据 → **工具业务失败时黄条永不出现**——护栏存在的意义（"AI 说做了但实际没做"）恰是这种场景。TA6 之前黄条能触发纯属"工具执行不了"的副产品。
**修法方向**：内置 handler 对业务失败（content 内 ok:false / 非 0 code）不得映射 SUCCESS——要么 handler 抛 AppException（40400 带 need_clarify 语义，由既有错误→响应映射承载），要么管道把 `ok:false` 解析为 error 状态。**判定权威=mcp_tool_call_log.status 与 SSE status 必须如实反映业务结果**；护栏零改动即恢复触发（无 success 凭据→打标）。

### D2（P1）· 课程名解析零候选，模糊兜底缺失

《Python 入门》在库中**不存在**（2627 门在售无一含"Python"），但 need_clarify 结果 `candidates:[]`——按名解析精确未命中时应给 LIKE 模糊候选（如"没有《Python 入门》，最接近的是《XXX》《YYY》，要收藏这个吗？"）。修在 `resolve_series_by_name`（`app/mcp/executor.py`）。

### D3（P0）· 跨会话记忆召回失效（TC1-F1）

编排者复现：会话 A `memorized:["用户名字：王小明"]`（写入路径正常，user_memory_event 落库）；新会话问"我叫什么名字"→ 记忆区为空。TC1 定因 Milvus upsert NaN 降级——先复现（看 Memory:vector 日志 NaN 降级行），修 NaN 根因（embedding 产出 NaN 的防护/清洗），修完双会话实测召回恢复。

## 工作项

1. 逐项修复 D1/D2/D3，每项修前先复现留证、修后复验。
2. 自验（真实 HTTP）：
   - ① 收藏不存在的课 → 调用日志 status=**非 SUCCESS**、SSE 如实、**黄条触发**（`tool_receipt_unverified:true`）；AI 话术含"未找到"+模糊候选（D2 后）。
   - ② 收藏真实存在的课（先 SQL 挑一门在售课名）→ SUCCESS + 真实落库 series_favorite +1（验完把这条收藏经应用接口删除还原）。
   - ③ 跨会话记忆：A 会话记名字 → 新会话问名字 → 正确答出（D3）。
   - ④ 回归：`pytest -k "favorite or memory or receipt or chat"` 零新增失败（在 `edu-agent\` 下跑）。
3. **手册两站翻转**：黄条站换成新稳定话术（收藏不存在的课，连续 3 次触发截图）；记忆站解除"当前阻塞"标注恢复可用话术。改 `docs/面试演示-逐步点击手册.md` 对应两节 + `docs/用户使用手册.md` 同步节。

## 铁律

- 域：`app/mcp/executor.py`（handler 状态语义+解析器）、记忆向量 NaN 修复涉及的文件（`app/ai/memory/` 域）、receipt 状态映射管道（如需）、两本手册。**禁碰** recommender（TB1 契约）、observability（TB2b）、并发槽（TA5）、前端代码。
- SQL 参数绑定；不 push；**每项缺陷一个 commit**：
  - `fix(be)/ta7-d1: 内置工具业务失败不得映射 SUCCESS(凭据语义真化,护栏恢复触发)`
  - `fix(be)/ta7-d2: 课程名解析模糊候选兜底`
  - `fix(be)/ta7-d3: 跨会话记忆召回修复(Milvus NaN 根因)`
  - `docs(demo)/ta7: 黄条/记忆站话术更新`
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TA7.md`：三缺陷修前修后证据（调用日志对照/黄条 3 截图/记忆双会话输出）。

## owner 验收口径

Given owner 演示，When ① 说"收藏《随便编的不存在的课》"，Then AI 如实说没找到+给候选+黄条出现；② 说收藏一门真课时真实收藏；③ 上一会话报的名字，新会话 AI 答得出。
