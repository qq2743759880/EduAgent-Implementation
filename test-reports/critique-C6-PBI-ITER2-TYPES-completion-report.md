# C6-PBI-ITER2-TYPES 完工报告（critique-C6-PBI-ITER2-TYPES-completion-report）

> 日期：2026-09-04 ｜ 执行模式：TT 编排 C6 题型扩展迭代二（practice/复习加 FILL/DRAG_SORT/MATCH 真实作答）
> 交付文件：仅 `edu-frontend/public/practice.html`（唯一改动文件，未新增交付源码文件）
> 打靶脚本（测试资产，非交付）交由编排者复核：`test-reports/tt_target_iter2_types.js`

## 目标与判定口径

PBI-ITER2-TYPES 判定口径：
1. **登录态下 FILL/DRAG_SORT/MATCH 三题型可点可答**，后端返回**真实判定**（非演示/非"暂未开放"）；不再弹"暂未开放"toast。
2. **错题本里这三类型错题 row 可进入复习**（`SUP_REVIEW` 判定不再当"不可练"），复习会话能按三型渲染并作答。
3. 不改后端契约，answer 格式与 `schemas.py` 对齐；糖果 token、无 MOCK 冒充真实反馈、`演示数据` 角标不动。

三项口径：✅ 全达成（见"批判承接核对"）。

## 资产消费证据

开工前真实读取：
- 工作区规则 `AGENTS.md`（前端注入模式 / edu-api.js / 关键教训 4、9：IIFE 注入、`URLSearchParams` 走 `EAPI.pageId`、避免重定义全局）——按此保持既有空 IIFE 注入模式，未引入新全局冲突。
- 后端契约 `edu-agent/app/interactive/quiz/schemas.py`：
  - `SubmitAnswer.answer`：FILL=`list[str]|str`、DRAG_SORT=`list`、MATCH=`list[{left_id,right_id}]` → 前端 `collectAnswer` 据此返回。
  - `Question.correct` 已 `exclude=True` → 前端渲染只依赖 `items`（DRAG_SORT）/`pairs`（MATCH）/题干`___`（FILL），打靶实证 `has_correct=false`。
  - FILL 无 `items`/`pairs` 下发 → 空位数须前端推断（见 FILL 空位数策略）。
- 后端判分 `edu-agent/app/interactive/quiz/service.py` `_grade()`（L253-315）：
  - FILL 逐空 `str(a).strip().lower()==str(c).strip().lower()`，空位数不匹配返回 0；→ 前端必须逐空 `.trim()` 且空位数一致。
  - DRAG_SORT 按**位置**匹配 `pos_match/len` 计分（全对才 `is_correct=true`）。→ 前端必须按"屏幕显示序"提交，不能按原始序。
  - MATCH 按**配对命中数**计分。→ 前端每条 `<left_id,right_id>` 提交。
- 后端路由 `edu-agent/app/interactive/quiz/router.py`：`next`/`submit`/`wrong-book`/`wrong-next`/`question/{custom_code}` 前缀 `/api/interactive/quiz`，均需登录态（`Depends(get_current_user)`）。
- 目标文件 `practice.html` 通读全量：`SUP/SUPKEY/SUP_REVIEW`、`renderQuestion/collectAnswer`、类型条 `.iter2`、错题本 `wb-filter .pill.iter2`、`showIter2/iter2-toast`、`bindTopicControls` 迭代二守卫。
- 前端设计资产：按编排要求改用本仓库糖果契约（`--candy-*` token），三态（作答→判分→错误反馈）沿用现 `renderResult2` 的 `result.ok/.error + rev-expl` 机制，交互/判分三态与现状一致；未读外部 skill（本机路径不可直接读写），已在代码中沿用既有实现风格。

**自检发现并修复**：
- `next?question_type=FILL` **不保证返回该题型**（后端 `__next` 优先到期错题、`ensure_type=False` 时同型过滤落空则回退全题库）——打靶脚本首轮即踩中（返回 Q-MATH-SINGLE-SUM100 而非 FILL）。此属后端既有行为，非本任务可改（红线：不改契约）；已改走 `/question/{custom_code}` 精确打靶，并在"遗留/风险"登记该观测。前端专项入口/错题本 redo 拉到的题目无论哪型都能被新渲染分支承接，故闭环仍成立。
- 打靶脚本 console 曾因 `+`/`&&` 优先级丢前缀字符串 → 已用 `String()`/模板修正。

## 实现明细（仅 `practice.html`）

**渲染分支（`renderQuestion`）**
- `FILL` → `renderFill(q)`：`fillBlankCount(q)` 确定空位数（策略：① `q.items` 长度优先；② 数题干 `/_+/g` 中长度≥2 的连下划线占位符数量；③ `Math.max(1,n||1)` 兜底）。逐空渲染 `.fill-row`(标签+`.blank-input`)，单空省略"第 1 空"标签。
- `DRAG_SORT` → `renderDrag(q)`：遍历 `q.items` 渲染 `.drag-item`（顺序号 + label + ↑/↓ 交换按钮），非 HTML5 drag、交互清晰（critique 可解）；ES/HTML/视觉三态健全。
- `MATCH` → `renderMatch(q)`：遍历 `q.pairs` 左项渲染 `.match-item`，每项配一个右项 `<select>`（选项=全部 right_text）；下拉选择即连线。
- 未知题型保持优雅降级提示；三型均有空态（无 items/pairs 时提示"暂无可…"）。
- 新增 CSS：`.fill-blanks/.fill-row/.drag-list/.drag-item/.match-grid/.match-item` + `.type-chip.drag/.type-chip.match`，全部为 `--candy-*`/`--ht-*` token，零硬编码业务色。

**收集（`collectAnswer`）**
- FILL → `list[str]`（每空 `.trim()`）；DRAG_SORT → 屏幕显示序 `list[item_id]`；MATCH → `list[{left_id,right_id}]`。

**提交/校验/反馈（`doSubmit`）**
- 三型校验：FILL 全空必填（`ans.some(!v)` 拦截避免后端"空位数匹配"语义歧义）；DRAG_SORT 需有条目；MATCH 每项需已选右项。
- 提交体沿用现结构 `{question_id, custom_code, question_type, answer, time_spent_sec}`，走 `EAPI.post('/api/interactive/quiz/submit')`。
- 反馈沿用 `renderResult2`：`is_correct/score/score_max/added_to_wrong_book/explain_text` 如实渲染；**错误/4xx 壳**走 `.catch` → `.result.error` + `e.message` 提示，不静默。

**移除迭代二占位**
- `SUP_REVIEW` 三型 → `true`（L890）。
- 登录态专项 `wb-filter` 三 pill：去 `iter2` 类/`data-iter2`/`title`，改真实可点筛选（`bindTopicControls` 已删 `if(b.dataset.iter2){showIter2...}` 守卫 → 直接 `startReview({type})`）。
- 类型条 `③ 填空 · 迭代二` → `③ 填空` 可选中（demo 态切到真实填空演示项）。
- 删除 `showIter2` 函数及 `iter2Timer`、`.iter2` 两处 CSS、`.iter2-toast` CSS 与所有调用点（grep 待办零残留，见实测）。

**错题本专项复习闭环**
- `loadWrong` 行判定 `SUP_REVIEW[row.question_type]!==false` 对三型恒真 → 渲染"重做"按钮；重做 → `startReview({type:null})` → `next` 拉题（错题优先）→ `renderQuestion` 现可按任意三型渲染作答。

## 独立实证验证（真实 HTTP + 真实后端 8000，student user000001/Test@123456）

前端 JS 语法：`node --check`（抽取内联 `<script>` 块）→ **JS SYNTAX OK**。

真实打靶（`tt_target_iter2_types.js`，登录 200 拿 token 后精确打 `/api/interactive/quiz/question/{code}` → `/submit`）：

| 题型 | custom_code | 提交答案 | is_correct | score | 入错题本 | 说明 |
|----|----|----|----|----|----|----|
| FILL | Q-EN-FILL-BIGGER | `['bigger']` | true | 5/5 | false | 判对 |
| FILL | 同上 | `['biiger']` | false | 0/5 | true | 判错（逐空 strip/lower） |
| DRAG_SORT | Q-MATH-DRAG-OP | `['C','B','A']` | true | 5/5 | false | 全位正确判对 |
| DRAG_SORT | 同上 | `['A','B','C']` | false | 1.67/5 | true | 1/3 位置分 |
| DRAG_SORT | 同上 | `['C','A','B']` | false | 1.67/5 | true | 仅首位对→1/3（**位置分实证**） |
| MATCH | Q-EN-MATCH-ANTONYM | L1-R1,L2-R2,L3-R3 | true | 5/5 | false | 全对判对 |
| MATCH | 同上 | L1-R2,L2-R1,L3-R3 | false | 1.67/5 | true | 1/3 配对命中 |

- 下发题证实：三型题型 `has_correct=false`（`correct` 已 exclude，前端拿不到答案）；DRAG_SORT 下发 `items`、MATCH 下发 `pairs`、FILL 无 items/pairs → 空位数推断必要。
- 错题本归集：`wrong-book?status=ACTIVE` total=8，`{"FILL":1,"DRAG_SORT":2,"MATCH":1,"SINGLE":2,"MULTI":1,"JUDGE":1}` → 三型错题确实入本，`SUP_REVIEW` 全 true 路径下渲染 redo、可复习。

静态自查：
- `data-iter2 / showIter2 / iter2Timer / iter2-toast / "iter2" / .iter2` 残留 = 0（仅 4 处注释含"迭代二"字样，属合理说明）。
- 硬编码 hex：全文件仅 token 定义区 `:root`（L23-44）与尾巴 `演示数据` 角标（L1416，任务明确不动）；**我新增代码零 hex**，全走 token。
- `SUP_REVIEW[` 仅 1 处（L938 错题行判定），全 true 下恒真。

## 批判承接核对（C6 三项口径）

| 承接项 | 结果 |
|----|----|
| 登录态三题型可作答 + 后端真实判定（非演示/非占位） | ✅ 打靶证实 is_correct/score 为后端真判（含位置分/配对分/逐空判分） |
| 错题本三型可复习（SUP_REVIEW 不再当不可练） | ✅ SUP_REVIEW 全 true；错题归集含三型；redo→复习会话按三型渲染 |
| 不改契约 + 糖果 token + 无 MOCK 冒充 | ✅ answer 对齐 schemas.py；零新增硬编码色；未引入 MOCK |

**FILL 空位数策略边界（如实登记）**：FILL 后端不下发空位数（`items` 仅 DRAG_SORT 填充、`_load_by_code_or_id` 对 question 表真实题不填 items/pairs）。前端策略为"优先 items → 数题干 `___` → 兜底 1"。局限：
1. 多空但题干用非下划线占位（如数字序号、单个 `_`、图片内占位）时可能漏计/误计；
2. 单个 `_` 不会计入（避免 markdown/code 误判），但若题目真用单 `_` 作占位会少算一空；
3. 真实题库（question 表 `stem`）若占位风格不统一，空位数可能与后端 `answer_text` 数组长度不符 → 后端返回"空位数不匹配"0 分。改进方向（后续）需在契约里为 FILL 下发空位数或 `items`（issue：后端 FILL 未落地）。mock（Q-EN-FILL-BIGGER）为 1 空，实证通过。

**MATCH 正确配对在 pairs 泄露（设计观察）**：mock 的 `pairs` 即正确答案映射（每 left 的 right 就是唯一正确项），前端渲染据此能直接推出答案（`pairs` 字段对外虽注释"左右乱序"但 mock 未混淆）。需后端对 `pairs` 做真正混淆（乱序 right 侧 + 随机 key）才能防作弊。本任务不改契约，仅按 pairs 渲染 UI。

## 遗留 / 风险
- **`next?question_type=X` 不强制题型**（后端 ensure_type=False + 错题优先）：专项练习"填空/拖拽/连线"入口在存在到期错题时可能拉到任意 type 的错题；前端三型渲染已全覆盖，故不会无法作答，但"专项 FILL"不保证出 FILL 题。属后端既有行为，非本任务范围。
- **FILL 多空空位数推断局限**（同上节），真实题库风格不统一时可能判"空位数不匹配"0 分；建议后续下拉直接在后端 Question 固化空位数（或补 items）。
- **真实题库（question 表）的 DRAG_SORT/MATCH 未填充 items/pairs**（`_load_by_code_or_id` 只映射 choices）：打到这类真实题时前端会渲染"该排序/连线题暂无可用条目"空态。mock 打靶已覆盖；真实数据可补充时需在后端填充 items/pairs。
- 打靶污染了 student 错题本：写入 FILL/DRAG_SORT/MATCH 若干错题（total 扰动由 4→8）。如需干净环境可清空该账号 quiz_wrong_book/quiz_answer_session，未在交付中处理（避免越权改库，留编排者决策）。
- 门户/其它页面的同类"迭代二"占位（若有）不在本任务文件范围内，未扫。

## 交付摘要
- 改动文件：`e:\stu\project\stu\EduAgent实施手册\edu-frontend\public\practice.html`（仅此文件）
- SUP_REVIEW 现状：`{SINGLE:true, MULTI:true, JUDGE:true, FILL:true, DRAG_SORT:true, MATCH:true}`
- 打靶 is_correct 证据：见上表（真实判定，答对得对、故意答错得错、部分得分实证）
- iter2 残留 grep：`data-iter2/showIter2/iter2Timer/iter2-toast/"iter2"/.iter2` 全部 = 0；仅 4 处注释含"迭代二"字样
- FILL 空位数策略：items→`___`(≥2连下划线) 计数→兜底 1，局限见上
- 测试脚本：`test-reports/tt_target_iter2_types.js`（编排者复核用）