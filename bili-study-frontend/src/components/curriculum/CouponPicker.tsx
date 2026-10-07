/**
 * CouponPicker — 课程详情页「领券」弹窗（task46，对齐 P8 + HTML 效果图）。
 * 数据：GET /api/coupons?series_id= 系列适用券模板（CouponTemplate[]）。
 * 交互：未领取 → 领取（POST /api/trade/coupon/receive，幂等防超发）；已领取 → 可勾选抵扣（选中 coupon_id 用于下单）。
 * 已领取态由父级传入 receivedCoupons（listMyCoupons 交叉标记 + 本会话新领）。
 */
"use client";

import { useId, useState } from "react";
import { Ticket, CheckCircle2, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatAmount } from "@/components/ui/price-text";
import type { Coupon, CouponTemplate } from "@/lib/api/coupons";
import { cn } from "@/lib/utils";

export function CouponPicker({
  open,
  onOpenChange,
  templates,
  templatesLoading,
  receivedCoupons,
  onReceive,
  selectedCouponId,
  onSelectCoupon,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templates: CouponTemplate[];
  templatesLoading: boolean;
  receivedCoupons: Coupon[];
  onReceive: (templateId: number) => Promise<void>;
  selectedCouponId: number | null;
  onSelectCoupon: (couponId: number | null) => void;
}) {
  const titleId = useId();
  const [receivingId, setReceivingId] = useState<number | null>(null);

  const handleReceive = async (templateId: number) => {
    setReceivingId(templateId);
    try {
      await onReceive(templateId);
    } finally {
      setReceivingId(null);
    }
  };

  const receivedByTemplate = (templateId: number): Coupon[] =>
    receivedCoupons.filter((c) => c.coupon_template_id === templateId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle id={titleId}>领券中心</DialogTitle>
          <DialogDescription>领取本课程适用优惠券，下单时自动抵扣。</DialogDescription>
        </DialogHeader>

        <div className="grid max-h-[50vh] gap-3 overflow-y-auto pr-1">
          {templatesLoading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl border-2 border-border bg-muted" />
            ))
          ) : templates.length === 0 ? (
            <p className="rounded-xl border-2 border-dashed border-border p-6 text-center text-sm text-muted-foreground">
              暂无本课程适用优惠券
            </p>
          ) : (
            templates.map((t) => {
              const received = receivedByTemplate(t.coupon_template_id);
              const isReceived = received.length > 0;
              const isReceiving = receivingId === t.coupon_template_id;
              return (
                <div
                  key={t.coupon_template_id}
                  className={cn(
                    "flex items-center gap-3 rounded-xl border-2 border-candy-orange/40 bg-candy-orange-soft p-3",
                    isReceived && "border-border bg-card",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-candy-orange text-white"
                  >
                    <Ticket className="h-5 w-5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-bold text-foreground">{t.coupon_name}</span>
                      {isReceived && (
                        <span className="inline-flex items-center gap-0.5 rounded-full border border-candy-green/40 bg-candy-green-soft px-1.5 py-0.5 text-3xs font-bold text-candy-green">
                          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                          已领取
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      <b className="font-bold text-candy-orange">
                        {formatAmount(t.face_value, "¥", 0)}
                      </b>{" "}
                      优惠券 · 满 {formatAmount(t.min_spend, "¥", 0)} 可用
                    </span>
                    <span className="mt-0.5 block text-3xs text-muted-foreground">
                      {t.valid_from?.slice(0, 10)} ~ {t.valid_to?.slice(0, 10)}
                    </span>
                  </span>
                  <span className="shrink-0">
                    {isReceived ? (
                      <label className="flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-foreground">
                        <input
                          type="radio"
                          name="use-coupon"
                          aria-label={`抵扣 ${t.coupon_name}`}
                          checked={received.some((c) => c.coupon_id === selectedCouponId)}
                          onChange={() =>
                            onSelectCoupon(
                              selectedCouponId === received[0]?.coupon_id ? null : (received[0]?.coupon_id ?? null),
                            )
                          }
                          className="h-4 w-4 accent-candy-purple"
                        />
                        抵扣
                      </label>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleReceive(t.coupon_template_id)}
                        disabled={isReceiving}
                        className="inline-flex items-center gap-1 rounded-lg border-2 border-border bg-candy-green px-3 py-1.5 text-xs font-bold text-white shadow-[0_2px_0_rgba(31,31,31,0.14)] transition-all hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isReceiving && <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
                        领取
                      </button>
                    )}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
