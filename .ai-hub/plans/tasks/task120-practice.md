# task120 — practice 完整接入（真判分 + 单词 + 错题表）

- 域：FE ｜ 平台：trae ｜ 波次：W3 ｜ 依赖：task101；**与 task113 组成依赖边**（correct 字段移除前必须已切后端判分）
- 文件：`practice.html`

## 目标
练习页从"仅写一个错题数 + 本地假判分"升级为真实练习闭环。

## 证据
- audit §1.1：practice.html 注入"勉强有效：仅写错题数一个数字"；四题型复习会话为本地判分（潜在依赖 quiz `correct` 泄漏字段）。
- audit §X8/B3：后端 `POST /api/interactive/quiz/submit` 真判分 + 错题本回写；task113 将移除 `correct` 下发。
- 可用契约：`GET /quiz/next`（优先到期错题）、`POST /quiz/submit`（SubmitResult：is_correct/score/explain_text/added_to_wrong_book/mastery_change）、`GET /quiz/wrong-book`（page/page_size/status/due）、`GET /quiz/wrong-next`、`GET /api/vocab/daily|progress`、`POST /api/vocab/recall`（SM-2 0-5）。

## 改动点
1. 错题本表格真实渲染（当前只取 items.length）：题干/题型/错次/到期时间，接翻页与 status 过滤。
2. 复习会话改真判分：每题 `POST submit` 后按 SubmitResult 展示对错/解析/掌握度变化；**删除一切对 `correct` 字段的本地判分依赖**（与 task113 联动，grep 归零）。
3. 单词卡接 `GET vocab/daily` + 认识/模糊/忘记映射 SM-2 质量 0-5 `POST vocab/recall`；进度卡接 vocab/progress。
4. 专项练习入口按题型/错题到期聚合（复用 wrong-book 过滤），不做后端变更。

## GWT 验收
- Given student token 与错题种子，When 打开 practice，Then 错题表渲染真实行（与 curl wrong-book items 一致）且分页可用。
- When 完成一轮 5 题复习，Then 每题判分来自后端（Network 可见 5 次 submit），错对结果与 SubmitResult 一致；答错题进入错题本（DB 实证）。
- When 单词卡点"忘记"，Then recall 请求质量值 ∈[0,2] 且 progress 变化。
- 机验：`grep -n "\.correct" practice.html` = 0；本地判分函数移除。

## 风险
- FILL/DRAG_SORT/MATCH 题型答案结构复杂，首期复习会话支持 SINGLE/MULTI/JUDGE 三类，其余题型入口置灰标注"迭代二"——范围写完工报告。
