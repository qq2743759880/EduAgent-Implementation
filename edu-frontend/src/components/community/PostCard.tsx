/**
 * PostCard — C24 社区帖子卡片（candy-playful frozen，task51 对齐 approved community.html）。
 * - 墨色描边 + 3D 实底阴影；置顶📌糖果黄 pill / 锁定🔒灰 pill / 版块糖果色 pill / 标签紫 soft。
 * - 点击标题 → /community/{post_id}；锁定帖只读（无链接、无焦点、aria-disabled）。
 * - meta：作者 · 时间 · 👁浏览 · 💬评论 · 👍点赞（字段与契约⑬ mock 一致：view/comment/like）。
 * 纯展示组件，不发起写请求（点赞/收藏由详情页 ReactButtons 负责）。
 */
import Link from "next/link";
import { Eye, Heart, Lock, MessageCircle, Pin } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PostSummary } from "@/lib/api/community";
import { getBoardMeta, formatDateTime, stripMarkdown } from "@/lib/community-meta";

export interface PostCardProps {
  post: PostSummary;
}

function MetaStat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <span className="inline-flex items-center gap-1 tabular-nums">
      {icon}
      <span className="sr-only">{label}</span>
      {value}
    </span>
  );
}

export function PostCard({ post }: PostCardProps) {
  const board = getBoardMeta(post.board_code);
  const locked = post.is_locked;

  return (
    <article
      aria-label={locked ? `锁定帖（只读）：${post.title}` : undefined}
      className={cn(
        "flex flex-col gap-2.5 rounded-3xl border-[3px] border-foreground bg-white p-4",
        "shadow-[0_5px_0_color-mix(in_oklch,var(--foreground),transparent_82%)]",
        locked
          ? "cursor-default"
          : "transition-transform hover:-translate-y-0.5 hover:border-candy-purple",
      )}
    >
      {/* 顶部：🔒锁定 / 📌置顶 / 版块糖果 pill */}
      <div className="flex flex-wrap items-center gap-2">
        {locked && (
          <span className="inline-flex items-center gap-1 rounded-md border-2 border-foreground/20 px-2 py-0.5 text-3xs font-extrabold text-muted-foreground">
            <Lock className="h-3 w-3" aria-hidden="true" />
            锁定
          </span>
        )}
        {post.is_pinned && (
          <span className="inline-flex items-center gap-1 rounded-md border-2 border-foreground bg-candy-yellow px-2 py-0.5 text-3xs font-extrabold text-foreground">
            <Pin className="h-3 w-3" aria-hidden="true" />
            置顶
          </span>
        )}
        <span
          className={cn(
            "rounded-full border-2 border-foreground px-2.5 py-0.5 text-3xs font-extrabold",
            board.colorClass,
          )}
        >
          {board.label}
        </span>
      </div>

      {locked ? (
        <h3 className="text-base font-extrabold leading-snug text-foreground md:text-lg">
          {post.title}
        </h3>
      ) : (
        <h3>
          <Link
            href={`/community/${post.post_id}`}
            className="text-base font-extrabold leading-snug text-foreground transition-colors hover:text-candy-purple md:text-lg"
          >
            {post.title}
          </Link>
        </h3>
      )}

      {post.summary && (
        <p className="line-clamp-2 text-sm leading-relaxed text-muted-foreground">
          {stripMarkdown(post.summary)}
        </p>
      )}

      {post.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {post.tags.slice(0, 5).map((t) => (
            <span
              key={t}
              className="rounded-full border border-candy-purple/25 bg-candy-purple-soft px-2.5 py-0.5 text-3xs font-bold text-candy-purple"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-2xs text-muted-foreground">
        <span className="font-extrabold text-foreground">
          {post.author_name ?? "匿名学员"}
        </span>
        <span aria-hidden="true" className="text-foreground/30">
          ·
        </span>
        <span>{formatDateTime(post.created_at)}</span>
        <span aria-hidden="true" className="text-foreground/30">
          ·
        </span>
        <span className="ml-auto inline-flex items-center gap-3">
          <MetaStat icon={<Eye className="h-3.5 w-3.5" aria-hidden="true" />} label="浏览" value={post.view_count} />
          <MetaStat icon={<MessageCircle className="h-3.5 w-3.5" aria-hidden="true" />} label="评论" value={post.comment_count} />
          <MetaStat icon={<Heart className="h-3.5 w-3.5" aria-hidden="true" />} label="点赞" value={post.like_count} />
        </span>
      </div>
    </article>
  );
}