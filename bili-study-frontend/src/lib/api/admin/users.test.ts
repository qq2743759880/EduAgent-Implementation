/**
 * lib/api/admin/users.ts 单测（task03 / task40 拦截器解包迁移）
 * 验证：列表参数、角色/状态切换请求体、dashboard metrics 路径、写操作失败必须抛（R-7）
 * mock http.* 直接返回业务体（契约冻结①：拦截器已解包，无 .data 壳）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, ApiError } from "@/lib/api-client";
import {
  changeUserRole,
  changeUserStatus,
  getDashboardMetrics,
  listUsers,
  userDisplayName,
  userRoleLabel,
} from "./users";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);

beforeEach(() => vi.clearAllMocks());

describe("用户列表", () => {
  it("role_code/keyword/status 过滤 + 分页透传", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 20, items: [] });
    await listUsers({ role_code: "teacher", keyword: "张", status: 1, page: 2, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/users", {
      params: {
        page: 2, page_size: 20, role_code: "teacher", keyword: "张", status: 1,
      },
    });
  });
});

describe("角色切换 / 状态切换", () => {
  it("changeUserRole POST /{id}/role body {target_role}", async () => {
    mockPost.mockResolvedValueOnce({ updated: true, user_id: 5, target_role: "teacher" });
    await changeUserRole(5, "teacher");
    expect(mockPost).toHaveBeenCalledWith("/api/admin/users/5/role", { target_role: "teacher", reason: undefined });
  });

  it("changeUserRole 携带 reason", async () => {
    mockPost.mockResolvedValueOnce({ updated: true, user_id: 5, target_role: "student" });
    await changeUserRole(5, "student", "转班");
    expect(mockPost).toHaveBeenCalledWith("/api/admin/users/5/role", { target_role: "student", reason: "转班" });
  });

  it("changeUserStatus POST /{id}/status body {status, yn}", async () => {
    mockPost.mockResolvedValueOnce({ updated: true, user_id: 5, status: 0, yn: 0 });
    await changeUserStatus(5, { status: 0, yn: 0 });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/users/5/status", { status: 0, yn: 0 });
  });

  it("最后 1 个 admin 降级被拒（40303）→ 抛 ApiError 壳（调用方 toast 明确提示）", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(403, { code: 40303, message: "至少保留 1 名可用管理员账号" }));
    await expect(changeUserRole(1, "student")).rejects.toMatchObject({
      status: 403,
      code: 40303,
      message: "至少保留 1 名可用管理员账号",
    });
  });
});

describe("dashboard metrics", () => {
  it("GET /api/admin/users/dashboard/metrics 返回 6 项指标", async () => {
    mockGet.mockResolvedValueOnce({
      total_user_count: 100,
      active_user_count_7d: 42,
      role_breakdown: { admin: 1, manager: 2, teacher: 3, student: 94 },
      disabled_user_count: 5,
      new_register_count_7d: 12,
      avg_login_days_per_user_30d: 3.5,
    });
    const m = await getDashboardMetrics();
    expect(mockGet).toHaveBeenCalledWith("/api/admin/users/dashboard/metrics", { params: undefined });
    expect(m.total_user_count).toBe(100);
    expect(m.role_breakdown.student).toBe(94);
    expect(m.avg_login_days_per_user_30d).toBeCloseTo(3.5);
  });

  it("metrics 失败必须抛（500）", async () => {
    mockGet.mockRejectedValueOnce(new ApiError(500, { code: 50000, message: "INTERNAL" }));
    await expect(getDashboardMetrics()).rejects.toMatchObject({ status: 500 });
  });
});

describe("显示辅助", () => {
  it("userRoleLabel 中文映射", () => {
    expect(userRoleLabel("admin")).toBe("管理员");
    expect(userRoleLabel("student")).toBe("学员");
    expect(userRoleLabel("x")).toBe("x");
  });

  it("userDisplayName 优先级 real_name > username > email > 用户#id", () => {
    expect(userDisplayName({ user_id: 1, real_name: "张三", username: "zhang", email: "a@b.c", role_code: "student", status: 1, yn: 1, created_at: "", updated_at: "" })).toBe("张三");
    expect(userDisplayName({ user_id: 2, username: "li", email: "a@b.c", role_code: "student", status: 1, yn: 1, created_at: "", updated_at: "" })).toBe("li");
    expect(userDisplayName({ user_id: 3, email: "a@b.c", role_code: "student", status: 1, yn: 1, created_at: "", updated_at: "" })).toBe("a@b.c");
    expect(userDisplayName({ user_id: 4, role_code: "student", status: 1, yn: 1, created_at: "", updated_at: "" })).toBe("用户#4");
  });
});
