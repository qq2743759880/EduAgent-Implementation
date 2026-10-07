/**
 * 管理端题库 枚举与显示辅助（task03，G3 题库管理）
 *
 * 契约来源（L1：以 edu-agent 后端代码为准，design-guide §4.4 仅是摘要）：
 *  - app/domains/question_admin/router.py + schemas.py（P7 管理端题库管理）
 *
 * ⚠️ 与 design-guide 摘要的关键差异（后端代码为权威）：
 *  - 题型枚举是 single_choice / multi_choice / true_false / fill_blank / short_answer
 *    （设计指南写的 single/multi/judge/fill/short 是占位摘要，直接提交会 422）
 *  - options_json 是 [{label, content}] 数组（非 {A:"..."} 对象）
 *  - 批量导入走后端两段式 /import-preview + /import-execute（旧 /batch-import 契约已移除）
 *
 * W-NEXT-FEBE-SCAN-002（2026-09-18，OpenAPI 实测对账）：
 *  - 真实路由是 /api/admin/questions/questions（题目集合）与
 *    /api/admin/questions/questions/{question_id}（单题）——旧代码写的
 *    /api/admin/questions(/{id}) 后端从未注册（404 断点），已对齐。
 *  - 后端无跨题库"题目总列表"端点：题目列表只能按题库查
 *    GET /api/admin/questions/banks/{bank_id}/questions（见 question-bank.ts listBankQuestions，
 *    /admin/questions 页面在用）。
 *
 * W-NEXT-QUESTIONFORM-FIX-001（2026-09-18，follow-up 收口）：
 *  - legacy QuestionForm 组件（task03 草稿 body 构造，与后端 QuestionAdminCreate
 *    真实必填 bank_id/question_type_id/stem/answer_text 不匹配，见
 *    app/domains/question_admin/schemas.py:57）经全仓库 grep 确证零挂载零 import
 *    （唯一 import 是组件自身测试），已整体删除（含 QuestionForm.test.tsx）。
 *  - 本文件死封装 createQuestion/updateQuestion/QuestionCreateInput 及仅其消费的
 *    listQuestionTags/QuestionTag/QuestionAdminDetail/QuestionOption 同步删除。
 *    活 UI：/admin/questions 页两级管理 + BankImportDialog 批量导入 +
 *    QuestionDetailEditor，全部走 question-bank.ts（题目写操作唯一入口）。
 *  - 本文件保留题型/学科/难度枚举与显示辅助（后端契约对照的展示层单一来源）。
 */

/* ============================================================
 * 枚举
 * ============================================================ */
export const QUESTION_TYPE_OPTIONS = [
  { value: "single_choice", label: "单选题" },
  { value: "multi_choice", label: "多选题" },
  { value: "true_false", label: "判断题" },
  { value: "fill_blank", label: "填空题" },
  { value: "short_answer", label: "简答题" },
] as const;
export type QuestionTypeValue = (typeof QUESTION_TYPE_OPTIONS)[number]["value"];

export const QUESTION_SUBJECT_OPTIONS = [
  { value: "english", label: "英语" },
  { value: "programming", label: "编程" },
  { value: "math", label: "数学" },
  { value: "physics", label: "物理" },
  { value: "chemistry", label: "化学" },
] as const;
export type QuestionSubjectCode = (typeof QUESTION_SUBJECT_OPTIONS)[number]["value"];

export const QUESTION_DIFFICULTY_OPTIONS = [
  { value: "L1", label: "L1 入门" },
  { value: "L2", label: "L2 基础" },
  { value: "L3", label: "L3 进阶" },
  { value: "L4", label: "L4 高级" },
  { value: "L5", label: "L5 专家" },
] as const;
export type QuestionDifficultyCode = (typeof QUESTION_DIFFICULTY_OPTIONS)[number]["value"];

/* ============================================================
 * 显示辅助（纯函数）
 * ============================================================ */
export function questionTypeLabel(code: string): string {
  return QUESTION_TYPE_OPTIONS.find((t) => t.value === code)?.label ?? code;
}

export function questionSubjectLabel(code: string): string {
  return QUESTION_SUBJECT_OPTIONS.find((s) => s.value === code)?.label ?? code;
}

export function questionDifficultyLabel(code: string): string {
  return QUESTION_DIFFICULTY_OPTIONS.find((d) => d.value === code)?.label ?? code;
}

/**
 * 判断题答案映射（前端展示层约定：true_false 的 correct_answer 存 "对"/"错"）
 */
export const TRUE_FALSE_ANSWERS = [
  { value: "对", label: "正确" },
  { value: "错", label: "错误" },
] as const;

/**
 * 生成单选题/多选题选项初始集合（label 用 A/B/C/D...）
 */
export function buildOptionLabels(count: number): string[] {
  const n = Math.max(2, Math.min(count, 26));
  return Array.from({ length: n }, (_, i) => String.fromCharCode(65 + i));
}
