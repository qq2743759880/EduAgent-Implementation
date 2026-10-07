/**
 * 管理端题库 · contract④ question 域（task58 新增，契约权威 = .opencode/handoffs/task13-contract.md）
 *  - 两级管理：question_bank（题库 CRUD，bank_code 唯一）→ question（题目，question_code 唯一 per bank）
 *  - 端点（前缀 /api/admin/questions）：
 *      题型  GET /types
 *      题库  GET /banks（分页+关键词）· POST /banks · PATCH /banks/{id} · DELETE /banks/{id}（yn 软删）
 *      题目  GET /banks/{bank_id}/questions（分页+题型+keyword LIKE stem/analysis_text）
 *            POST /questions · PATCH /questions/{id} · DELETE /questions/{id}
 *      导入  POST /import-preview?bank_id=N（逐行校验不落库）· POST /import-execute?bank_id=N（幂等）
 *  - 错误码：40921 题库编码重复 / 40922 题目编码重复（唯一约束冲突段）
 *  - 标签废除：不再维护 admin_question_tag → 知识点改为 stem + analysis_text LIKE 全文检索
 *  - 错误契约（R-7）：写操作失败一律抛 ApiError，由 useMutation onError → toast / 行内提示
 */
import { adminDelete, adminGet, adminPatch, adminPost, type ApiError } from "@/lib/api/admin";
import type { AdminPage, AdminPageParams } from "@/lib/admin-api-types";

/* ============================================================
 * 类型（对齐 contract④，字段 snake_case）
 * ============================================================ */

/** 题型维表 dim_question_type（只读） */
export interface QuestionTypeOption {
  id: number;
  type_code: string;
  type_name: string;
  objective_flag: number;
}

/** 题库 question_bank（yn=1 有效 / 0 软删） */
export interface QuestionBank {
  id: number;
  institution_id: number;
  category_id?: number | null;
  category_name?: string | null;
  bank_code: string;
  bank_name: string;
  description?: string | null;
  question_count?: number | null;
  yn: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface QuestionBankFormInput {
  institution_id: number;
  bank_code: string;
  bank_name: string;
  category_id?: number | null;
  description?: string | null;
}

/** 题目 question（摘录列表行所需字段） */
export interface QuestionListItem {
  id: number;
  bank_id: number;
  question_code: string;
  question_type_id: number;
  question_type_code?: string | null;
  question_type_name?: string | null;
  stem: string;
  objective_flag: number | boolean;
  yn: number;
  created_at?: string | null;
  updated_at?: string | null;
}

/** 批量导入 · 单行（与 import-preview/execute 请求体 items 对齐） */
export interface ImportItemInput {
  question_code: string;
  question_type_id?: number | null;
  stem: string;
  answer_text: string;
  options_json?: Array<{ label: string; content: string }> | null;
  analysis_text?: string | null;
}

/** 批量导入 · 预览响应（import-preview，逐行校验不落库） */
export interface ImportPreviewRow {
  row_index: number;
  question_code?: string | null;
  valid: boolean;
  errors: string[];
}
export interface ImportPreviewResult {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  rows: ImportPreviewRow[];
  message: string;
}

/** 批量导入 · 执行响应（import-execute，幂等：重复 question_code 跳过） */
export interface ImportExecuteResult {
  total: number;
  imported: number;
  skipped: number;
  failed: number;
  messages: string[];
}

/** 题目详情（GET /questions/{id}，契约④ QuestionResponseAdmin，task59 编辑页） */
export interface QuestionDetail {
  id: number;
  bank_id: number;
  question_code: string;
  question_type_id: number;
  stem: string;
  options_json?: Array<{ key: string; text: string }> | null;
  answer_text: string;
  /** ★ 解析（task59 必修展示/编辑） */
  analysis_text?: string | null;
  yn: number;
  created_at?: string | null;
  updated_at?: string | null;
}

/** 更新题目入参（PATCH /questions/{id}，契约④ QuestionAdminUpdate；objective_flag 无此字段，不提交） */
export interface QuestionUpdateInput {
  question_type_id?: number;
  stem?: string;
  options_json?: Array<{ key: string; text: string }> | null;
  answer_text?: string;
  analysis_text?: string | null;
}

/* ============================================================
 * 题型
 * ============================================================ */
export async function listQuestionTypes(): Promise<QuestionTypeOption[]> {
  const resp = await adminGet<{ items: QuestionTypeOption[]; total: number }>("/api/admin/questions/types");
  return resp.items ?? [];
}

/* ============================================================
 * 题库 CRUD
 * ============================================================ */
export interface ListBanksParams extends AdminPageParams {
  keyword?: string;
  category_id?: number;
}

export async function listBanks(params: ListBanksParams = {}): Promise<AdminPage<QuestionBank>> {
  const query: Record<string, unknown> = { page: params.page ?? 1, page_size: params.page_size ?? 10 };
  if (params.keyword?.trim()) query.keyword = params.keyword.trim();
  if (typeof params.category_id === "number") query.category_id = params.category_id;
  if (typeof params.yn === "number") query.yn = params.yn;
  return adminGet<AdminPage<QuestionBank>>("/api/admin/questions/banks", query);
}

export async function createBank(input: QuestionBankFormInput): Promise<{ id: number }> {
  return adminPost<{ id: number }>("/api/admin/questions/banks", input);
}

export async function updateBank(bankId: number, input: Partial<QuestionBankFormInput>): Promise<{ updated: boolean; id: number }> {
  return adminPatch<{ updated: boolean; id: number }>(`/api/admin/questions/banks/${bankId}`, input);
}

export async function deleteBank(bankId: number): Promise<{ deleted: boolean; id: number }> {
  return adminDelete<{ deleted: boolean; id: number }>(`/api/admin/questions/banks/${bankId}`);
}

/* ============================================================
 * 题目（按题库）
 * ============================================================ */
export interface ListBankQuestionsParams extends AdminPageParams {
  question_type_id?: number;
  objective_flag?: number;
  /** 全文检索：LIKE stem + analysis_text、题目编码（替代已废除的标签筛选） */
  keyword?: string;
}

export async function listBankQuestions(
  bankId: number,
  params: ListBankQuestionsParams = {},
): Promise<AdminPage<QuestionListItem>> {
  const query: Record<string, unknown> = { page: params.page ?? 1, page_size: params.page_size ?? 10 };
  if (params.keyword?.trim()) query.keyword = params.keyword.trim();
  if (typeof params.question_type_id === "number") query.question_type_id = params.question_type_id;
  if (typeof params.objective_flag === "number") query.objective_flag = params.objective_flag;
  if (typeof params.yn === "number") query.yn = params.yn;
  return adminGet<AdminPage<QuestionListItem>>(`/api/admin/questions/banks/${bankId}/questions`, query);
}

export async function deleteQuestion(questionId: number): Promise<{ deleted: boolean; id: number }> {
  return adminDelete<{ deleted: boolean; id: number }>(`/api/admin/questions/questions/${questionId}`);
}

/** 题目详情（task59 编辑页回填，含 analysis_text） */
export async function getQuestion(questionId: number): Promise<QuestionDetail> {
  return adminGet<QuestionDetail>(`/api/admin/questions/questions/${questionId}`);
}

/** 更新题目（task59 保存；analysis_text 后端 min_length 兜底 → 422） */
export async function updateQuestion(
  questionId: number,
  input: QuestionUpdateInput,
): Promise<{ updated: boolean; id: number }> {
  return adminPatch<{ updated: boolean; id: number }>(`/api/admin/questions/questions/${questionId}`, input);
}

/** 题库详情（task59 面包屑展示 bank_name） */
export async function getBank(bankId: number): Promise<QuestionBank> {
  return adminGet<QuestionBank>(`/api/admin/questions/banks/${bankId}`);
}

/* ============================================================
 * 批量导入（preview → execute）
 * ============================================================ */
export async function importPreview(bankId: number, items: ImportItemInput[]): Promise<ImportPreviewResult> {
  return adminPost<ImportPreviewResult>(`/api/admin/questions/import-preview?bank_id=${bankId}`, { items });
}

export async function importExecute(bankId: number, items: ImportItemInput[]): Promise<ImportExecuteResult> {
  return adminPost<ImportExecuteResult>(`/api/admin/questions/import-execute?bank_id=${bankId}`, { items });
}

/* ============================================================
 * 显示辅助 / 错误映射（纯函数）
 * ============================================================ */

/** contract④ 唯一约束冲突码 → 提示文案 */
export function bankErrorHint(err: unknown): { code: number; message: string } | null {
  if (err && typeof err === "object" && "code" in err && err.code === 40921) {
    return { code: 40921, message: "题库编码已存在（40921，institution_id + bank_code 唯一）" };
  }
  if (err && typeof err === "object" && "code" in err && err.code === 40922) {
    return { code: 40922, message: "题目编码已存在（40922，bank_id + question_code 唯一）" };
  }
  return null;
}

/**
 * 归一抛错对象 → {code,message,detail}（供行内错误分支读取错误码，如 40921/40922）。
 * 返回 null 表示无法识别（对应调用方走全局 toast，R-7）。
 */
export function toAdminApiError(err: unknown): { status: number; code: number | string; message: string; detail?: unknown } | null {
  if (err && typeof err === "object") {
    const code = "code" in err ? (err as { code?: number | string }).code : undefined;
    const message = "message" in err ? String((err as { message?: string }).message ?? "") : "";
    const status = "status" in err ? Number((err as { status?: number }).status ?? 0) : 0;
    const detail = "detail" in err ? (err as { detail?: unknown }).detail : undefined;
    if (code !== undefined || message) return { status, code: code ?? 0, message, detail };
  }
  return null;
}

export function typeNameOf(t: QuestionTypeOption | undefined): string {
  return t?.type_name ?? t?.type_code ?? "—";
}

/** 把 CSV 行内的题型列（可能为名称或数字 id）解析为 type_id；解析失败返回 null（预览会标失败行） */
export function resolveTypeId(raw: string, types: QuestionTypeOption[]): number | null {
  const t = raw.trim();
  if (!t) return null;
  if (/^\d+$/.test(t)) return Number(t);
  const hit = types.find((x) => x.type_name === t || x.type_code === t);
  return hit ? hit.id : null;
}

export type { ApiError };