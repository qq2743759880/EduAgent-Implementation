/**
 * LoginForm 重定向单测（task69 · task42 批判②「redirect 含 query 深层路由回跳」）
 *
 * 验证 /login?redirect=/admin/users?page=2 → 登录成功后 router.replace 原样保留完整
 * 路径+query（不仅仅是 path），且恶意/非法 redirect 被 isSafeRedirect 拒回 /dashboard。
 * 以组件级断言替代 Playwright（已被项目禁用）。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { routerMock, toastMock } = vi.hoisted(() => ({
  routerMock: { replace: vi.fn(), refresh: vi.fn() },
  toastMock: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));

let currentRedirect = "/admin/users?page=2";

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  useSearchParams: () => new URLSearchParams(currentRedirect ? `redirect=${encodeURIComponent(currentRedirect)}` : ""),
}));

vi.mock("sonner", () => ({ toast: toastMock }));

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

import { http } from "@/lib/api-client";
import { LoginForm } from "./LoginForm";

const postMock = vi.mocked(http.post);

beforeEach(() => {
  vi.clearAllMocks();
});

async function loginAndSubmit() {
  render(<LoginForm />);
  await userEvent.type(screen.getByPlaceholderText(/输入账号/), "user000001");
  await userEvent.type(screen.getByPlaceholderText(/6 位以上/), "Test@123456");
  await userEvent.click(screen.getByRole("button", { name: "登录" }));
}

describe("LoginForm · redirect 含 query 深层路由回跳（task42 批判②）", () => {
  it("redirect=/admin/users?page=2 → 登录成功完整回跳（query 保留）", async () => {
    postMock.mockResolvedValueOnce({
      access_token: "access-jwt",
      refresh_token: "refresh-jwt",
      user: { user_id: 90001, username: "user000001", role: "student" },
    } as never);

    await loginAndSubmit();

    expect(postMock).toHaveBeenCalled();
    expect(routerMock.replace).toHaveBeenCalledWith("/admin/users?page=2");
  });

  it("不带 redirect → 默认回跳 /dashboard", async () => {
    currentRedirect = "";
    postMock.mockResolvedValueOnce({
      access_token: "access-jwt",
      refresh_token: "refresh-jwt",
      user: { user_id: 90001, username: "user000001", role: "student" },
    } as never);

    await loginAndSubmit();

    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });

  it("非法 redirect（协议相对 //evil.com）→ 拒回 /dashboard，不拼接外部地址", async () => {
    currentRedirect = "//evil.com";
    postMock.mockResolvedValueOnce({
      access_token: "access-jwt",
      refresh_token: "refresh-jwt",
      user: { user_id: 90001, username: "user000001", role: "student" },
    } as never);

    await loginAndSubmit();

    expect(routerMock.replace).toHaveBeenCalledWith("/dashboard");
  });
});