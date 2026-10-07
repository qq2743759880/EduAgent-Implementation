/**
 * CandyStatRow — 复习中心顶层统计（task49，candy-playful frozen）
 *   - 错题待复习：listWrongBook(only_not_mastered).total（契约⑤ wrong-book，question 表出题源）
 *   - 单词待回忆 / 连续学习：getVocabProgress()（SM-2 词卡，范围外复用）
 * 数据缺失时以「—」占位，不伪造假值；失败静默（统计为增强信息，不阻塞主体）。
 */
"use client";

import { useMemo } from "react";
import { BookMarked, CalendarCheck2, ScrollText } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getVocabProgress, listWrongBook } from "@/lib/api/learning";
import { cn } from "@/lib/utils";

interface ItemDef {
  label: string;
  sub: string;
  value: string | null;
  icon: React.ReactNode;
  accent: "green" | "blue" | "purple";
}

export function CandyStatRow() {
  const wrongQ = useQuery({
    queryKey: ["practice_stat_wrong"] as const,
    queryFn: () => listWrongBook({ page: 1, page_size: 1, only_not_mastered: true }),
    staleTime: 2 * 60_000,
    retry: false,
  });
  const vocabQ = useQuery({
    queryKey: ["practice_stat_vocab"] as const,
    queryFn: () => getVocabProgress({ window_days: 30 }),
    staleTime: 2 * 60_000,
    retry: false,
  });

  const wrongTotal = wrongQ.data?.total;
  const dueToday = vocabQ.data?.due_today ?? null;
  const streak = vocabQ.data?.streak_days ?? null;

  const items: ItemDef[] = useMemo(
    () => [
      {
        label: "待复习错题",
        sub: "错题本 · 未掌握",
        value: wrongTotal != null ? String(wrongTotal) : "—",
        accent: "green",
        icon: <ScrollText className="h-5 w-5" aria-hidden="true" />,
      },
      {
        label: "待回忆单词",
        sub: "SM-2 今日到期",
        value: dueToday != null ? String(dueToday) : "—",
        accent: "blue",
        icon: <BookMarked className="h-5 w-5" aria-hidden="true" />,
      },
      {
        label: "连续学习",
        sub: "词卡每日打卡",
        value: streak != null ? `${streak} 天` : "—",
        accent: "purple",
        icon: <CalendarCheck2 className="h-5 w-5" aria-hidden="true" />,
      },
    ],
    [wrongTotal, dueToday, streak],
  );

  return (
    <div
      className="grid grid-cols-1 gap-3 sm:grid-cols-3"
      aria-label="复习概览"
    >
      {items.map((it) => (
        <div
          key={it.label}
          className="flex items-center gap-3 rounded-2xl border-[3px] border-foreground bg-white p-4 shadow-[0_5px_0_rgba(31,31,31,0.14)]"
        >
          <span
            className={cn(
              "grid h-11 w-11 shrink-0 place-items-center rounded-xl border-2 border-foreground",
              it.accent === "green" && "bg-candy-green-soft text-candy-green",
              it.accent === "blue" && "bg-candy-blue/15 text-candy-blue",
              it.accent === "purple" && "bg-candy-purple-soft text-candy-purple",
            )}
          >
            {it.icon}
          </span>
          <div className="min-w-0">
            <div className="text-xl font-extrabold leading-none tabular-nums">{it.value}</div>
            <div className="mt-1 truncate text-3xs font-bold text-muted-foreground">
              {it.label} <span className="font-medium">· {it.sub}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}