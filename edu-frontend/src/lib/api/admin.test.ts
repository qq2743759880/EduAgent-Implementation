/**
 * api/admin.ts 单测（task02 验收 / task40 拦截器解包迁移）
 * admin API 请求失败（403/500）→ 错误按 {code, message, detail} 壳透出，不静默吞
 *
 * 策略：保留真实 ApiError 类（importOriginal 部分注入），仅 mock http 辅助方法；
 * 契约冻结①后 http.* 调用结果即业务数据本体（无 {data: X} 解包），
 * 验证骨架把后端 {code,message,detail} 壳原样透传给调用方。
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { http, ApiError } from "@/lib/api-client";
import {
  adminDelete,
  adminGet,
  adminPatch,
  adminPost,
  toAdminErrorBody,
} from "./admin";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);
const mockPatch = vi.mocked(http.patch);
const mockDelete = vi.mocked(http.delete);

/** 构造后端标准错误壳：{code, message, detail}（如 403 RAG_FORBIDDEN / 500 内部错误） */
function makeApiError(status: number, code: number, message: string, detail?: unknown) {
  return new ApiError(status, { code, message, detail });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("adminGet（列表/详情）", () => {
  it("query params 传给 axios（分页参数透传）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 20, items: [] });
    await adminGet("/api/admin/users", { page: 1, page_size: 20, role_code: "admin" });
    expect(mockGet).toHaveBeenCalledWith("/api/admin/users", {
      params: { page: 1, page_size: 20, role_code: "admin" },
    });
  });

  it("403 → 抛 ApiError，code/message/detail 壳透出，不吞错", async () => {
    const err = makeApiError(403, 40300, "FORBIDDEN", { reason: "role" });
    mockGet.mockRejectedValueOnce(err);
    await expect(adminGet("/api/admin/users")).rejects.toMatchObject({
      status: 403,
      code: 40300,
      message: "FORBIDDEN",
      detail: { reason: "role" },
    });
  });

  it("500 → 抛 ApiError，message 来自后端壳", async () => {
    const err = makeApiError(500, 50000, "INTERNAL_SERVER_ERROR", "db down");
    mockGet.mockRejectedValueOnce(err);
    await expect(adminGet("/api/admin/users/dashboard/metrics")).rejects.toMatchObject({
      status: 500,
      code: 50000,
      message: "INTERNAL_SERVER_ERROR",
      detail: "db down",
    });
  });
});

describe("写操作（adminPost/adminPatch/adminDelete）", () => {
  it("POST 成功返回数据", async () => {
    mockPost.mockResolvedValueOnce({ ok: true });
    const resp = await adminPost("/api/admin/courses/series", { name: "x" });
    expect(mockPost).toHaveBeenCalledWith("/api/admin/courses/series", { name: "x" });
    expect(resp).toEqual({ ok: true });
  });

  it("POST 失败必须抛（不静默吞错，由调用方 toast）", async () => {
    mockPost.mockRejectedValueOnce(makeApiError(403, 40300, "FORBIDDEN"));
    await expect(adminPost("/api/admin/courses/series", {})).rejects.toMatchObject({
      status: 403,
      code: 40300,
    });
  });

  it("PATCH 失败必须抛", async () => {
    mockPatch.mockRejectedValueOnce(makeApiError(500, 50000, "INTERNAL_SERVER_ERROR"));
    await expect(adminPatch("/api/admin/questions/1", {})).rejects.toMatchObject({
      status: 500,
      code: 50000,
    });
  });

  it("DELETE 失败必须抛", async () => {
    mockDelete.mockRejectedValueOnce(makeApiError(403, 40300, "FORBIDDEN"));
    await expect(adminDelete("/api/admin/questions/1")).rejects.toMatchObject({
      status: 403,
      code: 40300,
    });
  });
});

describe("toAdminErrorBody（{code,message,detail} 壳归一）", () => {
  it("ApiError → 四字段壳", () => {
    const body = toAdminErrorBody(makeApiError(403, 40300, "无权限", { need: "admin" }));
    expect(body).toEqual({
      status: 403,
      code: 40300,
      message: "无权限",
      detail: { need: "admin" },
    });
  });

  it("ApiError status=0（网络错误）→ 明确网络文案，不伪装成 500（对抗 #5）", () => {
    const body = toAdminErrorBody(
      new ApiError(0, { code: 0, message: "网络错误，无法连接后端服务，请检查网络" }),
    );
    expect(body).toEqual({
      status: 0,
      code: 0,
      message: "网络错误，无法连接后端服务，请检查网络",
      detail: undefined,
    });
  });

  it("普通 Error → status/code 为 0，message 保留", () => {
    expect(toAdminErrorBody(new Error("Network Error"))).toEqual({
      status: 0,
      code: 0,
      message: "Network Error",
      detail: undefined,
    });
  });

  it("未知值 → status=0 + 网络错误文案兜底", () => {
    expect(toAdminErrorBody("oops")).toMatchObject({
      status: 0,
      message: expect.stringContaining("网络错误"),
    });
  });
});
