/**
 * TicketsClient — 我的工单客户端逻辑（Season-2 React，task100）
 *
 * - 保护路由：未登录 → /login?redirect=/tickets
 * - 数据来源：契约⑫ GET /api/trade/after_sales/tickets（task22 已实现）
 * - 列表（分页）+ 状态筛选 + 【新建工单】→ 创建成功刷新并跳转详情
 * - 失败即 toast + console.error，不吞错。
 */
"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, RefreshCcw, Ticket } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import {
  createTicket,
  listMyTickets,
  type Ticket as TicketDTO,
  type TicketStatus,
  type TicketType,
} from "@/lib/api/tickets";
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
import { useAuthStore } from "@/lib/auth-client";

/** 2026-08-13T09:12:00 → "2026-08-13 09:12" */
function fmtCn(s: string | null | undefined): string {
  if (!s) return "-";
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(s);
  return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : s;
}

const TICKET_TYPE_OPTIONS: { value: TicketType; label: string }[] = [
  { value: "consult", label: "咨询" },
  { value: "appeal", label: "人工申诉" },
  { value: "refund", label: "退款" },
  { value: "other", label: "其他" },
];

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "全部状态" },
  { value: "open", label: "待受理" },
  { value: "processing", label: "处理中" },
  { value: "resolved", label: "已解决" },
  { value: "closed", label: "已关闭" },
];

const PAGE_SIZE = 10;

const TICKET_STATUS_SET: TicketStatus[] = ["open", "processing", "resolved", "closed"];

export default function TicketsClient() {
  const router = useRouter();
  const sp = useSearchParams();
  const ready = useAuthStore((s) => s.ready);
  const token = useAuthStore((s) => s.token);
  const authed = ready && !!token;

  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<string>("");
  const [createOpen, setCreateOpen] = useState(false);

  /* 保护路径：hydrate 完成后未登录 → 跳 login */
  useEffect(() => {
    if (!ready) return;
    if (authed) return;
    const redirect = encodeURIComponent(window?.location.pathname + (window?.location.search ?? ""));
    router.replace(`/login?redirect=${redirect}`);
  }, [ready, authed, router]);

  const statusParam: TicketStatus | undefined = status
    ? (TICKET_STATUS_SET.includes(status as TicketStatus) ? (status as TicketStatus) : undefined)
    : undefined;

  const q = useQuery({
    queryKey: ["tickets", "me", statusParam, page],
    queryFn: () =>
      listMyTickets({
        ...(statusParam ? { status: statusParam } : {}),
        page,
        page_size: PAGE_SIZE,
      }),
    staleTime: 30_000,
    enabled: !!authed,
  });

  const { mutate: runCreate, isPending: createPending } = useMutation({
    mutationFn: createTicket,
    onSuccess: (ticket) => {
      toast.success("工单已创建", { description: ticket.ticket_no || "已提交，等待受理" });
      setCreateOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["tickets"] });
      router.push(`/tickets/${ticket.ticket_id}`);
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "创建工单失败";
      console.error("[tickets] create failed", err);
      toast.error(msg);
    },
  });

  useEffect(() => {
    setPage(1);
  }, [status]);

  const data = q.data;

  if (!authed) return <AuthRedirectSkeleton />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Select
            options={STATUS_OPTIONS}
            value={status || ""}
            onValueChange={(v) => setStatus(v ?? "")}
            placeholder="全部状态"
            className="w-36"
          />
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void q.refetch()}
            disabled={q.isFetching}
          >
            <RefreshCcw className={"mr-1.5 h-4 w-4 " + (q.isFetching ? "animate-spin" : "")} />
            刷新
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" />
            新建工单
          </Button>
        </div>
      </div>

      {q.isError ? (
        <ErrorState
          title="加载我的工单失败"
          message={q.error instanceof Error ? q.error.message : "GET /api/trade/after_sales/tickets 暂不可达"}
          retry={() => q.refetch()}
        />
      ) : q.isLoading ? (
        <ListSkeleton />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon={<Ticket />}
          title={statusParam ? "该状态下还没有工单" : "还没有工单"}
          description="遇到课程、订单或账号问题，可以随时提交工单寻求人工协助"
          action={
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-1 h-4 w-4" />
              新建工单
            </Button>
          }
        />
      ) : (
        <div className="space-y-3">
          {data.items.map((t) => (
            <TicketRow key={t.ticket_id} ticket={t} />
          ))}
          <Pagination
            page={data.page > Math.max(1, Math.ceil(data.total / data.page_size))
              ? Math.max(1, Math.ceil(data.total / data.page_size))
              : data.page}
            pageSize={data.page_size}
            total={data.total}
            onPageChange={setPage}
          />
        </div>
      )}

      <CreateTicketDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onConfirm={(input) => runCreate(input)}
        submitting={createPending}
      />
    </div>
  );
}

function TicketRow({ ticket }: { ticket: TicketDTO }) {
  const typeLabel = TICKET_TYPE_OPTIONS.find((t) => t.value === ticket.ticket_type)?.label ?? ticket.ticket_type;
  return (
    <Link
      href={`/tickets/${ticket.ticket_id}`}
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border-2 border-foreground/10 bg-card px-4 py-3.5 transition-colors hover:border-primary/40 hover:bg-muted/40"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary-deep/10 to-primary/10 text-primary-deep">
        <Ticket className="h-4.5 w-4.5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-foreground">{ticket.title}</p>
        <p className="mt-0.5 text-3xs text-muted-foreground">
          {typeLabel}
          {ticket.order_no ? ` · 关联订单 ${ticket.order_no}` : ""} · {fmtCn(ticket.created_at)}
        </p>
      </div>
      <StatusBadge map="ticket_status" status={ticket.status} />
      <Badge variant="secondary" className="shrink-0">
        {typeLabel}
      </Badge>
    </Link>
  );
}

function CreateTicketDialog({
  open,
  onOpenChange,
  onConfirm,
  submitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (input: { ticket_type: TicketType; title: string; content: string; order_no?: string }) => void;
  submitting: boolean;
}) {
  const [ticketType, setTicketType] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [orderNo, setOrderNo] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setTicketType(null);
      setTitle("");
      setContent("");
      setOrderNo("");
      setErr(null);
    }
  }, [open]);

  const submit = () => {
    const t = ticketType as TicketType | null;
    if (!t) {
      setErr("请选择工单类型");
      return;
    }
    if (!title.trim()) {
      setErr("请填写标题");
      return;
    }
    if (!content.trim()) {
      setErr("请填写问题描述");
      return;
    }
    onConfirm({
      ticket_type: t,
      title: title.trim(),
      content: content.trim(),
      ...(orderNo.trim() ? { order_no: orderNo.trim() } : {}),
    });
    setErr(null);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建工单</DialogTitle>
          <DialogDescription>提交咨询、申诉或售后问题，我们尽快受理。</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Select
            label="工单类型"
            options={TICKET_TYPE_OPTIONS}
            value={ticketType}
            onValueChange={(v) => setTicketType(v)}
            placeholder="请选择工单类型"
            required
          />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ticket-title" className="text-xs font-medium text-foreground">
              标题
            </label>
            <Input
              id="ticket-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="一句话概括你的问题"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ticket-content" className="text-xs font-medium text-foreground">
              问题描述
            </label>
            <Textarea
              id="ticket-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="请详细描述遇到的问题"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ticket-order" className="text-xs font-medium text-foreground">
              关联订单号（可选）
            </label>
            <Input
              id="ticket-order"
              value={orderNo}
              onChange={(e) => setOrderNo(e.target.value)}
              placeholder="如有订单问题可填写订单号"
            />
          </div>
          {err ? <p className="text-xs text-destructive">{err}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={submit} disabled={submitting}>
            提交工单
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
        「我的工单」需要登录后才能查看你的咨询与售后工单。
      </p>
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-14 animate-pulse rounded-2xl border-2 border-foreground/10 bg-card" />
      ))}
    </div>
  );
}