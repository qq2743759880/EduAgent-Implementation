/**
 * 管理端题库 API（task03，G3 题库管理）
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
 * W-NEXT-FEBE-SCAN-002 断点根因修复（2026-09-18，OpenAPI 实测对账）：
 *  - 真实路由是 /api/admin/questions/questions（题目集合）与
 *    /api/admin/questions/questions/{question_id}（单题）——旧代码写的
 *    /api/admin/questions(/{id}) 后端从未注册（404 断点），已对齐。
 *  - 后端无跨题库"题目总列表"端点：题目列表只能按题库查
 *    GET /api/admin/questions/banks/{bank_id}/questions（见 question-bank.ts listBankQuestions，
 *    /admin/questions 页面在用）。旧的跨库 listQuestions/getQuestion/deleteQuestion
 *    死封装已删除（全仓库 grep 零引用，活引用全部在 question-bank.ts 同名封装）。
 *
 * 错误契约（R-7）：所有写操作失败一律向上抛 ApiError，由 useMutation onError → toast。
 */
import { adminPatch, adminPost } from "@/lib/api/admin";

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
 * 类型（对齐后端 schemas）
 * ============================================================ */
export interface QuestionTag {
  id: number;
  tag_type: string;
  tag_code: string;
  tag_name: string;
  subject_code?: string | null;
  description?: string | null;
  sort_no: number;
  yn: number;
  created_at: string;
  updated_at: string;
}

/** 标签列表（后端已移除 tag 维度，question schema 注释明确"标签逻辑删除→LIKE 查询"；返回空数组避免 404） */
export async function listQuestionTags(_params: {
  tag_type?: string;
  subject_code?: string;
} = {}): Promise<QuestionTag[]> {
  return [];
}

export interface QuestionOption {
  label: string;
  content: string;
}

export interface QuestionAdminDetail {
  id: number;
  question_code: string;
  subject_code: string;
  question_type: string;
  difficulty_level: string;
  stem_html: string;
  analysis_html?: string | null;
  options_json: QuestionOption[];
  correct_answer: string;
  correct_answer_detail?: string | null;
  default_score: number;
  knowledge_point_codes: string[];
  yn: number;
  created_by?: number | null;
  updated_by?: number | null;
  created_at: string;
  updated_at: string;
  tags: QuestionTag[];
}

export interface QuestionCreateInput {
  question_code: string;
  subject_code: string;
  question_type: string;
  difficulty_level: string;
  stem_html: string;
  analysis_html?: string | null;
  options_json: QuestionOption[];
  correct_answer: string;
  correct_answer_detail?: string | null;
  default_score: number;
  knowledge_point_codes: string[];
  tag_ids: number[];
}

/* ============================================================
 * 题目（W-NEXT-FEBE-SCAN-002 对齐 question_admin 真实路由）
 *
 * ⚠️ 遗留 body 契约缺口（如实披露，非本次引入）：QuestionAdminCreate 后端真实
 *    必填是 bank_id/question_type_id/stem/answer_text（app/domains/question_admin/
 *    schemas.py:57），而本文件 QuestionCreateInput 仍是 task03 草稿形状
 *    （question_code/subject_code/tag_ids/...）。二者不匹配 —— 即便路径正确，
 *    旧 payload 也会 422。唯一下游 QuestionForm（task03 legacy 表单）当前未挂载
 *    （全仓库 grep 零 import，活 UI：/admin/questions 页两级管理 + BankImportDialog
 *    批量导入 + QuestionDetailEditor 走 question-bank.ts），故无运行时影响。
 *    后续处置（follow-up）：整体删除 legacy QuestionForm + 本文件死封装，
 *    或按 QuestionAdminCreate 重写 payload —— 需任务单裁决，不在断点修复范围。
 * ============================================================ */
export async function createQuestion(input: QuestionCreateInput): Promise<{ id: number }> {
  return adminPost<{ id: number }>("/api/admin/questions/questions", input);
}

export async function updateQuestion(
  questionId: number,
  input: Partial<QuestionCreateInput>,
): Promise<{ updated: boolean; id: number }> {
  return adminPatch<{ updated: boolean; id: number }>(
    `/api/admin/questions/questions/${questionId}`,
    input,
  );
}

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
