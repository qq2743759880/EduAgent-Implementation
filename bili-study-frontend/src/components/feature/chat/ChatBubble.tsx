/**
 * ChatBubble — AI 问答消息气泡（task50 核心，candy-playful frozen）
 * 对齐 chat.html 效果图：用户消息糖果紫右对齐 / AI 消息卡片白底左对齐。
 *  - user   ：bg-candy-purple 白字、圆角右收（border-bottom-right-radius 小）
 *  - ai     ：bg-card 白底 + border-foreground 粗描边、圆角左收；内容用 MarkdownView 安全渲染
 *  - streaming：AI 消息末尾追加糖果绿闪烁光标方块（animate-pulse）
 *  - meta   ：text-3xs 时间戳；AI 消息展示「🔎 N 篇引用」（rag_retrieved_count / sources）
 *  - system ：居中灰条（会话失败等系统提示，不吞错）
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { ChatRole } from "@/lib/api/chat";
import { MarkdownView } from "@/components/community/MarkdownView";

export interface ChatBubbleProps {
  role: ChatRole;
  content: string;
  /** 是否仍在流式生成（viscus cursor） */
  streaming?: boolean;
  /** 时间戳（created_at，ISO 字符串；缺省不渲染 meta 行） */
  time?: string | null;
  /** 引用计数（rag_retrieved_count 或 sources.length；>0 才显示） */
  retrievedCount?: number | null;
}

const fmtTime = (iso: string): string => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso ?? "").slice(0, 5);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
};

export function ChatBubble({
  role,
  content,
  streaming = false,
  time = null,
  retrievedCount = null,
}: ChatBubbleProps) {
  // system：居中提示条（不可忽视的系统/失败信息）
  if (role === "system") {
    return (
      <div
        data-slot="chat-bubble-system"
        role="status"
        className="flex min-w-0 items-center justify-center text-2xs text-muted-foreground"
      >
        <div className="max-w-[85%] rounded-lg bg-muted/60 px-3 py-1.5 text-center leading-5">{content}</div>
      </div>
    );
  }

  const isUser = role === "user";
  const showMeta = time != null;
  const showRefs = !isUser && (retrievedCount ?? 0) > 0;

  return (
    <div
      data-slot="chat-bubble"
      data-role={role}
      className={cn(
        "flex min-w-0 max-w-[86%] flex-col",
        isUser ? "self-end items-end" : "self-start items-start",
      )}
    >
      <div
        className={cn(
          "min-w-0 rounded-2xl border-[3px] px-3.5 py-2.5 text-sm leading-6",
          isUser
            ? "bg-candy-purple text-white"
            : "border-foreground bg-card text-foreground",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{content}</p>
        ) : (
          <MarkdownView content={content} />
        )}
        {streaming && !isUser ? (
          <span
            aria-hidden="true"
            className="ml-0.5 inline-block h-[1.05em] w-px animate-pulse bg-candy-green align-middle"
          />
        ) : null}
      </div>
      {showMeta ? (
        <div className={cn("mt-1.5 flex items-center gap-2 px-1 text-3xs text-muted-foreground", isUser ? "justify-end" : "")}>
          <span aria-hidden="true">{(isUser ? "😊" : "🤖")}</span>
          <time className="tabular-nums">{time ? fmtTime(time) : ""}</time>
          {showRefs ? (
            <span className="font-semibold text-candy-blue" title="引用知识库条目">
              🔎 {retrievedCount} 篇引用
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}