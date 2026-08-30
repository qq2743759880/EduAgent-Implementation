/**
 * /courses/[seriesId] 课程详情页（task46）
 * Server Component：await params 后把 seriesId 传给客户端组件 CourseDetailClient
 * （Next.js 16 惯例，与 /learning/[seriesId]/[sessionId] 一致）。
 */
import type { Metadata } from "next";
import { CourseDetailClient } from "./_components/CourseDetailClient";

export const metadata: Metadata = {
  title: "课程详情 · EduAgent",
  description: "查看课程大纲、班次、评价与思维导图，报名学习。",
};

interface PageParams {
  params: Promise<{ seriesId: string }>;
}

export default async function CourseDetailPage({ params }: PageParams) {
  const resolved = await params;
  const seriesId = Number(resolved.seriesId);
  return <CourseDetailClient seriesId={Number.isFinite(seriesId) ? seriesId : 0} />;
}
