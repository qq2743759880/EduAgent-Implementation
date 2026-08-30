"use client"

import * as React from "react"
import { Select as SelectPrimitive } from "@base-ui/react/select"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { ChevronDownIcon, CheckIcon, CircleAlertIcon } from "lucide-react"

export type SelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
};

/**
 * 表单下拉（受控字符串值）：label + trigger + 选项列表 + error + disabled。
 *  value 为空时展示 placeholder；错误信息展示于底部（不吞错）。
 */
function Select({
  label,
  options,
  value,
  onValueChange,
  placeholder = "请选择",
  error,
  disabled = false,
  required = false,
  name,
  className,
}: {
  label?: React.ReactNode;
  options: SelectOption[];
  value: string | null;
  onValueChange?: (value: string | null) => void;
  placeholder?: string;
  error?: React.ReactNode;
  disabled?: boolean;
  required?: boolean;
  name?: string;
  className?: string;
}) {
  const labelId = React.useId().replace(/:/g, "");
  const hasError = Boolean(error);

  return (
    <div className={cn("flex flex-col gap-1.5", className)} data-slot="select">
      {label ? (
        <label htmlFor={labelId} className="text-xs font-medium text-foreground">
          {label}
          {required ? <span className="ml-0.5 text-destructive">*</span> : null}
        </label>
      ) : null}
      <SelectPrimitive.Root
        name={name}
        disabled={disabled}
        required={required}
        value={value}
        onValueChange={onValueChange}
        items={options.map((o) => ({ label: o.label, value: o.value }))}
        data-slot="select-root"
      >
        <SelectPrimitive.Trigger
          id={labelId}
          data-slot="select-trigger"
          aria-invalid={hasError || undefined}
          render={
            <Button
              variant="outline"
              className={cn(
                "w-full justify-between font-normal",
                !value && "text-muted-foreground",
                hasError && "border-destructive ring-3 ring-destructive/20"
              )}
            />
          }
        >
          <SelectPrimitive.Value placeholder={placeholder} />
          <ChevronDownIcon className="size-4 text-muted-foreground" />
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Positioner data-slot="select-positioner">
          <SelectPrimitive.Popup
            data-slot="select-popup"
            className="z-50 min-w-[var(--anchor-width)] overflow-hidden rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-lg outline-none"
          >
            {options.map((opt) => (
              <SelectPrimitive.Item
                key={opt.value}
                value={opt.value}
                disabled={opt.disabled}
                className="group/item flex cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm outline-none select-none data-highlighted:bg-muted data-highlighted:text-foreground data-disabled:pointer-events-none data-disabled:opacity-50"
              >
                <SelectPrimitive.ItemText>{opt.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator className="text-primary">
                  <CheckIcon className="size-4" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Popup>
        </SelectPrimitive.Positioner>
      </SelectPrimitive.Root>
      {hasError ? (
        <p role="alert" className="flex items-center gap-1 text-xs text-destructive">
          <CircleAlertIcon className="size-3.5" />
          {error}
        </p>
      ) : null}
    </div>
  )
}

export { Select }