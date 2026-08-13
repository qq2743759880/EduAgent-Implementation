/**
 * MarkdownView — 项目统一的安全 Markdown 渲染器
 *
 * 用途：帖子正文（详情页）、PostEditor 实时预览、评论内容等全部 markdown 展示。
 *
 * 安全（对抗 fe-task01 #1）：react-markdown 默认 skipHtml=true，不渲染 raw HTML，
 * 即 `<img onerror=...>` 类输入不会被解析为 DOM 节点、不会执行脚本。
 * 预览与正文渲染必须统一走本组件（无 rehypeRaw 的默认安全配置），
 * 禁止在渲染链路引入 rehype-raw / rehype-sanitize 白名单。
 */
import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

export interface MarkdownViewProps {
  content: string;
  className?: string;
}

/** memo：正文 props 仅 content 字符串，点赞/收藏/回帖计数变化时跳过 react-markdown 重解析 */
export const MarkdownView = memo(function MarkdownView({ content, className }: MarkdownViewProps) {
  return (
    <div
      className={cn(
        "prose-sm max-w-none text-[15px] leading-7 text-foreground [&_h1]:mb-3 [&_h1]:mt-5 [&_h1]:text-xl [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-lg [&_h2]:font-semibold [&_p]:my-2 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_blockquote]:border-l-4 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:bg-zinc-900 [&_pre]:p-4 [&_pre]:text-xs [&_pre]:text-zinc-100 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_a]:text-primary [&_a]:underline",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
});
