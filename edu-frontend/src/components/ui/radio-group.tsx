"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/* =========================================================
 * Self-contained RadioGroup + RadioGroupItem
 * ---------------------------------------------------------
 * 避免 @base-ui/react radio 在不同版本的 parts 命名漂移问题
 *（Radio/RadioPrimitive.Radio 与 .Item 的导出不统一）。
 * =======================================================*/

type RadioGroupContextValue = {
  name: string;
  value: unknown;
  disabled?: boolean;
  onChange: (next: string) => void;
};

const RadioGroupContext = React.createContext<RadioGroupContextValue | null>(null);

function useRadioGroup() {
  const ctx = React.useContext(RadioGroupContext);
  if (!ctx) throw new Error("<RadioGroupItem /> must be used inside a <RadioGroup />");
  return ctx;
}

interface RadioGroupProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "onChange" | "value" | "defaultValue"> {
  value?: unknown;
  defaultValue?: unknown;
  disabled?: boolean;
  name?: string;
  /** ShadCN-style callback: (nextValue) => void */
  onValueChange?: (next: string) => void;
  /** Backwards-compatible event-ish callback */
  onChange?: (event: { target: { value: string } }) => void;
}

const RadioGroup = React.forwardRef<HTMLDivElement, RadioGroupProps>(function RadioGroup(
  {
    className,
    value: controlled,
    defaultValue,
    disabled,
    name,
    onValueChange,
    onChange,
    children,
    ...props
  },
  ref,
) {
  const [internal, setInternal] = React.useState<unknown>(defaultValue);
  const isControlled = controlled !== undefined;
  const value = isControlled ? controlled : internal;
  const generatedName = React.useId();
  const finalName = name ?? `radio-${generatedName}`;

  const handleChange = React.useCallback(
    (next: string) => {
      if (!isControlled) setInternal(next);
      onValueChange?.(next);
      onChange?.({ target: { value: next } });
    },
    [isControlled, onValueChange, onChange],
  );

  const ctxValue = React.useMemo<RadioGroupContextValue>(
    () => ({ name: finalName, value, disabled, onChange: handleChange }),
    [finalName, value, disabled, handleChange],
  );

  return (
    <RadioGroupContext.Provider value={ctxValue}>
      <div
        ref={ref}
        role="radiogroup"
        data-slot="radio-group"
        className={cn("grid gap-2", className)}
        {...props}
      >
        {children}
      </div>
    </RadioGroupContext.Provider>
  );
});

interface RadioGroupItemProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "value"> {
  value: string | number;
}

const RadioGroupItem = React.forwardRef<HTMLInputElement, RadioGroupItemProps>(function RadioGroupItem(
  { className, disabled: itemDisabled, id, value, style, ...props },
  ref,
) {
  const { name, value: groupValue, disabled: groupDisabled, onChange } = useRadioGroup();
  const disabled = itemDisabled ?? groupDisabled;
  const checked = String(groupValue) === String(value);
  const autoId = React.useId();
  const inputId = id ?? autoId;

  return (
    <>
      <input
        ref={ref}
        id={inputId}
        type="radio"
        name={name}
        value={value}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        aria-checked={checked}
        className="peer sr-only absolute h-0 w-0 opacity-0 pointer-events-none"
        {...props}
      />
      <span
        aria-hidden
        data-slot="radio-group-item"
        style={style}
        className={cn(
          "relative shrink-0 inline-flex items-center justify-center rounded-full border border-input text-primary transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-4 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-4 aria-invalid:ring-destructive/20 dark:bg-input/30 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
          "peer-focus-visible:border-ring peer-focus-visible:ring-4 peer-focus-visible:ring-ring/50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
          "h-[1.125rem] w-[1.125rem]",
          className,
        )}
      >
        <span
          data-slot="radio-group-indicator"
          className={cn(
            "flex items-center justify-center",
            checked ? "opacity-100" : "opacity-0",
          )}
        >
          <span className="block h-[0.625rem] w-[0.625rem] rounded-full bg-current" />
        </span>
      </span>
    </>
  );
});

export { RadioGroup, RadioGroupItem };
