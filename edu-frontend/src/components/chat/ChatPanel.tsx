/**
 * ChatPanel —— AI 问答主面板（浮动模式 / 全屏模式共用）
 *
 * - 两种展示：floating=true（右下角 380×560 卡片）/ floating=false（由外部容器接管尺寸，用于全屏聊天页 center 栏）
 * - 依赖注入 props（受控，便于外部 GlobalChatInjection 和 ChatFullScreenClient 复用同一份会话流）：
 *     { open, onClose, isFloating, selectedSessionId, onRequestSessionsPanel, messages, isStreaming, onSend, onStop, onNewSession, userNickname, userAvatar, unreadSourcesDot, compactSources }
 * - 底部输入框：textarea + Enter 发送（Shift+Enter 换行）+ Send 按钮 + isStreaming 时显示 Stop 按钮
 * - 消息自动滚到底（scrollRef + useEffect 监听 messages.length / isStreaming / assistant 最后一条增量内容）
 * - assistant 消息下挂 SourceCardList + ToolCallList（两条在 msg 内部 div，保持视觉锚定）
 * - 顶部 Header：AI 品牌头像/标题/当前会话名/侧边栏按钮（onRequestSessionsPanel）/关闭按钮（floating 模式展示）/全屏跳转 / 新对话
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  ArrowUpRight,
  Bot,
  Maximize2,
  MessageSquarePlus,
  PanelLeftClose,
  Send,
  Sparkles,
  Square,
  X,
  CornerDownLeft,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/auth-client";
import type { ChatMessage, ChatSession } from "@/lib/api/chat";
import { NewMessageSchema } from "@/lib/validators/chat-schemas";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { SourceCardList } from "./SourceCardList";
import { ToolCallList } from "./ToolCallVisualizer";

/* ================= 类型 ================= */

export interface ChatPanelHandle {
  focusInput: () => void;
}

export interface ChatPanelProps {
  /** floating 模式：右上角关闭按钮 + 固定尺寸（380×560 + 最大 h-[80vh]）+ 右下角阴影卡片 */
  floating?: boolean;
  /** 受控显示（floating 模式使用；fullscreen 模式下可忽略） */
  open?: boolean;
  /** 关闭回调（floating） */
  onClose?: () => void;
  /** 点击侧栏按钮的回调（floating 下通常打开抽屉；fullscreen 下通常切换 left 栏状态） */
  onRequestSessionsPanel?: () => void;
  /** 当前选中会话（用于 header 显示标题 + new 时清空） */
  session?: ChatSession | null;
  /** 消息列表 */
  messages: ChatMessage[];
  /** 正在生成中 */
  isStreaming: boolean;
  /** 发送一条消息（纯文本，已做 schema 校验）；返回 false 代表校验失败 */
  onSend: (text: string) => void | Promise<void>;
  /** 停止当前生成 */
  onStop: () => void;
  /** 新对话按钮回调 */
  onNewSession: () => void | Promise<void>;
  /** 用户昵称 / 头像（传向 ChatMessageBubble） */
  userNickname?: string;
  userAvatar?: string | null;
  /** sources 紧凑 mode（floating 下 compact=true） */
  compactSources?: boolean;
  className?: string;
  /** 禁用/隐藏会话侧栏按钮 */
  hideSessionsButton?: boolean;
  /** side 栏是否已展开（全屏中心栏 header 使用） */
  sessionsPanelOpen?: boolean;
  /** 外层 wrapper style，用于全屏聊天中心栏贴 padding */
  style?: React.CSSProperties;
  /** 外部 ref 获取 focusInput 等句柄 */
  panelRef?: React.Ref<ChatPanelHandle>;
}

const MAX_LEN = 4000;

/* ================= 组件 ================= */

export const ChatPanel = React.forwardRef<HTMLDivElement, ChatPanelProps>(function ChatPanel(
  props,
  ref,
) {
  const {
    floating = false,
    open: _open,
    onClose,
    onRequestSessionsPanel,
    session,
    messages,
    isStreaming,
    onSend,
    onStop,
    onNewSession,
    userNickname,
    userAvatar,
    compactSources,
    className,
    hideSessionsButton = false,
    sessionsPanelOpen,
    style,
    panelRef,
  } = props;
  void sessionsPanelOpen;

  // 修复: isAuthenticated() 内部调用 get()，Zustand selector 无法追踪其依赖
  // 改为直接访问 s.ready && s.token，确保 token 变化时组件正确重渲染
  const authed = useAuthStore((s) => s.ready && !!s.token);

  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [draft, setDraft] = React.useState("");
  const [draftErr, setDraftErr] = React.useState<string | null>(null);
  const [sending, setSending] = React.useState(false);

  /* ---------- ref 暴露 focusInput ---------- */
  React.useImperativeHandle(
    panelRef,
    () => ({
      focusInput: () => {
        textareaRef.current?.focus({ preventScroll: true });
      },
    }),
    [],
  );

  /* ---------- 自动滚动到底 ---------- */
  React.useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages.length, isStreaming, draft]);

  /* ---------- textarea 自适应高度 ---------- */
  const adjustHeight = React.useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    const maxH = floating ? 140 : 200;
    ta.style.height = Math.min(ta.scrollHeight, maxH) + "px";
  }, [floating]);

  React.useEffect(adjustHeight, [draft, adjustHeight]);

  /* ---------- 提交 ---------- */
  const submit = React.useCallback(async () => {
    if (!authed) {
      toast.error("请先登录后使用 AI 助手");
      return;
    }
    if (sending || isStreaming) return;
    const parsed = NewMessageSchema.safeParse(draft);
    if (!parsed.success) {
      const first = parsed.error.issues[0];
      setDraftErr(first ? first.message : "内容不符合要求");
      return;
    }
    setDraftErr(null);
    const val = parsed.data;
    setSending(true);
    try {
      await onSend(val);
      setDraft("");
    } catch (e) {
      toast.error("发送失败", { description: e instanceof Error ? e.message : undefined });
    } finally {
      setSending(false);
      // 等 setState 生效后再调高度
      window.requestAnimationFrame(adjustHeight);
    }
  }, [authed, sending, isStreaming, draft, onSend, adjustHeight]);

  /* ---------- 键盘：Enter=发送 / Shift+Enter=换行 ---------- */
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  };

  const charsLeft = MAX_LEN - [...draft].length;
  const nearLimit = charsLeft < 200;

  /* ---------- header 标题 ---------- */
  const sessionTitle =
    session?.title?.trim() ||
    (messages.length > 1 ? (messages[0]?.content?.trim().slice(0, 18) + (messages[0]?.content?.trim().length || 0 > 18 ? "…" : "")) : "新对话");
  const sessionSubtitle = session?.updated_at
    ? formatRelative(session.updated_at)
    : messages.length > 0
      ? `${messages.filter((m) => m.role !== "system").length} 条消息`
      : "开始你的第一个问题";

  const wrapBase = cn(
    "flex flex-col bg-background text-foreground shadow-xl",
    floating
      ? cn(
          "fixed z-40 right-6 bottom-24 w-[380px] max-w-[92vw]",
          // fe-task07：ring-1 ring-black/5 → ring-border（D5）
          "h-[560px] max-h-[80vh] rounded-2xl border border-border ring-1 ring-border",
          _open === false ? "hidden" : "",
        )
      : "h-full w-full border-0 rounded-none",
    className,
  );

  return (
    <section ref={ref} className={wrapBase} aria-label="AI 问答助手面板" style={style}>
      {/* Header */}
      <header className="flex items-center gap-2 border-b border-border/80 px-3 py-2.5">
        {!hideSessionsButton ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onRequestSessionsPanel}
            aria-label="打开会话列表"
            title="会话列表"
          >
            <PanelLeftClose className="size-4" aria-hidden />
          </Button>
        ) : null}
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {/* fe-task07：头像渐变 → 主色渐变；在线点 → bg-success 保留 */}
          <span className="relative inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-primary-deep to-primary text-primary-foreground shadow shadow-primary/30">
            <Bot className="size-4" aria-hidden />
            <span className="absolute -right-0.5 -bottom-0.5 inline-flex size-3 items-center justify-center rounded-full bg-success text-white ring-2 ring-background">
              <Sparkles className="size-2" aria-hidden />
            </span>
          </span>
          <div className="min-w-0 flex-1 space-y-0.5">
            <div className="flex items-center gap-1.5">
              {/* sizeExceptions 例外③：13.5px → text-sm */}
              <span className={cn("truncate text-sm font-semibold leading-tight")}>
                EduAgent 助手
              </span>
              {isStreaming && (
                <Badge variant="default" className="h-4 px-1.5 text-4xs font-medium bg-primary text-primary-foreground">
                  生成中
                </Badge>
              )}
            </div>
            <div className={cn("truncate text-3xs text-muted-foreground")}>
              {sessionTitle} · {sessionSubtitle}
            </div>
          </div>
        </div>

        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          title="新对话"
          aria-label="新对话"
          onClick={() => {
            void onNewSession();
            setDraft("");
            setDraftErr(null);
            if (panelRef && "current" in (panelRef as React.MutableRefObject<ChatPanelHandle | null>)) {
              (panelRef as React.MutableRefObject<ChatPanelHandle | null>).current?.focusInput();
            }
          }}
        >
          <MessageSquarePlus className="size-4" />
        </Button>
        {floating ? (
          <>
            <Link
              href="/chat"
              aria-label="进入全屏聊天页"
              title="全屏聊天"
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <Maximize2 className="size-4" />
            </Link>
            {onClose && (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={onClose}
                aria-label="关闭 AI 面板"
                title="关闭"
              >
                <X className="size-4" />
              </Button>
            )}
          </>
        ) : (
          <Link
            href="/chat"
            aria-label="打开独立聊天页"
            title="打开独立页"
            className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <ArrowUpRight className="size-4" />
          </Link>
        )}
      </header>

      {/* Messages */}
      <div
        ref={scrollRef}
        className={cn(
          "min-h-0 flex-1 overflow-y-auto",
          floating ? "px-3 py-3 space-y-4" : "px-5 py-5 space-y-6",
        )}
      >
        {messages.length === 0 ? (
          <WelcomeEmptyState compact={!!floating} onPickSample={(t) => setDraft((d) => d ? `${d}\n${t}` : t)} />
        ) : (
          messages.map((msg, i) => (
            <div key={msg.message_id ?? `msg-${i}`} className="space-y-2.5">
              <ChatMessageBubble
                message={msg}
                userNickname={userNickname}
                userAvatar={userAvatar}
              />
              {/* 将 sources/tool_calls 作为下一行独立块渲染，保持消息气泡视觉干净 */}
              {msg.role === "assistant" && msg.tool_calls?.length ? (
                <div className={cn(floating ? "pl-11" : "pl-12 max-w-[640px]")}>
                  <ToolCallList calls={msg.tool_calls} compact={compactSources ?? floating} />
                </div>
              ) : null}
              {msg.role === "assistant" && msg.sources?.length ? (
                <div className={cn(floating ? "pl-11" : "pl-12")}>
                  <SourceCardList
                    sources={msg.sources}
                    compact={compactSources ?? floating}
                    max={floating ? 3 : 5}
                  />
                </div>
              ) : null}
            </div>
          ))
        )}
      </div>

      <Separator />

      {/* Composer */}
      <div
        className={cn(
          "space-y-1.5",
          floating ? "px-3 pb-3 pt-2" : "px-5 pb-4 pt-3",
        )}
      >
        {draftErr && (
          <div className="text-3xs text-destructive">{draftErr}</div>
        )}
        <div
          className={cn(
            "relative rounded-xl border border-border/80 bg-muted/30 focus-within:border-primary/60 focus-within:bg-background transition-colors",
            "shadow-sm",
          )}
        >
          <Textarea
            ref={textareaRef}
            placeholder={
              authed
                ? (floating ? "提问知识点、讲题、学习规划…（Enter 发送 / Shift+Enter 换行）" : "向 EduAgent 提问：知识点讲解、错题解析、学习计划生成、调用课程与能力工具…（Enter 发送 / Shift+Enter 换行）")
                : "请先登录后再提问"
            }
            rows={1}
            value={draft}
            disabled={!authed}
            onChange={(e) => {
              const v = e.target.value;
              if (v.length <= MAX_LEN) {
                setDraft(v);
                if (draftErr) setDraftErr(null);
              } else {
                setDraftErr(`内容最多 ${MAX_LEN} 字符（当前 ${v.length}）`);
              }
            }}
            onKeyDown={handleKeyDown}
            className={cn(
              // sizeExceptions 例外③：输入框 13.5px → text-sm
              "resize-none border-0 bg-transparent px-3 pt-3 pb-9 pr-14 text-sm leading-6 shadow-none focus-visible:ring-0",
              floating ? "min-h-[44px]" : "min-h-[52px]",
            )}
            spellCheck={false}
          />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between px-3 pb-2 text-3xs">
            <span className="inline-flex items-center gap-1 text-muted-foreground/80">
              <CornerDownLeft className="size-3" aria-hidden />
              Enter 发送 · Shift+Enter 换行
            </span>
            <span
              className={cn(
                "tabular-nums",
                nearLimit
                  ? charsLeft < 0
                    ? "text-destructive font-semibold"
                    : "text-warning-foreground"
                  : "text-muted-foreground/70",
              )}
            >
              {charsLeft}
            </span>
          </div>

          {/* 右下角按钮：Stop > Send */}
          <div className="absolute right-2 bottom-1.5">
            {isStreaming ? (
              <Button
                type="button"
                variant="destructive"
                size="icon-sm"
                onClick={onStop}
                aria-label="停止生成"
                title="停止"
              >
                <Square className="size-3.5 fill-current" aria-hidden />
              </Button>
            ) : (
              <Button
                type="button"
                variant="default"
                size="icon-sm"
                onClick={() => void submit()}
                disabled={!authed || sending || !draft.trim() || !!draftErr}
                aria-label="发送消息"
                title="发送（Enter）"
              >
                <Send className="size-4" aria-hidden />
              </Button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
});

export default ChatPanel;

/* ================= 帮助：相对时间 ================= */

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "";
  const diff = Date.now() - t;
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s} 秒前`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d} 天前`;
  const dt = new Date(t);
  return `${dt.getMonth() + 1}/${dt.getDate()}`;
}

/* ================= 空态欢迎：示例提示 ================= */

function WelcomeEmptyState({
  compact,
  onPickSample,
}: { compact: boolean; onPickSample: (text: string) => void }) {
  const samples = compact
    ? [
        "帮我讲一下勾股定理的推导过程",
        "解释这道二次函数错题",
        "给我一份数学 7 天复习计划",
      ]
    : [
        "帮我讲一下勾股定理的推导过程，并配 3 道练习题。",
        "解析这道错题的考点，给出同类题解题思路。",
        "根据我的课程进度，生成数学、物理各一份 7 天复习计划。",
        "查询我最近三次模考的知识点掌握热力图，并给出薄弱点。",
      ];
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-2 py-4 text-center">
      <div className="relative">
        {/* fe-task07：空态渐变 → 主色渐变；在线点 → bg-success */}
        <span className="inline-flex size-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary-deep to-primary text-primary-foreground shadow-lg shadow-primary/30">
          <Bot className="size-5" aria-hidden />
        </span>
        <span className="absolute -right-1 -top-1 inline-flex size-4 items-center justify-center rounded-full bg-success text-white ring-2 ring-background">
          <Sparkles className="size-2.5" aria-hidden />
        </span>
      </div>
      <div className="space-y-1">
        {/* sizeExceptions 例外④：15px → text-base */}
        <div className="text-base font-semibold">你好，我是 EduAgent AI 学习助手</div>
        <div className={cn(
          "text-2xs leading-5 text-muted-foreground",
          compact ? "max-w-[300px]" : "max-w-[520px]",
        )}>
          可以解答学科问题、讲解错题、生成学习计划、还能调用课程与 MCP 工具为你检索资料和运行任务。试试下面这些：
        </div>
      </div>
      <ul className={cn(
        "grid w-full gap-2",
        compact ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2",
      )}>
        {samples.map((s, i) => (
          <li key={i}>
            <button
              type="button"
              onClick={() => onPickSample(s)}
              className={cn(
                // fe-task07：hover 漂移统一 hover:border-primary-border hover:shadow-card
                "flex w-full items-start gap-2 rounded-xl border border-border bg-background p-2.5 text-left text-2xs leading-5 transition-all hover:border-primary-border hover:shadow-card hover:bg-muted/30",
              )}
            >
              <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                <Sparkles className="size-3" aria-hidden />
              </span>
              <span className="min-w-0 flex-1 text-foreground">{s}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
