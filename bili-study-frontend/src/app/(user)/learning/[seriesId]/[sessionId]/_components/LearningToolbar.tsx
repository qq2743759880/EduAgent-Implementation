/**
 * LearningToolbar — 学习页底部工具栏（task48 糖果色，fixed 底部）
 *   - AI 提问 → /chat?context=session:{sessionId}（J17）
 *   - 错题本 → /practice（J18）
 */
"use client";

import Link from "next/link";
import { BookOpen, Bot, Sparkles } from "lucide-react";

export interface LearningToolbarProps {
  seriesId: number;
  sessionId: number;
}

export function LearningToolbar({ seriesId, sessionId }: LearningToolbarProps) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-20 border-t-[3px] border-foreground bg-white shadow-[0_-4px_0_rgba(31,31,31,0.1)]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-2.5 md:px-6">
        <Link
          href={`/chat?context=session:${sessionId}`}
          className="inline-flex min-w-[200px] flex-1 items-center gap-3 rounded-xl border-[3px] border-foreground bg-candy-purple px-4 py-2.5 text-left text-sm font-extrabold text-white shadow-[0_4px_0_rgba(124,58,237,0.5)] transition-transform hover:-translate-y-px active:translate-y-px"
        >
          <Bot className="h-5 w-5 shrink-0" aria-hidden="true" />
          <span className="flex flex-col leading-tight">
            <span className="inline-flex items-center gap-1">
              AI 提问 · 本课答疑
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            </span>
            <span className="text-3xs font-semibold text-white/85">
              基于本节内容实时问答
            </span>
          </span>
        </Link>
        <Link
          href={`/practice?from_session=${sessionId}`}
          className="inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-white px-4 py-2.5 text-sm font-extrabold text-foreground shadow-[0_4px_0_rgba(31,31,31,0.16)] transition-transform hover:-translate-y-px active:translate-y-px"
        >
          <BookOpen className="h-4 w-4" aria-hidden="true" />
          错题本 · 去练习
        </Link>
        <span className="order-3 w-full text-center text-3xs font-medium text-muted-foreground md:order-none md:w-auto">
          会话上下文 · session:{sessionId} · 系列 {seriesId}
        </span>
      </div>
    </div>
  );
}