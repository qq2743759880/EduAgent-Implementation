/**
 * community.ts API 封装单测（task40 拦截器解包迁移）
 * 覆盖：查询参数拼装、写操作字段对齐（content_md）、写操作失败向上抛（不吞错）。
 * mock http.* 直接返回业务体（契约冻结①：拦截器已解包，无 .data 壳）
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { http } from "@/lib/api-client";
import {
  createComment,
  createPost,
  getRankings,
  listComments,
  listPosts,
  togglePostFavorite,
  togglePostLike,
} from "./community";

vi.mock("@/lib/api-client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    ...actual,
    http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  };
});

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("listPosts", () => {
  it("默认参数：sort=HOT&page=1&page_size=20", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, page: 1, page_size: 20, items: [], mine_total_posts: 0 });
    await listPosts();
    expect(mockGet).toHaveBeenCalledWith("/api/community/posts?sort=HOT&page=1&page_size=20");
  });

  it("分版 + 排序 + 分页参数正确拼装", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listPosts({ sort: "NEW", board_code: "english", page: 3, page_size: 10 });
    expect(mockGet).toHaveBeenCalledWith(
      "/api/community/posts?sort=NEW&board_code=english&page=3&page_size=10",
    );
  });

  it("空 board_code 不拼该参数（=全部）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listPosts({ board_code: "", keyword: "  " });
    expect(mockGet).toHaveBeenCalledWith("/api/community/posts?sort=HOT&page=1&page_size=20");
  });

  it("列表失败向上抛（页面负责错误态，不静默返回空）", async () => {
    mockGet.mockRejectedValueOnce(new Error("Network Error"));
    await expect(listPosts()).rejects.toThrow("Network Error");
  });
});

describe("listPosts keyword 转义（对抗 fe-task01 #8）", () => {
  it("keyword 含 %/_ 时转义（后端 LIKE 通配符，防超集命中）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listPosts({ keyword: "100%_off" });
    expect(mockGet).toHaveBeenCalledWith(
      "/api/community/posts?sort=HOT&keyword=100%5C%25%5C_off&page=1&page_size=20",
    );
  });

  it("反斜杠本身也转义（防止破坏转义序列）", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listPosts({ keyword: "a\\b" });
    expect(mockGet).toHaveBeenCalledWith(
      "/api/community/posts?sort=HOT&keyword=a%5C%5Cb&page=1&page_size=20",
    );
  });

  it("纯空白 keyword 仍不拼参数", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listPosts({ keyword: "  " });
    expect(mockGet).toHaveBeenCalledWith("/api/community/posts?sort=HOT&page=1&page_size=20");
  });
});

describe("createPost（写操作）", () => {
  it("body 字段对齐后端 schema：title/content_md/board_code/tags", async () => {
    mockPost.mockResolvedValueOnce({ post_id: 42, points_awarded: 5, badge_unlocked: [] });
    const resp = await createPost({
      title: "雅思 7.5 备考心得",
      content_md: "# 心得",
      board_code: "english",
      tags: ["雅思", "阅读"],
    });
    expect(mockPost).toHaveBeenCalledWith("/api/community/posts", {
      title: "雅思 7.5 备考心得",
      content_md: "# 心得",
      board_code: "english",
      tags: ["雅思", "阅读"],
    });
    expect(resp.post_id).toBe(42);
    expect(resp.points_awarded).toBe(5);
  });

  it("发帖失败必须抛错（不静默吞错，由调用方 toast）", async () => {
    mockPost.mockRejectedValueOnce(new Error("标题过短"));
    await expect(
      createPost({ title: "x", content_md: "yy", board_code: "general" }),
    ).rejects.toThrow("标题过短");
  });
});

describe("点赞 / 收藏 / 回帖（写操作）", () => {
  it("togglePostLike 走 POST /posts/{id}/like", async () => {
    mockPost.mockResolvedValueOnce({ target_type: "POST", target_id: 7, react_type: "LIKE", active: true, total_count: 3, points_awarded: 0 });
    const resp = await togglePostLike(7);
    expect(mockPost).toHaveBeenCalledWith("/api/community/posts/7/like");
    expect(resp.active).toBe(true);
    expect(resp.total_count).toBe(3);
  });

  it("togglePostFavorite 走 POST /posts/{id}/favorite", async () => {
    mockPost.mockResolvedValueOnce({ active: false, total_count: 0 });
    await togglePostFavorite(7);
    expect(mockPost).toHaveBeenCalledWith("/api/community/posts/7/favorite");
  });

  it("createComment body 携带 content_md + parent_id，响应含 points=2", async () => {
    mockPost.mockResolvedValueOnce({ comment_id: 9, created_at: "2026-08-12T10:00:00", points: 2 });
    const resp = await createComment(7, { content_md: "沙发！", parent_id: 1, reply_to_id: 1 });
    expect(mockPost).toHaveBeenCalledWith("/api/community/posts/7/comments", {
      content_md: "沙发！",
      parent_id: 1,
      reply_to_id: 1,
    });
    expect(resp.points).toBe(2);
  });

  it("写操作失败全部向上抛", async () => {
    mockPost.mockRejectedValue(new Error("403 Forbidden"));
    await expect(togglePostLike(1)).rejects.toThrow();
    await expect(togglePostFavorite(1)).rejects.toThrow();
    await expect(createComment(1, { content_md: "hi" })).rejects.toThrow();
  });
});

describe("comments / rankings（列表）", () => {
  it("listComments 拼装分页参数", async () => {
    mockGet.mockResolvedValueOnce({ total: 0, items: [] });
    await listComments(7, 2, 20);
    expect(mockGet).toHaveBeenCalledWith("/api/community/posts/7/comments?page=2&page_size=20");
  });

  it("getRankings 拼装 scope/dimension/top_n（契约：DAILY|WEEKLY|MONTHLY|ALL_TIME）", async () => {
    mockGet.mockResolvedValueOnce({ scope: "WEEKLY", dimension: "POINTS", top: [], my_rank: null });
    await getRankings("WEEKLY", "POINTS", 20);
    expect(mockGet).toHaveBeenCalledWith(
      "/api/gamification/rankings?scope=WEEKLY&dimension=POINTS&top_n=20",
    );
  });
});
