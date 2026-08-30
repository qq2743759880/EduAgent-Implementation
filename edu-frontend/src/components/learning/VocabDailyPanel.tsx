/**
 * VocabDailyPanel — 单词本每日卡片面板（P5 /api/vocab/daily + /recall）
 * 特性：
 *   - 卡片翻面：正面 word + phonetic + 例句；点击「显示释义」→翻面（definition）
 *   - SM-2 质量 6 按钮：0/1（失败，当天重复） 2/3（勉强，天数短） 4/5（轻松，间隔拉长）
 *   - 今日进度条（已完成/计划数）；compact 模式下隐藏复习模式切换
 */
"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenText,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Eye,
  Flame,
  Loader2,
  RotateCcw,
  Volume2,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { toast } from "sonner";
import {
  getVocabDaily,
  recallVocab,
  type VocabCardOut,
} from "@/lib/api/learning";
import { cn } from "@/lib/utils";

export interface VocabDailyPanelProps {
  subject_code?: "english" | string;
  plan_count?: number;
  compact?: boolean;
  /** 每次 recall 后的回调（用于更新单词进度卡） */
  onRecall?: (payload: { card_id: number | string; quality: 0 | 1 | 2 | 3 | 4 | 5; accepted: boolean }) => void;
}

const SM_QUALITIES: ReadonlyArray<{
  q: 0 | 1 | 2 | 3 | 4 | 5;
  label: string;
  desc: string;
  tone: "fail" | "mild" | "good";
}> = [
  { q: 0, label: "0", desc: "完全不记得", tone: "fail" },
  { q: 1, label: "1", desc: "错误但似曾相识", tone: "fail" },
  { q: 2, label: "2", desc: "错误但回忆难度大", tone: "mild" },
  { q: 3, label: "3", desc: "勉强记得", tone: "mild" },
  { q: 4, label: "4", desc: "记得（正常）", tone: "good" },
  { q: 5, label: "5", desc: "秒记，完美", tone: "good" },
];

export function VocabDailyPanel({
  subject_code = "english",
  plan_count = 20,
  compact = false,
  onRecall,
}: VocabDailyPanelProps) {
  const q = useQuery({
    queryKey: ["vocab_daily", subject_code, plan_count] as const,
    async queryFn() {
      return getVocabDaily({ subject_code, plan_count, include_new_ratio: 0.3 });
    },
    staleTime: 60_000,
  });

  const cards: VocabCardOut[] = q.data?.cards ?? [];
  const planCount = q.data?.plan_count ?? plan_count;
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [finishedIds, setFinishedIds] = useState<ReadonlySet<string | number>>(
    () => new Set(),
  );

  useEffect(() => {
    setIndex(0);
    setRevealed(false);
  }, [q.dataUpdatedAt, q.data?.today]);

  const currentCard: VocabCardOut | undefined = cards[index];
  const progress = cards.length
    ? Math.max(0, Math.min(1, finishedIds.size / Math.max(1, planCount)))
    : 0;

  const qc = useQueryClient();
  const submit = useMutation({
    async mutationFn(payload: { card: VocabCardOut; quality: 0 | 1 | 2 | 3 | 4 | 5 }) {
      return recallVocab({
        card_id: payload.card.card_id,
        quality: payload.quality,
      });
    },
    onSuccess: async (r, variables) => {
      onRecall?.({
        card_id: variables.card.card_id,
        quality: variables.quality,
        accepted: !!r.accepted,
      });
      setFinishedIds((prev) => {
        const next = new Set(prev);
        next.add(variables.card.card_id);
        return next;
      });
      if (variables.quality <= 1) {
        toast.message("本次错误，稍后会再次出现", { description: "SM-2 质量 0-1 → 当天重复" });
      } else {
        toast.success("已记录回忆质量");
      }
      // 等下一张卡
      goNext();
      // 同步刷新进度视图（VocabProgressCard 订阅 vocab/progress）
      await qc.invalidateQueries({ queryKey: ["vocab_progress"] });
    },
  });

  const goNext = useCallback(() => {
    setRevealed(false);
    setTimeout(() => {
      setIndex((i) => {
        if (cards.length === 0) return i;
        const next = (i + 1) % cards.length;
        return next;
      });
    }, 80);
  }, [cards.length]);
  const goPrev = useCallback(() => {
    setRevealed(false);
    setTimeout(() => {
      setIndex((i) => {
        if (cards.length === 0) return i;
        return (i - 1 + cards.length) % cards.length;
      });
    }, 80);
  }, [cards.length]);

  return (
    <Card>
      <CardHeader className={cn("flex-row flex-wrap items-center justify-between gap-3", compact && "py-4")}>
        <div>
          <CardTitle className="flex items-center gap-2 text-lg">
            <BookOpenText className="h-5 w-5 text-primary" />
            今日单词
          </CardTitle>
          <CardDescription>
            {q.data?.today ?? new Date().toISOString().slice(0, 10)} · 计划{" "}
            <b>{planCount}</b> 张，已复习 <b>{finishedIds.size}</b> 张
            {q.data?.new_today ? `（含 ${q.data.new_today} 新词）` : ""}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {!compact && (
            <Button asChild size="sm" variant="ghost">
              <Link href="/practice/vocab">
                <Flame className="mr-1.5 h-4 w-4" />
                去复习中心
              </Link>
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => void q.refetch()}
            disabled={q.isFetching}
          >
            <RotateCcw className={"mr-1.5 h-4 w-4 " + (q.isFetching ? "animate-spin" : "")} />
            重新出题
          </Button>
        </div>
      </CardHeader>
      <CardContent className={cn("space-y-4", compact && "pt-0")}>
        <div>
          <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
            <span>今日完成度</span>
            <span>{(progress * 100).toFixed(0)}%</span>
          </div>
          <Progress value={progress * 100} />
        </div>

        {q.isLoading && !q.data ? (
          <CardSkeleton />
        ) : q.isError ? (
          <ErrorState msg={q.error instanceof Error ? q.error.message : "加载失败"} onRetry={() => q.refetch()} />
        ) : cards.length === 0 ? (
          <EmptyToday />
        ) : (
          <CardStack
            card={currentCard}
            total={cards.length}
            index={index}
            revealed={revealed}
            onReveal={() => setRevealed(true)}
            onPrev={goPrev}
            onNext={goNext}
            finishedCurrent={
              !!currentCard && finishedIds.has(currentCard.card_id)
            }
          />
        )}

        {currentCard && (
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">
              回忆质量（SM-2）：点击按钮提交本次记忆
            </div>
            <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
              {SM_QUALITIES.map((meta) => (
                <Button
                  key={meta.q}
                  type="button"
                  variant={revealed ? "outline" : "ghost"}
                  disabled={!revealed || submit.isPending}
                  onClick={() => submit.mutate({ card: currentCard, quality: meta.q })}
                  className={cn(
                    "flex-col gap-0.5 !py-2.5",
                    revealed &&
                      (meta.tone === "fail"
                        ? "border-destructive/40 text-destructive hover:bg-destructive/10"
                        : meta.tone === "mild"
                          ? "border-warning/40 text-warning-foreground hover:bg-warning/10"
                          : "border-success/40 text-success-foreground hover:bg-success/10"),
                  )}
                >
                  <span className="text-sm font-bold">{meta.label}</span>
                  <span className="line-clamp-1 text-4xs text-current/80">{meta.desc}</span>
                </Button>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ---------- 子组件 ---------- */

function CardStack({
  card,
  total,
  index,
  revealed,
  onReveal,
  onPrev,
  onNext,
  finishedCurrent,
}: {
  card: VocabCardOut;
  total: number;
  index: number;
  revealed: boolean;
  onReveal: () => void;
  onPrev: () => void;
  onNext: () => void;
  finishedCurrent: boolean;
}) {
  return (
    <div className="relative [perspective:1400px]">
      <div
        onClick={revealed ? undefined : onReveal}
        className={cn(
          "relative min-h-[260px] cursor-pointer select-none rounded-xl border p-5 transition-all duration-300",
          revealed ? "shadow-lg ring-2 ring-primary/20 bg-card border-primary-border" : "bg-muted/40 border-border hover:bg-muted/60",
        )}
      >
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="text-xs">
            第 {index + 1} / {total} 张
          </Badge>
          {card.interval_days != null && card.interval_days >= 1 && (
            <Badge variant="outline" className="text-xs">
              SM-2 间隔 {card.interval_days} 天
            </Badge>
          )}
          {card.ef != null && (
            <Badge variant="outline" className="text-xs">
              EF {card.ef.toFixed(2)}
            </Badge>
          )}
          {finishedCurrent ? (
            <Badge className="ml-auto bg-success-foreground text-white text-xs gap-1">
              <CheckCircle2 className="h-3 w-3" /> 已回忆
            </Badge>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="ml-auto"
              onClick={(e) => {
                e.stopPropagation();
                onReveal();
              }}
            >
              <Eye className="mr-1.5 h-4 w-4" />
              {revealed ? "已显示" : "显示释义"}
            </Button>
          )}
        </div>

        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-3xl font-bold tracking-tight">{card.word}</div>
            {card.phonetic && (
              <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                <Volume2 className="h-3.5 w-3.5" />
                {card.phonetic}
              </div>
            )}
          </div>
          <div className="hidden items-center gap-1 md:flex">
            <Button type="button" variant="outline" size="icon" onClick={onPrev} aria-label="上一张">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="icon" onClick={onNext} aria-label="下一张">
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* 背面：释义 + 例句（有 reveal 动效） */}
        <div
          className={cn(
            "mt-4 overflow-hidden transition-all",
            revealed ? "max-h-[480px] opacity-100" : "max-h-0 opacity-0",
          )}
        >
          <div className="space-y-3 rounded-xl border border-border bg-card p-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                中文释义
              </div>
              <div className="mt-1 whitespace-pre-wrap leading-7">
                {card.definition ?? "暂无释义，请先显示释义。"}
              </div>
            </div>
            {card.examples?.length ? (
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  例句
                </div>
                <ul className="mt-1 space-y-1.5 text-sm leading-6">
                  {card.examples.slice(0, 3).map((e, i) => (
                    <li key={i} className="before:mr-2 before:text-primary/70 before:content-['›']">
                      {e}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {card.next_review_at ? (
              <div className="text-xs text-muted-foreground">
                下次复习：{new Date(card.next_review_at).toLocaleDateString()}
              </div>
            ) : null}
          </div>
        </div>

        {!revealed && (
          <div className="mt-4 rounded-xl border border-dashed p-3 text-center text-xs text-muted-foreground">
            尝试回忆释义后，点击卡片或右上角「显示释义」查看答案。
          </div>
        )}
      </div>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="space-y-3 rounded-xl border border-border bg-muted/40 p-5">
      <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
      <div className="h-9 w-1/2 animate-pulse rounded bg-muted" />
      <div className="h-4 w-full animate-pulse rounded bg-muted" />
      <div className="h-28 w-full animate-pulse rounded-xl bg-muted" />
    </div>
  );
}

function ErrorState({ msg, onRetry }: { msg: string; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-5">
      <div className="flex items-center gap-2 text-destructive-foreground">
        <XCircle className="h-5 w-5" />
        <span className="font-semibold">加载失败</span>
      </div>
      <p className="mt-1 text-sm text-destructive-foreground/90">{msg}</p>
      <Button size="sm" variant="outline" className="mt-3 border-destructive/30 text-destructive hover:bg-destructive/10" onClick={onRetry}>
        <Loader2 className="mr-1.5 h-4 w-4" /> 重试
      </Button>
    </div>
  );
}

function EmptyToday() {
  return (
    <div className="rounded-xl border border-dashed border-border p-8 text-center">
      <Flame className="mx-auto mb-2 h-6 w-6 text-warning-foreground" />
      <div className="text-base font-semibold text-foreground">今天暂无复习任务</div>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        你已完成今日计划，或英语单词本还没有内容。点「重新出题」可让 P5 再抓一批。
      </p>
      <div className="mt-4 flex items-center justify-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href="/practice/vocab">查看单词进度</Link>
        </Button>
      </div>
    </div>
  );
}
