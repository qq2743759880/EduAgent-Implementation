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

const KIND_BADGE: Record<NonNullable<PointGainItem["kind"]>, string> = {
  study: "bg-sky-50 text-sky-700 border-sky-100",
  badge: "bg-violet-50 text-violet-700 border-violet-100",
  explore: "bg-emerald-50 text-emerald-700 border-emerald-100",
  share: "bg-amber-50 text-amber-700 border-amber-100",
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
        "border-slate-200/80 shadow-sm bg-gradient-to-br from-amber-50/40 via-white to-violet-50/40",
        className,
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Gift className="h-4 w-4 text-fuchsia-500" />
              积分与成长
            </CardTitle>
            <CardDescription className="text-sm text-slate-500 pt-1">
              完成学习任务、解锁徽章均可获得积分，积分可用于后续兑换成长特权。
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="pt-5 space-y-5">
        <div className="flex items-end justify-between gap-3 flex-wrap">
          <div className="space-y-1">
            <div className="text-xs text-slate-500 inline-flex items-center gap-1.5">
              <Coins className="h-3.5 w-3.5 text-amber-500" />
              当前积分
            </div>
            <div
              className={cn(
                "text-4xl font-extrabold tracking-tight tabular-nums bg-gradient-to-br from-amber-500 to-fuchsia-600 bg-clip-text text-transparent",
                loading && "opacity-60 animate-pulse",
              )}
            >
              {loading ? "—" : total.toLocaleString()}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Sparkle className={cn("h-4 w-4", gainTone === "emerald" ? "text-emerald-500" : gainTone === "rose" ? "text-rose-500" : "text-slate-400")} />
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-xl px-3 py-1 text-sm font-semibold tabular-nums border",
                gainTone === "emerald" && "bg-emerald-50 text-emerald-700 border-emerald-100",
                gainTone === "rose" && "bg-rose-50 text-rose-700 border-rose-100",
                gainTone === "slate" && "bg-slate-50 text-slate-600 border-slate-200",
              )}
            >
              {todayGain >= 0 ? "+" : ""}
              {todayGain.toLocaleString()}
              <span className="font-normal text-xs opacity-80">今日</span>
            </span>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>今日明细</span>
            {recentGains.length > 0 ? <span>共 {recentGains.length} 条</span> : null}
          </div>
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="h-8 rounded-lg bg-slate-100/80 animate-pulse"
                />
              ))}
            </div>
          ) : recentGains.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 bg-white/60 p-5 text-sm text-slate-400 flex flex-col items-center justify-center gap-1">
              <Sparkle className="h-4 w-4 text-slate-300" />
              今天还没有积分记录，去学习一个章节解锁第一枚积分吧。
            </div>
          ) : (
            <ul className="space-y-1.5">
              {recentGains.map((g, i) => (
                <li
                  key={g.key ?? `gain-${i}`}
                  className="group rounded-xl px-3 py-2 flex items-center justify-between gap-3 bg-white/70 hover:bg-white border border-transparent hover:border-slate-200/80 transition-all"
                >
                  <div className="min-w-0 flex items-center gap-2">
                    <Badge
                      variant="outline"
                      className={cn("text-[10px] border", KIND_BADGE[g.kind || "study"])}
                    >
                      {KIND_LABEL[g.kind || "study"]}
                    </Badge>
                    <span className="text-sm text-slate-800 truncate">{g.title}</span>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {g.at ? <span className="text-[11px] text-slate-400 tabular-nums">{g.at}</span> : null}
                    <span className="text-sm font-semibold tabular-nums text-emerald-600">
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
