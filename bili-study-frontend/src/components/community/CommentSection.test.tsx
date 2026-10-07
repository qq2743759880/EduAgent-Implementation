/**
 * CommentSection 单测（task52）：评论分页 C2 + 回帖 + 锁定禁用。
 * 契约：GET /posts/{id}/comments?page&page_size → { total, page, page_size, items }
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CommentSection } from "./CommentSection";
import { listComments, createComment, type CommentListResponse } from "@/lib/api/community";

vi.mock("@/lib/api/community", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/community")>("@/lib/api/community");
  return { ...actual, listComments: vi.fn(), createComment: vi.fn(), toggleCommentLike: vi.fn() };
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockListComments = vi.mocked(listComments);
const mockCreateComment = vi.mocked(createComment);

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

function renderSection(props: Partial<React.ComponentProps<typeof CommentSection>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CommentSection postId={1} {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CommentSection 分页 C2", () => {
  const USER = { pointerEventsCheck: 0, delay: null } as const;

  it("评论 >20 条时显示分页器，点下一页加载第 2 页", async () => {
    const user = userEvent.setup(USER);
    mockListComments
      .mockResolvedValueOnce(makePage(1, 25))
      .mockResolvedValueOnce(makePage(2, 25));

    renderSection();

    /* 第 1 页：20 条可见 + 分页器（2 页） */
    expect(await screen.findByText("评论内容 1", undefined, { timeout: 10000 })).toBeInTheDocument();
    expect(screen.getByText("评论内容 20")).toBeInTheDocument();
    expect(screen.getByText("共 25 条")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "评论分页" })).toBeInTheDocument();

    /* 点下一页 → 第 2 页 */
    await user.click(screen.getByRole("button", { name: "下一页" }));
    expect(await screen.findByText("评论内容 25", undefined, { timeout: 15000 })).toBeInTheDocument();
    expect(mockListComments).toHaveBeenNthCalledWith(2, 1, 2, 20);
  });

  it("单页（≤20 条）不显示分页器", async () => {
    mockListComments.mockResolvedValueOnce(makePage(1, 15));

    renderSection();

    expect(await screen.findByText("评论内容 1", undefined, { timeout: 10000 })).toBeInTheDocument();
    expect(screen.getByText("评论内容 15")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "评论分页" })).not.toBeInTheDocument();
  });

  it("评论总数展示与分页一致", async () => {
    mockListComments.mockResolvedValueOnce(makePage(1, 25));

    renderSection();

    /* 标题徽标：25 条（锚定避免与分页器『共 25 条』重复匹配） */
    expect(await screen.findByText(/^25 条$/, undefined, { timeout: 10000 })).toBeInTheDocument();
    /* 分页器：共 25 条 */
    expect(screen.getByText(/^共 25 条$/)).toBeInTheDocument();
  });

  it("回帖成功：调用 createComment + 清空输入 + 计数 +1 回调", async () => {
    const user = userEvent.setup(USER);
    /* mockResolvedValue（非 Once）：回帖成功后 invalidate 重拉评论列表时 mock 不耗尽，避免 Query data undefined 警告 */
    mockListComments.mockResolvedValue(makePage(1, 0));
    mockCreateComment.mockResolvedValueOnce({ comment_id: 99, created_at: "2026-08-22T10:00:00", points: 2 });
    const onCount = vi.fn();

    renderSection({ onCommentCountChange: onCount });

    const input = await screen.findByPlaceholderText(/写下你的看法/);
    await user.type(input, "好帖，收藏了！");
    await user.click(screen.getByRole("button", { name: /发布/ }));

    await waitFor(() => {
      expect(mockCreateComment).toHaveBeenCalledWith(1, { content_md: "好帖，收藏了！" });
    });
    expect(onCount).toHaveBeenCalledWith(1);
  });

  it("锁定帖：输入框与发布按钮禁用", async () => {
    mockListComments.mockResolvedValueOnce(makePage(1, 0));

    renderSection({ locked: true });

    const input = await screen.findByPlaceholderText(/本帖已锁定/);
    expect(input).toBeDisabled();
    expect(screen.getByRole("button", { name: /发布/ })).toBeDisabled();
  });
});
