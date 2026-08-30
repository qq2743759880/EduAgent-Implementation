/**
 * /practice/[mode] — 复习中心入口（task49 三模式）
 *   mode ∈ wrong-book | topic | vocab
 *   - wrong-book 错题本：listWrongBook 错题列表 → QuizSession 逐题复习
 *   - topic 专项练习：按题型（QuestionMode）过滤取题 → QuizSession
 *   - vocab 单词本：复用既有 SM-2 词卡（VocabDailyPanel / VocabProgressCard，范围外不动）
 *   其他 mode：显示「模式不存在」CTA 跳回仪表盘 / 我的课程
 */
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "复习中心 · EduAgent",
  description: "重做错题、专项刷题、复习单词，巩固你的薄弱知识点。",
};

import PracticeCenterClient from "./_components/PracticeCenterClient";

interface PageParams {
  params: Promise<{ mode: string }>;
}

export default async function PracticeCenterPage({ params }: PageParams) {
  const resolved = await params;
  const mode = String(resolved.mode ?? "").toLowerCase();
  const normalized =
    mode === "wrong-book" || mode === "topic" || mode === "vocab" ? mode : null;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-10">
      <PracticeCenterClient mode={normalized} rawMode={mode} />
    </div>
  );
}
