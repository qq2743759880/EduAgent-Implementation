/**
 * 社区列表页（/community，task51）· candy-playful frozen（对齐 approved community.html）
 * - Hero（糖果渐变 + 吉祥物 🐣）+ 版块 chips + 排序 + 关键词搜索（防抖）
 * + 🎒 我的帖子计数 + 发新帖（桌面 CTA / 移动 FAB）+ 帖子列表（C24 PostCard）+ 分页 + 四态
 * - 数据契约⑬：GET /api/community/posts?board_code&keyword&sort&page&page_size
 *   → data{total,page,page_size,items,mine_total_posts}；点击帖子 → /community/[postId]（J 表内联动）
 */
"use client";

import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, PenLine } from "lucide-react";
import { cn } from "@/lib/utils";
import { ProtectedRoute } from "@/lib/protected-route";
import { PostCard } from "@/components/community/PostCard";
import { CommunityFilterBar } from "@/components/community/CommunityFilterBar";
import { PostEditor } from "@/components/community/PostEditor";
import { listPosts, type BoardCode, type PostSort } from "@/lib/api/community";

const PAGE_SIZE = 10;
const INK_3D =
  "shadow-[0_5px_0_color-mix(in_oklch,var(--foreground),transparent_82%)]";

export function CommunityPageInner() {
  const [board, setBoard] = useState<BoardCode | "">("");
  const [sort, setSort] = useState<PostSort>("HOT");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [editorOpen, setEditorOpen] = useState(false);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["community", "posts", { board, sort, page, keyword }] as const,
    async queryFn() {
      return listPosts({ sort, board_code: board, keyword, page, page_size: PAGE_SIZE });
    },
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

  const items = data?.items ?? [];
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));
  const mineTotal = data?.mine_total_posts ?? 0;

  const onBoardChange = useCallback((next: BoardCode | "") => {
    setBoard(next);
    setPage(1);
  }, []);

  const onSortChange = useCallback((next: PostSort) => {
    setSort(next);
    setPage(1);
  }, []);

  const onSearch = useCallback((next: string) => {
    setKeyword(next);
    setPage(1);
  }, []);

  const openEditor = useCallback(() => setEditorOpen(true), []);

  return (
    <div className="min-h-screen bg-candy-bg">
      <main className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-3 py-4 md:px-5">
        {/* Hero */}
        <section
          aria-label="社区欢迎区"
          className="relative overflow-hidden rounded-[1.75rem] border-[3px] border-foreground/90 bg-gradient-to-br from-candy-orange-soft via-candy-orange-soft to-candy-purple-soft px-5 py-6 md:px-6 md:py-7"
        >
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -right-8 -top-8 h-36 w-36 rounded-full bg-[radial-gradient(circle,rgba(255,200,0,0.4),transparent_70%)]"
          />
          <div className="relative flex items-center gap-4">
            <div
              role="img"
              aria-label="吉祥物小鸡"
              className="flex-shrink-0 animate-[candy-float_3.4s_ease-in-out_infinite] text-5xl drop-shadow-[0_6px_0_rgba(31,31,31,0.12)] md:text-6xl"
            >
              🐣
            </div>
            <div className="min-w-0">
              <span className="inline-flex items-center gap-1 rounded-full border-2 border-foreground/90 bg-white px-2.5 py-0.5 text-3xs font-extrabold text-foreground">
                🧩 学中玩社区
              </span>
              <h1 className="mt-2 text-2xl font-extrabold leading-tight tracking-tight text-foreground md:text-3xl">
                一起讨论一起进步，找到同路人
              </h1>
              <p className="mt-1 max-w-md text-2xs text-muted-foreground md:text-sm">
                发帖提问 / 分享笔记 / 组队学习。每个真诚回复都值得被点赞。
              </p>
            </div>
          </div>
        </section>

        {/* 工具行：我的帖子计数 + 发新帖（桌面 CTA） */}
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border-2 border-candy-purple/35 bg-candy-purple-soft px-3 py-1 text-2xs font-extrabold text-foreground">
            我的帖子 <b className="text-candy-purple">{mineTotal}</b>
          </span>
          <button
            type="button"
            onClick={openEditor}
            className={cn(
              "ml-auto hidden items-center gap-1.5 rounded-xl border-[3px] border-foreground bg-candy-orange px-4 py-2 text-sm font-extrabold text-white transition-transform hover:-translate-y-0.5 md:inline-flex",
              INK_3D,
            )}
          >
            <PenLine className="h-4 w-4" aria-hidden="true" />
            发新帖
          </button>
        </div>

        {editorOpen && (
          <PostEditor defaultBoard={board === "" ? "general" : board} onPosted={() => setEditorOpen(false)} />
        )}

        {/* 筛选：版块 chips + 排序 + 搜索 */}
        <CommunityFilterBar
          board={board}
          onBoardChange={onBoardChange}
          sort={sort}
          onSortChange={onSortChange}
          onSearch={onSearch}
        />

        {/* 列表四态 */}
        {isLoading && !data ? (
          <PostListSkeleton />
        ) : isError ? (
          <PostErrorState onRetry={() => refetch()} />
        ) : items.length === 0 ? (
          <PostEmptyState onPost={openEditor} />
        ) : (
          <>
            <div className="space-y-3">
              {items.map((post) => (
                <PostCard key={post.post_id} post={post} />
              ))}
            </div>
            {totalPages > 1 && (
              <CandyPager
                page={page}
                totalPages={totalPages}
                total={data?.total ?? 0}
                onChange={setPage}
              />
            )}
          </>
        )}
      </main>

      {/* 移动端 FAB（发布） */}
      <button
        type="button"
        onClick={openEditor}
        className={cn(
          "fixed bottom-5 right-4 z-40 inline-flex items-center gap-1.5 rounded-full border-[3px] border-foreground bg-candy-orange px-5 py-3 text-base font-extrabold text-white md:hidden",
          INK_3D,
        )}
        aria-label="发新帖"
      >
        <PenLine className="h-5 w-5" aria-hidden="true" />
        发新帖
      </button>
    </div>
  );
}

function PostListSkeleton() {
  return (
    <div role="status" aria-busy="true" className="space-y-3">
      <span className="sr-only">正在加载帖子…</span>
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-28 animate-pulse rounded-3xl border-[3px] border-foreground/15 bg-white" />
      ))}
    </div>
  );
}

function PostErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className={cn("flex flex-col items-center gap-3 rounded-3xl border-[3px] border-foreground bg-white p-10 text-center", INK_3D)}>
      <span aria-hidden="true" className="text-5xl">
        😵
      </span>
      <h3 className="text-lg font-extrabold text-foreground">帖子加载失败</h3>
      <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
        网络开小差了，请稍后重试。若仍无法加载，可点击下方按钮刷新。
      </p>
      <button
        type="button"
        onClick={onRetry}
        className={cn(
          "mt-1 inline-flex items-center gap-1.5 rounded-xl border-[3px] border-foreground bg-candy-red px-4 py-2 text-sm font-extrabold text-white",
          INK_3D,
        )}
      >
        🔄 重试
      </button>
    </div>
  );
}

function PostEmptyState({ onPost }: { onPost: () => void }) {
  return (
    <div role="status" className={cn("flex flex-col items-center gap-3 rounded-3xl border-[3px] border-foreground bg-white p-12 text-center", INK_3D)}>
      <span aria-hidden="true" className="text-5xl">
        🏝️
      </span>
      <h3 className="text-lg font-extrabold text-foreground">暂无帖子</h3>
      <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
        这个版块还没有人发过帖，来当第一个分享的人吧～
      </p>
      <button
        type="button"
        onClick={onPost}
        className={cn(
          "mt-1 inline-flex items-center gap-1.5 rounded-xl border-[3px] border-foreground bg-candy-green px-4 py-2 text-sm font-extrabold text-white",
          INK_3D,
        )}
      >
        ＋ 发第一篇
      </button>
    </div>
  );
}

function CandyPager({
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
  const pageBtn = "grid min-w-9 h-9 place-items-center rounded-xl border-2 border-foreground bg-white px-2 text-sm font-extrabold text-foreground";

  return (
    <nav aria-label="分页" className="mt-1 flex w-full max-w-full items-center justify-center gap-2">
      <div className="flex min-w-0 max-w-full items-center justify-center gap-2 overflow-x-auto whitespace-nowrap p-0.5 pb-2 [scrollbar-width:thin]">
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
        // 仅展示当前附近的页码窗口（上限 7 页）
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
      </div>
    </nav>
  );
}

function CommunityPage() {
  return (
    <ProtectedRoute>
      <CommunityPageInner />
    </ProtectedRoute>
  );
}

export default CommunityPage;