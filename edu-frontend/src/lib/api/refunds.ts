import { http } from "@/lib/api-client";

/**
 * 退款客户端（对齐后端 task19 契约⑩ edu.sql refund_request 权威枚举）。
 * 端点（用户侧前缀 /api/refunds）：
 *   POST /api/refunds                      申请退款（金额服务端强制 ≤ 实付）
 *   GET  /api/refunds?status=&page=&page_size=   我的退款（倒序）
 *   POST /api/refunds/{refund_id}/cancel    撤销退款（仅 pending）
 * refund_type 权威：personal_reason/course_unsatisfied/schedule_conflict/duplicate_purchase
 * refund_status 权威：pending/approved/rejected/refunded
 */

export type RefundType =
  | "personal_reason"
  | "course_unsatisfied"
  | "schedule_conflict"
  | "duplicate_purchase";

export type RefundStatus = "pending" | "approved" | "rejected" | "refunded";

export interface Refund {
  id: number;
  refund_no: string;
  order_no: string;
  refund_type: RefundType;
  refund_status: RefundStatus;
  apply_amount: number;
  approved_amount: number | null;
  refund_reason: string;
  /** approver 备注（拒绝理由） */
  remark: string | null;
  approver_user_id: number | null;
  applied_at: string;
  approved_at: string | null;
  refunded_at: string | null;
  created_at: string;
  /** 撤销 = 软删 yn=0（撤销后不展示为待处理） */
  cancelled: boolean;
}

export interface RefundCreateInput {
  order_no: string;
  refund_type: RefundType;
  apply_amount: number;
  reason: string;
}

export interface RefundCancelResult {
  cancelled: boolean;
  refund_no: string;
}

export interface ListRefundsParams {
  status?: RefundStatus;
  page?: number;
  page_size?: number;
}

export interface RefundPage {
  total: number;
  page: number;
  page_size: number;
  items: Refund[];
}

/** 退款类型选项（供 UI 下拉，label 与 status.ts REFUND_TYPE_TEXT 对齐） */
export const REFUND_TYPE_OPTIONS: { value: RefundType; label: string }[] = [
  { value: "personal_reason", label: "个人原因" },
  { value: "course_unsatisfied", label: "课程不满意" },
  { value: "schedule_conflict", label: "时间冲突" },
  { value: "duplicate_purchase", label: "重复购买" },
];

export function createRefund(input: RefundCreateInput): Promise<Refund> {
  return http.post<Refund>("/api/refunds", input);
}

export function listRefunds(params: ListRefundsParams = {}): Promise<RefundPage> {
  return http.get<RefundPage>("/api/refunds", { params });
}

export function cancelRefund(refundId: number): Promise<RefundCancelResult> {
  return http.post<RefundCancelResult>(`/api/refunds/${refundId}/cancel`);
}