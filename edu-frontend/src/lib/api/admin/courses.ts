/**
 * 管理端课程 API（task03，G3 课程管理）
 *
 * 契约来源（L1：以 edu-agent 后端代码为准，design-guide §4.3 仅是摘要）：
 *  - app/admin/course_admin/router.py + schemas.py（P7 管理端课程管理）
 *  - app/curriculum/schemas.py（Series/Module/Session/Cohort 只读模型）
 *
 * 与用户端 curriculum.ts 的关键差异（勿混用）：
 *  - 管理端系列字段是 series_name（非 series_title）、level_name 必填、target_hours（非 total_hours）
 *  - 视频上传是「占位式」：Init→(前端模拟进度)→Finalize→Bind 四步，转码状态 pending→ready
 *  - 课件上传无真实接口，走 GET /materials/redirect-upload 返回 P1 管道指引（307 语义）
 *
 * 错误契约（R-7）：所有写操作（POST/PATCH/DELETE）失败一律向上抛 ApiError，
 * 由 useMutation onError → toast + console.error 提示，禁止 catch 返回空态冒充成功。
 */
import { adminDelete, adminGet, adminPatch, adminPost } from "@/lib/api/admin";
import type { AdminPage, AdminPageParams } from "@/lib/admin-api-types";

/* ============================================================
 * 枚举（与后端 curriculum.schemas.SubjectCode / LevelCode 对齐）
 * ============================================================ */
export const ADMIN_SUBJECT_OPTIONS = [
  { value: "english", label: "英语" },
  { value: "programming", label: "编程" },
  { value: "math", label: "数学" },
  { value: "physics", label: "物理" },
  { value: "chemistry", label: "化学" },
] as const;
export type AdminSubjectCode = (typeof ADMIN_SUBJECT_OPTIONS)[number]["value"];

export const ADMIN_LEVEL_OPTIONS = [
  { value: "L1", label: "L1 入门" },
  { value: "L2", label: "L2 基础" },
  { value: "L3", label: "L3 进阶" },
  { value: "L4", label: "L4 高级" },
  { value: "L5", label: "L5 专家" },
] as const;
export type AdminLevelCode = (typeof ADMIN_LEVEL_OPTIONS)[number]["value"];

export const SALE_STATUS_OPTIONS = [
  { value: "draft", label: "草稿" },
  { value: "on_sale", label: "在售" },
  { value: "off_sale", label: "下架" },
] as const;
export type SaleStatusCode = (typeof SALE_STATUS_OPTIONS)[number]["value"];

export const TEACHING_STATUS_OPTIONS = [
  { value: "scheduled", label: "未开始" },
  { value: "in_progress", label: "进行中" },
  { value: "completed", label: "已完成" },
  { value: "cancelled", label: "已取消" },
] as const;
export type TeachingStatusCode = (typeof TEACHING_STATUS_OPTIONS)[number]["value"];

/* ============================================================
 * 类型（对齐后端只读模型）
 * ============================================================ */
export interface AdminSeriesItem {
  id: number;
  series_code: string;
  series_name: string;
  subject_code: string;
  level_code: string;
  level_name: string;
  description?: string | null;
  cover_url?: string | null;
  target_hours: number;
  sale_status: SaleStatusCode;
  sort_no: number;
  created_by?: number | null;
  created_at: string;
  updated_at: string;
  cohort_count: number;
  total_session_count: number;
}

export interface AdminCohort {
  id: number;
  series_id: number;
  cohort_code: string;
  cohort_name: string;
  start_date?: string | null;
  end_date?: string | null;
  max_student_count: number;
  current_student_count: number;
  sale_price: number;
  yn: number;
  created_at: string;
  updated_at: string;
}

export interface AdminSession {
  id: number;
  module_id: number;
  session_no: number;
  session_title: string;
  description?: string | null;
  teaching_status: TeachingStatusCode;
  teaching_date?: string | null;
  duration_minutes: number;
  video_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminModule {
  id: number;
  series_id: number;
  module_code: string;
  module_name: string;
  stage_no: number;
  description?: string | null;
  lesson_count: number;
  total_hours: number;
  created_at: string;
  updated_at: string;
  sessions: AdminSession[];
}

export interface AdminSeriesTree {
  series: AdminSeriesItem;
  cohorts: AdminCohort[];
  modules: AdminModule[];
  summary_total_sessions: number;
  summary_total_hours: number;
}

export interface AdminSeriesDetail {
  series: AdminSeriesItem;
  cohorts: AdminCohort[];
  modules: AdminModule[];
}

/* 视频资产（admin_course_video_asset） */
export interface AdminVideoAsset {
  id: number;
  asset_id: string;
  session_id?: number | null;
  asset_title: string;
  origin_file_name: string;
  object_key?: string | null;
  bucket_name?: string | null;
  file_size: number;
  duration_seconds: number;
  transcode_status: "pending" | "ready" | "failed" | string;
  transcode_message?: string | null;
  play_720_url?: string | null;
  play_1080_url?: string | null;
  content_hash?: string | null;
  created_by?: number | null;
  created_at: string;
  updated_at: string;
}

export interface VideoUploadInitResponse {
  asset_id: string;
  upload_type: string;
  upload_url: string;
  form_fields: Record<string, unknown>;
  transcode_status_tip: string;
  expires_at: string;
  bind_session_id?: number | null;
}

export interface MaterialRedirectInfo {
  redirect_endpoint: string;
  method: string;
  auth_header_required: boolean;
  supported_content_types: string[];
  tip: string;
}

/* ============================================================
 * 请求体类型（对齐后端 Create/Update schema，编辑时仅提交非空字段）
 * ============================================================ */
export interface SeriesCreateInput {
  series_code: string;
  series_name: string;
  subject_code: string;
  level_code: string;
  level_name: string;
  description?: string | null;
  cover_url?: string | null;
  target_hours?: number;
  sale_status?: string;
  sort_no?: number;
}

export interface ModuleCreateInput {
  series_id: number;
  module_code: string;
  module_name: string;
  stage_no: number;
  description?: string | null;
  lesson_count?: number;
  total_hours?: number;
}

export interface SessionCreateInput {
  module_id: number;
  session_no: number;
  session_title: string;
  description?: string | null;
  teaching_status?: string;
  teaching_date?: string | null;
  duration_minutes?: number;
  video_url?: string | null;
}

export interface CohortCreateInput {
  series_id: number;
  cohort_code: string;
  cohort_name: string;
  start_date?: string | null;
  end_date?: string | null;
  max_student_count?: number;
  sale_price?: number;
  yn?: number;
}

export interface VideoUploadInitInput {
  origin_file_name: string;
  file_size?: number;
  content_hash?: string | null;
  duration_seconds?: number;
  asset_title?: string | null;
  bind_session_id?: number | null;
}

export interface VideoUploadFinalizeInput {
  asset_id: string;
  object_key?: string | null;
  transcode_error?: string | null;
  play_720_url?: string | null;
  play_1080_url?: string | null;
  final_duration_seconds?: number;
}

/* ============================================================
 * 系列
 * ============================================================ */
export interface ListAdminSeriesParams extends AdminPageParams {
  subject_code?: string;
  level_code?: string;
}

export async function listAdminSeries(
  params: ListAdminSeriesParams = {},
): Promise<AdminPage<AdminSeriesItem>> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };
  if (params.subject_code) query.subject_code = params.subject_code;
  if (params.level_code) query.level_code = params.level_code;
  if (params.keyword?.trim()) query.keyword = params.keyword.trim();
  return adminGet<AdminPage<AdminSeriesItem>>("/api/admin/courses/series", query);
}

export async function getAdminSeriesDetail(seriesId: number): Promise<AdminSeriesDetail> {
  return adminGet<AdminSeriesDetail>(`/api/admin/courses/series/${seriesId}`);
}

export async function getAdminSeriesTree(seriesId: number): Promise<AdminSeriesTree> {
  return adminGet<AdminSeriesTree>(`/api/admin/courses/series/${seriesId}/tree`);
}

export async function createAdminSeries(input: SeriesCreateInput): Promise<{ id: number }> {
  return adminPost<{ id: number }>("/api/admin/courses/series", input);
}

export async function updateAdminSeries(
  seriesId: number,
  input: Partial<SeriesCreateInput>,
): Promise<{ updated: boolean; id: number }> {
  return adminPatch<{ updated: boolean; id: number }>(`/api/admin/courses/series/${seriesId}`, input);
}

/* ============================================================
 * 模块 / 课次 / 班次
 * ============================================================ */
export async function listAdminModules(seriesId?: number): Promise<AdminModule[]> {
  return adminGet<AdminModule[]>("/api/admin/courses/modules", seriesId ? { series_id: seriesId } : undefined);
}

export async function createAdminModule(input: ModuleCreateInput): Promise<{ id: number }> {
  return adminPost<{ id: number }>("/api/admin/courses/modules", input);
}

export async function updateAdminModule(
  moduleId: number,
  input: Partial<ModuleCreateInput>,
): Promise<{ updated: boolean; id: number }> {
  return adminPatch<{ updated: boolean; id: number }>(`/api/admin/courses/modules/${moduleId}`, input);
}

export async function deleteAdminModule(moduleId: number): Promise<{ deleted: boolean; id: number }> {
  return adminDelete<{ deleted: boolean; id: number }>(`/api/admin/courses/modules/${moduleId}`);
}

export async function listAdminSessions(moduleId?: number): Promise<AdminSession[]> {
  return adminGet<AdminSession[]>("/api/admin/courses/sessions", moduleId ? { module_id: moduleId } : undefined);
}

export async function createAdminSession(input: SessionCreateInput): Promise<{ id: number }> {
  return adminPost<{ id: number }>("/api/admin/courses/sessions", input);
}

export async function updateAdminSession(
  sessionId: number,
  input: Partial<SessionCreateInput>,
): Promise<{ updated: boolean; id: number }> {
  return adminPatch<{ updated: boolean; id: number }>(`/api/admin/courses/sessions/${sessionId}`, input);
}

export async function deleteAdminSession(sessionId: number): Promise<{ deleted: boolean; id: number }> {
  return adminDelete<{ deleted: boolean; id: number }>(`/api/admin/courses/sessions/${sessionId}`);
}

export async function listAdminCohorts(seriesId?: number): Promise<AdminCohort[]> {
  return adminGet<AdminCohort[]>("/api/admin/courses/cohorts", seriesId ? { series_id: seriesId } : undefined);
}

export async function createAdminCohort(input: CohortCreateInput): Promise<{ id: number }> {
  return adminPost<{ id: number }>("/api/admin/courses/cohorts", input);
}

export async function updateAdminCohort(
  cohortId: number,
  input: Partial<CohortCreateInput>,
): Promise<{ updated: boolean; id: number }> {
  return adminPatch<{ updated: boolean; id: number }>(`/api/admin/courses/cohorts/${cohortId}`, input);
}

export async function deleteAdminCohort(cohortId: number): Promise<{ deleted: boolean; id: number }> {
  return adminDelete<{ deleted: boolean; id: number }>(`/api/admin/courses/cohorts/${cohortId}`);
}

/* ============================================================
 * 视频三连（Init → Finalize → Bind）+ 列表 + 课件指引
 * ============================================================ */
export async function initVideoUpload(input: VideoUploadInitInput): Promise<VideoUploadInitResponse> {
  return adminPost<VideoUploadInitResponse>("/api/admin/courses/videos/upload/init", input);
}

export async function finalizeVideoUpload(input: VideoUploadFinalizeInput): Promise<AdminVideoAsset> {
  return adminPost<AdminVideoAsset>("/api/admin/courses/videos/upload/finalize", input);
}

export async function bindVideoToSession(assetId: string, sessionId: number): Promise<AdminVideoAsset> {
  return adminPost<AdminVideoAsset>("/api/admin/courses/videos/bind-session", {
    asset_id: assetId,
    session_id: sessionId,
  });
}

export async function listAdminVideoAssets(params: {
  session_id?: number;
  status?: string;
  page?: number;
  page_size?: number;
} = {}): Promise<AdminPage<AdminVideoAsset>> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };
  if (params.session_id != null) query.session_id = params.session_id;
  if (params.status) query.status = params.status;
  return adminGet<AdminPage<AdminVideoAsset>>("/api/admin/courses/videos", query);
}

export async function getMaterialRedirectInfo(): Promise<MaterialRedirectInfo> {
  return adminGet<MaterialRedirectInfo>("/api/admin/courses/materials/redirect-upload");
}

/* ============================================================
 * 显示辅助（纯函数，供页面/测试复用）
 * ============================================================ */
export function subjectLabel(code: string): string {
  return ADMIN_SUBJECT_OPTIONS.find((s) => s.value === code)?.label ?? code;
}

export function levelLabel(code: string): string {
  return ADMIN_LEVEL_OPTIONS.find((l) => l.value === code)?.label ?? code;
}

export function saleStatusLabel(code: string): string {
  return SALE_STATUS_OPTIONS.find((s) => s.value === code)?.label ?? code;
}

export function teachingStatusLabel(code: string): string {
  return TEACHING_STATUS_OPTIONS.find((t) => t.value === code)?.label ?? code;
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
