/**
 * OrdersClient — 我的订单客户端逻辑（Season-2 React，task100）
 *
 * - 保护路由：未登录 → /login?redirect=/orders
 * - 数据来源：契约⑧ GET /api/trade/orders（task17 已实现）+ 订单详情 getOrder（items/payments 嵌套）
 * - Tabs 本地按真实 status 分组：全部／待支付(pending)／已支付(paid+completed+partial_refunded)／已取消+已退款(cancelled+refunded)
 * - 操作：pending 可【取消订单】【去支付】；可退款单可【申请退款】；失败即 toast + console.error，不吞错。
 */
"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  CircleDollarSign,
  CreditCard,
  Loader2,
  RefreshCcw,
  ReceiptText,
  Undo2,
  Wallet,
} from "lucide-react";
import { toast } from "sonner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Pagination } from "@/components/ui/pagination";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { useAuthStore } from "@/lib/auth-client";
import {
  listOrders,
  getOrder,
  cancelOrder,
  type Order,
  type OrderItem,
  type PaymentItem,
} from "@/lib/api/orders";
import { launchPayment, type PayChannel } from "@/lib/api/payments";
import { createRefund, REFUND_TYPE_OPTIONS, type RefundType } from "@/lib/api/refunds";
import { cn } from "@/lib/utils";

type OrderTabId = "all" | "pending" | "paid" | "finished";

const TABS: { id: OrderTabId; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "pending", label: "待支付" },
  { id: "paid", label: "已支付" },
  { id: "finished", label: "已取消 / 已退款" },
];

const TAB_IDS = TABS.map((t) => t.id);

const PAID_STATUSES: Order["status"][] = ["paid", "completed", "partial_refunded"];
const FINISHED_STATUSES: Order["status"][] = ["cancelled", "refunded"];

const PER_PAGE = 8;

const PAY_CHANNEL_OPTIONS: { value: PayChannel; label: string }[] = [
  { value: "wechat_pay", label: "微信支付" },
  { value: "alipay", label: "支付宝" },
  { value: "bank_card", label: "银行卡" },
  { value: "offline_transfer", label: "线下转账" },
  { value: "public_account", label: "对公账户" },
  { value: "campus_cashier", label: "校内收银" },
  { value: "mock", label: "模拟支付（测试）" },
];

export function money(v: number): string {
  return `¥${(Number.isFinite(v) ? v : 0).toFixed(2)}`;
}

/** 2026-08-13T09:12:00 → "2026-08-13 09:12" */
export function fmtTime(s: string | null | undefined): string {
  if (!s) return "-";
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(s);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : s;
}

function inTab(o: Order, tab: OrderTabId): boolean {
  switch (tab) {
    case "pending":
      return o.status === "pending";
    case "paid":
      return PAID_STATUSES.includes(o.status);
    case "finished":
      return FINISHED_STATUSES.includes(o.status);
    case "all":
    default:
      return true;
  }
}

function tabFromUrl(sp: ReturnType<typeof useSearchParams>): OrderTabId {
  const raw = sp.get("tab");
  return isTabId(raw) ? raw : "all";
}

function isTabId(v: string | null): v is OrderTabId {
  return !!v && (TAB_IDS as string[]).includes(v);
}

export default function OrdersClient() {
  const router = useRouter();
  const sp = useSearchParams();
  const ready = useAuthStore((s) => s.ready);
  const token = useAuthStore((s) => s.token);
  const authed = ready && !!token;

  const [page, setPage] = useState(1);
  const [expandedOrderNo, setExpandedOrderNo] = useState<string | null>(null);
  const [payOrder, setPayOrder] = useState<Order | null>(null);
  const [refundOrder, setRefundOrder] = useState<Order | null>(null);
  const [cancelOrderNo, setCancelOrderNo] = useState<string | null>(null);

  const queryClient = useQueryClient();

  /* 保护路径：hydrate 完成后未登录 → 跳 login */
  useEffect(() => {
    if (!ready) return;
    if (authed) return;
    const redirect = encodeURIComponent(window?.location.pathname + (window?.location.search ?? ""));
    router.replace(`/login?redirect=${redirect}`);
  }, [ready, authed, router]);

  const tab: OrderTabId = tabFromUrl(sp);

  /* 单次拉取全部订单（page_size 上限 100），本地按 status 分组 → 计数真实 + 三 tab 可切换 */
  const q = useQuery({
    queryKey: ["orders", "me"],
    queryFn: () => listOrders({ page: 1, page_size: 100 }),
    staleTime: 60_000,
    enabled: !!authed,
  });

  const groups = useMemo(() => {
    const list = q.data?.items ?? [];
    const g: Record<OrderTabId, Order[]> = { all: [], pending: [], paid: [], finished: [] };
    for (const o of list) {
      const added: OrderTabId[] = ["all"];
      if (inTab(o, "pending")) added.push("pending");
      if (inTab(o, "paid")) added.push("paid");
      if (inTab(o, "finished")) added.push("finished");
      for (const id of added) g[id].push(o);
    }
    return g;
  }, [q.data]);

  const badgeCounts = useMemo(
    () => ({
      all: groups.all.length,
      pending: groups.pending.length,
      paid: groups.paid.length,
      finished: groups.finished.length,
    }),
    [groups],
  );

  /* tab 切换时重置分页与展开态 */
  useEffect(() => {
    setPage(1);
    setExpandedOrderNo(null);
  }, [tab]);

  const activeList = groups[tab] ?? [];
  const totalPages = Math.max(1, Math.ceil(activeList.length / PER_PAGE));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const pageView = activeList.slice((safePage - 1) * PER_PAGE, safePage * PER_PAGE);

  const { mutate: runCancel, isPending: cancelPending } = useMutation({
    mutationFn: (orderNo: string) => cancelOrder(orderNo),
    onSuccess: (res) => {
      toast.success("订单已取消", { description: `订单 ${res.order_no} 已取消` });
      setCancelOrderNo(null);
      void queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "取消订单失败";
      console.error("[orders] cancel failed", err);
      toast.error(msg);
    },
  });

  if (!authed) return <AuthRedirectSkeleton />;

  return (
    <div className="space-y-5">
      <Tabs
        value={tab}
        onValueChange={(v) => {
          if (isTabId(v)) router.push(`/orders?tab=${v}`, { scroll: false });
        }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <TabsList variant="line" className="gap-1">
            {TABS.map((t) => (
              <TabsTrigger key={t.id} value={t.id} className="gap-2">
                {t.id === "pending" ? (
                  <Wallet className="h-4 w-4" />
                ) : t.id === "paid" ? (
                  <CircleDollarSign className="h-4 w-4" />
                ) : t.id === "finished" ? (
                  <Undo2 className="h-4 w-4" />
                ) : (
                  <ReceiptText className="h-4 w-4" />
                )}
                {t.label}
                <Badge variant="secondary" className="h-5 px-1.5 py-0 text-4xs">
                  {badgeCounts[t.id]}
                </Badge>
              </TabsTrigger>
            ))}
          </TabsList>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => void q.refetch()}
            disabled={q.isFetching}
          >
            <RefreshCcw className={"mr-1.5 h-4 w-4 " + (q.isFetching ? "animate-spin" : "")} />
            刷新
          </Button>
        </div>

        {q.isError ? (
          <ErrorState
            title="加载我的订单失败"
            message={q.error instanceof Error ? q.error.message : "GET /api/trade/orders 暂不可达"}
            retry={() => q.refetch()}
          />
        ) : q.isLoading ? (
          <GridSkeleton />
        ) : (
          TABS.map((t) => (
            <TabsContent key={t.id} value={t.id}>
              {groups[t.id].length === 0 ? (
                <EmptyState
                  icon={<ReceiptText />}
                  title={
                    t.id === "pending"
                      ? "没有待支付订单"
                      : t.id === "paid"
                        ? "还没有已支付的订单"
                        : t.id === "finished"
                          ? "没有已取消 / 已退款订单"
                          : "还没有订单"
                  }
                  description={
                    t.id === "all"
                      ? "去课程中心挑一门喜欢的课程下单吧"
                      : "订单会按状态分门别类列在这里"
                  }
                  action={
                    t.id === "all" ? (
                      <Button asChild size="sm">
                        <Link href="/courses">去选课 →</Link>
                      </Button>
                    ) : undefined
                  }
                />
              ) : (
                <div className="space-y-3">
                  {pageView.map((o) => (
                    <OrderCard
                      key={o.order_no}
                      order={o}
                      expanded={expandedOrderNo === o.order_no}
                      onToggle={() =>
                        setExpandedOrderNo((cur) => (cur === o.order_no ? null : o.order_no))
                      }
                      onPay={() => setPayOrder(o)}
                      onCancel={() => setCancelOrderNo(o.order_no)}
                      onRefund={() => setRefundOrder(o)}
                    />
                  ))}
                  {activeList.length > PER_PAGE ? (
                    <Pagination
                      page={safePage}
                      pageSize={PER_PAGE}
                      total={activeList.length}
                      onPageChange={setPage}
                    />
                  ) : null}
                </div>
              )}
            </TabsContent>
          ))
        )}
      </Tabs>

      <PayDialog
        order={payOrder}
        onClose={() => setPayOrder(null)}
        onDone={() => void queryClient.invalidateQueries({ queryKey: ["orders"] })}
      />
      <RefundDialog
        order={refundOrder}
        onClose={() => setRefundOrder(null)}
        onSubmitted={() => void queryClient.invalidateQueries({ queryKey: ["orders"] })}
      />
      <ConfirmDialog
        open={!!cancelOrderNo}
        onOpenChange={(open) => {
          if (!open) setCancelOrderNo(null);
        }}
        title="确认取消订单？"
        description={
          cancelOrderNo
            ? `订单 ${cancelOrderNo} 取消后优惠券将退回，库存座位同步释放。该操作不可撤销。`
            : undefined
        }
        confirmText="确认取消"
        loading={cancelPending}
        onConfirm={() => {
          if (cancelOrderNo) runCancel(cancelOrderNo);
        }}
        onCancel={() => setCancelOrderNo(null)}
      />
    </div>
  );
}

/* ─────────────────────────── 订单卡片 + 详情 ─────────────────────────── */

function OrderCard({
  order,
  expanded,
  onToggle,
  onPay,
  onCancel,
  onRefund,
}: {
  order: Order;
  expanded: boolean;
  onToggle: () => void;
  onPay: () => void;
  onCancel: () => void;
  onRefund: () => void;
}) {
  const refundable = PAID_STATUSES.includes(order.status);
  const detail = useQuery({
    queryKey: ["order", order.order_no],
    queryFn: () => getOrder(order.order_no),
    staleTime: 60_000,
    enabled: expanded,
  });

  return (
    <div className="overflow-hidden rounded-2xl border-2 border-foreground/10 bg-card">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3.5">
        <button
          type="button"
          onClick={onToggle}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-deep/10 to-primary/10 text-primary-deep">
            <ReceiptText className="h-4.5 w-4.5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-foreground">
              {order.series_title || "课程订单"}
            </p>
            <p className="mt-0.5 truncate font-mono text-3xs text-muted-foreground">
              {order.order_no}
            </p>
          </div>
          <ChevronDown
            className={cn(
              "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
              expanded && "rotate-180",
            )}
          />
        </button>

        <span className="text-sm font-bold tabular-nums text-foreground">{money(order.pay_amount)}</span>
        <StatusBadge map="order_status" status={order.status} />

        <div className="flex flex-wrap items-center gap-1.5">
          {order.status === "pending" ? (
            <>
              <Button size="sm" variant="default" onClick={onPay}>
                <CreditCard className="mr-1 h-3.5 w-3.5" />
                去支付
              </Button>
              <Button size="sm" variant="ghost" onClick={onCancel}>
                取消订单
              </Button>
            </>
          ) : refundable ? (
            <Button size="sm" variant="ghost" onClick={onRefund}>
              申请退款
            </Button>
          ) : null}
        </div>
      </div>

      {expanded ? (
        <div className="border-t border-foreground/10 px-4 py-3">
          {detail.isLoading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              加载订单详情…
            </div>
          ) : detail.isError ? (
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-destructive">
                订单详情加载失败：{detail.error instanceof Error ? detail.error.message : "未知错误"}
              </p>
              <Button size="xs" variant="outline" onClick={() => void detail.refetch()}>
                重试
              </Button>
            </div>
          ) : detail.data ? (
            <OrderDetailBody data={detail.data} onMutated={() => void detail.refetch()} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** isError 分支 detail.data 为 null，这里只渲染非空详情 */
function OrderDetailBody({
  data,
  onMutated,
}: {
  data: Order;
  onMutated: () => void;
}) {
  void onMutated;
  return (
    <div className="space-y-3 text-xs">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-4">
        <Field label="下单时间" value={fmtTime(data.created_at)} />
        <Field label="原价" value={money(data.order_amount)} />
        <Field label="优惠" value={`-${money(data.discount_amount)}`} />
        <Field label="实付" value={money(data.pay_amount)} />
        {data.paid_at ? <Field label="支付时间" value={fmtTime(data.paid_at)} /> : null}
        {data.cancelled_at ? <Field label="取消时间" value={fmtTime(data.cancelled_at)} /> : null}
      </div>

      {data.items.length > 0 ? (
        <section>
          <h3 className="mb-1.5 font-semibold text-foreground">订单明细</h3>
          <ul className="space-y-1 rounded-xl border border-foreground/10 p-3">
            {data.items.map((it) => (
              <OrderItemRow key={it.order_item_id} item={it} />
            ))}
          </ul>
        </section>
      ) : null}

      {data.payments.length > 0 ? (
        <section>
          <h3 className="mb-1.5 font-semibold text-foreground">支付记录</h3>
          <ul className="space-y-1 rounded-xl border border-foreground/10 p-3">
            {data.payments.map((pm) => (
              <PaymentRow key={pm.payment_no} payment={pm} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground">{label}</p>
      <p className="font-mono tabular-nums text-foreground">{value}</p>
    </div>
  );
}

function OrderItemRow({ item }: { item: OrderItem }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2">
      <span className="font-semibold text-foreground">{item.item_name}</span>
      <span className="flex items-center gap-3">
        <StatusBadge map="order_item_status" status={item.order_item_status} />
        <span className="font-mono tabular-nums text-muted-foreground">
          {money(item.unit_price)}
          {item.discount_amount > 0 ? ` - ${money(item.discount_amount)}` : ""}
        </span>
        <span className="font-mono font-bold tabular-nums text-foreground">
          {money(item.payable_amount)}
        </span>
      </span>
    </li>
  );
}

function PaymentRow({ payment }: { payment: PaymentItem }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2">
      <span className="font-mono text-muted-foreground">{payment.payment_no}</span>
      <span className="flex items-center gap-3">
        <span className="capitalize text-foreground/70">{payment.payment_channel.replaceAll("_", " ")}</span>
        <StatusBadge map="payment_status" status={payment.payment_status} />
        <span className="font-mono font-bold tabular-nums text-foreground">{money(payment.amount)}</span>
        <span className="text-muted-foreground">{fmtTime(payment.paid_at)}</span>
      </span>
    </li>
  );
}

/* ─────────────────────────── 去支付 弹窗 ─────────────────────────── */

function PayDialog({
  order,
  onClose,
  onDone,
}: {
  order: Order | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const [channel, setChannel] = useState<PayChannel | null>("mock");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (order) setChannel("mock");
  }, [order]);

  const submit = () => {
    if (!order || !channel) return;
    setSubmitting(true);
    launchPayment(order.order_no, { pay_channel: channel })
      .then((res) => {
        console.log("[orders] payment launched", res);
        if (res.audit_pending) {
          toast.success("线下转账，到账审核中", {
            description: "到账审核通过后，订单会自动更新为已支付。",
          });
        } else if (res.pay_url) {
          toast.success("支付发起成功，请完成付款", { description: res.pay_url });
          window.open(res.pay_url, "_blank", "noopener,noreferrer");
        } else {
          toast.success("支付发起成功", {
            description: "请在支付渠道完成付款，稍后刷新查看订单状态。",
          });
        }
        onDone();
        onClose();
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "发起支付失败";
        console.error("[orders] launch payment failed", err);
        toast.error(msg);
      })
      .finally(() => setSubmitting(false));
  };

  return (
    <Dialog open={!!order} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>选择支付方式</DialogTitle>
          <DialogDescription>
            {order ? `订单 ${order.order_no} · 应付 ${money(order.pay_amount)}` : ""}
          </DialogDescription>
        </DialogHeader>
        <Select
          label="支付渠道"
          options={PAY_CHANNEL_OPTIONS}
          value={channel}
          onValueChange={(v) => setChannel(v as PayChannel | null)}
          placeholder="请选择支付渠道"
          required
        />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={!channel || submitting}>
            <CreditCard className="mr-1 h-4 w-4" />
            去支付
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ─────────────────────────── 申请退款 弹窗 ─────────────────────────── */

function RefundDialog({
  order,
  onClose,
  onSubmitted,
}: {
  order: Order | null;
  onClose: () => void;
  onSubmitted: () => void;
}) {
  const [refundType, setRefundType] = useState<string | null>("personal_reason");
  const [applyAmount, setApplyAmount] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (order) {
      setRefundType("personal_reason");
      setApplyAmount(order.pay_amount > 0 ? String(order.pay_amount) : "");
      setReason("");
      setErr(null);
    }
  }, [order]);

  const amountNum = Number(applyAmount);

  const submit = () => {
    if (!order) return;
    const t = refundType as RefundType | null;
    if (!t) {
      setErr("请选择退款类型");
      return;
    }
    if (!reason.trim()) {
      setErr("请填写退款原因");
      return;
    }
    if (!Number.isFinite(amountNum) || amountNum <= 0) {
      setErr("请输入有效的退款金额");
      return;
    }
    if (amountNum > order.pay_amount) {
      setErr(`退款金额不能超过实付金额 ${money(order.pay_amount)}`);
      return;
    }
    setSubmitting(true);
    createRefund({ order_no: order.order_no, refund_type: t, apply_amount: amountNum, reason: reason.trim() })
      .then(() => {
        toast.success("退款申请已提交", { description: "我们会尽快审核你的退款申请。" });
        onSubmitted();
        onClose();
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "提交退款失败";
        console.error("[orders] create refund failed", e);
        setErr(msg);
      })
      .finally(() => setSubmitting(false));
  };

  return (
    <Dialog open={!!order} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>申请退款</DialogTitle>
          <DialogDescription>
            {order ? `订单 ${order.order_no} · 实付 ${money(order.pay_amount)}` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Select
            label="退款类型"
            options={REFUND_TYPE_OPTIONS}
            value={refundType}
            onValueChange={(v) => setRefundType(v)}
            placeholder="请选择退款类型"
            required
          />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="refund-amount" className="text-xs font-medium text-foreground">
              退款金额（元）
            </label>
            <Input
              id="refund-amount"
              type="number"
              min="0.01"
              step="0.01"
              value={applyAmount}
              onChange={(e) => setApplyAmount(e.target.value)}
              placeholder="申请退款金额，须不超过实付金额"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="refund-reason" className="text-xs font-medium text-foreground">
              退款原因
            </label>
            <Textarea
              id="refund-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="请说明退款原因"
            />
          </div>
          {err ? <p className="text-xs text-destructive">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button variant="destructive" onClick={submit} disabled={submitting}>
            提交申请
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AuthRedirectSkeleton() {
  return (
    <div className="rounded-xl border border-dashed border-border p-10 text-center">
      <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-primary" />
      <div className="text-base font-semibold text-foreground">正在跳转登录…</div>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        「我的订单」需要登录后才能查看你的全部订单。
      </p>
    </div>
  );
}

function GridSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-16 animate-pulse rounded-2xl border-2 border-foreground/10 bg-card" />
      ))}
    </div>
  );
}