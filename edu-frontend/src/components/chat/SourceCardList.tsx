/**
 * SourceCardList —— RAG 引用来源列表
 *   - 单条 RagDoc 渲染为一张胶囊式小卡片（浮动面板紧凑 320px / 全屏聊天页宽松 640px）
 *   - 三类型 Icon：section=BookOpenText / question=CircleHelp / doc=FileText
 *   - score：0-1 的小数，映射为 0~100 的 Progress 条（score<0.2 不显示条，阈值过滤避免太弱噪声）
 *   - snippet：最多两行 line-clamp
 *   - 跳转：优先 anchor_url；其次根据 series_id + session_id 推导 /learning/x/y；其次根据 series_id 推 /courses/x
 *   - 空态：返回 null，保持消息气泡干净
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { BookOpenText, CircleHelp, FileText, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { RagDoc, RagDocType } from "@/lib/api/chat";

export interface SourceCardListProps {
  sources: RagDoc[];
  /** 最多展示条数（浮动模式下建议 3，全屏 5） */
  max?: number;
  /** 更紧凑排版（用于 floating chat panel） */
  compact?: boolean;
  className?: string;
  /** 自定义点击事件，返回 true 可阻止默认跳转 */
  onBeforeJump?: (doc: RagDoc) => boolean | void;
}

const MIN_SCORE = 0.18;
const TYPE_LABEL: Record<RagDocType, string> = {
  section: "课节",
  question: "题目",
  doc: "资料",
};

function TypeIcon({ type, className }: { type: RagDocType; className?: string }) {
  const cls = cn("size-4 shrink-0", className);
  if (type === "section") return <BookOpenText className={cls} aria-hidden />;
  if (type === "question") return <CircleHelp className={cls} aria-hidden />;
  return <FileText className={cls} aria-hidden />;
}

function TypeBadge({ type }: { type: RagDocType }) {
  const variant =
    type === "section" ? "secondary" :
    type === "question" ? "destructive" : "outline";
  return (
    <Badge
      variant={variant as "secondary" | "destructive" | "outline"}
      className="inline-flex items-center gap-1"
    >
      <TypeIcon type={type} className="size-3" />
      {TYPE_LABEL[type]}
    </Badge>
  );
}

function resolveHref(doc: RagDoc): string | null {
  if (doc.anchor_url) return doc.anchor_url;
  if (doc.series_id != null && doc.session_id != null) {
    return `/learning/${encodeURIComponent(String(doc.series_id))}/${encodeURIComponent(String(doc.session_id))}`;
  }
  if (doc.question_id != null) {
    // 优先跳转错题页（若有错误项则 practice?focus=wrong 过滤）
    return `/practice/quiz?question_id=${encodeURIComponent(String(doc.question_id))}`;
  }
  if (doc.series_id != null) {
    return `/courses/${encodeURIComponent(String(doc.series_id))}`;
  }
  return null;
}

export function SourceCardList({
  sources,
  max = 3,
  compact = true,
  className,
  onBeforeJump,
}: SourceCardListProps) {
  const list = React.useMemo(() => {
    const dedup = new Map<string | number, RagDoc>();
    for (const d of sources) {
      if (!d) continue;
      const k = d.id ?? `${d.type}:${d.title}`;
      if (!dedup.has(k)) dedup.set(k, d);
    }
    return Array.from(dedup.values())
      .sort((a, b) => (b.score ?? -1) - (a.score ?? -1))
      .slice(0, Math.max(1, max));
  }, [sources, max]);

  if (!list.length) return null;

  return (
    <div
      className={cn(
        "w-full rounded-xl border border-border/60 bg-muted/30 p-2.5 space-y-2",
        compact ? "max-w-[320px]" : "max-w-full",
        className,
      )}
      role="list"
      aria-label={`引用来源（${list.length} 条）`}
    >
      <div className="flex items-center justify-between px-1 pt-0.5 text-3xs uppercase tracking-wide text-muted-foreground">
        <span>引用来源</span>
        <span className="tabular-nums">{list.length}</span>
      </div>
      <ul className={cn("space-y-2", compact ? "space-y-1.5" : "space-y-2.5")}>
        {list.map((doc, idx) => {
          const href = resolveHref(doc);
          const showScore = typeof doc.score === "number" && doc.score >= MIN_SCORE;
          const scorePct = showScore
            ? Math.max(0, Math.min(1, doc.score as number)) * 100
            : 0;
          const card = (
            <li
              key={String(doc.id ?? `${doc.type}-${idx}`)}
              role="listitem"
              className={cn(
                "group relative rounded-lg border border-border bg-background p-2.5 transition-all hover:border-primary-border hover:shadow-card",
                compact ? "p-2" : "p-3",
              )}
            >
              <div className="flex items-start gap-2.5">
                {/* fe-task07：来源类型三色 → 主色（TypeBadge 文字补偿，§2.6） */}
                <div
                  className={cn(
                    "shrink-0 inline-flex items-center justify-center rounded-md bg-primary/10 text-primary",
                    compact ? "size-7" : "size-8",
                  )}
                >
                  <TypeIcon
                    type={doc.type}
                    className={compact ? "size-3.5" : "size-4"}
                  />
                </div>

                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <TypeBadge type={doc.type} />
                    {showScore && (
                      <span className="text-3xs tabular-nums text-muted-foreground">
                        {Math.round(scorePct)}%
                      </span>
                    )}
                    {href && (
                      <ExternalLink
                        className="ml-auto size-3 text-muted-foreground/70 opacity-0 transition group-hover:opacity-100"
                        aria-hidden
                      />
                    )}
                  </div>
                  <div
                    className={cn(
                      "text-sm-table font-medium leading-5 text-foreground line-clamp-1 break-all",
                      compact ? "text-2xs leading-4" : "",
                    )}
                    title={doc.title}
                  >
                    {doc.title}
                  </div>
                  {doc.snippet && (
                    <div
                      className={cn(
                        "text-2xs leading-5 text-muted-foreground line-clamp-2 break-words",
                        compact ? "line-clamp-2" : "line-clamp-3",
                      )}
                    >
                      {doc.snippet}
                    </div>
                  )}
                  {showScore && (
                    <Progress
                      value={scorePct}
                      className="mt-1.5 h-1 [&_[data-slot=progress-indicator]]:bg-primary"
                      aria-label={`相关度 ${Math.round(scorePct)}%`}
                    />
                  )}
                </div>
              </div>
            </li>
          );

          // 决定是否带跳转
          if (!href) return card;
          const needsCustom = typeof onBeforeJump === "function";
          if (needsCustom) {
            return (
              <button
                key={`link-${String(doc.id ?? `${doc.type}-${idx}`)}`}
                type="button"
                onClick={() => {
                  const blocked = onBeforeJump?.(doc) === true;
                  if (blocked) return;
                  if (/^https?:\/\//i.test(href)) {
                    window.open(href, "_blank", "noopener,noreferrer");
                  } else {
                    window.location.href = href;
                  }
                }}
                className="block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
              >
                {card}
              </button>
            );
          }
          const isExternal = /^https?:\/\//i.test(href);
          if (isExternal) {
            return (
              <a
                key={`ext-${String(doc.id ?? `${doc.type}-${idx}`)}`}
                href={href}
                target="_blank"
                rel="noreferrer noopener"
                className="block w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
              >
                {card}
              </a>
            );
          }
          return (
            <Link
              key={`int-${String(doc.id ?? `${doc.type}-${idx}`)}`}
              href={href}
              className="block w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-lg"
            >
              {card}
            </Link>
          );
        })}
      </ul>
    </div>
  );
}

export default SourceCardList;
