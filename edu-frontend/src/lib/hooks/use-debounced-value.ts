"use client";

import { useEffect, useState } from "react";

/**
 * 防抖值：value 变化后 delay ms 才更新返回快照。
 *
 * 用于列表页关键词筛选：输入框绑定原始 value（即时反馈），queryKey / 请求只依赖防抖后的
 * 快照（applied），避免逐击键触发后端请求（fx-task03-perf.md F1，300ms 防抖 + applied 进 queryKey）。
 */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
