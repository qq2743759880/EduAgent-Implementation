/**
 * ReactButtons — 帖子点赞 / 收藏软切换按钮（candy-playful frozen，task52 对齐 approved community-post.html）
 * - 点赞：激活糖果绿底白字 / 收藏：激活糖果黄底墨字；未激活白底墨描边；3D 实底阴影
 * - 交互契约（后端 POST /posts/{id}/like|favorite 软切换）：
 *   响应 { active, total_count } 是唯一权威 → 每次 toggle 后以响应回填计数，即时更新且与服务端一致
 * - 计数回写按 target 定向（onCountsChange(target, next)）：like 只回写 like、favorite 只回写 favorite，
 *   不引用兄弟字段闭包值，杜绝陈旧值整体覆盖（对抗评审轻微问题 4）
 * - points_awarded > 0 时回调 onPointsAwarded（父组件 toast「+N 积分」）
 * - 写操作用 useMutation（R-7）：失败由 QueryClient 全局 onError toast，不静默吞错
 */
"use client";

import { useMutation } from "@tanstack/react-query";
import { Bookmark, Heart, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { togglePostFavorite, togglePostLike } from "@/lib/api/community";

export type ReactCountTarget = "like" | "favorite";

export interface ReactTargetState {
  active: boolean;
  count: number;
}

export interface ReactButtonsProps {
  postId: number;
  /** 初始点赞状态/计数（来自列表或详情接口） */
  likeActive: boolean;
  likeCount: number;
  favoriteActive: boolean;
  favoriteCount: number;
  /** 父组件同步回调：按 target 定向回写（只回写被操作项的计数） */
  onCountsChange?: (target: ReactCountTarget, next: ReactTargetState) => void;
  /** 后端返回 points_awarded > 0 时回调（父组件 toast「+N 积分」） */
  onPointsAwarded?: (points: number) => void;
  /** 紧凑模式（列表卡片可复用），默认 false */
  compact?: boolean;
  /** 锁定帖禁用（操作行隐藏由父组件控制，此处置灰兜底） */
  disabled?: boolean;
}

const INK_3D = "shadow-[0_4px_0_color-mix(in_oklch,var(--foreground),transparent_82%)]";

export function ReactButtons({
  postId,
  likeActive,
  likeCount,
  favoriteActive,
  favoriteCount,
  onCountsChange,
  onPointsAwarded,
  compact = false,
  disabled = false,
}: ReactButtonsProps) {
  const likeMutation = useMutation({
    mutationFn: () => togglePostLike(postId),
    onSuccess: (resp) => {
      onCountsChange?.("like", { active: resp.active, count: resp.total_count });
      if (resp.points_awarded > 0) onPointsAwarded?.(resp.points_awarded);
    },
  });

  const favMutation = useMutation({
    mutationFn: () => togglePostFavorite(postId),
    onSuccess: (resp) => {
      onCountsChange?.("favorite", { active: resp.active, count: resp.total_count });
      if (resp.points_awarded > 0) onPointsAwarded?.(resp.points_awarded);
    },
  });

  const busy = likeMutation.isPending || favMutation.isPending;

  const baseBtn =
    "inline-flex items-center gap-1.5 rounded-xl border-[3px] border-foreground font-extrabold transition-transform enabled:hover:-translate-y-0.5 enabled:active:translate-y-px enabled:active:shadow-none disabled:cursor-not-allowed disabled:opacity-50";
  const idleBtn = cn("bg-white text-foreground", INK_3D);

  return (
    <div className={cn("inline-flex items-center gap-2", compact && "gap-1.5")}>
      <button
        type="button"
        onClick={() => likeMutation.mutate()}
        disabled={busy || disabled}
        aria-pressed={likeActive}
        className={cn(
          baseBtn,
          likeActive
            ? "bg-candy-green text-white shadow-[0_4px_0_color-mix(in_oklch,var(--candy-green),black_30%)]"
            : idleBtn,
          compact ? "px-2.5 py-1 text-xs" : "px-4 py-2 text-sm",
        )}
      >
        {likeMutation.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Heart className={cn("h-4 w-4", likeActive && "fill-current")} aria-hidden="true" />
        )}
        <span className="tabular-nums">{likeCount}</span>
        <span className="sr-only">{likeActive ? "已赞" : "点赞"}</span>
      </button>

      <button
        type="button"
        onClick={() => favMutation.mutate()}
        disabled={busy || disabled}
        aria-pressed={favoriteActive}
        className={cn(
          baseBtn,
          favoriteActive
            ? "bg-candy-yellow text-foreground shadow-[0_4px_0_color-mix(in_oklch,var(--candy-yellow),black_30%)]"
            : idleBtn,
          compact ? "px-2.5 py-1 text-xs" : "px-4 py-2 text-sm",
        )}
      >
        {favMutation.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <Bookmark className={cn("h-4 w-4", favoriteActive && "fill-current")} aria-hidden="true" />
        )}
        <span className="tabular-nums">{favoriteCount}</span>
        <span className="sr-only">{favoriteActive ? "已收藏" : "收藏"}</span>
      </button>
    </div>
  );
}
