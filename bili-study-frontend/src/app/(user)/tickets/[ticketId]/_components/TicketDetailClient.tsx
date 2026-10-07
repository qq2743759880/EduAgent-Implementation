/**
 * TicketDetailClient — 工单详情客户端逻辑（Season-2 React，task100）
 *
 * - 保护路由：未登录 → /login?redirect=/tickets/{id}
 * - 数据来源：契约⑫ GET /api/trade/after_sales/ticket/{ticket_id}（task22 已实现，越权 404）
 * - 显示 reply；已 resolved/closed 且未评分 → 满意度评价（1-5 星 + 可选 comment）
 * - 失败即 toast + console.error，不吞错。
 */
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Loader2, MessageCircleReply, Star } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Textarea } from "@/components/ui/textarea";
import { getTicket, submitTicketSatisfaction, type Ticket, type TicketType } from "@/lib/api/tickets";
import { useAuthStore } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

const TICKET_TYPE_TEXT: Record<TicketType, string> = {
  consult: "咨询",
  appeal: "人工申诉",
  refund: "退款",
  other: "其他",
};

function fmtCn(s: string | null | undefined): string {
  if (!s) return "-";
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(s);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : s;
}

export default function TicketDetailClient({ ticketId }: { ticketId: number }) {
  const router = useRouter();
  const ready = useAuthStore((s) => s.ready);
  const token = useAuthStore((s) => s.token);
  const authed = ready && !!token;

  const queryClient = useQueryClient();

  useEffect(() => {
    if (!ready) return;
    if (authed) return;
    const redirect = encodeURIComponent(`/tickets/${ticketId}`);
    router.replace(`/login?redirect=${redirect}`);
  }, [ready, authed, ticketId, router]);

  const q = useQuery({
    queryKey: ["ticket", ticketId],
    queryFn: () => getTicket(ticketId),
    staleTime: 30_000,
    enabled: authed && ticketId > 0,
  });

  if (!authed) {
    return (
      <div className="rounded-xl border border-dashed border-border p-10 text-center">
        <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-primary" />
        <div className="text-sm text-muted-foreground">正在跳转登录…</div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5">
      <Link
        href="/tickets"
        className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="h-4 w-4" />
        返回工单列表
      </Link>

      {q.isError ? (
        <ErrorState
          title="加载工单失败"
          message={q.error instanceof Error ? q.error.message : "GET /api/trade/after_sales/ticket 暂不可达"}
          retry={() => q.refetch()}
        />
      ) : q.isLoading ? (
        <div className="flex h-64 items-center justify-center text-sm text-foreground/60">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          加载工单详情…
        </div>
      ) : q.data ? (
        <TicketDetailBody ticket={q.data} onMutated={() => q.refetch()} />
      ) : null}
    </div>
  );
}

function TicketDetailBody({
  ticket,
  onMutated,
}: {
  ticket: Ticket;
  onMutated: () => void;
}) {
  const satScore = ticket.satisfaction_score;
  const awaitingReview =
    (ticket.status === "resolved" || ticket.status === "closed") && satScore === null;

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border-2 border-foreground/10 bg-card p-5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge map="ticket_status" status={ticket.status} />
          <span className="rounded-full bg-muted px-2 py-0.5 text-3xs font-medium text-muted-foreground">
            {TICKET_TYPE_TEXT[ticket.ticket_type] ?? ticket.ticket_type}
          </span>
          {ticket.order_no ? (
            <span className="font-mono text-3xs text-muted-foreground">关联订单 {ticket.order_no}</span>
          ) : null}
        </div>
        <h1 className="mt-2 text-lg font-bold text-foreground">{ticket.title}</h1>
        <p className="mt-1 text-3xs text-muted-foreground">
          #{ticket.ticket_no} · 创建于 {fmtCn(ticket.created_at)}
        </p>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-foreground/80">
          {ticket.content}
        </p>
      </section>

      {ticket.reply ? (
        <section className="rounded-2xl border-2 border-primary/20 bg-primary/5 p-5">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-primary-deep">
            <MessageCircleReply className="h-4 w-4" />
            客服回复
          </p>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/85">{ticket.reply}</p>
          <p className="mt-2 text-3xs text-muted-foreground">回复时间 {fmtCn(ticket.updated_at)}</p>
        </section>
      ) : (
        <EmptyState
          icon={<MessageCircleReply />}
          title="等待受理中"
          description="客服尚未回复，请耐心等待；处理后本页会实时展示回复。"
        />
      )}

      {awaitingReview ? (
        <SatisfactionForm ticketId={ticket.ticket_id} onSubmitted={onMutated} />
      ) : satScore ? (
        <section className="rounded-2xl border-2 border-foreground/10 bg-card p-5">
          <p className="text-xs font-semibold text-foreground">你的满意度评价</p>
          <div className="mt-2 flex items-center gap-1" aria-label={`评分 ${satScore} 星`}>
            {Array.from({ length: 5 }).map((_, i) => (
              <Star
                key={i}
                className={cn(
                  "h-5 w-5",
                  i < satScore
                    ? "fill-amber-400 text-amber-400"
                    : "text-muted-foreground/30",
                )}
              />
            ))}
          </div>
          {ticket.satisfaction_comment ? (
            <p className="mt-2 text-sm text-foreground/75">{ticket.satisfaction_comment}</p>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function SatisfactionForm({
  ticketId,
  onSubmitted,
}: {
  ticketId: number;
  onSubmitted: () => void;
}) {
  const queryClient = useQueryClient();
  const [score, setScore] = useState(0);
  const [hover, setHover] = useState(0);
  const [comment, setComment] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const { mutate: runSubmit, isPending } = useMutation({
    mutationFn: (input: { satisfaction_score: number; satisfaction_comment?: string }) =>
      submitTicketSatisfaction(ticketId, input),
    onSuccess: () => {
      toast.success("感谢你的评价");
      setErr(null);
      void queryClient.invalidateQueries({ queryKey: ["ticket", ticketId] });
      onSubmitted();
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : "提交评价失败";
      console.error("[tickets] satisfaction failed", e);
      setErr(msg);
    },
  });

  const submit = () => {
    if (score < 1) {
      setErr("请选择 1-5 星评分");
      return;
    }
    runSubmit({ satisfaction_score: score, ...(comment.trim() ? { satisfaction_comment: comment.trim() } : {}) });
  };

  return (
    <section className="rounded-2xl border-2 border-amber-300/40 bg-card p-5">
      <p className="text-sm font-semibold text-foreground">本次服务满意吗？</p>
      <p className="mt-0.5 text-xs text-muted-foreground">请为本次工单处理评分（1-5 星）</p>
      <div
        className="mt-3 flex items-center gap-1"
        onMouseLeave={() => setHover(0)}
        role="radiogroup"
        aria-label="满意度评分"
      >
        {Array.from({ length: 5 }).map((_, i) => {
          const n = i + 1;
          const active = (hover || score) >= n;
          return (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={score === n}
              aria-label={`${n} 星`}
              className="rounded p-0.5 transition-transform hover:scale-110"
              onMouseEnter={() => setHover(n)}
              onClick={() => setScore(n)}
            >
              <Star
                className={cn(
                  "h-6 w-6",
                  active ? "fill-amber-400 text-amber-400" : "text-muted-foreground/30",
                )}
              />
            </button>
          );
        })}
      </div>
      <div className="mt-3 flex flex-col gap-1.5">
        <label htmlFor="satisfaction-comment" className="text-xs font-medium text-foreground">
          评价（可选）
        </label>
        <Textarea
          id="satisfaction-comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="说说你对本次处理服务的看法"
        />
      </div>
      {err ? <p className="mt-2 text-xs text-destructive">{err}</p> : null}
      <div className="mt-3">
        <Button onClick={submit} disabled={isPending}>
          提交评价
        </Button>
      </div>
    </section>
  );
}