/**
 * CourseDetailClient — /courses/[seriesId] 课程详情页客户端逻辑（task46，对齐 P8 + HTML 效果图 APPROVED）
 *
 * 由 page.tsx（server component）await params 后传入 seriesId。
 * 四态：loading（Hero/Tabs 骨架）/ error（ErrorState + 重试）/ empty（404 EmptyState）/ success（完整渲染）
 * 数据流（全部真实契约，无 MOCK）：
 *   - GET /api/series/{id}             → SeriesDetail
 *   - GET /api/series/{id}/cohorts     → Cohort[]（默认选中最低价在售且有席位班次）
 *   - GET /api/cohorts/{id}/modules    → ModuleWithSessions[]（随选中班次联动刷新）
 *   - GET /api/mindmap/course/{id}     → 思维导图（匿名）
 *   - GET /api/coupons?series_id=      → 领券弹窗模板（登录后）
 *   - GET /api/coupons（我的有效券）    → 已领取券（抵扣选择）
 *   - GET/POST/DELETE /api/favorites   → 收藏（登录后）
 *   - POST /api/trade/order            → 立即报名（Idempotency-Key）
 * 未登录交互（报名/领券/收藏）→ /login?redirect= 原路返回。
 */
"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronRight, PackageOpen } from "lucide-react";

import { CourseDetailHero } from "@/components/curriculum/CourseDetailHero";
import { CourseDetailTabs } from "@/components/curriculum/CourseDetailTabs";
import { CouponPicker } from "@/components/curriculum/CouponPicker";
import type { MindmapLoadState } from "@/components/curriculum/CourseMindmapView";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Button } from "@/components/ui/button";
import {
  getCourseMindmap,
  getSeriesDetail,
  listCohortModules,
  listSeriesCohorts,
  type MindMapResponse,
  type ModuleWithSessions,
} from "@/lib/api/curriculum";
import {
  listMyCoupons,
  listSeriesCoupons,
  receiveCoupon,
} from "@/lib/api/coupons";
import { addFavorite, listFavorites, removeFavorite } from "@/lib/api/favorites";
import { createOrder } from "@/lib/api/orders";
import { useAuthStore } from "@/lib/auth-client";
import { toast } from "sonner";

function priceOf(v: string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "请求失败，请稍后重试";
}

export function CourseDetailClient({ seriesId }: { seriesId: number }) {
  const router = useRouter();
  const authed = useAuthStore((s) => s.ready && !!s.token);
  const valid = Number.isFinite(seriesId) && seriesId > 0;

  /* ---------- 数据查询 ---------- */
  const detailQ = useQuery({
    queryKey: ["series_detail", seriesId] as const,
    queryFn: () => getSeriesDetail(seriesId),
    enabled: valid,
    staleTime: 120_000,
  });

  const cohortsQ = useQuery({
    queryKey: ["series_cohorts", seriesId] as const,
    queryFn: () => listSeriesCohorts(seriesId),
    enabled: valid,
    staleTime: 120_000,
  });

  const mindmapQ = useQuery<MindMapResponse | null, unknown>({
    queryKey: ["series_mindmap", seriesId] as const,
    async queryFn() {
      try {
        return await getCourseMindmap(seriesId);
      } catch (e) {
        /* 404/500 时后端可能抛「系列不存在」，吞掉转 empty 态 */
        const status =
          e && typeof e === "object" && "status" in e ? Number((e as { status?: unknown }).status) : 0;
        if (status === 404 || status === 500) return null;
        throw e;
      }
    },
    enabled: valid,
    staleTime: 120_000,
    retry: 1,
  });

  /* ---------- 班次选择（默认最低价在售班次） ---------- */
  // C-B（task115）后 /api/series/{id}/cohorts 返回外层 {total,page,page_size,items}，读外层 items
  const cohorts = useMemo(() => cohortsQ.data?.items ?? [], [cohortsQ.data]);
  const [selectedCohortId, setSelectedCohortId] = useState<number | null>(null);
  const defaultCohort = useMemo(() => {
    const onSale = cohorts
      .filter((c) => (c.yn ?? 1) === 1)
      .filter((c) => c.current_student_count < c.max_student_count)
      .sort((a, b) => (priceOf(a.sale_price) ?? 1e9) - (priceOf(b.sale_price) ?? 1e9));
    return onSale[0] ?? cohorts[0] ?? null;
  }, [cohorts]);
  const effectiveCohortId = selectedCohortId ?? defaultCohort?.id ?? null;
  const selectedCohort = cohorts.find((c) => c.id === effectiveCohortId) ?? null;

  const modulesQ = useQuery({
    queryKey: ["cohort_modules", effectiveCohortId] as const,
    queryFn: () => listCohortModules(effectiveCohortId!),
    enabled: !!effectiveCohortId,
    staleTime: 120_000,
  });

  /* ---------- 领券（登录后） ---------- */
  const [couponOpen, setCouponOpen] = useState(false);
  const [selectedCouponId, setSelectedCouponId] = useState<number | null>(null);

  const templatesQ = useQuery({
    queryKey: ["series_coupons", seriesId] as const,
    queryFn: () => listSeriesCoupons(seriesId),
    enabled: couponOpen && authed,
    staleTime: 60_000,
  });

  const myCouponsQ = useQuery({
      queryKey: ["my_coupons", "unused"] as const,
      queryFn: () => listMyCoupons({ status: "unused", page_size: 100 }),
    enabled: authed,
    staleTime: 60_000,
  });
  const receivedCoupons = myCouponsQ.data?.items ?? [];
  const selectedCoupon = receivedCoupons.find((c) => c.coupon_id === selectedCouponId) ?? null;

  /* ---------- 收藏（登录后） ---------- */
  const favQ = useQuery({
    queryKey: ["my_favorites", "series"] as const,
    queryFn: () => listFavorites({ target_type: "series", page_size: 100 }),
    enabled: authed,
    staleTime: 60_000,
  });
  const favorited = favQ.data?.items?.some((f) => f.series_id === seriesId) ?? false;

  /* ---------- 交互 ---------- */
  const requireLogin = () => {
    router.push(`/login?redirect=${encodeURIComponent(`/courses/${seriesId}`)}`);
  };

  const receiveMutation = useMutation({
    mutationFn: (templateId: number) => receiveCoupon({ coupon_template_id: templateId }),
    onSuccess: (coupon) => {
      toast.success("领券成功", { description: coupon.coupon_name });
      myCouponsQ.refetch();
      templatesQ.refetch();
    },
    onError: (e) => toast.error("领券失败", { description: errorMessage(e) }),
  });

  const favMutation = useMutation<Awaited<ReturnType<typeof addFavorite>> | Awaited<ReturnType<typeof removeFavorite>>, unknown, void>({
    mutationFn: () => (favorited ? removeFavorite(seriesId) : addFavorite({ series_id: seriesId })),
    onSuccess: () => {
      toast.success(favorited ? "已取消收藏" : "收藏成功");
      favQ.refetch();
    },
    onError: (e) => toast.error("操作失败", { description: errorMessage(e) }),
  });

  const orderMutation = useMutation({
    mutationFn: () =>
      createOrder(
        {
          series_id: seriesId,
          cohort_id: effectiveCohortId!,
          coupon_id: selectedCouponId ?? undefined,
        },
        crypto.randomUUID(),
      ),
    onSuccess: (order) => {
      toast.success("下单成功", {
        description: `订单号 ${order.order_no}，请前往订单页完成支付`,
      });
      /* 支付页在 task47 接入后跳转 /orders/[orderNo]/pay */
    },
    onError: (e) => toast.error("下单失败", { description: errorMessage(e) }),
  });

  const handleOpenCoupon = () => {
    if (!authed) {
      requireLogin();
      return;
    }
    setCouponOpen(true);
  };

  const handleToggleFavorite = () => {
    if (!authed) {
      requireLogin();
      return;
    }
    favMutation.mutate();
  };

  const handleEnroll = () => {
    if (!authed) {
      requireLogin();
      return;
    }
    if (!effectiveCohortId) {
      toast.warning("请先选择一个班次");
      return;
    }
    orderMutation.mutate();
  };

  /* ---------- 思维导图态 ---------- */
  const mindmapState: MindmapLoadState = mindmapQ.isLoading
    ? { status: "loading" }
    : mindmapQ.isError
      ? { status: "error", message: errorMessage(mindmapQ.error) }
      : !mindmapQ.data?.nodes?.length
        ? { status: "empty" }
        : { status: "ready", data: mindmapQ.data };

  /* ---------- 渲染 ---------- */
  if (!valid) {
    return (
      <PageShell>
        <EmptyState
          icon={<PackageOpen />}
          title="课程不存在"
          description="链接无效或课程已被下架"
          action={
            <Button asChild size="sm">
              <Link href="/courses">返回课程中心</Link>
            </Button>
          }
        />
      </PageShell>
    );
  }

  if (detailQ.isLoading && !detailQ.data) {
    return (
      <PageShell>
        <DetailSkeleton />
      </PageShell>
    );
  }

  if (detailQ.isError && !detailQ.data) {
    return (
      <PageShell>
        <ErrorState title="加载失败" message={errorMessage(detailQ.error)} retry={() => detailQ.refetch()} />
      </PageShell>
    );
  }

  if (!detailQ.data) {
    return (
      <PageShell>
        <EmptyState
          icon={<PackageOpen />}
          title="课程不存在"
          description="该课程可能已下架或链接有误"
          action={
            <Button asChild size="sm">
              <Link href="/courses">返回课程中心</Link>
            </Button>
          }
        />
      </PageShell>
    );
  }

  const series = detailQ.data;
  const modules: ModuleWithSessions[] = modulesQ.data?.modules ?? [];

  return (
    <div className="min-h-screen bg-background pb-24">
      <Breadcrumb seriesName={series.series_name} seriesId={seriesId} />

      <main className="mx-auto w-full max-w-7xl px-4 pt-6 md:px-6 lg:px-8">
        <CourseDetailHero
          series={series}
          cohorts={cohorts}
          selectedCohortId={effectiveCohortId}
          onSelectCohort={setSelectedCohortId}
          coupon={selectedCoupon}
          onOpenCoupon={handleOpenCoupon}
          favorited={favorited}
          onToggleFavorite={handleToggleFavorite}
          onEnroll={handleEnroll}
          enrolling={orderMutation.isPending}
          authed={authed}
        />

        <CourseDetailTabs
          series={series}
          cohort={selectedCohort}
          modules={modules}
          modulesLoading={modulesQ.isLoading}
          reviews={[]}
          mindmapState={mindmapState}
        />

        <CouponPicker
          open={couponOpen}
          onOpenChange={setCouponOpen}
          templates={templatesQ.data ?? []}
          templatesLoading={templatesQ.isLoading}
          receivedCoupons={receivedCoupons}
          onReceive={(templateId) => receiveMutation.mutateAsync(templateId).then(() => undefined)}
          selectedCouponId={selectedCouponId}
          onSelectCoupon={setSelectedCouponId}
        />
      </main>
    </div>
  );
}

/* ---------------- 布局骨架 ---------------- */

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-background pb-24">
      <header className="border-b border-border bg-card/80 backdrop-blur">
        <div className="mx-auto w-full max-w-7xl px-4 py-4 md:px-6 lg:px-8">
          <nav aria-label="面包屑" className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Link className="transition-colors hover:text-foreground" href="/courses">
              课程中心
            </Link>
            <ChevronRight aria-hidden="true" className="h-3 w-3" />
            <span className="text-foreground">课程详情</span>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl px-4 pt-6 md:px-6 lg:px-8">{children}</main>
    </div>
  );
}

function Breadcrumb({ seriesName, seriesId }: { seriesName: string; seriesId: number }) {
  return (
    <header className="border-b border-border bg-card/80 backdrop-blur">
      <div className="mx-auto w-full max-w-7xl px-4 py-4 md:px-6 lg:px-8">
        <nav aria-label="面包屑" className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <Link className="transition-colors hover:text-foreground" href="/courses">
            课程中心
          </Link>
          <ChevronRight aria-hidden="true" className="h-3 w-3" />
          <Link className="transition-colors hover:text-foreground" href="/courses/search">
            搜索
          </Link>
          <ChevronRight aria-hidden="true" className="h-3 w-3" />
          <span className="font-semibold text-foreground">{seriesName}</span>
          <span className="text-3xs text-muted-foreground/70">#{seriesId}</span>
        </nav>
      </div>
    </header>
  );
}

function DetailSkeleton() {
  return (
    <div role="status" aria-live="polite" className="space-y-6">
      <span className="sr-only">正在加载课程详情…</span>
      <div className="h-64 animate-pulse rounded-3xl border-[3px] border-border bg-muted/60" aria-hidden="true" />
      <div className="flex gap-2 border-b border-border pb-2" aria-hidden="true">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-8 w-24 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
      <div className="space-y-3" aria-hidden="true">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-xl border-2 border-border bg-muted/40" />
        ))}
      </div>
    </div>
  );
}
