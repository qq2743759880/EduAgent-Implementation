/**
 * SourceCardList —— RAG 引用来源列表（task40 对齐 RetrievedDoc 契约）
 *   - 单条 RetrievedDoc 渲染为一张胶囊式小卡片（浮动面板紧凑 320px / 全屏聊天页宽松 640px）
 *   - 三类型 Icon：content_type=course→BookOpenText / question→CircleHelp / 其余→FileText
 *   - score：0-1 的小数，映射为 0~100 的 Progress 条（score<0.2 不显示条，阈值过滤避免太弱噪声）
 *   - snippet = content（line-clamp 限行）；title = series_name ?? source_file ?? 片段首行
 *   - 跳转：仅 series_code 可点回 /courses/{code}（契约未提供 anchor/question 跳转字段）
 *   - 空态：返回 null，保持消息气泡干净
 */
"use client";

import * as React from "react";
import Link from "next/link";
import { BookOpenText, CircleHelp, FileText, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { RetrievedDoc } from "@/lib/api/chat";

export interface SourceCardListProps {
  sources: RetrievedDoc[];
  /** 最多展示条数（浮动模式下建议 3，全屏 5） */
  max?: number;
  /** 更紧凑排版（用于 floating chat panel） */
  compact?: boolean;
  className?: string;
  /** 自定义点击事件，返回 true 可阻止默认跳转 */
  onBeforeJump?: (doc: RetrievedDoc) => boolean | void;
}

const MIN_SCORE = 0.18;

type DocKind = "section" | "question" | "doc";

function kindOf(doc: RetrievedDoc): DocKind {
  if (doc.content_type === "question") return "question";
  if (doc.content_type === "course") return "section";
  return "doc";
}

const KIND_LABEL: Record<DocKind, string> = {
  section: "课节",
  question: "题目",
  doc: "资料",
};

function titleOf(doc: RetrievedDoc, idx: number): string {
  if (doc.series_name?.trim()) return doc.series_name.trim();
  if (doc.source_file?.trim()) return doc.source_file.trim();
  const head = doc.content?.trim().split("\n")[0] ?? "";
  return head ? (head.length > 40 ? `${head.slice(0, 40)}…` : head) : `知识片段 ${idx + 1}`;
}

function TypeIcon({ kind, className }: { kind: DocKind; className?: string }) {
  const cls = cn("size-4 shrink-0", className);
  if (kind === "section") return <BookOpenText className={cls} aria-hidden />;
  if (kind === "question") return <CircleHelp className={cls} aria-hidden />;
  return <FileText className={cls} aria-hidden />;
}

function TypeBadge({ kind }: { kind: DocKind }) {
  const variant =
    kind === "section" ? "secondary" :
    kind === "question" ? "destructive" : "outline";
  return (
    <Badge
      variant={variant as "secondary" | "destructive" | "outline"}
      className="inline-flex items-center gap-1"
    >
      <TypeIcon kind={kind} className="size-3" />
      {KIND_LABEL[kind]}
    </Badge>
  );
}

function resolveHref(doc: RetrievedDoc): string | null {
  if (doc.series_code?.trim()) {
    return `/courses/${encodeURIComponent(doc.series_code.trim())}`;
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
    const dedup = new Map<string, RetrievedDoc>();
    for (const d of sources) {
      if (!d) continue;
      const k = d.doc_id || `${d.series_code ?? ""}:${d.content.slice(0, 32)}`;
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
          const kind = kindOf(doc);
          const title = titleOf(doc, idx);
          const showScore = typeof doc.score === "number" && doc.score >= MIN_SCORE;
          const scorePct = showScore
            ? Math.max(0, Math.min(1, doc.score as number)) * 100
            : 0;
          const key = doc.doc_id || `${kind}-${idx}`;
          const card = (
            <li
              key={key}
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
                    kind={kind}
                    className={compact ? "size-3.5" : "size-4"}
                  />
                </div>

                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <TypeBadge kind={kind} />
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
                    title={title}
                  >
                    {title}
                  </div>
                  {doc.content && (
                    <div
                      className={cn(
                        "text-2xs leading-5 text-muted-foreground line-clamp-2 break-words",
                        compact ? "line-clamp-2" : "line-clamp-3",
                      )}
                    >
                      {doc.content}
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
                key={`link-${key}`}
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
                key={`ext-${key}`}
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
              key={`int-${key}`}
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
