/**
 * 管理端 · 课程列表（/admin/courses，task03）
 *  - 系列列表：GET /api/admin/courses/series（subject/level/keyword 过滤 + 分页）
 *  - 创建/编辑系列：SeriesForm（POST /series · PATCH /series/{id}）
 *  - 下架/上架：PATCH /series/{id} { sale_status: "off_sale" | "on_sale" }（系列表无 yn 列，死接口 POST /series/{id}/yn 已删除）
 *  - 行点击进入系列详情（模块/课次/班次/视频）
 */
"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { BookOpen, Edit3, EyeOff, Plus, Search } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { SeriesForm } from "@/components/admin/SeriesForm";
import { ErrorState, EmptyState, LoadingState, NativeSelect } from "@/components/admin/controls";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";
import {
  ADMIN_LEVEL_OPTIONS,
  ADMIN_SUBJECT_OPTIONS,
  levelLabel,
  listAdminSeries,
  saleStatusLabel,
  subjectLabel,
  updateAdminSeries,
  type AdminSeriesItem,
} from "@/lib/api/admin/courses";

const PAGE_SIZE = 10;

export default function AdminCoursesPage() {
  const queryClient = useQueryClient();
  const [subject, setSubject] = useState("");
  const [level, setLevel] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<AdminSeriesItem | null>(null);

  // perf F1：关键词 300ms 防抖后进 queryKey（applied 快照），空串归一 undefined 减少无效 key 变体
  const appliedKeyword = useDebouncedValue(keyword, 300);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "series", { subject, level, keyword: appliedKeyword || undefined, page }] as const,
    async queryFn() {
      return listAdminSeries({ subject_code: subject, level_code: level, keyword: appliedKeyword || undefined, page, page_size: PAGE_SIZE });
    },
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  });

  // 列表响应无 yn 字段（后端 SeriesListItem 不暴露软删位），下架语义用 sale_status 表达
  const saleMutation = useMutation({
    mutationFn: ({ id, sale_status }: { id: number; sale_status: "on_sale" | "off_sale" }) =>
      updateAdminSeries(id, { sale_status }),
    onSuccess: (_d, vars) => {
      toast.success(vars.sale_status === "off_sale" ? "系列已下架" : "系列已上架");
      queryClient.invalidateQueries({ queryKey: ["admin", "series"] });
    },
  });

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">课程管理</h1>
          <p className="text-sm text-slate-500">系列 → 模块 → 课次 → 视频全链路管理</p>
        </div>
        <Button onClick={() => { setEditing(null); setFormOpen(true); }}>
          <Plus className="mr-1.5 h-4 w-4" /> 创建系列
        </Button>
      </div>

      {/* 过滤栏 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <div className="w-full sm:w-52">
          <label htmlFor="filter-subject" className="mb-1 block text-xs text-slate-500">学科</label>
          <NativeSelect id="filter-subject" value={subject} onChange={(e) => { setSubject(e.target.value); setPage(1); }}>
            <option value="">全部学科</option>
            {ADMIN_SUBJECT_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-40">
          <label htmlFor="filter-level" className="mb-1 block text-xs text-slate-500">难度</label>
          <NativeSelect id="filter-level" value={level} onChange={(e) => { setLevel(e.target.value); setPage(1); }}>
            <option value="">全部分级</option>
            {ADMIN_LEVEL_OPTIONS.map((l) => (
              <option key={l.value} value={l.value}>{l.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="min-w-0 flex-1">
          <label htmlFor="filter-keyword" className="mb-1 block text-xs text-slate-500">关键词</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              id="filter-keyword"
              className="pl-8"
              value={keyword}
              placeholder="系列名称 / 编码 / 简介"
              onChange={(e) => { setKeyword(e.target.value); setPage(1); }}
            />
          </div>
        </div>
        <Button variant="outline" onClick={() => { setSubject(""); setLevel(""); setKeyword(""); setPage(1); }}>
          重置
        </Button>
      </div>

      {/* 列表三态 */}
      {isLoading && !data ? (
        <LoadingState label="加载系列…" />
      ) : isError ? (
        <ErrorState message={error instanceof Error ? error.message : "系列加载失败"} onRetry={() => refetch()} />
      ) : (data?.items?.length ?? 0) === 0 ? (
        <EmptyState message="暂无系列" hint="点击右上角「创建系列」开始搭建课程" />
      ) : (
        <>
          <div className="space-y-2" data-testid="series-list">
            {data!.items.map((s) => (
              <SeriesRow
                key={s.id}
                series={s}
                onEdit={() => { setEditing(s); setFormOpen(true); }}
                onToggleSale={(sale_status) => {
                  // 对抗 #9：下架是影响用户端可见性的破坏性操作，需二次确认；上架为恢复操作不需要
                  if (sale_status === "off_sale"
                      && !window.confirm(`确定下架系列「${s.series_name}」吗？下架后用户端不再展示该课程。`)) {
                    return;
                  }
                  saleMutation.mutate({ id: s.id, sale_status });
                }}
                busy={saleMutation.isPending && saleMutation.variables?.id === s.id}
              />
            ))}
          </div>
          {totalPages > 1 && <PaginationBar page={page} total_pages={totalPages} onChange={setPage} />}
        </>
      )}

      <SeriesForm
        open={formOpen}
        onOpenChange={setFormOpen}
        series={editing}
        onSaved={() => setEditing(null)}
      />
    </div>
  );
}

function SeriesRow({
  series,
  onEdit,
  onToggleSale,
  busy,
}: {
  series: AdminSeriesItem;
  onEdit: () => void;
  onToggleSale: (sale_status: "on_sale" | "off_sale") => void;
  busy?: boolean;
}) {
  const offSale = series.sale_status === "off_sale";
  return (
    <div
      className={`group flex items-center justify-between gap-3 rounded-xl border bg-white px-4 py-3 transition-colors hover:border-indigo-200 hover:shadow-sm ${offSale ? "border-slate-200 opacity-70" : "border-slate-200"}`}
      data-testid="series-row"
    >
      <Link href={`/admin/courses/${series.id}`} className="flex min-w-0 flex-1 items-center gap-3">
        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-slate-700 to-indigo-600 text-white">
          <BookOpen className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-medium text-slate-800">{series.series_name}</span>
            {offSale && <Badge variant="destructive">已下架</Badge>}
            {series.sale_status === "draft" && (
              <Badge variant="outline">{saleStatusLabel(series.sale_status)}</Badge>
            )}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-600">
            <code className="font-mono">{series.series_code}</code>
            <span>{subjectLabel(series.subject_code)}</span>
            <span>{levelLabel(series.level_code)} · {series.level_name}</span>
            <span>{series.total_session_count} 课次</span>
            <span>{series.cohort_count} 班次</span>
          </div>
        </div>
      </Link>
      <div className="flex shrink-0 items-center gap-1">
        <Button variant="ghost" size="sm" onClick={onEdit} data-testid={`edit-${series.id}`}>
          <Edit3 className="mr-1 h-3.5 w-3.5" /> 编辑
        </Button>
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => onToggleSale(offSale ? "on_sale" : "off_sale")}
          data-testid={`sale-${series.id}`}
        >
          <EyeOff className="mr-1 h-3.5 w-3.5" />
          {offSale ? "上架" : "下架"}
        </Button>
      </div>
    </div>
  );
}
