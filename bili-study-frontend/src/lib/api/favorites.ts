import { http } from "@/lib/api-client";

/**
 * 课程收藏客户端（PROPOSED — 待后端 task16 实现，契约冻结后跑 contract-diff 复核）
 * 业务语义：课程（series）收藏 CRUD，替换 learning.ts 中已删除的 localStorage 本地收藏
 * 端点设计上浮见 .opencode/handoffs/api-request.md
 */

export type FavoriteTargetType = "series";

export interface FavoriteItem {
  favorite_id: number;
  user_id: number;
  target_type: FavoriteTargetType;
  series_id: number;
  series_title: string;
  cover_url: string | null;
  created_at: string;
}

export interface FavoriteCreateInput {
  series_id: number;
}

export interface FavoriteDeletedResponse {
  deleted: boolean;
  series_id: number;
}

export interface ListFavoritesParams {
  target_type?: FavoriteTargetType;
  page?: number;
  page_size?: number;
}

export interface FavoritePage {
  total: number;
  page: number;
  page_size: number;
  items: FavoriteItem[];
}

export function listFavorites(
  params: ListFavoritesParams = {},
): Promise<FavoritePage> {
  return http.get<FavoritePage>("/api/favorites", { params });
}

export function addFavorite(input: FavoriteCreateInput): Promise<FavoriteItem> {
  return http.post<FavoriteItem>("/api/favorites", input);
}

export function removeFavorite(seriesId: number): Promise<FavoriteDeletedResponse> {
  return http.delete<FavoriteDeletedResponse>(`/api/favorites/${seriesId}`);
}
