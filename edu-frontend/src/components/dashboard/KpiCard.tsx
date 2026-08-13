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

/**
 * 指标卡配色（fe-task07 收敛）：分功能 6 色 → 单主色（指标区分靠标题文字）；
 * ring 光环移除（ring 字段置空，消费方 cn 忽略）。
 */
const ACCENT_MAP: Record<NonNullable<KpiCardProps["accent"]>, { iconBg: string; ring: string; tintText: string }> = {
  indigo: {
    iconBg: "bg-primary-soft text-primary",
    ring: "",
    tintText: "text-primary",
  },
  emerald: {
    iconBg: "bg-primary-soft text-primary",
    ring: "",
    tintText: "text-primary",
  },
  amber: {
    iconBg: "bg-primary-soft text-primary",
    ring: "",
    tintText: "text-primary",
  },
  sky: {
    iconBg: "bg-primary-soft text-primary",
    ring: "",
    tintText: "text-primary",
  },
  rose: {
    iconBg: "bg-primary-soft text-primary",
    ring: "",
    tintText: "text-primary",
  },
  violet: {
    iconBg: "bg-primary-soft text-primary",
    ring: "",
    tintText: "text-primary",
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
        "overflow-hidden border-border shadow-card transition-shadow bg-card",
        className,
      )}
    >
      <CardContent className="p-5 flex items-start gap-4">
        <div
          className={cn(
            "h-11 w-11 rounded-xl shrink-0 flex items-center justify-center shadow-sm",
            theme.iconBg,
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
            <span className="text-sm font-medium text-muted-foreground truncate">{title}</span>
            {!loading && delta && delta.value ? (
              <span
                className={cn(
                  "inline-flex items-center gap-0.5 text-xs font-semibold shrink-0",
                  tone === "positive" && "text-success-foreground",
                  tone === "negative" && "text-destructive",
                  tone === "neutral" && "text-muted-foreground",
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
          <div className={cn("text-3xl font-bold tracking-tight text-foreground tabular-nums", loading && "animate-pulse bg-muted rounded-md h-9 w-28 inline-block")}>
            {loading ? <span className="sr-only">loading</span> : value}
          </div>
          {subtitle ? (
            <p className={cn("text-xs text-muted-foreground leading-5", loading && "opacity-60")}>{subtitle}</p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export default KpiCard;
