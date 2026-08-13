/**
 * 社区共用元数据：分版定义、板块配色、时间格式化。
 * 供 PostCard / BoardTabs / PostEditor / 页面复用，避免文案与配色漂移。
 */
import type { BoardCode } from "@/lib/api/community";

export interface BoardMeta {
  code: BoardCode;
  label: string;
  /** 纯色 Badge 用（outline 变体） */
  colorClass: string;
  /** 渐变头部/图标底色用 */
  gradientClass: string;
}

/**
 * 4 个学科分版（契约：english/math/programming/general，空=全部）。
 * fe-task07 收敛：分版四色 → 单主色（colorClass 统一主色 soft 底）；gradientClass 置空（禁自造渐变）；
 * 分版区分靠 label 文字（英语/数学/编程/综合）。
 */
export const BOARDS: BoardMeta[] = [
  { code: "english", label: "英语", colorClass: "bg-primary-soft text-primary", gradientClass: "" },
  { code: "math", label: "数学", colorClass: "bg-primary-soft text-primary", gradientClass: "" },
  { code: "programming", label: "编程", colorClass: "bg-primary-soft text-primary", gradientClass: "" },
  { code: "general", label: "综合", colorClass: "bg-primary-soft text-primary", gradientClass: "" },
];

/** code → meta 索引（未知 code 兜底 general） */
export const BOARD_META: Record<string, BoardMeta> = Object.fromEntries(
  BOARDS.map((b) => [b.code, b]),
);

export function getBoardMeta(code: string | null | undefined): BoardMeta {
  return BOARD_META[code ?? ""] ?? BOARD_META.general;
}

/** 时间显示：今天 → HH:mm，今年 → M月d日 HH:mm，更早 → yyyy年M月d日 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  if (d.toDateString() === now.toDateString()) return hm;
  if (d.getFullYear() === now.getFullYear()) {
    return `${d.getMonth() + 1}月${d.getDate()}日 ${hm}`;
  }
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

/** 相对时间：刚刚 / n分钟前 / n小时前 / n天前 / 具体日期 */
export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const diffSec = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (diffSec < 60) return "刚刚";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} 分钟前`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} 小时前`;
  if (diffSec < 86400 * 30) return `${Math.floor(diffSec / 86400)} 天前`;
  return formatDateTime(value);
}

/**
 * 去除常见 Markdown 标记为纯文本（列表摘要展示用，避免暴露源码语法）。
 * 仅处理展示层常见语法，不解析嵌套结构；对无标记文本保持原样。
 */
export function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, "") // 标题 #
    .replace(/\*\*([^*]+)\*\*/g, "$1") // 粗体 **text**
    .replace(/\*([^*]+)\*/g, "$1") // 斜体 *text*
    .replace(/`([^`]+)`/g, "$1") // 行内代码 `code`
    .replace(/^>\s?/gm, "") // 引用 >
    .replace(/^[-*+]\s+/gm, "") // 无序列表
    .replace(/^\d+\.\s+/gm, "") // 有序列表
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1") // 图片 → 替代文本
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1") // 链接 → 链接文字
    .replace(/\s+/g, " ")
    .trim();
}
