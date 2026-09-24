# TO-EXEC-TA6 — 对话建课/收藏易用性（owner 实测反馈：要填很多 ID）

> 分支 `feature/opt-waves`；后端 9988 在岗。开工令自包含。owner 原话定性："让他帮我创课程有相关功能，但步骤十分繁琐，要提供很多 id 参数以至于测试失败。"

## 定因（编排者已核，执行者复核）

`app/mcp/executor.py:1279` `_course_create_handler`：必填仅 `title` + `series_code`（`^[a-z0-9_]+$` ≤64），`institution_id` 服务端自动解析（executor.py:1336 最小 yn=1 院校），`modules` 可选。**用户不该被要任何 ID**——但 LLM 把内部参数名原样抛给用户（msg912 同病：favorite_add 反问 course_id 而不是自己按课程名解析）。两层根因：① 工具 schema 里 series_code 必填且无自动派生；② 模型缺"禁止向用户索要数据库 ID"纪律。

## 工作项

1. **series_code 改可选**：不传时服务端按 title 自动生成合法编码（slug 规则自定：如小写+下划线，中文 title 用可读转写或 `course_` 前缀+短随机后缀），唯一约束冲突（40901）时自动加后缀重试 ≤3 次；用户显式传了才用用户的（保留 exact-pin 校验）。`modules` 语义不变。
2. **favorite_add 支持按名解析**：读 `favorite_add` handler 现行参数——允许传课程名（course_name），服务端按课程名精确/唯一匹配 DB 解析 course_id（模糊多命中时返回候选列表让模型追问一次，不许猜）；course_id 直传路径保留。
3. **模型纪律**：在工具定义 description/系统提示层加一条硬纪律："**禁止向用户索要数据库 ID/编码类内部参数**——能派生的派生（series_code），能查的先查（course_id），解析不了再问且只问业务语言（如'哪门课'）"。改动点选在工具 def 注册处（executor 注册 description）+ chat 系统提示（`app/chat/prompts/` 现行文件），最小化。
4. **自验（真实 HTTP，admin `adm02test`）**：
   - ① 对话只说"帮我创建一门《TA6 验收课程》"（不给任何编码）→ 确认卡弹出且 args 里 series_code 已自动生成 → approve → series 表 +1 行、编码合法、created_by 正确。
   - ② student `user000001` 说"把《Python 入门》加入收藏"（不给课程 ID）→ favorite_add 真实执行（user_write 不弹卡）→ favorites 落库；执行后把这条收藏软删/按项目口径清理并报告。
   - ③ 显式传 series_code 仍走用户值；传非法 series_code 仍被 exact-pin 拒。
   - ④ 回归：`pytest -k "favorite or course or hitl"` 子集零新增失败。

## 铁律

- 域：`app/mcp/executor.py`（两 handler + 工具 description）、`app/chat/prompts/` 现行提示文件、（如确需）课程解析用的只读 SQL。**禁碰 `app/chat/service.py` 并发槽逻辑（TA5 在改）、observability（TB2-b 在改）、recommender（TB1 在改）、前端**。
- 注意与 TA5/TB1/TB2-b 的同仓并行：开工前先 `git log --oneline -3` 记基线，只提交本单文件。
- SQL 参数绑定；不 push；单 commit：`fix(be)/ta6: 对话建课零 ID 化(series_code 自动派生)+favorite_add 按名解析+禁索 ID 纪律`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TA6.md`：diff 摘要、四步自验 HTTP 证据、回归输出。

## owner 验收口径（GWT）

Given owner 用 admin 登录，When 只说"帮我创建一门《XXX》课程"，Then 弹确认卡→同意→课程出现，全程零 ID 输入；student 说"收藏《某课程》"同理零 ID。
