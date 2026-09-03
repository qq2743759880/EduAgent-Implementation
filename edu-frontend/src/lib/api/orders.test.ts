/**
 * orders.ts API 封装单测（task100 Season-2：订单契约对齐 task17）
 * 覆盖：旧枚举 → 后端权威枚举、getOrder 详情嵌套、list/cancel/create（幂等头）。
 * mock http.* 直接返回业务体（契约冻结①：拦截器已解包，无 .data 壳）
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { http } from "@/lib/api-client";
import { cancelOrder, createOrder, getOrder, listOrders, type Order } from "./orders";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);

function makeOrder(overrides: Partial<Order> = {}): Order {
  return {
    order_no: "E20260813000001",
    user_id: 1,
    series_id: 1001,
    cohort_id: 12,
    series_title: "通用编程入门班",
    order_amount: 2799,
    discount_amount: 0,
    pay_amount: 2799,
    coupon_id: null,
    status: "pending",
    created_at: "2026-08-13T09:12:00",
    paid_at: null,
    cancelled_at: null,
    items: [],
    payments: [],
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("listOrders", () => {
  it("默认分页参数透传（向后端分页壳传递 page/page_size）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 100, items: [] });
    await listOrders({ page: 1, page_size: 100 });
    expect(mockGet).toHaveBeenCalledWith("/api/trade/orders", {
      params: { page: 1, page_size: 100 },
    });
  });

  it("status 过滤传后端权威枚举值", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listOrders({ status: "pending", page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/trade/orders", {
      params: { status: "pending", page: 1, page_size: 20 },
    });
  });

  it("refundable=true 透传（后端返回 paid/completed/partial_refunded）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listOrders({ refundable: true, page: 1, page_size: 20 });
    expect(mockGet).toHaveBeenCalledWith("/api/trade/orders", {
      params: { refundable: true, page: 1, page_size: 20 },
    });
  });

  it("失败向上抛（页面负责错误态，不静默返回空）", async () => {
    mockGet.mockRejectedValueOnce(new Error("Network Error"));
    await expect(listOrders()).rejects.toThrow("Network Error");
  });
});

describe("getOrder（详情嵌套）", () => {
  it("返回订单详情，含 items + payments 嵌套字段", async () => {
    const detail = makeOrder({
      status: "paid",
      items: [
        {
          order_item_id: 1,
          cohort_id: 12,
          item_name: "通用编程入门班 · 春季班",
          unit_price: 2799,
          discount_amount: 0,
          payable_amount: 2799,
          order_item_status: "paid",
        },
      ],
      payments: [
        {
          payment_no: "P20260813",
          payment_channel: "mock",
          payment_status: "paid",
          amount: 2799,
          paid_at: "2026-08-13T09:15:00",
        },
      ],
    });
    mockGet.mockResolvedValueOnce(detail);
    const resp = await getOrder("E20260813000001");
    expect(mockGet).toHaveBeenCalledWith("/api/trade/order/E20260813000001");
    expect(resp.status).toBe("paid");
    expect(resp.items?.[0]?.order_item_id).toBe(1);
    expect(resp.payments?.[0]?.payment_status).toBe("paid");
  });
});

describe("createOrder（幂等下单）", () => {
  it("body 字段 + Idempotency-Key 请求头缺一不可", async () => {
    mockPost.mockResolvedValueOnce(makeOrder({ status: "pending" }));
    const key = `uuid-${Date.now()}`;
    await createOrder({ series_id: 1001, cohort_id: 12, coupon_id: 5 }, key);
    expect(mockPost).toHaveBeenCalledWith(
      "/api/trade/order",
      { series_id: 1001, cohort_id: 12, coupon_id: 5 },
      { headers: { "Idempotency-Key": key } },
    );
  });

  it("无 coupon 时不传 coupon_id", async () => {
    mockPost.mockResolvedValueOnce(makeOrder());
    await createOrder({ series_id: 1001, cohort_id: 12 }, "k");
    expect(mockPost).toHaveBeenCalledWith(
      "/api/trade/order",
      { series_id: 1001, cohort_id: 12 },
      { headers: { "Idempotency-Key": "k" } },
    );
  });

  it("下单失败向上抛（不吞错，由调用方 toast）", async () => {
    mockPost.mockRejectedValueOnce(new Error("库存不足"));
    await expect(
      createOrder({ series_id: 1001, cohort_id: 12 }, "k"),
    ).rejects.toThrow("库存不足");
  });
});

describe("cancelOrder", () => {
  it("取消订单走 POST {order_no}/cancel", async () => {
    mockPost.mockResolvedValueOnce({ cancelled: true, order_no: "E20260813000001" });
    const resp = await cancelOrder("E20260813000001");
    expect(mockPost).toHaveBeenCalledWith("/api/trade/order/E20260813000001/cancel");
    expect(resp.cancelled).toBe(true);
  });
});