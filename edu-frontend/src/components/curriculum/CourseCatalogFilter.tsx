/**
 * CourseCatalogFilter — 课程中心「两级导航」筛选条（task44）。
 * 一级学科大类 chips → 二级课程方向 chips（选中一级后出现）；交付/价格/排序/重置。
 * 使用 task41 C9 FilterBar（role=group）+ C12 Select。
 * <768px 折叠为「筛选」按钮（默认收起，点击展开，含当前条件摘要）。
 */
"use client";

import { useMemo, useState } from "react";
import { ChevronDown, RotateCcw, SlidersHorizontal } from "lucide-react";
import { FilterBar } from "@/components/ui/filter-bar";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  COURSE_CATALOG,
  DELIVERY_LABELS,
  PRICE_RANGES,
  SORT_OPTIONS,
  directionEmoji,
  type SortValue,
} from "@/lib/curriculum-catalog";

export interface CourseFilterValue {
  /** 一级学科大类名（"" = 全部） */
  category: string;
  /** 二级课程方向名（"" = 全部方向） */
  direction: string;
  /** 交付模式（"any" = 全部） */
  delivery: string;
  /** 价格区间 value（"any" = 不限） */
  price: string;
  /** 排序 */
  sort: SortValue;
}

export const DEFAULT_FILTER: CourseFilterValue = {
  category: "",
  direction: "",
  delivery: "any",
  price: "any",
  sort: "default",
};

interface CourseCatalogFilterProps {
  value: CourseFilterValue;
  onChange: (next: CourseFilterValue) => void;
}

export function CourseCatalogFilter({ value, onChange }: CourseCatalogFilterProps) {
  const [open, setOpen] = useState(false);

  const directions = useMemo(
    () => COURSE_CATALOG.find((c) => c.name === value.category)?.directions ?? [],
    [value.category],
  );

  const set = (patch: Partial<CourseFilterValue>) => onChange({ ...value, ...patch });

  const summary = useMemo(() => {
    const parts: string[] = [];
    if (value.category) parts.push(value.category);
    if (value.direction) parts.push(value.direction);
    if (value.delivery !== "any") {
      parts.push(DELIVERY_LABELS[value.delivery as keyof typeof DELIVERY_LABELS] ?? value.delivery);
    }
    if (value.price !== "any") {
      parts.push(PRICE_RANGES.find((r) => r.value === value.price)?.label ?? "");
    }
    if (value.sort !== "default") {
      parts.push(SORT_OPTIONS.find((s) => s.value === value.sort)?.label ?? "");
    }
    return parts.filter(Boolean).join(" · ") || "全部课程";
  }, [value]);

  const reset = () => onChange({ ...DEFAULT_FILTER });

  return (
    <div className="rounded-xl border-2 border-border bg-card p-3 md:p-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="course-filter-rows"
        className="flex w-full items-center gap-2 rounded-lg border-2 border-border bg-background px-3 py-2.5 text-2xs font-bold text-foreground md:hidden"
      >
        <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
        <span>筛选</span>
        <span className="ml-auto max-w-[58%] truncate text-right font-bold text-candy-orange">{summary}</span>
        <ChevronDown
          className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
          aria-hidden="true"
        />
      </button>

      <FilterBar
        id="course-filter-rows"
        className={cn(
          "mt-3 md:mt-0",
          open
            ? "flex-col items-stretch gap-3 md:flex-row md:flex-wrap md:items-center md:gap-2"
            : "hidden md:flex",
        )}
      >
        <FilterGroup label="学科">
          <FilterChip active={value.category === ""} onClick={() => set({ category: "", direction: "" })}>
            全部
          </FilterChip>
          {COURSE_CATALOG.map((c) => (
            <FilterChip
              key={c.name}
              active={value.category === c.name}
              onClick={() => set({ category: c.name, direction: "" })}
            >
              {c.emoji} {c.name}
            </FilterChip>
          ))}
        </FilterGroup>

        {value.category ? (
          <FilterGroup label="方向" accent="orange">
            <FilterChip
              active={value.direction === ""}
              accent="orange"
              onClick={() => set({ direction: "" })}
            >
              全部方向
            </FilterChip>
            {directions.map((d) => (
              <FilterChip
                key={d}
                active={value.direction === d}
                accent="orange"
                onClick={() => set({ direction: d })}
              >
                {directionEmoji(d)} {d}
              </FilterChip>
            ))}
          </FilterGroup>
        ) : null}

        <Divider />

        <FilterGroup label="交付">
          <FilterChip active={value.delivery === "any"} onClick={() => set({ delivery: "any" })}>
            全部
          </FilterChip>
          {(Object.keys(DELIVERY_LABELS) as Array<keyof typeof DELIVERY_LABELS>).map((k) => (
            <FilterChip key={k} active={value.delivery === k} onClick={() => set({ delivery: k })}>
              {DELIVERY_LABELS[k]}
            </FilterChip>
          ))}
        </FilterGroup>

        <Divider />

        <FilterGroup label="价格">
          <Select
            options={PRICE_RANGES.map((r) => ({ value: r.value, label: r.label }))}
            value={value.price}
            onValueChange={(v) => set({ price: v ?? "any" })}
            placeholder="不限"
            className="w-40"
          />
        </FilterGroup>

        <Divider />

        <FilterGroup label="排序">
          {SORT_OPTIONS.map((s) => (
            <FilterChip key={s.value} active={value.sort === s.value} onClick={() => set({ sort: s.value })}>
              {s.label}
            </FilterChip>
          ))}
        </FilterGroup>

        <button
          type="button"
          onClick={reset}
          className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-2xs font-bold text-muted-foreground transition-colors hover:bg-candy-red/10 hover:text-candy-red"
        >
          <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
          重置 ×
        </button>
      </FilterBar>
    </div>
  );
}

function FilterGroup({
  label,
  children,
  accent = "muted",
}: {
  label: string;
  children: React.ReactNode;
  accent?: "muted" | "orange";
}) {
  return (
    <div className="flex min-w-0 items-start gap-2">
      <span
        className={cn(
          "pt-1.5 text-2xs font-bold",
          accent === "orange" ? "text-candy-purple" : "text-muted-foreground",
        )}
      >
        {label}
      </span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  children,
  accent = "purple",
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  accent?: "purple" | "orange";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border-2 px-3 py-1 text-2xs font-semibold transition-all active:scale-95",
        active
          ? accent === "orange"
            ? "border-candy-orange bg-candy-orange text-white shadow-[0_3px_0_rgba(255,77,0,0.3)]"
            : "border-candy-purple bg-candy-purple text-white shadow-[0_3px_0_rgba(124,58,237,0.35)]"
          : "border-border bg-background text-foreground hover:-translate-y-px hover:border-candy-purple hover:text-candy-purple",
      )}
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div aria-hidden="true" className="hidden h-7 w-px bg-border md:block" />;
}
