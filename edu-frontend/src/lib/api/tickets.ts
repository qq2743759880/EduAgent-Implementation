import { http } from "@/lib/api-client";

/**
 * 工单/人工申诉客户端（PROPOSED — 待后端 task22 实现，契约冻结后跑 contract-diff 复核）
 * 端点对齐后端幂等中间件预留前缀 /api/trade/after_sales/ticket
 * 业务语义：工单创建（consult/appeal 人工申诉）/ 我的工单 / 满意度评价
 * 端点设计上浮见 .opencode/handoffs/api-request.md
 */

export type TicketType = "consult" | "appeal" | "refund" | "other";
export type TicketStatus = "open" | "processing" | "resolved" | "closed";

export interface Ticket {
  ticket_id: number;
  ticket_no: string;
  user_id: number;
  order_no: string | null;
  ticket_type: TicketType;
  title: string;
  content: string;
  status: TicketStatus;
  reply: string | null;
  satisfaction_score: number | null;
  satisfaction_comment: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface TicketCreateInput {
  order_no?: string;
  ticket_type: TicketType;
  title: string;
  content: string;
}

export interface TicketSatisfactionInput {
  satisfaction_score: number;
  satisfaction_comment?: string;
}

export interface TicketSatisfactionResult {
  ticket_id: number;
  satisfaction_score: number;
  submitted: boolean;
}

export interface ListTicketsParams {
  status?: TicketStatus;
  ticket_type?: TicketType;
  page?: number;
  page_size?: number;
}

export interface TicketPage {
  total: number;
  page: number;
  page_size: number;
  items: Ticket[];
}

export function createTicket(input: TicketCreateInput): Promise<Ticket> {
  return http.post<Ticket>("/api/trade/after_sales/ticket", input);
}

export function listMyTickets(params: ListTicketsParams = {}): Promise<TicketPage> {
  return http.get<TicketPage>("/api/trade/after_sales/tickets", { params });
}

export function getTicket(ticketId: number): Promise<Ticket> {
  return http.get<Ticket>(`/api/trade/after_sales/ticket/${ticketId}`);
}

export function submitTicketSatisfaction(
  ticketId: number,
  input: TicketSatisfactionInput,
): Promise<TicketSatisfactionResult> {
  return http.post<TicketSatisfactionResult>(
    `/api/trade/after_sales/ticket/${ticketId}/satisfaction`,
    input,
  );
}
