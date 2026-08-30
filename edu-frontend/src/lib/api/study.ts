import { http } from "@/lib/api-client";

/**
 * 学习域客户端（PROPOSED — 待后端 task21 实现，契约冻结后跑 contract-diff 复核）
 * 端点设计上浮见 .opencode/handoffs/api-request.md
 * 业务语义：班次访问鉴权（access_scope）/ 学习大纲 / 课次完成态；
 * 打点 / 作业 / 考试提交仍走 learning.ts 消费的 /api/progress 契约
 */

export interface StudyAccessResult {
  series_id: number;
  cohort_id: number | null;
  accessible: boolean;
  reason: string | null;
}

export interface StudySessionOutlineItem {
  session_id: number;
  session_title: string;
  session_no: number;
  duration_minutes: number;
  video_url: string | null;
  watch_ratio: number;
  homework_done: boolean;
}

export interface StudyModuleOutlineItem {
  module_id: number;
  module_title: string;
  module_no: number;
  overall_ratio: number;
  sessions: StudySessionOutlineItem[];
}

export interface StudyOutline {
  series_id: number;
  series_title: string;
  overall_ratio: number;
  total_sessions: number;
  completed_sessions: number;
  modules: StudyModuleOutlineItem[];
}

export interface SessionCompleteResult {
  session_id: number;
  completed: boolean;
}

export function getStudyAccess(seriesId: number): Promise<StudyAccessResult> {
  return http.get<StudyAccessResult>(`/api/study/courses/${seriesId}/access`);
}

export function getStudyOutline(seriesId: number): Promise<StudyOutline> {
  return http.get<StudyOutline>(`/api/study/courses/${seriesId}/outline`);
}

export function completeStudySession(
  sessionId: number,
): Promise<SessionCompleteResult> {
  return http.post<SessionCompleteResult>(
    `/api/study/sessions/${sessionId}/complete`,
  );
}
