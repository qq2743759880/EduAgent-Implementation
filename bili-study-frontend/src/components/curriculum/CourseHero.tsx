/**
 * CourseHero — 课程中心「学中玩」Hero（task44）。
 * 吉祥物 + 口号 + 真实目录统计（9 大学科 / 3 种交付 / AI 学习伴侣）。
 * 数据全部来自 COURSE_CATALOG 常量，无 MOCK 数字（验收：grep 无 fallback 假数据）。
 */
"use client";

import { COURSE_CATALOG, DELIVERY_LABELS } from "@/lib/curriculum-catalog";

const STATS = [
  { icon: "💻", label: "学科方向", value: `${COURSE_CATALOG.length} 大类` },
  { icon: "🎬", label: "交付模式", value: `${Object.keys(DELIVERY_LABELS).length} 种` },
  { icon: "🤖", label: "AI 学习伴侣", value: "问答 · 导图 · 习题" },
] as const;

export function CourseHero() {
  return (
    <section
      className="relative overflow-hidden rounded-[1.75rem] border-[3px] border-foreground/90 bg-gradient-to-br from-candy-orange-soft via-candy-orange-soft to-candy-purple-soft px-5 py-5 md:px-6 md:py-6"
      aria-label="课程中心欢迎区"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-[radial-gradient(circle,rgba(255,200,0,0.4),transparent_70%)]"
      />
      <div className="relative flex items-center gap-4 md:gap-6">
        <div
          role="img"
          aria-label="吉祥物猫头鹰"
          className="flex-shrink-0 animate-[candy-float_3.2s_ease-in-out_infinite] text-5xl drop-shadow-[0_6px_0_rgba(31,31,31,0.12)] md:text-6xl"
        >
          🦉
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="font-heading text-2xl font-extrabold leading-tight tracking-tight text-foreground md:text-[1.625rem]">
            学中玩 · 玩中学，每天进步<b className="text-candy-orange">一点点</b>
          </h2>
          <p className="mt-1 text-2xs text-muted-foreground md:text-sm">
            像玩游戏一样把课程学完，按学科 × 方向两级导航，找到最适合你的课
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {STATS.map((s) => (
              <div
                key={s.label}
                className="flex items-center gap-1.5 rounded-xl border-2 border-border bg-card px-3 py-1.5 text-2xs text-foreground shadow-[0_3px_0_rgba(31,31,31,0.08)]"
              >
                <span aria-hidden="true" className="text-base leading-none">
                  {s.icon}
                </span>
                <span className="text-muted-foreground">{s.label}</span>
                <b className="font-heading text-sm font-extrabold text-candy-orange">
                  {s.value}
                </b>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
