/**
 * ChatFloatingButton — 全局浮动 AI 助手入口按钮
 *  - 右下角 fixed 定位（z-40，避免遮挡 toast 的 z-50）
 *  - 开启状态旋转 MessageCircleSquare → X；关闭状态圆形按钮 + Sparkles 徽标
 *  - badge：未读新消息计数（由父组件 ChatPanel 通过 context/prop 注入）
 *  - 未登录时 disabled 且显示登录提示 tooltip
 */
"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { MessageCircle, Sparkles, X, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/auth-client";

export interface ChatFloatingButtonProps {
  /** 受控展开状态 */
  open: boolean;
  onToggle: () => void;
  /** 未读消息计数（>0 展示徽标） */
  unreadCount?: number;
  /** 底部偏移（适配移动端 tab 栏 / 固定 footer） */
  bottomOffset?: number;
  rightOffset?: number;
  className?: string;
}

export function ChatFloatingButton({
  open,
  onToggle,
  unreadCount = 0,
  bottomOffset = 24,
  rightOffset = 24,
  className,
}: ChatFloatingButtonProps) {
  const router = useRouter();
  const authed = useAuthStore((s) => s.ready && s.isAuthenticated());
  const [tipOpen, setTipOpen] = React.useState(false);

  const handleClick = () => {
    if (!authed) {
      // 弹登录提示 tooltip 3 秒，同时跳 /login
      setTipOpen(true);
      window.setTimeout(() => setTipOpen(false), 2600);
      const current = encodeURIComponent(window?.location?.pathname ?? "/dashboard");
      router.push(`/login?redirect=${current}`);
      return;
    }
    onToggle();
  };

  const badgeValue =
    typeof unreadCount === "number" && unreadCount > 99 ? "99+" :
    (unreadCount ?? 0) > 0 ? String(unreadCount) : null;

  return (
    <div
      className={cn(
        "fixed z-40",
        className,
      )}
      style={{ bottom: bottomOffset, right: rightOffset }}
    >
      <div className="relative">
        {/* 未登录 tooltip */}
        <div
          role="status"
          aria-live="polite"
          className={cn(
            "pointer-events-none absolute bottom-full right-0 mb-3 whitespace-nowrap rounded-lg border border-border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md transition-all duration-200",
            tipOpen ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2",
          )}
        >
          <span className="inline-flex items-center gap-1.5">
            <LogIn className="h-3 w-3 text-primary" />
            请先登录后使用 AI 助手
          </span>
          <div className="absolute right-6 -bottom-1 h-2 w-2 rotate-45 border-b border-r border-border bg-popover" />
        </div>

        <Button
          variant="default"
          size="icon-lg"
          onClick={handleClick}
          aria-label={open ? "关闭 AI 助手面板" : "打开 AI 助手"}
          aria-expanded={open}
          className={cn(
            "size-14 rounded-full shadow-lg shadow-primary/20 transition-all duration-300",
            open ? "bg-muted hover:bg-muted text-foreground scale-95 rotate-90" : "hover:scale-105",
            !authed && "opacity-70 cursor-not-allowed grayscale-[0.4]",
          )}
        >
          {open ? (
            <X className="size-6" aria-hidden />
          ) : (
            <MessageCircle className="size-6" aria-hidden />
          )}

          {/* 徽标：关闭状态有未读才展示（未读 = warning 状态保留） */}
          {!open && badgeValue && (
            <Badge
              variant="destructive"
              data-slot="floating-badge"
              className="absolute -right-1 -top-1 h-5 min-w-5 px-1 text-4xs font-bold shadow bg-warning-foreground text-white"
            >
              {badgeValue}
            </Badge>
          )}
          {/* 关闭状态展示 sparkles 角标（产品化识别） */}
          {!open && !badgeValue && (
            <span className="absolute -right-0.5 -top-0.5 inline-flex size-4 items-center justify-center rounded-full bg-warning-foreground text-white shadow">
              <Sparkles className="size-2.5" aria-hidden />
            </span>
          )}
        </Button>

        {/* 波纹动画（未启用时轻提示这是交互按钮） */}
        {!open && authed && (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 rounded-full bg-primary/30 animate-ping opacity-40"
          />
        )}
      </div>
    </div>
  );
}

export default ChatFloatingButton;
