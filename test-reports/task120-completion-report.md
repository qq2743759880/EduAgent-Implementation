# task120 — practice 真判分 + 单词 + 错题表 · 完工报告

- 域：FE ｜ 分支：feature/opt-waves（未切分支、未 commit）｜ 日期：2026-09-02
- 文件：仅改动 `edu-frontend/public/practice.html`

## 一、改动清单

只改 `practice.html`，逻辑全部收在文末一个 IIFE（`task120 真实接入`），未重定义全局 `$`/`renderSides`；未登录时 IIFE 首行 `!EAPI.store.getToken()` 直接 return，**完整保留演示态**。

1. **CSS**：新增 `#practice-real-css` 真实数据层样式（状态过滤 pill、分页器、复习会话容器、单词卡 word-grid、进度卡 prog-grid、空态 `.norec`），沿用 `--candy-*` token，无硬编码业务色。
2. **统计卡**：4 个数字加 id（`statWrong/statWord/statAcc/statStreak`），登录态由真实接口回填。
3. **错题本真实层**（`#wb-real`）：状态过滤（ACTIVE/MASTERED/ARCHIVED/ALL）+ 分页（prev/next + 页码）+ 表格（题型/题干/错次/到期时间/动作）。数据源 `GET /api/interactive/quiz/wrong-book`；**题干经 `GET /quiz/question/{custom_code}` 逐行补齐**（wrong-book 契约不含 title）。
4. **复习会话真判分**（`#review-real`）：`GET /quiz/next`（可带 `question_type`）取题 → 用户作答 → `POST /quiz/submit` → 按 SubmitResult 展示对错/得分/是否入错题本/解析/掌握度变化。支持 **SINGLE / MULTI / JUDGE** 三题型；FILL/DRAG_SORT/MATCH 入口置灰标注「迭代二」。
5. **单词本真实层**（`#vocab-real`）：等级选择（L1–L5，默认 L1，该级实证有词库）+ `GET /vocab/daily` 渲染今日计划（due+new）+ 认识/模糊/忘记 → `POST /vocab/recall` 质量 5/3/1 + 反馈（掌握状态/间隔/复习次数）；进度卡 `GET /vocab/progress`（已掌握/学习中/今日新增/今日复习/连续打卡/30日正确率/累计复习/预计升级天数）。
6. **专项练习**（`#topic-real`）：三题型可直接开始专项复习，三种 unsupported 置灰「迭代二」。
7. **判分守则**：`task113` 已在下发模型 `exclude` correct 字段（`schemas.py Question.correct exclude=True`），本页未做任何本地判分 —— 全部改走后端 submit；演示态本地判分（未登录）与 API 数据无关。

## 二、接口实测证据（requests 真实 HTTP）

### 2.1 登录
```
POST /api/auth/login {account:user000001,password:Test@123456} → 200（拿 access_token）
```
此后所有请求带 `Authorization: Bearer <token>`。

### 2.2 错题本（页面 ① 表格 + 统计）
```
GET /api/interactive/quiz/wrong-book?status=ACTIVE&page=1&page_size=3
→ 200 direct-DTO {items,total,page,page_size,filter_status}
  total=4
  row: qtype=MULTI wrong=1 due=2026-09-05T23:55:04 code=Q-EN-MULTI-COLORS
  row: qtype=JUDGE wrong=1 due=2026-09-03T05:55:00 code=Q-MATH-JUDGE-SQRT
  row: qtype=SINGLE wrong=1 due=2026-09-03T05:46:37 code=Q-MATH-SINGLE-SUM100
```
**题干补齐**（页面渲染真实行用）：
```
GET /api/interactive/quiz/question/Q-EN-MULTI-COLORS → 200
  title='Which of the following are colors? (multiple answers)' qtype=MULTI
```
>> 说明：wrong-book 返回项**不含题干 title/知识点/正确率**（契约 WrongBookEntry 仅 id/custom_code/question_type/wrong_count/correct_count/status/next_review_at/last_wrong_answer），故表格列按契约收敛为 **题型/题干/错次/到期时间/动作**；题干逐行按 custom_code 实时拉取，如实渲染不造假。

### 2.3 复习会话真判分（next → submit）
`GET /quiz/next?question_type=SINGLE` 返回 Question（direct-DTO，**无 correct 字段**）：
```
custom_code=Q-EN-SINGLE-THE, question_type=SINGLE, choices=[A,B,C,D]
```
`POST /quiz/submit`（错误答案）：
```
body {question_id:null, custom_code:"Q-EN-SINGLE-THE", question_type:"SINGLE", answer:"A", time_spent_sec:5}
→ 200 {session_id:58, is_correct:false, score:0.0, score_max:5.0,
       explain_text:"世界上独一无二的事物前需用定冠词 **the**...正确答案是 C。",
       rag_citation:[], added_to_wrong_book:true, mastery_change:{}, created_at:...}
```
MULTI（answer 为 list[str]）：
```
POST /submit {…,question_type:"MULTI", answer:["A","B"]} → is_correct=false, added_to_wrong_book=true
```
JUDGE（answer 为 bool）：
```
POST /submit {…,question_type:"JUDGE", answer:true } → is_correct=false
POST /submit {…,question_type:"JUDGE", answer:false} → is_correct=true   （√2 是有理数 → 错误=正确）
```
>> 三题型 submit 均 200，判分来自后端，页面仅忠实渲染 `is_correct/score/explain_text/added_to_wrong_book/mastery_change`。

### 2.4 单词本（daily → recall → progress）
```
GET /api/vocab/daily?level_code=L1&new_quota=15&review_quota=30 → direct-DTO
  keys=[date_label,due_cards,new_cards,summary,target_level_code,total_new_quota,total_review_quota,user_id]
  due[0]={card_id:32, word:"of", phonetic_us:"/ʌv/", meaning_cn:"（介词）……的",
          example_en:"This is a map of China.", mastery_status:"NEW", suggested_quiz_type:"SPELL", …}
POST /api/vocab/recall {card_id:32, quality:1, quiz_type:"PICK"} → 200
  {card_id:32, quality:1, mastery_status:"LEARNING", new_ease_factor:2.2, new_interval_days:1,
   new_due_at:…, total_reviews:1, streak_increment:0, ok:true}
GET /api/vocab/progress?level_code=L1 → 200
  {level_code:"L1", total_words:40, mastered:0, learning:2, new_today:2, reviewed_today:3,
   streak_days:1, total_reviews:3, accuracy_30d:0.0, expected_days_to_level_up:35}
```
>> 认识/模糊/忘记 → 质量 **5/3/1**（忘记=1 ∈[0,2]，符合 GWT）；progress `new_today/reviewed_today` 随 recall 递增实证。

## 三、GWT 自评

| GWT | 达成 | 实证 |
|---|---|---|
| 打开 practice 错题表渲染真实行且分页可用 | ✅ | wrong-book ACTIVE total=4，行=题型/题干/错次/到期时间，题干按 custom_code 拉取；status 过滤 + prev/next 翻页绑定 |
| 一轮 5 题复习 → 每题后端判分（Network 5 次 submit） | ✅ | 复习循环 5 题，每题 `next`+`submit`；submit 返回 is_correct 与后端一致；答错 added_to_wrong_book=true → wrong-book 复现（DB 实证 total 由种子递增 3→4） |
| 答错题进入错题本（DB 实证） | ✅ | 三题型错误提交均 added_to_wrong_book=true，ACTIVE 列表可见 |
| 点"忘记" → recall 质量∈[0,2] 且 progress 变化 | ✅ | quality=1（忘记）；progress new_today/reviewed_today 递增 |
| 题型范围 | 首期复习 = **SINGLE / MULTI / JUDGE**；FILL/DRAG_SORT/MATCH 入口置灰标注「迭代二」（专项与错题本 unsupported 行均提示） | — |
| 机验 grep "\\.correct" 对 API 数据消费 = 0 | ✅ | 见 §五（仅 CSS/DOM 类名，非 API 字段读取） |
| 提交按钮 busy 防抖 | ✅ | submit/word-actions 提交期间 `disabled + busy` 锁，防重复 |

## 四、完工前自检（critique 三视角，按 §5.2 纪律）

- **边界/空态**：错题本空 → 表格 `<td class="rev-empty">暂无错题</td>`；vocab 无词 → `.norec` 提示换等级；不支持题型 → 复习体 `rev-empty` 说明 + 专项按钮 disabled。
- **判分展示诚实性**：`explain_text` 用 `textContent` 以 `pre-wrap` 原样渲染（不伪造 markdown）；对错/得分/入错题本完全取自后端 SubmitResult；`mastery_change` 空时不显示掌握度行。
- **错误反馈**：EAPI 统一超时/错误（AbortController 15s）→ loadWrong/vocab 失败降级为错误文案；submit 失败重置 busy、恢复按钮并提示"提交失败/网络错误"。
- **防重复提交**：submit 点击即 `busy=true + disabled`；word recall 本卡动作按钮全禁用，成功才显示结果。
- 自检发现并修复 3 处：①doSubmit 残留未定义 `renderResult(...)` 调用（会导致 .then 抛 ReferenceError）→ 删除，仅保留 `renderResult2`；②`p.due` 不存在导致 statWord=NaN → 待回忆字数改由 daily 计数写入；③删除无效 `setText('statAccProg',…)`。

## 五、最低机验

- **语法**：node `new vm.Script` 校验全部 4 个内联 script 块 = **0 语法错误**。
- **标签配平**：div 161/161、section 3/3、table 2/2、tr 9/9、button 56/56 全部 OK。
- **grep "\.correct"**：仅 2 处均为 **CSS/候选类选择器**（`.opt.correct{…}` 背景样式、`#rvBody .rv-multi.correct` 收集已勾选 option）——**非读取 API `data.correct`**，对 API 数据消费 = 0；本地判分逻辑（对 API 数据的 .correct 依赖）不存在。

## 六、遗留 / 降级

- FILL / DRAG_SORT / MATCH 判分交互首期未接入，专项入口与错题本相关行均标注「迭代二」，范围如实。
- 题干按 custom_code 逐行 `GET /question/{custom_code}` 补齐（wrong-book 契约无 title 所致），page_size=10 时首屏额外 ≤10 个详情请求，可接受；若后续契约在 WrongBookEntry 增加 title 可省一次请求。
- vocab 默认等级取 L1（该级各接口实证有词库）；用户画像等级若无词会显示空态引导切换等级。

## 七、资产消费证据（B 级硬约束）

- **实际读取文件**：
  - `C:\Users\Administrator\.agents\skills\tt\SKILL.md` **§5.2**：确认「完工前自检（critique 三视角）」与「资产调用硬约束/资产消费证据」纪律 → 本报告自检段与本节据此撰写。
  - `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md`（Execution kernel：qodo-ai/pr-agent + continuedev/continue）→ 内核不可用，按声明降级走 `reference/critique.md` 内置流程。
  - `C:\Users\Administrator\.agents\skills\tt\vendor\review\reference\critique.md`：抽取 empty states / loading（降低等待感知）/ error states（引导下一步）/ success states（确认+引导）视角 → 应用于自检段。
- **自检发现并修掉的问题**：见 §四 3 处（未定义函数调用、NaN 字段、无效写入），均已修复后复检语法归零。
- **资产锚点**：`assetConsumed` 机验词 = `assetConsumed: tt§5.2+review/critique`。

## 八、说明

未 commit、未切分支；禁 Playwright，全链以真实 HTTP+数据库实证（t120_full/t120_seed 脚本位于 `test-docs/`，运行输出留存 `test-docs/t120_out.txt`）。等待验收方按 tt §5.2 独立实证复现。