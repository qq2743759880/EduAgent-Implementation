/**
 * 管理端课程 API（task03 → task56 → task57 重构）
 *
 * 契约来源（L1：以 edu-agent 后端代码为权威，task12-contract.md 契约③）：
 *  - app/domains/course_admin/router.py + schemas.py（四级 CRUD + 视频分片 + 转码）
 *
 * task57 契约对齐要点（勿沿用旧契约）：
 *  - 四级归属：Module.cohort_id（非 series_id）；Session.series_cohort_course_id（模块物理 ID）；Cohort 创建必填 institution_id + head_teacher_id。
 *  - 列表端点返回「裸数组」（router `ok(data=[...])`），非 {items, page_meta}。
 *  - series 详情返回单个 SeriesResponseAdmin（无 subject_code / level_code / target_hours）。
 *  - 视频四段：init-chunked / finalize-chunked / bind-session 为 POST（参数走 query string）；
 *    transcode-status 轮询 GET /videos/{video_id}/transcode-status。
 *  - 转码枚举 transcode_status ∈ pending|in_progress|completed|failed；review_status ∈ pending|approved|rejected。
 *  - 章节（session_video_chapter，含 start_second/end_second）：schema 已冻结但 router 无 CRUD 端点 → 契约缺口，
 *    前端做 UI 脚手架（disabled 占位）实披露，不做 MOCK。
 *  - 唯一约束错误码 40901~40907：gray 分支文案见 `uniqueConflictTip`。
 *
 * 错误契约（R-7）：所有写操作失败一律向上抛 ApiError，由调用方 onError → toast + console.error。
 */
import { http, ApiError } from "@/lib/api-client";
import type { AdminPageParams } from "@/lib/admin-api-types";
import { adminDelete, adminGet, adminPatch, adminPost } from "@/lib/api/admin";

/* ============================================================
 * 枚举（与后端 curriculum.schemas 对齐；保留 subject/level 供用户端 MeHeader 复用）
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
  { value: "off_sale", label: "已下架" },
] as const;
export type SaleStatusCode = (typeof SALE_STATUS_OPTIONS)[number]["value"];

export const DELIVERY_MODE_OPTIONS = [
  { value: "online_live", label: "直播" },
  { value: "online_recorded", label: "录播" },
  { value: "offline_face_to_face", label: "面授" },
] as const;
export type DeliveryModeCode = (typeof DELIVERY_MODE_OPTIONS)[number]["value"];

export const TECHING_STATUS_OPTIONS = [
  { value: "scheduled", label: "未开始" },
  { value: "in_progress", label: "进行中" },
  { value: "completed", label: "已完成" },
  { value: "cancelled", label: "已取消" },
] as const;
export type TeachingStatusCode = (typeof TECHING_STATUS_OPTIONS)[number]["value"];
/** 历史命名保留（用户端/历史测试引用） */
export const TEACHING_STATUS_OPTIONS = TECHING_STATUS_OPTIONS;

export const TRANSCode = ["pending", "in_progress", "completed", "failed"] as const;
/** 视频转码状态（session_video.transcode_status） */
export type TranscodeStatusCode = (typeof TRANSCode)[number];

export const REVIEW_STATUS_OPTIONS = [
  { value: "pending", label: "待审核" },
  { value: "approved", label: "审核通过" },
  { value: "rejected", label: "已驳回" },
] as const;
export type ReviewStatusCode = (typeof REVIEW_STATUS_OPTIONS)[number]["value"];

export const SERIES_SORT_OPTIONS = [
  { value: "default", label: "默认排序" },
  { value: "newest", label: "最新创建" },
  { value: "name_asc", label: "名称升序" },
  { value: "name_desc", label: "名称降序" },
] as const;
export type SeriesSortCode = (typeof SERIES_SORT_OPTIONS)[number]["value"];

/* 唯一约束错误码 → 中文文案（契约③：40901~40907 保持稳定字符串） */
export const UNIQUE_CONFLICT_TIPS: Record<number, string> = {
  40901: "系列编码已存在（institution + series_code 冲突）",
  40902: "班次编码已存在（institution + cohort_code 冲突）",
  40903: "模块阶段号已存在（cohort + stage_no 冲突）",
  40904: "课次编号已存在（module + session_no 冲突）",
  40905: "资源编码已存在（session + asset_code 冲突）",
  40906: "视频编码已存在（asset + video_code 冲突）",
  40907: "章节号已存在（video + chapter_no 冲突）",
};

/* ============================================================
 * 类型（对齐后端 domains.course_admin 各 ResponseAdmin）
 * ============================================================ */

/** SeriesResponseAdmin（series 列表项 / 详情 / 创建 / 更新共用） */
export interface AdminSeries {
  id: number;
  institution_id: number;
  delivery_mode: DeliveryModeCode;
  series_code: string;
  series_name: string;
  description?: string | null;
  cover_url?: string | null;
  target_learner_identity_codes?: string[];
  target_learning_goal_codes?: string[];
  target_grade_codes?: string[];
  sale_status: SaleStatusCode;
  created_by: number;
  created_at: string;
  updated_at: string;
}

/** CohortResponseAdmin */
export interface AdminCohort {
  id: number;
  institution_id: number;
  series_id: number;
  campus_id?: number | null;
  head_teacher_id: number;
  cohort_code: string;
  cohort_name: string;
  sale_price: number;
  max_student_count: number;
  current_student_count: number;
  yn: number;
  start_date?: string | null;
  end_date?: string | null;
  created_at: string;
  updated_at: string;
}

/** ModuleResponseAdmin（模块 = series_cohort_course，归属 cohort_id） */
export interface AdminModule {
  id: number;
  cohort_id: number;
  module_code: string;
  module_name: string;
  description?: string | null;
  lesson_count: number;
  total_hours: number;
  stage_no: number;
  start_date?: string | null;
  end_date?: string | null;
  created_at: string;
  updated_at: string;
}

/** SessionResponseAdmin（课次 = series_cohort_session，归属 series_cohort_course_id） */
export interface AdminSession {
  id: number;
  series_cohort_course_id: number;
  room_id?: number | null;
  session_no: number;
  session_title: string;
  teaching_status: TeachingStatusCode;
  checkin_required: number;
  teaching_date?: string | null;
  start_time?: string | null;
  end_time?: string | null;
  created_at: string;
  updated_at: string;
}

/** 分片上传 init POST /videos/init-chunked → ChunkedUploadInitResponse */
export interface ChunkedUploadInitResponse {
  upload_id: string;
  chunk_size: number;
  upload_urls: string[];
  strategy: "chunked" | "local_fallback" | string;
}

/** 分片上传 finalize POST /videos/finalize-chunked → ChunkedUploadFinalizeResponse */
export interface ChunkedUploadFinalizeResponse {
  upload_id: string;
  asset_id: number;
  video_id: number;
  transcode_status: TranscodeStatusCode;
}

/** 绑定 POST /videos/bind-session（service 返回 bound 语义） */
export interface BindVideoResponse {
  bound: boolean;
  video_id?: number;
  session_id?: number;
  [key: string]: unknown;
}

/** 转码状态 GET /videos/{video_id}/transcode-status → TranscodeStatusResponse */
export interface TranscodeStatus {
  video_id: number;
  transcode_status: TranscodeStatusCode;
  review_status: ReviewStatusCode;
}

/** 章节（session_video_chapter；schema 冻结，路由未注册 → 前端仅占位 UI） */
export interface AdminChapter {
  id: number;
  video_id: number;
  chapter_no: number;
  chapter_title: string;
  start_second: number;
  end_second: number;
  created_at: string;
  updated_at: string;
}

/* task56 保留（课程总览列表使用） */
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

export interface SeriesCreateInput {
  institution_id: number;
  delivery_mode: DeliveryModeCode;
  series_code: string;
  series_name: string;
  description?: string | null;
  cover_url?: string | null;
  target_learner_identity_codes?: string[];
  target_learning_goal_codes?: string[];
  target_grade_codes?: string[];
  sale_status?: SaleStatusCode;
}

/* 请求体（Cohort/Module/Session，对齐 CreateAdmin schema） */
export interface CohortCreateInput {
  institution_id: number;
  series_id: number;
  campus_id?: number | null;
  head_teacher_id: number;
  cohort_code: string;
  cohort_name: string;
  sale_price: number;
  max_student_count: number;
  current_student_count?: number;
  start_date?: string | null;
  end_date?: string | null;
}
export type CohortUpdateInput = Partial<Pick<CohortCreateInput, "head_teacher_id" | "cohort_name" | "sale_price" | "max_student_count" | "start_date" | "end_date">>;

export interface ModuleCreateInput {
  cohort_id: number;
  module_code: string;
  module_name: string;
  description?: string | null;
  lesson_count: number;
  total_hours: number;
  stage_no: number;
  start_date?: string | null;
  end_date?: string | null;
}
export type ModuleUpdateInput = Partial<Pick<ModuleCreateInput, "module_name" | "description" | "lesson_count" | "total_hours" | "stage_no" | "start_date" | "end_date">>;

export interface SessionCreateInput {
  series_cohort_course_id: number;
  room_id?: number | null;
  session_no: number;
  session_title: string;
  teaching_status?: TeachingStatusCode;
  checkin_required?: number;
  teaching_date?: string | null;
  start_time?: string | null;
  end_time?: string | null;
}
export type SessionUpdateInput = Partial<Pick<SessionCreateInput, "room_id" | "session_title" | "teaching_status" | "checkin_required" | "teaching_date" | "start_time" | "end_time">>;

/* task56 保留（课程总览列表 / SeriesForm） */
export interface AdminSeriesListItem {
  id: number;
  institution_id: number;
  delivery_mode: DeliveryModeCode;
  series_code: string;
  series_name: string;
  description?: string | null;
  cover_url?: string | null;
  sale_status: SaleStatusCode;
  created_by: number;
  created_at: string;
  updated_at: string;
}

export interface AdminSeriesListResponse {
  items: AdminSeriesListItem[];
  page_meta: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
    has_more: boolean;
  };
}

export interface ListAdminSeriesParams extends AdminPageParams {
  delivery_mode?: DeliveryModeCode;
  sale_status?: SaleStatusCode;
  sort?: SeriesSortCode;
  institution_id?: number;
}

/* ============================================================
 * 系列 Series（task56 已实现，保留）
 * ============================================================ */
export async function listAdminSeries(
  params: ListAdminSeriesParams = {},
): Promise<AdminSeriesListResponse> {
  const query: Record<string, unknown> = { page: params.page ?? 1, page_size: params.page_size ?? 20 };
  if (params.delivery_mode) query.delivery_mode = params.delivery_mode;
  if (params.sale_status) query.sale_status = params.sale_status;
  if (params.sort) query.sort = params.sort;
  if (params.institution_id != null) query.institution_id = params.institution_id;
  if (params.keyword?.trim()) query.keyword = params.keyword.trim();
  return adminGet<AdminSeriesListResponse>("/api/admin/courses/series", query);
}

/** 系列详情：GET /series/{id} 返回单个 SeriesResponseAdmin（无旧 subject_code/level_code/target_hours） */
export async function getAdminSeriesDetail(seriesId: number): Promise<AdminSeries> {
  return adminGet<AdminSeries>(`/api/admin/courses/series/${seriesId}`);
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

/** 软删系列：series 无 yn 列 → DELETE 置 sale_status='off_sale' */
export async function deleteAdminSeries(seriesId: number): Promise<{ deleted: boolean; id: number }> {
  return adminDelete<{ deleted: boolean; id: number }>(`/api/admin/courses/series/${seriesId}`);
}

/* ============================================================
 * 班次 Cohort（task57）
 * ============================================================ */

/** 按系列列表：GET /series/{series_id}/cohorts → 裸数组 */
export async function listAdminCohorts(seriesId: number): Promise<AdminCohort[]> {
  return adminGet<AdminCohort[]>(`/api/admin/courses/series/${seriesId}/cohorts`);
}

export async function createAdminCohort(input: CohortCreateInput): Promise<AdminCohort> {
  return adminPost<AdminCohort>("/api/admin/courses/cohorts", input);
}

export async function updateAdminCohort(
  cohortId: number,
  input: CohortUpdateInput,
): Promise<AdminCohort> {
  return adminPatch<AdminCohort>(`/api/admin/courses/cohorts/${cohortId}`, input);
}

export async function deleteAdminCohort(cohortId: number): Promise<void> {
  return adminDelete<void>(`/api/admin/courses/cohorts/${cohortId}`);
}

/* ============================================================
 * 模块 Module（归属 cohort_id，task57）
 * ============================================================ */

/** 按班次列表：GET /cohorts/{cohort_id}/modules → 裸数组 */
export async function listAdminModules(cohortId: number): Promise<AdminModule[]> {
  return adminGet<AdminModule[]>(`/api/admin/courses/cohorts/${cohortId}/modules`);
}

export async function createAdminModule(input: ModuleCreateInput): Promise<AdminModule> {
  return adminPost<AdminModule>("/api/admin/courses/modules", input);
}

export async function updateAdminModule(
  moduleId: number,
  input: ModuleUpdateInput,
): Promise<AdminModule> {
  return adminPatch<AdminModule>(`/api/admin/courses/modules/${moduleId}`, input);
}

export async function deleteAdminModule(moduleId: number): Promise<void> {
  return adminDelete<void>(`/api/admin/courses/modules/${moduleId}`);
}

/* ============================================================
 * 课次 Session（归属 series_cohort_course_id，task57）
 * ============================================================ */

/** 按模块列表：GET /modules/{module_id}/sessions → 裸数组 */
export async function listAdminSessions(moduleId: number): Promise<AdminSession[]> {
  return adminGet<AdminSession[]>(`/api/admin/courses/modules/${moduleId}/sessions`);
}

export async function createAdminSession(input: SessionCreateInput): Promise<AdminSession> {
  return adminPost<AdminSession>("/api/admin/courses/sessions", input);
}

export async function updateAdminSession(
  sessionId: number,
  input: SessionUpdateInput,
): Promise<AdminSession> {
  return adminPatch<AdminSession>(`/api/admin/courses/sessions/${sessionId}`, input);
}

export async function deleteAdminSession(sessionId: number): Promise<void> {
  return adminDelete<void>(`/api/admin/courses/sessions/${sessionId}`);
}

/* ============================================================
 * 视频分片上传四段（task57；init/finalize/bind 为 POST + query，transcode 为 GET）
 * ============================================================ */
export interface VideoUploadMeta {
  file_name: string;
  file_size: number;
  chunk_count: number;
}

export async function initChunkedUpload(
  sessionId: number,
  meta: VideoUploadMeta,
): Promise<ChunkedUploadInitResponse> {
  return adminPost<ChunkedUploadInitResponse>("/api/admin/courses/videos/init-chunked", undefined, {
    params: {
      session_id: sessionId,
      file_name: meta.file_name,
      file_size: meta.file_size,
      chunk_count: meta.chunk_count,
    },
  });
}

export async function finalizeChunkedUpload(
  upload_id: string,
): Promise<ChunkedUploadFinalizeResponse> {
  return adminPost<ChunkedUploadFinalizeResponse>("/api/admin/courses/videos/finalize-chunked", undefined, {
    params: { upload_id },
  });
}

export async function bindSessionVideo(
  sessionId: number,
  videoId: number,
  sortNo: number = 0,
): Promise<BindVideoResponse> {
  return adminPost<BindVideoResponse>("/api/admin/courses/videos/bind-session", undefined, {
    params: { session_id: sessionId, video_id: videoId, sort_no: sortNo },
  });
}

export async function getTranscodeStatus(videoId: number): Promise<TranscodeStatus> {
  return http.get<TranscodeStatus>(`/api/admin/courses/videos/${videoId}/transcode-status`);
}

/** 课件上传指引（保留：resource 四入口中「课件」接入 P1 管道） */
export interface MaterialRedirectInfo {
  redirect_endpoint: string;
  method: string;
  auth_header_required: boolean;
  supported_content_types: string[];
  tip: string;
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
export function deliveryModeLabel(code: string): string {
  return DELIVERY_MODE_OPTIONS.find((d) => d.value === code)?.label ?? code;
}
export function teachingStatusLabel(code: string): string {
  return TECHING_STATUS_OPTIONS.find((t) => t.value === code)?.label ?? code;
}
export function reviewStatusLabel(code: string): string {
  return REVIEW_STATUS_OPTIONS.find((r) => r.value === code)?.label ?? code;
}
export function transcodeStatusLabel(code: string): string {
  switch (code) {
    case "pending": return "待转码";
    case "in_progress": return "转码中";
    case "completed": return "已完成";
    case "failed": return "失败";
    default: return code;
  }
}
/**
 * 转码徽章 tone（task57）：pending→warning / in_progress→primary / completed→success / failed→destructive。
 * 仅返回语义 token class（禁 slate/arbitrary），供 Badge 复用。
 */
export function transcodeBadgeTone(code: string): string {
  switch (code) {
    case "pending": return "border-transparent bg-warning/10 text-warning";
    case "in_progress": return "border-transparent bg-primary/10 text-primary";
    case "completed": return "border-transparent bg-candy-green-soft text-candy-green";
    case "failed": return "border-transparent bg-destructive/10 text-destructive";
    default: return "border-transparent bg-muted text-muted-foreground";
  }
}
export function reviewBadgeTone(code: string): string {
  switch (code) {
    case "approved": return "border-transparent bg-candy-green-soft text-candy-green";
    case "rejected": return "border-transparent bg-destructive/10 text-destructive";
    default: return "border-transparent bg-warning/10 text-warning";
  }
}

/** 唯一约束冲突 → 前端分支提示（onError 中按 ApiError.code 命中文案；非 409 返回默认消息） */
export function uniqueConflictTip(err: unknown, fallback: string): string {
  if (err instanceof ApiError && typeof err.code === "number") {
    const tip = UNIQUE_CONFLICT_TIPS[err.code];
    if (tip) return tip;
    if (err.code === 40400) return "目标资源不存在或已被删除";
  }
  return fallback;
}

/** 序列化中文日期为后端 date 要求（YYYY-MM-DD）；空值返回 undefined */
export function toDateInput(value?: string | null): string {
  return value ? value.slice(0, 10) : "";
}
/** 由起止秒生成 mm:ss 标签（供章节 GUI） */
export function fmtSeconds(totalSeconds: number): string {
  if (isNaN(totalSeconds) || totalSeconds < 0) totalSeconds = 0;
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}