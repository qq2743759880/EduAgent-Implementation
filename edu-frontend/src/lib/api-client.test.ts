/**
 * api-client.ts 单测（对抗 #5：断网/连接拒绝 status=0 不再伪装成 500）
 *
 * 策略：复用模块真实 axios 实例（拦截器已注册），仅覆盖 api.defaults.adapter
 * 抛无响应体的 AxiosError，断言最终 reject 为 ApiError 且 status=0 + 明确网络文案。
 */
import { AxiosError } from "axios";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { api, isAuthEndpoint, onApiUnauthorized } from "./api-client";

describe("响应拦截器：网络错误（无响应体）", () => {
  it("断网/连接拒绝（ERR_NETWORK）→ ApiError status=0 + 明确网络文案，不伪装 500", async () => {
    api.defaults.adapter = async () => {
      throw new AxiosError("Network Error", "ERR_NETWORK", undefined, {});
    };
    await expect(api.get("/api/admin/users")).rejects.toMatchObject({
      status: 0,
      code: 0,
      message: expect.stringContaining("无法连接"),
    });
  });

  it("请求超时（ECONNABORTED）→ status=0 + 超时文案", async () => {
    api.defaults.adapter = async () => {
      throw new AxiosError("timeout of 15000ms exceeded", "ECONNABORTED", undefined, {});
    };
    await expect(api.get("/api/admin/users")).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining("超时"),
    });
  });

  it("明确不是后端 500：status 不可能是 500", async () => {
    api.defaults.adapter = async () => {
      throw new AxiosError("Network Error", "ERR_NETWORK", undefined, {});
    };
    await expect(api.get("/api/admin/users")).rejects.toMatchObject({
      status: 0,
    });
  });
});

describe("isAuthEndpoint：认证类接口判定（task03 复测 #1 修复）", () => {
  it("登录接口 → true（含 query 参数防御）", () => {
    expect(isAuthEndpoint("/api/auth/login")).toBe(true);
    expect(isAuthEndpoint("/api/auth/login?tenant=1")).toBe(true);
  });

  it("注册接口 → true", () => {
    expect(isAuthEndpoint("/api/auth/register")).toBe(true);
  });

  it("业务接口 / me / 其他认证路径 → false（应走全局登出）", () => {
    expect(isAuthEndpoint("/api/admin/users")).toBe(false);
    expect(isAuthEndpoint("/api/auth/me")).toBe(false);
    expect(isAuthEndpoint("/api/auth/refresh")).toBe(false);
    expect(isAuthEndpoint("/api/courses")).toBe(false);
  });

  it("undefined / 空 → false", () => {
    expect(isAuthEndpoint(undefined)).toBe(false);
    expect(isAuthEndpoint("")).toBe(false);
  });
});

describe("响应拦截器：认证接口 401/403 不触发全局回调（task03 复测 #1 修复）", () => {
  const handler = vi.fn();
  let savedAdapter: typeof api.defaults.adapter;

  function httpError(
    url: string,
    status: 401 | 403,
    message: string,
    code: number,
  ): AxiosError {
    return new AxiosError(
      `Request failed with status code ${status}`,
      "ERR_BAD_REQUEST",
      { url } as never,
      {},
      {
        status,
        statusText: status === 401 ? "Unauthorized" : "Forbidden",
        headers: {},
        config: { url } as never,
        data: { code, message },
      },
    );
  }

  beforeAll(() => {
    savedAdapter = api.defaults.adapter;
    onApiUnauthorized(handler);
  });

  afterEach(() => {
    handler.mockClear();
  });

  afterAll(() => {
    /* 注销回调，避免污染同文件其他用例（空 handler 不产生副作用） */
    onApiUnauthorized(() => undefined);
    api.defaults.adapter = savedAdapter;
  });

  it("POST /api/auth/login 401（密码错误）→ 不触发全局回调，ApiError 保留 message", async () => {
    api.defaults.adapter = async () => {
      throw httpError("/api/auth/login", 401, "账号或密码错误", 40111);
    };
    await expect(api.post("/api/auth/login", { account: "x", password: "y" })).rejects.toMatchObject({
      status: 401,
      code: 40111,
      message: "账号或密码错误",
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it("POST /api/auth/login 403（账号禁用，40112）→ 不触发全局回调，交由 LoginForm 渲染 root.server 横幅", async () => {
    api.defaults.adapter = async () => {
      throw httpError("/api/auth/login", 403, "该账号已被禁用，请联系管理员", 40112);
    };
    await expect(api.post("/api/auth/login", { account: "x", password: "y" })).rejects.toMatchObject({
      status: 403,
      code: 40112,
      message: "该账号已被禁用，请联系管理员",
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it("POST /api/auth/register 401/403 → 不触发全局回调（注册表单原地渲染错误）", async () => {
    api.defaults.adapter = async () => {
      throw httpError("/api/auth/register", 401, "注册校验失败", 42200);
    };
    await expect(api.post("/api/auth/register", {})).rejects.toMatchObject({
      status: 401,
      message: "注册校验失败",
    });
    expect(handler).not.toHaveBeenCalled();
  });

  it("业务接口 401（token 过期）→ 仍触发全局回调（全局登出 + 跳 /login）", async () => {
    api.defaults.adapter = async () => {
      throw httpError("/api/admin/users", 401, "登录已过期，请重新登录", 40100);
    };
    await expect(api.get("/api/admin/users")).rejects.toMatchObject({
      status: 401,
      message: "登录已过期，请重新登录",
    });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(401);
  });

  it("业务接口 403（角色无权限）→ 仍触发全局回调", async () => {
    api.defaults.adapter = async () => {
      throw httpError("/api/admin/users", 403, "角色无权限", 40300);
    };
    await expect(api.get("/api/admin/users")).rejects.toMatchObject({
      status: 403,
    });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(403);
  });
});
