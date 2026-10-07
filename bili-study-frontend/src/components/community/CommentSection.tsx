/**
 * CommentSection — 帖子评论区（candy-playful frozen，task52 对齐 approved community-post.html）
 * - 评论列表分页 C2（‹ 页码 › 共 N 条），对齐 P22 规范与 HTML 蓝本
 * - 回帖表单（Textarea 自动增高 + 糖果橙发布按钮）；锁定帖禁用输入 + 提示
 * - 评论点赞软切换（POST /comments/{id}/like）→ 响应回填计数；失败 toast + console.error（R-7 不吞错）
 * - 回帖成功 toast +2 积分 + invalidate 评论 queryKey + 父组件计数 +1
 * 契约：
 *   GET  /posts/{id}/comments?page&page_size → { total, page, page_size, items }
 *   POST /posts/{id}/comments { content_md, parent_id?, reply_to_id? } → { comment_id, points: 2 }
 *   POST /comments/{id}/like → { active, total_count }
 */
"use client";

import { memo, useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Loader2, Send, ThumbsUp } from "lucide-react";
import { toast } from "sonner";
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
const INK_3D = "shadow-[0_4px_0_color-mix(in_oklch,var(--foreground),transparent_82%)]";

export interface CommentSectionProps {
  postId: number;
  /** 父组件在回帖成功后把详情页 comment_count +1 */
  onCommentCountChange?: (delta: number) => void;
  /** 锁定帖：禁用评论输入 */
  locked?: boolean;
}

export function CommentSection({ postId, onCommentCountChange, locked = false }: CommentSectionProps) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [page, setPage] = useState(1);

  const commentsQ = useQuery({
    queryKey: ["community", "comments", postId, page] as const,
    queryFn: () => listComments(postId, page, PAGE_SIZE),
    staleTime: 30_000,
  });

  const comments = commentsQ.data?.items ?? [];
  const total = commentsQ.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const createMutation = useMutation({
    mutationFn: () => createComment(postId, { content_md: draft.trim() }),
    onSuccess: (resp) => {
      toast.success("回帖成功", {
        description: resp.points > 0 ? `获得 +${resp.points} 积分` : undefined,
      });
      setDraft("");
      setPage(1);
      onCommentCountChange?.(1);
      void queryClient.invalidateQueries({ queryKey: ["community", "comments", postId] });
      void queryClient.invalidateQueries({ queryKey: ["gamification", "points"] });
    },
  });

  const submitDisabled = draft.trim().length < 1 || locked;

  const handleSubmit = () => {
    if (submitDisabled || createMutation.isPending) return;
    createMutation.mutate();
  };

  const handlePageChange = useCallback((next: number) => {
    setPage(Math.max(1, next));
  }, []);

  return (
    <div className="flex flex-col gap-3">
      {/* 评论区标题 */}
      <div className="flex items-center gap-2">
        <span className="text-base font-extrabold tracking-tight text-foreground">
          💬 评论
        </span>
        <span className="inline-flex items-center rounded-full border-2 border-foreground bg-candy-yellow px-2 py-0.5 text-3xs font-extrabold text-foreground">
          {total} 条
        </span>
      </div>

      {/* 回帖表单（CommentComposer） */}
      <div className={cn("flex flex-col gap-2 rounded-3xl border-[3px] border-foreground bg-white p-3", INK_3D)}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={locked}
          rows={3}
          maxLength={5000}
          aria-label="评论内容"
          placeholder={locked ? "本帖已锁定，无法评论" : "写下你的看法…（Markdown 支持）"}
          className="min-h-16 w-full resize-none rounded-xl border-2 border-foreground bg-transparent px-3 py-2 text-sm leading-relaxed text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-candy-purple disabled:cursor-not-allowed disabled:bg-candy-bg disabled:text-muted-foreground"
        />
        <div className="flex items-center justify-end gap-2">
          <span className="text-3xs font-bold text-muted-foreground">发布 +2 积分</span>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitDisabled || createMutation.isPending}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-xl border-[3px] border-foreground bg-candy-orange px-4 py-2 text-sm font-extrabold text-white transition-transform enabled:hover:-translate-y-0.5 enabled:active:translate-y-px enabled:active:shadow-none disabled:cursor-not-allowed disabled:opacity-50",
              INK_3D,
            )}
          >
            {createMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="h-4 w-4" aria-hidden="true" />
            )}
            发布
          </button>
        </div>
      </div>

      {/* 评论列表四态 */}
      {commentsQ.isLoading ? (
        <CommentSkeleton />
      ) : commentsQ.isError ? (
        <div
          role="alert"
          className={cn("flex flex-col items-center gap-2 rounded-3xl border-[3px] border-foreground bg-white p-8 text-center", INK_3D)}
        >
          <span aria-hidden="true" className="text-4xl">😵</span>
          <p className="text-sm font-extrabold text-foreground">回帖加载失败</p>
          <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">
            网络开小差了，请稍后重试。
          </p>
          <button
            type="button"
            onClick={() => void commentsQ.refetch()}
            className={cn(
              "mt-1 inline-flex items-center gap-1.5 rounded-xl border-[3px] border-foreground bg-candy-red px-4 py-1.5 text-xs font-extrabold text-white",
              INK_3D,
            )}
          >
            🔄 重试
          </button>
        </div>
      ) : comments.length === 0 ? (
        <div
          role="status"
          className={cn("flex flex-col items-center gap-2 rounded-3xl border-[3px] border-foreground bg-white p-10 text-center", INK_3D)}
        >
          <span aria-hidden="true" className="text-4xl">
            {locked ? "🔒" : "🛋️"}
          </span>
          <p className="text-sm font-extrabold text-foreground">
            {locked ? "暂无评论" : "暂无评论，来抢沙发吧～"}
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2.5">
          {comments.map((c) => (
            <CommentRow key={c.comment_id} comment={c} />
          ))}
          {totalPages > 1 && (
            <CommentPager page={page} totalPages={totalPages} total={total} onChange={handlePageChange} />
          )}
        </div>
      )}
    </div>
  );
}

const CommentRow = memo(function CommentRow({ comment }: { comment: CommentItem }) {
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
      const msg = err instanceof Error ? err.message : "点赞失败，请稍后重试";
      toast.error(msg);
      console.error("[CommentSection] comment like failed:", err);
    } finally {
      setLikeBusy(false);
    }
  };

  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-2xl border-2 border-foreground bg-white p-3 shadow-[0_3px_0_color-mix(in_oklch,var(--foreground),transparent_82%)]",
        comment.parent_id != null && "ml-5 border-dashed",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-2xs text-muted-foreground">
        <span className="font-extrabold text-candy-purple">
          {comment.author_name ?? "匿名学员"}
        </span>
        {comment.parent_id != null && (
          <span className="rounded-md border border-foreground/20 bg-candy-purple-soft px-1.5 py-0.5 text-3xs font-bold text-candy-purple">
            回复
          </span>
        )}
        <span aria-hidden="true" className="text-foreground/30">·</span>
        <span>{formatRelativeTime(comment.created_at)}</span>
        <button
          type="button"
          onClick={() => void handleLikeClick()}
          disabled={likeBusy}
          aria-pressed={liked}
          aria-label={liked ? "取消点赞评论" : "点赞评论"}
          className={cn(
            "ml-auto inline-flex items-center gap-1 rounded-full border-2 border-foreground px-2.5 py-1 text-2xs font-extrabold text-foreground transition-transform enabled:hover:-translate-y-0.5 enabled:active:translate-y-px enabled:active:shadow-none disabled:cursor-not-allowed disabled:opacity-50",
            liked
              ? "bg-candy-green text-white shadow-[0_2px_0_color-mix(in_oklch,var(--candy-green),black_30%)]"
              : "bg-white shadow-[0_2px_0_color-mix(in_oklch,var(--foreground),transparent_82%)]",
          )}
        >
          {likeBusy ? (
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
          ) : (
            <ThumbsUp className={cn("h-3 w-3", liked && "fill-current")} aria-hidden="true" />
          )}
          <span className="tabular-nums">{likeCount}</span>
          <span className="sr-only">{liked ? "已赞" : "点赞"}</span>
        </button>
      </div>

      <div className="text-sm">
        <MarkdownView content={comment.content_md} />
      </div>
    </div>
  );
});

function CommentPager({
  page,
  totalPages,
  total,
  onChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const prevDisabled = page <= 1;
  const nextDisabled = page >= totalPages;
  const pageBtn =
    "grid min-w-9 h-9 place-items-center rounded-xl border-2 border-foreground bg-white px-2 text-sm font-extrabold text-foreground";

  return (
    <nav aria-label="评论分页" className="mt-1 flex items-center justify-center gap-2">
      <button
        type="button"
        aria-label="上一页"
        disabled={prevDisabled}
        onClick={() => onChange(page - 1)}
        className={cn(pageBtn, prevDisabled && "cursor-not-allowed opacity-40")}
      >
        <ChevronLeft className="h-4 w-4" aria-hidden="true" />
      </button>
      {Array.from({ length: Math.min(7, totalPages) }, (_, i) => {
        const windowStart = Math.max(1, Math.min(page - 3, totalPages - 6));
        const n = windowStart + i;
        if (n < 1) return null;
        return (
          <button
            key={n}
            type="button"
            aria-current={page === n ? "page" : undefined}
            onClick={() => onChange(n)}
            className={cn(
              pageBtn,
              page === n ? "bg-candy-green text-white" : "hover:border-candy-purple",
            )}
          >
            {n}
          </button>
        );
      })}
      <button
        type="button"
        aria-label="下一页"
        disabled={nextDisabled}
        onClick={() => onChange(page + 1)}
        className={cn(pageBtn, nextDisabled && "cursor-not-allowed opacity-40")}
      >
        <ChevronRight className="h-4 w-4" aria-hidden="true" />
      </button>
      <span className="ml-1 text-2xs font-bold text-muted-foreground">共 {total} 条</span>
    </nav>
  );
}

function CommentSkeleton() {
  return (
    <div role="status" aria-busy="true" className="space-y-2.5">
      <span className="sr-only">正在加载评论…</span>
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded-2xl border-[3px] border-foreground/15 bg-white" />
      ))}
    </div>
  );
}
