/**
 * ChatSessionList — AI 问答会话列表（task50-fix，candy-playful frozen）
 * 对齐 chat.html v2 侧栏：💬 对话列表标题 + 「＋ 新建」按钮；
 * 行为：标题/时间、当前会话糖果紫高亮、hover 删除入口、点选切换、空态引导。
 * 数据与 CRUD 由 useChatSessions 注入（listChatSessions / createChatSession / deleteChatSession / selectSession）。
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { ChatSession } from "@/lib/api/chat";

export interface ChatSessionListProps {
  sessions: ChatSession[];
  activeId: string | null;
  loading?: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  className?: string;
}

/** 会话列表时间：今日 HH:mm、昨日「昨日」、更早 M-D */
function fmtSessDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const today = now.toDateString();
  if (d.toDateString() === today) {
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  const y = new Date(now);
  y.setDate(now.getDate() - 1);
  if (d.toDateString() === y.toDateString()) return "昨日";
  return `${d.getMonth() + 1}-${d.getDate()}`;
}

export function ChatSessionList({
  sessions,
  activeId,
  loading = false,
  onSelect,
  onNew,
  onDelete,
  className,
}: ChatSessionListProps) {
  return (
    <div data-slot="chat-session-list" className={cn("flex min-h-0 flex-col", className)}>
      {/* 头部：标题 + 新建 */}
      <div className="mb-2 flex shrink-0 items-center gap-2" data-slot="chat-session-head">
        <span className="text-sm font-extrabold tracking-tight">💬 对话列表</span>
        <button
          type="button"
          onClick={onNew}
          data-slot="chat-session-new"
          className="ml-auto inline-flex items-center gap-1 rounded-lg border-[3px] border-foreground bg-candy-green px-2.5 py-1 text-2xs font-extrabold text-white shadow-[0_3px_0_color-mix(in_oklch,var(--candy-green),black_30%)] transition-transform enabled:hover:bg-[color-mix(in_oklch,var(--candy-green),black_8%)] enabled:active:translate-y-px enabled:active:shadow-none"
        >
          ＋ 新建
        </button>
      </div>

      {/* 列表 */}
      <div
        data-slot="chat-session-items"
        className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto"
      >
        {loading ? (
          <div className="space-y-1.5">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="h-11 animate-pulse rounded-xl bg-muted/50"
                aria-hidden="true"
              />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div
            role="status"
            className="px-3 py-8 text-center text-2xs leading-5 text-muted-foreground"
          >
            还没有会话，点右上「＋ 新建」开始第一段对话吧 ✨
          </div>
        ) : (
          sessions.map((s) => {
            const active = s.session_id === activeId;
            const title = s.title?.trim() || "未命名对话";
            const timeLabel = fmtSessDate(s.last_message_at ?? s.updated_at);
            return (
              <div
                key={s.session_id}
                data-slot="chat-session-row"
                data-active={active || undefined}
                className={cn(
                  "group flex cursor-pointer items-center gap-2 rounded-xl border-2 border-transparent px-2 py-1.5 transition-[background-color,border-color]",
                  active
                    ? "border-candy-purple/40 bg-candy-purple-soft"
                    : "hover:bg-candy-purple-soft",
                  s.session_id.startsWith("tmp_") && "opacity-70",
                )}
                onClick={() => onSelect(s.session_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect(s.session_id);
                  }
                }}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-lg text-sm",
                    active ? "bg-candy-purple text-white" : "bg-candy-purple-soft",
                  )}
                >
                  {active ? "💬" : "🗂"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-2xs font-bold leading-4 text-foreground">
                    {title}
                  </span>
                  {timeLabel ? (
                    <span className="mt-0.5 block text-3xs leading-3 text-muted-foreground">
                      {timeLabel}
                    </span>
                  ) : null}
                </span>
                <button
                  type="button"
                  aria-label={`删除会话 ${title}`}
                  title="删除会话"
                  data-slot="chat-session-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(s.session_id);
                  }}
                  onKeyDown={(e) => {
                    // 阻止冒泡到行 onKeyDown（否则 Enter/Space 会同时触发选中）
                    e.stopPropagation();
                  }}
                  className="size-5 shrink-0 rounded-md text-sm text-muted-foreground opacity-0 transition-[opacity,background-color,color] hover:bg-candy-orange-soft hover:text-candy-orange group-hover:opacity-100 group-focus-within:opacity-100"
                >
                  🗑
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}