/**
 * 功能入口 7 行 NavListItem（task54 me，J20 跳转表）：
 * /orders /coupons /favorites /my-courses /refunds /tickets /practice/wrong-book。
 * 纯静态展示（无数据请求），hover 反馈，ChevronRight 引导。
 */
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  Receipt,
  Ticket,
  Star,
  BookOpen,
  Undo2,
  LifeBuoy,
  NotebookPen,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavEntry {
  href: string;
  title: string;
  desc: string;
  Icon: LucideIcon;
  tone: string;
}

const ENTRIES: NavEntry[] = [
  { href: "/orders", title: "我的订单", desc: "查看 / 支付 / 管理订单 · J6 去支付", Icon: Receipt, tone: "bg-candy-yellow/25" },
  { href: "/coupons", title: "我的优惠券", desc: "失效 / 可用的购课优惠券", Icon: Ticket, tone: "bg-candy-green-soft" },
  { href: "/favorites", title: "我的收藏", desc: "收藏的课程，快速回到心仪内容", Icon: Star, tone: "bg-candy-blue-soft" },
  { href: "/my-courses", title: "我的班次", desc: "已报名课程 · 继续学习 / 售后 · J14/J15/J16", Icon: BookOpen, tone: "bg-candy-blue-soft" },
  { href: "/refunds", title: "退款记录", desc: "退款申请状态与进度", Icon: Undo2, tone: "bg-candy-orange-soft" },
  { href: "/tickets", title: "售后工单", desc: "工单 / 人工申诉跟进", Icon: LifeBuoy, tone: "bg-candy-pink/25" },
  { href: "/practice/wrong-book", title: "错题本", desc: "专项练习 · 错题复习与解析", Icon: NotebookPen, tone: "bg-candy-yellow/25" },
];

export function MeNavList({ labelledby }: { labelledby?: string }) {
  return (
    <div
      aria-labelledby={labelledby}
      className="overflow-hidden rounded-2xl border-[3px] border-foreground bg-white shadow-[0_4px_0_rgba(31,31,31,0.14)]"
    >
      {ENTRIES.map(({ href, title, desc, Icon, tone }, i) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "flex items-center gap-3.5 px-4 py-3.5 transition-colors hover:bg-candy-bg",
            i > 0 && "border-t-2 border-dashed border-foreground/10",
          )}
        >
          <span
            className={cn(
              "grid h-9 w-9 shrink-0 place-items-center rounded-xl border-[2px] border-foreground",
              tone,
            )}
            aria-hidden="true"
          >
            <Icon className="h-4.5 w-4.5 text-foreground" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-bold text-foreground">{title}</span>
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">{desc}</span>
          </span>
          <span
            className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border-[2px] border-foreground bg-candy-bg text-foreground"
            aria-hidden="true"
          >
            <ChevronRight className="h-4 w-4" />
          </span>
        </Link>
      ))}
    </div>
  );
}