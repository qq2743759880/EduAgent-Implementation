/**
 * 管理端 · 系列详情（/admin/courses/[seriesId]，task57 重构）
 *  - 系列信息卡：GET /api/admin/courses/series/{id}（单个 SeriesResponseAdmin，无旧 subject_code/level_code/target_hours）
 *  - ModuleTree：选中班次 → 模块 Accordion → 课次 四级 CRUD + 视频分片上传/转码轮询
 *  - 风格 candy-playful：清 task03 遗留 slate 灰系，色全部走语义 token（border-border/bg-card/text-foreground/badge candy 系）
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
  deliveryModeLabel,
  saleStatusLabel,
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

  const series = detailQ.data;

  return (
    <div className="space-y-5">
      <Link
        href="/admin/courses"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="h-4 w-4" /> 返回课程列表
      </Link>

      {/* 系列信息卡 */}
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-border bg-card p-5">
        <div className="flex min-w-0 items-start gap-3">
          <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-candy-purple text-primary-foreground">
            <BookOpen className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-foreground">{series.series_name}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">{series.series_code}</code>
              {deliveryBadge(series.delivery_mode)}
              {saleBadge(series.sale_status)}
              <span>机构 #{series.institution_id}</span>
            </div>
            {series.description && (
              <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{series.description}</p>
            )}
          </div>
        </div>
      </div>

      <ModuleTree series={series} />
    </div>
  );
}

function saleBadge(status: string) {
  if (status === "on_sale") return <Badge className="border-transparent bg-candy-green-soft text-candy-green">在售</Badge>;
  if (status === "draft") return <Badge className="border-transparent bg-muted text-muted-foreground">草稿</Badge>;
  return <Badge className="border-dashed bg-muted/50 text-muted-foreground">已下架</Badge>;
}

function deliveryBadge(mode: string) {
  const classes: Record<string, string> = {
    online_live: "border-transparent bg-candy-blue/10 text-candy-blue",
    online_recorded: "border-transparent bg-candy-purple/10 text-candy-purple",
    offline_face_to_face: "border-transparent bg-candy-orange/10 text-candy-orange",
  };
  const cls = classes[mode] ?? "border-transparent bg-muted text-muted-foreground";
  return <Badge className={cls}>{deliveryModeLabel(mode)}</Badge>;
}

export { saleStatusLabel, deliveryModeLabel };