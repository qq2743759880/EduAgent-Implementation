/**
 * B3-impl 组件级测试（jsdom + 真实 refine 链路：页面 → EduRefineProvider → eduDataProvider → 桩 fetch）
 * 覆盖开工单要求的三个核心分支：manager 短路（横幅+不发列表请求）/ 40303 红线 / 窗口化分页，
 * 另补：ADMIN 正常列表 / 启停写路径 / 唯一 admin 前端拦截 / 空态。
 * 数据形状按 2026-09-12 curl 实测：裸 DTO {total,page,page_size,items}、错误壳 {code:"40303",message,data}。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within, configure } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { getEduQueryClient } from "@edu/refine-layer";
import type { AdminUserItem } from "@/lib/api/admin/users";
import UsersRefinePage from "./page";

// 本文件首测跑完整 refine 链（gate→auth/me→provider→list+metrics，多次桩 fetch），
// 全量套件并行负载下 1s 默认 waitFor 偶发不够，放宽本文件异步等待上限（suite testTimeout=20s 内）
configure({ asyncUtilTimeout: 8000 });

const { replaceMock, pushMock, toastWarning, toastError, toastSuccess } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  pushMock: vi.fn(),
  toastWarning: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: replaceMock, push: pushMock }) }));
vi.mock("sonner", () => ({ toast: { success: toastSuccess, error: toastError, warning: toastWarning } }));

/* ---------------- 桩 fetch：按 URL 路由 ---------------- */
type RouteResult = { status?: number; body: unknown };
let route: (url: string, init: RequestInit) => RouteResult | "unhandled" = () => "unhandled";
let calls: Array<{ url: string; init: RequestInit }> = [];

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input);
      calls.push({ url, init });
      const r = route(url, init);
      if (r === "unhandled") throw new Error("unhandled fetch: " + url);
      return new Response(JSON.stringify(r.body ?? null), {
        status: r.status ?? 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

const ok = (data: unknown): RouteResult => ({ status: 200, body: { code: 0, message: "ok", data } });

function user(i: number, over: Partial<AdminUserItem> = {}): AdminUserItem {
  return {
    user_id: i,
    username: `user${String(i).padStart(3, "0")}`,
    real_name: `用户${i}`,
    phone: null,
    email: `u${i}@edu.local`,
    role_code: "student",
    status: 1,
    yn: 1,
    created_at: "2026-01-01T10:00:00",
    updated_at: "2026-01-01T10:00:00",
    last_login_at: null,
    ...over,
  };
}

const listDto = (items: AdminUserItem[], total = items.length) => ({ total, page: 1, page_size: 10, items });

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UsersRefinePage />
    </QueryClientProvider>,
  );
}

const apiCalls = () => calls.filter((c) => new URL(c.url).pathname.startsWith("/api/admin/users"));
const listCalls = () => apiCalls().filter((c) => new URL(c.url).pathname === "/api/admin/users");

beforeEach(() => {
  vi.clearAllMocks();
  calls = [];
  getEduQueryClient().clear();
  localStorage.setItem("edu:auth:token", "t-refine-test");
  localStorage.setItem("edu:auth:refresh", "r-refine-test");
  stubFetch();
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("UsersRefinePage（Refine 版）", () => {
  it("ADMIN 正常态：走 refine dataProvider 拉列表（page=1&page_size=10）并渲染行", async () => {
    route = (url) => {
      const u = new URL(url);
      if (u.pathname === "/api/auth/me") return ok({ role: "admin" });
      if (u.pathname === "/api/admin/users/dashboard/metrics") return ok({ role_breakdown: { admin: 5 }, total_user_count: 100034 });
      if (u.pathname === "/api/admin/users") return ok(listDto([user(1), user(2, { role_code: "admin", username: "adm02test" })], 100034));
      return "unhandled";
    };
    renderPage();
    await waitFor(() => expect(screen.getAllByTestId("refine-user-row")).toHaveLength(2));
    const u = new URL(listCalls()[0].url);
    expect(u.searchParams.get("page")).toBe("1");
    expect(u.searchParams.get("page_size")).toBe("10");
    expect(screen.getByTestId("refine-total")).toHaveTextContent("共 100034 条 · 第 1/10004 页");
  });

  it("manager 短路：只读横幅 + 不发任何 /api/admin/users 请求（H2a/P1-9 请求前拦截）", async () => {
    route = (url) => (new URL(url).pathname === "/api/auth/me" ? ok({ role: "manager" }) : "unhandled");
    renderPage();
    await waitFor(() => expect(screen.getByTestId("refine-manager-banner")).toBeInTheDocument());
    expect(screen.getByTestId("refine-manager-banner")).toHaveTextContent("该模块仅 ADMIN 可用");
    expect(listCalls()).toHaveLength(0);
    expect(apiCalls()).toHaveLength(0);
  });

  it("窗口化分页：total=100034 时渲染首末页+省略号，翻页发 page=2 请求", async () => {
    route = (url) => {
      const u = new URL(url);
      if (u.pathname === "/api/auth/me") return ok({ role: "admin" });
      if (u.pathname === "/api/admin/users/dashboard/metrics") return ok({ role_breakdown: { admin: 5 }, total_user_count: 100034 });
      if (u.pathname === "/api/admin/users") return ok(listDto(Array.from({ length: 10 }, (_, i) => user(i + 1)), 100034));
      return "unhandled";
    };
    const usr = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getAllByTestId("refine-user-row")).toHaveLength(10));
    const nav = screen.getByRole("navigation", { name: "分页" });
    expect(within(nav).getByText("…")).toBeInTheDocument(); // 窗口化省略号
    expect(within(nav).getByText("10004")).toBeInTheDocument(); // 末页常驻
    expect(within(nav).getByText("2")).toBeInTheDocument();
    await usr.click(within(nav).getByText("2"));
    await waitFor(() => expect(listCalls().some((c) => new URL(c.url).searchParams.get("page") === "2")).toBe(true));
  });

  it("启停二次确认：确认后 POST /{id}/status body {status:0,yn:0} 并刷新列表", async () => {
    let statusCalls = 0;
    route = (url) => {
      const u = new URL(url);
      if (u.pathname === "/api/auth/me") return ok({ role: "admin" });
      if (u.pathname === "/api/admin/users/dashboard/metrics") return ok({ role_breakdown: { admin: 5 }, total_user_count: 100034 });
      if (u.pathname === "/api/admin/users") return ok(listDto([user(7)]));
      if (u.pathname === "/api/admin/users/7/status") {
        statusCalls += 1;
        return ok({ updated: true, user_id: 7, status: 0, yn: 0 });
      }
      return "unhandled";
    };
    const usr = userEvent.setup();
    renderPage();
    const row = await screen.findByTestId("refine-user-row");
    await usr.click(within(row).getByRole("button", { name: "禁用" }));
    await screen.findByText("确认禁用该账号？");
    await usr.click(screen.getByTestId("refine-confirm-status"));
    await waitFor(() => expect(statusCalls).toBe(1));
    const body = JSON.parse(String(calls.find((c) => c.url.endsWith("/api/admin/users/7/status"))?.init.body));
    expect(body).toEqual({ status: 0, yn: 0, reason: undefined });
    expect(toastSuccess).toHaveBeenCalledWith("已禁用该用户");
  });

  it("40303 红线：编辑降级 admin 被后端拒绝 → 红线条幅 + toast.error，保存禁用", async () => {
    route = (url) => {
      const u = new URL(url);
      if (u.pathname === "/api/auth/me") return ok({ role: "admin" });
      if (u.pathname === "/api/admin/users/dashboard/metrics") return ok({ role_breakdown: { admin: 5 }, total_user_count: 100034 });
      if (u.pathname === "/api/admin/users") return ok(listDto([user(5, { role_code: "admin", username: "adm02test" })]));
      if (u.pathname === "/api/admin/users/5/role") {
        return { status: 403, body: { code: "40303", message: "至少保留 1 名可用管理员账号", data: null } };
      }
      return "unhandled";
    };
    const usr = userEvent.setup();
    renderPage();
    const row = await screen.findByTestId("refine-user-row");
    await usr.click(within(row).getByRole("button", { name: "编辑" }));
    await screen.findByText(/编辑用户/);
    await usr.selectOptions(screen.getByLabelText("编辑角色"), "student");
    await usr.click(screen.getByTestId("refine-save-edit"));
    await waitFor(() => expect(screen.getByTestId("refine-redline")).toHaveTextContent("至少保留 1 名可用管理员账号"));
    expect(toastError).toHaveBeenCalledWith("至少保留 1 名可用管理员账号");
    expect(screen.getByTestId("refine-save-edit")).toBeDisabled(); // 40303 后禁用保存
  });

  it("唯一可用 admin（metrics admin=1）：降级/禁用前端先拦截（保存禁用+红线），不发请求", async () => {
    route = (url) => {
      const u = new URL(url);
      if (u.pathname === "/api/auth/me") return ok({ role: "admin" });
      if (u.pathname === "/api/admin/users/dashboard/metrics") return ok({ role_breakdown: { admin: 1 }, total_user_count: 100034 });
      if (u.pathname === "/api/admin/users") return ok(listDto([user(5, { role_code: "admin", username: "adm02test" })]));
      return "unhandled";
    };
    const usr = userEvent.setup();
    renderPage();
    // 等待 metrics 加载完成（adminCount 依赖 role_breakdown），再打开编辑弹窗
    await screen.findByText(/共 100034 位用户/);
    const row = await screen.findByTestId("refine-user-row");
    await usr.click(within(row).getByRole("button", { name: "编辑" }));
    await screen.findByText(/编辑用户/);
    await usr.selectOptions(screen.getByLabelText("编辑角色"), "student");
    expect(screen.getByTestId("refine-redline")).toHaveTextContent("唯一可用 admin");
    expect(screen.getByTestId("refine-save-edit")).toBeDisabled();
    expect(calls.filter((c) => c.init.method === "POST")).toHaveLength(0);
  });

  it("空态：组合查询 total=0 → 未匹配到用户", async () => {
    route = (url) => {
      const u = new URL(url);
      if (u.pathname === "/api/auth/me") return ok({ role: "admin" });
      if (u.pathname === "/api/admin/users/dashboard/metrics") return ok({ role_breakdown: { admin: 5 }, total_user_count: 100034 });
      if (u.pathname === "/api/admin/users") return ok(listDto([], 0));
      return "unhandled";
    };
    renderPage();
    await waitFor(() => expect(screen.getByText("未匹配到用户（组合查询为空/调整筛选）")).toBeInTheDocument());
    expect(screen.getByTestId("refine-total")).toHaveTextContent("共 0 条");
  });

  it("40300 兜底错误态：列表 403 → 展示 message + HTTP/code 载荷", async () => {
    route = (url) => {
      const u = new URL(url);
      if (u.pathname === "/api/auth/me") return ok({ role: "admin" });
      if (u.pathname === "/api/admin/users/dashboard/metrics") return ok({ role_breakdown: { admin: 5 }, total_user_count: 100034 });
      if (u.pathname === "/api/admin/users") {
        return { status: 403, body: { code: "40300", message: "角色无权限。当前角色=manager，允许角色=['admin']", data: null } };
      }
      return "unhandled";
    };
    renderPage();
    await waitFor(() => expect(screen.getByTestId("refine-error")).toBeInTheDocument());
    expect(screen.getByTestId("refine-error")).toHaveTextContent("角色无权限");
    expect(screen.getByTestId("refine-error")).toHaveTextContent("HTTP 403 · code 40300");
  });
});
