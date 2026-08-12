"use client";

import * as React from "react";
import {
  Controller,
  FormProvider,
  useFormContext,
  type ControllerProps,
  type FieldPath,
  type FieldValues,
} from "react-hook-form";

import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";

type FormFieldContextValue<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
> = {
  name: TName;
  id: string;
};

const FormFieldContext = React.createContext<FormFieldContextValue | null>(null);

function useFormFieldContextOrThrow(): FormFieldContextValue {
  const ctx = React.useContext(FormFieldContext);
  if (!ctx) {
    throw new Error("Form components must be used within a <FormField>");
  }
  return ctx;
}

type FormItemContextValue = {
  id: string;
};

const FormItemContext = React.createContext<FormItemContextValue | null>(null);

function useFormItemContextOrThrow(): FormItemContextValue {
  const ctx = React.useContext(FormItemContext);
  if (!ctx) {
    throw new Error("FormItem children must be used within a <FormItem>");
  }
  return ctx;
}

const Form = FormProvider;

function FormField<
  TFieldValues extends FieldValues = FieldValues,
  TName extends FieldPath<TFieldValues> = FieldPath<TFieldValues>,
>({ ...props }: ControllerProps<TFieldValues, TName>) {
  const generatedId = React.useId();
  const fieldCtxValue = React.useMemo<FormFieldContextValue<TFieldValues, TName>>(
    () => ({ name: props.name, id: generatedId }),
    [props.name, generatedId],
  );
  return (
    <FormFieldContext.Provider value={fieldCtxValue}>
      <Controller {...props} />
    </FormFieldContext.Provider>
  );
}

function useFormField() {
  const field = useFormFieldContextOrThrow();
  const item = useFormItemContextOrThrow();
  const form = useFormContext();
  if (!form) {
    throw new Error("Form components must be used within a <Form> provider");
  }
  const fieldState = form.getFieldState(field.name, form.formState);
  const error = fieldState.error;
  return {
    form,
    name: field.name,
    id: field.id,
    formItemId: item.id,
    formDescriptionId: `${item.id}-form-item-description`,
    formMessageId: `${item.id}-form-item-message`,
    invalid: Boolean(error),
    error,
  };
}

function FormItem({ className, ...props }: React.ComponentProps<"div">) {
  const id = React.useId();
  const value = React.useMemo(() => ({ id }), [id]);
  return (
    <FormItemContext.Provider value={value}>
      <div
        data-slot="form-item"
        className={cn("space-y-2 group/form-item", className)}
        {...props}
      />
    </FormItemContext.Provider>
  );
}

function FormLabel({ className, ...props }: React.ComponentProps<typeof Label>) {
  const { error, formItemId } = useFormField();
  return (
    <Label
      data-slot="form-label"
      data-error={Boolean(error) || undefined}
      htmlFor={formItemId}
      className={cn(
        "data-[error=true]:text-destructive",
        className,
      )}
      style={undefined}
      {...props}
    />
  );
}

function FormControl({ children, ...props }: React.ComponentPropsWithoutRef<"div">) {
  const { id, formDescriptionId, formMessageId, error } = useFormField();
  const ariaDescribedBy = [
    formDescriptionId,
    error ? formMessageId : undefined,
  ]
    .filter(Boolean)
    .join(" ") || undefined;
  return (
    <div data-slot="form-control" {...props}>
      {React.isValidElement(children)
        ? React.cloneElement(
            children as React.ReactElement<Record<string, unknown>>,
            {
              id,
              "aria-invalid": error ? true : undefined,
              "aria-describedby": ariaDescribedBy,
              ...(children as React.ReactElement<Record<string, unknown>>).props,
            },
          )
        : children}
    </div>
  );
}

function FormDescription({ className, ...props }: React.ComponentProps<"p">) {
  const { formDescriptionId } = useFormField();
  return (
    <p
      data-slot="form-description"
      id={formDescriptionId}
      className={cn("text-[13px] text-muted-foreground text-slate-500 leading-5", className)}
      {...props}
    />
  );
}

function FormMessage({ className, children, ...props }: React.ComponentProps<"p">) {
  const { formMessageId, error } = useFormField();
  const body = error ? String(error.message ?? "") : children;
  if (!body) return null;
  return (
    <p
      data-slot="form-message"
      id={formMessageId}
      className={cn("text-[13px] font-medium text-destructive text-rose-600 leading-5", className)}
      {...props}
    >
      {body}
    </p>
  );
}

export { Form, FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage, useFormField };
