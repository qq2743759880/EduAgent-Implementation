/**
 * FavoriteButton — 课程详情页「收藏」心形按钮（task46，对齐 P8 + HTML 效果图）。
 * 受控组件：favorited 由父级维护；aria-pressed 双通道（状态不依赖颜色传达）。
 * 登录校验由父级（页面）处理：未登录跳 /login?redirect=。
 */
"use client";

import { Heart } from "lucide-react";
import { cn } from "@/lib/utils";

export function FavoriteButton({
  favorited,
  onToggle,
  disabled = false,
  seriesName,
}: {
  favorited: boolean;
  onToggle: () => void;
  disabled?: boolean;
  seriesName: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      aria-pressed={favorited}
      aria-label={favorited ? `取消收藏 ${seriesName}` : `收藏 ${seriesName}`}
      className={cn(
        "inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border-2 border-border bg-card shadow-[0_3px_0_rgba(31,31,31,0.14)] transition-all",
        "hover:-translate-y-0.5 hover:border-candy-red/50 active:translate-y-0 active:shadow-none",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-candy-blue",
        "disabled:cursor-not-allowed disabled:opacity-50",
      )}
    >
      <Heart
        aria-hidden="true"
        className={cn(
          "h-5 w-5 transition-colors",
          favorited ? "fill-candy-red text-candy-red" : "text-muted-foreground",
        )}
      />
    </button>
  );
}
