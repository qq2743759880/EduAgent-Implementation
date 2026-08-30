/**
 * CourseDetailTabs — 课程详情页 Tabs 四栏（task46，对齐 P8 + HTML 效果图）。
 * 课程大纲（四级树）/ 班次详情 / 课程评价 / 思维导图（echarts 复用）。
 */
"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CourseDetailSyllabus } from "@/components/curriculum/CourseDetailSyllabus";
import { CohortDetailPanel } from "@/components/curriculum/CohortDetailPanel";
import { ReviewList, type ReviewItem } from "@/components/curriculum/ReviewList";
import { CourseMindmapView, type MindmapLoadState } from "@/components/curriculum/CourseMindmapView";
import type { Cohort, ModuleWithSessions, SeriesDetail } from "@/lib/api/curriculum";

export function CourseDetailTabs({
  series,
  cohort,
  modules,
  modulesLoading,
  reviews,
  mindmapState,
}: {
  series: SeriesDetail;
  cohort: Cohort | null;
  modules: ModuleWithSessions[];
  modulesLoading: boolean;
  reviews: ReviewItem[];
  mindmapState: MindmapLoadState;
}) {
  return (
    <Tabs defaultValue="outline" className="mt-6">
      <TabsList variant="line" className="w-full justify-start gap-1 border-b border-border">
        <TabsTrigger value="outline">📘 课程大纲</TabsTrigger>
        <TabsTrigger value="cohort">📅 班次详情</TabsTrigger>
        <TabsTrigger value="review">⭐ 课程评价 ({reviews.length})</TabsTrigger>
        <TabsTrigger value="mind">🧠 思维导图</TabsTrigger>
      </TabsList>

      <TabsContent value="outline" className="pt-4">
        {modulesLoading ? (
          <div className="space-y-3" aria-hidden="true">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-16 animate-pulse rounded-xl border-2 border-border bg-muted" />
            ))}
          </div>
        ) : (
          <CourseDetailSyllabus cohortName={cohort?.cohort_name ?? series.series_name} modules={modules} />
        )}
      </TabsContent>

      <TabsContent value="cohort" className="pt-4">
        <CohortDetailPanel cohort={cohort} />
      </TabsContent>

      <TabsContent value="review" className="pt-4">
        <ReviewList reviews={reviews} />
      </TabsContent>

      <TabsContent value="mind" className="pt-4">
        <CourseMindmapView state={mindmapState} />
      </TabsContent>
    </Tabs>
  );
}
