# 契约变更单 reshape-a2(第三波验收发现的缺口,待用户签字)

> 来源:第三波独立验收 + task06/10/12 完工报告的缺口上报(均已 curl/DB 实证)。签字后冻结为 `contracts/reshape-a2.json`。

| # | 变更 | 动机(实证) | 提案 | 优先级 |
|---|---|---|---|---|
| 1 | 新增 `POST /api/progress/video/start` body=`{video_id, cohort_id}` → `{play_session_id}` | G1(P0):tick-batch 要求已存在的 session_video_play.id,但全后端无任何创建播放会话的 INSERT(400010+只读 DB 证实 user1 仅种子行)→ 学习页打点链路死锁,前端已诚实降级 | 建 play 会话端点;G2 一并解决:`last_position_seconds` 经 tick 更新,watch_ratio 才有分子 | P0 |
| 2 | 澄清 `GET /api/admin/courses/series` 过滤语义 | agent④ 实测:`status` 参数被忽略(2629 全量);有效参数 `sale_status=off_sale`(56);`include_deleted=true` 是"不过滤全量"而非"仅回收站"——现 admin-courses.html 回收站视图过滤语义错误 | 文档层澄清+admin-courses 接线时用 `sale_status=off_sale` | P1(接线必修) |
| 3 | 管理端全局聚合端点(订单数/营收/热门课程) | task12 实证:trade 域全为用户本人视角,无管理端聚合 → 仪表盘三区块只能占位 | 归 task70-91 后端聚合范畴,单独立项 | P2 |
| 4 | `POST /api/favorites` 补登 | 已在 reshape-b.json amendments 补登(2026-09-06 验收 A4),此处汇总可见 | 无代码变更 | 已闭环 |

签字格式:`1 同意 2 同意 3 同意` 或逐条改。
