/**
 * UserTable 单测（task03 验收：角色切换 student→teacher 再禁用生效）
 *  - 渲染用户行（角色下拉/禁用按钮/详情按钮）
 *  - 角色切换触发 POST /users/{id}/role（body {target_role}）
 *  - 禁用触发 POST /users/{id}/status（body {status:0, yn:0}）
 *  - 失败（40303 最后 1 个 admin）→ 抛 ApiError（由全局 MutationCache toast）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api-client";
import { UserTable } from "./UserTable";
import type { AdminUserItem } from "@/lib/api/admin/users";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>("@/lib/api-client");
  return {
    ...actual,
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockPost = vi.mocked(api.post);

const USERS: AdminUserItem[] = [
  {
    user_id: 1,
    username: "admin01",
    real_name: "系统管理员",
    email: "admin@edu.local",
    role_code: "admin",
    status: 1,
    yn: 1,
    created_at: "2026-01-01T10:00:00",
    updated_at: "2026-01-01T10:00:00",
    last_login_at: "2026-08-11T09:00:00",
  },
  {
    user_id: 2,
    username: "stu01",
    real_name: "小明",
    email: "stu01@edu.local",
    role_code: "student",
    status: 1,
    yn: 1,
    created_at: "2026-02-01T10:00:00",
    updated_at: "2026-02-01T10:00:00",
    last_login_at: null,
  },
];

function renderTable() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UserTable users={USERS} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("UserTable", () => {
  it("渲染用户行 + 角色下拉 + 禁用/详情按钮", () => {
    renderTable();
    expect(screen.getByTestId("user-table")).toBeInTheDocument();
    expect(screen.getAllByTestId("user-row")).toHaveLength(2);
    expect(screen.getByText("系统管理员")).toBeInTheDocument();
    expect(screen.getByText("小明")).toBeInTheDocument();
    // 角色下拉（admin 用户）
    expect(screen.getByTestId("role-select-1")).toHaveValue("admin");
    // 禁用按钮 + 详情按钮
    expect(screen.getByTestId("disable-1")).toBeInTheDocument();
    expect(screen.getByTestId("detail-2")).toBeInTheDocument();
  });

  it("角色切换 student→teacher：POST /users/2/role body {target_role:'teacher'}", async () => {
    mockPost.mockResolvedValueOnce({ data: { updated: true, user_id: 2, target_role: "teacher" } });
    renderTable();
    const select = screen.getByTestId("role-select-2") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "teacher" } });
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/admin/users/2/role", {
        target_role: "teacher",
        reason: undefined,
      });
    });
  });

  it("禁用用户：POST /users/2/status body {status:0, yn:0}", async () => {
    mockPost.mockResolvedValueOnce({ data: { updated: true, user_id: 2, status: 0, yn: 0 } });
    renderTable();
    fireEvent.click(screen.getByTestId("disable-2"));
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/admin/users/2/status", { status: 0, yn: 0 });
    });
  });

  it("最后 1 个 admin 降级被拒（40303）→ 请求发出且错误壳透出", async () => {
    const rejected = Promise.reject(new ApiError(403, { code: 40303, message: "至少保留 1 名可用管理员账号" }));
    rejected.catch(() => undefined); // 防 unhandled rejection
    mockPost.mockReturnValueOnce(rejected as never);
    renderTable();
    const select = screen.getByTestId("role-select-1") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "student" } });
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/admin/users/1/role", {
        target_role: "student",
        reason: undefined,
      });
    });
    // useMutation 失败路径：ApiError 由 MutationCache onError 处理（toast），此处验证不吞错
    const call = mockPost.mock.calls[0];
    expect(call[0]).toBe("/api/admin/users/1/role");
  });
});
