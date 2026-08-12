"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  SUBJECT_LABELS,
  SUBJECT_OPTIONS,
  type SubjectKey,
} from "@/lib/validators/profile-schemas";

interface SubjectMultiSelectProps {
  value?: SubjectKey[];
  onChange?: (next: SubjectKey[]) => void;
  onBlur?: () => void;
  disabled?: boolean;
  className?: string;
  /** 每行多少个，默认 auto-fill(至少 2 个) */
  minCol?: number;
}

export function SubjectMultiSelect({
  value = [],
  onChange,
  onBlur,
  disabled = false,
  className,
  minCol = 2,
}: SubjectMultiSelectProps) {
  const selected = new Set(value);

  function toggle(key: SubjectKey) {
    if (disabled) return;
    const next = selected.has(key)
      ? Array.from(selected).filter((k) => k !== key)
      : Array.from(selected).concat(key);
    onChange?.(next as SubjectKey[]);
  }

  function clearAll() {
    if (disabled) return;
    onChange?.([]);
  }

  return (
    <div className={cn("space-y-2", className)} onBlurCapture={onBlur}>
      <div
        className="grid gap-2"
        style={{
          gridTemplateColumns: `repeat(auto-fill, minmax(${100 / Math.max(minCol, 1)}%, 1fr))`,
        }}
      >
        {SUBJECT_OPTIONS.map((key) => {
          const on = selected.has(key);
          return (
            <button
              type="button"
              key={key}
              disabled={disabled}
              onClick={() => toggle(key)}
              className={cn(
                "h-10 px-3 rounded-lg text-sm font-medium transition-all border",
                "flex items-center justify-center gap-1.5",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60",
                on
                  ? "bg-gradient-to-br from-indigo-600 to-sky-600 text-white border-transparent shadow-sm hover:brightness-[1.02]"
                  : "bg-white text-slate-700 border-slate-200 hover:border-indigo-300 hover:text-indigo-700 hover:bg-indigo-50/50",
                disabled && "opacity-60 cursor-not-allowed hover:border-slate-200 hover:text-slate-700",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  on ? "bg-white/90" : "bg-slate-300",
                )}
              />
              {SUBJECT_LABELS[key]}
            </button>
          );
        })}
      </div>
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>
          已选 <span className="font-semibold text-slate-700">{value.length}</span> 个 · 共 {SUBJECT_OPTIONS.length} 个可选
        </span>
        <button
          type="button"
          onClick={clearAll}
          disabled={disabled || value.length === 0}
          className="text-indigo-600 hover:text-indigo-700 hover:underline disabled:text-slate-300 disabled:hover:no-underline disabled:cursor-not-allowed"
        >
          清空选择
        </button>
      </div>
    </div>
  );
}

/**
 * 「仅展示学科徽章」的只读版本，用于 Dashboard/用户简卡 等不需切换的场景
 */
export function SubjectBadgeList({
  value = [],
  variant = "secondary",
  className,
}: {
  value?: SubjectKey[];
  variant?: "secondary" | "outline" | "default";
  className?: string;
}) {
  if (value.length === 0) return null;
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {value.map((k) => (
        <Badge key={k} variant={variant}>
          {SUBJECT_LABELS[k]}
        </Badge>
      ))}
    </div>
  );
}

export default SubjectMultiSelect;
