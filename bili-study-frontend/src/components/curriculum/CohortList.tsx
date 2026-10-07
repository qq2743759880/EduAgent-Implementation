/**
 * CohortList — 课程详情页「班次选择」RadioGroup 卡（task46，对齐 P8 + HTML 效果图）。
 * 每班次卡：班次名 + 价格 + 剩余席位 + 容量进度条；满员（current_student_count >= max_student_count）disabled。
 * 仅展示真实契约字段（Cohort），无 MOCK fallback。
 */
"use client";

import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { PriceText } from "@/components/ui/price-text";
import { type Cohort } from "@/lib/api/curriculum";
import { cn } from "@/lib/utils";

export function CohortList({
  cohorts,
  selectedId,
  onSelect,
}: {
  cohorts: Cohort[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  if (cohorts.length === 0) {
    return (
      <p className="rounded-xl border-2 border-dashed border-border p-4 text-center text-xs text-muted-foreground">
        暂无在售班次
      </p>
    );
  }

  return (
    <RadioGroup
      value={selectedId ?? undefined}
      onValueChange={(v) => onSelect(Number(v))}
      className="grid gap-2"
      aria-label="选择班次"
    >
      {cohorts.map((c) => {
        const full = c.current_student_count >= c.max_student_count;
        const remaining = Math.max(0, c.max_student_count - c.current_student_count);
        const ratio = c.max_student_count > 0
          ? Math.min(100, Math.round((c.current_student_count / c.max_student_count) * 100))
          : 0;
        const price = Number(c.sale_price);
        return (
          <label
            key={c.id}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-xl border-2 border-border bg-card p-3 transition-all",
              "has-[:checked]:border-candy-purple has-[:checked]:shadow-[0_3px_0_rgba(31,31,31,0.14)]",
              full && "cursor-not-allowed opacity-60",
            )}
          >
            <RadioGroupItem
              value={c.id}
              disabled={full}
              className="mt-0.5 border-2 text-candy-purple"
            />
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-bold text-foreground">{c.cohort_name}</span>
                {full ? (
                  <span className="rounded-full border border-candy-red/40 bg-candy-red/10 px-2 py-0.5 text-3xs font-bold text-candy-red">
                    已满员
                  </span>
                ) : (
                  <span className="rounded-full border border-candy-green/40 bg-candy-green-soft px-2 py-0.5 text-3xs font-bold text-candy-green">
                    有席位
                  </span>
                )}
                <span className="text-3xs text-muted-foreground">
                  {c.start_date?.slice(0, 10) ?? "-"} 开班
                </span>
              </span>
              <span className="mt-1.5 block h-1.5 w-full overflow-hidden rounded-full bg-muted" aria-hidden="true">
                <span
                  className={cn("block h-full rounded-full", ratio > 80 ? "bg-candy-red" : "bg-candy-green")}
                  style={{ width: `${ratio}%` }}
                />
              </span>
              <span className="mt-1.5 flex items-center justify-between text-3xs text-muted-foreground">
                <span>
                  {full ? "已报满" : `余 ${remaining}/${c.max_student_count} 席`} · 班主任{" "}
                  {c.head_teacher_id ? `#${c.head_teacher_id}` : "-"}
                </span>
                <span className="flex items-baseline gap-0.5">
                  <PriceText amount={price} decimals={0} size="sm" className="text-candy-orange" />
                </span>
              </span>
            </span>
          </label>
        );
      })}
    </RadioGroup>
  );
}
