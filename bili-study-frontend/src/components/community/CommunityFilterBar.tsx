/**
 * CommunityFilterBar — 社区筛选行（candy-playful，task51 对齐 approved community.html）。
 * - 版块 chips：role=group + 单选 aria-pressed（非 APG Tabs，语义为单选筛选）。
 * - 排序：原生 select（HOT/NEW/LIKE）。
 * - 关键词搜索：输入防抖 300ms 触发 onSearch；回车/搜索按钮立即触发。
 * 受控：board/sort 由页面持有；keyword 在组件内瞬时输入、经防抖回传页面（React Query 以其为 key）。
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { BOARDS } from "@/lib/community-meta";
import type { BoardCode, PostSort } from "@/lib/api/community";

export interface CommunityFilterBarProps {
  board: BoardCode | "";
  onBoardChange: (board: BoardCode | "") => void;
  sort: PostSort;
  onSortChange: (sort: PostSort) => void;
  onSearch: (keyword: string) => void;
}

const SORT_LABELS: Record<PostSort, { label: string; emoji: string }> = {
  HOT: { label: "热门", emoji: "🔥" },
  NEW: { label: "最新", emoji: "🕒" },
  LIKE: { label: "点赞多", emoji: "👍" },
};

const SORTS: PostSort[] = ["HOT", "NEW", "LIKE"];

export function CommunityFilterBar({
  board,
  onBoardChange,
  sort,
  onSortChange,
  onSearch,
}: CommunityFilterBarProps) {
  const [input, setInput] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 跳过首次挂载：避免初始空输入也排程一次冗余的 onSearch("")
  const mounted = useRef(false);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onSearch(input.trim()), 300);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [input, onSearch]);

  return (
    <div className="flex flex-col gap-3 rounded-3xl border-[3px] border-foreground bg-white p-3 shadow-[0_5px_0_color-mix(in_oklch,var(--foreground),transparent_82%)] md:flex-row md:items-center md:justify-between">
      {/* 版块 chips（单选筛选） */}
      <div role="group" aria-label="按版块筛选" className="flex flex-wrap gap-2">
        {([
          { code: "", label: "全部" },
          ...BOARDS.map((b) => ({ code: b.code, label: b.label })),
        ] satisfies Array<{ code: BoardCode | ""; label: string }>).map((tab) => {
          const active = board === tab.code;
          return (
            <button
              key={tab.code || "all"}
              type="button"
              aria-pressed={active}
              onClick={() => onBoardChange(tab.code)}
              className={cn(
                "rounded-full border-2 px-3 py-1 text-2xs font-extrabold transition-colors",
                active
                  ? "border-foreground bg-candy-green text-white"
                  : "border-foreground/25 bg-white text-muted-foreground hover:border-candy-purple hover:text-foreground",
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* 排序 + 搜索 */}
      <div className="flex items-center gap-2">
        <label className="sr-only" htmlFor="community-sort">
          排序方式
        </label>
        <select
          id="community-sort"
          value={sort}
          onChange={(e) => onSortChange(e.target.value as PostSort)}
          className="rounded-full border-2 border-foreground/25 bg-white px-3 py-1 text-2xs font-bold text-foreground focus:border-foreground focus:outline-none"
        >
          {SORTS.map((s) => (
            <option key={s} value={s}>
              {SORT_LABELS[s].emoji} {SORT_LABELS[s].label}
            </option>
          ))}
        </select>

        <div className="flex items-center overflow-hidden rounded-full border-2 border-foreground/25 bg-white focus-within:border-foreground">
          <input
            type="search"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="搜帖子…"
            aria-label="搜索帖子关键词"
            className="bg-transparent px-3 py-1 text-2xs text-foreground outline-none placeholder:text-muted-foreground/60"
          />
          <button
            type="button"
            aria-label="搜索"
            onClick={() => onSearch(input.trim())}
            className="grid h-full place-items-center border-l-2 border-foreground/25 bg-candy-yellow px-2.5 text-foreground"
          >
            <Search className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  );
}