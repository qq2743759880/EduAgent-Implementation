"use client";

import { use, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  Clock,
  Loader2,
  Star,
  Users,
  Waypoints,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { CourseMindmapView, type MindmapLoadState } from "@/components/curriculum/CourseMindmapView";
import { CourseSyllabusTree } from "@/components/curriculum/CourseSyllabusTree";
import { ReviewList } from "@/components/curriculum/ReviewList";
import {
  LEVEL_OPTIONS,
  SUBJECT_OPTIONS,
  getCourseMindmap,
  getSeriesDetail,
  getSeriesTree,
  type SeriesSummary,
  type MindMapResponse,
} from "@/lib/api/curriculum";
import { useAuthStore } from "@/lib/auth-client";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export default function CourseDetailPage({ params }: { params: Promise<{ seriesId: string }> }) {
  const resolved = use(params);
  const seriesId = Number(resolved.seriesId);
  const router = useRouter();
  const loggedIn = useAuthStore((s) => !!s.token);

  /* 详情（主表 + 班次 + 模块列表） — 快速首屏信息 */
  const detailQ = useQuery({
    queryKey: ["series_detail", seriesId] as const,
    async queryFn() {
      return getSeriesDetail(seriesId);
    },
    enabled: Number.isFinite(seriesId) && seriesId > 0,
    staleTime: 120_000,
  });

  /* 完整树（模块 → 课次） */
  const treeQ = useQuery({
    queryKey: ["series_tree", seriesId] as const,
    async queryFn() {
      return getSeriesTree(seriesId);
    },
    enabled: Number.isFinite(seriesId) && seriesId > 0,
    staleTime: 120_000,
  });

  /* 思维导图 —— P4 mindmap API 允许 404 / 空节点降级 */
  const mindmapState: MindmapLoadState = useMemo<MindmapLoadState>(() => {
    /* 这里不直接 useQuery，而是把 fetch 包成 async IIFE 的状态管理，
       避免 CourseMindmapView 自己去管 data 生命周期。*/
    return { status: "loading" };
  }, []);

  const series: SeriesSummary | undefined =
    treeQ.data?.series ?? detailQ.data?.series;
  const modulesForSyllabus =
    treeQ.data?.modules ?? detailQ.data?.modules ?? [];
  const cohorts = treeQ.data?.cohorts ?? detailQ.data?.cohorts ?? [];

  const bestCohort = cohorts
    .filter((c) => (c.yn ?? 1) === 1)
    .sort(
      (a, b) =>
        (typeof a.price_current === "number" ? a.price_current : 9999999) -
        (typeof b.price_current === "number" ? b.price_current : 9999999),
    )[0];

  const priceCurrent =
    (bestCohort && typeof bestCohort.price_current === "number"
      ? bestCohort.price_current
      : null) ??
    (series && typeof series.price_current === "number" ? series.price_current : 999);
  const priceOriginal =
    (bestCohort && typeof bestCohort.price_original === "number"
      ? bestCohort.price_original
      : null) ??
    (series && typeof series.price_original === "number" ? series.price_original : Math.round(priceCurrent * 1.3));

  return (
    <div className="min-h-screen bg-slate-50/50 pb-24">
      {/* 顶部面包屑 */}
      <header className="border-b bg-white/80 backdrop-blur">
        <div className="mx-auto w-full max-w-7xl px-4 py-4 md:px-6 lg:px-8">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Button variant="ghost" size="sm" className="h-7 px-2 text-muted-foreground hover:text-foreground" onClick={() => router.back()}>
              <ArrowLeft className="mr-1 h-3.5 w-3.5" /> 返回
            </Button>
            <Link className="hover:text-foreground" href="/courses">
              课程首页
            </Link>
            <span>/</span>
            <Link className="hover:text-foreground" href="/courses/search">
              搜索
            </Link>
            <span>/</span>
            <span className="text-foreground">
              {series?.series_title ?? `课程 ${seriesId}`}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-4 pt-6 md:px-6 lg:px-8">
        {detailQ.isLoading && !series ? <HeroSkeleton /> : null}

        {detailQ.isError && !series ? (
          <ErrorBox
            title="加载失败"
            message={
              detailQ.error instanceof Error
                ? detailQ.error.message
                : "无法获取课程详情，请稍后重试"
            }
          />
        ) : null}

        {series ? (
          <>
            <HeroSection
              series={series}
              bestCohortTitle={bestCohort?.cohort_title}
              priceCurrent={priceCurrent}
              priceOriginal={priceOriginal}
              students={series.student_count ?? bestCohort?.enrolled_count ?? 0}
              enrolledLoggedIn={loggedIn}
              onEnroll={() => handleEnroll(loggedIn, series.id, router)}
            />

            <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="space-y-6">
                <Tabs defaultValue="syllabus" className="w-full">
                  <TabsList className="grid w-full max-w-xl grid-cols-3">
                    <TabsTrigger value="syllabus">教学大纲</TabsTrigger>
                    <TabsTrigger value="mindmap">思维导图</TabsTrigger>
                    <TabsTrigger value="review">学员评价</TabsTrigger>
                  </TabsList>

                  <TabsContent value="syllabus" className="pt-4">
                    <CourseSyllabusTree modules={modulesForSyllabus} />
                  </TabsContent>

                  <TabsContent value="mindmap" className="pt-4">
                    <MindmapLoader seriesId={seriesId} />
                  </TabsContent>

                  <TabsContent value="review" className="pt-4">
                    <ReviewList />
                  </TabsContent>
                </Tabs>
              </div>

              <aside className="space-y-4 lg:sticky lg:top-6 h-fit">
                <EnrollCard
                  priceCurrent={priceCurrent}
                  priceOriginal={priceOriginal}
                  cohortTitle={bestCohort?.cohort_title ?? "标准班"}
                  enrolledLoggedIn={loggedIn}
                  onEnroll={() => handleEnroll(loggedIn, series.id, router)}
                />
                <HighlightsCard
                  hours={series.total_hours ?? 0}
                  sessions={series.session_count ?? modulesForSyllabus.reduce((s, m) => s + (m.sessions?.length ?? m.session_count ?? 0), 0)}
                  modules={series.module_count ?? modulesForSyllabus.length}
                  rating={series.rating ?? 4.5}
                />
                <CohortsList
                  cohorts={cohorts}
                  selectedId={bestCohort?.id}
                  onPick={(id) => toast.info(`已切换：${cohorts.find((c) => c.id === id)?.cohort_title ?? ""}`)}
                />
              </aside>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}

/* ---------------- 子组件 ---------------- */

function HeroSection({
  series,
  bestCohortTitle,
  priceCurrent,
  priceOriginal,
  students,
  enrolledLoggedIn,
  onEnroll,
}: {
  series: SeriesSummary;
  bestCohortTitle?: string;
  priceCurrent: number;
  priceOriginal: number;
  students: number;
  enrolledLoggedIn: boolean;
  onEnroll: () => void;
}) {
  const subject = SUBJECT_OPTIONS.find((s) => s.code === series.subject_code);
  const level = LEVEL_OPTIONS.find((l) => l.code === series.level_code);
  return (
    <section className="overflow-hidden rounded-3xl border bg-white shadow-sm">
      <div className="grid lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className={"relative min-h-[240px] bg-gradient-to-br px-6 py-10 text-white " + subjectBgGradient(series.subject_code)}>
          <div className="pointer-events-none absolute inset-0 opacity-40 [background-image:radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.4),transparent_60%),radial-gradient(ellipse_at_bottom_left,rgba(0,0,0,0.2),transparent_55%)]" />
          <div className="relative flex flex-wrap items-center gap-2">
            {subject && (
              <Badge className="bg-white/20 text-white backdrop-blur hover:bg-white/25">
                {subject.name}
              </Badge>
            )}
            {level && (
              <Badge variant="outline" className="border-white/40 bg-white/10 text-white backdrop-blur">
                {level.name}
              </Badge>
            )}
            {bestCohortTitle && (
              <Badge variant="outline" className="border-white/40 bg-white/10 text-white backdrop-blur">
                班次：{bestCohortTitle}
              </Badge>
            )}
          </div>
          <h1 className="relative mt-5 text-3xl font-bold leading-tight md:text-4xl">
            {series.series_title}
          </h1>
          {(series.subtitle || series.description) && (
            <p className="relative mt-3 max-w-2xl text-sm leading-7 text-white/90 md:text-base">
              {series.subtitle || series.description}
            </p>
          )}
          <div className="relative mt-6 flex flex-wrap items-center gap-5 text-sm text-white/90">
            <span className="inline-flex items-center gap-1.5">
              <Star className="h-4 w-4 fill-amber-300 text-amber-300" />
              <b className="text-white">{(series.rating ?? 4.5).toFixed(1)}</b>
              <span className="text-white/80">平均评分</span>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Users className="h-4 w-4" />
              {students.toLocaleString()} 人已报名
            </span>
            <span className="inline-flex items-center gap-1.5">
              <BookOpen className="h-4 w-4" />
              {(series.module_count ?? 0) + " 模块"}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Clock className="h-4 w-4" />
              {(typeof series.total_hours === "number" ? `${series.total_hours} 学时` : `${series.session_count ?? 0} 课次`)}
            </span>
          </div>
        </div>

        <div className="border-t border-white/10 bg-slate-900/95 px-6 py-8 text-white lg:border-l lg:border-t-0">
          <div className="text-xs uppercase tracking-wider text-white/60">课程价格</div>
          <div className="mt-2 flex items-baseline gap-3">
            <span className="text-4xl font-bold text-amber-300">¥{priceCurrent}</span>
            {priceOriginal > priceCurrent && (
              <span className="text-sm text-white/50 line-through">
                ¥{priceOriginal}
              </span>
            )}
          </div>
          <ul className="mt-5 space-y-2 text-sm text-white/85">
            <li className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-400" />分级课程 + 学习路径思维导图</li>
            <li className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-400" />配套互动习题 + 错题本 + AI 单词本</li>
            <li className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-400" />AI 问答助手 7×24 小时（知识库引用来源）</li>
            <li className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-400" />学习进度 + 能力雷达持续追踪</li>
          </ul>
          <div className="mt-6 space-y-2">
            <Button
              size="lg"
              className={cn(
                "w-full bg-amber-400 font-semibold text-slate-900 hover:bg-amber-300",
              )}
              onClick={onEnroll}
            >
              {enrolledLoggedIn ? "立即报名 · 已登录" : "登录后立即报名"}
            </Button>
            <p className="text-center text-xs text-white/50">
              支付由系统后台统一对账，报名失败不会扣费
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function HeroSkeleton() {
  return (
    <div className="h-[360px] w-full animate-pulse rounded-3xl border bg-slate-100" />
  );
}

function ErrorBox({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-2xl border border-rose-200 bg-rose-50/40 p-6">
      <div className="text-base font-semibold text-rose-700">{title}</div>
      <p className="mt-1 text-sm text-rose-600">{message}</p>
    </div>
  );
}

function EnrollCard({
  priceCurrent,
  priceOriginal,
  cohortTitle,
  enrolledLoggedIn,
  onEnroll,
}: {
  priceCurrent: number;
  priceOriginal: number;
  cohortTitle: string;
  enrolledLoggedIn: boolean;
  onEnroll: () => void;
}) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <Badge variant="outline" className="text-xs">
            选中班次：{cohortTitle}
          </Badge>
        </div>
        <div className="mt-4 flex items-baseline gap-2">
          <span className="text-2xl font-bold text-rose-600">¥{priceCurrent}</span>
          {priceOriginal > priceCurrent && (
            <span className="text-xs text-muted-foreground line-through">¥{priceOriginal}</span>
          )}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">一次报名，有效期内无限回看 + 助教答疑</div>
        <Button className="mt-4 w-full" onClick={onEnroll} size="lg">
          {enrolledLoggedIn ? "立即报名" : "登录后报名"}
        </Button>
      </CardContent>
    </Card>
  );
}

function HighlightsCard({
  hours, sessions, modules, rating,
}: { hours: number; sessions: number; modules: number; rating: number; }) {
  const items = [
    { label: "学时", value: hours ? `${hours} h` : `${sessions} 课次`, Icon: Clock },
    { label: "模块", value: `${modules}`, Icon: Waypoints },
    { label: "课次", value: `${sessions}`, Icon: BookOpen },
    { label: "评分", value: `${rating.toFixed(1)}`, Icon: Star },
  ] as const;
  return (
    <Card>
      <CardContent className="grid grid-cols-2 gap-3 p-4">
        {items.map(({ label, value, Icon }) => (
          <div key={label} className="rounded-xl border bg-slate-50/60 p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Icon className="h-3.5 w-3.5" /> {label}
            </div>
            <div className="mt-1 text-lg font-semibold">{value}</div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function CohortsList({
  cohorts,
  selectedId,
  onPick,
}: {
  cohorts: { id: number; cohort_title: string; price_current?: number | null; enrolled_count?: number | null; capacity?: number | null; start_date?: string | null }[];
  selectedId?: number;
  onPick: (id: number) => void;
}) {
  if (!cohorts.length) return null;
  return (
    <Card>
      <CardContent className="p-4">
        <div className="mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">可报名班次</div>
        <ul className="space-y-2">
          {cohorts
            .filter((c) => (c as { yn?: number }).yn ?? 1 === 1)
            .map((c, i) => {
              const sel = c.id === selectedId;
              const price = typeof c.price_current === "number" ? c.price_current : 999;
              const enroll = c.enrolled_count ?? 0;
              const cap = c.capacity ?? 999;
              const pct = Math.min(100, Math.round((enroll / Math.max(1, cap)) * 100));
              return (
                <li key={c.id ?? `cohort-${i}`}>
                  <button
                    type="button"
                    onClick={() => onPick(c.id)}
                    className={cn(
                      "w-full rounded-xl border p-3 text-left transition-all",
                      sel ? "border-primary bg-primary/5" : "hover:border-foreground/30",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{c.cohort_title}</span>
                      <span className="text-sm font-semibold text-rose-600">¥{price}</span>
                    </div>
                    {c.start_date && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        开班日期：{c.start_date}
                      </div>
                    )}
                    <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            pct > 85 ? "bg-rose-500" : pct > 50 ? "bg-amber-400" : "bg-emerald-500",
                          )}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="w-14 text-right tabular-nums">{enroll}/{cap}</span>
                    </div>
                  </button>
                </li>
              );
            })}
        </ul>
      </CardContent>
    </Card>
  );
}

/**
 * MindmapLoader — 在详情页内部做真实 fetch → 把结果态传给 CourseMindmapView
 * 放在组件内部，避免父组件 (page) 被客户端状态污染而必须拆文件。
 */
function MindmapLoader({ seriesId }: { seriesId: number }) {
  const { data, isLoading, isError, error } = useQuery<MindMapResponse | null, unknown>({
    queryKey: ["series_mindmap", seriesId] as const,
    async queryFn(): Promise<MindMapResponse | null> {
      try {
        return await getCourseMindmap(seriesId);
      } catch (e) {
        /* 404 时 P4 后端可能抛 "系列不存在"，这里吞掉返回 null，UI 转 empty */
        const status =
          e && typeof e === "object" && "status" in e ? Number((e as { status?: unknown }).status) : 0;
        if (status === 404 || status === 500) return null;
        throw e;
      }
    },
    enabled: Number.isFinite(seriesId) && seriesId > 0,
    staleTime: 120_000,
    retry: 1,
  });

  const state: MindmapLoadState = isLoading
    ? { status: "loading" }
    : isError
      ? {
          status: "error",
          message: error instanceof Error ? error.message : "加载图谱失败",
        }
      : !data || !data.nodes?.length
        ? { status: "empty" }
        : { status: "ready", data };

  return <CourseMindmapView state={state} />;
}

function handleEnroll(loggedIn: boolean, seriesId: number, router: ReturnType<typeof useRouter>) {
  if (!loggedIn) {
    const redirect = encodeURIComponent(`/courses/${seriesId}`);
    router.push(`/login?redirect=${redirect}`);
    return;
  }
  /* 课程支付接口 P4/P8 暂未开放，先 toast 占位说明 */
  toast.success("报名流程：请前往我的订单完成支付", {
    description: `课程 ID = ${seriesId}。实际支付接口将在后续阶段接入。`,
  });
}

function subjectBgGradient(code: string | null | undefined): string {
  switch (code) {
    case "english":
      return "from-sky-600 via-sky-500 to-cyan-500";
    case "programming":
      return "from-violet-600 via-indigo-500 to-purple-500";
    case "math":
      return "from-emerald-600 via-teal-500 to-green-500";
    case "chinese":
      return "from-amber-500 via-orange-400 to-rose-400";
    case "physics":
      return "from-rose-600 via-pink-500 to-red-500";
    default:
      return "from-slate-700 via-slate-600 to-slate-700";
  }
}
