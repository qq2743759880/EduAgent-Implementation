/**
 * ChatMessageBubble
 *  - 三角色气泡：user / assistant / system
 *  - assistant 消息用 react-markdown 渲染 Markdown；代码块 <pre> 带 copy 按钮（navigator.clipboard）
 *  - streaming=true：末尾追加 Streaming Dots 动画 & 光标闪烁
 *  - 无内容时 assistant 给出 Dots 占位
 *  - avatar：用户 → AvatarFallback（首字）；助手 → Sparkles + 品牌色圆；system → AlertCircle + amber 背景
 */
"use client";

import * as React from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import { Bot, Copy, Check, AlertCircle, User as UserIcon, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage, ChatRole } from "@/lib/api/chat";

/* ========================= 帮助函数 ========================= */

function fallbackInitials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "我";
  // 取汉字/单词首字，最多两个
  const parts = trimmed.split(/\s+/);
  const first = parts[0] ?? "";
  const isASCII = /^[\x00-\x7F]+$/.test(first);
  if (isASCII) return first.slice(0, 2).toUpperCase();
  const second = parts[1] ?? "";
  return (first.slice(0, 1) + second.slice(0, 1)) || first.slice(0, 2);
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* fallback */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return true;
  } catch {
    return false;
  }
}

/* ========================= 子组件 ========================= */

function StreamingDots({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-end gap-[3px] align-middle leading-none h-[1em]",
        className,
      )}
      aria-label="生成中"
    >
      <span className="size-[5px] rounded-full bg-current opacity-60 animate-bounce [animation-delay:-0.32s]" />
      <span className="size-[5px] rounded-full bg-current opacity-80 animate-bounce [animation-delay:-0.16s]" />
      <span className="size-[5px] rounded-full bg-current animate-bounce" />
    </span>
  );
}

function CodeBlock({
  className,
  children,
}: React.ClassAttributes<HTMLElement> & React.HTMLAttributes<HTMLElement> & { children?: React.ReactNode }) {
  const textRef = React.useRef<HTMLPreElement>(null);
  const [copied, setCopied] = React.useState(false);
  const content = React.useMemo(() => {
    let s = "";
    const walk = (node: React.ReactNode): void => {
      if (typeof node === "string" || typeof node === "number") {
        s += String(node);
        return;
      }
      if (Array.isArray(node)) {
        node.forEach(walk);
        return;
      }
      if (React.isValidElement(node)) {
        const p = node.props as { children?: React.ReactNode };
        walk(p?.children);
      }
    };
    walk(children);
    return s.replace(/\n$/, "");
  }, [children]);

  const handleCopy = async () => {
    const ok = await copyToClipboard(content);
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  };

  // 从 className 中提取语言标记（react-markdown convention: "language-py"）
  const lang =
    typeof className === "string"
      ? (className.match(/language-([\w-]+)/)?.[1] ?? "")
      : "";

  return (
    <pre
      ref={textRef}
      className={cn(
        "group/code relative overflow-x-auto rounded-xl border border-border bg-zinc-950 text-zinc-100 p-4 pr-12 text-[13px] leading-6 my-3",
      )}
    >
      <div className="absolute right-2 top-2 flex items-center gap-2">
        {lang && (
          <span className="text-[11px] uppercase tracking-wide text-zinc-400 select-none">
            {lang}
          </span>
        )}
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-zinc-300 opacity-0 transition group-hover/code:opacity-100 hover:bg-white/10 hover:text-white"
          aria-label={copied ? "已复制" : "复制代码"}
        >
          {copied ? (
            <>
              <Check className="size-3" /> 已复制
            </>
          ) : (
            <>
              <Copy className="size-3" /> 复制
            </>
          )}
        </button>
      </div>
      <code className={className}>{children}</code>
    </pre>
  );
}

/* ========================= 头像 ========================= */

function RoleAvatar({
  role,
  nickname,
  avatar,
}: { role: ChatRole; nickname?: string; avatar?: string | null }) {
  if (role === "user") {
    const initials = fallbackInitials(nickname?.trim() || "我");
    if (avatar) {
      return (
        <span className="inline-flex size-8 shrink-0 overflow-hidden rounded-full ring-2 ring-background">
          <img
            src={avatar}
            alt={nickname ?? "我"}
            className="size-full object-cover"
            referrerPolicy="no-referrer"
          />
        </span>
      );
    }
    return (
      <span
        className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-secondary-foreground ring-2 ring-background text-xs font-semibold"
        aria-label={nickname ?? "我"}
      >
        <UserIcon className="size-4" aria-hidden />
        <span className="sr-only">{initials}</span>
      </span>
    );
  }

  if (role === "system") {
    return (
      <span
        className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700 ring-2 ring-background dark:bg-amber-500/20 dark:text-amber-300"
        aria-label="系统消息"
      >
        <AlertCircle className="size-4" aria-hidden />
      </span>
    );
  }

  // assistant
  return (
    <span
      className="relative inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-white ring-2 ring-background shadow shadow-indigo-500/30"
      aria-label="AI 助手"
    >
      <Bot className="size-4" aria-hidden />
      <span className="absolute -right-0.5 -bottom-0.5 inline-flex size-3 items-center justify-center rounded-full bg-amber-400 text-white ring-2 ring-background">
        <Sparkles className="size-2" aria-hidden />
      </span>
    </span>
  );
}

/* ========================= 主组件 ========================= */

export interface ChatMessageBubbleProps {
  message: ChatMessage;
  /** 用户昵称（用于头像 fallback） */
  userNickname?: string;
  userAvatar?: string | null;
  className?: string;
  /** 点击引用来源时的跳转拦截（可为绝对 URL 或内部 path） */
  onSourceClick?: (doc: NonNullable<ChatMessage["sources"]>[number]) => void;
}

export function ChatMessageBubble({
  message,
  userNickname,
  userAvatar,
  className,
  onSourceClick,
}: ChatMessageBubbleProps) {
  const { role, content, streaming, sources, tool_calls } = message;
  const isUser = role === "user";
  const isSystem = role === "system";
  const isAssistant = role === "assistant";
  void onSourceClick;

  return (
    <div
      className={cn(
        "flex w-full gap-3",
        isUser ? "flex-row-reverse" : "flex-row",
        className,
      )}
    >
      <RoleAvatar
        role={role}
        nickname={isUser ? userNickname : undefined}
        avatar={isUser ? userAvatar : undefined}
      />

      <div
        className={cn(
          "flex min-w-0 max-w-[85%] flex-col gap-1.5",
          isUser ? "items-end" : "items-start",
        )}
      >
        <div
          className={cn(
            "relative rounded-2xl text-[14px] leading-6 whitespace-pre-wrap break-words",
            isUser &&
              "rounded-tr-md bg-primary text-primary-foreground px-4 py-2.5 shadow-sm",
            isAssistant &&
              "rounded-tl-md border border-border bg-background text-foreground px-4 py-3 shadow-sm",
            isSystem &&
              "rounded-tl-md border border-amber-200/70 bg-amber-50 text-amber-900 px-4 py-3 dark:bg-amber-500/10 dark:text-amber-200 dark:border-amber-500/20",
            streaming && "min-h-[2.5rem]",
          )}
        >
          {isAssistant || isSystem ? (
            <>
              {content ? (
                isSystem ? (
                  <span>{content}</span>
                ) : (
                  <div className="prose prose-sm max-w-none prose-pre:!p-0 prose-pre:!bg-transparent prose-a:text-primary prose-a:underline-offset-4 prose-headings:mb-2 prose-headings:mt-4 prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5 prose-table:my-2 dark:prose-invert">
                    <ReactMarkdown
                      components={{
                        pre: CodeBlock as unknown as React.ComponentType<React.HTMLAttributes<HTMLElement>>,
                        a: ({ href, children, ...rest }) => {
                          const url = typeof href === "string" ? href : "#";
                          const isExternal = /^https?:\/\//i.test(url);
                          if (isExternal) {
                            return (
                              <a
                                href={url}
                                target="_blank"
                                rel="noreferrer noopener"
                                {...rest}
                              >
                                {children}
                              </a>
                            );
                          }
                          return (
                            <Link href={url} {...(rest as Omit<React.AnchorHTMLAttributes<HTMLAnchorElement> & { className?: string }, "href">)}>
                              {children}
                            </Link>
                          );
                        },
                      }}
                    >
                      {content}
                    </ReactMarkdown>
                  </div>
                )
              ) : streaming ? (
                <StreamingDots className="text-primary" />
              ) : null}
              {streaming && content ? (
                <span
                  aria-hidden
                  className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[2px] bg-primary/80 animate-pulse align-middle"
                />
              ) : null}
            </>
          ) : (
            <span>{content}</span>
          )}
        </div>

        {/* MCP 工具调用可视化（仅 assistant） */}
        {isAssistant && tool_calls && tool_calls.length > 0 ? (
          <div className="w-full">{/* C-5-4 ToolCallVisualizer 占位由 ChatPanel 注入，这里保持组件解耦 */}</div>
        ) : null}

        {/* 引用来源卡片（仅 assistant） */}
        {isAssistant && sources && sources.length > 0 ? (
          <div className="w-full">{/* C-5-3 SourceCardList 占位由 ChatPanel 注入 */}</div>
        ) : null}
      </div>
    </div>
  );
}

export default ChatMessageBubble;
