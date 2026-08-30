"use client"

import * as React from "react"
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { XIcon } from "lucide-react"

function Dialog({ modal = true, ...props }: DialogPrimitive.Root.Props) {
  // modal 默认 true（Base UI 默认值显式化）：焦点困在弹窗内 + 锁定背景滚动 + 外部指针禁用
  return <DialogPrimitive.Root data-slot="dialog" modal={modal} {...props} />
}

function DialogTrigger({ ...props }: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogPortal({ ...props }: DialogPrimitive.Portal.Props) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />
}

function DialogClose({ ...props }: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

function DialogOverlay({
  className,
  ...props
}: DialogPrimitive.Backdrop.Props) {
  return (
    <DialogPrimitive.Backdrop
      data-slot="dialog-overlay"
      className={cn(
        "fixed inset-0 isolate z-50 bg-black/10 duration-100 supports-backdrop-filter:backdrop-blur-xs data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0",
        className
      )}
      {...props}
    />
  )
}

function DialogContent({
  className,
  children,
  showCloseButton = true,
  initialFocus,
  finalFocus,
  ...props
}: DialogPrimitive.Popup.Props & {
  showCloseButton?: boolean
  /**
   * 打开时聚焦的元素（缺省 Base UI 行为：首个可聚焦元素）。
   * 受控 open + key 重挂载场景下，如需精确指定可传 RefObject。
   */
  initialFocus?: DialogPrimitive.Popup.Props["initialFocus"]
  /**
   * 关闭后归还焦点的元素（缺省 Base UI 行为：触发按钮或打开前焦点元素）。
   */
  finalFocus?: DialogPrimitive.Popup.Props["finalFocus"]
}) {
  const returnFocusRef = React.useRef<HTMLElement | null>(null)

  // a11y 兜底：
  //  1) 弹窗打开（Popup 挂载）时记录弹窗外最后聚焦元素，关闭（Popup 卸载）时归还焦点 ——
  //     覆盖受控 open + key 重挂载（open=true 直接挂载）等 Base UI 内部 `elementFocusedBeforeOpen`
  //     追踪失效的场景，保证关闭后焦点不落 BODY（与 Base UI 自带 returnFocus 同目标，幂等）。
  //  2) 初始焦点兜底 —— Base UI 的初始聚焦走 rAF，在 dev/HMR 负载下偶发未生效（实测复现），
  //     若打开后焦点仍未进入弹窗，延迟一拍把焦点移入首个可聚焦元素（a11y 2.4.3：打开即聚焦对话框）。
  const setPopupRef = React.useCallback((node: HTMLDivElement | null) => {
    if (node) {
      if (!returnFocusRef.current && typeof document !== "undefined") {
        const active = document.activeElement
        if (active instanceof HTMLElement && active !== document.body && !node.contains(active)) {
          returnFocusRef.current = active
        }
      }
      const openedFromOutside = document.activeElement instanceof HTMLElement
        && !node.contains(document.activeElement)
      if (openedFromOutside) {
        const first = node.querySelector<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement | HTMLButtonElement | HTMLAnchorElement>(
          'input, select, textarea, button, a[href], [tabindex]:not([tabindex="-1"])',
        )
        const prev = document.activeElement
        const isDisabled = (el: typeof first) =>
          el !== null && "disabled" in el && (el as { disabled?: boolean }).disabled === true
        if (first && !isDisabled(first)) {
          setTimeout(() => {
            // 仅当 Base UI 未接管焦点时兜底聚焦（避免双写竞争）
            if (node.isConnected && (document.activeElement === prev || document.activeElement === document.body)) {
              first.focus()
            }
          }, 0)
        }
      }
    } else {
      const target = returnFocusRef.current
      returnFocusRef.current = null
      if (target && target.isConnected && typeof target.focus === "function") {
        target.focus({ preventScroll: true })
      }
    }
  }, [])

  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Popup
        ref={setPopupRef}
        initialFocus={initialFocus}
        finalFocus={finalFocus}
        data-slot="dialog-content"
        className={cn(
          "fixed top-1/2 left-1/2 z-50 grid w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl bg-popover p-4 text-sm text-popover-foreground ring-1 ring-foreground/10 duration-100 outline-none sm:max-w-sm data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
          className
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <DialogPrimitive.Close
            data-slot="dialog-close"
            render={
              <Button
                variant="ghost"
                className="absolute top-2 right-2"
                size="icon-sm"
              />
            }
          >
            <XIcon
            />
            <span className="sr-only">Close</span>
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Popup>
    </DialogPortal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  )
}

function DialogFooter({
  className,
  showCloseButton = false,
  children,
  ...props
}: React.ComponentProps<"div"> & {
  showCloseButton?: boolean
}) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "-mx-4 -mb-4 flex flex-col-reverse gap-2 rounded-b-xl border-t bg-muted/50 p-4 sm:flex-row sm:justify-end",
        className
      )}
      {...props}
    >
      {children}
      {showCloseButton && (
        <DialogPrimitive.Close render={<Button variant="outline" />}>
          Close
        </DialogPrimitive.Close>
      )}
    </div>
  )
}

function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn(
        "font-heading text-base leading-none font-medium",
        className
      )}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn(
        "text-sm text-muted-foreground *:[a]:underline *:[a]:underline-offset-3 *:[a]:hover:text-foreground",
        className
      )}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
