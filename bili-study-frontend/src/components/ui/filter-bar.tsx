"use client"

import * as React from "react"

import { cn } from "@/lib/utils"

/** 筛选条容器：flex wrap + gap-2，内含 Select/Input 等筛选控件组合。 */
function FilterBar({
  children,
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="filter-bar"
      role="group"
      aria-label="筛选条件"
      className={cn("flex flex-wrap items-center gap-2", className)}
      {...props}
    >
      {children}
    </div>
  )
}

export { FilterBar }