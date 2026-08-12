"use client";

import { type LucideIcon, TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export type KpiDelta =
  | { direction: "up" | "down" | "flat"; value: string; tone?: "positive" | "negative" | "neutral" }
  | null
  | undefined;

interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: ReactNode;
  icon?: LucideIcon | ReactNode;
  delta?: KpiDelta;
  accent?: "indigo" | "emerald" | "amber" | "sky" | "rose" | "violet";
  className?: string;
  loading?: boolean;
}

const ACCENT_MAP: Record<NonNullable<KpiCardProps["accent"]>, { iconBg: string; ring: string; tintText: string }> = {
  indigo: {
    iconBg: "from-indigo-500 to-indigo-600 text-white",
    ring: "ring-indigo-100",
    tintText: "text-indigo-600",
  },
  emerald: {
    iconBg: "from-emerald-500 to-teal-600 text-white",
    ring: "ring-emerald-100",
    tintText: "text-emerald-600",
  },
  amber: {
    iconBg: "from-amber-400 to-orange-500 text-white",
    ring: "ring-amber-100",
    tintText: "text-amber-600",
  },
  sky: {
    iconBg: "from-sky-500 to-cyan-600 text-white",
    ring: "ring-sky-100",
    tintText: "text-sky-600",
  },
  rose: {
    iconBg: "from-rose-500 to-pink-600 text-white",
    ring: "ring-rose-100",
    tintText: "text-rose-600",
  },
  violet: {
    iconBg: "from-violet-500 to-fuchsia-600 text-white",
    ring: "ring-violet-100",
    tintText: "text-violet-600",
  },
};

export function KpiCard({
  title,
  value,
  subtitle,
  icon,
  delta,
  accent = "indigo",
  className,
  loading = false,
}: KpiCardProps) {
  const theme = ACCENT_MAP[accent];
  const tone = delta?.tone ?? (delta?.direction === "up" ? "positive" : delta?.direction === "down" ? "negative" : "neutral");

  return (
    <Card
      className={cn(
        "overflow-hidden border-slate-200/80 shadow-sm hover:shadow-md transition-shadow bg-white",
        className,
      )}
    >
      <CardContent className="p-5 flex items-start gap-4">
        <div
          className={cn(
            "h-11 w-11 rounded-2xl shrink-0 flex items-center justify-center shadow-sm ring-8",
            "bg-gradient-to-br",
            theme.iconBg,
            theme.ring,
          )}
        >
          {icon && typeof icon === "function" ? (
            (() => {
              const IconCmp = icon as LucideIcon;
              return <IconCmp className="h-5 w-5" />;
            })()
          ) : (
            icon
          )}
        </div>
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium text-slate-500 truncate">{title}</span>
            {!loading && delta && delta.value ? (
              <span
                className={cn(
                  "inline-flex items-center gap-0.5 text-xs font-semibold shrink-0",
                  tone === "positive" && "text-emerald-600",
                  tone === "negative" && "text-rose-600",
                  tone === "neutral" && "text-slate-500",
                )}
              >
                {delta.direction === "up" ? (
                  <TrendingUp className="h-3.5 w-3.5" />
                ) : delta.direction === "down" ? (
                  <TrendingDown className="h-3.5 w-3.5" />
                ) : null}
                {delta.value}
              </span>
            ) : null}
          </div>
          <div className={cn("text-3xl font-bold tracking-tight text-slate-900 tabular-nums", loading && "animate-pulse bg-slate-100 rounded-md h-9 w-28 inline-block")}>
            {loading ? <span className="sr-only">loading</span> : value}
          </div>
          {subtitle ? (
            <p className={cn("text-xs text-slate-500 leading-5", loading && "opacity-60")}>{subtitle}</p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export default KpiCard;
