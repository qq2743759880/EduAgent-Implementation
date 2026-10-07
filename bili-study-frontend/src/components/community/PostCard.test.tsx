/**
 * PostCard（C24，candy-playful）单测：渲染标题/作者/统计/分版/置顶锁定，标题链接指向详情页。
 * 列表卡仅展示 👁浏览/💬评论/👍点赞（对齐契约⑬ approved community.html，无收藏）。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PostCard } from "./PostCard";
import type { PostSummary } from "@/lib/api/community";

function makePost(overrides: Partial<PostSummary> = {}): PostSummary {
  return {
    post_id: 11,
    board_code: "english",
    author_id: 1,
    author_name: "小明",
    title: "雅思 7.5 备考心得分享",
    summary: "三个月从 6.0 到 7.5，分享我的阅读提速方法…",
    tags: ["雅思", "阅读"],
    is_pinned: false,
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

describe("PostCard", () => {
  it("渲染标题、作者、摘要与浏览/评论/点赞统计", () => {
    render(<PostCard post={makePost()} />);
    expect(screen.getByText("雅思 7.5 备考心得分享")).toBeInTheDocument();
    expect(screen.getByText("小明")).toBeInTheDocument();
    expect(screen.getByText(/三个月从 6.0 到 7.5/)).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("标题链接指向 /community/{post_id}", () => {
    render(<PostCard post={makePost()} />);
    const link = screen.getByRole("link", { name: "雅思 7.5 备考心得分享" });
    expect(link).toHaveAttribute("href", "/community/11");
  });

  it("渲染分版标签（英语）", () => {
    render(<PostCard post={makePost()} />);
    expect(screen.getByText("英语")).toBeInTheDocument();
  });

  it("置顶帖显示置顶标记", () => {
    render(<PostCard post={makePost({ is_pinned: true })} />);
    expect(screen.getByText("置顶")).toBeInTheDocument();
  });

  it("锁定帖只读：无链接、aria-label 注明只读、显示锁定标记", () => {
    const { container } = render(<PostCard post={makePost({ is_locked: true })} />);
    expect(screen.getByText("锁定")).toBeInTheDocument();
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector("article")).toHaveAttribute(
      "aria-label",
      "锁定帖（只读）：雅思 7.5 备考心得分享",
    );
  });

  it("未知分版兜底显示「综合」", () => {
    render(<PostCard post={makePost({ board_code: "physics" })} />);
    expect(screen.getByText("综合")).toBeInTheDocument();
  });
});