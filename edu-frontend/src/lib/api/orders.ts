import { http } from "@/lib/api-client";

/**
 * 订单客户端（PROPOSED — 待后端 task17 实现，契约冻结后跑 contract-diff 复核）
 * 端点对齐后端幂等中间件预留前缀 /api/trade/order（下单需 Idempotency-Key）
 * 端点设计上浮见 .opencode/handoffs/api-request.md
 */

export type OrderStatus =
  | "created"
  | "pending_payment"
  | "paid"
  | "cancelled"
  | "refunding"
  | "refunded"
  | "closed";

export interface Order {
  order_no: string;
  user_id: number;
  series_id: number;
  cohort_id: number;
  series_title: string;
  order_amount: number;
  discount_amount: number;
  pay_amount: number;
  coupon_id: number | null;
  status: OrderStatus;
  created_at: string;
  paid_at: string | null;
  cancelled_at: string | null;
}

export interface OrderCreateInput {
  series_id: number;
  cohort_id: number;
  coupon_id?: number;
}

export interface OrderCancelResult {
  cancelled: boolean;
  order_no: string;
}

export interface ListOrdersParams {
  status?: OrderStatus;
  page?: number;
  page_size?: number;
}

export interface OrderPage {
  total: number;
  page: number;
  page_size: number;
  items: Order[];
}

export function createOrder(
  input: OrderCreateInput,
  idempotencyKey: string,
): Promise<Order> {
  return http.post<Order>("/api/trade/order", input, {
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

export function listOrders(params: ListOrdersParams = {}): Promise<OrderPage> {
  return http.get<OrderPage>("/api/trade/orders", { params });
}

export function getOrder(orderNo: string): Promise<Order> {
  return http.get<Order>(`/api/trade/order/${orderNo}`);
}

export function cancelOrder(orderNo: string): Promise<OrderCancelResult> {
  return http.post<OrderCancelResult>(`/api/trade/order/${orderNo}/cancel`);
}
