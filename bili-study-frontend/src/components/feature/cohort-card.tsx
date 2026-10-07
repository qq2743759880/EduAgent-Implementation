/**
 * CohortCard — 我的班次卡片（C16，task47，candy-playful 糖果色）
 *
 * 语义：enrollments enroll_status（非 P3 progress 推断），三态：
 *   active    学习中 → [继续学习][课程详情][售后]，进度条 + 下次课
 *   completed 已完成 → [查看证书][写评价][再次报名]，结课时间
 *   refunded  已退款 → 灰色态 + [查看退款]，退款单信息
 *
 * 引用组件：StatusBadge（enroll_status 双通道）、Progress 派生进度条、
 *           Button / Badge；tokens 用 candy 语义色，禁硬编码 hex。
 * a11y：进度条 role="progressbar" + aria-*；状态由文案承载（不依赖颜色）。
 */
"use client";

import Link from "next/link";
import { BookOpen, ChevronRight, Play, Receipt, RotateCcw, Star, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { statusText } from "@/lib/status";
import type { EnrolledCohort } from "@/lib/api/enrollments";

/** 封面糖果渐变族（按系列 id 派生，仅用 candy tokens，禁硬编码 hex） */
const COVER_GRADIENTS = [
  "bg-gradient-to-br from-candy-orange to-candy-orange-soft",
  "bg-gradient-to-br from-candy-green to-candy-green-soft",
  "bg-gradient-to-br from-candy-purple to-candy-purple-soft",
  "bg-gradient-to-br from-candy-blue to-candy-blue/50",
  "bg-gradient-to-br from-candy-yellow to-candy-yellow/70",
] as const;

/** 封面吉祥物（按系列 id 派生，纯装饰 aria-hidden） */
const MASCOTS = ["🦉", "🐰", "🐧", "🐻", "🐥", "🦊"] as const;

function pick(v: number, arr: readonly string[]): string {
  return arr[((v % arr.length) + arr.length) % arr.length];
}

/** 封面渐变族派生（负数归一，与 pick 一致） */
function gradientFor(seriesId: number): string {
  return pick(seriesId, COVER_GRADIENTS);
}

function fmtPct(ratio: number | null | undefined): number {
  if (typeof ratio !== "number" || !Number.isFinite(ratio)) return 0;
  return Math.round(Math.max(0, Math.min(1, ratio)) * 100);
}

function gaugeTone(pct: number): "hot" | "normal" {
  // 92% 以上进入 hot（糖果橙），对齐效果图
  return pct >= 92 ? "hot" : "normal";
}

function fmtTime(s?: string | null): string {
  if (!s) return "";
  // 后端 teaching_at 已格式化，直接截取 M-D HH:mm 防溢出
  const m = /(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})/.exec(s);
  if (m) return `${m[1]}-${m[2]} ${m[3]}:${m[4]}`;
  return s;
}

/** 继续学习 → 最近未完成课次；无课时回课程详情 */
function continueHref(data: EnrolledCohort): string {
  const sid = data.next_session?.session_id;
  if (typeof sid === "number" && sid > 0) return `/learning/${data.series_id}/${sid}`;
  return `/courses/${data.series_id}`;
}

export function CohortCard({ data }: { data: EnrolledCohort }) {
  const status = data.enroll_status ?? "active";
  const pct = fmtPct(data.overall_ratio);
  const hot = gaugeTone(pct);
  const gradient = gradientFor(data.series_id);
  const mascot = pick(data.cohort_id, MASCOTS);
  const seriesMeta = [
    data.series_name ?? "系列课程",
    statusText("delivery_mode", data.delivery_mode ?? ""),
  ].filter(Boolean);
  const refunded = status === "refunded";
  const completed = status === "completed";
  const finishedAt = data.finished_at ? data.finished_at.slice(0, 10) : null;

  return (
    <article
      data-slot="cohort-card"
      className={
        "group flex h-full flex-col overflow-hidden rounded-[1.75rem] border-2 border-foreground/80 bg-card transition-transform duration-200 hover:-translate-y-0.5 hover:shadow-[0_8px_0_rgba(31,31,31,0.14)] " +
        (refunded ? "opacity-85 saturate-[0.25]" : "")
      }
    >
      {/* ===== 封面横条：糖果渐变 + 系列 + 班次 + 徽章 ===== */}
      <div
        className={
          "relative flex items-center gap-3 px-4 py-4 text-white " +
          (refunded ? "bg-gradient-to-br from-foreground/60 to-foreground/70" : gradient)
        }
      >
        <span
          aria-hidden="true"
          className="absolute -right-6 -top-10 h-24 w-24 rounded-full bg-white/20"
        />
        <span
          aria-hidden="true"
          className="absolute bottom-[-1.6rem] left-[34%] h-14 w-14 rounded-full bg-candy-yellow/20"
        />
        <span aria-hidden="true" className="relative text-3xl drop-shadow-[0_3px_0_rgba(31,31,31,0.18)]">
          {mascot}
        </span>
        <div className="relative min-w-0 flex-1">
          <div className="truncate text-xs font-bold tracking-wide text-white/90">
            {seriesMeta.join(" · ")}
          </div>
          <div className="mt-0.5 truncate text-[1.05rem] font-extrabold leading-snug text-white drop-shadow-[0_2px_0_rgba(31,31,31,0.2)]">
            {data.cohort_name ?? "未命名班次"}
          </div>
        </div>
        <StatusBadge
          map="enroll_status"
          status={status}
          className="relative shrink-0 border-2 border-white/90 bg-white/25 font-extrabold backdrop-blur-sm"
        />
      </div>

      {/* ===== 卡片体 ===== */}
      <div className="flex flex-1 flex-col gap-3 p-4">
        {refunded ? (
          /* ---------- 已退款：无进度，退款单 ---------- */
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span aria-hidden="true" className="text-base">💸</span>
            <span>
              已退款 <b className="font-bold text-foreground">{data.refund?.refund_amount ?? "—"}</b>
              {data.refund?.refund_no ? (
                <span className="ml-1">· 退款单 <b className="font-bold text-foreground">{data.refund.refund_no}</b></span>
              ) : null}
              {data.refund?.refunded_at ? (
                <span className="ml-1">（{data.refund.refunded_at.slice(0, 10)}）</span>
              ) : null}
            </span>
          </div>
        ) : (
          <>
            {/* ---------- 进度：label + pct + bar + meta ---------- */}
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[0.8rem] font-bold text-foreground">课程进度</span>
              <span
                className={
                  "text-[0.8rem] font-extrabold tabular-nums " +
                  (hot ? "text-candy-orange" : "text-candy-green")
                }
              >
                {pct}%
              </span>
            </div>
            <div
              role="progressbar"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`课程进度 ${pct}%`}
              className="h-3.5 w-full overflow-hidden rounded-full border-2 border-foreground/15 bg-foreground/10"
            >
              <div
                data-hot={hot}
                className={
                  "h-full rounded-full transition-[width] duration-500 ease-out " +
                  (hot
                    ? "bg-gradient-to-r from-candy-orange to-candy-orange-soft"
                    : "bg-gradient-to-r from-candy-green to-candy-green-soft")
                }
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="flex flex-wrap gap-x-3.5 gap-y-0.5 text-xs text-muted-foreground">
              <span>模块 <b className="font-bold text-foreground">{data.module_done ?? 0}/{data.module_total ?? 0}</b></span>
              <span>课次 <b className="font-bold text-foreground">{data.session_done ?? 0}/{data.session_total ?? 0}</b></span>
              {!completed && data.next_session?.module_title ? (
                <span>
                  下次课: <b className="font-bold text-foreground">{data.next_session.module_title}</b>
                </span>
              ) : completed && finishedAt ? (
                <span>
                  结课: <b className="font-bold text-foreground">{finishedAt}</b>
                </span>
              ) : null}
            </div>

            {/* ---------- 下次课条（active）：名称 truncate + 时间右对齐 ---------- */}
            {!completed && data.next_session?.session_title ? (
              <div className="flex items-center gap-2 rounded-xl border-2 border-dashed border-candy-green/40 bg-candy-green-soft px-3 py-2 text-[0.8rem] text-foreground">
                <span aria-hidden="true" className="shrink-0 text-[0.95rem]">⏰</span>
                <span className="min-w-0 truncate">
                  下次课 <b className="font-bold text-candy-green">{data.next_session.session_title}</b>
                </span>
                {data.next_session.teaching_at ? (
                  <span className="ml-auto shrink-0 pl-2 font-bold tabular-nums text-foreground">
                    {fmtTime(data.next_session.teaching_at)}
                  </span>
                ) : null}
              </div>
            ) : null}
          </>
        )}

        {/* ---------- 操作 ---------- */}
        <div className="mt-auto flex flex-wrap gap-2 pt-1">
          {completed ? (
            <>
              <Button asChild size="sm" className="shrink-0">
                <Link href={`/courses/${data.series_id}`}>
                  <Trophy className="mr-1.5 h-3.5 w-3.5" /> 查看证书
                </Link>
              </Button>
              <Button asChild size="sm" variant="outline" className="shrink-0">
                <Link href={`/courses/${data.series_id}`}>
                  <Star className="mr-1.5 h-3.5 w-3.5" /> 写评价
                </Link>
              </Button>
              <Button asChild size="sm" variant="ghost" className="shrink-0">
                <Link href="/courses">
                  <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> 再次报名
                </Link>
              </Button>
            </>
          ) : refunded ? (
            <Button asChild size="sm" variant="outline" className="shrink-0">
              <Link href="/refunds">
                <Receipt className="mr-1.5 h-3.5 w-3.5" /> 查看退款
              </Link>
            </Button>
          ) : (
            <>
              <Button asChild size="sm" className="shrink-0 grow-[2] basis-full motion-reduce:grow-0 sm:basis-auto sm:grow-0">
                <Link href={continueHref(data)}>
                  <Play className="mr-1.5 h-3.5 w-3.5" /> 继续学习
                </Link>
              </Button>
              <Button
                asChild
                size="sm"
                variant="outline"
                className="shrink-0 grow motion-reduce:grow-0"
              >
                <Link href={data.series_id ? `/courses/${data.series_id}` : "/courses"}>
                  <BookOpen className="mr-1.5 h-3.5 w-3.5" /> 课程详情
                </Link>
              </Button>
              <Button asChild size="sm" variant="ghost" className="shrink-0 grow motion-reduce:grow-0">
                <Link href="/tickets">
                  <ChevronRight className="mr-1 h-3.5 w-3.5" /> 售后
                </Link>
              </Button>
            </>
          )}
        </div>
      </div>
    </article>
  );
}