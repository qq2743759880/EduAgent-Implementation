/**
 * payments.ts API 封装单测（task100 Season-2：支付契约）
 * 覆盖：发起支付（线下转账 audit_pending 分支）、支付详情、列表、
 * 取消支付、重试支付。渠道/状态均为后端权威枚举。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { http } from "@/lib/api-client";
import {
  cancelPayment,
  getPayment,
  launchPayment,
  listPayments,
  retryPayment,
  type Payment,
} from "./payments";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);

function makePayment(overrides: Partial<Payment> = {}): Payment {
  return {
    payment_no: "P20260813",
    order_no: "E20260813000001",
    pay_amount: 2799,
    pay_channel: "mock",
    status: "pending",
    channel_trade_no: null,
    created_at: "2026-08-13T09:12:00",
    finished_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("launchPayment（发起支付）", () => {
  it("真实渠道（如 wechat_pay）正常发起，audit_pending=false", async () => {
    mockPost.mockResolvedValueOnce({
      payment_no: "P20260813",
      order_no: "E20260813000001",
      status: "pending",
      pay_url: "https://pay.example.com/wechat/...",
      qr_code_url: null,
      audit_pending: false,
    });
    const resp = await launchPayment("E20260813000001", { pay_channel: "wechat_pay" });
    expect(mockPost).toHaveBeenCalledWith("/api/trade/payment/E20260813000001", {
      pay_channel: "wechat_pay",
    });
    expect(resp.status).toBe("pending");
    expect(resp.audit_pending).toBe(false);
  });

  it("线下转账 → audit_pending=true（无即时回调，前端提示到账审核中）", async () => {
    mockPost.mockResolvedValueOnce({
      payment_no: "P20260813",
      order_no: "E20260813000001",
      status: "pending",
      pay_url: null,
      qr_code_url: null,
      audit_pending: true,
    });
    const resp = await launchPayment("E20260813000001", {
      pay_channel: "offline_transfer",
    });
    expect(resp.audit_pending).toBe(true);
    expect(resp.pay_url).toBeNull();
  });

  it("发起失败向上抛（不吞错）", async () => {
    mockPost.mockRejectedValueOnce(new Error("订单状态非法"));
    await expect(
      launchPayment("E20260813000001", { pay_channel: "mock" }),
    ).rejects.toThrow("订单状态非法");
  });
});

describe("getPayment（支付详情 / 轮询）", () => {
  it("按 payment_no 取详情", async () => {
    mockGet.mockResolvedValueOnce(makePayment({ status: "paid", finished_at: "2026-08-13T09:15:00" }));
    const resp = await getPayment("P20260813");
    expect(mockGet).toHaveBeenCalledWith("/api/trade/payment/P20260813");
    expect(resp.status).toBe("paid");
  });
});

describe("listPayments（支付分页）", () => {
  it("status + order_no 过滤透传", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listPayments({ status: "paid", order_no: "E20260813000001", page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/trade/payments", {
      params: { status: "paid", order_no: "E20260813000001", page: 1, page_size: 20 },
    });
  });
});

describe("cancelPayment / retryPayment（状态流转）", () => {
  it("取消支付（pending → closed）", async () => {
    mockPost.mockResolvedValueOnce({ cancelled: true, payment_no: "P20260813" });
    const resp = await cancelPayment("P20260813");
    expect(mockPost).toHaveBeenCalledWith("/api/trade/payment/P20260813/cancel");
    expect(resp.cancelled).toBe(true);
  });

  it("重试支付（closed/failed → pending），返回支付详情", async () => {
    mockPost.mockResolvedValueOnce(makePayment({ status: "pending" }));
    const resp = await retryPayment("P20260813");
    expect(mockPost).toHaveBeenCalledWith("/api/trade/payment/P20260813/retry");
    expect(resp.status).toBe("pending");
  });
});