/**
 * CourseCard — 课程列表卡片（task44「学中玩」风格，task46 复用）。
 * 封面：糖果渐变 + 白字课程名 + 学科 emoji + 交付徽章 + 编码（全部由真实契约字段派生）。
 * 卡片体：标题 / 分类徽章 / 简介（空显示「-」）/ 价格「¥X 起」（C14 PriceText，decimals=0）。
 * 仅展示真实数据，无 MOCK fallback（验收：grep 无 fallbackPrice/fallbackRating）。
 */
"use client";

import Link from "next/link";
import { PriceText } from "@/components/ui/price-text";
import { type SeriesListItem } from "@/lib/api/curriculum";
import {
  DELIVERY_LABELS,
  categoryLabel,
  coverEmoji,
  coverGradient,
} from "@/lib/curriculum-catalog";
import { cn } from "@/lib/utils";

export function CourseCard({ data }: { data: SeriesListItem }) {
  const price = data.min_price != null ? Number(data.min_price) : null;
  const hasPrice = price != null && Number.isFinite(price);

  return (
    <Link
      href={`/courses/${data.id}`}
      className="group block overflow-hidden rounded-2xl border-2 border-border bg-card transition-all duration-200 hover:-translate-y-1 hover:border-candy-purple hover:shadow-[0_10px_24px_-10px_rgba(124,58,237,0.28)] active:scale-[0.97]"
    >
      {/* 封面：糖果渐变 + 白字标题 + emoji + 交付徽章 + 编码 */}
      <div
        className={cn(
          "relative aspect-video overflow-hidden bg-gradient-to-br",
          coverGradient(data),
        )}
      >
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.25),transparent_60%)]"
        />
        <span className="absolute left-2.5 top-2.5 rounded-full bg-foreground/45 px-2.5 py-1 text-3xs font-bold text-white backdrop-blur-sm">
          {DELIVERY_LABELS[data.delivery_mode]}
        </span>
        <span
          aria-hidden="true"
          className="absolute bottom-3 right-3 text-4xl leading-none drop-shadow-[0_3px_0_rgba(31,31,31,0.18)]"
        >
          {coverEmoji(data)}
        </span>
        <span className="absolute bottom-2.5 left-2.5 rounded-md bg-foreground/35 px-1.5 py-0.5 font-mono text-3xs text-white/90">
          {data.series_code}
        </span>
        <h3 className="absolute left-1/2 top-1/2 z-[1] w-[82%] -translate-x-1/2 -translate-y-1/2 text-center font-heading text-xl font-extrabold leading-snug text-white drop-shadow-[0_2px_6px_rgba(31,31,31,0.35)] line-clamp-2">
          {data.series_name}
        </h3>
      </div>

      {/* 卡片体 */}
      <div className="flex flex-col gap-2 p-3.5">
        <h3 className="line-clamp-2 min-h-10 font-heading text-base font-bold leading-snug text-foreground">
          {data.series_name}
        </h3>
        <div className="flex flex-wrap gap-1.5">
          <span className="rounded-full border border-candy-purple/30 bg-candy-purple-soft px-2 py-0.5 text-3xs font-bold text-candy-purple">
            {coverEmoji(data)} {categoryLabel(data)}
          </span>
        </div>
        <p className="line-clamp-2 min-h-8 text-2xs text-muted-foreground">
          {data.description || "-"}
        </p>
        <div className="mt-auto flex items-center justify-between border-t-2 border-dashed border-border pt-2.5">
          {hasPrice ? (
            <span className="flex items-baseline gap-0.5">
              <PriceText amount={price} decimals={0} size="lg" className="text-candy-orange" />
              <span className="text-2xs font-semibold text-muted-foreground">起</span>
            </span>
          ) : (
            <span className="text-2xs text-muted-foreground">-</span>
          )}
          <span className="text-2xs font-semibold text-candy-purple opacity-0 transition-opacity group-hover:opacity-100">
            查看详情 →
          </span>
        </div>
      </div>
    </Link>
  );
}
