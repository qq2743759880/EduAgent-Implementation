/**
 * MutationCache/QueryCache onError 契约测试（task37 差异单②）
 *
 * 目标：401/403 在「全局 MutationCache」与「组件级」均正确提示，且无重复双弹。
 *  - globalMutationError（MutationCache）：写操作 401/403 统一 toast，不再早退静默；
 *  - globalQueryError（QueryCache）：读操作 401/403 保持静默（api-client onApiUnauthorized
 *    已负责清 token + 跳登录/守卫），仅非认证错误 toast —— 避免加载场景重复 toast 噪声。
 */
import { describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { ApiError } from "./api-client";
import { globalMutationError, globalQueryError, createQueryClient } from "./query-client";

function toastErrorSpy() {
  return vi.spyOn(toast, "error");
}

describe("globalMutationError（写操作 → 统一 toast）", () => {
  it("401 → toast.error 一次（不再早退静默）", () => {
    const spy = toastErrorSpy();
    globalMutationError(new ApiError(401, { code: 40111, message: "登录已过期" }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("登录已过期", expect.anything());
  });

  it("403 → toast.error 一次（无权限/红线兜底可见提示）", () => {
    const spy = toastErrorSpy();
    globalMutationError(new ApiError(403, { code: 40303, message: "至少保留 1 名可用管理员账号" }));
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("至少保留 1 名可用管理员账号", expect.anything());
  });

  it("403 带 detail → message + description 均透传", () => {
    const spy = toastErrorSpy();
    globalMutationError(new ApiError(403, { code: 40302, message: "操作被拒绝", detail: "非本班任课教师" }));
    expect(spy).toHaveBeenCalledWith("操作被拒绝", { description: "非本班任课教师" });
  });

  it("非认证状态码（409）→ 仍统一 toast", () => {
    const spy = toastErrorSpy();
    globalMutationError(new ApiError(409, { code: 40901, message: "名称冲突" }));
    expect(spy).toHaveBeenCalledWith("名称冲突", expect.anything());
  });
});

describe("globalQueryError（读操作 → 401/403 静默，其余 toast）", () => {
  it("401 → 不 toast（onApiUnauthorized 已负责清 token + 跳登录）", () => {
    const spy = toastErrorSpy();
    globalQueryError(new ApiError(401, { code: 40111, message: "登录已过期" }));
    expect(spy).not.toHaveBeenCalled();
  });

  it("403 → 不 toast（管理员守卫负责无权限跳转）", () => {
    const spy = toastErrorSpy();
    globalQueryError(new ApiError(403, { code: 40300, message: "无权限" }));
    expect(spy).not.toHaveBeenCalled();
  });

  it("500 → toast", () => {
    const spy = toastErrorSpy();
    globalQueryError(new ApiError(500, { code: "50000", message: "服务内部错误" }));
    expect(spy).toHaveBeenCalledWith("服务内部错误", expect.anything());
  });
});

describe("createQueryClient 端到端接线契约", () => {
  it("真实触发 mutation → 401 全局单次 toast（生产路径与单测一致）", async () => {
    const qc = createQueryClient();
    const spy = toastErrorSpy();
    const mut = qc.getMutationCache().build(qc, {
      mutationFn: () => Promise.reject(new ApiError(401, { code: 40111, message: "登录已过期" })),
    });
    await expect(mut.execute({})).rejects.toMatchObject({ status: 401 });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("登录已过期", expect.anything());
  });

  it("真实触发 mutation → 403 全局单次 toast（红线兜底可见提示）", async () => {
    const qc = createQueryClient();
    const spy = toastErrorSpy();
    const mut = qc.getMutationCache().build(qc, {
      mutationFn: () =>
        Promise.reject(new ApiError(403, { code: 40303, message: "至少保留 1 名可用管理员账号" })),
    });
    await expect(mut.execute({})).rejects.toMatchObject({ status: 403 });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("至少保留 1 名可用管理员账号", expect.anything());
  });
});