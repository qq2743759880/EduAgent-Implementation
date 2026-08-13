/**
 * 管理端用户 API（task03，G3 用户管理）
 *
 * 契约来源（L1：以 edu-agent 后端代码为准，design-guide §4.5 仅是摘要）：
 *  - app/admin/user_admin/router.py + schemas.py（P7 管理端用户管理）
 *
 * 关键契约（后端为权威）：
 *  - 列表项主键是 user_id（非 id）；字段 username/real_name/phone/email/role_code/status/yn
 *  - 角色切换 POST /{user_id}/role body {target_role, reason?}
 *    → 最后 1 个可用 admin 降级被拒：40303「至少保留 1 名可用管理员账号」
 *  - 状态切换 POST /{user_id}/status body {status: 0|1, yn?, reason?}（status 必填）
 *  - dashboard/metrics 是独立接口：GET /api/admin/users/dashboard/metrics
 *
 * 错误契约（R-7）：所有写操作失败一律向上抛 ApiError，由 useMutation onError → toast。
 */
import { adminGet, adminPost } from "@/lib/api/admin";
import type { AdminPage } from "@/lib/admin-api-types";

/* ============================================================
 * 枚举
 * ============================================================ */
export const USER_ROLE_OPTIONS = [
  { value: "admin", label: "管理员" },
  { value: "manager", label: "运营" },
  { value: "teacher", label: "教师" },
  { value: "student", label: "学员" },
] as const;
export type UserRoleValue = (typeof USER_ROLE_OPTIONS)[number]["value"];

export const USER_STATUS_OPTIONS = [
  { value: 1, label: "正常" },
  { value: 0, label: "禁用" },
] as const;

/* ============================================================
 * 类型（对齐后端 schemas）
 * ============================================================ */
export interface AdminUserItem {
  user_id: number;
  username?: string | null;
  real_name?: string | null;
  phone?: string | null;
  email?: string | null;
  role_code: string;
  status: number;
  yn: number;
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
}

export interface DashboardMetrics {
  total_user_count: number;
  active_user_count_7d: number;
  role_breakdown: Record<string, number>;
  disabled_user_count: number;
  new_register_count_7d: number;
  avg_login_days_per_user_30d: number;
}

export interface ListUsersParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  yn?: number | boolean;
  role_code?: string;
  /** 账号状态：1 正常 / 0 禁用 */
  status?: number;
}

/* ============================================================
 * 接口
 * ============================================================ */
export async function listUsers(params: ListUsersParams = {}): Promise<AdminPage<AdminUserItem>> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };
  if (params.role_code) query.role_code = params.role_code;
  if (params.keyword?.trim()) query.keyword = params.keyword.trim();
  if (typeof params.status === "number") query.status = params.status;
  if (typeof params.yn === "number") query.yn = params.yn;
  return adminGet<AdminPage<AdminUserItem>>("/api/admin/users", query);
}

export async function changeUserRole(
  userId: number,
  targetRole: string,
  reason?: string,
): Promise<{ updated: boolean; user_id: number; target_role: string }> {
  return adminPost<{ updated: boolean; user_id: number; target_role: string }>(
    `/api/admin/users/${userId}/role`,
    { target_role: targetRole, reason },
  );
}

export async function changeUserStatus(
  userId: number,
  input: { status: number; yn?: number; reason?: string },
): Promise<{ updated: boolean; user_id: number; status: number; yn?: number }> {
  const body: { status: number; yn?: number; reason?: string } = { status: input.status };
  if (typeof input.yn === "number") body.yn = input.yn;
  if (input.reason?.trim()) body.reason = input.reason.trim();
  return adminPost<{ updated: boolean; user_id: number; status: number; yn?: number }>(
    `/api/admin/users/${userId}/status`,
    body,
  );
}

export async function getDashboardMetrics(): Promise<DashboardMetrics> {
  return adminGet<DashboardMetrics>("/api/admin/users/dashboard/metrics");
}

/* ============================================================
 * 显示辅助（纯函数）
 * ============================================================ */
export function userRoleLabel(code: string): string {
  return USER_ROLE_OPTIONS.find((r) => r.value === code)?.label ?? code;
}

/** 用户展示名：real_name > username > email > 未知 */
export function userDisplayName(u: AdminUserItem): string {
  return (
    u.real_name?.trim() ||
    u.username?.trim() ||
    u.email?.trim() ||
    `用户#${u.user_id}`
  );
}

export function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
