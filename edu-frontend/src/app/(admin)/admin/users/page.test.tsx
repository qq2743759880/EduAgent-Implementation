/**
 * /admin/users 页面测试（task60，契约⑤ 用户域）
 *  - GWT① 关键词输入防抖 400ms 后才触发带 keyword 的查询
 *  - 角色/状态组合查询透传 refetch；分页 >1 页时分页可用
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminUsersPage from "./page";
import { listUsers, type AdminUserItem } from "@/lib/api/admin/users";
import type { AdminPage } from "@/lib/admin-api-types";

vi.mock("@/lib/api/admin/users", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/admin/users")>();
  return {
    ...actual,
    listUsers: vi.fn(),
  };
});

const listUsersMock = vi.mocked(listUsers);

const USERS: AdminUserItem[] = Array.from({ length: 10 }, (_, i) => ({
  user_id: i + 1,
  username: `user${i + 1}`,
  real_name: `用户${i + 1}`,
  email: `u${i + 1}@edu.local`,
  phone: null,
  role_code: "student",
  status: 1,
  yn: 1,
  created_at: "2026-01-01T10:00:00",
  updated_at: "2026-01-01T10:00:00",
  last_login_at: null,
}));

function usersPage(items: AdminUserItem[], total = items.length): AdminPage<AdminUserItem> {
  return { total, page: 1, page_size: 10, items };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AdminUsersPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listUsersMock.mockResolvedValue(usersPage(USERS));
});

afterEach(() => vi.restoreAllMocks());

describe("AdminUsersPage", () => {
  it("初始加载渲染用户表（GET /api/admin/users，page_size 10）", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("user-table")).toBeInTheDocument());
    expect(listUsersMock).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, page_size: 10 }),
    );
    await waitFor(() => expect(screen.getAllByTestId("user-row")).toHaveLength(10));
  });

  it("关键词输入防抖 400ms：窗口期内不触发，400ms 后触发带 keyword 查询", async () => {
    renderPage();
    await waitFor(() => expect(listUsersMock).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText(/关键词/), { target: { value: "小" } });

    // 防抖窗口内（250ms < 400ms）不应发起带 keyword 的查询
    await act(async () => {
      await new Promise((r) => setTimeout(r, 250));
    });
    expect(listUsersMock.mock.calls.filter((c) => c[0]?.keyword)).toHaveLength(0);

    // 400ms 后触发
    await waitFor(
      () => expect(listUsersMock).toHaveBeenLastCalledWith(expect.objectContaining({ keyword: "小" })),
      { timeout: 2000 },
    );
  });

  it("角色筛选 + 分页：切换角色触发 role_code 查询；多页时翻页触发 page 查询", async () => {
    listUsersMock.mockResolvedValue(usersPage(USERS, 25));
    renderPage();
    await waitFor(() => expect(screen.getAllByTestId("user-row")).toHaveLength(10));

    // 角色筛选
    fireEvent.change(screen.getByLabelText(/角色/), { target: { value: "teacher" } });
    await waitFor(() =>
      expect(listUsersMock).toHaveBeenLastCalledWith(expect.objectContaining({ role_code: "teacher", page: 1 })),
    );

    // 分页：总 25 条 / 每页 10 → 3 页；点击第 2 页
    const page2 = screen.getByRole("button", { name: "2" });
    expect(page2).toBeInTheDocument();
    fireEvent.click(page2);
    await waitFor(() =>
      expect(listUsersMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, role_code: "teacher" })),
    );
  });
});