/**
 * 社区 & 成就中心 API 封装（能力 6 / P6，task01）
 *
 * 后端路由：
 *   社区（app/community/router.py，9 条，全部 require_login）：
 *     GET  /api/community/posts?sort&board_code&keyword&page&page_size
 *     POST /api/community/posts                 {board_code,title,content_md,tags}
 *     GET  /api/community/posts/{id}            （浏览量自动 +1）
 *     POST /api/community/posts/{id}/like       软切换（点赞/取消）
 *     POST /api/community/posts/{id}/favorite   软切换（收藏/取消）
 *     GET/POST /api/community/posts/{id}/comments
 *     POST /api/community/comments/{id}/like
 *   成就（app/gamification/router.py，5 条）：
 *     GET /api/gamification/me/badges
 *     GET /api/gamification/me/points?page&page_size
 *     GET /api/gamification/rankings?scope&dimension&top_n
 *
 * 契约口径：字段名以后端 schemas.py 为准（如 post_id/summary/content_md、
 * unlocked_count/badge_name、recent_logs、rankings.top 等），
 * 不要按 PRD 旧口径（id/content_preview/nickname/is_mine）写死。
 *
 * 错误处理（红线 4 / R-7 治理）：
 *   - 写操作（POST）失败一律向上抛 ApiError，由调用方 toast，绝不静默吞错；
 *   - 列表操作同样不 try/catch 兜底——页面层负责 loading/error/empty 三态。
 */
import { api } from "@/lib/api-client";

/* =====================================================================
 * TYPES（对齐 app/community/schemas.py + app/gamification/schemas.py）
 * ===================================================================*/

export type BoardCode = "english" | "math" | "programming" | "general";

export type PostSort = "HOT" | "NEW" | "LIKE";

export interface PostSummary {
  post_id: number;
  board_code: string;
  author_id: number;
  author_name: string | null;
  title: string;
  /** 后端把 content_md 截 120 字生成 */
  summary: string;
  tags: string[];
  is_pinned: boolean;
  is_locked: boolean;
  view_count: number;
  like_count: number;
  comment_count: number;
  favorite_count: number;
  hot_score: number;
  mine_react_like: boolean;
  mine_react_favorite: boolean;
  created_at: string;
  updated_at: string;
}

export interface PostDetail extends PostSummary {
  content_md: string;
}

export interface PostListResponse {
  total: number;
  page: number;
  page_size: number;
  items: PostSummary[];
  mine_total_posts: number;
}

export interface CommentItem {
  comment_id: number;
  post_id: number;
  author_id: number;
  author_name: string | null;
  parent_id: number | null;
  reply_to_id: number | null;
  content_md: string;
  like_count: number;
  mine_liked: boolean;
  created_at: string;
}

export interface CommentListResponse {
  total: number;
  page: number;
  page_size: number;
  items: CommentItem[];
}

export interface ReactToggleResponse {
  target_type: "POST" | "COMMENT";
  target_id: number;
  react_type: "LIKE" | "FAVORITE";
  active: boolean;
  total_count: number;
  points_awarded: number;
}

export interface CreatePostPayload {
  title: string;
  content_md: string;
  board_code: BoardCode;
  tags?: string[];
}

export interface CreatePostResponse {
  post_id: number;
  points_awarded: number;
  badge_unlocked: string[];
}

export interface CreateCommentPayload {
  content_md: string;
  parent_id?: number | null;
  reply_to_id?: number | null;
}

export interface CreateCommentResponse {
  comment_id: number;
  created_at: string;
  /** 后端固定回帖奖励 2 分 */
  points: number;
}

/* ---------------- gamification ---------------- */

export type BadgeCategory = "LEARNING" | "ACHIEVEMENT" | "SOCIAL";
export type BadgeRarity = "COMMON" | "RARE" | "EPIC" | "LEGENDARY";

export interface BadgeItem {
  badge_code: string;
  badge_name: string;
  badge_desc: string;
  category: BadgeCategory;
  icon_emoji: string | null;
  rarity: BadgeRarity;
  trigger_rule: string;
  rule_value: number;
  reward_points: number;
  unlocked: boolean;
  unlocked_at: string | null;
  progress_current: number;
  progress_required: number;
  progress_pct: number;
}

export interface BadgeListResponse {
  total: number;
  unlocked_count: number;
  next_milestone: string;
  items: BadgeItem[];
}

export interface PointLogItem {
  log_id: number;
  point_type: string;
  delta: number;
  balance_after: number;
  note: string | null;
  created_at: string;
}

export interface PointsResponse {
  user_id: number;
  total_points: number;
  level_no: number;
  level_title: string;
  level_min: number;
  next_level_min: number;
  level_progress_pct: number;
  logs_total: number;
  recent_logs: PointLogItem[];
}

export type RankingScope = "DAILY" | "WEEKLY" | "MONTHLY" | "ALL_TIME";
export type RankingDimension = "POINTS" | "STUDY_MIN" | "BADGE_COUNT";

export interface RankingRow {
  rank_no: number;
  user_id: number;
  user_name: string | null;
  metric_value: number;
  level_no: number;
  is_myself: boolean;
  badge_count: number;
}

export interface RankingResponse {
  scope: RankingScope;
  dimension: RankingDimension;
  snapshot_date: string;
  top: RankingRow[];
  my_rank: RankingRow | null;
  source: string;
}

/* =====================================================================
 * 社区
 * ===================================================================*/

export interface ListPostsParams {
  sort?: PostSort;
  board_code?: BoardCode | "";
  keyword?: string;
  page?: number;
  page_size?: number;
}

/**
 * LIKE 通配符转义（对抗 fe-task01 #8）：后端 list_posts 对 keyword 走
 * `LIKE '%keyword%'`（community/service.py），未做转义。MySQL 默认转义符为
 * 反斜杠，这里把 `%`、`_` 与转义符本身统一转义，避免用户输入通配符造成超集命中。
 */
export function escapeLikeKeyword(value: string): string {
  return value.replace(/[\\%_]/g, "\\$&");
}

export async function listPosts(params: ListPostsParams = {}): Promise<PostListResponse> {
  const search = new URLSearchParams();
  search.set("sort", params.sort ?? "HOT");
  if (params.board_code) search.set("board_code", params.board_code);
  if (params.keyword?.trim()) search.set("keyword", escapeLikeKeyword(params.keyword.trim()));
  search.set("page", String(params.page ?? 1));
  search.set("page_size", String(params.page_size ?? 20));

  const { data } = await api.get<PostListResponse>(`/api/community/posts?${search.toString()}`);
  return data;
}

export async function getPostDetail(postId: number): Promise<PostDetail> {
  const { data } = await api.get<PostDetail>(`/api/community/posts/${postId}`);
  return data;
}

/** 发帖（成功 +5 分，后端在 points_awarded 返回）——写操作，失败必须抛 */
export async function createPost(payload: CreatePostPayload): Promise<CreatePostResponse> {
  const { data } = await api.post<CreatePostResponse>("/api/community/posts", payload);
  return data;
}

/** 点赞/取消点赞（软切换，返回 active + total_count）——写操作，失败必须抛 */
export async function togglePostLike(postId: number): Promise<ReactToggleResponse> {
  const { data } = await api.post<ReactToggleResponse>(`/api/community/posts/${postId}/like`);
  return data;
}

/** 收藏/取消收藏（软切换）——写操作，失败必须抛 */
export async function togglePostFavorite(postId: number): Promise<ReactToggleResponse> {
  const { data } = await api.post<ReactToggleResponse>(`/api/community/posts/${postId}/favorite`);
  return data;
}

export async function listComments(
  postId: number,
  page = 1,
  page_size = 20,
): Promise<CommentListResponse> {
  const { data } = await api.get<CommentListResponse>(
    `/api/community/posts/${postId}/comments?page=${page}&page_size=${page_size}`,
  );
  return data;
}

/** 回帖（成功 +2 分，后端固定返回 points:2）——写操作，失败必须抛 */
export async function createComment(
  postId: number,
  payload: CreateCommentPayload,
): Promise<CreateCommentResponse> {
  const { data } = await api.post<CreateCommentResponse>(
    `/api/community/posts/${postId}/comments`,
    payload,
  );
  return data;
}

/** 点赞评论——写操作，失败必须抛 */
export async function toggleCommentLike(commentId: number): Promise<ReactToggleResponse> {
  const { data } = await api.post<ReactToggleResponse>(`/api/community/comments/${commentId}/like`);
  return data;
}

/* =====================================================================
 * 成就 / 游戏化
 * ===================================================================*/

export async function getMyBadges(): Promise<BadgeListResponse> {
  const { data } = await api.get<BadgeListResponse>("/api/gamification/me/badges");
  return data;
}

export async function getMyPoints(page = 1, page_size = 20): Promise<PointsResponse> {
  const { data } = await api.get<PointsResponse>(
    `/api/gamification/me/points?page=${page}&page_size=${page_size}`,
  );
  return data;
}

export async function getRankings(
  scope: RankingScope = "DAILY",
  dimension: RankingDimension = "POINTS",
  topN = 20,
): Promise<RankingResponse> {
  const { data } = await api.get<RankingResponse>(
    `/api/gamification/rankings?scope=${scope}&dimension=${dimension}&top_n=${topN}`,
  );
  return data;
}
