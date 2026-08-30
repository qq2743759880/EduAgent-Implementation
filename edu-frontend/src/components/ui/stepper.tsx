"use client"

import * as React from "react"

import { cn } from "@/lib/utils"
import { CheckIcon } from "lucide-react"

export type StepperStep = {
  title: React.ReactNode;
  description?: React.ReactNode;
  status: "done" | "current" | "todo";
};

/**
 * 步骤条（支付/退款/导入流程）。
 *  a11y：<ol> 列表；current 项带 aria-current="step"；completed 用文字 + 对勾双通道（非纯色）。
 */
function Stepper({
  steps,
  className,
  ...props
}: React.ComponentProps<"ol"> & { steps: StepperStep[] }) {
  const currentIndex = steps.findIndex((s) => s.status === "current");
  return (
    <ol
      data-slot="stepper"
      aria-label="步骤进度"
      className={cn("flex w-full items-start", className)}
      {...props}
    >
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1;
        const done = step.status === "done";
        const current = step.status === "current";
        return (
          <li key={i} className={cn("flex-1", isLast && "flex-none")} aria-current={current ? "step" : undefined}>
            <div className="flex items-center gap-2">
              <span
                data-status={step.status}
                className={cn(
                  "flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium",
                  done && "border-primary bg-primary text-primary-foreground",
                  current && "border-primary bg-primary-soft text-primary-soft-foreground ring-4 ring-primary/15",
                  step.status === "todo" && "border-border bg-muted text-muted-foreground"
                )}
              >
                {done ? <CheckIcon className="size-3.5" aria-hidden="true" /> : i + 1}
              </span>
              {!isLast ? (
                <span
                  aria-hidden="true"
                  className={cn(
                    "h-px flex-1",
                    step.status === "done" ? "bg-primary/40" : "bg-border"
                  )}
                />
              ) : null}
            </div>
            <div className="mt-2">
              <p className={cn(
                "text-xs font-medium",
                current ? "text-foreground" : "text-muted-foreground"
              )}>
                {done ? <span className="sr-only">已完成：</span> : null}
                {current ? <span className="sr-only">当前：</span> : null}
                {step.title}
              </p>
              {step.description ? (
                <p className="mt-0.5 text-xs text-muted-foreground">{step.description}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  )
}

export { Stepper }