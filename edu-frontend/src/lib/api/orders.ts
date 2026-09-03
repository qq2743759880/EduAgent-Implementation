import { http } from "@/lib/api-client";
import type { PaymentStatus } from "./payments";

/**
 * 订单客户端（对齐后端 task17 契约⑧ edu.sql order.order_status 权威枚举）。
 * 端点 /api/trade/order*（幂等中间件前缀 /api/trade/order，下单需 Idempotency-Key）。
 * OrderStatus 权威：pending/paid/completed/cancelled/partial_refunded/refunded
 * （不再使用 clients 早期缩略枚举 created/pending_payment/refunding/closed）。
 */

export type OrderStatus =
  | "pending"
  | "paid"
  | "completed"
  | "cancelled"
  | "partial_refunded"
  | "refunded";

export type OrderItemStatus = "pending" | "paid" | "completed" | "cancelled" | "refunded";

/** 订单明细（GWT② 嵌套，仅订单详情返回） */
export interface OrderItem {
  order_item_id: number;
  cohort_id: number;
  item_name: string;
  unit_price: number;
  discount_amount: number;
  payable_amount: number;
  order_item_status: OrderItemStatus;
}

/** 支付记录（GWT② 嵌套，仅订单详情返回） */
export interface PaymentItem {
  payment_no: string;
  payment_channel: string;
  payment_status: PaymentStatus;
  amount: number;
  paid_at: string | null;
}

export interface Order {
  order_no: string;
  user_id: number;
  series_id: number;
  cohort_id: number;
  series_title: string | null;
  /** 原价总额 = order.total_amount */
  order_amount: number;
  /** 优惠金额 = order.discount_amount */
  discount_amount: number;
  /** 实付 = order.payable_amount */
  pay_amount: number;
  /** 优惠券领券记录 id（coupon_receive_record.id） */
  coupon_id: number | null;
  status: OrderStatus;
  created_at: string;
  paid_at: string | null;
  cancelled_at: string | null;
  /** 列表接口不填；订单详情接口填充 */
  items: OrderItem[];
  payments: PaymentItem[];
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
  /** true=仅可退款订单（paid/completed/partial_refunded），覆盖 status 走多值逻辑 */
  refundable?: boolean;
  page?: number;
  page_size?: number;
}

export interface OrderPage {
  total: number;
  page: number;
  page_size: number;
  items: Order[];
}

/** 下单（幂等：必须带 Idempotency-Key；金额服务端重算，可信前端仅传标识） */
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

/** 订单详情（items + payments 嵌套） */
export function getOrder(orderNo: string): Promise<Order> {
  return http.get<Order>(`/api/trade/order/${orderNo}`);
}

export function cancelOrder(orderNo: string): Promise<OrderCancelResult> {
  return http.post<OrderCancelResult>(`/api/trade/order/${orderNo}/cancel`);
}