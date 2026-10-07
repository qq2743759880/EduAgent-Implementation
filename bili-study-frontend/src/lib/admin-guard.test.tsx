/**
 * admin-guard.tsx 单测（task02 验收：student 拦截 + toast + 重定向；未登录 302 登录页且回跳；
 * 2026-08-12 对抗修正 #2：后端 /api/admin/* 全部 ADMIN-only，manager 同样拦截）
 *
 * mock 策略：
 *  - next/navigation：固定 pathname="/admin/dashboard"，router.replace 记录调用
 *  - sonner：toast.warning / toast.error 记录调用
 *  - @/lib/auth-client：用真实 zustand store（支持 selector 与 setState），逐用例切换登录态/角色
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AdminGuard } from "./admin-guard";

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

const CHILD_TEXT = "admin-page-content";

function renderGuard() {
  return render(
    <AdminGuard>
      <div>{CHILD_TEXT}</div>
    </AdminGuard>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  setAuth({ ready: false, token: null, me: null });
});

describe("AdminGuard 校验占位（无白屏）", () => {
  it("hydrate 未完成：显示校验占位，不渲染 children，不跳转", () => {
    setAuth({ ready: false });
    renderGuard();
    expect(screen.getByText("正在校验登录状态…")).toBeInTheDocument();
    expect(screen.queryByText(CHILD_TEXT)).not.toBeInTheDocument();
    expect(routerMock.replace).not.toHaveBeenCalled();
  });
});

describe("AdminGuard 未登录", () => {
  it("跳登录页并带 redirect=当前 URL（回跳），toast 提示请先登录", () => {
    setAuth({ ready: true, token: null, me: null });
    renderGuard();

    expect(screen.queryByText(CHILD_TEXT)).not.toBeInTheDocument();
    expect(toastMock.warning).toHaveBeenCalledWith("请先登录");
    // /admin/dashboard → /login?redirect=%2Fadmin%2Fdashboard
    expect(routerMock.replace).toHaveBeenCalledTimes(1);
    expect(routerMock.replace).toHaveBeenCalledWith("/login?redirect=%2Fadmin%2Fdashboard");
  });
});

describe("AdminGuard 角色拦截", () => {
  it("student：toast 无权限 + 重定向回用户端 /dashboard，不渲染管理端内容", () => {
    setAuth({ ready: true, token: "token-x", me: { id: 1, nickname: "小明", email: "s@x.com", roles: ["student"] } });
    renderGuard();

    expect(screen.queryByText(CHILD_TEXT)).not.toBeInTheDocument();
    expect(toastMock.error).toHaveBeenCalledWith("无权限访问管理端");
    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });

  it("teacher：同样被拦截", () => {
    setAuth({ ready: true, token: "token-x", me: { roles: ["teacher"] } });
    renderGuard();
    expect(toastMock.error).toHaveBeenCalledWith("无权限访问管理端");
    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });

  it("manager：同样被拦截（后端 /api/admin/* 全部 ADMIN-only，实测 manager 403，对抗 #2）", () => {
    setAuth({ ready: true, token: "token-x", me: { roles: ["manager"] } });
    renderGuard();
    expect(screen.queryByText(CHILD_TEXT)).not.toBeInTheDocument();
    expect(toastMock.error).toHaveBeenCalledWith("无权限访问管理端");
    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });

  it("无 roles 字段（未知角色）：按非管理端拦截", () => {
    setAuth({ ready: true, token: "token-x", me: { id: 1, nickname: "x", email: "x@x.com" } });
    renderGuard();
    expect(toastMock.error).toHaveBeenCalledWith("无权限访问管理端");
  });
});

describe("AdminGuard 放行（RBAC 仅 admin）", () => {
  it("admin：渲染 children，无 toast，无跳转", () => {
    setAuth({ ready: true, token: "token-x", me: { roles: ["admin"] } });
    renderGuard();
    expect(screen.getByText(CHILD_TEXT)).toBeInTheDocument();
    expect(toastMock.error).not.toHaveBeenCalled();
    expect(toastMock.warning).not.toHaveBeenCalled();
    expect(routerMock.replace).not.toHaveBeenCalled();
  });

  it("roles 大小写不敏感（ADMIN）：放行", () => {
    setAuth({ ready: true, token: "token-x", me: { roles: ["ADMIN"] } });
    renderGuard();
    expect(screen.getByText(CHILD_TEXT)).toBeInTheDocument();
  });
});
