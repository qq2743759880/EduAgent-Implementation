"use client";

import { Award, Crown, Medal, Trophy, User } from "lucide-react";
import type { ReactNode } from "react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

export type RankRange = "day" | "week" | "month";

export interface RankEntry {
  rank: number;
  userId?: number | string;
  nickname: string;
  avatar?: string | null;
  score: number;
  /** 用于标记 Top1/2/3 之外额外突出的行；也用作「是我自己」标记 */
  mine?: boolean;
  /** 一行小标签，比如「本周提升 5 名」 */
  tag?: string;
}

interface RankListProps {
  /** 3 个周期的数据；若缺某个周期，切换到该周期会显示空状态 */
  data: Partial<Record<RankRange, RankEntry[]>> & {
    myRank?: Partial<Record<RankRange, RankEntry & { totalPlayers?: number }>>;
  };
  defaultRange?: RankRange;
  /** topN 显示，默认 10 */
  topN?: number;
  className?: string;
  loading?: boolean;
  /** 切换周期回调（父层触发 refetch） */
  onRangeChange?: (range: RankRange) => void;
}

const RANGE_LABEL: Record<RankRange, string> = {
  day: "今日",
  week: "本周",
  month: "本月",
};

/**
 * 名次奖牌图标（fe-task07 收敛）：名次多色 → 第一名 warning（奖牌豁免）、2/3 名 muted-foreground
 * （orange 为禁色删除）；名次靠既有 rank 序号数字 badge 结构补偿。
 */
const MEDAL_ICON: Record<number, ReactNode> = {
  1: <Crown className="h-4 w-4 text-warning-foreground" />,
  2: <Medal className="h-4 w-4 text-muted-foreground" />,
  3: <Trophy className="h-4 w-4 text-muted-foreground" />,
};

export function RankList({
  data,
  defaultRange = "week",
  topN = 10,
  className,
  loading = false,
  onRangeChange,
}: RankListProps) {
  const ranges: RankRange[] = ["day", "week", "month"];
  const myAny = data.myRank ?? {};

  return (
    <Card className={cn("border-border shadow-card bg-card", className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <Award className="h-4 w-4 text-primary" />
              学习排行榜
            </CardTitle>
            <CardDescription className="text-sm text-muted-foreground pt-1">
              和全站同学一起比拼：勤奋持续的同学将获得更多徽章与特权。
            </CardDescription>
          </div>
          <Badge variant="secondary" className="bg-primary-soft text-primary border-primary-border font-medium text-3xs">
            仅展示 TOP {topN}
          </Badge>
        </div>
      </CardHeader>
      <Tabs
        defaultValue={defaultRange}
        className="w-full"
        onValueChange={(v) => onRangeChange?.(v as RankRange)}
      >
        <div className="px-6">
          <TabsList className="grid grid-cols-3 max-w-xs mb-4 bg-card border border-border shadow-sm">
            {ranges.map((r) => (
              <TabsTrigger key={r} value={r} className="h-9 text-sm">
                {RANGE_LABEL[r]}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        {ranges.map((range) => {
          const list = (data[range] ?? []).slice(0, topN);
          const my = myAny[range];
          return (
            <TabsContent key={range} value={range} className="mt-0">
              <Separator />
              <CardContent className="pt-4 space-y-4">
                <RankListBody list={list} topN={topN} loading={loading} />
                {my ? <MyRankRow me={my} /> : null}
              </CardContent>
            </TabsContent>
          );
        })}
      </Tabs>
    </Card>
  );
}

function RankListBody({
  list,
  topN,
  loading,
}: {
  list: RankEntry[];
  topN: number;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="space-y-1.5">
        {/* 骨架行数与 topN 数据行对齐 + 行结构（px-3 py-2.5 + h-8）与 RankRow 同高，消除骨架→数据 CLS（perf P1-2） */}
        {Array.from({ length: topN }).map((_, i) => (
          <div key={i} className="px-3 py-2.5">
            <div className="h-8 rounded-xl bg-slate-100/80 animate-pulse" />
          </div>
        ))}
      </div>
    );
  }
  if (list.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-muted/40 p-6 text-sm text-muted-foreground flex flex-col items-center justify-center gap-1">
        <Trophy className="h-5 w-5 text-muted-foreground/60" />
        暂无排行榜数据，去完成一个练习让自己登上 TOP {topN} 吧。
      </div>
    );
  }
  return (
    <ul className="space-y-1.5">
      {list.map((u) => (
        <RankRow key={`${u.userId ?? u.nickname}-${u.rank}`} u={u} />
      ))}
    </ul>
  );
}

function RankRow({ u }: { u: RankEntry }) {
  const medal = MEDAL_ICON[u.rank];
  return (
    <li
      className={cn(
        "rounded-xl border px-3 py-2.5 flex items-center gap-3 transition-all",
        "bg-card border-border hover:bg-muted/60",
        u.mine && "ring-2 ring-primary-border",
      )}
    >
      <div className="w-7 shrink-0 flex items-center justify-center">
        {medal || <span className="text-sm font-semibold text-muted-foreground tabular-nums">{u.rank}</span>}
      </div>
      <Avatar className="h-8 w-8 shrink-0 border border-card shadow-sm">
        {u.avatar ? <AvatarImage src={u.avatar} alt={u.nickname} /> : null}
        <AvatarFallback className="text-xs bg-gradient-to-br from-primary-deep to-primary text-primary-foreground font-semibold">
          {u.nickname.slice(0, 1).toUpperCase()}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-foreground truncate">{u.nickname}</span>
          {u.mine ? (
            <Badge variant="outline" className="text-4xs bg-primary-soft text-primary border-primary-border shrink-0">
              我
            </Badge>
          ) : null}
          {u.tag ? (
            <span className="text-4xs text-success-foreground font-medium shrink-0">
              {u.tag}
            </span>
          ) : null}
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="text-sm font-bold tabular-nums text-foreground">
          {u.score.toLocaleString()}
        </div>
        <div className="text-4xs text-muted-foreground leading-none">积分</div>
      </div>
    </li>
  );
}

function MyRankRow({ me }: { me: RankEntry & { totalPlayers?: number } }) {
  const total = me.totalPlayers;
  return (
    <>
      <Separator />
      <div
        className={cn(
          "rounded-xl px-3 py-3 flex items-center gap-3",
          "bg-primary-soft text-primary ring-1 ring-primary-border",
        )}
      >
        <div className="w-7 shrink-0 flex items-center justify-center text-sm font-semibold text-primary tabular-nums">
          {me.rank ?? "—"}
        </div>
        <Avatar className="h-8 w-8 shrink-0 border-2 border-card shadow-sm">
          {me.avatar ? <AvatarImage src={me.avatar} alt={me.nickname} /> : null}
          <AvatarFallback className="text-xs bg-gradient-to-br from-primary-deep to-primary text-primary-foreground font-semibold">
            {(me.nickname || "U").slice(0, 1).toUpperCase()}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <User className="h-3.5 w-3.5 text-primary" />
            <span className="text-sm font-semibold text-primary-soft-foreground truncate">我的排名</span>
          </div>
          <p className="text-3xs text-muted-foreground leading-5 pt-0.5">
            {total
              ? `超过了总人数 ${Math.max(0, Math.round((1 - me.rank / total) * 100)).toFixed(0)}% 的同学`
              : "继续努力，每天学习 30 分钟就可以爬升一个台阶 📈"}
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm font-bold tabular-nums text-foreground">
            {me.score.toLocaleString()}
          </div>
          <div className="text-4xs text-muted-foreground leading-none">我的积分</div>
        </div>
      </div>
    </>
  );
}

export default RankList;
