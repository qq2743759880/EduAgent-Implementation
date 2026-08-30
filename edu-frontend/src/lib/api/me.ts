/**
 * 用户端「个人中心 /me」API 封装（G5 / fe-task54）
 *
 * 契约口径（edu-agent/app/users/router.py:file:line 实证）：
 *   - GET  /api/users/me                → MeHead（兼容端点：auth info + 画像合并视图，router.py:39-57）
 *   - GET  /api/users/me/student-profile → StudentProfileRow ｜ {}（router.py:60-69，student_profile 表原始行）
 *   - GET  /api/users/me/learning-summary → LearningSummary（router.py:72-118：总时长/活跃班次/作业/考试）
 *   - PUT  /api/users/me/profile        → UserProfile（schemas.py:66-81 UserProfileUpdate，全 Optional）
 *
 * 积分/等级 StatCard 复用 community.ts getMyPoints（GET /api/gamification/me/points，契约⑬），不重复定义。
 *
 * 写入缺口（契约⑤ 现状）：student_profile 表仅有 GET 读取；PUT /api/users/me/profile 仅持久化
 * UserProfile 字段（nickname / grade_code / school_name / learning_goals / subject_preferences ...）。
 * student_profile 的 learner_identity_id / learning_goal_id / education_level_id / industry_name /
 * job_role_name / years_of_experience **无对应写入端点** —— 本页档案表单对这部分做展示回显，
 * 保存仅把 UserProfile 可写字段（school_name → 学校）经 PUT /me/profile 提交，缺口在 handoff 标注。
 * 错误处理：读操作不 try/catch 兜底，错误上抛 ApiError 由页面 ErrorState 承接（R-7）。
 */
import { http } from "@/lib/api-client";

/** GET /api/users/me 契约（router.py:39-57 实证形状） */
export interface MeHead {
  id: number;
  nickname: string;
  email?: string | null;
  avatar?: string | null;
  roles?: string[];
  tenantId?: number | null;
  learningGoal?: string;
  subjectPreferences?: string[];
  profile?: Record<string, unknown>;
}

/** GET /api/users/me/student-profile：student_profile 表原始行（FK/枚举原值，未 JOIN 展示名） */
export interface StudentProfileRow {
  user_id?: number;
  learner_identity_id?: number | null;
  learning_goal_id?: number | null;
  education_level_id?: number | null;
  grade_id?: number | null;
  real_name?: string | null;
  phone?: string | null;
  email?: string | null;
  class_name?: string | null;
  school_name?: string | null;
  industry_name?: string | null;
  job_role_name?: string | null;
  years_of_experience?: string | null;
  [k: string]: unknown;
}

/** GET /api/users/me/learning-summary 契约（router.py:113-118） */
export interface LearningSummary {
  total_watched_seconds: number;
  active_cohorts_count: number;
  homework_submitted: number;
  exam_submitted: number;
  exam_avg_score: number;
}

/** PUT /api/users/me/profile 可写子集（UserProfileUpdate 实证字段，仅传需更新的键） */
export interface MeProfilePatch {
  nickname?: string;
  school_name?: string;
  grade_code?: string;
}

/** 读当前用户（auth info + 画像合并视图） */
export function getMe(): Promise<MeHead> {
  return http.get<MeHead>("/api/users/me");
}

/** 读学员档案（student_profile 表影院行，可能为 {}） */
export function getStudentProfile(): Promise<StudentProfileRow> {
  return http.get<StudentProfileRow>("/api/users/me/student-profile");
}

/** 读学习汇总（total_watched_seconds / active_cohorts_count / ...） */
export function getLearningSummary(): Promise<LearningSummary> {
  return http.get<LearningSummary>("/api/users/me/learning-summary");
}

/** 保存 UserProfile 可写字段（school→school_name；其余 student_profile dim 字段无写入端点） */
export function updateProfile(payload: MeProfilePatch): Promise<Record<string, unknown>> {
  return http.put<Record<string, unknown>>("/api/users/me/profile", payload);
}