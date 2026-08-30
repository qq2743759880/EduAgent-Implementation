/**
 * VocabProgressCard — 单词总览进度卡
 * 数据来源：P5 /api/vocab/progress（streak_days / 词数三态 / 30 天学习热力）
 */
"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { BookOpenText, Flame, Loader2, Target, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getVocabProgress, type VocabProgressOut } from "@/lib/api/learning";
import { cn } from "@/lib/utils";

export interface VocabProgressCardProps {
  subjectCode?: string;
  windowDays?: number;
  compact?: boolean;
}

export function VocabProgressCard({
  subjectCode = "english",
  windowDays = 30,
  compact = false,
}: VocabProgressCardProps) {
  const q = useQuery({
    queryKey: ["vocab_progress", subjectCode, windowDays] as const,
    async queryFn(): Promise<VocabProgressOut> {
      return getVocabProgress({ subject_code: subjectCode, window_days: windowDays });
    },
    staleTime: 120_000,
  });
  const d: VocabProgressOut = q.data ?? {};
  const total = d.total_cards ?? 0;
  const mastered = d.mastered_cards ?? 0;
  const learning = d.learning_cards ?? 0;
  const due = d.due_today ?? 0;
  const streak = d.streak_days ?? 0;
  const series = d.last_30_days ?? [];
  const seriesMax = Math.max(1, ...series.map((x) => x.studied_count ?? 0));

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-lg">
            <BookOpenText className="h-5 w-5 text-primary" />
            单词本 · 总览
          </CardTitle>
          <CardDescription>
            近 {windowDays} 天 · 连续打卡 {streak} 天
            {q.data?.subject_code ? ` · ${q.data.subject_code.toUpperCase()}` : ""}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild size="sm" variant="ghost">
            <Link href="/practice/vocab">
              <Target className="mr-1.5 h-4 w-4" />
              打开复习页
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent className={cn("space-y-4", compact && "pt-0")}>
        {/* 顶部数字 4 宫格（fe-task07：统计分类 4 色 → 主色/状态；已掌握=success 状态保留） */}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatCell label="总词数" value={total.toLocaleString()} Icon={Users} tone="bg-primary" />
          <StatCell label="已掌握" value={mastered.toLocaleString()} Icon={Target} tone="bg-success" />
          <StatCell label="学习中" value={learning.toLocaleString()} Icon={BookOpenText} tone="bg-primary" />
          <StatCell label="今日待复习" value={due.toLocaleString()} Icon={Flame} tone="bg-warning-foreground" />
        </div>

        <SeparatorSoft />

        {/* 30 天热力（简化为彩色柱子） */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">近 {windowDays} 天学习量</span>
            <span className="text-muted-foreground">
              峰值：{seriesMax === 1 ? "—" : seriesMax.toLocaleString()} 词 / 天
            </span>
          </div>
          {q.isFetching && !q.data ? (
            <div className="h-14 w-full animate-pulse rounded-xl bg-muted" />
          ) : series.length ? (
            <div className="flex h-16 items-end gap-[2px] overflow-x-auto pr-1">
              {series.map((row, i) => {
                const count = row.studied_count ?? 0;
                const ratio = count / seriesMax;
                const level =
                  count === 0 ? 0 : ratio < 0.15 ? 1 : ratio < 0.4 ? 2 : ratio < 0.7 ? 3 : 4;
                return (
                  <div
                    key={row.date ?? i}
                    title={`${row.date ?? ""} · ${count} 次学习`}
                    className={cn(
                      "min-w-[10px] flex-1 rounded-sm transition-all",
                      colorForLevel(level),
                    )}
                    style={{ height: `${Math.max(6, ratio * 100)}%` }}
                  />
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed p-5 text-center text-xs text-muted-foreground">
              暂无 30 天学习记录。去单词面板随便复习一张吧～
            </div>
          )}
        </div>

        {/* 掌握比例条 */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">掌握比例</span>
            <span className="font-semibold text-foreground">
              {total > 0 ? ((mastered / total) * 100).toFixed(1) : 0}%
              <Badge variant="secondary" className="ml-2 text-4xs">
                {mastered.toLocaleString()} / {total.toLocaleString()}
              </Badge>
            </span>
          </div>
          <div className="relative h-3 overflow-hidden rounded-full bg-muted">
            <div
              className="absolute inset-y-0 left-0 bg-success"
              style={{ width: `${total > 0 ? (mastered / total) * 100 : 0}%` }}
            />
            <div
              className="absolute inset-y-0 bg-primary"
              style={{
                left: `${total > 0 ? (mastered / total) * 100 : 0}%`,
                width: `${total > 0 ? (learning / total) * 100 : 0}%`,
                opacity: 0.85,
              }}
            />
          </div>
          <div className="flex items-center gap-3 text-3xs text-muted-foreground">
            <Legend dot="bg-success" label="已掌握" />
            <Legend dot="bg-primary" label="学习中" />
            <Legend dot="bg-muted-foreground/50" label="未开始" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StatCell({
  label,
  value,
  Icon,
  tone,
}: {
  label: string;
  value: string;
  Icon: React.ComponentType<{ className?: string }>;
  tone: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-gradient-to-b from-card to-muted/40 p-3.5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className={cn("grid h-6 w-6 place-items-center rounded-md text-white", tone)}>
          <Icon className="h-3.5 w-3.5" />
        </span>
        {label}
      </div>
      <div className="mt-1.5 text-xl font-bold tabular-nums leading-none text-foreground">{value}</div>
    </div>
  );
}

function Legend({ dot, label }: { dot: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("inline-block h-2.5 w-2.5 rounded-full", dot)} />
      {label}
    </span>
  );
}

function SeparatorSoft() {
  return <div className="h-px w-full bg-border" />;
}

function colorForLevel(level: number): string {
  // fe-task07：热力分级 → 主色系透明度（数据密度分级，文字/高度补偿）
  switch (level) {
    case 0:
      return "bg-muted";
    case 1:
      return "bg-primary/20";
    case 2:
      return "bg-primary/50";
    case 3:
      return "bg-primary/80";
    default:
      return "bg-primary";
  }
}

// 为 Loader2 留位（未来增加 loading 细节）
export const __vocab_load_loader = Loader2;
