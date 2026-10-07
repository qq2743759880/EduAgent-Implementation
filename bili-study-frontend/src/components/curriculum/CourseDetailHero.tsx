/**
 * CourseDetailHero — 课程详情页 Hero（task46，对齐 P8 + HTML 效果图）。
 * 左 2/3 糖果渐变封面（白字标题 + emoji + 交付/班次/分类 facts）；右 1/3 购买面板：
 * CohortList 班次选择 → 价格联动 → 收藏/领券 → 立即报名 + 费用明细（券后实付）。
 * 全部字段来自真实契约（SeriesDetail / Cohort / Coupon），无 MOCK。
 */
"use client";

import { Ticket, Lock } from "lucide-react";
import { CohortList } from "@/components/curriculum/CohortList";
import { FavoriteButton } from "@/components/curriculum/FavoriteButton";
import { PriceText, formatAmount } from "@/components/ui/price-text";
import {
  DELIVERY_LABELS,
  coverEmoji,
  coverGradient,
} from "@/lib/curriculum-catalog";
import type { Cohort, SeriesDetail } from "@/lib/api/curriculum";
import type { Coupon } from "@/lib/api/coupons";
import { cn } from "@/lib/utils";

export function CourseDetailHero({
  series,
  cohorts,
  selectedCohortId,
  onSelectCohort,
  coupon,
  onOpenCoupon,
  favorited,
  onToggleFavorite,
  onEnroll,
  enrolling,
  authed,
}: {
  series: SeriesDetail;
  cohorts: Cohort[];
  selectedCohortId: number | null;
  onSelectCohort: (id: number) => void;
  coupon: Coupon | null;
  onOpenCoupon: () => void;
  favorited: boolean;
  onToggleFavorite: () => void;
  onEnroll: () => void;
  enrolling: boolean;
  authed: boolean;
}) {
  const categoryNames = series.categories?.map((c) => c.category_name) ?? [];
  const coverLike = { category_names: categoryNames };
  const selectedCohort = cohorts.find((c) => c.id === selectedCohortId) ?? null;
  const price = selectedCohort ? Number(selectedCohort.sale_price) : 0;
  const usable = Boolean(coupon && price >= coupon.min_spend);
  const payAmount = usable && coupon ? Math.max(0, price - coupon.face_value) : price;
  const full = selectedCohort
    ? selectedCohort.current_student_count >= selectedCohort.max_student_count
    : false;

  return (
    <section
      aria-label="课程信息"
      className="grid grid-cols-1 gap-4 rounded-3xl border-[3px] border-foreground bg-card p-3.5 shadow-[0_5px_0_rgba(31,31,31,0.14)] lg:grid-cols-[2fr_1fr]"
    >
      {/* 封面 2/3 */}
      <div
        className={cn(
          "relative flex min-h-64 flex-col justify-end overflow-hidden rounded-2xl bg-gradient-to-br p-5",
          coverGradient(coverLike),
        )}
      >
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.28),transparent_60%)]"
        />
        <span
          aria-hidden="true"
          className="absolute right-3 top-2 animate-[candy-float_3.2s_ease-in-out_infinite] text-5xl drop-shadow-[0_4px_0_rgba(31,31,31,0.18)]"
        >
          {coverEmoji(coverLike)}
        </span>
        <span className="absolute left-3 top-3 rounded-full bg-foreground/45 px-2.5 py-1 text-3xs font-bold text-white backdrop-blur-sm">
          {DELIVERY_LABELS[series.delivery_mode]}
        </span>

        <h1 className="relative max-w-[88%] font-heading text-2xl font-extrabold leading-tight text-white drop-shadow-[0_3px_0_rgba(31,31,31,0.22)]">
          {series.series_name}
        </h1>
        <p className="relative mt-2 max-w-[92%] text-xs leading-relaxed text-white/95">
          {series.description || "暂无课程简介"}
        </p>
        <div className="relative mt-3.5 flex flex-wrap gap-2">
          {[
            `🖥 ${DELIVERY_LABELS[series.delivery_mode]}`,
            `📅 ${series.cohort_count ?? 0} 个班次`,
            `🏷 ${categoryNames.join(" · ") || "课程"}`,
          ].map((f) => (
            <span
              key={f}
              className="rounded-full bg-foreground/35 px-2.5 py-1 text-3xs font-semibold text-white backdrop-blur-sm"
            >
              {f}
            </span>
          ))}
        </div>
      </div>

      {/* 购买面板 1/3 */}
      <div className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <span className="text-xs text-muted-foreground">班次价格</span>
          <span className="flex items-baseline gap-0.5">
            <PriceText amount={series.min_price} decimals={0} size="lg" className="text-candy-orange" />
            <span className="text-3xs font-semibold text-muted-foreground">起</span>
          </span>
        </div>

        <CohortList cohorts={cohorts} selectedId={selectedCohortId} onSelect={onSelectCohort} />

        <div className="flex gap-2">
          <FavoriteButton
            favorited={favorited}
            onToggle={onToggleFavorite}
            seriesName={series.series_name}
          />
          <button
            type="button"
            onClick={onOpenCoupon}
            className="inline-flex h-11 flex-1 items-center justify-center gap-1.5 rounded-xl border-2 border-border bg-card px-3 text-sm font-bold text-foreground shadow-[0_3px_0_rgba(31,31,31,0.14)] transition-all hover:-translate-y-0.5 active:translate-y-0 active:shadow-none"
          >
            <Ticket className="h-4 w-4 text-candy-orange" aria-hidden="true" />
            {coupon ? `已选券 -${formatAmount(coupon.face_value, "¥", 0)}` : "领券"}
          </button>
        </div>

        <button
          type="button"
          onClick={onEnroll}
          disabled={!selectedCohort || full || enrolling}
          className="inline-flex h-12 items-center justify-center gap-1.5 rounded-xl border-2 border-foreground bg-candy-orange px-4 text-base font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.14)] transition-all hover:-translate-y-0.5 hover:bg-candy-orange/90 active:translate-y-0 active:shadow-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          {enrolling ? (
            "提交中…"
          ) : full ? (
            <>
              <Lock className="h-4 w-4" aria-hidden="true" /> 该班次已满员
            </>
          ) : (
            <>
              立即报名
              <span className="flex items-baseline gap-1">
                <PriceText amount={payAmount} decimals={0} className="text-white" />
                {usable && coupon && (
                  <span className="text-xs font-semibold text-white/70 line-through">
                    {formatAmount(price, "¥", 0)}
                  </span>
                )}
              </span>
            </>
          )}
        </button>

        {!authed && (
          <p className="rounded-xl border-2 border-dashed border-candy-orange/40 bg-candy-orange-soft px-3 py-2 text-center text-xs font-bold text-candy-orange">
            🔒 未登录：报名/领券/收藏将跳转登录并原路返回
          </p>
        )}

        <div className="rounded-xl border-2 border-dashed border-candy-orange/30 bg-candy-orange-soft px-3.5 py-2.5 text-xs text-foreground">
          <div className="flex justify-between">
            <span className="text-muted-foreground">班次</span>
            <span className="font-semibold">{selectedCohort?.cohort_name ?? "-"}</span>
          </div>
          <div className="mt-1 flex justify-between">
            <span className="text-muted-foreground">优惠券</span>
            <span className="font-semibold">
              {usable && coupon ? `-${formatAmount(coupon.face_value, "¥", 0)}` : "未使用"}
            </span>
          </div>
          <div className="mt-1 flex justify-between border-t border-dashed border-candy-orange/30 pt-1.5">
            <span className="font-semibold text-foreground">实付</span>
            <span className="font-extrabold text-candy-orange">
              {formatAmount(payAmount, "¥", 0)}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
