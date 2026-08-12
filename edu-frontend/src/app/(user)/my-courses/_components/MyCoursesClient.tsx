/**
 * MyCoursesClient — 我的课程客户端逻辑
 *   - 保护路由：未登录 → login?redirect=
 *   - 加载 P3 /api/progress/courses，注入本地收藏夹字段
 *   - Tabs in_progress / completed / favorited
 *   - 收藏点击后：立即更新 __favorited 并重分类（无需再打后端）
 */
"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  BookMarked,
  GraduationCap,
  Heart,
  Loader2,
  RefreshCcw,
  Trophy,
} from "lucide-react";
import { useAuthStore } from "@/lib/auth-client";
import {
  favoriteSeriesIds,
  getMyCourses,
  setFavoriteSeries,
  type CourseProgressOut,
} from "@/lib/api/learning";
import { MyCourseCard } from "@/components/learning/MyCourseCard";
import { CourseTabsEmpty } from "@/components/learning/CourseTabsEmpty";
import { Badge } from "@/components/ui/badge";

type TabId = "in_progress" | "completed" | "favorited";

function clamp1(v: number | null | undefined): number {
  if (typeof v !== "number" || !Number.isFinite(v)) return 0;
  return Math.max(0, Math.min(1, v));
}

function withFavorites(list: CourseProgressOut[]): CourseProgressOut[] {
  const set = new Set(favoriteSeriesIds());
  return list.map((c) => ({ ...c, __favorited: set.has(c.series_id) }));
}

function groupIntoTabs(list: CourseProgressOut[]) {
  const in_progress: CourseProgressOut[] = [];
  const completed: CourseProgressOut[] = [];
  const favorited: CourseProgressOut[] = [];
  for (const c of list) {
    const overall = clamp1(c.overall_ratio);
    if (overall >= 0.9999) completed.push(c);
    else in_progress.push(c);
    if (c.__favorited) favorited.push(c);
  }
  // 最近活动优先
  const byActivity = (a: CourseProgressOut, b: CourseProgressOut) =>
    ts(b.last_activity_at) - ts(a.last_activity_at);
  in_progress.sort(byActivity);
  completed.sort(byActivity);
  favorited.sort(byActivity);
  return { in_progress, completed, favorited };
}

function ts(iso: string | null | undefined): number {
  if (!iso) return 0;
  const t = new Date(iso).getTime();
  return Number.isFinite(t) ? t : 0;
}

export default function MyCoursesClient() {
  const router = useRouter();
  const sp = useSearchParams();
  const authed = useAuthStore((s) => s.isAuthenticated());

  /* 保护路径：未登录 → 跳 login（redirect 回当前页） */
  useEffect(() => {
    if (authed) return;
    const redirect = encodeURIComponent("/my-courses" + (window?.location.search ?? ""));
    router.replace(`/login?redirect=${redirect}`);
  }, [authed, router]);

  const queryClient = useQueryClient();
  const q = useQuery({
    queryKey: ["my_courses"] as const,
    queryFn: async () => {
      const list = await getMyCourses();
      return withFavorites(list);
    },
    staleTime: 60_000,
    enabled: !!authed,
  });

  const data = q.data ?? [];
  const groups = useMemo(() => groupIntoTabs(data), [data]);

  // 默认 tab：?tab=xxx，否则用 groups 里第一个非空，再 fallback 到 in_progress
  const initialTab = (sp.get("tab") as TabId | null) ?? null;
  const defaultTab: TabId =
    initialTab && ["in_progress", "completed", "favorited"].includes(initialTab)
      ? initialTab
      : groups.in_progress.length
        ? "in_progress"
        : groups.favorited.length
          ? "favorited"
          : groups.completed.length
            ? "completed"
            : "in_progress";
  const [tab, setTab] = useState<TabId>(defaultTab);

  useEffect(() => {
    if (initialTab && tab !== initialTab) setTab(initialTab);
  }, [initialTab, tab]);

  const onFavoritedChange = useCallback(
    (seriesId: number, nextFav: boolean) => {
      setFavoriteSeries(seriesId, nextFav);
      // 立即把 __favorited 在 React Query cache 里就地更新（不触发 refetch）
      queryClient.setQueryData<CourseProgressOut[]>(["my_courses"], (prev) =>
        prev?.map((c) => (c.series_id === seriesId ? { ...c, __favorited: nextFav } : c)),
      );
      toast.success(nextFav ? "已加入收藏" : "已取消收藏");
    },
    [queryClient],
  );

  if (!authed) return <AuthRedirectSkeleton />;

  const badges: Record<TabId, number> = {
    in_progress: groups.in_progress.length,
    completed: groups.completed.length,
    favorited: groups.favorited.length,
  };

  return (
    <div className="space-y-5">
      <Tabs
        defaultValue={tab}
        value={tab}
        onValueChange={(v) => {
          setTab(v as TabId);
          router.replace(`/my-courses?tab=${v}`, { scroll: true });
        }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList>
            <TabsTrigger value="in_progress" className="gap-2">
              <GraduationCap className="h-4 w-4" />
              进行中
              <Badge variant="secondary" className="h-5 py-0 text-[10px]">
                {badges.in_progress}
              </Badge>
            </TabsTrigger>
            <TabsTrigger value="completed" className="gap-2">
              <Trophy className="h-4 w-4" />
              已完成
              <Badge variant="secondary" className="h-5 py-0 text-[10px]">
                {badges.completed}
              </Badge>
            </TabsTrigger>
            <TabsTrigger value="favorited" className="gap-2">
              <Heart className="h-4 w-4" />
              已收藏
              <Badge variant="secondary" className="h-5 py-0 text-[10px]">
                {badges.favorited}
              </Badge>
            </TabsTrigger>
          </TabsList>

          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void q.refetch()}
              disabled={q.isFetching}
            >
              <RefreshCcw className={"mr-1.5 h-4 w-4 " + (q.isFetching ? "animate-spin" : "")} />
              刷新
            </Button>
            <Button asChild size="sm">
              <Link href="/courses">
                <BookMarked className="mr-1.5 h-4 w-4" />
                去课程首页
              </Link>
            </Button>
          </div>
        </div>

        {q.isLoading && !q.data ? (
          <GridLoading rows={badges.in_progress || groups.favorited.length || 4} />
        ) : q.isError ? (
          <ErrorPanel onRetry={() => q.refetch()} msg={q.error instanceof Error ? q.error.message : "加载失败"} />
        ) : (
          <>
            <TabsContent value="in_progress">
              {groups.in_progress.length ? (
                <CourseGrid>
                  {groups.in_progress.map((c, i) => (
                    <MyCourseCard
                      key={c.series_id ?? `prog-${i}`}
                      data={c}
                      onFavoritedChange={(next) => onFavoritedChange(c.series_id, next)}
                    />
                  ))}
                </CourseGrid>
              ) : (
                <CourseTabsEmpty kind="in_progress" />
              )}
            </TabsContent>
            <TabsContent value="completed">
              {groups.completed.length ? (
                <CourseGrid>
                  {groups.completed.map((c, i) => (
                    <MyCourseCard
                      key={c.series_id ?? `done-${i}`}
                      data={c}
                      onFavoritedChange={(next) => onFavoritedChange(c.series_id, next)}
                    />
                  ))}
                </CourseGrid>
              ) : (
                <CourseTabsEmpty kind="completed" />
              )}
            </TabsContent>
            <TabsContent value="favorited">
              {groups.favorited.length ? (
                <CourseGrid>
                  {groups.favorited.map((c, i) => (
                    <MyCourseCard
                      key={c.series_id ?? `fav-${i}`}
                      data={c}
                      onFavoritedChange={(next) => onFavoritedChange(c.series_id, next)}
                    />
                  ))}
                </CourseGrid>
              ) : (
                <CourseTabsEmpty kind="favorited" />
              )}
            </TabsContent>
          </>
        )}
      </Tabs>
    </div>
  );
}

function CourseGrid({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">{children}</div>
  );
}

function GridLoading({ rows }: { rows: number }) {
  const n = Math.max(3, Math.min(6, rows));
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} className="overflow-hidden rounded-2xl border bg-white/70 p-0">
          <div className="h-32 w-full animate-pulse bg-gradient-to-br from-slate-200 via-slate-100 to-slate-200" />
          <div className="space-y-2 p-4">
            <div className="h-3 w-1/3 animate-pulse rounded bg-slate-200" />
            <div className="h-3 w-4/5 animate-pulse rounded bg-slate-200" />
            <div className="h-2 w-full animate-pulse rounded bg-slate-200" />
            <div className="h-2 w-1/2 animate-pulse rounded bg-slate-200" />
            <div className="h-8 w-full animate-pulse rounded-lg bg-slate-200" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ErrorPanel({ msg, onRetry }: { msg: string; onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-rose-200 bg-rose-50/50 p-6">
      <div className="font-semibold text-rose-700">加载我的课程失败</div>
      <p className="mt-1 text-sm text-rose-600">{msg}</p>
      <Button size="sm" variant="outline" className="mt-3 border-rose-300 text-rose-700" onClick={onRetry}>
        <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> 重试
      </Button>
    </div>
  );
}

function AuthRedirectSkeleton() {
  return (
    <div className="rounded-2xl border border-dashed p-10 text-center">
      <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-primary" />
      <div className="text-base font-semibold">正在跳转登录…</div>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        「我的课程」需要登录后才能看到你报名的所有课程。
      </p>
    </div>
  );
}
