"use client"

import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"
import { statusText, statusTone, type StatusMapKey, type StatusTone } from "@/lib/status"

/**
 * 状态徽章：颜色 + 文字 双通道（禁止纯色块）。
 *  - 推荐用法：`<StatusBadge map="order_status" status="paid" />`，tone/label 从映射表自动解析。
 *  - 覆盖用法：手动传入 `tone` / `label`（如枚举值未纳入映射表时）。
 * a11y：状态由文本承载（不依赖颜色传达），tone 仅作视觉增强。
 */

const statusBadgeVariants = cva(
  "inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 rounded-4xl border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        success: "bg-success/10 text-success",
        warning: "bg-warning/10 text-warning",
        danger: "bg-destructive/10 text-destructive",
        neutral: "bg-muted text-muted-foreground",
        primary: "bg-primary-soft text-primary-soft-foreground",
      },
    },
    defaultVariants: {
      tone: "neutral",
    },
  }
)

export type StatusBadgeProps = {
  /** 枚举组 key（取 §3.3 STATUS_MAPS） */
  map?: StatusMapKey;
  /** 后端原始状态值（snake_case），经 map 解析出 tone/label */
  status?: string | null;
  /** 手动覆盖文案（优先于 map 解析） */
  label?: string;
  /** 手动覆盖色调（优先于 map 解析） */
  tone?: StatusTone;
  /** 展示形态：badge=完整胶囊，dot=语义点+紧凑 */
  variant?: "badge" | "dot";
};

function StatusBadge({
  map,
  status,
  label,
  tone,
  variant = "badge",
  className,
  render,
  children,
  ...props
}: StatusBadgeProps &
  VariantProps<typeof statusBadgeVariants> &
  useRender.ComponentProps<"span">) {
  const resolvedTone = (tone ?? (map ? statusTone(map, status) : undefined)) ?? "neutral";
  const resolvedLabel = label ?? (map ? statusText(map, status) : status) ?? "-";
  const visibleChildren = children ?? resolvedLabel;

  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        role: "status",
        className: cn(statusBadgeVariants({ tone: resolvedTone }), className),
        children: visibleChildren,
      },
      props
    ),
    render,
    state: {
      slot: "status-badge",
      tone: resolvedTone,
      variant,
    },
  })
}

export { StatusBadge, statusBadgeVariants }