/**
 * BoardTabs — 社区分版切换（全部 + 4 学科）+ 排序切换（热门/最新/点赞）
 * 受控组件：value/onChange 由页面持有（写回 URL 查询参数或本地 state）。
 *
 * 无障碍（APG Tabs 模式）：
 *   - role=tablist/tab + aria-controls 指向分版内容 tabpanel
 *   - roving tabindex（仅选中 tab 可 Tab 聚焦）+ ArrowLeft/Right/Home/End 切换
 *   - 排序切换为独立按钮组（aria-pressed），不复用 tab 语义
 */
"use client";

import { useRef } from "react";
import { Flame, Clock, ThumbsUp } from "lucide-react";
import { cn } from "@/lib/utils";
import { BOARDS } from "@/lib/community-meta";
import type { BoardCode, PostSort } from "@/lib/api/community";

export interface BoardTabsProps {
  value: BoardCode | "";
  onChange: (board: BoardCode | "") => void;
  sort: PostSort;
  onSortChange: (sort: PostSort) => void;
}

const SORT_OPTIONS: Array<{ value: PostSort; label: string; Icon: typeof Flame }> = [
  { value: "HOT", label: "热门", Icon: Flame },
  { value: "NEW", label: "最新", Icon: Clock },
  { value: "LIKE", label: "点赞", Icon: ThumbsUp },
];

/** 分版 Tab 顺序（全部 + 4 学科），与页面 tabpanel 的 aria-labelledby 约定共享 */
export const BOARD_TAB_VALUES: Array<{ code: BoardCode | ""; label: string; gradientClass?: string }> = [
  { code: "", label: "全部" },
  ...BOARDS.map((b) => ({ code: b.code, label: b.label, gradientClass: b.gradientClass })),
];

/** 分版 tab 的 DOM id（页面 tabpanel 用 aria-labelledby 引用） */
export function boardTabId(board: BoardCode | ""): string {
  return board === "" ? "board-tab-all" : `board-tab-${board}`;
}

/** 分版内容 tabpanel 的 DOM id（tab 的 aria-controls 指向） */
export const BOARD_PANEL_ID = "community-posts-panel";

/** 键盘方向键导航（APG Tabs）：左右循环 + Home/End */
function moveIndex(key: string, index: number, length: number): number {
  if (key === "Home") return 0;
  if (key === "End") return length - 1;
  if (key === "ArrowRight") return (index + 1) % length;
  if (key === "ArrowLeft") return (index - 1 + length) % length;
  return index;
}

export function BoardTabs({ value, onChange, sort, onSortChange }: BoardTabsProps) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const onTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    const next = moveIndex(e.key, index, BOARD_TAB_VALUES.length);
    onChange(BOARD_TAB_VALUES[next].code);
    tabRefs.current[next]?.focus();
  };

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      {/* 分版 Tab：全部 + 4 学科 */}
      <div
        className="inline-flex flex-wrap items-center gap-1 rounded-xl bg-muted p-1"
        role="tablist"
        aria-label="社区分版"
      >
        {BOARD_TAB_VALUES.map((tab, i) => {
          const active = value === tab.code;
          return (
            <BoardTabButton
              key={tab.code || "all"}
              id={boardTabId(tab.code)}
              active={active}
              controls={BOARD_PANEL_ID}
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(tab.code)}
              onKeyDown={(e) => onTabKeyDown(e, i)}
              ref={(el) => {
                tabRefs.current[i] = el;
              }}
            >
              {tab.code === "" ? (
                "全部"
              ) : (
                <>
                  <span
                    className={cn(
                      "mr-1 inline-block h-2 w-2 rounded-full bg-current opacity-80",
                      tab.gradientClass,
                    )}
                  />
                  {tab.label}
                </>
              )}
            </BoardTabButton>
          );
        })}
      </div>

      {/* 排序切换 */}
      <div className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-0.5">
        {SORT_OPTIONS.map(({ value: v, label, Icon }) => (
          <button
            key={v}
            type="button"
            onClick={() => onSortChange(v)}
            aria-pressed={sort === v}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-foreground",
              sort === v
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:bg-slate-100 hover:text-foreground",
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function BoardTabButton({
  id,
  active,
  controls,
  tabIndex,
  onClick,
  onKeyDown,
  ref,
  children,
}: {
  id: string;
  active: boolean;
  controls: string;
  tabIndex: number;
  onClick: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLButtonElement>) => void;
  ref?: React.Ref<HTMLButtonElement>;
  children: React.ReactNode;
}) {
  return (
    <button
      ref={ref}
      id={id}
      type="button"
      role="tab"
      aria-selected={active}
      aria-controls={controls}
      tabIndex={tabIndex}
      onClick={onClick}
      onKeyDown={onKeyDown}
      className={cn(
        "inline-flex items-center rounded-lg px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-foreground",
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}
