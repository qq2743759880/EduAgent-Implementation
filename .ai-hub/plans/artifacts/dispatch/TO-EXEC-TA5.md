# TO-EXEC-TA5 — user 并发槽泄漏修复（yy 新增单，P0 验收时发现）

> 分支 `feature/opt-waves`；后端 9988 在岗。开工令自包含。

## 背景（编排者实测复现）

P0 验收时实测：`user000001` 调 `/api/chat/stream` 直接返回 `done` 帧 `degraded_reason:"user_concurrent_over_limit"`（latency 20ms，零 token）。TA1-3 执行者在 LLM 上游失败窗口观察到该用户并发槽未随失败释放（进程内计数器泄漏），重启后端即恢复。**根因方向：LLM 失败/超时/异常路径没有走 finally 释放并发槽**——只有正常 done 释放。这是演示阻断级缺陷（owner 的 student 账号聊几轮坏了就永久降级）。

## 工作项

1. 读并发槽实现（`app/chat/service.py` 附近，搜 `concurrent`/`user_concurrent_over_limit`），定位获取/释放路径；确认失败路径（LLM 异常、SSE 客户端断连、超时）是否释放。
2. 修复：释放收口到 `finally`（或等价机制），保证任何退出路径都归还槽；**不得放宽并发上限本身**。
3. 自验（真实 HTTP）：① 正常问答一轮后同用户再问，不出现 `user_concurrent_over_limit`；② 人造失败路径（如临时指向不可达上游或用不可达模型名发起）后，同用户再问**不**被限（此步不许改 .env 持久配置，用请求级/临时手段，验完即还原）；③ 并发上限语义仍在：同用户并发打满时仍正确拒绝。
4. 回归：跑 chat 相关既有 pytest 契约测试（`pytest -k chat` 或项目内对应套件），零新增失败。

## 铁律

- 只许改并发槽相关后端文件（预计 `app/chat/service.py` 或其并发模块）；禁碰 recommender（TB1 在改）、`.env`、前端。
- SQL 参数绑定；不 push；单 commit：`fix(be)/ta5: chat 用户并发槽失败路径泄漏修复(finally 收口)`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TA5.md`：泄漏路径定位（文件:行）、修复 diff、三步自验 HTTP 证据、回归结果。

## owner 验收口径

Given owner 用 student 账号连问多轮（含一次中途打断），When 继续提问，Then 永远能正常回答，不再出现"并发超限"降级。
