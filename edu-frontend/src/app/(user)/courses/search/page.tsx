"use client";

import { useCallback, useEffect, useMemo, useState, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Search as SearchIcon, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CourseCard } from "@/components/curriculum/CourseCard";
import {
  SubjectLevelFilters,
  type SubjectLevelFiltersValue,
} from "@/components/curriculum/SubjectLevelFilters";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import {
  LEVEL_OPTIONS,
  SUBJECT_OPTIONS,
  listSeries,
  type SeriesSummary,
} from "@/lib/api/curriculum";
import { CourseSearchSchema, type CourseSearchInput } from "@/lib/validators/curriculum";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 12;

export default function CoursesSearchPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-[70vh] flex items-center justify-center text-sm text-muted-foreground">
          正在加载搜索条件…
        </div>
      }
    >
      <CoursesSearchPageInner />
    </Suspense>
  );
}

function CoursesSearchPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  /* 把 URL query 解析为安全的 CourseSearchInput（Zod 校验） */
  const parsed = useMemo<CourseSearchInput>(() => {
    const obj: Record<string, string | undefined> = {
      q: searchParams.get("q") ?? undefined,
      subject: searchParams.get("subject") ?? undefined,
      level: searchParams.get("level") ?? undefined,
      min_price: searchParams.get("min_price") ?? undefined,
      max_price: searchParams.get("max_price") ?? undefined,
      page: searchParams.get("page") ?? undefined,
      page_size: searchParams.get("page_size") ?? undefined,
    };
    const res = CourseSearchSchema.safeParse(obj);
    return res.success ? res.data : CourseSearchSchema.parse({});
  }, [searchParams]);

  const filters: SubjectLevelFiltersValue = {
    q: parsed.q,
    subject: parsed.subject as SubjectLevelFiltersValue["subject"],
    level: parsed.level as SubjectLevelFiltersValue["level"],
    min_price: parsed.min_price,
    max_price: parsed.max_price,
  };
  const page = parsed.page;
  const pageSize = parsed.page_size ?? PAGE_SIZE;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["series_list", filters, page, pageSize] as const,
    async queryFn() {
      return listSeries({
        subject_code: filters.subject,
        level_code: filters.level,
        keyword: filters.q,
        min_price: filters.min_price,
        max_price: filters.max_price,
        page,
        page_size: pageSize,
      });
    },
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  });

  const items: SeriesSummary[] = data?.items ?? [];
  const pageMeta = data?.page_meta ?? {
    page,
    page_size: pageSize,
    total: items.length,
    total_pages: Math.max(1, Math.ceil(items.length / pageSize)),
  };

  const pushUrl = useCallback(
    (next: Partial<CourseSearchInput>) => {
      const merged: CourseSearchInput = {
        ...CourseSearchSchema.parse({}),
        q: parsed.q,
        subject: parsed.subject,
        level: parsed.level,
        min_price: parsed.min_price,
        max_price: parsed.max_price,
        page: parsed.page,
        page_size: parsed.page_size,
        ...next,
      };
      const sp = new URLSearchParams();
      if (merged.q && merged.q.trim()) sp.set("q", merged.q.trim());
      if (merged.subject && merged.subject !== "all") sp.set("subject", merged.subject);
      if (merged.level && merged.level !== "all") sp.set("level", merged.level);
      if (typeof merged.min_price === "number") sp.set("min_price", String(merged.min_price));
      if (typeof merged.max_price === "number") sp.set("max_price", String(merged.max_price));
      sp.set("page", String(merged.page));
      sp.set("page_size", String(merged.page_size ?? PAGE_SIZE));
      router.replace(`/courses/search?${sp.toString()}`, { scroll: true });
    },
    [router, parsed],
  );

  const onFiltersChange = useCallback(
    (next: SubjectLevelFiltersValue) => {
      pushUrl({
        q: next.q,
        subject: next.subject as CourseSearchInput["subject"],
        level: next.level as CourseSearchInput["level"],
        min_price: next.min_price,
        max_price: next.max_price,
        page: 1,
      });
    },
    [pushUrl],
  );

  /* 兼容 filters 与 URL 不同步（本地表单未 submit）时，不重复刷新 */
  const [localFilters, setLocalFilters] = useState<SubjectLevelFiltersValue>(filters);
  useEffect(() => {
    setLocalFilters(filters);
  }, [filters]);

  const appliedChips = useMemo(() => {
    return buildChips(localFilters);
  }, [localFilters]);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border bg-card/80 backdrop-blur-md">
        <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-6 lg:px-8">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Link className="hover:text-foreground" href="/courses">
              课程首页
            </Link>
            <span>/</span>
            <span className="text-foreground">搜索结果</span>
          </div>
          <h1 className="mt-2 text-2xl font-semibold md:text-3xl">
            {parsed.q ? `搜索结果：${parsed.q}` : "搜索课程"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            共 {pageMeta.total.toLocaleString()} 条结果（第 {pageMeta.page}/
            {Math.max(1, pageMeta.total_pages)} 页）
          </p>

          {appliedChips.length > 0 && (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                已应用：
              </span>
              {appliedChips.map((chip, i) => (
                <Badge key={i} variant="outline" className="px-2.5 py-1 text-xs">
                  {chip.label}
                  <button
                    type="button"
                    aria-label={`移除 ${chip.label} 筛选`}
                    onClick={() => pushUrl(chip.clear)}
                    className="ml-1.5 rounded-full p-0.5 text-muted-foreground hover:bg-foreground/10"
                  >
                    ×
                  </button>
                </Badge>
              ))}
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground"
                onClick={() => pushUrl({ subject: "all", level: "all", q: undefined, min_price: undefined, max_price: undefined, page: 1 })}
              >
                清空全部
              </Button>
            </div>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-4 pb-24 pt-6 md:px-6 lg:px-8">
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-5">
            <SubjectLevelFilters
              value={localFilters}
              onChange={onFiltersChange}
              showSearch
              showPrice
            />
          </aside>

          <section className="space-y-6">
            {isLoading ? (
              <CardGridLoading />
            ) : isError ? (
              <ErrorState onRetry={() => refetch()} error={error} />
            ) : items.length === 0 ? (
              <EmptyState onClear={() => pushUrl({ subject: "all", level: "all", q: undefined, min_price: undefined, max_price: undefined, page: 1 })} />
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {items.map((s, i) => (
                    <CourseCard key={s.id ?? `ss-${i}`} data={s} />
                  ))}
                </div>

                {pageMeta.total_pages > 1 && (
                  <div className="pt-4">
                    <PaginationBar
                      page={pageMeta.page}
                      total_pages={pageMeta.total_pages}
                      onChange={(p) => pushUrl({ page: p })}
                    />
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

function buildChips(
  filters: SubjectLevelFiltersValue,
): { label: string; clear: Partial<CourseSearchInput> }[] {
  const chips: { label: string; clear: Partial<CourseSearchInput> }[] = [];
  if (filters.q) {
    chips.push({
      label: `关键词：${filters.q}`,
      clear: { q: undefined, page: 1 },
    });
  }
  if (filters.subject !== "all") {
    const sub = SUBJECT_OPTIONS.find((s) => s.code === filters.subject);
    if (sub) {
      chips.push({
        label: `学科：${sub.name}`,
        clear: { subject: "all", page: 1 },
      });
    }
  }
  if (filters.level !== "all") {
    const lv = LEVEL_OPTIONS.find((x) => x.code === filters.level);
    chips.push({
      label: `级别：${lv?.name ?? filters.level}`,
      clear: { level: "all", page: 1 },
    });
  }
  if (typeof filters.min_price === "number" || typeof filters.max_price === "number") {
    chips.push({
      label: `价格：¥${filters.min_price ?? 0} – ¥${filters.max_price ?? "不限"}`,
      clear: { min_price: undefined, max_price: undefined, page: 1 },
    });
  }
  return chips;
}

function CardGridLoading() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-72 animate-pulse rounded-xl border border-border bg-muted/40 p-3">
          <div className="h-40 w-full rounded-xl bg-muted" />
          <div className="mt-4 h-4 w-2/3 rounded bg-muted" />
          <div className="mt-2 h-3 w-full rounded bg-muted" />
          <div className="mt-2 h-3 w-1/2 rounded bg-muted" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({ onClear }: { onClear: () => void }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-10 text-center">
      <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-xl bg-primary/10 text-primary">
        <SearchIcon className="h-6 w-6" />
      </div>
      <div className="text-base font-semibold text-foreground">没有匹配的课程</div>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
        试试清空筛选条件，或返回课程首页浏览推荐。
      </p>
      <div className="mt-4 flex items-center justify-center gap-2">
        <Button variant="outline" size="sm" onClick={onClear}>清空筛选</Button>
        <Button asChild size="sm">
          <Link href="/courses">返回课程首页</Link>
        </Button>
      </div>
    </div>
  );
}

function ErrorState({ onRetry, error }: { onRetry: () => void; error: unknown }) {
  const msg =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "加载失败，请稍后重试";
  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-6">
      <div className="text-base font-semibold text-destructive-foreground">加载失败</div>
      <p className="mt-1 text-sm text-destructive-foreground/90">{msg}</p>
      <Button variant="outline" size="sm" className="mt-3 border-destructive/30 text-destructive hover:bg-destructive/10" onClick={onRetry}>
        点击重试
      </Button>
    </div>
  );
}
