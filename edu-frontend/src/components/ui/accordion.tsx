"use client"

import * as React from "react"
import { Accordion as AccordionPrimitive } from "@base-ui/react/accordion"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ChevronDownIcon } from "lucide-react"

/**
 * 手风琴（Base UI Accordion）：单/多展开（multiple）。
 * 组合用法：<Accordion><AccordionItem value=...><AccordionTrigger>标题</AccordionTrigger><AccordionPanel>内容</AccordionPanel></AccordionItem></Accordion>
 * 受控用 value/onValueChange；非受控用 defaultValue。
 */

function Accordion({
  className,
  ...props
}: AccordionPrimitive.Root.Props) {
  return (
    <AccordionPrimitive.Root
      data-slot="accordion"
      className={cn("w-full", className)}
      {...props}
    />
  )
}

function AccordionItem({
  className,
  ...props
}: AccordionPrimitive.Item.Props) {
  return (
    <AccordionPrimitive.Item
      data-slot="accordion-item"
      className={cn("border-b border-border last:border-0", className)}
      {...props}
    />
  )
}

function AccordionTrigger({
  className,
  children,
  ...props
}: AccordionPrimitive.Trigger.Props) {
  return (
    <AccordionPrimitive.Header data-slot="accordion-header" className={cn("flex", className)}>
      <AccordionPrimitive.Trigger
        render={
          <Button
            variant="ghost"
            className="flex-1 justify-between gap-2 px-3 font-medium data-open:aria-[pressed=false]:text-foreground [&[aria-expanded=true]_svg]:rotate-180"
          />
        }
        {...props}
      >
        <span className="text-left">{children}</span>
        <ChevronDownIcon
          data-slot="accordion-chevron"
          className="size-4 shrink-0 text-muted-foreground transition-transform duration-200"
        />
      </AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  )
}

/**
 * Panel：内容区。所有子项均渲染于 DOM，关闭项用 hidden 折叠（keepMounted），
 * 以便「课程大纲四级树」深层内容可被页面内搜索/CSS 稳定过渡。
 */
function AccordionPanel({
  className,
  ...props
}: AccordionPrimitive.Panel.Props) {
  return (
    <AccordionPrimitive.Panel
      data-slot="accordion-panel"
      className={cn(
        "px-3 pb-3 text-sm text-muted-foreground data-closed:animate-out data-closed:fade-out data-open:animate-in data-open:fade-in",
        className
      )}
      {...props}
    />
  )
}

export { Accordion, AccordionItem, AccordionTrigger, AccordionPanel }