"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

export type TimelineTone = "success" | "warning" | "danger" | "neutral" | "primary";

export type TimelineItem = {
  title: React.ReactNode;
  description?: React.ReactNode;
  time?: React.ReactNode;
  status?: TimelineTone;
};

const NODE_COLOR: Record<TimelineTone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-destructive",
  neutral: "bg-muted",
  primary: "bg-primary",
};

/**
 * 时间线（退款轨迹 / 工单跟进 / 视频转码）：竖向节点 + 连接线。
 *  a11y：<ol> 列表；节点为装饰（aria-hidden），语义由 title/status 文本承载。
 */
function Timeline({
  items,
  className,
  ...props
}: React.ComponentProps<"ol"> & { items: TimelineItem[] }) {
  return (
    <ol
      data-slot="timeline"
      className={cn("space-y-0", className)}
      {...props}
    >
      {items.map((item, i) => {
        const tone = item.status ?? "neutral";
        const isLast = i === items.length - 1;
        return (
          <li key={i} className="relative flex gap-3 pb-2">
            <div className="flex flex-col items-center">
              <span
                aria-hidden="true"
                className={cn("mt-1.5 size-2.5 shrink-0 rounded-full", NODE_COLOR[tone])}
              />
              {!isLast ? (
                <span aria-hidden="true" className="mt-1 w-px flex-1 bg-border" />
              ) : null}
            </div>
            <div className="min-w-0 flex-1 pb-4">
              <p className="flex flex-wrap items-center gap-x-2 text-sm text-foreground">
                {item.title}
                {item.time ? (
                  <time className="text-xs text-muted-foreground tabular-nums">{item.time}</time>
                ) : null}
              </p>
              {item.description ? (
                <p className="mt-0.5 text-xs text-muted-foreground">{item.description}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  )
}

export { Timeline }