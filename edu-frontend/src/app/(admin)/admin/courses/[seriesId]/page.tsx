/**
 * 管理端 · 系列详情（/admin/courses/[seriesId]，task03）
 *  - 系列概要（GET /series/{id} 主表信息）
 *  - ModuleTree：模块/课次/班次管理 + 视频四步流 + 课件重定向提示（GET /series/{id}/tree）
 */
"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, BookOpen } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ModuleTree } from "@/components/admin/ModuleTree";
import { ErrorState, LoadingState } from "@/components/admin/controls";
import {
  getAdminSeriesDetail,
  levelLabel,
  saleStatusLabel,
  subjectLabel,
} from "@/lib/api/admin/courses";

export default function AdminSeriesDetailPage({
  params,
}: {
  params: Promise<{ seriesId: string }>;
}) {
  const resolved = use(params);
  const seriesId = Number(resolved.seriesId);
  const valid = Number.isFinite(seriesId) && seriesId > 0;

  const detailQ = useQuery({
    queryKey: ["admin", "series", seriesId, "detail"] as const,
    queryFn: () => getAdminSeriesDetail(seriesId),
    enabled: valid,
    staleTime: 30_000,
  });

  if (!valid) {
    return <ErrorState message="无效的系列 ID" />;
  }

  if (detailQ.isLoading) return <LoadingState label="加载系列详情…" />;
  if (detailQ.isError || !detailQ.data) {
    return (
      <ErrorState
        message={detailQ.error instanceof Error ? detailQ.error.message : "系列详情加载失败"}
        onRetry={() => detailQ.refetch()}
      />
    );
  }

  const series = detailQ.data.series;

  return (
    <div className="space-y-5">
      <Link
        href="/admin/courses"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600"
      >
        <ArrowLeft className="h-4 w-4" /> 返回课程列表
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex min-w-0 items-start gap-3">
          <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-slate-700 to-indigo-600 text-white">
            <BookOpen className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-slate-900">{series.series_name}</h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono">{series.series_code}</code>
              <Badge variant="outline">{subjectLabel(series.subject_code)}</Badge>
              <Badge variant="outline">{levelLabel(series.level_code)} · {series.level_name}</Badge>
              <Badge variant={series.sale_status === "on_sale" ? "default" : "outline"}>
                {saleStatusLabel(series.sale_status)}
              </Badge>
              <span>目标 {series.target_hours} 小时</span>
            </div>
            {series.description && (
              <p className="mt-2 max-w-2xl text-sm text-slate-600">{series.description}</p>
            )}
          </div>
        </div>
      </div>

      <ModuleTree series={series} />
    </div>
  );
}
