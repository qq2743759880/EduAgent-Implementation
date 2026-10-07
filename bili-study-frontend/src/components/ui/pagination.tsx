"use client"

import * as React from "react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react"

/**
 * 分页：上一页 / 下一页 + 页码区间 + 总条数。
 *  - page >= 1；total 条数；pageSize 每页条数。
 *  - 位移分页（非页码条），适合后端游标/总量分页。
 *  a11y：nav[aria-label=分页导航] + 上/下页按钮 aria-label + disabled 边界。
 */
function Pagination({
  page = 1,
  pageSize = 20,
  total = 0,
  onPageChange,
  disabled = false,
  className,
  ...props
}: Omit<React.ComponentProps<"nav">, "onChange"> & {
  page?: number;
  pageSize?: number;
  total?: number;
  onPageChange?: (page: number) => void;
  disabled?: boolean;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const hasPrev = !disabled && safePage > 1;
  const hasNext = !disabled && safePage < totalPages;
  const rangeStart = total === 0 ? 0 : (safePage - 1) * pageSize + 1;
  const rangeEnd = Math.min(total, safePage * pageSize);

  const prev = () => onPageChange?.(safePage - 1);
  const next = () => onPageChange?.(safePage + 1);

  return (
    <nav
      data-slot="pagination"
      aria-label="分页导航"
      className={cn("flex flex-wrap items-center justify-end gap-3", className)}
      {...props}
    >
      <span className="text-xs text-muted-foreground" aria-live="polite">
        {total === 0
          ? "共 0 条"
          : `第 ${rangeStart}-${rangeEnd} 条 / 共 ${total} 条`}
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="xs"
          onClick={prev}
          disabled={!hasPrev}
          aria-label="上一页"
        >
          <ChevronLeftIcon />
        </Button>
        <span className="min-w-14 px-2 text-center text-xs text-muted-foreground tabular-nums" aria-live="polite">
          {safePage} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="xs"
          onClick={next}
          disabled={!hasNext}
          aria-label="下一页"
        >
          <ChevronRightIcon />
        </Button>
      </div>
    </nav>
  )
}

export { Pagination }