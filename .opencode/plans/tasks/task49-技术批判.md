# task49 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task49 /practice 复习中心（TraeWork，commit d3a14e9）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `d3a14e9`（9 文件 +1628，含 practice.html 效果图）|
| 组件交付 | ✅ WrongBookPanel/TopicPanel/QuizSession + page.tsx |
| tsc | ✅ 0 错误 |
| vitest | ✅ **52 文件/389 测试全 PASS 实跑**（29.58s，含 QuizSession 9 项）|
| eslint | ✅ 0 错误 0 警告 |
| grep 审计 4 项 | ✅ 任意字号/hex/内联色/禁闭色全 0 |
| learning 契约 | ✅ listWrongBook(9)/getNextQuestion(6)/submitAnswer(8) 调用确认 |
| explain_content | ✅ 12 处解析 + MarkdownView 5 处渲染（GWT① 核心）|
| 出题源 | ✅ admin_question 0 引用（question 表）|
| MOCK | ✅ 仅测试 vi.mock（假数据禁用验证）|

## 批判 1（P2）：practice HTML 效果图 APPROVED 记录在报告，但编排侧需确认

**问题描述**：报告称"已先产出 practice.html 效果图并经你 APPROVED 后进入 React"——HTML 审核流闭环在 TraeWork 与用户侧完成，编排侧看板应补记（同 task44 经验：HTML 签收须双记录）。

**证据来源**：task49 报告 GWT①；task44-技术批判（HTML 签收看板滞后教训）。

**优化方案**：编排者看板补记 practice.html APPROVED；后续 HTML 签收双记录。

## 批判 2（P2）：QuizSession 依赖 quiz 后端（interactive 模块）待联调

**问题描述**：listWrongBook/getNextQuestion/submitAnswer 走 task40 契约⑤（learning.ts），后端 interactive 模块（错题本/出题/判分）可能未完全就绪——前端写真实接口 + 待联调（测试 vi.mock 隔离）。

**证据来源**：QuizSession 注释"契约未就绪→ErrorState 重试"；后端 interactive 模块状态。

**优化方案**：不阻塞（前端已按规范）。后端 interactive 落地后联调跑契约测试 + Playwright。

## 总评

| GWT | 结果 |
|-----|------|
| ① 判分即时 + analysis_text 解析渲染 | ✅ explain_content MarkdownView 12+5 处 |
| ② 错题本 question 表（无 admin_question）| ✅ admin_question 0 引用 |
| ③ SM-2 词卡范围外不动 | ✅ vocab 复用既有 |

**结论：task49 验收通过。** 前端复习中心完成；批判 1/2 均 P2（HTML 签收双记录 / quiz 后端待联调）。
