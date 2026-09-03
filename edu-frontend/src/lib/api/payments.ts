import { http } from "@/lib/api-client";

/**
 * 支付客户端（对齐后端 task18 契约⑨ edu.sql payment_record 权威枚举）。
 * 端点 /api/trade/payment*（/api/payments* 为后端 alias，前端统一走 trade 前缀）。
 * 渠道 PayChannel 权威：wechat_pay/alipay/bank_card/offline_transfer/public_account/campus_cashier/mock
 *   （不再使用 clients 早期缩略枚举 wechat/alipay/balance）。
 * 状态 PaymentStatus 权威：pending/paid/failed/closed/partial_refunded/refunded
 *   （不再使用 succeeded/expired）。
 * 发起支付含 audit_pending 附加字段：线下转账 → 提示「到账审核中」，无即时回调。
 */

export type PayChannel =
  | "wechat_pay"
  | "alipay"
  | "bank_card"
  | "offline_transfer"
  | "public_account"
  | "campus_cashier"
  | "mock";

export type PaymentStatus =
  | "pending"
  | "paid"
  | "failed"
  | "closed"
  | "partial_refunded"
  | "refunded";

export interface Payment {
  payment_no: string;
  order_no: string;
  pay_amount: number;
  pay_channel: PayChannel;
  status: PaymentStatus;
  channel_trade_no: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface PaymentLaunchInput {
  pay_channel: PayChannel;
}

export interface PaymentLaunchResult {
  payment_no: string;
  order_no: string;
  status: PaymentStatus;
  pay_url: string | null;
  qr_code_url: string | null;
  /** 线下转账无即时回调 → 前端提示「到账审核中」（GWT③） */
  audit_pending: boolean;
}

export interface PaymentCancelResult {
  cancelled: boolean;
  payment_no: string;
}

export interface ListPaymentsParams {
  status?: PaymentStatus;
  order_no?: string;
  page?: number;
  page_size?: number;
}

export interface PaymentPage {
  total: number;
  page: number;
  page_size: number;
  items: Payment[];
}

/** 发起支付 */
export function launchPayment(
  orderNo: string,
  input: PaymentLaunchInput,
): Promise<PaymentLaunchResult> {
  return http.post<PaymentLaunchResult>(`/api/trade/payment/${orderNo}`, input);
}

/** 支付详情 / 轮询 */
export function getPayment(paymentNo: string): Promise<Payment> {
  return http.get<Payment>(`/api/trade/payment/${paymentNo}`);
}

/** 支付分页查询（status/order_no 过滤） */
export function listPayments(params: ListPaymentsParams = {}): Promise<PaymentPage> {
  return http.get<PaymentPage>("/api/trade/payments", { params });
}

/** 取消支付（pending → closed） */
export function cancelPayment(paymentNo: string): Promise<PaymentCancelResult> {
  return http.post<PaymentCancelResult>(`/api/trade/payment/${paymentNo}/cancel`);
}

/** 重试支付（closed/failed → pending） */
export function retryPayment(paymentNo: string): Promise<Payment> {
  return http.post<Payment>(`/api/trade/payment/${paymentNo}/retry`);
}