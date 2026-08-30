/**
 * EditUserDialog 单测（task60 /admin/users 重构）
 *  - 角色切换   → POST /users/{id}/role  {target_role, reason}
 *  - 状态切换   → POST /users/{id}/status {status, yn, reason}
 *  - 最后 1 个可用 admin 红线：降级/禁用/保存全禁用 + 红线条幅（前端禁用 + 提示）
 *  - 后端 40303 拒绝（非红线场景后端兜底）：由全局 MutationCache onError → toast（task37 差异单②）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import { http, ApiError } from "@/lib/api-client";
import { globalMutationError } from "@/lib/query-client";
import { EditUserDialog } from "./EditUserDialog";
import type { AdminUserItem } from "@/lib/api/admin/users";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockPost = vi.mocked(http.post);

const ADMIN: AdminUserItem = {
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
};

const STU: AdminUserItem = {
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
};

function renderDialog(user: AdminUserItem, lastAdmin: boolean) {
  // 接入真实全局 MutationCache onError（task37 差异单②）：401/403 由全局统一 toast，组件级零补偿
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
    mutationCache: new MutationCache({ onError: globalMutationError }),
  });
  const onOpenChange = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <EditUserDialog user={user} lastAdmin={lastAdmin} open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("EditUserDialog", () => {
  it("渲染角色/状态/reason/保存控件（默认值来自 user）", () => {
    renderDialog(STU, false);
    expect(screen.getByTestId("edit-role")).toBeInTheDocument();
    expect(screen.getByTestId("edit-role")).toHaveValue("student");
    expect(screen.getByTestId("edit-reason")).toBeInTheDocument();
    expect(screen.getByTestId("edit-save")).toBeInTheDocument();
    expect(screen.getByText("编辑用户 · 小明")).toBeInTheDocument();
  });

  it("角色切换 student→teacher → POST /users/2/role {target_role:teacher}", async () => {
    mockPost.mockResolvedValueOnce({ updated: true, user_id: 2, target_role: "teacher" });
    renderDialog(STU, false);
    const select = screen.getByTestId("edit-role") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "teacher" } });
    fireEvent.click(screen.getByTestId("edit-save"));
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/admin/users/2/role", {
        target_role: "teacher",
        reason: undefined,
      });
    });
  });

  it("状态禁用 → POST /users/2/status {status:0, yn:0}", async () => {
    mockPost.mockResolvedValueOnce({ updated: true, user_id: 2, status: 0, yn: 0 });
    renderDialog(STU, false);
    fireEvent.click(screen.getByRole("button", { name: "禁用" }));
    fireEvent.click(screen.getByTestId("edit-save"));
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/admin/users/2/status", {
        status: 0,
        yn: 0,
      });
    });
  });

  it("最后 1 个可用 admin：降级(角色选择)/禁用/保存全禁用 + 红线条幅提示", () => {
    renderDialog(ADMIN, true);
    expect(screen.getByTestId("edit-role")).toBeDisabled();
    expect(screen.getByRole("button", { name: "禁用" })).toBeDisabled();
    expect(screen.getByTestId("edit-save")).toBeDisabled();
    expect(screen.getByText("红线保护")).toBeInTheDocument();
    // 未做任何变更时保存本就不应可点（红线豁免环）
    expect(screen.getByTestId("edit-save")).toBeDisabled();
  });

  it("后端 40303 兜底拒绝（非红线场景）→ 全局 MutationCache onError 单次 toast，无组件级双弹", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(403, { code: 40303, message: "至少保留 1 名可用管理员账号" }));
    const toastSpy = vi.spyOn(toast, "error");
    renderDialog(ADMIN, false);
    const select = screen.getByTestId("edit-role") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "student" } });
    fireEvent.click(screen.getByTestId("edit-save"));
    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("至少保留 1 名可用管理员账号", expect.anything());
    });
    // 全局 MutationCache 兜底：恰好一次，组件级无重复补偿
    expect(toastSpy).toHaveBeenCalledTimes(1);
  });

  it("登录失效 401 → 全局 MutationCache onError 单次 toast", async () => {
    mockPost.mockRejectedValueOnce(new ApiError(401, { code: 40111, message: "登录已过期" }));
    const toastSpy = vi.spyOn(toast, "error");
    renderDialog(STU, false);
    const select = screen.getByTestId("edit-role") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "teacher" } });
    fireEvent.click(screen.getByTestId("edit-save"));
    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("登录已过期", expect.anything());
    });
    expect(toastSpy).toHaveBeenCalledTimes(1);
  });
});