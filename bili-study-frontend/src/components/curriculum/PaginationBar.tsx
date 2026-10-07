/**
 * PaginationBar — 受控分页组件（shadcn Pagination 风格）
 * 首页/搜索页复用。
 */
"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface PaginationBarProps {
  page: number;
  total_pages: number;
  onChange: (page: number) => void;
  /** 两侧固定页码按钮数，默认 1 */
  siblingCount?: number;
  className?: string;
}

export function PaginationBar({
  page,
  total_pages,
  onChange,
  siblingCount = 1,
  className,
}: PaginationBarProps) {
  const pages = buildPages(page, Math.max(1, total_pages), siblingCount);
  const disabled = total_pages <= 1;

  return (
    <nav
      className={cn(
        "mx-auto flex w-full max-w-xl items-center justify-center gap-1.5 py-2",
        className,
      )}
      aria-label="分页"
    >
      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={() => onChange(Math.max(1, page - 1))}
        disabled={disabled || page <= 1}
        aria-label="上一页"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      {pages.map((p, i) =>
        p === "…" ? (
          <span
            key={"ellipsis-" + i}
            className="inline-flex h-9 w-9 items-center justify-center text-sm text-muted-foreground"
          >
            …
          </span>
        ) : (
          <Button
            type="button"
            key={p}
            variant={p === page ? "default" : "outline"}
            size="icon"
            onClick={() => onChange(p)}
            aria-current={p === page ? "page" : undefined}
          >
            {p}
          </Button>
        ),
      )}
      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={() => onChange(Math.min(total_pages, page + 1))}
        disabled={disabled || page >= total_pages}
        aria-label="下一页"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </nav>
  );
}

/**
 * 生成页码序列（支持省略号）。
 * 规则：首末 1 页常驻；当前页两侧 siblingCount 页；缺口用 "…"。
 */
export function buildPages(
  current: number,
  totalPages: number,
  siblingCount: number,
): (number | "…")[] {
  if (totalPages <= 1) return [1];
  const first = 1;
  const last = totalPages;
  const leftSibling = Math.max(first + 1, current - siblingCount);
  const rightSibling = Math.min(last - 1, current + siblingCount);
  const range: (number | "…")[] = [first];

  const showLeftDots = leftSibling > first + 1;
  const showRightDots = rightSibling < last - 1;

  if (showLeftDots) {
    range.push("…");
  } else {
    for (let i = first + 1; i < leftSibling; i++) range.push(i);
  }
  for (let i = leftSibling; i <= rightSibling; i++) range.push(i);
  if (showRightDots) {
    range.push("…");
  } else {
    for (let i = rightSibling + 1; i <= last - 1; i++) range.push(i);
  }
  if (last !== first) range.push(last);
  return range;
}
