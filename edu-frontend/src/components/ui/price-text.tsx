"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

/** 金额千分位格式化（数值 → 「¥12,345.00」）。amount 传「元」数值/字符串；decimals 控制小数位（默认 2）。 */
export function formatAmount(
  amount: number | string | null | undefined,
  prefix = "¥",
  decimals = 2,
): string {
  if (amount === null || amount === undefined || amount === "") return "-";
  const n = Number(amount);
  if (Number.isNaN(n)) return "-";
  const fixed = n.toFixed(decimals);
  const [int, dec] = fixed.split(".");
  const withComma = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return decimals > 0 ? `${prefix}${withComma}.${dec}` : `${prefix}${withComma}`;
}

/**
 * 金额展示：tabular-nums 对齐，可划线显示原价、高亮促销价。
 *  - amount：现价（元）
 *  - original：若提供，显示为划线原价
 *  - highlight：促销高亮（primary 强调，勿用于危险语义）
 *  - decimals：小数位（默认 2；课程卡片「¥X 起」传 0）
 */
function PriceText({
  amount,
  prefix = "¥",
  original,
  highlight = false,
  decimals = 2,
  className,
  size = "md",
  ...props
}: React.ComponentProps<"span"> & {
  amount: number | string | null | undefined;
  prefix?: string;
  original?: number | string | null;
  highlight?: boolean;
  decimals?: number;
  size?: "sm" | "md" | "lg";
}) {
  return (
    <span
      data-slot="price-text"
      className={cn(
        "inline-flex items-baseline gap-1 tabular-nums whitespace-nowrap",
        size === "sm" && "text-sm",
        size === "md" && "text-base",
        size === "lg" && "text-xl",
        className
      )}
      {...props}
    >
      {original != null && original !== "" ? (
        <span className="text-xs text-muted-foreground line-through">
          {formatAmount(original, prefix, decimals)}
        </span>
      ) : null}
      <span className={cn("font-semibold", highlight ? "text-primary" : "text-foreground")}>
        {formatAmount(amount, prefix, decimals)}
      </span>
    </span>
  )
}

export { PriceText }