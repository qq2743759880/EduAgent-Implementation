"use client"

import * as React from "react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { TriangleAlertIcon } from "lucide-react"

/** 全站统一错误态：不吞错——原样展示 message，暴露重试入口。role="alert" 播报错误。 */
function ErrorState({
  title = "加载失败",
  message,
  retry,
  retryLabel = "重试",
  className,
  ...props
}: Omit<React.ComponentProps<"div">, "title"> & {
  /** 错误标题（默认「加载失败」） */
  title?: React.ReactNode;
  /** 错误详情（应传后端/异常原文，不可吞错） */
  message?: React.ReactNode;
  /** 重试回调；不传则隐藏重试按钮 */
  retry?: () => void;
  retryLabel?: React.ReactNode;
}) {
  return (
    <div
      data-slot="error-state"
      role="alert"
      className={cn(
        "flex min-h-40 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-destructive/40 bg-destructive/5 px-6 py-10 text-center",
        className
      )}
      {...props}
    >
      <div className="mb-1 text-destructive [&_svg]:size-8" aria-hidden="true">
        <TriangleAlertIcon />
      </div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      {message ? (
        <p className="max-w-sm text-xs text-muted-foreground break-words">{message}</p>
      ) : null}
      {retry ? (
        <div className="mt-2">
          <Button variant="outline" size="sm" onClick={retry}>
            {retryLabel}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

export { ErrorState }