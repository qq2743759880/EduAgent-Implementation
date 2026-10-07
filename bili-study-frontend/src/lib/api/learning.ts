/**
 * 学习中心 / 播放页 / 复习模式的 API 请求封装（task40 改造）
 * 路由来源：
 *   - P3 progress:   /api/progress/courses | video/tick-batch | homework/submit | exam/submit
 *   - P5 互动习题:   /api/interactive/quiz/next | /submit | /wrong-book
 *   - P5 单词闯关:   /api/vocab/daily | /recall | /progress
 *   - P4 个人导图:   /api/mindmap/me/{seriesId}
 *   - 服务端收藏：   @/lib/api/favorites.ts（task16 班次收藏；下方 localStorage 版为过渡）
 *
 * task40 红线：拦截器已解包（零 .data）；读操作不 catch 兜底伪装成功（R-7），
 * 错误向上抛 ApiError，组件/Query 层负责空态渲染。
 */
"use client";

import { http } from "@/lib/api-client";
import { type MindMapResponse } from "./curriculum";

/* ---------- 进度（P3） ---------- */

export interface SessionProgressOut {
  session_id: number;
  session_title?: string | null;
  video_watch_ratio?: number | null;
  video_watch_seconds?: number | null;
  video_total_seconds?: number | null;
  homework_done_ratio?: number | null;
  exam_done_ratio?: number | null;
  session_score?: number | null;
  last_updated_at?: string | null;
}

export interface ModuleProgressOut {
  module_id: number;
  module_title?: string | null;
  overall_ratio?: number | null;
  sessions?: SessionProgressOut[];
}

export interface CourseProgressOut {
  series_id: number;
  series_title: string;
  series_code?: string | null;
  subject_code?: string | null;
  level_code?: string | null;
  cover_url?: string | null;
  overall_ratio?: number | null;
  video_watch_ratio?: number | null;
  homework_done_ratio?: number | null;
  exam_done_ratio?: number | null;
  last_session_id?: number | null;
  last_session_title?: string | null;
  last_activity_at?: string | null;
  enrolled_at?: string | null;
  modules?: ModuleProgressOut[];
  /** 本地字段：收藏标记（服务端收藏见 favorites.ts） */
  __favorited?: boolean;
}

export function getMyCourses(seriesId?: number): Promise<CourseProgressOut[]> {
  const qs = typeof seriesId === "number" && seriesId > 0 ? `?series_id=${seriesId}` : "";
  return http.get<CourseProgressOut[]>(`/api/progress/courses${qs}`);
}

export interface VideoTickInput {
  session_id: number;
  tick_second: number;
  total_seconds?: number | null;
}
export interface TickBatchResult {
  saved_count: number;
  watch_ratio_synced?: number | null;
}

function generatePlaySessionId(seriesId: number): string {
  const rand8 =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `ps-${seriesId}-${Date.now().toString(36)}-${rand8}`;
}

export async function submitVideoTicks(
  seriesId: number,
  ticks: VideoTickInput[],
  options: { play_session_id?: string } = {},
): Promise<TickBatchResult> {
  if (!ticks.length) return { saved_count: 0 };
  const play_session_id = options.play_session_id ?? generatePlaySessionId(seriesId);
  return http.post<TickBatchResult>("/api/progress/video/tick-batch", {
    play_session_id,
    series_id: seriesId,
    ticks,
  });
}

export interface HomeworkSubmitInput {
  series_id: number;
  session_id: number;
  homework_title?: string | null;
  score_earned?: number | null;
  score_total?: number | null;
  detail_payload?: unknown;
}
export async function submitHomework(
  input: HomeworkSubmitInput,
): Promise<{ saved: boolean; session_homework_ratio?: number | null }> {
  /*
   * 后端 homework submit 的 Pydantic schema 要求 answers 字段（而非 detail_payload），
   * 缺它直接 422 "Field required" @ loc=["body","answers"]。
   * 两边都传，score_* 原样保留。
   */
  const body: Record<string, unknown> = {
    series_id: input.series_id,
    session_id: input.session_id,
    homework_title: input.homework_title ?? null,
    answers: (input as unknown as { answers?: unknown }).answers ?? input.detail_payload ?? {},
    score_earned: input.score_earned ?? null,
    score_total: input.score_total ?? null,
    detail_payload: input.detail_payload ?? null,
  };
  return http.post<{ saved: boolean; session_homework_ratio?: number | null }>(
    "/api/progress/homework/submit",
    body,
  );
}

export interface ExamSubmitInput {
  series_id: number;
  session_id: number;
  exam_title?: string | null;
  score_earned?: number | null;
  score_total?: number | null;
  session_score_outof100?: number | null;
  paper_id?: string | number | null;
  detail_payload?: unknown;
}
export async function submitExam(
  input: ExamSubmitInput,
): Promise<{ saved: boolean; session_score_synced?: number | null }> {
  /*
   * 后端 exam submit 要求 paper_id（422 "Field required" @ loc=["body","paper_id"]）。
   * 调用方未传时用 `paper-s-session` 规则生成稳定占位 id。
   */
  const paperId = input.paper_id ?? `paper-${input.series_id}-${input.session_id}`;
  const body: Record<string, unknown> = {
    series_id: input.series_id,
    session_id: input.session_id,
    exam_title: input.exam_title ?? null,
    paper_id: paperId,
    answers: (input as unknown as { answers?: unknown }).answers ?? input.detail_payload ?? {},
    score_earned: input.score_earned ?? null,
    score_total: input.score_total ?? null,
    session_score_outof100: input.session_score_outof100 ?? null,
    detail_payload: input.detail_payload ?? null,
  };
  return http.post<{ saved: boolean; session_score_synced?: number | null }>(
    "/api/progress/exam/submit",
    body,
  );
}

/* ---------- P5 互动习题（quiz） ---------- */

export type QuestionMode =
  | "SINGLE"
  | "MULTIPLE"
  | "JUDGE"
  | "FILL"
  | "DRAG"
  | "MATCH";

export interface QuestionOption {
  key: string;
  text: string;
}

export interface QuestionOut {
  question_id: number | string;
  subject_code?: string | null;
  mode: QuestionMode;
  difficulty?: "EASY" | "NORMAL" | "HARD" | null;
  stem: string;
  options?: QuestionOption[] | null;
  blanks_hint?: string[] | null;
  is_from_wrong_book?: boolean;
  wrong_book_id?: number | null;
  source_session_id?: number | null;
}

export interface NextQuestionParams {
  subject_code?: string;
  series_id?: number;
  session_id?: number;
  mode?: QuestionMode | "MIXED";
  difficulty?: string;
  from_wrong_book?: boolean;
  prefer_wrong_book_ratio?: number;
  only_not_mastered?: boolean;
}

export interface SubmitAnswerInput {
  question_id: number | string;
  subject_code?: string;
  answer: unknown; // SINGLE/JUDGE=string; MULTIPLE=string[]; FILL=string[]
  time_spent_seconds?: number;
  user_analysis?: string;
  used_hint?: boolean;
  session_id?: number;
  custom_code?: string;
  series_id?: number;
}

export interface SubmitAnswerOut {
  is_correct: boolean;
  score?: number | null;
  correct_answer?: unknown;
  explain_content?: string | null;
  mastery_changed?: number | null;
  wrong_book_snapshot_saved?: boolean;
  wrong_book_id?: number | null;
}

export async function getNextQuestion(params: NextQuestionParams = {}): Promise<QuestionOut | null> {
  const search = new URLSearchParams();
  if (params.subject_code) search.set("subject_code", params.subject_code);
  if (typeof params.series_id === "number") search.set("series_id", String(params.series_id));
  if (typeof params.session_id === "number") search.set("session_id", String(params.session_id));
  if (params.mode) search.set("mode", params.mode);
  if (params.difficulty) search.set("difficulty", params.difficulty);
  if (params.from_wrong_book) search.set("from_wrong_book", "1");
  if (typeof params.prefer_wrong_book_ratio === "number") {
    search.set("prefer_wrong_book_ratio", String(params.prefer_wrong_book_ratio));
  }
  if (params.only_not_mastered) search.set("only_not_mastered", "1");
  const data = await http.get<QuestionOut | { question: QuestionOut } | null>(
    `/api/interactive/quiz/next?${search.toString()}`,
  );
  if (!data) return null;
  return isQuestionOut(data) ? data : data.question ?? null;
}

export async function submitAnswer(input: SubmitAnswerInput): Promise<SubmitAnswerOut> {
  /*
   * 后端 quiz submit 要求以下字段（缺任一 422）：
   *   - custom_code（前端兜底 `q-${question_id}`）
   *   - question_type（调用方未给时兜底 SINGLE）
   */
  const custom_code =
    input.custom_code ??
    (input.question_id == null ? "q-0" : `q-${String(input.question_id)}`);
  const question_type =
    (input as unknown as { question_type?: QuestionMode }).question_type ?? "SINGLE";
  const body: Record<string, unknown> = {
    question_id: input.question_id,
    question_type,
    custom_code,
    subject_code: input.subject_code ?? null,
    answer: input.answer,
    time_spent_seconds: input.time_spent_seconds ?? null,
    user_analysis: input.user_analysis ?? null,
    used_hint: !!input.used_hint,
    session_id: input.session_id ?? null,
    series_id: typeof input.series_id === "number" ? input.series_id : null,
  };
  return http.post<SubmitAnswerOut>("/api/interactive/quiz/submit", body);
}

export interface WrongBookItem {
  id: number;
  question_id: number | string;
  stem: string;
  mode?: QuestionMode | null;
  correct_answer?: unknown;
  user_answer_wrong?: unknown;
  explain_content?: string | null;
  mistake_count?: number | null;
  last_mistake_at?: string | null;
  mastered_at?: string | null;
  /** 错题来源课次，用于从错题本跳回对应课 */
  source_session_id?: number | null;
}

export interface WrongBookPage {
  items: WrongBookItem[];
  total: number;
  page: number;
  page_size: number;
}

export async function listWrongBook(params: {
  subject_code?: string;
  page?: number;
  page_size?: number;
  only_not_mastered?: boolean;
}): Promise<WrongBookPage> {
  const search = new URLSearchParams();
  if (params.subject_code) search.set("subject_code", params.subject_code);
  search.set("page", String(params.page ?? 1));
  search.set("page_size", String(params.page_size ?? 20));
  if (params.only_not_mastered) search.set("only_not_mastered", "1");
  return http.get<WrongBookPage>(`/api/interactive/quiz/wrong-book?${search.toString()}`);
}

/* ---------- P5 单词闯关 ---------- */

export interface VocabCardOut {
  card_id: number | string;
  word: string;
  phonetic?: string | null;
  definition?: string | null;
  examples?: string[] | null;
  subject_code?: string | null;
  source_series_id?: number | null;
  ef?: number | null;
  repetition?: number | null;
  interval_days?: number | null;
  next_review_at?: string | null;
}

export interface VocabDailyOut {
  today: string;
  plan_count: number;
  cards: VocabCardOut[];
  mastered_today?: number | null;
  new_today?: number | null;
}

export async function getVocabDaily(params?: {
  subject_code?: string;
  plan_count?: number;
  include_new_ratio?: number;
}): Promise<VocabDailyOut> {
  const search = new URLSearchParams();
  if (params?.subject_code) search.set("subject_code", params.subject_code);
  if (typeof params?.plan_count === "number") search.set("plan_count", String(params.plan_count));
  if (typeof params?.include_new_ratio === "number") {
    search.set("include_new_ratio", String(params.include_new_ratio));
  }
  return http.get<VocabDailyOut>(`/api/vocab/daily?${search.toString()}`);
}

/**
 * recallVocab —— 提交一次 SM-2 质量分（0..5）
 * quality 0-1：失败；2-3：拉锯；4-5：良好
 */
export async function recallVocab(params: {
  card_id: number | string;
  quality: 0 | 1 | 2 | 3 | 4 | 5;
  time_spent_seconds?: number;
  show_hint?: boolean;
}): Promise<{
  accepted: boolean;
  next_ef?: number | null;
  next_repetition?: number | null;
  next_interval_days?: number | null;
  next_review_at?: string | null;
  mastery_updated?: number | null;
}> {
  return http.post("/api/vocab/recall", params);
}

export interface VocabProgressOut {
  subject_code?: string | null;
  streak_days?: number | null;
  total_cards?: number | null;
  mastered_cards?: number | null;
  learning_cards?: number | null;
  due_today?: number | null;
  last_30_days?: { date: string; studied_count?: number | null }[];
}

export async function getVocabProgress(params?: {
  subject_code?: string;
  window_days?: number;
}): Promise<VocabProgressOut> {
  const search = new URLSearchParams();
  if (params?.subject_code) search.set("subject_code", params.subject_code);
  if (typeof params?.window_days === "number") search.set("window_days", String(params.window_days));
  return http.get<VocabProgressOut>(`/api/vocab/progress?${search.toString()}`);
}

/* ---------- P4 个人导图（我的掌握） ---------- */

export async function getMyCourseMindmap(seriesId: number): Promise<MindMapResponse> {
  return http.get<MindMapResponse>(`/api/mindmap/me/${seriesId}`);
}

/* ---------- 本地：收藏（localStorage，过渡实现） ----------
 * 服务端班次收藏已由 task16 落地，客户端见 @/lib/api/favorites.ts。
 * 页面全量切换到服务端收藏在 fe-task 后续页面任务中执行，此处保留兼容。
 */

const FAV_KEY = "edu:fav:series_ids";

function readFavIds(): Set<number> {
  if (typeof window === "undefined") return new Set<number>();
  try {
    const raw = window.localStorage.getItem(FAV_KEY);
    if (!raw) return new Set<number>();
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return new Set<number>();
    const set = new Set<number>();
    for (const v of arr) {
      const n = Number(v);
      if (Number.isFinite(n) && n > 0) set.add(n);
    }
    return set;
  } catch {
    return new Set<number>();
  }
}
function writeFavIds(set: Set<number>) {
  if (typeof window === "undefined") return;
  const arr = Array.from(set).sort((a, b) => a - b);
  window.localStorage.setItem(FAV_KEY, JSON.stringify(arr));
}

export function favoriteSeriesIds(): number[] {
  return Array.from(readFavIds());
}
export function isSeriesFavorited(seriesId: number): boolean {
  return readFavIds().has(seriesId);
}
export function toggleFavoriteSeries(seriesId: number): boolean {
  const set = readFavIds();
  if (set.has(seriesId)) {
    set.delete(seriesId);
    writeFavIds(set);
    return false;
  }
  set.add(seriesId);
  writeFavIds(set);
  return true;
}
export function setFavoriteSeries(seriesId: number, fav: boolean): void {
  const set = readFavIds();
  if (fav) set.add(seriesId);
  else set.delete(seriesId);
  writeFavIds(set);
}

/* ---------- 类型守卫 ---------- */

function isQuestionOut(x: unknown): x is QuestionOut {
  return (
    !!x &&
    typeof x === "object" &&
    "mode" in (x as Record<string, unknown>) &&
    "stem" in (x as Record<string, unknown>)
  );
}
