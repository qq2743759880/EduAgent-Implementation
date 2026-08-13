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
}

const CAT_COLORS: Record<NonNullable<BadgeItem["category"]>, { gradient: string; ring: string; chip: string }> = {
  streak: {
    gradient: "from-amber-400 to-orange-500 text-white",
    ring: "ring-amber-100",
    chip: "bg-amber-50 text-amber-700 border-amber-100",
  },
  subject: {
    gradient: "from-sky-500 to-indigo-600 text-white",
    ring: "ring-sky-100",
    chip: "bg-sky-50 text-sky-700 border-sky-100",
  },
  achievement: {
    gradient: "from-violet-500 to-fuchsia-600 text-white",
    ring: "ring-violet-100",
    chip: "bg-violet-50 text-violet-700 border-violet-100",
  },
  social: {
    gradient: "from-emerald-500 to-teal-600 text-white",
    ring: "ring-emerald-100",
    chip: "bg-emerald-50 text-emerald-700 border-emerald-100",
  },
  explore: {
    gradient: "from-rose-500 to-pink-600 text-white",
    ring: "ring-rose-100",
    chip: "bg-rose-50 text-rose-700 border-rose-100",
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
    <Card className={cn("border-slate-200/80 shadow-sm bg-white", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Award className="h-4 w-4 text-violet-500" />
              {title}
              <UIBadge
                variant="secondary"
                className="ml-1 bg-violet-50 text-violet-700 border border-violet-100 font-semibold"
              >
                {earned}/{total}
              </UIBadge>
            </CardTitle>
            <CardDescription className="text-sm text-slate-500 pt-1">{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="pt-5">
        {badges.length === 0 ? (
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
                  "group relative rounded-2xl border p-4 transition-all",
                  "flex flex-col items-center text-center gap-2",
                  "hover:-translate-y-0.5 hover:shadow-md",
                  b.earned
                    ? "bg-white border-slate-200 hover:border-violet-200"
                    : "bg-slate-50/70 border-dashed border-slate-200 hover:border-slate-300",
                )}
                title={b.unlockCondition && !b.earned ? `解锁条件：${b.unlockCondition}` : b.description}
              >
                <div
                  className={cn(
                    "relative h-14 w-14 rounded-2xl ring-8 flex items-center justify-center bg-gradient-to-br shadow-sm",
                    theme.gradient,
                    theme.ring,
                    !b.earned && "grayscale opacity-50",
                  )}
                >
                  {b.icon ?? <Sparkle className="h-6 w-6" />}
                  {!b.earned ? (
                    <span className="absolute -bottom-1 -right-1 h-6 w-6 rounded-full bg-slate-700/80 ring-2 ring-white text-white flex items-center justify-center">
                      <Lock className="h-3 w-3" />
                    </span>
                  ) : null}
                </div>
                <div className="space-y-0.5 min-h-0 flex-1 w-full">
                  <div className={cn("font-semibold text-slate-900 leading-5", !b.earned && "text-slate-500")}>
                    {b.name}
                  </div>
                  {b.description ? (
                    <p className="text-[11px] leading-4 text-slate-500 line-clamp-2 min-h-[2rem]">
                      {b.description}
                    </p>
                  ) : (
                    <div className="min-h-[2rem]" />
                  )}
                </div>
                <div className="flex flex-wrap justify-center gap-1 pt-1">
                  <UIBadge variant="outline" className={cn("text-[10px] font-medium border", theme.chip)}>
                    {CAT_LABELS[cat]}
                  </UIBadge>
                  {b.earnedAt ? (
                    <UIBadge variant="secondary" className="text-[10px] bg-slate-100 text-slate-600 border-slate-200">
                      {b.earnedAt}
                    </UIBadge>
                  ) : (
                    <UIBadge variant="outline" className="text-[10px] border-slate-200 text-slate-400">
                      未获得
                    </UIBadge>
                  )}
                </div>
                {!b.earned && b.unlockCondition ? (
                  <div className="mt-1 text-[10px] leading-4 text-slate-400 line-clamp-2 group-hover:text-slate-500">
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
