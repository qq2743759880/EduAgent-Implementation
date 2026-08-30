"use client";

/**
 * Skeleton — 骨架屏加载占位组件（Phase 4 用户体验）
 *
 * 面试考点：
 * - 骨架屏 vs Spinner：骨架屏减少用户感知等待时间（预期管理）
 * - 作业帮/猿辅导都在用：课程列表、题库列表、个人中心都用 Skeleton
 * - 用 Tailwind animate-pulse 实现简单骨架动画
 *
 * 用法：
 *   <Skeleton className="h-6 w-48" />          // 单行文本占位
 *   <Skeleton className="h-32 w-full" />        // 卡片占位
 *   <Skeleton className="h-10 w-10 rounded-full" /> // 头像占位
 */
import { type HTMLAttributes } from "react";

export function Skeleton({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`animate-pulse rounded-md bg-gray-200 ${className}`}
      aria-hidden="true"
      {...props}
    />
  );
}

/**
 * CourseCardSkeleton — 课程卡片骨架屏
 */
export function CourseCardSkeleton() {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <Skeleton className="mb-3 h-40 w-full rounded-lg" />
      <Skeleton className="mb-2 h-5 w-3/4" />
      <Skeleton className="mb-2 h-4 w-full" />
      <Skeleton className="h-4 w-1/2" />
      <div className="mt-3 flex items-center gap-2">
        <Skeleton className="h-8 w-8 rounded-full" />
        <Skeleton className="h-4 w-20" />
      </div>
    </div>
  );
}

/**
 * CardSkeleton — 通用卡片骨架屏
 */
export function CardSkeleton() {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-6 shadow-sm">
      <Skeleton className="mb-4 h-6 w-1/3" />
      <Skeleton className="mb-2 h-4 w-full" />
      <Skeleton className="mb-2 h-4 w-5/6" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

/**
 * TableSkeleton — 表格骨架屏
 */
export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200">
      {/* 表头 */}
      <div className="flex gap-4 border-b border-gray-100 bg-gray-50 px-4 py-3">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-4 flex-1" />
        ))}
      </div>
      {/* 数据行 */}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div key={rowIdx} className="flex gap-4 border-b border-gray-50 px-4 py-3">
          {Array.from({ length: cols }).map((_, colIdx) => (
            <Skeleton key={colIdx} className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * DashboardSkeleton — 仪表盘骨架屏
 */
export function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      {/* KPI 卡片行 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
      {/* 图表区域 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Skeleton className="h-64 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    </div>
  );
}