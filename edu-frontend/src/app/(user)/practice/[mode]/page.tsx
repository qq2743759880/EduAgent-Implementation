/**
 * /practice/[mode] — 复习中心入口
 *   mode ∈ wrong-book | vocab
 *   其他 mode：显示「模式不存在」CTA 跳回仪表盘 / 我的课程
 */
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "复习中心 · EduAgent",
  description: "重做错题、复习单词，巩固你的薄弱知识点。",
};

import PracticeCenterClient from "./_components/PracticeCenterClient";

interface PageParams {
  params: Promise<{ mode: string }>;
}

export default async function PracticeCenterPage({ params }: PageParams) {
  const resolved = await params;
  const mode = String(resolved.mode ?? "").toLowerCase();
  const normalized = mode === "wrong-book" || mode === "vocab" ? mode : null;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 md:py-10">
      <PracticeCenterClient mode={normalized} rawMode={mode} />
    </div>
  );
}
