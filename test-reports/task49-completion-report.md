# task49 完成报告 · /practice/[mode] 复习中心练习页（React 实现）

> 前端开发者（TRAE SOLO CN） · 糖果色 candy-playful FROZEN
> 依赖：task44/46/47/48 ✓；task13（契约④ question 出题源已切 question 表）；task40 契约⑤（interactive/quiz）
> 状态：**完成，交付 fe-tester 独立复核 APPROVED，待编排者验收**

---

## 一、任务范围（HTML 审核流 ✓ → React）

- **Step1 效果图已签收**：`test-reports/fe-html/practice.html`（糖果三入口 + StatCard + 复习作答 + analysis_text 解析演示），用户已 APPROVED。
- **Step2 React**：本报告覆盖。三模式 `/practice/[mode]` = `wrong-book | topic | vocab`。

## 二、产物清单

| 文件 | 说明 |
|------|------|
| `src/app/(user)/practice/[mode]/page.tsx` | mode 扩展至 wrong-book/topic/vocab；非法 mode → UnsupportedMode |
| `_components/PracticeCenterClient.tsx` | 糖果头 + 三入口卡 + 统计行 + 内容区分发（列表 ⇄ 复习会话） |
| `_components/CandyStatRow.tsx` | 顶层统计：错题待复习 / 待回忆单词 / 连续学习（真实源，缺失显示占位） |
| `_components/WrongBookPanel.tsx` | 错题 DataTable + 开始复习/行内重做 + 分页 + 空态/错误态 |
| `_components/TopicPanel.tsx` | 专项练习：按 dim_question_type（题型）过滤的四种题型卡 |
| `_components/QuizSession.tsx` | 复习会话核心：取题→作答→判分→explain_content 解析（MarkdownView） |
| `_components/QuizSession.test.tsx` | 9 个单测（GWT①② + 状态机/辅助函数） |

## 三、数据契约（复用 task40 契约⑤，禁 MOCK）

错题出题源已切 **question 表**（task13/契约④），全部复用 `@/lib/api/learning.ts`：

| 接口 | 用途 |
|------|------|
| `listWrongBook({only_not_mastered})` | 错题列表（GET /api/interactive/quiz/wrong-book） |
| `getNextQuestion` | 逐题取题：wrong-book → `{from_wrong_book, prefer_wrong_book_ratio, only_not_mastered}`；topic → `{mode: <题型>}` |
| `submitAnswer` | 判分 → 返回 `is_correct / correct_answer / explain_content`（即 analysis_text） |
| `getVocabDaily/Progress/recallVocab` | 单词本 SM-2（**范围外复用不动**） |

**时间戳/判分真实**：`time_spent_seconds` 由出题时 `Date.now()` 起算、提交时一次性计算（禁用固定字面量假值）。

## 四、与 HTML 效果图 / task59 的一致性

- 交互对齐 practice.html：入口卡 Green/Blue/Purple、StatCard、判分横幅（✓/✗）、解析面板 `✦ 本题解析 · analysis_text`。
- **analysis_text 渲染**：复用项目统一安全 Markdown 渲染器 `<MarkdownView content={result.explain_content} />`（react-markdown 默认 skipHtml，无 rehypeRaw，安全性对齐），样式与 task59 管理端预览标签一致。

## 五、GWT 验收逐条

**GWT① Given HTML APPROVED, When 复习作答, Then 判分即时展示 + analysis_text 解析渲染（Markdown 预览与 task59 管理端一致）**
- QuizSession 提交 `submitAnswer` → `setResult` + `setPhase("result")` → 判分横幅（回答正确/错误 + 得分 + 正确答案提示）→ `MarkdownView` 渲染 `explain_content`。✅ 单测「渲染题干与选项，答对后展示判分横幅与 Markdown 解析」「答错时展示错误横幅与正确答案提示」。

**GWT② Given 错题本加载, When 请求, Then 数据来源 question 表（题干含解析字段），无旧 admin_question 引用**
- 全部数据走 `listWrongBook`/`getNextQuestion`（question 表出题源），fe-tester 独立 grep 确认对 `admin_question`/`WrongBookList`(旧) 引用 = 0。✅

**GWT③ Given 词卡回忆, When 进入单词本, Then SM-2 行为不变（范围外不动）**
- vocab 复用 `VocabDailyPanel`/`VocabProgressCard`，fe-tester 确认两文件 LastWriteTime 早于 task49 未被改动。✅

## 六、验证证据（fe-tester 独立子代理复核，全程只读）

| 项 | 结果 |
|---|---|
| tsc --noEmit | 0 错误 |
| eslint（7 文件） | 0 error / 0 warning |
| 新增单测 QuizSession.test.tsx | 9 passed |
| 全量 vitest | 52 files / 389 tests 全绿 |
| npm run build | 成功；`/practice/[mode]` = ƒ Dynamic |

**grep 审计固定 4 项（task48 修复后强制）**：任意字号 `text-[Npx]` = 0；硬编码 hex class = 0；内联 style 色值 = 0；禁闭色（sky/violet/cyan/teal/fuchsia）= 0。

## 七、待联调说明（契约未就绪处理）

- interactive/quiz 后端未完全就绪：拉题/错题失败出 ErrorState + 重试，提交失败卡内提示，全部真实接口调用，**无 MOCK**。
- vocab SM-2 复用不动（既有契约，范围外）。

## 八、交付物

- 完成报告（本文件）、效果图 `test-reports/fe-html/practice.html`
- git commit（含 task49）：见 git log
- 已运行 `powershell -File D:\.ai-hub\sync.ps1`

**已交付，停下等待编排者验收指令，不进入下一任务。**