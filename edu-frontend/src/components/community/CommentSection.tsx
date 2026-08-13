/**
 * CommentSection — 帖子评论列表 + 回帖表单
 *
 * 契约：
 *   GET  /posts/{id}/comments?page&page_size → { total, page, page_size, items }
 *     （page 1-based；>20 条可点「加载更多」按页追加，对齐后端分页契约）
 *   POST /posts/{id}/comments { content_md, parent_id?, reply_to_id? } → { comment_id, points: 2 }
 *   POST /comments/{id}/like → { active, total_count }（评论点赞软切换）
 *
 * 回帖成功 toast +2 积分；计数即时更新（父组件传入 onCommentCountChange 写回详情计数）。
 */
"use client";

import { memo, useCallback, useMemo, useState } from "react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Loader2, MessageCircle, Send, ThumbsUp } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/community-meta";
import {
  createComment,
  listComments,
  toggleCommentLike,
  type CommentItem,
} from "@/lib/api/community";
import { MarkdownView } from "./MarkdownView";

const PAGE_SIZE = 20;

export interface CommentSectionProps {
  postId: number;
  /** 父组件在回帖成功后把详情页 comment_count +1 */
  onCommentCountChange?: (delta: number) => void;
}

export function CommentSection({ postId, onCommentCountChange }: CommentSectionProps) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<CommentItem | null>(null);

  /** 分页加载：初始第 1 页，getNextPageParam 由后端 total/page/page_size 推导下一页 */
  const commentsQ = useInfiniteQuery({
    queryKey: ["community", "comments", postId] as const,
    queryFn: ({ pageParam }) => listComments(postId, pageParam, PAGE_SIZE),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.page * lastPage.page_size < lastPage.total ? lastPage.page + 1 : undefined,
    staleTime: 30_000,
  });

  /** 引用稳定化：仅当查询数据变化时变更，供 handleReply 的 useCallback 依赖 */
  const comments = useMemo(
    () => commentsQ.data?.pages.flatMap((p) => p.items) ?? [],
    [commentsQ.data],
  );

  const createMutation = useMutation({
    mutationFn: () =>
      createComment(postId, {
        content_md: draft.trim(),
        parent_id: replyTo ? replyTo.comment_id : null,
        reply_to_id: replyTo ? replyTo.comment_id : null,
      }),
    onSuccess: (resp) => {
      toast.success("回帖成功", {
        description: resp.points > 0 ? `获得 +${resp.points} 积分` : undefined,
      });
      setDraft("");
      setReplyTo(null);
      onCommentCountChange?.(1);
      void queryClient.invalidateQueries({ queryKey: ["community", "comments", postId] });
      void queryClient.invalidateQueries({ queryKey: ["gamification", "points"] });
    },
  });

  const submitDisabled = draft.trim().length < 1;

  const handleSubmit = () => {
    if (submitDisabled || createMutation.isPending) return;
    createMutation.mutate();
  };

  /** 稳定回调：点击「回复」时只传 comment_id，CommentRow 可被 memo 跳过重渲染 */
  const handleReply = useCallback(
    (commentId: number) => {
      setReplyTo(comments.find((c) => c.comment_id === commentId) ?? null);
    },
    [comments],
  );

  const { total } = commentsQ.data?.pages[0] ?? { total: 0 };

  return (
    <div className="space-y-4">
      {/* 回帖表单 */}
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <MessageCircle className="h-4 w-4 text-primary" />
          参与讨论
          {replyTo && (
            <button
              type="button"
              className="ml-1 inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs font-normal text-secondary-foreground hover:bg-muted/80"
              onClick={() => setReplyTo(null)}
            >
              回复 @{replyTo.author_name ?? "匿名"} <span className="text-secondary-foreground">×</span>
            </button>
          )}
        </div>
        <Label htmlFor="reply-content" className="sr-only">
          回帖内容
        </Label>
        <Textarea
          id="reply-content"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={replyTo ? `回复 @${replyTo.author_name ?? "匿名"}…` : "写下你的看法…（支持 Markdown）"}
          rows={3}
          maxLength={5000}
        />
        <div className="mt-2 flex items-center justify-between">
          {/* fe-task07：回帖奖励 emerald 状态保留 → text-success-foreground（小字 4.5:1） */}
          <span className="text-xs text-success-foreground">回帖奖励 +2 积分</span>
          <Button
            type="button"
            size="sm"
            onClick={handleSubmit}
            disabled={submitDisabled || createMutation.isPending}
          >
            {createMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            发表回帖
          </Button>
        </div>
      </div>

      {/* 评论列表 */}
      <div className="space-y-3">
        <div className="text-sm text-muted-foreground">
          共 {total} 条回帖{commentsQ.isLoading ? "（加载中…）" : ""}
        </div>

        {commentsQ.isLoading ? (
          <CommentSkeleton />
        ) : commentsQ.isError ? (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive-foreground">
            回帖加载失败，请稍后重试。
          </div>
        ) : comments.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            还没有回帖，来抢沙发吧～
          </div>
        ) : (
          <>
            {comments.map((c) => (
              <CommentRow key={c.comment_id} comment={c} onReply={handleReply} />
            ))}
            {commentsQ.hasNextPage && (
              <div className="flex justify-center pt-1">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void commentsQ.fetchNextPage()}
                  disabled={commentsQ.isFetchingNextPage}
                  aria-busy={commentsQ.isFetchingNextPage}
                >
                  {commentsQ.isFetchingNextPage ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5" />
                  )}
                  加载更多（{comments.length}/{total}）
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

const CommentRow = memo(function CommentRow({
  comment,
  onReply,
}: {
  comment: CommentItem;
  onReply: (commentId: number) => void;
}) {
  const [liked, setLiked] = useState(comment.mine_liked);
  const [likeCount, setLikeCount] = useState(comment.like_count);
  const [likeBusy, setLikeBusy] = useState(false);

  const handleLikeClick = async () => {
    if (likeBusy) return;
    setLikeBusy(true);
    try {
      const resp = await toggleCommentLike(comment.comment_id);
      setLiked(resp.active);
      setLikeCount(resp.total_count);
    } catch (err) {
      /* 直接调用不走 QueryClient 全局 onError，这里显式 toast + console.error（R-7 不吞错） */
      const msg = err instanceof Error ? err.message : "点赞失败，请稍后重试";
      toast.error(msg);
      console.error("[CommentSection] comment like failed:", err);
    } finally {
      setLikeBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span className="font-medium text-secondary-foreground">
          {comment.author_name ?? "匿名学员"}
        </span>
        {comment.parent_id != null && (
          <span className="rounded bg-muted px-1.5 py-0.5 text-3xs">回复</span>
        )}
        <span>{formatRelativeTime(comment.created_at)}</span>
      </div>

      <div className="mt-2">
        <MarkdownView content={comment.content_md} />
      </div>

      <div className="mt-2 flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-destructive"
          onClick={handleLikeClick}
          disabled={likeBusy}
          aria-pressed={liked}
        >
          {likeBusy ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ThumbsUp className={cn("h-3.5 w-3.5", liked && "fill-current text-destructive")} />
          )}
          <span className="tabular-nums">{likeCount}</span>
          {liked ? "已赞" : "点赞"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs text-muted-foreground hover:text-primary"
          onClick={() => onReply(comment.comment_id)}
        >
          回复
        </Button>
      </div>
    </div>
  );
});

function CommentSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-20 animate-pulse rounded-xl border border-border bg-muted/40" />
      ))}
    </div>
  );
}
