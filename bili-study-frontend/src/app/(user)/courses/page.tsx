"use client";

import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { SearchX } from "lucide-react";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { CourseCard } from "@/components/curriculum/CourseCard";
import { CourseHero } from "@/components/curriculum/CourseHero";
import { CourseSearchInput } from "@/components/curriculum/CourseSearchInput";
import {
  CourseCatalogFilter,
  DEFAULT_FILTER,
  type CourseFilterValue,
} from "@/components/curriculum/CourseCatalogFilter";
import { listSeries, type SeriesListItem } from "@/lib/api/curriculum";
import { parsePriceRange } from "@/lib/curriculum-catalog";

const PAGE_SIZE = 15;

export default function CoursesHomePage() {
  const [filters, setFilters] = useState<CourseFilterValue>(DEFAULT_FILTER);
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, isError, error, refetch } = useQuery({
    // queryKey 含全部筛选参数：一级/二级学科、交付、价格、排序、关键词、页码
    queryKey: ["series_list", filters, keyword, page] as const,
    async queryFn() {
      const { min, max } = parsePriceRange(filters.price);
      // 二级方向选中时覆盖一级（后端 category 为分类名模糊匹配）
      const category = filters.direction || filters.category || undefined;
      return listSeries({
        category,
        delivery_mode:
          filters.delivery !== "any"
            ? (filters.delivery as SeriesListItem["delivery_mode"])
            : undefined,
        keyword: keyword || undefined,
        price_min: min,
        price_max: max,
        sort: filters.sort,
        page,
        page_size: PAGE_SIZE,
      });
    },
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  });

  // 契约②（C-B）：listSeries 返回外层 {total,page,page_size,items}，不再消费 page_meta 兼容字段
  const items: SeriesListItem[] = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageSize = data?.page_size ?? PAGE_SIZE;
  const currentPage = data?.page ?? page;

  const onFiltersChange = useCallback((next: CourseFilterValue) => {
    setFilters(next);
    setPage(1);
  }, []);

  const onKeywordChange = useCallback((kw: string) => {
    setKeyword(kw);
    setPage(1);
  }, []);

  return (
    <div className="min-h-screen bg-candy-bg">
      <main className="mx-auto w-full max-w-6xl px-4 pb-24 pt-6 md:px-6 lg:px-8">
        <div className="mb-1 flex flex-wrap items-center gap-3">
          <h1 className="font-heading text-[1.75rem] font-extrabold tracking-tight text-foreground">
            课程中心
          </h1>
          <span className="rounded-full border border-candy-purple/40 bg-candy-purple-soft px-2.5 py-0.5 text-3xs font-bold text-candy-purple">
            契约② GET /api/series · 两级导航 · 学中玩
          </span>
        </div>
        <p className="mb-4 text-2xs text-muted-foreground">
          一级学科大类 → 二级课程方向 · 筛选即重查 · 关键词防抖 400ms · 仅 on_sale · 价格=min_price「¥X 起」
        </p>

        <CourseHero />

        <div className="mt-5">
          <CourseSearchInput value={keyword} onDebouncedChange={onKeywordChange} />
        </div>

        <div className="mt-4">
          <CourseCatalogFilter value={filters} onChange={onFiltersChange} />
        </div>

        <div className="mb-3 mt-5 flex items-center gap-2 text-2xs text-muted-foreground" aria-live="polite">
          {isLoading ? (
            <>
              <span
                aria-hidden="true"
                className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-border border-t-candy-green"
              />
              查询中…
            </>
          ) : (
            <>
              共 <b className="font-bold text-foreground">{total.toLocaleString()}</b> 门课程
            </>
          )}
        </div>

        {isLoading ? (
          <CardGridLoading />
        ) : isError ? (
          <ErrorState
            title="加载失败"
            message={error instanceof Error ? error.message : "网络似乎开小差了，请稍后重试"}
            retry={() => refetch()}
          />
        ) : items.length === 0 ? (
          <EmptyState
            icon={<SearchX />}
            title="没有符合条件的课程"
            description="换一个关键词或筛选条件再试试"
          />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((s) => (
                <CourseCard key={s.id} data={s} />
              ))}
            </div>
            <div className="mt-6">
              <Pagination
                page={currentPage}
                pageSize={pageSize}
                total={total}
                onPageChange={setPage}
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function CardGridLoading() {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="overflow-hidden rounded-2xl border-2 border-border bg-card"
        >
          <div className="aspect-video animate-pulse bg-muted" />
          <div className="space-y-2 p-3.5">
            <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
            <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
            <div className="h-3 w-full animate-pulse rounded bg-muted" />
          </div>
        </div>
      ))}
    </div>
  );
}
