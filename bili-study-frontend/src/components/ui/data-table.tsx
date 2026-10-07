"use client"

import * as React from "react"

import { cn } from "@/lib/utils"
import { EmptyState } from "@/components/ui/empty-state"
import { Skeleton } from "@/components/ui/skeleton"
import { ArrowDownIcon, ArrowUpIcon, ArrowUpDownIcon, InboxIcon } from "lucide-react"

/** 排序列定义：key 必填（渲染 accessor 或 row[key]），accessor 优先。 */
export type DataTableColumn<T> = {
  key: string;
  header: React.ReactNode;
  accessor?: (row: T) => React.ReactNode;
  sortable?: boolean;
  align?: "left" | "center" | "right";
  className?: string; // th 样式
  cellClassName?: string;
};

export type SortState = {
  key: string;
  dir: "asc" | "desc";
} | null;

/**
 * 通用数据表：内建 排序表头 / 加载骨架 / 空态。
 *  - 排序通过 onSortChange 回传（不内置状态，保持无状态受控）。
 *  a11y：原生 table 结构；可排序列 th 带 aria-sort；排序触发为可聚焦按钮（键盘可达）。
 */
function DataTable<T>({
  columns,
  data,
  rowKey,
  loading = false,
  sort = null,
  onSortChange,
  onRowClick,
  emptyTitle = "暂无数据",
  emptyDescription,
  emptyAction,
  className,
  tableClassName,
}: {
  columns: DataTableColumn<T>[];
  data: T[];
  rowKey: (row: T) => string | number;
  loading?: boolean;
  sort?: SortState;
  onSortChange?: (key: string, dir: "asc" | "desc") => void;
  onRowClick?: (row: T) => void;
  emptyTitle?: React.ReactNode;
  emptyDescription?: React.ReactNode;
  emptyAction?: React.ReactNode;
  className?: string;
  tableClassName?: string;
}) {
  const alignClass = (align?: DataTableColumn<T>["align"]) =>
    align === "center"
      ? "text-center"
      : align === "right"
        ? "text-right"
        : "text-left";

  const renderCell = (col: DataTableColumn<T>, row: T) =>
    col.accessor?.(row) ?? ((row as Record<string, unknown>)[col.key] as React.ReactNode) ?? "-";

  // 加载骨架：与真实列同构，aria-busy + 骨架无实义文字
  const renderSkeletonRows = () =>
    Array.from({ length: 5 }).map((_, ri) => (
      <tr key={ri} className="border-b border-border/60 last:border-0" aria-hidden="true">
        {columns.map((col) => (
          <td key={col.key} className={cn("px-4 py-3", alignClass(col.align))}>
            <Skeleton className={cn("h-4", col.align === "center" ? "mx-auto" : "")} />
          </td>
        ))}
      </tr>
    ));

  return (
    <div
      data-slot="data-table"
      className={cn("overflow-x-auto rounded-xl border border-border", className)}
      aria-busy={loading || undefined}
    >
      <table className={cn("w-full min-w-full border-collapse text-sm", tableClassName)}>
        <thead>
          <tr className="border-b border-border bg-muted/40 text-xs text-muted-foreground">
            {columns.map((col) => {
              const active = sort?.key === col.key;
              const ariaSort = col.sortable
                ? active
                  ? sort?.dir === "asc"
                    ? "ascending"
                    : "descending"
                  : "none"
                : undefined;
              return (
                <th
                  key={col.key}
                  scope="col"
                  aria-sort={ariaSort}
                  className={cn("px-4 py-2.5 font-medium", alignClass(col.align), col.className)}
                >
                  {col.sortable ? (
                    <button
                      type="button"
                      onClick={() =>
                        onSortChange?.(
                          col.key,
                          active && sort?.dir === "asc" ? "desc" : "asc"
                        )
                      }
                      className={cn(
                        "inline-flex items-center gap-1 rounded-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                        active ? "text-foreground" : "hover:text-foreground"
                      )}
                      aria-label={`按${typeof col.header === "string" ? col.header : col.key}排序`}
                    >
                      {col.header}
                      {active ? (
                        sort?.dir === "asc" ? (
                          <ArrowUpIcon className="size-3" />
                        ) : (
                          <ArrowDownIcon className="size-3" />
                        )
                      ) : (
                        <ArrowUpDownIcon className="size-3 text-muted-foreground" />
                      )}
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading
            ? renderSkeletonRows()
            : data.map((row) => (
                <tr
                  key={rowKey(row)}
                  className={cn(
                    "border-b border-border/60 transition-colors last:border-0",
                    onRowClick && "cursor-pointer hover:bg-muted/40"
                  )}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((col) => (
                    <td key={col.key} className={cn("px-4 py-3", alignClass(col.align), col.cellClassName)}>
                      {renderCell(col, row)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
      {!loading && data.length === 0 && (
        <div className="border-t border-border/60">
          <EmptyState
            icon={<InboxIcon />}
            title={emptyTitle ?? "暂无数据"}
            description={emptyDescription}
            action={emptyAction}
          />
        </div>
      )}
    </div>
  )
}

export { DataTable }