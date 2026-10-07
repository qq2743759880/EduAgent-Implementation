/**
 * ReactButtons 单测：点赞/收藏软切换，计数以服务端响应为准即时更新。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReactButtons } from "./ReactButtons";
import { togglePostLike, togglePostFavorite } from "@/lib/api/community";

vi.mock("@/lib/api/community", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/community")>("@/lib/api/community");
  return { ...actual, togglePostLike: vi.fn(), togglePostFavorite: vi.fn() };
});

const mockToggleLike = vi.mocked(togglePostLike);
const mockToggleFavorite = vi.mocked(togglePostFavorite);

/** ReactButtons 内部用 useMutation，需要 QueryClientProvider */
function renderButtons(props: React.ComponentProps<typeof ReactButtons>) {
  const qc = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ReactButtons {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ReactButtons", () => {
  it("渲染初始点赞/收藏计数", () => {
    renderButtons({
      postId: 1,
      likeActive: false,
      likeCount: 3,
      favoriteActive: false,
      favoriteCount: 5,
    });
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /点赞/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /收藏/ })).toBeInTheDocument();
  });

  it("点赞成功后用服务端 total_count 即时更新计数（定向回写 like）", async () => {
    const user = userEvent.setup();
    const onCountsChange = vi.fn();
    mockToggleLike.mockResolvedValueOnce({
      target_type: "POST",
      target_id: 1,
      react_type: "LIKE",
      active: true,
      total_count: 4,
      points_awarded: 0,
    });

    renderButtons({
      postId: 1,
      likeActive: false,
      likeCount: 3,
      favoriteActive: false,
      favoriteCount: 5,
      onCountsChange,
    });

    await user.click(screen.getByRole("button", { name: /点赞/ }));
    await waitFor(() => {
      expect(onCountsChange).toHaveBeenCalledWith("like", { active: true, count: 4 });
    });
    expect(mockToggleLike).toHaveBeenCalledWith(1);
  });

  it("点赞成功只回写 like 项，不携带/覆盖 favorite（定向更新防陈旧值回写）", async () => {
    const user = userEvent.setup();
    const onCountsChange = vi.fn();
    mockToggleLike.mockResolvedValueOnce({
      target_type: "POST",
      target_id: 1,
      react_type: "LIKE",
      active: true,
      total_count: 9,
      points_awarded: 0,
    });

    renderButtons({
      postId: 1,
      likeActive: false,
      likeCount: 3,
      favoriteActive: true, // 模拟与本 render 不同的收藏态（陈旧兄弟字段场景）
      favoriteCount: 5,
      onCountsChange,
    });

    await user.click(screen.getByRole("button", { name: /点赞/ }));
    await waitFor(() => {
      expect(onCountsChange).toHaveBeenCalledWith("like", { active: true, count: 9 });
    });
    expect(onCountsChange).toHaveBeenCalledTimes(1);
  });

  it("再点一次取消点赞（软切换 active=false）", async () => {
    const user = userEvent.setup();
    const onCountsChange = vi.fn();
    mockToggleLike.mockResolvedValueOnce({
      target_type: "POST",
      target_id: 1,
      react_type: "LIKE",
      active: false,
      total_count: 2,
      points_awarded: 0,
    });

    renderButtons({
      postId: 1,
      likeActive: true,
      likeCount: 3,
      favoriteActive: false,
      favoriteCount: 5,
      onCountsChange,
    });

    await user.click(screen.getByRole("button", { name: /已赞/ }));
    await waitFor(() => {
      expect(onCountsChange).toHaveBeenCalledWith("like", { active: false, count: 2 });
    });
  });

  it("收藏切换走 /favorite 对应函数（定向回写 favorite）", async () => {
    const user = userEvent.setup();
    const onCountsChange = vi.fn();
    mockToggleFavorite.mockResolvedValueOnce({
      target_type: "POST",
      target_id: 1,
      react_type: "FAVORITE",
      active: true,
      total_count: 6,
      points_awarded: 0,
    });

    renderButtons({
      postId: 1,
      likeActive: false,
      likeCount: 0,
      favoriteActive: false,
      favoriteCount: 5,
      onCountsChange,
    });

    await user.click(screen.getByRole("button", { name: /收藏/ }));
    await waitFor(() => {
      expect(mockToggleFavorite).toHaveBeenCalledWith(1);
      expect(onCountsChange).toHaveBeenCalledWith("favorite", { active: true, count: 6 });
    });
  });

  it("写操作失败：不更新计数（错误由全局 onError toast）", async () => {
    const user = userEvent.setup();
    const onCountsChange = vi.fn();
    mockToggleLike.mockRejectedValueOnce(new Error("403"));

    renderButtons({
      postId: 1,
      likeActive: false,
      likeCount: 3,
      favoriteActive: false,
      favoriteCount: 5,
      onCountsChange,
    });

    await user.click(screen.getByRole("button", { name: /点赞/ }));
    await waitFor(() => expect(mockToggleLike).toHaveBeenCalled());
    expect(onCountsChange).not.toHaveBeenCalled();
  });
});
