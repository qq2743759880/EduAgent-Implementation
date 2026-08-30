/**
 * 我的班次 API 封装（task47，契约⑪）
 *
 * 路由：GET /api/enrollments/me/cohorts?status=
 * 状态：后端 task20/21 未就绪 —— 本模块先按契约⑪ + P10 规范定义类型/调用，
 *       联调后可稳定接收后端 JSON。task40 红线：读操作不 catch 兜底伪装成功（R-7）。
 *
 * progress 关系：enroll_status 直接来自后端，不再由 overall_ratio 推断（区别于旧 P3
 *   MyCourseCard 的「≥99.99% → 已完成」推断）。
 */
"use client";

import { http } from "@/lib/api-client";

/** enroll_status 全集（对齐 src/lib/status.ts STATUS_MAPS.enroll_status） */
export type EnrollStatus = "active" | "completed" | "cancelled" | "refunded";

/** 下次课（四级结构：module → session，用于「继续学习」跳转 + 展示） */
export interface EnrolledNextSession {
  series_id?: number | null;
  module_id?: number | null;
  module_title?: string | null;
  session_id?: number | null;
  session_title?: string | null;
  /** ISO 上课时间（后端已格式化，如 2026-03-08 09:00） */
  teaching_at?: string | null;
}

/** 退款信息（refunded 态展示「查看退款」） */
export interface EnrolledRefund {
  refund_no?: string | null;
  refund_amount?: string | null;
  refunded_at?: string | null;
}

/**
 * 我的班次单条（契约⑪ GET /api/enrollments/me/cohorts 列表元素）。
 * 字段名预留为后端 snake_case；类型字段全部可选容错（联调期后端字段可能微调）。
 */
export interface EnrolledCohort {
  /** 报名记录 id（student_cohort_rel） */
  enrollment_id: number;
  /** 班次 id */
  cohort_id: number;
  cohort_name?: string | null;
  /** 系列 id（用于跳转） */
  series_id: number;
  series_name?: string | null;
  series_code?: string | null;
  /** 学科 / 级别（徽章映射复用 curriculum SUBJECT_OPTIONS / LEVEL_OPTIONS） */
  subject_code?: string | null;
  level_code?: string | null;
  cover_url?: string | null;
  delivery_mode?: "online_live" | "online_recorded" | "offline_face_to_face" | null;
  /** 报名状态：active/completed/cancelled/refunded */
  enroll_status: EnrollStatus;

  /* ---------- 进度聚合（四级：模块 / 课次） ---------- */
  overall_ratio?: number | null;
  module_done?: number | null;
  module_total?: number | null;
  session_done?: number | null;
  session_total?: number | null;

  /* ---------- 下次课 / 结课 / 退款 ---------- */
  next_session?: EnrolledNextSession | null;
  /** 结课时间（completed 态） */
  finished_at?: string | null;
  /** 退款单（refunded 态） */
  refund?: EnrolledRefund | null;
}

/** 班次状态 tab id（对齐 STATUS_MAPS.enroll_status active/completed/refunded；cancelled 不独立成 tab） */
export type EnrolledTabId = "active" | "completed" | "refunded";

/**
 * 拉取我的班次列表。
 * @param status 可选，按 enroll_status 过滤（active/completed/cancelled/refunded 均可）；
 *               不传则返回全部（当前页面拉全量后在本地按 tab 分组）。
 */
export function getEnrolledCohorts(status?: EnrollStatus): Promise<EnrolledCohort[]> {
  const qs = status ? `?status=${status}` : "";
  return http.get<EnrolledCohort[]>(`/api/enrollments/me/cohorts${qs}`);
}