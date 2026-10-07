/**
 * admin-nav.ts 单测：RBAC 菜单过滤 + 角色判断（task02 验收：管理端菜单 RBAC 过滤；
 * 2026-08-12 对抗修正 #2：后端 /api/admin/* 全部 require_role([ADMIN])，前端收紧为仅 admin 放行）
 */
import { describe, expect, it } from "vitest";
import {
  ADMIN_NAV_ITEMS,
  filterAdminNav,
  isAdmin,
  isAdminRole,
} from "./admin-nav";

describe("filterAdminNav（RBAC 菜单过滤）", () => {
  it("admin：渲染全部 6 个菜单", () => {
    const items = filterAdminNav(["admin"]);
    expect(items).toHaveLength(6);
    expect(items.map((i) => i.label)).toEqual(["仪表盘", "课程", "题库", "用户", "RAG", "MCP"]);
  });

  it("manager：渲染 0 个菜单（后端无任何管理端点权限，前端不渲染菜单）", () => {
    expect(filterAdminNav(["manager"])).toHaveLength(0);
  });

  it("student / teacher：渲染 0 个菜单", () => {
    expect(filterAdminNav(["student"])).toHaveLength(0);
    expect(filterAdminNav(["teacher"])).toHaveLength(0);
  });

  it("角色数组混合 admin 与 student：含 admin 即放行 6 项", () => {
    expect(filterAdminNav(["student", "admin"])).toHaveLength(6);
  });

  it("角色大小写不敏感：ADMIN 放行 6 项；Manager 不放行", () => {
    expect(filterAdminNav(["ADMIN"])).toHaveLength(6);
    expect(filterAdminNav(["Manager"])).toHaveLength(0);
  });

  it("无角色 / 空数组：渲染 0 项（守卫拦截逻辑另行测试）", () => {
    expect(filterAdminNav()).toHaveLength(0);
    expect(filterAdminNav(null)).toHaveLength(0);
    expect(filterAdminNav([])).toHaveLength(0);
  });
});

describe("isAdminRole（守卫放行集合，仅 admin）", () => {
  it("仅 admin 放行；manager 不放行（后端 ADMIN-only，对抗 #2）", () => {
    expect(isAdminRole(["admin"])).toBe(true);
    expect(isAdminRole(["manager"])).toBe(false);
    expect(isAdminRole(["student", "admin"])).toBe(true);
  });

  it("student / teacher 不放行", () => {
    expect(isAdminRole(["student"])).toBe(false);
    expect(isAdminRole(["teacher"])).toBe(false);
  });

  it("边界：undefined / null / 空数组 / 非字符串元素", () => {
    expect(isAdminRole()).toBe(false);
    expect(isAdminRole(null)).toBe(false);
    expect(isAdminRole([])).toBe(false);
    expect(isAdminRole(["ADMIN"])).toBe(true);
  });
});

describe("isAdmin（admin 判断）", () => {
  it("仅 admin 为 true；manager 不算 admin", () => {
    expect(isAdmin(["admin"])).toBe(true);
    expect(isAdmin(["manager"])).toBe(false);
    expect(isAdmin(["student"])).toBe(false);
  });
});

describe("ADMIN_NAV_ITEMS 契约", () => {
  it("恰好 6 个菜单", () => {
    expect(ADMIN_NAV_ITEMS).toHaveLength(6);
  });

  it("所有菜单 href 均为 /admin/* 前缀（与用户端路由隔离）", () => {
    for (const item of ADMIN_NAV_ITEMS) {
      expect(item.href.startsWith("/admin/")).toBe(true);
    }
  });
});
