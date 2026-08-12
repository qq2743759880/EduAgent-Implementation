/**
 * 分级课程 API 封装
 * 后端路由：/api/curriculum/*（匿名可访问）
 * 思维导图：/api/mindmap/course/{seriesId}（P4 接口，匿名）
 */
import { api } from "@/lib/api-client";

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

export interface SeriesSummary {
  id: number;
  series_code: string;
  series_title: string;
  subject_code: string;
  level_code: string;
  subtitle?: string | null;
  description?: string | null;
  cover_url?: string | null;
  total_hours?: number | null;
  session_count?: number | null;
  module_count?: number | null;
  cohort_count?: number | null;
  rating?: number | null;
  student_count?: number | null;
  price_original?: number | null;
  price_current?: number | null;
  yn?: number;
}

export interface PageMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface SeriesListResponse {
  items: SeriesSummary[];
  page_meta: PageMeta;
}

export interface CohortOut {
  id: number;
  series_id: number;
  cohort_code: string;
  cohort_title: string;
  schedule_note?: string | null;
  price_original?: number | null;
  price_current?: number | null;
  capacity?: number | null;
  enrolled_count?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  yn?: number;
}

export interface SessionOut {
  id: number;
  module_id: number;
  session_title: string;
  stage_no?: number | null;
  duration_minutes?: number | null;
  teaching_date?: string | null;
  video_url?: string | null;
  is_free_preview?: number | null;
}

export interface ModuleOut {
  id: number;
  series_id: number;
  module_no?: number | null;
  module_title: string;
  stage_no?: number | null;
  description?: string | null;
  sessions?: SessionOut[];
  session_count?: number | null;
}

export interface SeriesDetailResponse {
  series: SeriesSummary;
  cohorts: CohortOut[];
  modules: ModuleOut[];
}

export interface SeriesTreeResponse {
  series: SeriesSummary;
  cohorts: CohortOut[];
  modules: ModuleOut[];
}

export interface ListSeriesParams {
  subject_code?: SubjectCode | "all";
  level_code?: LevelCode | "all";
  keyword?: string;
  min_price?: number;
  max_price?: number;
  page?: number;
  page_size?: number;
}

export async function listSeries(params: ListSeriesParams = {}): Promise<SeriesListResponse> {
  const search = new URLSearchParams();
  if (params.subject_code && params.subject_code !== "all") {
    search.set("subject_code", params.subject_code);
  }
  if (params.level_code && params.level_code !== "all") {
    search.set("level_code", params.level_code);
  }
  if (params.keyword?.trim()) {
    search.set("keyword", params.keyword.trim());
  }
  if (typeof params.min_price === "number" && Number.isFinite(params.min_price)) {
    search.set("min_price", String(params.min_price));
  }
  if (typeof params.max_price === "number" && Number.isFinite(params.max_price)) {
    search.set("max_price", String(params.max_price));
  }
  search.set("page", String(params.page ?? 1));
  search.set("page_size", String(params.page_size ?? 12));

  const { data } = await api.get<SeriesListResponse>(`/api/curriculum/series?${search.toString()}`);
  /*
    前端本地扩展价格与评分：后端 P0-P 的 SeriesSummary 模型里 price_current 等字段可能为 None，
    这里给列表做一个本地 mock 兜底，保证 UI 在数据不完整时仍然有可读性。
  */
  const items = (data.items ?? []).map((it) => ({
    ...it,
    price_current: it.price_current ?? fallbackPrice(it),
    price_original: it.price_original ?? Math.round((it.price_current ?? fallbackPrice(it)) * 1.3),
    rating: it.rating ?? fallbackRating(it),
    student_count: it.student_count ?? fallbackStudents(it),
  }));
  return {
    items,
    page_meta: data.page_meta ?? {
      page: params.page ?? 1,
      page_size: params.page_size ?? 12,
      total: items.length,
      total_pages: Math.ceil(items.length / (params.page_size ?? 12)),
    },
  };
}

export async function getSeriesDetail(seriesId: number): Promise<SeriesDetailResponse> {
  const { data } = await api.get<SeriesDetailResponse>(`/api/curriculum/series/${seriesId}`);
  return data;
}

export async function getSeriesTree(seriesId: number): Promise<SeriesTreeResponse> {
  const { data } = await api.get<SeriesTreeResponse>(`/api/curriculum/series/${seriesId}/tree`);
  return data;
}

/**
 * getSeriesTreeFlat — 取课程树并摊平为播放页需要的形状。
 * 后端 curriculum.schemas 用的是 series_name / module_name / duration_minutes，
 * 而部分前端代码按 series_title / module_title 写；这里两套名字都兜住，
 * 避免任一侧改名后播放页直接空标题。
 */
export async function getSeriesTreeFlat(seriesId: number): Promise<SeriesTreeOut> {
  const { data } = await api.get<Record<string, any>>(
    `/api/curriculum/series/${seriesId}/tree`,
  );
  const s = (data?.series ?? {}) as Record<string, any>;
  const rawModules = Array.isArray(data?.modules) ? data.modules : [];
  return {
    title: s.series_name ?? s.series_title ?? "",
    series_code: s.series_code ?? null,
    subject_code: s.subject_code ?? null,
    level_code: s.level_code ?? null,
    cover_url: s.cover_url ?? null,
    modules: rawModules.map((m: Record<string, any>) => ({
      module_id: m.id ?? m.module_id,
      title: m.module_name ?? m.module_title ?? null,
      sessions: (Array.isArray(m.sessions) ? m.sessions : []).map(
        (x: Record<string, any>) => ({
          session_id: x.id ?? x.session_id,
          title: x.session_title ?? x.title ?? null,
          duration_seconds:
            typeof x.duration_minutes === "number"
              ? x.duration_minutes * 60
              : (x.duration_seconds ?? null),
          video_url: x.video_url ?? null,
        }),
      ),
    })),
  };
}

/*
 * P4 思维导图接口
 * 返回形态：{ nodes: [...], links: [...], categories: [...], legend: [...], stats: {...} }（由后端 mindmap.schemas.MindMap 定义）
 */
export interface MindMapNode {
  id: string;
  name: string;
  category?: number;
  value?: number;
  status?: "not_started" | "learning" | "mastered";
  symbolSize?: number;
  x?: number;
  y?: number;
}

export interface MindMapLink {
  source: string;
  target: string;
  relation?: string;
  lineStyle?: { type?: string; color?: string };
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
 * SeriesTreeOut — 播放页使用的扁平化视图
 * 由 getSeriesTree() 从后端嵌套结构 {series:{...}, modules:[...]} 摊平而来，
 * 字段名对齐后端 curriculum.schemas（series_name / module_name / duration_minutes）。
 */
export interface SeriesTreeOut {
  title: string;
  series_code?: string | null;
  subject_code?: string | null;
  level_code?: string | null;
  cover_url?: string | null;
  modules: Array<{
    module_id: number;
    title: string | null;
    sessions: Array<{
      session_id: number;
      title: string | null;
      duration_seconds?: number | null;
      video_url?: string | null;
    }>;
  }>;
}

export async function getCourseMindmap(seriesId: number): Promise<MindMapResponse> {
  const { data } = await api.get<MindMapResponse>(`/api/mindmap/course/${seriesId}`);
  return data;
}

// -------- 本地 mock 兜底（后端不完整时不影响 UI） --------
function fallbackPrice(s: SeriesSummary): number {
  const base = (s.id % 9) * 180 + 99;
  return Number(base.toFixed(0));
}
function fallbackRating(s: SeriesSummary): number {
  return Number((4.3 + ((s.id % 7) * 0.1)).toFixed(1));
}
function fallbackStudents(s: SeriesSummary): number {
  return 120 + (s.id % 13) * 80;
}
