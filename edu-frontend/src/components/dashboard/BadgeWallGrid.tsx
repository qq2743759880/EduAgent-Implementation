"use client";

import { Award, Lock, Sparkle } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Badge as UIBadge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export interface BadgeItem {
  /** 唯一键，用于 React key */
  key: string;
  name: string;
  description?: string;
  /** 解锁条件（未获得时 tooltip 展示） */
  unlockCondition?: string;
  /** 徽章分类，用于 icon 颜色分组 */
  category?: "streak" | "subject" | "achievement" | "social" | "explore";
  /** 是否已获得 */
  earned?: boolean;
  /** 获得时间（字符串 ISO 或中文展示皆可） */
  earnedAt?: string;
  icon?: ReactNode;
}

interface BadgeWallGridProps {
  badges: BadgeItem[];
  title?: string;
  description?: string;
  className?: string;
  /** 至少 4 列；大屏最多 6 列 */
  minCols?: 3 | 4 | 5 | 6;
  /** 加载中：渲染等量网格骨架（替代空态误导文案，perf P1-3） */
  loading?: boolean;
}

/**
 * 徽章分类配色（fe-task07 收敛）：分功能 5 色 → 单主色（分类区分靠 CAT_LABELS 文字）；
 * ring 光环移除（ring 字段置空，消费方 cn 忽略）。
 */
const CAT_COLORS: Record<NonNullable<BadgeItem["category"]>, { gradient: string; ring: string; chip: string }> = {
  streak: {
    gradient: "bg-primary-soft text-primary",
    ring: "",
    chip: "bg-primary-soft text-primary border-primary-border",
  },
  subject: {
    gradient: "bg-primary-soft text-primary",
    ring: "",
    chip: "bg-primary-soft text-primary border-primary-border",
  },
  achievement: {
    gradient: "bg-primary-soft text-primary",
    ring: "",
    chip: "bg-primary-soft text-primary border-primary-border",
  },
  social: {
    gradient: "bg-primary-soft text-primary",
    ring: "",
    chip: "bg-primary-soft text-primary border-primary-border",
  },
  explore: {
    gradient: "bg-primary-soft text-primary",
    ring: "",
    chip: "bg-primary-soft text-primary border-primary-border",
  },
};

const CAT_LABELS: Record<NonNullable<BadgeItem["category"]>, string> = {
  streak: "连续打卡",
  subject: "学科专项",
  achievement: "里程碑",
  social: "协作成长",
  explore: "探索体验",
};

export function BadgeWallGrid({
  badges,
  title = "徽章墙",
  description = "持续学习、解锁徽章：点亮你的专属学习成长图谱。",
  className,
  minCols = 5,
  loading = false,
}: BadgeWallGridProps) {
  const earned = badges.filter((b) => b.earned).length;
  const total = badges.length;

  const gridCols =
    minCols === 3
      ? "grid-cols-3 sm:grid-cols-4 lg:grid-cols-6"
      : minCols === 4
      ? "grid-cols-2 sm:grid-cols-4 lg:grid-cols-6"
      : minCols === 6
      ? "grid-cols-3 sm:grid-cols-5 lg:grid-cols-6"
      : "grid-cols-3 sm:grid-cols-5 lg:grid-cols-6";

  return (
    <Card className={cn("border-border shadow-card bg-card", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Award className="h-4 w-4 text-primary" />
              {title}
              <UIBadge
                variant="secondary"
                className="ml-1 bg-primary-soft text-primary border border-primary-border font-semibold"
              >
                {earned}/{total}
              </UIBadge>
            </CardTitle>
            <CardDescription className="text-sm text-muted-foreground pt-1">{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="pt-5">
        {loading ? (
          /* 加载骨架：与数据网格同栅格等宽，避免空态误导闪现（perf P1-3）；aria-hidden 装饰性 */
          <div className={cn("grid gap-4", gridCols)} aria-hidden="true">
            {Array.from({ length: minCols }).map((_, i) => (
              <div
                key={i}
                className="flex flex-col items-center text-center gap-2 rounded-xl border border-border bg-muted/40 p-4"
              >
                <div className="h-14 w-14 rounded-xl bg-muted animate-pulse" />
                <div className="h-3.5 w-16 rounded bg-muted animate-pulse" />
                <div className="h-2.5 w-20 rounded bg-muted animate-pulse" />
              </div>
            ))}
          </div>
        ) : badges.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-muted/40 p-8 flex flex-col items-center justify-center gap-2 text-center">
            <Award className="h-8 w-8 text-muted-foreground/60" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">解锁第一枚徽章，从今天的学习开始</p>
            <Link href="/courses" className="text-sm font-medium text-primary hover:underline">
              去课程中心看看
            </Link>
          </div>
        ) : (
        <div className={cn("grid gap-4", gridCols)}>
          {badges.map((b, i) => {
            const cat = b.category || "achievement";
            const theme = CAT_COLORS[cat];
            return (
              <div
                key={b.key ?? `badge-${i}`}
                className={cn(
                  "group relative rounded-xl border p-4 transition-all",
                  "flex flex-col items-center text-center gap-2",
                  "hover:-translate-y-0.5 hover:shadow-card hover:border-primary-border",
                  b.earned
                    ? "bg-card border-border"
                    : "bg-muted/50 border-dashed border-border hover:border-muted-foreground/50",
                )}
                title={b.unlockCondition && !b.earned ? `解锁条件：${b.unlockCondition}` : b.description}
              >
                <div
                  className={cn(
                    "relative h-14 w-14 rounded-xl flex items-center justify-center shadow-sm",
                    theme.gradient,
                    !b.earned && "grayscale opacity-50",
                  )}
                >
                  {b.icon ?? <Sparkle className="h-6 w-6" />}
                  {!b.earned ? (
                    <span className="absolute -bottom-1 -right-1 h-6 w-6 rounded-full bg-slate-700/80 ring-2 ring-card text-white flex items-center justify-center">
                      <Lock className="h-3 w-3" />
                    </span>
                  ) : null}
                </div>
                <div className="space-y-0.5 min-h-0 flex-1 w-full">
                  <div className={cn("font-semibold text-foreground leading-5", !b.earned && "text-muted-foreground")}>
                    {b.name}
                  </div>
                  {b.description ? (
                    <p className="text-3xs leading-4 text-muted-foreground line-clamp-2 min-h-[2rem]">
                      {b.description}
                    </p>
                  ) : (
                    <div className="min-h-[2rem]" />
                  )}
                </div>
                <div className="flex flex-wrap justify-center gap-1 pt-1">
                  <UIBadge variant="outline" className={cn("text-4xs font-medium border", theme.chip)}>
                    {CAT_LABELS[cat]}
                  </UIBadge>
                  {b.earnedAt ? (
                    <UIBadge variant="secondary" className="text-4xs bg-muted text-secondary-foreground border-border">
                      {b.earnedAt}
                    </UIBadge>
                  ) : (
                    <UIBadge variant="outline" className="text-4xs border-border text-muted-foreground">
                      未获得
                    </UIBadge>
                  )}
                </div>
                {!b.earned && b.unlockCondition ? (
                  <div className="mt-1 text-4xs leading-4 text-muted-foreground line-clamp-2 group-hover:text-secondary-foreground">
                    解锁：{b.unlockCondition}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
        )}
      </CardContent>
    </Card>
  );
}

export default BadgeWallGrid;
