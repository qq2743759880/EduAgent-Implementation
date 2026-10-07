"use client"

import * as React from "react"
import { Menu as BaseDropdownMenu } from "@base-ui/react/menu"

import { cn } from "@/lib/utils"

/**
 * 下拉菜单（Base UI Menu）：触发器 + 弹出菜单项。键盘导航 / 焦点管理由 Base UI 内建。
 * 组合用法：<DropdownMenu><DropdownMenuTrigger><Button>操作</Button></DropdownMenuTrigger>
 *             <DropdownMenuContent>
 *               <DropdownMenuItem onClick={() => {}}>编辑</DropdownMenuItem>
 *               <DropdownMenuItem destructive>删除</DropdownMenuItem>
 *             </DropdownMenuContent></DropdownMenu>
 */

const DropdownMenu = BaseDropdownMenu.Root;
const DropdownMenuTrigger = BaseDropdownMenu.Trigger;

function DropdownMenuContent({
  className,
  sideOffset = 4,
  anchor,
  ...props
}: BaseDropdownMenu.Popup.Props & {
  sideOffset?: number;
  anchor?: BaseDropdownMenu.Positioner.Props["anchor"];
}) {
  return (
    <BaseDropdownMenu.Portal>
      <BaseDropdownMenu.Positioner
        sideOffset={sideOffset}
        anchor={anchor}
        data-slot="dropdown-menu-positioner"
      >
        <BaseDropdownMenu.Popup
          data-slot="dropdown-menu"
          className={cn(
            "z-50 min-w-[8rem] overflow-hidden rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-lg outline-none data-closed:animate-out data-closed:fade-out-0 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95",
            className
          )}
        >
          {props.children}
        </BaseDropdownMenu.Popup>
      </BaseDropdownMenu.Positioner>
    </BaseDropdownMenu.Portal>
  )
}

function DropdownMenuItem({
  className,
  destructive = false,
  ...props
}: BaseDropdownMenu.Item.Props & { destructive?: boolean }) {
  return (
    <BaseDropdownMenu.Item
      data-slot="dropdown-menu-item"
      data-destructive={destructive || undefined}
      className={cn(
        "flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-muted data-highlighted:text-foreground data-disabled:pointer-events-none data-disabled:opacity-50",
        destructive && "text-destructive data-highlighted:bg-destructive/10 data-highlighted:text-destructive",
        className
      )}
      {...props}
    />
  )
}

function DropdownMenuSeparator({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      role="separator"
      data-slot="dropdown-menu-separator"
      className={cn("my-1 h-px bg-border", className)}
      {...props}
    />
  )
}

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
}