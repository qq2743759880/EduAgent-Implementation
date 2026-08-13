/**
 * ReactButtons — 帖子点赞 / 收藏软切换按钮（计数即时更新）
 *
 * 交互契约（后端 POST /posts/{id}/like|favorite 软切换）：
 *   响应 { active, total_count } 是唯一权威 → 每次 toggle 后以响应回填
 *   点赞数 / 收藏数，做到"即时更新"且与服务端最终一致。
 *
 * 计数回写按 target 定向（onCountsChange(target, next)）：
 *   like 成功后只回写 like 项、favorite 成功后只回写 favorite 项。
 *   回调不引用兄弟字段的本次 render 闭包值，杜绝"陈旧值整体覆盖"的极端时序问题
 *   （对抗评审轻微问题 4）。
 *
 * 写操作用 useMutation（设计指南 §5.2）：失败由 QueryClient 全局 onError toast，
 * 不会出现 unhandled rejection / 静默吞错（R-7 治理）。
 */
"use client";

import { useMutation } from "@tanstack/react-query";
import { Bookmark, Heart, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
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
  /** 紧凑模式（列表卡片可复用），默认 false */
  compact?: boolean;
}

export function ReactButtons({
  postId,
  likeActive,
  likeCount,
  favoriteActive,
  favoriteCount,
  onCountsChange,
  compact = false,
}: ReactButtonsProps) {
  const likeMutation = useMutation({
    mutationFn: () => togglePostLike(postId),
    onSuccess: (resp) =>
      onCountsChange?.("like", { active: resp.active, count: resp.total_count }),
  });

  const favMutation = useMutation({
    mutationFn: () => togglePostFavorite(postId),
    onSuccess: (resp) =>
      onCountsChange?.("favorite", { active: resp.active, count: resp.total_count }),
  });

  const busy = likeMutation.isPending || favMutation.isPending;

  return (
    <div className={cn("inline-flex items-center gap-2", compact && "gap-1.5")}>
      <Button
        type="button"
        variant={likeActive ? "default" : "outline"}
        size={compact ? "sm" : "default"}
        onClick={() => likeMutation.mutate()}
        disabled={busy}
        aria-pressed={likeActive}
        className={cn(
          "gap-1.5",
          // fe-task07：点赞/收藏激活双色 → 主色（区分靠 Heart vs Bookmark 图标 + fill-current + aria-pressed）
          likeActive && "bg-primary text-primary-foreground hover:bg-primary-strong border-primary",
        )}
      >
        {likeMutation.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Heart className={cn("h-4 w-4", likeActive && "fill-current")} />
        )}
        <span className="tabular-nums">{likeCount}</span>
        <span className="sr-only sm:not-sr-only">{likeActive ? "已赞" : "点赞"}</span>
      </Button>

      <Button
        type="button"
        variant={favoriteActive ? "default" : "outline"}
        size={compact ? "sm" : "default"}
        onClick={() => favMutation.mutate()}
        disabled={busy}
        aria-pressed={favoriteActive}
        className={cn(
          "gap-1.5",
          favoriteActive && "bg-primary text-primary-foreground hover:bg-primary-strong border-primary",
        )}
      >
        {favMutation.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Bookmark className={cn("h-4 w-4", favoriteActive && "fill-current")} />
        )}
        <span className="tabular-nums">{favoriteCount}</span>
        <span className="sr-only sm:not-sr-only">{favoriteActive ? "已收藏" : "收藏"}</span>
      </Button>
    </div>
  );
}
