"use client";

import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { BookOpen, Flame, Search as SearchIcon, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
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

const PAGE_SIZE = 12;

export default function CoursesHomePage() {
  const [filters, setFilters] = useState<SubjectLevelFiltersValue>({
    subject: "all",
    level: "all",
  });

  const [page, setPage] = useState(1);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["series_list", filters, page] as const,
    async queryFn() {
      return listSeries({
        subject_code: filters.subject,
        level_code: filters.level,
        keyword: filters.q,
        min_price: filters.min_price,
        max_price: filters.max_price,
        page,
        page_size: PAGE_SIZE,
      });
    },
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  });

  const items: SeriesSummary[] = data?.items ?? [];
  const pageMeta = data?.page_meta ?? {
    page,
    page_size: PAGE_SIZE,
    total: items.length,
    total_pages: Math.max(1, Math.ceil(items.length / PAGE_SIZE)),
  };

  const onFiltersChange = useCallback(
    (next: SubjectLevelFiltersValue) => {
      setFilters(next);
      setPage(1);
    },
    [],
  );

  const heroStats = useMemo(() => {
    return [
      { label: "分级系列", value: SUBJECT_OPTIONS.length + " 大学科", Icon: BookOpen },
      { label: "阶梯难度", value: LEVEL_OPTIONS.length + " 级进阶", Icon: Sparkles },
      { label: "学员口碑", value: "4.8 平均评分", Icon: Flame },
    ] as const;
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-white">
      <HeroSection stats={heroStats} />

      <main className="mx-auto w-full max-w-7xl px-4 pb-24 pt-6 md:px-6 lg:px-8">
        <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-5">
            <SubjectLevelFilters
              value={filters}
              onChange={onFiltersChange}
              showSearch
              showPrice
            />
            <div className="hidden rounded-2xl border bg-gradient-to-br from-primary/5 via-primary/2 to-transparent p-5 lg:block">
              <div className="text-xs font-semibold uppercase tracking-wider text-primary">
                不知道学什么？
              </div>
              <div className="mt-1.5 text-base font-semibold">免费做学习水平测评</div>
              <p className="mt-1 text-sm text-muted-foreground">
                5 分钟定位当前水平，AI 自动推荐下一步路径与目标课程。
              </p>
              <Button asChild className="mt-4 w-full" size="sm">
                <Link href="/courses/search">
                  <SearchIcon className="mr-1.5 h-4 w-4" /> 去匹配课程
                </Link>
              </Button>
            </div>
          </aside>

          <section className="space-y-6">
            <ResultHeader
              pageMeta={pageMeta}
              filters={filters}
              loading={isLoading}
            />

            {isLoading ? (
              <CardGridLoading />
            ) : isError ? (
              <ErrorState onRetry={() => refetch()} error={error} />
            ) : items.length === 0 ? (
              <EmptyState />
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {items.map((s, i) => (
                    <CourseCard key={s.id ?? `series-${i}`} data={s} />
                  ))}
                </div>

                {pageMeta.total_pages > 1 && (
                  <div className="pt-4">
                    <PaginationBar
                      page={page}
                      total_pages={pageMeta.total_pages}
                      onChange={setPage}
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

function HeroSection({
  stats,
}: {
  stats: ReadonlyArray<{ label: string; value: string; Icon: React.ComponentType<{ className?: string }> }>;
}) {
  return (
    <section className="relative overflow-hidden bg-gradient-to-br from-indigo-600 via-violet-600 to-sky-600 text-white">
      <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:radial-gradient(ellipse_at_top_left,rgba(255,255,255,0.6),transparent_55%),radial-gradient(ellipse_at_bottom_right,rgba(255,255,255,0.5),transparent_60%)]" />
      <div className="mx-auto w-full max-w-7xl px-4 py-14 md:px-6 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-[1.3fr_1fr] lg:items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/10 px-3 py-1 text-xs backdrop-blur-sm">
              <Sparkles className="h-3.5 w-3.5" />
              AI 驱动 · 分级自适应 · 11 个系列 66+ 课次
            </div>
            <h1 className="mt-4 text-3xl font-bold tracking-tight md:text-4xl">
              找到最适合你的 <span className="underline decoration-amber-300 decoration-[6px] decoration-4 underline-offset-[1px]">分级课程</span>
            </h1>
            <p className="mt-3 max-w-xl text-sm text-white/85 md:text-base">
              按学科 × 难度 L1–L5 分层，搭配学习路径图谱、互动习题和 AI 问答助手，
              从入门到精通一路陪你。
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button asChild size="lg" className="bg-white text-primary hover:bg-white/90">
                <Link href="/courses/search">
                  <SearchIcon className="mr-1.5 h-4 w-4" /> 搜索课程
                </Link>
              </Button>
              <Button
                asChild
                size="lg"
                variant="outline"
                className="border-white/50 bg-white/10 text-white hover:bg-white/20"
              >
                <Link href="/dashboard">我的学习</Link>
              </Button>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            {stats.map(({ label, value, Icon }) => (
              <div
                key={label}
                className="flex items-center gap-4 rounded-2xl border border-white/20 bg-white/10 p-4 backdrop-blur-sm"
              >
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-white/20">
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <div className="text-xs text-white/80">{label}</div>
                  <div className="text-lg font-semibold">{value}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function ResultHeader({
  pageMeta,
  filters,
  loading,
}: {
  pageMeta: { page: number; page_size: number; total: number; total_pages: number };
  filters: SubjectLevelFiltersValue;
  loading: boolean;
}) {
  const tokens: string[] = [];
  if (filters.q) tokens.push(`关键词「${filters.q}」`);
  if (filters.subject !== "all") {
    const s = SUBJECT_OPTIONS.find((x) => x.code === filters.subject);
    if (s) tokens.push(s.name);
  }
  if (filters.level !== "all") tokens.push(filters.level);
  if (typeof filters.min_price === "number" || typeof filters.max_price === "number") {
    tokens.push(
      `价格 ¥${filters.min_price ?? 0} – ¥${filters.max_price ?? "不限"}`,
    );
  }
  const label = tokens.length ? tokens.join(" · ") : "全部课程";

  return (
    <div className="flex flex-wrap items-end justify-between gap-2">
      <div>
        <h2 className="text-lg font-semibold md:text-xl">
          {loading ? "加载中…" : `共找到 ${pageMeta.total.toLocaleString()} 门课程`}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">筛选条件：{label}</p>
      </div>
      <div className="text-xs text-muted-foreground">
        第 {pageMeta.page}/{Math.max(1, pageMeta.total_pages)} 页 · 每页 {pageMeta.page_size} 条
      </div>
    </div>
  );
}

function CardGridLoading() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-72 animate-pulse rounded-2xl border bg-white p-3">
          <div className="h-40 w-full rounded-xl bg-slate-100" />
          <div className="mt-4 h-4 w-2/3 rounded bg-slate-100" />
          <div className="mt-2 h-3 w-full rounded bg-slate-100" />
          <div className="mt-2 h-3 w-1/2 rounded bg-slate-100" />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl border border-dashed p-10 text-center">
      <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-2xl bg-primary/10 text-primary">
        <SearchIcon className="h-6 w-6" />
      </div>
      <div className="text-base font-semibold">没找到匹配的课程</div>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
        试试减少筛选条件、清空关键词，或降低难度区间看看～
      </p>
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
    <div className="rounded-2xl border border-rose-200 bg-rose-50/50 p-6">
      <div className="text-base font-semibold text-rose-700">加载失败</div>
      <p className="mt-1 text-sm text-rose-600/90">{msg}</p>
      <Button variant="outline" size="sm" className="mt-3 border-rose-300 text-rose-700 hover:bg-rose-100" onClick={onRetry}>
        点击重试
      </Button>
    </div>
  );
}
