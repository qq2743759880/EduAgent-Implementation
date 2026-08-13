/**
 * 社区首页（/community）
 *  - 热门帖列表（GET /api/community/posts?sort&board_code&page，真实 API 无 MOCK）
 *  - 4 学科分版 Tab（english/math/programming/general）+ 排序（热门/最新/点赞）
 *  - 发帖：PostEditor（Markdown，发帖成功 +5 分 → 跳详情）
 */
"use client";

import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MessagesSquare, PenLine, RefreshCw, SearchX } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ProtectedRoute } from "@/lib/protected-route";
import { BoardTabs, boardTabId, BOARD_PANEL_ID } from "@/components/community/BoardTabs";
import { PostCard } from "@/components/community/PostCard";
import { PostEditor } from "@/components/community/PostEditor";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { listPosts, type BoardCode, type PostSort } from "@/lib/api/community";

const PAGE_SIZE = 10;

function CommunityPageInner() {
  const [board, setBoard] = useState<BoardCode | "">("");
  const [sort, setSort] = useState<PostSort>("HOT");
  const [page, setPage] = useState(1);
  const [editorOpen, setEditorOpen] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["community", "posts", { board, sort, page }] as const,
    async queryFn() {
      return listPosts({ sort, board_code: board, page, page_size: PAGE_SIZE });
    },
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

  const items = data?.items ?? [];
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));

  const onBoardChange = useCallback((next: BoardCode | "") => {
    setBoard(next);
    setPage(1);
  }, []);

  const onSortChange = useCallback((next: PostSort) => {
    setSort(next);
    setPage(1);
  }, []);

  return (
    <div className="min-h-screen bg-background">
      {/* 页头（fe-task07：三色渐变 → 品牌渐变） */}
      <header className="relative overflow-hidden bg-gradient-to-r from-primary-deep to-primary-strong text-primary-foreground">
        <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:radial-gradient(ellipse_at_top_left,rgba(255,255,255,0.6),transparent_55%)]" />
        <div className="mx-auto w-full max-w-5xl px-4 py-10 md:px-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/30 bg-white/10 px-3 py-1 text-xs backdrop-blur-sm">
            <MessagesSquare className="h-3.5 w-3.5" />
            学员社区 · 发帖 +5 分 · 回帖 +2 分
          </div>
          <h1 className="mt-3 text-2xl font-bold md:text-3xl">学习社区</h1>
          <p className="mt-2 max-w-2xl text-sm text-white/85">
            分享学习心得、提问答疑、收藏好帖，让每一次交流都被记录。
          </p>
          <div className="mt-5">
            <Button
              size="lg"
              className="bg-white font-semibold text-primary hover:bg-white/90"
              onClick={() => setEditorOpen((v) => !v)}
            >
              <PenLine className="mr-1.5 h-4 w-4" />
              {editorOpen ? "收起编辑器" : "发布帖子"}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl space-y-4 px-4 py-6 md:px-6">
        {editorOpen && (
          <PostEditor
            defaultBoard={board === "" ? "general" : board}
            onPosted={() => setEditorOpen(false)}
          />
        )}

        <BoardTabs value={board} onChange={onBoardChange} sort={sort} onSortChange={onSortChange} />

        {/* 分版 Tab 对应的内容面板（aria-controls/aria-labelledby 关联） */}
        <div
          id={BOARD_PANEL_ID}
          role="tabpanel"
          aria-labelledby={boardTabId(board)}
          className="space-y-4"
        >
          {/* 列表三态 */}
          {isLoading && !data ? (
            <PostListSkeleton />
          ) : isError ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : items.length === 0 ? (
            <EmptyState board={board} />
          ) : (
            <>
              <div className="space-y-3">
                {items.map((post) => (
                  <PostCard key={post.post_id} post={post} />
                ))}
              </div>
              {totalPages > 1 && (
                <PaginationBar page={page} total_pages={totalPages} onChange={setPage} />
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function PostListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-32 animate-pulse rounded-xl border border-border bg-muted/40" />
      ))}
    </div>
  );
}

function ErrorState({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const msg =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "帖子加载失败，请稍后重试";
  return (
    <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-8 text-center">
      <div className="text-base font-semibold text-destructive-foreground">加载失败</div>
      <p className="mt-1 text-sm text-destructive-foreground/90">{msg}</p>
      <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
        <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> 点击重试
      </Button>
    </div>
  );
}

function EmptyState({ board }: { board: BoardCode | "" }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-10 text-center">
      <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-xl bg-primary/10 text-primary">
        <SearchX className="h-6 w-6" />
      </div>
      <div className="text-base font-semibold text-foreground">这个版块还没有帖子</div>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
        {board === "" ? "当前没有帖子，来发布第一篇吧～" : "点击右上角「发布帖子」分享你的第一个话题吧～"}
      </p>
    </div>
  );
}

export default function CommunityPage() {
  return (
    <ProtectedRoute>
      <CommunityPageInner />
    </ProtectedRoute>
  );
}
