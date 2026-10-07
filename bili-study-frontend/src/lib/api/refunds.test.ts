/**
 * refunds.ts API 封装单测（task100 Season-2：退款契约）
 * 覆盖：申请退款、我的退款列表（status 过滤）、撤销退款。
 * 退款类型/状态均为后端权威枚举（不出现缩略值）。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { http } from "@/lib/api-client";
import {
  cancelRefund,
  createRefund,
  listRefunds,
  REFUND_TYPE_OPTIONS,
  type Refund,
} from "./refunds";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);

function makeRefund(overrides: Partial<Refund> = {}): Refund {
  return {
    id: 7,
    refund_no: "RF2026081300001",
    order_no: "E20260813000001",
    refund_type: "personal_reason",
    refund_status: "pending",
    apply_amount: 2799,
    approved_amount: null,
    refund_reason: "个人原因申请退款",
    remark: null,
    approver_user_id: null,
    applied_at: "2026-08-13T09:12:00",
    approved_at: null,
    refunded_at: null,
    created_at: "2026-08-13T09:12:00",
    cancelled: false,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("createRefund（申请退款）", () => {
  it("body 字段透传（金额后端强制校验，前端透传 apply_amount）", async () => {
    mockPost.mockResolvedValueOnce(makeRefund({ refund_status: "pending" }));
    await createRefund({
      order_no: "E20260813000001",
      refund_type: "course_unsatisfied",
      apply_amount: 2799,
      reason: "课程内容与预期不符",
    });
    expect(mockPost).toHaveBeenCalledWith("/api/refunds", {
      order_no: "E20260813000001",
      refund_type: "course_unsatisfied",
      apply_amount: 2799,
      reason: "课程内容与预期不符",
    });
  });

  it("重复购买类型（枚举防漂移）", async () => {
    mockPost.mockResolvedValueOnce(makeRefund());
    await createRefund({
      order_no: "E20260813000001",
      refund_type: "duplicate_purchase",
      apply_amount: 100,
      reason: "误下重复单",
    });
    expect(mockPost).toHaveBeenCalledWith("/api/refunds", {
      order_no: "E20260813000001",
      refund_type: "duplicate_purchase",
      apply_amount: 100,
      reason: "误下重复单",
    });
  });

  it("创建失败向上抛（不吞错）", async () => {
    mockPost.mockRejectedValueOnce(new Error("退款金额超出实付"));
    await expect(
      createRefund({ order_no: "x", refund_type: "personal_reason", apply_amount: 9999, reason: "r" }),
    ).rejects.toThrow("退款金额超出实付");
  });
});

describe("listRefunds（我的退款）", () => {
  it("默认分页参数透传", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 100, items: [] });
    await listRefunds({ page: 1, page_size: 100 });
    expect(mockGet).toHaveBeenCalledWith("/api/refunds", {
      params: { page: 1, page_size: 100 },
    });
  });

  it("status 过滤传后端权威枚举", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listRefunds({ status: "approved", page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/refunds", {
      params: { status: "approved", page: 1, page_size: 20 },
    });
  });
});

describe("cancelRefund（撤销退款，仅 pending）", () => {
  it("按 id 撤销走 POST /api/refunds/{id}/cancel", async () => {
    mockPost.mockResolvedValueOnce({ cancelled: true, refund_no: "RF2026081300001" });
    const resp = await cancelRefund(7);
    expect(mockPost).toHaveBeenCalledWith("/api/refunds/7/cancel");
    expect(resp.cancelled).toBe(true);
  });
});

describe("REFUND_TYPE_OPTIONS（UI 下拉数据单源）", () => {
  it("四个权威退款类型均在选项内", () => {
    const values = REFUND_TYPE_OPTIONS.map((o) => o.value).sort();
    expect(values).toEqual(
      [
        "personal_reason",
        "course_unsatisfied",
        "schedule_conflict",
        "duplicate_purchase",
      ].sort(),
    );
  });
});