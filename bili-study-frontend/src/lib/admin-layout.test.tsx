/**
 * (admin)/layout.tsx 单测（task02 验收：admin 访问管理端 → 侧边栏渲染 6 菜单；
 * 2026-08-12 对抗修正 #2：后端 /api/admin/* 全部 ADMIN-only，manager 被守卫拦截）
 *
 * 渲染真实 AdminLayout（含 AdminGuard + 侧边栏），按角色断言菜单可见性。
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AdminLayout from "@/app/(admin)/layout";

/** mock auth store 的最小状态形状 */
interface MockAuthState {
  ready: boolean;
  token: string | null;
  me: Record<string, unknown> | null;
  logout: () => void;
  isAuthenticated: () => boolean;
}

const { routerMock, toastMock } = vi.hoisted(() => ({
  routerMock: { replace: vi.fn(), refresh: vi.fn() },
  toastMock: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}));

const holder = vi.hoisted<{
  store: { setState: (partial: Partial<MockAuthState>) => void } | undefined;
}>(() => ({ store: undefined }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/dashboard",
  useRouter: () => routerMock,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("sonner", () => ({ toast: toastMock }));

vi.mock("@/lib/auth-client", async () => {
  const { create } = await import("zustand");
  const store = create<MockAuthState>(() => ({
    ready: false,
    token: null,
    me: null,
    logout: () => {},
    isAuthenticated: () => false,
  }));
  holder.store = store;
  return { useAuthStore: store };
});

function setAuth(partial: { ready?: boolean; token?: string | null; me?: Record<string, unknown> | null }) {
  holder.store!.setState({
    ready: partial.ready ?? false,
    token: partial.token ?? null,
    me: partial.me ?? null,
  });
}

const CHILD_TEXT = "admin-dashboard-placeholder";

function renderLayout() {
  return render(
    <AdminLayout>
      <div>{CHILD_TEXT}</div>
    </AdminLayout>,
  );
}

function getSidebar() {
  return screen.getByRole("complementary", { name: "管理端导航" });
}

beforeEach(() => {
  vi.clearAllMocks();
  setAuth({ ready: false, token: null, me: null });
});

describe("AdminLayout 侧边栏 RBAC 菜单过滤", () => {
  it("admin：渲染 6 个菜单（含 MCP），children 放行", () => {
    setAuth({ ready: true, token: "t", me: { id: 1, nickname: "Admin", email: "a@b.c", roles: ["admin"] } });
    renderLayout();

    const sidebar = getSidebar();
    // 品牌链接 + 6 菜单
    expect(within(sidebar).getAllByRole("link")).toHaveLength(7);
    for (const label of ["仪表盘", "课程", "题库", "用户", "RAG", "MCP"]) {
      expect(within(sidebar).getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText(CHILD_TEXT)).toBeInTheDocument();
  });

  it("manager：守卫拦截，不渲染侧边栏菜单，重定向回用户端（后端 ADMIN-only，对抗 #2）", () => {
    setAuth({ ready: true, token: "t", me: { id: 2, nickname: "Mgr", email: "m@b.c", roles: ["manager"] } });
    renderLayout();

    expect(screen.queryByRole("complementary", { name: "管理端导航" })).not.toBeInTheDocument();
    expect(screen.queryByText(CHILD_TEXT)).not.toBeInTheDocument();
    expect(toastMock.error).toHaveBeenCalledWith("无权限访问管理端");
    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });

  it("student：守卫拦截，不渲染侧边栏菜单，重定向回用户端", () => {
    setAuth({ ready: true, token: "t", me: { id: 3, nickname: "S", email: "s@b.c", roles: ["student"] } });
    renderLayout();

    expect(screen.queryByRole("complementary", { name: "管理端导航" })).not.toBeInTheDocument();
    expect(screen.queryByText(CHILD_TEXT)).not.toBeInTheDocument();
    expect(toastMock.error).toHaveBeenCalledWith("无权限访问管理端");
    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });

  it("未登录：不渲染管理端内容，跳登录页带 redirect", () => {
    setAuth({ ready: true, token: null, me: null });
    renderLayout();

    expect(screen.queryByText(CHILD_TEXT)).not.toBeInTheDocument();
    expect(toastMock.warning).toHaveBeenCalledWith("请先登录");
    expect(routerMock.replace).toHaveBeenCalledWith("/login?redirect=%2Fadmin%2Fdashboard");
  });
});
