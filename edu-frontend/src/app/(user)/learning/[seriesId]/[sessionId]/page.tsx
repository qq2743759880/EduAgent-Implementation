/**
 * /learning/[seriesId]/[sessionId] — 课次播放页
 * 组合：
 *   - ProtectedRoute 未登录 → /login?redirect=
 *   - 顶部：面包屑（课程 → 模块 → 课次）+ 上一课/下一课按钮
 *   - 左主区：VideoPlayer（liveProgress 更新本地状态）
 *   - 左主区下：InteractiveTabs（习题/单词/数学/编程）
 *   - 右栏 sticky：SessionSidebar（要点 + 迷你导图 + 进度快览 + 错题·单词 CTA）
 *
 * 数据准备：
 *   - 课次完整结构（series→modules→sessions）优先用 P3 getMyCourses() 返回的进度数据合成
 *   - 如果学生尚未报名（progress 列表无此系列）→ 回退 P4 getSeriesTree() 拿 curriculum tree（不展示学习进度数据，仅展示结构）
 */
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "课次播放 · EduAgent",
  description: "观看课程视频、做随堂练习、查看知识点图谱。",
};

import LearningPlayClient from "./_components/LearningPlayClient";

interface PageParams {
  params: Promise<{ seriesId: string; sessionId: string }>;
}

export default async function LearningPlayPage({ params }: PageParams) {
  const resolved = await params;
  const seriesId = Number(resolved.seriesId);
  const sessionId = Number(resolved.sessionId);
  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-10">
      <LearningPlayClient
        seriesId={Number.isFinite(seriesId) ? seriesId : 0}
        sessionId={Number.isFinite(sessionId) ? sessionId : 0}
      />
    </div>
  );
}
