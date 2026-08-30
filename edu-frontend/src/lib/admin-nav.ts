/**
 * 管理端导航 & RBAC 角色工具（task02，G2 管理端布局与权限）
 *
 * - ADMIN_NAV_ITEMS：6 个菜单（仪表盘/课程/题库/用户/RAG/MCP）
 * - RBAC 契约（2026-08-12 对抗修正 #2）：后端 /api/admin/* 全部 require_role([ADMIN])
 *   （user_admin / course_admin / question_admin / rag_admin / mcp 各 router 实测，
 *   manager 访问任一管理端点即 403），故前端放行集合收紧为仅 admin：
 *   - ADMIN_ALLOWED_ROLES = ["admin"]（不再放行 manager）
 *   - filterAdminNav 仅 admin 渲染 6 菜单，其余角色渲染 0 项（守卫已拦截，菜单不展示）
 * - 角色数据源：useAuthStore(s => s.me?.roles)（auth-client._normalizeUser 归一化，
 *   值形如 "admin"/"manager"/"teacher"/"student"；本模块统一小写兼容）
 *
 * 本模块为纯函数（无 React hooks / 无 window），供 layout 与测试直接复用。
 */
import type { ComponentType } from "react";
import {
  BookOpen,
  Cable,
  LayoutDashboard,
  ListChecks,
  Network,
  Users,
} from "lucide-react";

/** 管理端 RBAC 放行角色（仅 admin —— 后端 /api/admin/* 全部 ADMIN-only，见对抗 #2 处置） */
export const ADMIN_ALLOWED_ROLES = ["admin"] as const;
export type AdminRole = (typeof ADMIN_ALLOWED_ROLES)[number];

export interface AdminNavItem {
  href: string;
  label: string;
  Icon: ComponentType<{ className?: string }>;
  /** 激活态匹配前缀（子路由如 /admin/courses/[seriesId] 也算激活） */
  matchPrefix: string;
}

/** 6 个管理端菜单（URL 统一 /admin/* 前缀，与用户端 /courses /dashboard 隔离） */
export const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  { href: "/admin/dashboard", label: "仪表盘", Icon: LayoutDashboard, matchPrefix: "/admin/dashboard" },
  { href: "/admin/courses", label: "课程", Icon: BookOpen, matchPrefix: "/admin/courses" },
  { href: "/admin/questions", label: "题库", Icon: ListChecks, matchPrefix: "/admin/questions" },
  { href: "/admin/users", label: "用户", Icon: Users, matchPrefix: "/admin/users" },
  { href: "/admin/rag", label: "RAG", Icon: Network, matchPrefix: "/admin/rag" },
  { href: "/admin/mcp", label: "MCP", Icon: Cable, matchPrefix: "/admin/mcp" },
];

const ADMIN_ALLOWED_SET: ReadonlySet<string> = new Set(ADMIN_ALLOWED_ROLES);

function normalizeRole(role: unknown): string {
  return typeof role === "string" ? role.trim().toLowerCase() : "";
}

/** 是否管理端放行角色（仅 admin，大小写不敏感；manager/teacher/student 一律不放行） */
export function isAdminRole(roles?: string[] | null): boolean {
  if (!Array.isArray(roles) || roles.length === 0) return false;
  return roles.some((r) => ADMIN_ALLOWED_SET.has(normalizeRole(r)));
}

/** 是否 admin（与 isAdminRole 语义一致：放行集合即 admin，保留命名区分调用意图） */
export function isAdmin(roles?: string[] | null): boolean {
  if (!Array.isArray(roles) || roles.length === 0) return false;
  return roles.some((r) => normalizeRole(r) === "admin");
}

/** RBAC 菜单过滤：仅 admin 渲染 6 项；manager/teacher/student/未知渲染 0 项（守卫已拦截） */
export function filterAdminNav(roles?: string[] | null): AdminNavItem[] {
  return isAdminRole(roles) ? ADMIN_NAV_ITEMS : [];
}
