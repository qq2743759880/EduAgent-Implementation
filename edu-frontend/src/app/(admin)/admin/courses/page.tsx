/**
 * 管理端 · 课程总览（/admin/courses，task56 重构）
 *  - 系列列表：GET /api/admin/courses/series（keyword / delivery_mode / sale_status / sort + 分页）
 *  - 创建/编辑：SeriesForm（POST /series · PATCH /series/{id}，institution_id+delivery_mode 契约）
 *  - 上架/下架：PATCH /series/{id} { sale_status }（on_sale/off_sale）
 *  - 软删：DELETE /series/{id}（series 表无 yn 列 → 置 off_sale，『下架优先于删除』confirm 提示）
 *  - 行操作下拉：编辑 / 班次(→ /admin/courses/{id}，task57) / 上架|下架 / 删除
 *  - RBAC：非 admin 由 (admin)/layout.tsx AdminGuard 拦截（本页不重复）
 */
"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { BookOpen, Eye, EyeOff, Layers, MoreHorizontal, Plus, Search, Trash2, PencilLine } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { SeriesForm } from "@/components/admin/SeriesForm";
import { ErrorState, EmptyState, LoadingState, NativeSelect } from "@/components/admin/controls";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";
import {
  DELIVERY_MODE_OPTIONS,
  SALE_STATUS_OPTIONS,
  SERIES_SORT_OPTIONS,
  deleteAdminSeries,
  deliveryModeLabel,
  listAdminSeries,
  saleStatusLabel,
  updateAdminSeries,
  type AdminSeriesListItem,
  type DeliveryModeCode,
  type SaleStatusCode,
  type SeriesSortCode,
} from "@/lib/api/admin/courses";

const PAGE_SIZE = 10;

export default function AdminCoursesPage() {
  const queryClient = useQueryClient();
  const [deliveryMode, setDeliveryMode] = useState<DeliveryModeCode | "">("");
  const [saleStatus, setSaleStatus] = useState<SaleStatusCode | "">("");
  const [sort, setSort] = useState<SeriesSortCode | "">("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<AdminSeriesListItem | null>(null);
  const [delTarget, setDelTarget] = useState<AdminSeriesListItem | null>(null);
  const [offTarget, setOffTarget] = useState<AdminSeriesListItem | null>(null);

  // perf F1：关键词 300ms 防抖后进 queryKey（applied 快照）
  const appliedKeyword = useDebouncedValue(keyword, 300);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "courses", "series", { delivery_mode: deliveryMode || undefined, sale_status: saleStatus || undefined, sort: sort || undefined, keyword: appliedKeyword || undefined, page }] as const,
    async queryFn() {
      return listAdminSeries({
        delivery_mode: deliveryMode || undefined,
        sale_status: saleStatus || undefined,
        sort: sort || undefined,
        keyword: appliedKeyword || undefined,
        page,
        page_size: PAGE_SIZE,
      });
    },
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "courses", "series"] });

  const saleMutation = useMutation({
    mutationFn: ({ id, sale_status }: { id: number; sale_status: "on_sale" | "off_sale" }) =>
      updateAdminSeries(id, { sale_status }),
    onSuccess: (_d, vars) => {
      toast.success(vars.sale_status === "off_sale" ? "系列已下架" : "系列已上架");
      invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteAdminSeries(id),
    onSuccess: () => {
      toast.success("系列已删除（软删为下架）");
      invalidate();
    },
  });

  const totalPages = Math.max(1, data?.page_meta?.total_pages ?? 1);

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">课程管理</h1>
          <p className="text-sm text-muted-foreground">系列 → 班次 · 上下架与软删 · 来源 /api/admin/courses/series</p>
        </div>
        <Button onClick={() => { setEditing(null); setFormOpen(true); }}>
          <Plus className="mr-1.5 h-4 w-4" /> 新建系列
        </Button>
      </div>

      {/* 筛选栏 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-border bg-card p-3">
        <div className="w-full min-w-0 flex-1">
          <label htmlFor="filter-keyword" className="mb-1 block text-xs text-muted-foreground">搜索</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="filter-keyword"
              className="pl-8"
              value={keyword}
              placeholder="系列名称 / 编码"
              onChange={(e) => { setKeyword(e.target.value); setPage(1); }}
            />
          </div>
        </div>
        <div className="w-full sm:w-40">
          <label htmlFor="filter-dm" className="mb-1 block text-xs text-muted-foreground">交付模式</label>
          <NativeSelect id="filter-dm" value={deliveryMode} onChange={(e) => { setDeliveryMode(e.target.value as DeliveryModeCode | ""); setPage(1); }}>
            <option value="">全部交付</option>
            {DELIVERY_MODE_OPTIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-36">
          <label htmlFor="filter-ss" className="mb-1 block text-xs text-muted-foreground">状态</label>
          <NativeSelect id="filter-ss" value={saleStatus} onChange={(e) => { setSaleStatus(e.target.value as SaleStatusCode | ""); setPage(1); }}>
            <option value="">全部状态</option>
            {SALE_STATUS_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-40">
          <label htmlFor="filter-sort" className="mb-1 block text-xs text-muted-foreground">排序</label>
          <NativeSelect id="filter-sort" value={sort} onChange={(e) => { setSort(e.target.value as SeriesSortCode | ""); setPage(1); }}>
            <option value="">默认排序</option>
            {SERIES_SORT_OPTIONS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </NativeSelect>
        </div>
        <Button variant="outline" onClick={() => { setDeliveryMode(""); setSaleStatus(""); setSort(""); setKeyword(""); setPage(1); }}>
          重置
        </Button>
      </div>

      <div className="text-sm text-muted-foreground">共 <b className="text-foreground">{data?.page_meta?.total ?? 0}</b> 个系列</div>

      {/* 列表三态 + DataTable */}
      {isLoading && !data ? (
        <LoadingState label="加载系列…" />
      ) : isError ? (
        <ErrorState message={error instanceof Error ? error.message : "系列加载失败"} onRetry={() => refetch()} />
      ) : (data?.items?.length ?? 0) === 0 ? (
        <EmptyState message="暂无系列" hint="点击右上角「新建系列」开始搭建课程" />
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-border bg-card">
            <table className="w-full min-w-[560px] border-collapse text-sm" data-testid="series-table">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-3 font-medium">系列</th>
                  <th className="px-4 py-3 font-medium">交付模式</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="hidden px-4 py-3 font-medium md:table-cell">创建时间</th>
                  <th className="px-4 py-3 pr-5 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {data!.items.map((s) => (
                  <tr key={s.id} className="border-b border-border last:border-0" data-testid="series-row">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-candy-purple text-primary-foreground">
                          <BookOpen className="h-4 w-4" />
                        </span>
                        <div className="min-w-0">
                          <div className="font-medium text-foreground">{s.series_name}</div>
                          <code className="font-mono text-xs text-muted-foreground">{s.series_code}</code>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">{deliveryBadge(s.delivery_mode)}</td>
                    <td className="px-4 py-3">{saleBadge(s.sale_status)}</td>
                    <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">{s.created_at.slice(0, 10)}</td>
                    <td className="px-4 py-3 pr-5 text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={
                            <Button variant="ghost" size="icon" aria-label="系列操作" data-testid={`menu-${s.id}`} />
                          }
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem onSelect={() => { setEditing(s); setFormOpen(true); }} data-testid={`edit-${s.id}`}>
                            <PencilLine className="mr-2 h-4 w-4" /> 编辑
                          </DropdownMenuItem>
                          <DropdownMenuItem render={<Link href={`/admin/courses/${s.id}`} data-testid={`cohorts-${s.id}`} />}>
                            <Layers className="mr-2 h-4 w-4" /> 班次
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {s.sale_status === "off_sale" ? (
                            <DropdownMenuItem disabled={isBusy(saleMutation, s.id)} onSelect={() => saleMutation.mutate({ id: s.id, sale_status: "on_sale" })} data-testid={`on-${s.id}`}>
                              <Eye className="mr-2 h-4 w-4" /> 上架
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem disabled={isBusy(saleMutation, s.id)} onSelect={() => setOffTarget(s)} data-testid={`off-${s.id}`}>
                              <EyeOff className="mr-2 h-4 w-4" /> 下架
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuItem disabled={isBusy(deleteMutation, s.id)} destructive onSelect={() => setDelTarget(s)} data-testid={`del-${s.id}`}>
                            <Trash2 className="mr-2 h-4 w-4" /> 删除
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && <PaginationBar page={page} total_pages={totalPages} onChange={setPage} />}
        </>
      )}

      <SeriesForm open={formOpen} onOpenChange={setFormOpen} series={editing} onSaved={() => setEditing(null)} />

      {/* 下架确认（影响用户端可见性的破坏性操作，二次确认） */}
      <ConfirmDialog
        open={Boolean(offTarget)}
        onOpenChange={(o) => !o && setOffTarget(null)}
        title="下架系列"
        description={offTarget ? `确定下架「${offTarget.series_name}」吗？下架后用户端不再展示该系列，可随时再上架。` : ""}
        confirmLabel="确认下架"
        variant="danger"
        onConfirm={() => { if (offTarget) saleMutation.mutate({ id: offTarget.id, sale_status: "off_sale" }); setOffTarget(null); }}
      />

      {/* 删除确认（下架优先于删除：软删置 off_sale） */}
      <ConfirmDialog
        open={Boolean(delTarget)}
        onOpenChange={(o) => !o && setDelTarget(null)}
        title="删除系列"
        description={delTarget ? `删除「${delTarget.series_name}」？下架优先于删除：删除为软删，将把该系列置为「已下架」，用户端不再展示。` : ""}
        confirmLabel="删除（软删）"
        variant="danger"
        onConfirm={() => { if (delTarget) deleteMutation.mutate(delTarget.id); setDelTarget(null); }}
      />
    </div>
  );
}

/* ---------------- 小型子组件 ---------------- */

function saleBadge(status: SaleStatusCode) {
  if (status === "on_sale") return <Badge className="border-transparent bg-candy-green-soft text-candy-green">在售</Badge>;
  if (status === "draft") return <Badge className="border-transparent bg-muted text-muted-foreground">草稿</Badge>;
  return <Badge className="border-dashed bg-muted/50 text-muted-foreground">已下架</Badge>;
}

function deliveryBadge(mode: string) {
  const classes: Record<string, string> = {
    online_live: "bg-candy-blue/10 text-candy-blue",
    online_recorded: "bg-candy-purple/10 text-candy-purple",
    offline_face_to_face: "bg-candy-orange/10 text-candy-orange",
  };
  return <Badge className={`border-transparent ${classes[mode] ?? "bg-muted text-muted-foreground"}`}>{deliveryModeLabel(mode)}</Badge>;
}

function isBusy(m: { isPending: boolean; variables?: unknown }, id: number): boolean {
  if (!m.isPending) return false;
  const v = m.variables as { id?: number } | number | undefined;
  if (typeof v === "number") return v === id;
  return v?.id === id;
}

function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  variant,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  variant?: "danger";
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button variant={variant === "danger" ? "destructive" : "default"} onClick={onConfirm}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export { saleStatusLabel, deliveryModeLabel };