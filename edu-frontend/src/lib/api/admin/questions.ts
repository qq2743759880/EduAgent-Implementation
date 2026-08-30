/**
 * 管理端题库 API（task03，G3 题库管理）
 *
 * 契约来源（L1：以 edu-agent 后端代码为准，design-guide §4.4 仅是摘要）：
 *  - app/admin/question_admin/router.py + schemas.py（P7 管理端题库管理）
 *
 * ⚠️ 与 design-guide 摘要的关键差异（后端代码为权威）：
 *  - 题型枚举是 single_choice / multi_choice / true_false / fill_blank / short_answer
 *    （设计指南写的 single/multi/judge/fill/short 是占位摘要，直接提交会 422）
 *  - options_json 是 [{label, content}] 数组（非 {A:"..."} 对象）
 *  - 批量导入 POST /batch-import 的 body 是 list[dict]（非包裹对象）
 *  - 组卷 POST /papers/compose 的 body 是 {spec:{...}, paper_code, paper_title, expected_question_count}
 *
 * 错误契约（R-7）：所有写操作失败一律向上抛 ApiError，由 useMutation onError → toast。
 */
import { adminDelete, adminGet, adminPatch, adminPost } from "@/lib/api/admin";
import type { AdminPage, AdminPageParams } from "@/lib/admin-api-types";

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

export interface QuestionOption {
  label: string;
  content: string;
}

export interface QuestionAdminItem {
  id: number;
  question_code: string;
  subject_code: string;
  question_type: string;
  difficulty_level: string;
  stem_preview: string;
  default_score: number;
  yn: number;
  created_at: string;
  updated_at: string;
  tags: QuestionTag[];
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

export interface QuestionBatchImportResult {
  total: number;
  imported: number;
  skipped: number;
  failed: number;
  messages: string[];
}

export interface PaperComposeResult {
  draft_paper_id: number;
  paper_code: string;
  paper_title: string;
  selected_count: number;
  total_score: number;
  message: string;
  items: Array<{ question_id: number; sort_no: number; score: number }>;
}

export interface PaperComposeInput {
  spec: {
    subject_code: string;
    total_score: number;
    duration_minutes: number;
    pass_score: number;
    difficulty_level?: string | null;
    tag_ids: number[];
    per_question_score: number;
  };
  paper_code: string;
  paper_title: string;
  expected_question_count: number;
}

/* ============================================================
 * 标签
 * ============================================================ */
export async function listQuestionTags(params: {
  tag_type?: string;
  subject_code?: string;
} = {}): Promise<QuestionTag[]> {
  const query: Record<string, unknown> = {};
  if (params.tag_type) query.tag_type = params.tag_type;
  if (params.subject_code) query.subject_code = params.subject_code;
  return adminGet<QuestionTag[]>("/api/admin/questions/tags", query);
}

export async function createQuestionTag(input: {
  tag_type: string;
  tag_code: string;
  tag_name: string;
  subject_code?: string | null;
  description?: string | null;
  sort_no?: number;
}): Promise<{ id: number; tag_code: string }> {
  return adminPost<{ id: number; tag_code: string }>("/api/admin/questions/tags", input);
}

export async function deleteQuestionTag(tagId: number): Promise<{ deleted: boolean; id: number }> {
  return adminDelete<{ deleted: boolean; id: number }>(`/api/admin/questions/tags/${tagId}`);
}

/* ============================================================
 * 题目
 * ============================================================ */
export interface ListQuestionsParams extends AdminPageParams {
  subject_code?: string;
  question_type?: string;
  difficulty_level?: string;
  tag_id?: number;
}

export async function listQuestions(
  params: ListQuestionsParams = {},
): Promise<AdminPage<QuestionAdminItem>> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };
  if (params.subject_code) query.subject_code = params.subject_code;
  if (params.question_type) query.question_type = params.question_type;
  if (params.difficulty_level) query.difficulty_level = params.difficulty_level;
  if (params.keyword?.trim()) query.keyword = params.keyword.trim();
  if (typeof params.tag_id === "number") query.tag_id = params.tag_id;
  if (typeof params.yn === "number") query.yn = params.yn;
  return adminGet<AdminPage<QuestionAdminItem>>("/api/admin/questions", query);
}

export async function getQuestion(questionId: number): Promise<QuestionAdminDetail> {
  return adminGet<QuestionAdminDetail>(`/api/admin/questions/${questionId}`);
}

export async function createQuestion(input: QuestionCreateInput): Promise<{ id: number }> {
  return adminPost<{ id: number }>("/api/admin/questions", input);
}

export async function updateQuestion(
  questionId: number,
  input: Partial<QuestionCreateInput>,
): Promise<{ updated: boolean; id: number }> {
  return adminPatch<{ updated: boolean; id: number }>(`/api/admin/questions/${questionId}`, input);
}

export async function deleteQuestion(questionId: number): Promise<{ deleted: boolean; id: number }> {
  return adminDelete<{ deleted: boolean; id: number }>(`/api/admin/questions/${questionId}`);
}

/* ============================================================
 * 批量导入 / 组卷
 * ============================================================ */
/** 批量导入：body 为 list[dict]（后端契约，非包裹对象） */
export async function batchImportQuestions(items: QuestionCreateInput[]): Promise<QuestionBatchImportResult> {
  return adminPost<QuestionBatchImportResult>("/api/admin/questions/batch-import", items);
}

export async function composePaper(input: PaperComposeInput): Promise<PaperComposeResult> {
  return adminPost<PaperComposeResult>("/api/admin/questions/papers/compose", input);
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
