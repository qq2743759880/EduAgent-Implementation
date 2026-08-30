/**
 * 分级课程 API 封装（task40 对齐契约冻结② edu-agent/app/domains/course/schemas.py）
 *
 * 层级变更（task11 后）：series → cohort（班次）→ module（模块挂班次）→ session（课次挂模块）
 * 旧 /api/curriculum/* 已 307 重定向，前端直连新端点：
 *   - GET /api/series                    → SeriesListData {items, page_meta}
 *   - GET /api/series/{id}               → SeriesDetail
 *   - GET /api/series/{id}/cohorts       → Cohort[]
 *   - GET /api/cohorts/{id}              → CohortDetail {cohort, modules}
 *   - GET /api/cohorts/{id}/modules      → CohortModulesData {cohort_id, modules}
 * 思维导图：GET /api/mindmap/course/{seriesId}（匿名）
 */
import { http } from "@/lib/api-client";

/* =========================================================
 * UI 标签常量
 * =======================================================*/

/**
 * /api/series 分类筛选选项（对齐 dim_course_category 一级分类）。
 * 后端 category Query 为分类名模糊匹配。
 */
export const CATEGORY_OPTIONS = [
  { code: "computer_science", name: "计算机" },
  { code: "mathematics", name: "数学" },
  { code: "exam_prep", name: "考试与升学" },
  { code: "management", name: "管理" },
  { code: "enterprise_training", name: "企业培训" },
  { code: "campus_growth", name: "校园成长" },
] as const;

export type CategoryCode = (typeof CATEGORY_OPTIONS)[number]["code"];

/**
 * 学科/级别标签映射（UI 展示常量）。
 * /api/series 契约② 已无 subject_code/level_code 筛选（改用 category），
 * 此处仅供 progress 域 CourseProgressOut.subject_code/level_code 徽章映射。
 */
export const SUBJECT_OPTIONS = [
  { code: "english", name: "英语", color: "bg-sky-500" },
  { code: "programming", name: "编程", color: "bg-violet-500" },
  { code: "math", name: "数学", color: "bg-emerald-500" },
  { code: "chinese", name: "语文", color: "bg-amber-500" },
  { code: "physics", name: "物理", color: "bg-rose-500" },
] as const;

export type SubjectCode = (typeof SUBJECT_OPTIONS)[number]["code"];

export const LEVEL_OPTIONS = [
  { code: "L1", name: "L1 入门", short: "L1" },
  { code: "L2", name: "L2 基础", short: "L2" },
  { code: "L3", name: "L3 进阶", short: "L3" },
  { code: "L4", name: "L4 高级", short: "L4" },
  { code: "L5", name: "L5 专家", short: "L5" },
] as const;

export type LevelCode = (typeof LEVEL_OPTIONS)[number]["code"];

/* =========================================================
 * 分页元数据（后端 PageMeta）
 * =======================================================*/
export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_more: boolean;
}

/* =========================================================
 * 系列列表（SeriesListItem / SeriesListData）
 * =======================================================*/
export interface SeriesListItem {
  id: number;
  institution_id: number;
  delivery_mode: "online_live" | "online_recorded" | "offline_face_to_face";
  series_code: string;
  series_name: string;
  description: string | null;
  cover_url: string | null;
  target_learner_identity_codes: string[] | null;
  target_learning_goal_codes: string[] | null;
  target_grade_codes: string[] | null;
  sale_status: string;
  min_price: string | null;
  category_names: string[];
  created_at: string;
  updated_at: string;
}

export interface SeriesListData {
  items: SeriesListItem[];
  page_meta: PageMeta;
}

export interface CategoryBrief {
  id: number;
  category_code: string;
  category_name: string;
  category_level: number;
}

export interface SeriesDetail {
  id: number;
  institution_id: number;
  delivery_mode: "online_live" | "online_recorded" | "offline_face_to_face";
  series_code: string;
  series_name: string;
  description: string | null;
  cover_url: string | null;
  target_learner_identity_codes: string[] | null;
  target_learning_goal_codes: string[] | null;
  target_grade_codes: string[] | null;
  sale_status: string;
  min_price: string | null;
  max_price: string | null;
  categories: CategoryBrief[];
  cohort_count: number;
  created_at: string;
  updated_at: string;
}

/* =========================================================
 * 班次 / 模块 / 课次 / 视频（Cohort / Module / Session / SessionVideo）
 * =======================================================*/
export interface Cohort {
  id: number;
  institution_id: number;
  series_id: number;
  campus_id: number | null;
  head_teacher_id: number;
  cohort_code: string;
  cohort_name: string;
  sale_price: string;
  max_student_count: number;
  current_student_count: number;
  yn: number;
  start_date: string;
  end_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface CohortDetail {
  cohort: Cohort;
  modules: Module[];
}

export interface Module {
  id: number;
  cohort_id: number;
  module_code: string;
  module_name: string;
  description: string | null;
  lesson_count: number;
  total_hours: string;
  stage_no: number;
  start_date: string;
  end_date: string;
  created_at: string;
  updated_at: string;
}

export interface SessionVideo {
  id: number;
  asset_id: number;
  video_code: string;
  video_title: string;
  cover_url: string | null;
  duration_seconds: number;
  resolution_label: string | null;
  bitrate_kbps: number;
  transcode_status: string;
  review_status: string;
  file_url: string | null;
}

export interface Session {
  id: number;
  series_cohort_course_id: number;
  room_id: number | null;
  session_no: number;
  session_title: string;
  teaching_status: string;
  checkin_required: number;
  teaching_date: string;
  start_time: string | null;
  end_time: string | null;
  videos: SessionVideo[];
}

export interface ModuleWithSessions extends Module {
  sessions: Session[];
}

export interface CohortModulesData {
  cohort_id: number;
  modules: ModuleWithSessions[];
}

/** /api/series/{id}/cohorts 分页壳（后端返回 {items, page_meta}） */
export interface CohortListData {
  items: Cohort[];
  page_meta: { page: number; page_size: number; total: number; total_pages: number };
}

/* =========================================================
 * 列表查询参数（对齐 GET /api/series Query 签名）
 * =======================================================*/
export type SeriesSort = "default" | "newest" | "price_asc" | "price_desc";

export interface ListSeriesParams {
  category?: string;
  delivery_mode?: "online_live" | "online_recorded" | "offline_face_to_face";
  keyword?: string;
  price_min?: number;
  price_max?: number;
  sort?: SeriesSort;
  page?: number;
  page_size?: number;
}

export function listSeries(params: ListSeriesParams = {}): Promise<SeriesListData> {
  const search = new URLSearchParams();
  if (params.category?.trim()) search.set("category", params.category.trim());
  if (params.delivery_mode) search.set("delivery_mode", params.delivery_mode);
  if (params.keyword?.trim()) search.set("keyword", params.keyword.trim());
  if (typeof params.price_min === "number" && Number.isFinite(params.price_min)) {
    search.set("price_min", String(params.price_min));
  }
  if (typeof params.price_max === "number" && Number.isFinite(params.price_max)) {
    search.set("price_max", String(params.price_max));
  }
  if (params.sort) search.set("sort", params.sort);
  search.set("page", String(params.page ?? 1));
  search.set("page_size", String(params.page_size ?? 12));
  return http.get<SeriesListData>(`/api/series?${search.toString()}`);
}

export function getSeriesDetail(seriesId: number): Promise<SeriesDetail> {
  return http.get<SeriesDetail>(`/api/series/${seriesId}`);
}

export function listSeriesCohorts(seriesId: number): Promise<CohortListData> {
  return http.get<CohortListData>(`/api/series/${seriesId}/cohorts`);
}

export function getCohortDetail(cohortId: number): Promise<CohortDetail> {
  return http.get<CohortDetail>(`/api/cohorts/${cohortId}`);
}

export function listCohortModules(cohortId: number): Promise<CohortModulesData> {
  return http.get<CohortModulesData>(`/api/cohorts/${cohortId}/modules`);
}

/* =========================================================
 * 播放页视图：系列首个在售班次的模块树摊平
 * （LearningPlayClient 消费；URL /learning/[seriesId]/[sessionId] 中
 *   sessionId = series_cohort_session.id）
 * =======================================================*/
export interface SeriesTreeOut {
  title: string;
  series_code: string | null;
  cover_url: string | null;
  cohort_id: number | null;
  modules: Array<{
    module_id: number;
    title: string | null;
    sessions: Array<{
      session_id: number;
      title: string | null;
      duration_seconds: number | null;
      video_url: string | null;
    }>;
  }>;
}

/** 拉系列详情 + 首个在售班次模块树，摊平为播放页形状（无班次时返回空骨架） */
export async function getSeriesTreeFlat(seriesId: number): Promise<SeriesTreeOut> {
  const detail = await getSeriesDetail(seriesId);
  const cohorts = await listSeriesCohorts(seriesId);
  const cohortItems = cohorts.items ?? [];
  const onSale = cohortItems.find((c) => c.yn === 1) ?? cohortItems[0] ?? null;
  const modules = onSale ? (await listCohortModules(onSale.id)).modules : [];
  return {
    title: detail.series_name,
    series_code: detail.series_code,
    cover_url: detail.cover_url,
    cohort_id: onSale?.id ?? null,
    modules: modules.map((m) => ({
      module_id: m.id,
      title: m.module_name,
      sessions: m.sessions.map((s) => ({
        session_id: s.id,
        title: s.session_title,
        duration_seconds: s.videos[0]?.duration_seconds ?? null,
        video_url: s.videos.find((v) => v.file_url)?.file_url ?? null,
      })),
    })),
  };
}

/* =========================================================
 * P4 思维导图（/api/mindmap/course/{seriesId}，匿名）
 * 后端 snake_case 字段在此归一化为组件可读 camelCase。
 * =======================================================*/
export interface MindMapNode {
  id: string;
  name: string;
  category?: number;
  value?: number;
  /** 后端大写枚举：MASTERED / IN_PROGRESS / NOT_STARTED / BLOCKED（归一化后转小写） */
  status?: "not_started" | "learning" | "mastered" | "blocked";
  symbolSize?: number;
  x?: number;
  y?: number;
  /** 后端 mastery_ratio：0-1 掌握度 */
  masteryRatio?: number;
}

export interface MindMapLink {
  source: string;
  target: string;
  /** 后端 rel_type：CONTAINS / PREREQUISITE / RELATED_TO / TESTS */
  relation?: string;
  /** 后端 line_style：{color, type, width} */
  lineStyle?: { color?: string; type?: string; width?: number; curveness?: number };
}

export interface MindMapCategory {
  name: string;
  itemStyle?: { color?: string };
}

export interface MindMapResponse {
  title?: string;
  nodes: MindMapNode[];
  links: MindMapLink[];
  categories: MindMapCategory[];
  legend?: string[];
  stats?: Record<string, number | string>;
}

/**
 * 归一化后端 MindMap 响应（snake_case → 组件可读 camelCase）。
 * - links.rel_type → relation、links.line_style → lineStyle
 * - nodes.status 大写枚举 → 小写（MASTERED→mastered 等）
 * - nodes.mastery_ratio → masteryRatio（保留原字段，供需要时读取）
 */
export function normalizeMindMap(raw: {
  nodes?: Array<Record<string, unknown>>;
  links?: Array<Record<string, unknown>>;
  categories?: unknown;
  legend?: unknown;
  stats?: unknown;
  title?: unknown;
}): MindMapResponse {
  const STATUS_MAP: Record<string, MindMapNode["status"]> = {
    MASTERED: "mastered",
    IN_PROGRESS: "learning",
    NOT_STARTED: "not_started",
    BLOCKED: "blocked",
  };
  return {
    title: typeof raw.title === "string" ? raw.title : undefined,
    nodes: (raw.nodes ?? []).map((n) => {
      const status = typeof n.status === "string" ? STATUS_MAP[n.status] ?? undefined : undefined;
      return {
        id: String(n.id),
        name: String(n.name ?? ""),
        category: typeof n.category === "number" ? n.category : undefined,
        value: typeof n.value === "number" ? n.value : undefined,
        status,
        symbolSize: typeof n.symbolSize === "number" ? n.symbolSize : undefined,
        x: typeof n.x === "number" ? n.x : undefined,
        y: typeof n.y === "number" ? n.y : undefined,
        masteryRatio: typeof n.mastery_ratio === "number" ? n.mastery_ratio : undefined,
      };
    }),
    links: (raw.links ?? []).map((l) => ({
      source: String(l.source),
      target: String(l.target),
      relation: typeof l.rel_type === "string" ? l.rel_type : undefined,
      lineStyle: l.line_style && typeof l.line_style === "object" ? (l.line_style as MindMapLink["lineStyle"]) : undefined,
    })),
    categories: Array.isArray(raw.categories) ? (raw.categories as MindMapCategory[]) : [],
    legend: Array.isArray(raw.legend) ? (raw.legend as string[]) : undefined,
    stats: raw.stats && typeof raw.stats === "object" ? (raw.stats as Record<string, number | string>) : undefined,
  };
}

/**
 * 获取课程系列思维导图。后端 snake_case 字段在此归一化为组件可读 camelCase。
 */
export async function getCourseMindmap(seriesId: number): Promise<MindMapResponse> {
  const data = await http.get<Record<string, unknown>>(`/api/mindmap/course/${seriesId}`);
  return normalizeMindMap(data);
}
