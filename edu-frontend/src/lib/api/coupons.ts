import { http } from "@/lib/api-client";

/**
 * 优惠券客户端（PROPOSED — 待后端 task16 实现，契约冻结后跑 contract-diff 复核）
 * 领券端点对齐后端幂等中间件预留前缀 /api/trade/coupon/receive（防超发 + 幂等）
 * 端点设计上浮见 .opencode/handoffs/api-request.md
 */

export type CouponType = "discount" | "cash" | "full_cut";
export type CouponStatus = "unused" | "used" | "expired";

export interface CouponTemplate {
  coupon_template_id: number;
  coupon_name: string;
  coupon_type: CouponType;
  face_value: number;
  min_spend: number;
  valid_from: string;
  valid_to: string;
  total_count: number;
  received_count: number;
  per_user_limit: number;
}

export interface Coupon {
  coupon_id: number;
  coupon_template_id: number;
  coupon_name: string;
  coupon_type: CouponType;
  face_value: number;
  min_spend: number;
  status: CouponStatus;
  valid_from: string;
  valid_to: string;
  received_at: string;
  used_at: string | null;
  order_no: string | null;
}

export interface CouponReceiveInput {
  coupon_template_id: number;
}

export interface CouponPageParams {
  status?: CouponStatus;
  page?: number;
  page_size?: number;
}

export interface CouponPage {
  total: number;
  page: number;
  page_size: number;
  items: Coupon[];
}

export function listMyCoupons(params: CouponPageParams = {}): Promise<CouponPage> {
  return http.get<CouponPage>("/api/coupons", { params });
}

/**
 * 系列适用券模板列表（task46 课程详情领券弹窗，对齐 P8：GET /api/coupons?series_id=）。
 * 返回可领券模板（CouponTemplate[]）；已领取态由前端 listMyCoupons 交叉标记。
 */
export function listSeriesCoupons(seriesId: number): Promise<CouponTemplate[]> {
  return http.get<CouponTemplate[]>("/api/coupons", { params: { series_id: seriesId } });
}

export function listCouponTemplates(): Promise<CouponTemplate[]> {
  return http.get<CouponTemplate[]>("/api/coupons/templates");
}

export function receiveCoupon(input: CouponReceiveInput): Promise<Coupon> {
  return http.post<Coupon>("/api/trade/coupon/receive", input);
}
