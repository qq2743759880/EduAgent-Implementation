/**
 * PostEditor — 发帖表单（标题 + 分版 + Markdown 正文 + 标签）
 *
 * 契约：POST /api/community/posts { title, content_md, board_code, tags }
 *   → { post_id, points_awarded: 5, badge_unlocked[] }（发帖即 +5 分）
 *
 * 成功后：toast 提示 +5 分 → 跳转详情页 /community/{post_id}。
 * 失败：useMutation 全局 onError 已 toast，表单保持原样可重试（不跳转）。
 */
"use client";

import { useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Coins, Loader2, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { BOARDS } from "@/lib/community-meta";
import { createPost, type BoardCode } from "@/lib/api/community";
import { MarkdownView } from "./MarkdownView";

/* MDEditor 依赖 window，SSR 时动态挂载（ssr:false），否则首屏 build 报错 */
const MDEditor = dynamic(() => import("@uiw/react-md-editor"), { ssr: false });

const MAX_TITLE_LEN = 200;
const MAX_CONTENT_LEN = 20000;
const MAX_TAGS = 8;

export interface PostEditorProps {
  /** 默认分版（列表页当前 Tab） */
  defaultBoard?: BoardCode;
  /** 发帖成功后额外回调（如关闭编辑器） */
  onPosted?: (postId: number) => void;
  className?: string;
}

export function PostEditor({ defaultBoard = "general", onPosted, className }: PostEditorProps) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [board, setBoard] = useState<BoardCode>(defaultBoard);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [touched, setTouched] = useState(false);

  const tags = useMemo(
    () =>
      tagsText
        .split(/[,，\s]+/)
        .map((t) => t.trim())
        .filter(Boolean)
        .slice(0, MAX_TAGS),
    [tagsText],
  );

  const titleValid = title.trim().length >= 2 && title.trim().length <= MAX_TITLE_LEN;
  const contentValid = content.trim().length >= 2 && content.trim().length <= MAX_CONTENT_LEN;
  const formValid = titleValid && contentValid;
  /** 校验错误（touched 且非空时展示）：用于 aria-invalid / aria-describedby 关联 */
  const titleError = touched && !titleValid && title.trim().length > 0;
  const contentError = touched && !contentValid && content.trim().length > 0;

  /** 分版单选键盘导航（APG Radio）：左右/上下循环 + Home/End，roving tabindex */
  const boardRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const onBoardKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    let next = index;
    if (e.key === "Home") next = 0;
    else if (e.key === "End") next = BOARDS.length - 1;
    else if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (index + 1) % BOARDS.length;
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (index - 1 + BOARDS.length) % BOARDS.length;
    setBoard(BOARDS[next].code);
    boardRefs.current[next]?.focus();
  };

  const mutation = useMutation({
    mutationFn: () =>
      createPost({
        title: title.trim(),
        content_md: content,
        board_code: board,
        tags,
      }),
    onSuccess: (resp) => {
      toast.success("发布成功", {
        description:
          resp.points_awarded > 0
            ? `发帖获得 +${resp.points_awarded} 积分${
                resp.badge_unlocked?.length ? `，解锁徽章：${resp.badge_unlocked.join("、")}` : ""
              }`
            : "你的帖子已经发布",
      });
      setTouched(false);
      onPosted?.(resp.post_id);
      // 失效列表 + 积分缓存，下次进列表/成就中心取最新
      void queryClient.invalidateQueries({ queryKey: ["community", "posts"] });
      void queryClient.invalidateQueries({ queryKey: ["gamification", "points"] });
      router.push(`/community/${resp.post_id}`);
    },
  });

  const onSubmit = () => {
    setTouched(true);
    if (!formValid) {
      if (!title.trim()) toast.error("请填写标题（至少 2 个字）");
      else if (!content.trim()) toast.error("请填写正文（至少 2 个字）");
      else toast.error("内容超长，请控制在 20000 字以内");
      return;
    }
    mutation.mutate();
  };

  return (
    <div className={cn("space-y-4 rounded-xl border border-border bg-card p-4 md:p-5", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold text-foreground">发布新帖</h2>
        <p className="inline-flex items-center gap-1 text-xs text-success-foreground">
          <Coins className="h-3.5 w-3.5" /> 发帖奖励 +5 积分
        </p>
      </div>

      {/* 分版选择 */}
      <div className="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="选择分版">
        {BOARDS.map((b, i) => (
          <button
            key={b.code}
            ref={(el) => {
              boardRefs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={board === b.code}
            tabIndex={board === b.code ? 0 : -1}
            onClick={() => setBoard(b.code)}
            onKeyDown={(e) => onBoardKeyDown(e, i)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-foreground",
              board === b.code
                ? "border-transparent bg-primary text-white shadow-sm"
                : "border-border text-secondary-foreground hover:border-border hover:bg-muted",
            )}
          >
            {b.label}
          </button>
        ))}
      </div>

      {/* 标题 */}
      <div className="space-y-1.5">
        <Label htmlFor="post-title">标题</Label>
        <Input
          id="post-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="一句话说清你想分享/求助的内容"
          maxLength={MAX_TITLE_LEN}
          aria-invalid={titleError || undefined}
          aria-describedby={titleError ? "post-title-error" : undefined}
          className={cn(
            titleError && "border-destructive",
          )}
        />
        <div className="flex justify-between text-3xs text-muted-foreground">
          <span id="post-title-error" role="alert" className="text-destructive">
            {titleError ? "标题至少 2 个字" : ""}
          </span>
          <span className="tabular-nums">
            {title.length}/{MAX_TITLE_LEN}
          </span>
        </div>
      </div>

      {/* Markdown 正文
          安全说明（对抗 fe-task01 #1）：@uiw/react-md-editor 内置预览内核
          @uiw/react-markdown-preview 默认启用 rehypeRaw（node_modules 实证，props 无法关闭），
          会渲染作者输入的 raw HTML，构成 self-XSS 面。这里通过官方 components.preview
          把预览渲染器整体替换为项目统一 MarkdownView（react-markdown 默认 skipHtml，
          不渲染 raw HTML），预览与正文渲染走同一安全内核。 */}
      <div className="space-y-1.5">
        <Label htmlFor="post-content">正文（支持 Markdown）</Label>
        <div data-color-mode="light">
          <MDEditor
            value={content}
            onChange={(v) => setContent(v ?? "")}
            height={260}
            preview="live"
            components={{
              preview: (source) => <MarkdownView content={source} />,
            }}
            textareaProps={{
              id: "post-content",
              placeholder: "写下你的学习心得、提问或经验分享…",
              "aria-invalid": contentError || undefined,
              "aria-describedby": contentError ? "post-content-error" : undefined,
            }}
          />
        </div>
        <div className="flex justify-between text-3xs text-muted-foreground">
          <span id="post-content-error" role="alert" className="text-destructive">
            {contentError ? "正文至少 2 个字" : ""}
          </span>
          <span className="tabular-nums">{content.length}/{MAX_CONTENT_LEN}</span>
        </div>
      </div>

      {/* 标签 */}
      <div className="space-y-1.5">
        <Label htmlFor="post-tags">
          标签（可选，最多 {MAX_TAGS} 个，空格或逗号分隔）
        </Label>
        <Input
          id="post-tags"
          value={tagsText}
          onChange={(e) => setTagsText(e.target.value)}
          placeholder="例如：雅思 阅读 学习方法"
          maxLength={120}
        />
      </div>

      <div className="flex items-center justify-end gap-3 border-t border-border pt-3">
        {tags.length > 0 && (
          <div className="mr-auto flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <span key={t} className="rounded-md bg-muted px-1.5 py-0.5 text-3xs text-muted-foreground">
                #{t}
              </span>
            ))}
          </div>
        )}
        <Button type="button" onClick={onSubmit} disabled={mutation.isPending}>
          {mutation.isPending ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> 发布中…
            </>
          ) : (
            <>
              <Send className="h-4 w-4" /> 发布
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
