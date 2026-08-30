/**
 * 帖子详情（/community/[postId]，task52）· candy-playful frozen（对齐 approved community-post.html）
 * - 详情头（返回/版块/置顶锁定/标题/作者行）+ 操作行（点赞/收藏 react + 积分 toast）
 * - 正文 MarkdownView 渲染 + 评论区（分页 C2 + 回帖 + 评论点赞）
 * - 锁定帖：操作行隐藏 + 锁定 banner + 评论区禁用
 * - 帖子不存在 → ErrorState + 「← 返回列表」CTA（GWT③）
 * 数据契约⑬：GET /api/community/posts/{id}（浏览 +1）；GET/POST .../comments；POST .../like|favorite
 */
"use client";

import { use, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Eye, Lock } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { ProtectedRoute } from "@/lib/protected-route";
import { ReactButtons } from "@/components/community/ReactButtons";
import { CommentSection } from "@/components/community/CommentSection";
import { MarkdownView } from "@/components/community/MarkdownView";
import { ApiError } from "@/lib/api-client";
import { getBoardMeta, formatDateTime } from "@/lib/community-meta";
import { getPostDetail } from "@/lib/api/community";

const INK_3D = "shadow-[0_5px_0_color-mix(in_oklch,var(--foreground),transparent_82%)]";

export default function PostDetailPage({ params }: { params: Promise<{ postId: string }> }) {
  const resolved = use(params);
  const postId = Number(resolved.postId);
  const validId = Number.isFinite(postId) && postId > 0;

  return (
    <ProtectedRoute>
      {validId ? (
        <PostDetailInner key={postId} postId={postId} />
      ) : (
        <NotFoundCard message="帖子 ID 不合法" />
      )}
    </ProtectedRoute>
  );
}

/** 导出供单测直接渲染（跳过 ProtectedRoute，对齐列表页 CommunityPageInner 模式） */
export { PostDetailInner };

function PostDetailInner({ postId }: { postId: number }) {
  const router = useRouter();
  const detailQ = useQuery({
    queryKey: ["community", "post", postId] as const,
    queryFn: () => getPostDetail(postId),
    enabled: postId > 0,
    staleTime: 30_000,
  });

  const detail = detailQ.data;

  // 点赞/收藏本地态：以用户操作为准，未操作时用详情接口初始值
  const [likeOverride, setLikeOverride] = useState<{ active: boolean; count: number } | null>(null);
  const [favOverride, setFavOverride] = useState<{ active: boolean; count: number } | null>(null);
  const [commentDelta, setCommentDelta] = useState(0);

  const likeActive = likeOverride?.active ?? detail?.mine_react_like ?? false;
  const likeCount = likeOverride?.count ?? detail?.like_count ?? 0;
  const favActive = favOverride?.active ?? detail?.mine_react_favorite ?? false;
  const favCount = favOverride?.count ?? detail?.favorite_count ?? 0;
  const commentCount = (detail?.comment_count ?? 0) + commentDelta;

  const board = getBoardMeta(detail?.board_code);
  const locked = detail?.is_locked ?? false;

  if (detailQ.isLoading && !detail) return <DetailSkeleton />;
  if (detailQ.isError && !detail) {
    return (
      <NotFoundCard
        message={postDetailErrorMessage(detailQ.error)}
        action={
          <button
            type="button"
            onClick={() => router.push("/community")}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-xl border-[3px] border-foreground bg-candy-purple px-4 py-2 text-sm font-extrabold text-white",
              INK_3D,
            )}
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" /> 返回列表
          </button>
        }
      />
    );
  }
  if (!detail) return null;

  return (
    <div className="min-h-screen bg-candy-bg pb-16">
      <main className="mx-auto flex w-full max-w-4xl flex-col gap-3 px-3 py-4 md:px-5">
        {/* 返回列表 */}
        <button
          type="button"
          onClick={() => router.back()}
          className={cn(
            "inline-flex w-fit items-center gap-1.5 rounded-full border-2 border-foreground bg-white px-3.5 py-1.5 text-xs font-extrabold text-foreground transition-transform hover:-translate-y-0.5 active:translate-y-px active:shadow-none",
            INK_3D,
          )}
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> 返回列表
        </button>

        {/* 详情头 */}
        <header
          className={cn(
            "flex flex-col gap-3 rounded-3xl border-[3px] border-foreground bg-white p-5",
            INK_3D,
          )}
        >
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "rounded-full border-2 border-foreground px-2.5 py-0.5 text-3xs font-extrabold",
                board.colorClass,
              )}
            >
              {board.label}
            </span>
            {detail.is_pinned && (
              <span className="inline-flex items-center gap-1 rounded-md border-2 border-foreground bg-candy-yellow px-2 py-0.5 text-3xs font-extrabold text-foreground">
                📌 置顶
              </span>
            )}
            {locked && (
              <span className="inline-flex items-center gap-1 rounded-md border-2 border-foreground/20 px-2 py-0.5 text-3xs font-extrabold text-muted-foreground">
                <Lock className="h-3 w-3" aria-hidden="true" /> 锁定
              </span>
            )}
            {detail.tags.map((t) => (
              <span
                key={t}
                className="rounded-full border border-candy-purple/25 bg-candy-purple-soft px-2.5 py-0.5 text-3xs font-bold text-candy-purple"
              >
                #{t}
              </span>
            ))}
          </div>

          <h1 className="text-2xl font-extrabold leading-tight tracking-tight text-foreground md:text-3xl">
            {detail.title}
          </h1>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-2xs text-muted-foreground">
            <span className="font-extrabold text-foreground">
              {detail.author_name ?? "匿名学员"}
            </span>
            <span aria-hidden="true" className="text-foreground/30">·</span>
            <span>{formatDateTime(detail.created_at)}</span>
            <span aria-hidden="true" className="text-foreground/30">·</span>
            <span className="inline-flex items-center gap-1">
              <Eye className="h-3.5 w-3.5" aria-hidden="true" /> {detail.view_count} 浏览
            </span>
            <span aria-hidden="true" className="text-foreground/30">·</span>
            <span>👍 {likeCount}</span>
            <span aria-hidden="true" className="text-foreground/30">·</span>
            <span>⭐ {favCount}</span>
            <span aria-hidden="true" className="text-foreground/30">·</span>
            <span>💬 {commentCount}</span>
          </div>

          {/* 操作行：锁定帖隐藏点赞/收藏，显示锁定提示 */}
          {locked ? (
            <div className="flex items-center gap-2 rounded-xl border-2 border-candy-orange/30 bg-candy-orange-soft px-3 py-2 text-xs font-bold text-muted-foreground">
              🔒 本帖已锁定，仅管理员可回复。
            </div>
          ) : (
            <div className="border-t-2 border-dashed border-foreground/15 pt-3">
              <ReactButtons
                postId={postId}
                likeActive={likeActive}
                likeCount={likeCount}
                favoriteActive={favActive}
                favoriteCount={favCount}
                onCountsChange={(target, next) => {
                  if (target === "like") {
                    setLikeOverride({ active: next.active, count: next.count });
                  } else {
                    setFavOverride({ active: next.active, count: next.count });
                  }
                }}
                onPointsAwarded={(points) => {
                  toast.success(`🎉 +${points} 积分`);
                }}
              />
            </div>
          )}
        </header>

        {/* Markdown 正文 */}
        <section
          className={cn(
            "rounded-3xl border-[3px] border-foreground bg-white p-5 md:p-6",
            INK_3D,
          )}
        >
          <MarkdownView content={detail.content_md} />
        </section>

        {/* 评论区 */}
        <section className="mt-1">
          <CommentSection
            postId={postId}
            locked={locked}
            onCommentCountChange={(d) => setCommentDelta((v) => v + d)}
          />
        </section>
      </main>
    </div>
  );
}

/**
 * 详情加载失败文案（对抗 fe-task01 #11）：403「无权限」与 404「不存在」语义区分，
 * 其余错误透传后端 message。
 */
function postDetailErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 403) return "你没有权限查看该帖子";
    if (err.status === 404) return "帖子不存在或已被删除";
    return err.message;
  }
  return err instanceof Error ? err.message : "帖子不存在或已被删除";
}

function DetailSkeleton() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-4 px-3 py-4 md:px-5">
      <div className="h-64 animate-pulse rounded-3xl border-[3px] border-foreground/15 bg-white" />
      <div className="h-64 animate-pulse rounded-3xl border-[3px] border-foreground/15 bg-white" />
    </div>
  );
}

function NotFoundCard({ message, action }: { message: string; action?: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-[60vh] w-full max-w-4xl flex-col items-center justify-center gap-4 px-4 text-center">
      <div
        role="alert"
        className={cn(
          "flex w-full max-w-md flex-col items-center gap-3 rounded-3xl border-[3px] border-foreground bg-white p-10 text-center",
          INK_3D,
        )}
      >
        <span aria-hidden="true" className="text-5xl">🔍</span>
        <h2 className="text-lg font-extrabold text-foreground">帖子不存在</h2>
        <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">{message}</p>
        {action ?? (
          <Link
            href="/community"
            className={cn(
              "mt-1 inline-flex items-center gap-1.5 rounded-xl border-[3px] border-foreground bg-candy-purple px-4 py-2 text-sm font-extrabold text-white",
              INK_3D,
            )}
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" /> 返回列表
          </Link>
        )}
      </div>
    </div>
  );
}
