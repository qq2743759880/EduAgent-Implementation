/**
 * CommentSection 单测（对抗 fe-task01 #3）：
 * 回帖列表分页「加载更多」——>20 条评论可继续按页加载，加载完隐藏按钮。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommentSection } from "./CommentSection";
import { listComments, type CommentListResponse } from "@/lib/api/community";

vi.mock("@/lib/api/community", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/community")>("@/lib/api/community");
  return { ...actual, listComments: vi.fn(), createComment: vi.fn(), toggleCommentLike: vi.fn() };
});

const mockListComments = vi.mocked(listComments);

/** 构造后端分页响应：{ total, page, page_size, items }（契约对齐 CommentListResponse） */
function makePage(page: number, total: number, pageSize = 20): CommentListResponse {
  const start = (page - 1) * pageSize + 1;
  const count = Math.min(pageSize, Math.max(0, total - (page - 1) * pageSize));
  return {
    total,
    page,
    page_size: pageSize,
    items: Array.from({ length: count }, (_, i) => ({
      comment_id: start + i,
      post_id: 1,
      author_id: 1,
      author_name: `用户${start + i}`,
      parent_id: null,
      reply_to_id: null,
      content_md: `评论内容 ${start + i}`,
      like_count: 0,
      mine_liked: false,
      created_at: "2026-08-01T10:00:00",
    })),
  };
}

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CommentSection postId={1} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CommentSection 分页", () => {
  it("评论 >20 条时显示「加载更多」，点击后按页追加并隐藏按钮", async () => {
    const user = userEvent.setup();
    mockListComments
      .mockResolvedValueOnce(makePage(1, 25))
      .mockResolvedValueOnce(makePage(2, 25));

    renderSection();

    /* 第 1 页：20 条可见 + 加载更多按钮 */
    expect(await screen.findByText("评论内容 1")).toBeInTheDocument();
    expect(screen.getByText("评论内容 20")).toBeInTheDocument();
    const loadMore = screen.getByRole("button", { name: /加载更多/ });
    expect(loadMore).toHaveTextContent("20/25");

    await user.click(loadMore);

    /* 第 2 页追加：25 条全部可见，按钮消失 */
    await waitFor(() => {
      expect(screen.getByText("评论内容 25")).toBeInTheDocument();
    });
    expect(mockListComments).toHaveBeenNthCalledWith(2, 1, 2, 20);
    expect(screen.queryByRole("button", { name: /加载更多/ })).not.toBeInTheDocument();
  });

  it("单页（≤20 条）不显示「加载更多」", async () => {
    mockListComments.mockResolvedValueOnce(makePage(1, 15));

    renderSection();

    expect(await screen.findByText("评论内容 1")).toBeInTheDocument();
    expect(screen.getByText("评论内容 15")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /加载更多/ })).not.toBeInTheDocument();
  });

  it("评论总数展示与分页一致", async () => {
    mockListComments.mockResolvedValueOnce(makePage(1, 25));

    renderSection();

    expect(await screen.findByText(/共 25 条回帖/)).toBeInTheDocument();
  });
});
