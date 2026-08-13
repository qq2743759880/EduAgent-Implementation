/**
 * 帖子详情（/community/[postId]）
 *  - GET /api/community/posts/{id}（浏览量自动 +1）
 *  - 点赞/收藏软切换（ReactButtons，计数即时更新）
 *  - Markdown 正文渲染 + 回帖列表（回帖 +2 分）
 */
"use client";

import { use, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Eye, Loader2, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ProtectedRoute } from "@/lib/protected-route";
import { ReactButtons } from "@/components/community/ReactButtons";
import { CommentSection } from "@/components/community/CommentSection";
import { MarkdownView } from "@/components/community/MarkdownView";
import { ApiError } from "@/lib/api-client";
import { getBoardMeta, formatDateTime } from "@/lib/community-meta";
import { getPostDetail } from "@/lib/api/community";

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

function PostDetailInner({ postId }: { postId: number }) {
  const router = useRouter();
  const detailQ = useQuery({
    queryKey: ["community", "post", postId] as const,
    queryFn: () => getPostDetail(postId),
    enabled: postId > 0,
    staleTime: 30_000,
    retry: 1,
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

  if (detailQ.isLoading && !detail) return <DetailSkeleton />;
  if (detailQ.isError && !detail) {
    return (
      <NotFoundCard
        message={postDetailErrorMessage(detailQ.error)}
        action={
          <Button variant="outline" size="sm" onClick={() => router.push("/community")}>
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> 返回社区
          </Button>
        }
      />
    );
  }
  if (!detail) return null;

  return (
    <div className="min-h-screen bg-background pb-16">
      {/* 顶部工具条 */}
      <div className="sticky top-16 z-10 border-b border-border bg-card/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-4xl items-center gap-2 px-4 py-2.5 md:px-6">
          <Button variant="ghost" size="sm" className="h-7 px-2 text-muted-foreground" onClick={() => router.back()}>
            <ArrowLeft className="mr-1 h-3.5 w-3.5" /> 返回
          </Button>
          <Link href="/community" className="text-xs text-muted-foreground hover:text-foreground">
            社区首页
          </Link>
          <span className="text-xs text-muted-foreground">/</span>
          <span className="truncate text-xs text-secondary-foreground">{detail.title}</span>
        </div>
      </div>

      <article className="mx-auto w-full max-w-4xl px-4 pt-6 md:px-6">
        {/* 标题区 */}
        <header className="rounded-xl border border-border bg-card p-5 md:p-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={board.colorClass}>
              {board.label}
            </Badge>
            {detail.is_pinned && (
              <Badge variant="secondary" className="gap-1 bg-warning/10 text-warning-foreground border border-warning/40">
                置顶
              </Badge>
            )}
            {detail.tags.map((t) => (
              <span key={t} className="rounded-md bg-muted px-1.5 py-0.5 text-3xs text-muted-foreground">
                #{t}
              </span>
            ))}
          </div>

          <h1 className="mt-3 text-xl font-bold leading-snug text-foreground md:text-2xl">
            {detail.title}
          </h1>

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
            <span className="font-medium text-secondary-foreground">{detail.author_name ?? "匿名学员"}</span>
            <span>{formatDateTime(detail.created_at)}</span>
            <span className="inline-flex items-center gap-1">
              <Eye className="h-3.5 w-3.5" /> {detail.view_count} 浏览
            </span>
            <span>点赞 {likeCount}</span>
            <span>回帖 {commentCount}</span>
          </div>

          <div className="mt-4 border-t border-border pt-4">
            <ReactButtons
              postId={postId}
              likeActive={likeActive}
              likeCount={likeCount}
              favoriteActive={favActive}
              favoriteCount={favCount}
              onCountsChange={(target, next) => {
                // 定向回写：只更新被操作项的 override，不触碰兄弟字段（防陈旧值覆盖）
                if (target === "like") {
                  setLikeOverride({ active: next.active, count: next.count });
                } else {
                  setFavOverride({ active: next.active, count: next.count });
                }
              }}
            />
          </div>
        </header>

        {/* Markdown 正文 */}
        <section className="mt-4 rounded-xl border border-border bg-card p-5 md:p-7">
          <MarkdownView content={detail.content_md} />
        </section>

        {/* 评论 */}
        <section className="mt-6">
          <CommentSection postId={postId} onCommentCountChange={(d) => setCommentDelta((v) => v + d)} />
        </section>
      </article>
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
    <div className="mx-auto w-full max-w-4xl space-y-4 px-4 pt-6 md:px-6">
      <div className="h-64 animate-pulse rounded-xl border border-border bg-muted/40" />
      <div className="h-64 animate-pulse rounded-xl border border-border bg-muted/40" />
    </div>
  );
}

function NotFoundCard({ message, action }: { message: string; action?: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-[60vh] w-full max-w-4xl flex-col items-center justify-center gap-4 px-4 text-center">
      <div className="grid h-16 w-16 place-items-center rounded-xl bg-muted text-muted-foreground">
        <Loader2 className="h-7 w-7" />
      </div>
      <div className="text-base font-semibold text-foreground">{message}</div>
      {action ?? (
        <Button variant="outline" size="sm" asChild>
          <Link href="/community">
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> 返回社区
          </Link>
        </Button>
      )}
    </div>
  );
}
