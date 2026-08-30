/**
 * 全局枚举映射表（单源，§3.3）
 * 两处消费：StatusBadge（徽章 tone + label）+ 页面文案 statusText(map, value)。
 * 冻结约定（契约①）：内部 key 用 snake_case，与后端字段值一一对应；值不可变。
 *
 * tone 语义（对应 design-tokens 状态色）：
 *   success   emerald 成功/可完成
 *   warning   amber   待处理/需注意
 *   danger    rose    失败/危险/已拒绝
 *   neutral   slate   中性（已完成/关闭/禁用等无强调态）
 *   primary   indigo  进行中/主流程强调
 */

/** 徽章语义色调（仅 5 项，映射表中的 muted 统一归入 neutral） */
export type StatusTone =
  | "success"
  | "warning"
  | "danger"
  | "neutral"
  | "primary";

export type StatusMapEntry = {
  /** 按钮文案 */
  label: string;
  tone: StatusTone;
};

/** 枚举组 key 全集 */
export type StatusMapKey =
  | "order_status"
  | "order_item_status"
  | "payment_status"
  | "refund_status"
  | "receive_status"
  | "enroll_status"
  | "teaching_status"
  | "transcode_status"
  | "review_status"
  | "ticket_status"
  | "priority_level"
  | "series_sale_status"
  | "delivery_mode";

/**
 * 13 组状态机枚举映射。值为后端下发的原始状态字段值（snake_case），
 * 任一映射未命中时 tone 默认 neutral、label 回退为原始值（不静默吞错成像）。
 */
export const STATUS_MAPS: Record<StatusMapKey, Record<string, StatusMapEntry>> = {
  // 订单
  order_status: {
    pending: { label: "待付款", tone: "warning" },
    paid: { label: "已支付", tone: "success" },
    completed: { label: "已完成", tone: "neutral" },
    cancelled: { label: "已取消", tone: "neutral" },
    partial_refunded: { label: "部分退款", tone: "warning" },
    refunded: { label: "已退款", tone: "danger" },
  },
  // 订单明细
  order_item_status: {
    pending: { label: "待付款", tone: "warning" },
    paid: { label: "已支付", tone: "success" },
    completed: { label: "已完成", tone: "neutral" },
    cancelled: { label: "已取消", tone: "neutral" },
    refunded: { label: "已退款", tone: "danger" },
  },
  // 支付
  payment_status: {
    pending: { label: "处理中", tone: "warning" },
    paid: { label: "已支付", tone: "success" },
    failed: { label: "失败", tone: "danger" },
    closed: { label: "已关闭", tone: "neutral" },
    partial_refunded: { label: "部分退款", tone: "warning" },
    refunded: { label: "已退款", tone: "danger" },
  },
  // 退款
  refund_status: {
    pending: { label: "审核中", tone: "warning" },
    approved: { label: "已通过", tone: "primary" },
    rejected: { label: "已拒绝", tone: "danger" },
    refunded: { label: "已退款", tone: "success" },
  },
  // 优惠券领取
  receive_status: {
    unused: { label: "未使用", tone: "primary" },
    used: { label: "已使用", tone: "neutral" },
    expired: { label: "已过期", tone: "neutral" },
  },
  // 报名
  enroll_status: {
    active: { label: "学习中", tone: "success" },
    completed: { label: "已完成", tone: "neutral" },
    cancelled: { label: "已取消", tone: "neutral" },
    refunded: { label: "已退款", tone: "danger" },
  },
  // 课次
  teaching_status: {
    scheduled: { label: "未开始", tone: "neutral" },
    in_progress: { label: "进行中", tone: "primary" },
    completed: { label: "已完成", tone: "success" },
    cancelled: { label: "已取消", tone: "danger" },
  },
  // 转码
  transcode_status: {
    pending: { label: "待转码", tone: "warning" },
    in_progress: { label: "转码中", tone: "primary" },
    completed: { label: "已就绪", tone: "success" },
    failed: { label: "失败", tone: "danger" },
  },
  // 审核
  review_status: {
    pending: { label: "待审核", tone: "warning" },
    approved: { label: "已通过", tone: "success" },
    rejected: { label: "已驳回", tone: "danger" },
  },
  // 工单
  ticket_status: {
    pending: { label: "待受理", tone: "warning" },
    in_progress: { label: "处理中", tone: "primary" },
    closed: { label: "已关闭", tone: "neutral" },
  },
  // 优先级
  priority_level: {
    low: { label: "低", tone: "neutral" },
    medium: { label: "中", tone: "neutral" },
    high: { label: "高", tone: "warning" },
    urgent: { label: "紧急", tone: "danger" },
  },
  // 系列上下架
  series_sale_status: {
    draft: { label: "草稿", tone: "neutral" },
    on_sale: { label: "在售", tone: "success" },
    off_sale: { label: "已下架", tone: "neutral" },
  },
  // 交付模式
  delivery_mode: {
    online_live: { label: "在线直播", tone: "primary" },
    online_recorded: { label: "在线录播", tone: "primary" },
    offline_face_to_face: { label: "线下面授", tone: "primary" },
  },
};

/** 纯文案枚举（无状态语义，不用于徽章 tone） */
export const REFUND_TYPE_TEXT: Record<string, string> = {
  personal_reason: "个人原因",
  course_unsatisfied: "课程不满意",
  schedule_conflict: "时间冲突",
  duplicate_purchase: "重复购买",
};

export const TICKET_TYPE_TEXT: Record<string, string> = {
  after_sales: "售后",
  complaint: "投诉",
  refund: "退款",
  appeal: "人工申诉",
};

/** 由映射组取色调；未知值 fallback 到 neutral（不做吞错展示） */
export function statusTone<K extends StatusMapKey>(
  map: K,
  value: string | null | undefined,
): StatusTone {
  if (!value) return "neutral";
  return STATUS_MAPS[map][value]?.tone ?? "neutral";
}

/** 由映射组取中文文案；未知值原样回退（可见地暴露未映射状态） */
export function statusText<K extends StatusMapKey>(
  map: K,
  value: string | null | undefined,
): string {
  if (!value) return "-";
  const label = STATUS_MAPS[map][value]?.label;
  return label ?? value;
}