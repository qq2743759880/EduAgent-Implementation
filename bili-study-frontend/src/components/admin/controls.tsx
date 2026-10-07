/**
 * 管理端共享表单控件（task03）
 *  - NativeSelect：原生 select 的 shadcn 风格包装（UI 库无 Select 组件，用原生保 a11y）
 *  - FieldRow：表单行（label + 控件 + 错误）
 *  - LoadingState / ErrorState / EmptyState：列表三态复用
 *
 * W-NEXT-QUESTIONFORM-FIX-001（2026-09-18）：TagChip / NO_TAG_HINT 已删除 ——
 * 唯一消费者 legacy QuestionForm 整体删除（全仓库 grep 零挂载零活引用）。
 */
"use client";

import * as React from "react";
import { useId, type ReactNode } from "react";
import { AlertCircle, Inbox, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* ---------------- NativeSelect ---------------- */
export function NativeSelect({
  className,
  children,
  ...props
}: React.ComponentProps<"select"> & { children?: ReactNode }) {
  return (
    <select
      data-slot="native-select"
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-input bg-white px-2.5 py-1 text-sm transition-colors outline-none",
        "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
        "disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

/* ---------------- FieldRow（非 react-hook-form 的简单行式表单用） ---------------- */
export function FieldRow({
  label,
  required,
  error,
  children,
  hint,
  className,
  id,
}: {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: ReactNode;
  className?: string;
  /**
   * 控件 id：label htmlFor 与错误提示 id（`${id}-error`）同源。
   * 单子元素控件（Input/Textarea/NativeSelect 等）会由 FieldRow 自动注入 id / aria-invalid / aria-describedby；
   * 多子元素（如「分级名称 + 预填按钮」）需调用方在控件上手动设置相同 id 与 aria 属性。
   */
  id?: string;
}) {
  const autoId = useId();
  // controlId 解析：props.id > 子元素已有 id（单子元素或多子元素中的首个表单控件）> 自动生成
  const childrenArr = React.Children.toArray(children).filter(
    (c): c is React.ReactElement<Record<string, unknown>> => React.isValidElement(c),
  );
  const firstFormId = childrenArr
    .map((c) => (typeof c.props?.id === "string" ? c.props.id : undefined))
    .find(Boolean);
  const controlId = id ?? firstFormId ?? `field-${autoId}`;
  const errId = `${controlId}-error`;

  // 单子元素时自动为控件建立 label 关联；仅对表单控件（原生表单元素或受控组件）注入错误 aria。
  // 避免把 aria-invalid 打到 div/button 等非表单元素上（axe 会报 unsupported aria）。
  const child = childrenArr.length === 1 ? childrenArr[0] : null;
  const isDomTag = typeof child?.type === "string";
  const isFormControlTag = isDomTag && ["input", "select", "textarea"].includes(child.type as string);
  const injectAria = Boolean(error) && (isFormControlTag || !isDomTag);
  const control = child
    ? React.cloneElement(child, {
        ...(typeof child.props?.id === "string" ? {} : { id: controlId }),
        ...(injectAria
          ? { "aria-invalid": true as const, "aria-describedby": errId }
          : {}),
      })
    : children;

  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={controlId} className="text-[13px] font-medium text-slate-700">
        {label}
        {required && <span className="ml-0.5 text-rose-500">*</span>}
      </label>
      {control}
      {error ? (
        <p id={errId} className="text-[12px] text-rose-700">{error}</p>
      ) : hint ? (
        <p className="text-[12px] text-slate-500">{hint}</p>
      ) : null}
    </div>
  );
}

/**
 * 提交校验失败后把焦点移到第一个错误字段（a11y 3.3.1：为读屏用户提供到达错误的路径）。
 * selectors 以字段 key → CSS 选择器映射；按 errors 插入顺序取首个。
 */
export function focusFirstFieldError(
  errors: Record<string, string>,
  fieldSelectors: Record<string, string>,
) {
  const firstKey = Object.keys(errors)[0];
  if (!firstKey) return;
  const selector = fieldSelectors[firstKey];
  if (!selector) return;
  document.querySelector<HTMLElement>(selector)?.focus();
}

/* ---------------- 列表三态 ---------------- */
export function LoadingState({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="flex min-h-[180px] items-center justify-center gap-2 text-sm text-slate-500">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex min-h-[180px] flex-col items-center justify-center gap-2 rounded-xl border border-rose-200 bg-rose-50/50 p-6 text-center">
      <AlertCircle className="h-6 w-6 text-rose-500" />
      <div className="text-sm font-medium text-rose-700">加载失败</div>
      <p className="max-w-md text-[13px] text-rose-700">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-1" onClick={onRetry}>
          <RefreshCw className="mr-1 h-3.5 w-3.5" /> 重试
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  message,
  hint,
  compact = false,
}: {
  message: string;
  hint?: string;
  /** D-14：嵌套层级（如模块卡内课次空态）用紧凑形态，section 级保持 min-h-[180px] */
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-6 text-center",
        compact ? "min-h-0 py-3" : "min-h-[180px]",
      )}
    >
      <Inbox className="h-6 w-6 text-slate-300" />
      <div className="text-sm font-medium text-slate-600">{message}</div>
      {hint && <p className="max-w-md text-[13px] text-slate-500">{hint}</p>}
    </div>
  );
}
