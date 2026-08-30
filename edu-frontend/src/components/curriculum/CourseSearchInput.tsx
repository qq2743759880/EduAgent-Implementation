/**
 * CourseSearchInput — 课程搜索框（task44，防抖 400ms）。
 * 输入即更新本地文本，停止输入 400ms 后回调 onDebouncedChange（trim 后提交）。
 * 学中玩风格：圆角胶囊 + 糖果绿聚焦环。
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface CourseSearchInputProps {
  /** 已提交的关键词（父组件 queryKey 使用）；外部重置时同步清空输入框 */
  value: string;
  /** 防抖 400ms 后回调（trim 后） */
  onDebouncedChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function CourseSearchInput({
  value,
  onDebouncedChange,
  placeholder = "搜索课程名称、简介或编码",
  className,
}: CourseSearchInputProps) {
  const [text, setText] = useState(value);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 外部重置（如「重置 ×」）时同步清空输入框
  useEffect(() => {
    setText(value);
  }, [value]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const handleChange = (next: string) => {
    setText(next);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onDebouncedChange(next.trim()), 400);
  };

  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    setText("");
    onDebouncedChange("");
  };

  return (
    <div className={cn("relative", className)}>
      <Search
        aria-hidden="true"
        className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
      />
      <input
        type="text"
        value={text}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        aria-label="搜索课程"
        autoComplete="off"
        className="h-11 w-full rounded-full border-2 border-border bg-card pl-10 pr-10 text-sm text-foreground outline-none transition-all placeholder:text-muted-foreground focus:border-candy-green focus:ring-4 focus:ring-candy-green/20"
      />
      {text ? (
        <button
          type="button"
          onClick={clear}
          aria-label="清空搜索"
          className="absolute right-2.5 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-full bg-muted text-muted-foreground transition-colors hover:bg-border"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </div>
  );
}
