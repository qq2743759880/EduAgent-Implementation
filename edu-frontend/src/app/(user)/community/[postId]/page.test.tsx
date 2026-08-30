/**
 * /community/[postId] 帖子详情页测试（task52 candy-playful）：
 *  - 成功：渲染标题/作者/正文/点赞收藏操作行
 *  - 404：ErrorState（role=alert + 帖子不存在）+ 返回列表 CTA（GWT③）
 *  - 锁定帖：操作行隐藏（无点赞按钮）+ 锁定 banner + 评论区禁用
 * getPostDetail 全 vi.mock（真实 QueryClientProvider）。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PostDetailInner } from "./page";
import { getPostDetail, type PostDetail } from "@/lib/api/community";
import { ApiError } from "@/lib/api-client";

vi.mock("@/lib/api/community", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/community")>();
  return {
    ...actual,
    getPostDetail: vi.fn(),
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
}));

const getDetailMock = vi.mocked(getPostDetail);

function makeDetail(overrides: Partial<PostDetail> = {}): PostDetail {
  return {
    post_id: 11,
    board_code: "math",
    author_id: 1,
    author_name: "小豆芽",
    title: "高数第三章「分部积分」易错题集锦",
    summary: "整理了分部积分的 5 个典型易错点…",
    content_md: "整理了分部积分的 **5 个典型易错点**。",
    tags: ["高数", "易错"],
    is_pinned: true,
    is_locked: false,
    view_count: 1283,
    like_count: 342,
    comment_count: 18,
    favorite_count: 57,
    hot_score: 99.9,
    mine_react_like: false,
    mine_react_favorite: false,
    created_at: "2026-08-20T09:12:00",
    updated_at: "2026-08-20T09:12:00",
    ...overrides,
  };
}

function renderInner(postId = 11) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PostDetailInner postId={postId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PostDetailInner", () => {
  it("成功渲染详情：标题/作者/正文/点赞收藏操作行", async () => {
    getDetailMock.mockResolvedValueOnce(makeDetail());

    renderInner();

    expect(await screen.findByRole("heading", { name: /分部积分/ })).toBeInTheDocument();
    expect(screen.getByText("小豆芽")).toBeInTheDocument();
    expect(screen.getByText(/5 个典型易错点/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /点赞/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /收藏/ })).toBeInTheDocument();
  });

  it("帖子不存在（404）：ErrorState + 返回列表 CTA（GWT③）", async () => {
    getDetailMock.mockRejectedValue(
      new ApiError(404, { message: "帖子不存在", code: "COMMUNITY_POST_NOT_FOUND" }),
    );

    renderInner(999);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("帖子不存在")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /返回列表/ })).toBeInTheDocument();
  });

  it("锁定帖：操作行隐藏（无点赞按钮）+ 锁定提示 + 评论输入禁用", async () => {
    getDetailMock.mockResolvedValueOnce(makeDetail({ is_locked: true }));

    renderInner();

    expect(await screen.findByText(/本帖已锁定/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /点赞/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /收藏/ })).not.toBeInTheDocument();
    expect(await screen.findByPlaceholderText(/本帖已锁定/)).toBeDisabled();
  });
});
