/**
 * /tickets/[ticketId] 工单详情页（Season-2 React，task100）
 * Server Component：await params 后把 ticketId 传给客户端组件 TicketDetailClient。
 * 展示 reply；已 resolved/closed 且未评分 → 满意度评价（1-5 星 + 可选 comment）。
 */
import type { Metadata } from "next";
import TicketDetailClient from "./_components/TicketDetailClient";

export const metadata: Metadata = {
  title: "工单详情 · EduAgent",
  description: "查看工单处理进度与客服回复，并进行满意度评价。",
};

interface PageParams {
  params: Promise<{ ticketId: string }>;
}

export default async function TicketDetailPage({ params }: PageParams) {
  const resolved = await params;
  const ticketId = Number(resolved.ticketId);
  return <TicketDetailClient ticketId={Number.isFinite(ticketId) ? ticketId : 0} />;
}