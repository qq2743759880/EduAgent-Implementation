/**
 * UserTable 单测（task60 /admin/users 重构）
 *  - 渲染用户行（头像/姓名/角色徽章/状态/查看/编辑按钮）
 *  - 最后 1 个可用 admin 红线：行内「最后admin」徽章；多个有效 admin 时不标记
 *  - 「查看」打开学习详情 Dialog；端点未注册（后端无 GET /learning，实测 404）→ 契约缺口
 *    如实披露（非 MOCK），且不发必 404 死请求（W-NEXT-FEBE-SCAN-002 删死调用）
 *  - 角色/状态写操作已收敛至 EditUserDialog（见 EditUserDialog.test.tsx）
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http } from "@/lib/api-client";
import { UserTable } from "./UserTable";
import type { AdminUserItem } from "@/lib/api/admin/users";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const base = (overrides: Partial<AdminUserItem>): AdminUserItem => ({
  user_id: 1,
  username: "u",
  real_name: "名",
  email: "e@edu.local",
  role_code: "student",
  status: 1,
  yn: 1,
  created_at: "2026-01-01T10:00:00",
  updated_at: "2026-01-01T10:00:00",
  last_login_at: null,
  ...overrides,
});

const ADMIN_ONLY = [
  base({ user_id: 1, username: "admin01", real_name: "系统管理员", role_code: "admin", last_login_at: "2026-08-11T09:00:00" }),
  base({ user_id: 2, username: "stu01", real_name: "小明", role_code: "student" }),
];

const TWO_ADMINS = [
  base({ user_id: 1, username: "admin01", real_name: "管理员甲", role_code: "admin" }),
  base({ user_id: 2, username: "admin02", real_name: "管理员乙", role_code: "admin" }),
  base({ user_id: 3, username: "stu01", real_name: "小明", role_code: "student" }),
];

function renderTable(users: AdminUserItem[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UserTable users={users} />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("UserTable", () => {
  it("渲染用户行 + 角色徽章 + 状态 + 查看/编辑按钮", () => {
    renderTable(ADMIN_ONLY);
    expect(screen.getByTestId("user-table")).toBeInTheDocument();
    expect(screen.getAllByTestId("user-row")).toHaveLength(2);
    expect(screen.getByText("系统管理员")).toBeInTheDocument();
    expect(screen.getByText("小明")).toBeInTheDocument();
    expect(screen.getByText("管理员")).toBeInTheDocument(); // admin 角色徽章
    expect(screen.getByText("学员")).toBeInTheDocument(); // student 角色徽章
    expect(screen.getByTestId("view-1")).toBeInTheDocument();
    expect(screen.getByTestId("edit-1")).toBeInTheDocument();
    expect(screen.getByTestId("view-2")).toBeInTheDocument();
  });

  it("最后 1 个可用 admin → 行内显示「最后admin」徽章", () => {
    renderTable(ADMIN_ONLY);
    expect(screen.getByText("最后admin")).toBeInTheDocument();
  });

  it("存在多个有效 admin 时不标记最后 admin", () => {
    renderTable(TWO_ADMINS);
    expect(screen.queryByText("最后admin")).not.toBeInTheDocument();
  });

  it("「禁用中」用户 → 状态徽章显示「已禁用」", () => {
    renderTable([base({ user_id: 9, real_name: "被禁用用户", role_code: "student", status: 0, yn: 0 })]);
    expect(screen.getByText("已禁用")).toBeInTheDocument();
  });

  it("点击「查看」打开学习详情；端点未注册 → 契约缺口实披露且不发必 404 死请求（W-NEXT-FEBE-SCAN-002）", async () => {
    const mockGet = vi.mocked(http.get);
    mockGet.mockClear();
    renderTable(ADMIN_ONLY);
    fireEvent.click(screen.getByTestId("view-2"));
    // 死调用已删除：GET /api/admin/users/{id}/learning 后端从未注册（实测 404 code 40400），
    // 弹窗直接渲染缺口占位（字段结构预览），不再发起注定失败的请求
    expect(mockGet).not.toHaveBeenCalled();
    expect(await screen.findByText(/契约缺口/)).toBeInTheDocument();
    expect(screen.getByText(/active_cohorts_count/)).toBeInTheDocument();
  });
});