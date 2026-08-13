/**
 * PostCard — 社区帖子卡片（列表页单条）
 * 纯展示组件：title → 详情页链接，counts 来自后端聚合（点赞/回帖/收藏/浏览），
 * 点赞/收藏交互由详情页 ReactButtons 负责，列表页不重复发起写请求。
 */
"use client";

import Link from "next/link";
import { Bookmark, Eye, Heart, MessageCircle, Pin } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { PostSummary } from "@/lib/api/community";
import { BOARD_META, formatDateTime, stripMarkdown } from "@/lib/community-meta";

export interface PostCardProps {
  post: PostSummary;
  /** 是否高亮显示"我的帖子"（当前用户发帖） */
  isMine?: boolean;
}

export function PostCard({ post, isMine = false }: PostCardProps) {
  const board = BOARD_META[post.board_code] ?? BOARD_META.general;

  return (
    <article
      className={cn(
        "group rounded-xl border border-border bg-card p-4 transition-all hover:border-primary-border hover:shadow-card md:p-5",
        post.is_pinned && "border-warning/40 bg-warning/10",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className={cn("text-3xs font-medium", board.colorClass)}>
          {board.label}
        </Badge>
        {post.is_pinned && (
          <Badge variant="secondary" className="gap-1 text-3xs bg-warning/10 text-warning-foreground border border-warning/40">
            <Pin className="h-3 w-3" /> 置顶
          </Badge>
        )}
        {isMine && (
          <Badge variant="outline" className="text-3xs text-primary">
            我的帖子
          </Badge>
        )}
        {post.is_locked && (
          <Badge variant="outline" className="text-3xs text-muted-foreground">
            已锁定
          </Badge>
        )}
      </div>

      <Link
        href={`/community/${post.post_id}`}
        className="mt-2 block text-base font-semibold leading-snug text-foreground transition-colors group-hover:text-primary md:text-lg"
      >
        {post.title}
      </Link>

      {post.summary && (
        <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
          {stripMarkdown(post.summary)}
        </p>
      )}

      {post.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {post.tags.slice(0, 5).map((t) => (
            <span
              key={t}
              className="rounded-md bg-muted px-1.5 py-0.5 text-3xs text-muted-foreground"
            >
              #{t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
        <span className="font-medium text-secondary-foreground">{post.author_name ?? "匿名学员"}</span>
        <span>{formatDateTime(post.created_at)}</span>
        <span className="ml-auto inline-flex items-center gap-3">
          <span className="inline-flex items-center gap-1 tabular-nums">
            <Eye className="h-3.5 w-3.5" />
            <span className="sr-only">浏览</span>
            {post.view_count}
          </span>
          <span className="inline-flex items-center gap-1 tabular-nums">
            <Heart className="h-3.5 w-3.5" />
            <span className="sr-only">点赞</span>
            {post.like_count}
          </span>
          <span className="inline-flex items-center gap-1 tabular-nums">
            <MessageCircle className="h-3.5 w-3.5" />
            <span className="sr-only">回帖</span>
            {post.comment_count}
          </span>
          <span className="inline-flex items-center gap-1 tabular-nums">
            <Bookmark className="h-3.5 w-3.5" />
            <span className="sr-only">收藏</span>
            {post.favorite_count}
          </span>
        </span>
      </div>
    </article>
  );
}
