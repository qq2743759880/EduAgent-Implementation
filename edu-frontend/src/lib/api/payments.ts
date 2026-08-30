import { http } from "@/lib/api-client";

/**
 * 支付客户端（PROPOSED — 待后端 task18 实现，契约冻结后跑 contract-diff 复核）
 * 端点对齐后端幂等中间件预留前缀 /api/trade/payment（支付回调幂等由后端保证）
 * 端点设计上浮见 .opencode/handoffs/api-request.md
 */

export type PayChannel = "wechat" | "alipay" | "balance" | "mock";
export type PaymentStatus = "pending" | "succeeded" | "failed" | "expired";

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
}

export function launchPayment(
  orderNo: string,
  input: PaymentLaunchInput,
): Promise<PaymentLaunchResult> {
  return http.post<PaymentLaunchResult>(
    `/api/trade/payment/${orderNo}`,
    input,
  );
}

export function getPayment(paymentNo: string): Promise<Payment> {
  return http.get<Payment>(`/api/trade/payment/${paymentNo}`);
}
