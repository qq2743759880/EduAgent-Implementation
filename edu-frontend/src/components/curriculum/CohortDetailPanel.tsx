/**
 * CohortDetailPanel — 课程详情页「班次详情」Tab（task46，对齐 P8 + HTML 效果图）。
 * 展示选中班次的排期/容量/编码/班主任/校区等真实契约字段（Cohort），无 MOCK。
 */
"use client";

import { type Cohort } from "@/lib/api/curriculum";

export function CohortDetailPanel({ cohort }: { cohort: Cohort | null }) {
  if (!cohort) {
    return (
      <p className="rounded-xl border-2 border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        请先在上方选择一个班次
      </p>
    );
  }

  const rows: Array<[string, string]> = [
    ["班次名称", cohort.cohort_name],
    ["班次编码", cohort.cohort_code],
    ["开班日期", cohort.start_date?.slice(0, 10) ?? "-"],
    ["结课日期", cohort.end_date?.slice(0, 10) ?? "待定"],
    ["班级容量", `${cohort.current_student_count} / ${cohort.max_student_count} 人`],
    ["班主任", cohort.head_teacher_id ? `#${cohort.head_teacher_id}` : "-"],
    ["校区", cohort.campus_id ? `#${cohort.campus_id}` : "-"],
    ["上架状态", cohort.yn === 1 ? "在售" : "停售"],
  ];

  return (
    <div className="overflow-hidden rounded-xl border-2 border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border bg-candy-orange-soft px-4 py-3">
        <span aria-hidden="true" className="text-lg">📅</span>
        <span className="text-sm font-bold text-foreground">班次详情 · {cohort.cohort_name}</span>
      </div>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 px-4 py-4 sm:grid-cols-2">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-3 border-b border-dashed border-border pb-2">
            <dt className="shrink-0 text-xs text-muted-foreground">{k}</dt>
            <dd className="text-right text-sm font-semibold text-foreground">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
