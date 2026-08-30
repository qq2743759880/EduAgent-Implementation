/**
 * /community 社区列表页测试（task51 candy-playful）：
 *  - 四态：loading（骨架 role=status）/ error（role=alert + 重试）/ empty（role=status + 发第一篇）/ success（渲染帖子卡 + 分页）
 *  - 数据：🎒 我的帖子计数、共 N 条；点击版块 chip 重查（board_code 参数）；重试重新查询
 * listPosts 全 vi.mock（真实 QueryClientProvider，queryKey 全参数）。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommunityPageInner } from "./page";
import { listPosts, type PostListResponse, type PostSummary } from "@/lib/api/community";

vi.mock("@/lib/api/community", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/community")>();
  return {
    ...actual,
    listPosts: vi.fn(),
  };
});

const listPostsMock = vi.mocked(listPosts);

function makePost(overrides: Partial<PostSummary> = {}): PostSummary {
  return {
    post_id: 11,
    board_code: "english",
    author_id: 1,
    author_name: "小明",
    title: "雅思 7.5 备考心得分享",
    summary: "三个月从 6.0 到 7.5，分享我的阅读提速方法…",
    tags: ["雅思"],
    is_pinned: true,
    is_locked: false,
    view_count: 120,
    like_count: 8,
    comment_count: 3,
    favorite_count: 5,
    hot_score: 66.6,
    mine_react_like: false,
    mine_react_favorite: false,
    created_at: "2026-08-12T10:00:00",
    updated_at: "2026-08-12T10:00:00",
    ...overrides,
  };
}

function successResp(items: PostSummary[] = [makePost()]): PostListResponse {
  return { total: 12, page: 1, page_size: 10, items, mine_total_posts: 3 };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <CommunityPageInner />
    </QueryClientProvider>,
  );
}

describe("/community 列表页", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listPostsMock.mockResolvedValue(successResp());
  });

  it("加载态显示骨架（role=status + 读屏文本）", () => {
    listPostsMock.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("正在加载帖子…")).toBeInTheDocument();
  });

  it("成功态渲染帖子卡、『我的帖子』计数与分页", async () => {
    renderPage();
    expect(await screen.findByText("雅思 7.5 备考心得分享")).toBeInTheDocument();
    expect(screen.getByText(/我的帖子/)).toHaveTextContent("3");
    expect(screen.getByText("共 12 条")).toBeInTheDocument();
  });

  it("空态显示『暂无帖子』+ 发第一篇 CTA", async () => {
    listPostsMock.mockResolvedValue({ total: 0, page: 1, page_size: 10, items: [], mine_total_posts: 0 });
    renderPage();
    expect(await screen.findByText("暂无帖子")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("＋ 发第一篇")).toBeInTheDocument();
  });

  it("错误态显示『帖子加载失败』+ 重试；点重试重新查询", async () => {
    listPostsMock.mockRejectedValue(new Error("network"));
    renderPage();
    expect(await screen.findByText("帖子加载失败")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: /重试/ });
    listPostsMock.mockResolvedValue(successResp());
    await userEvent.setup().click(retry);
    await waitFor(() => expect(listPostsMock).toHaveBeenCalledTimes(2));
  });

  it("点击版块 chip 以 board_code 重新查询", async () => {
    renderPage();
    await screen.findByText("雅思 7.5 备考心得分享");
    await userEvent.setup().click(screen.getByText("数学"));
    await waitFor(() =>
      expect(listPostsMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ board_code: "math", page: 1 }),
      ),
    );
  });
});