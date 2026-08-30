"use client";

import { Coins, Gift, Sparkle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export interface PointGainItem {
  key: string;
  title: string;
  points: number;
  /** HH:mm 或短时间标签 */
  at?: string;
  /** badge 颜色：study / badge / explore / share */
  kind?: "study" | "badge" | "explore" | "share";
}

interface PointCardProps {
  total: number;
  todayGain: number;
  recentGains?: PointGainItem[];
  className?: string;
  loading?: boolean;
}

/** 积分明细类别徽章（fe-task07 收敛）：分功能 4 色 → 单主色；类别区分靠 KIND_LABEL 文字 */
const KIND_BADGE: Record<NonNullable<PointGainItem["kind"]>, string> = {
  study: "bg-primary-soft text-primary border-primary-border",
  badge: "bg-primary-soft text-primary border-primary-border",
  explore: "bg-primary-soft text-primary border-primary-border",
  share: "bg-primary-soft text-primary border-primary-border",
};

const KIND_LABEL: Record<NonNullable<PointGainItem["kind"]>, string> = {
  study: "学习",
  badge: "徽章",
  explore: "探索",
  share: "分享",
};

export function PointCard({
  total,
  todayGain,
  recentGains = [],
  className,
  loading = false,
}: PointCardProps) {
  const gainTone = todayGain > 0 ? "emerald" : todayGain < 0 ? "rose" : "slate";

  return (
    <Card
      className={cn(
        "border-border shadow-card bg-card",
        className,
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Gift className="h-4 w-4 text-primary" />
              积分与成长
            </CardTitle>
            <CardDescription className="text-sm text-muted-foreground pt-1">
              完成学习任务、解锁徽章均可获得积分，积分可用于后续兑换成长特权。
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="pt-5 space-y-5">
        <div className="flex items-end justify-between gap-3 flex-wrap">
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground inline-flex items-center gap-1.5">
              <Coins className="h-3.5 w-3.5 text-primary" />
              当前积分
            </div>
            <div
              className={cn(
                "text-4xl font-extrabold tracking-tight tabular-nums text-primary",
                loading && "opacity-60 animate-pulse",
              )}
            >
              {loading ? "—" : total.toLocaleString()}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Sparkle className={cn("h-4 w-4", gainTone === "emerald" ? "text-success" : gainTone === "rose" ? "text-destructive" : "text-muted-foreground")} />
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-xl px-3 py-1 text-sm font-semibold tabular-nums border",
                gainTone === "emerald" && "bg-success/10 text-success-foreground border-success/40",
                gainTone === "rose" && "bg-destructive/10 text-destructive-foreground border-destructive/30",
                gainTone === "slate" && "bg-muted text-secondary-foreground border-border",
              )}
            >
              {todayGain >= 0 ? "+" : ""}
              {todayGain.toLocaleString()}
              <span className="font-normal text-xs opacity-80">今日</span>
            </span>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>今日明细</span>
            {recentGains.length > 0 ? <span>共 {recentGains.length} 条</span> : null}
          </div>
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="h-8 rounded-lg bg-muted animate-pulse"
                />
              ))}
            </div>
          ) : recentGains.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border bg-card p-5 text-sm text-secondary-foreground flex flex-col items-center justify-center gap-1">
              <Sparkle className="h-4 w-4 text-muted-foreground/60" />
              今天还没有积分记录，去学习一个章节解锁第一枚积分吧。
            </div>
          ) : (
            <ul className="space-y-1.5">
              {recentGains.map((g, i) => (
                <li
                  key={g.key ?? `gain-${i}`}
                  className="group rounded-xl px-3 py-2 flex items-center justify-between gap-3 bg-card hover:bg-muted border border-transparent hover:border-border transition-all"
                >
                  <div className="min-w-0 flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className={cn("text-4xs border", KIND_BADGE[g.kind || "study"])}
                    >
                      {KIND_LABEL[g.kind || "study"]}
                    </Badge>
                    <span className="text-sm text-foreground truncate">{g.title}</span>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {g.at ? <span className="text-3xs text-secondary-foreground tabular-nums">{g.at}</span> : null}
                    <span className="text-sm font-semibold tabular-nums text-success-foreground">
                      +{g.points.toLocaleString()}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default PointCard;
