/**
 * SubjectLevelFilters
 * 分类 Tabs + 价格区间输入（task40 对齐 /api/series 契约②：category/keyword/price 筛选）
 * 受控组件：value 与 onChange 由父组件（search params）管理。
 * 契约② 已无 subject_code/level_code 筛选 —— 级别区移除，学科区改为一级分类。
 */
"use client";

import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { CATEGORY_OPTIONS, CategoryCode } from "@/lib/api/curriculum";

export interface SubjectLevelFiltersValue {
  q?: string;
  category: CategoryCode | "all";
  min_price?: number;
  max_price?: number;
}

const Schema = z
  .object({
    q: z.string().max(64, "关键词最多 64 字符").optional(),
    category: z.enum(["all", ...CATEGORY_OPTIONS.map((s) => s.code)] as [string, ...string[]]),
    min_price: z.coerce
      .number()
      .gte(0, "最低价 ≥ 0")
      .lte(999999, "超出范围")
      .optional()
      .or(z.literal("").transform(() => undefined)),
    max_price: z.coerce
      .number()
      .gte(0, "最高价 ≥ 0")
      .lte(999999, "超出范围")
      .optional()
      .or(z.literal("").transform(() => undefined)),
  })
  .superRefine((v, ctx) => {
    if (
      typeof v.min_price === "number" &&
      typeof v.max_price === "number" &&
      v.min_price > v.max_price
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["min_price"],
        message: "最低价不能大于最高价",
      });
    }
  });

/**
 * min_price / max_price 用了 z.coerce + .or(z.literal("")) ——
 * 输入端可以是 "" 或字符串数字，输出端才是 number | undefined。
 * useForm 需要分别拿到 input / output 泛型，resolver 类型才对得上。
 */
type SchemaInput = z.input<typeof Schema>;
type SchemaOutput = z.output<typeof Schema>;

export interface SubjectLevelFiltersProps {
  value: SubjectLevelFiltersValue;
  onChange: (next: SubjectLevelFiltersValue) => void;
  showSearch?: boolean;
  showPrice?: boolean;
}

export function SubjectLevelFilters({
  value,
  onChange,
  showSearch = true,
  showPrice = true,
}: SubjectLevelFiltersProps) {
  const form = useForm<SchemaInput, unknown, SchemaOutput>({
    resolver: zodResolver(Schema),
    defaultValues: {
      q: value.q ?? "",
      category: value.category ?? "all",
      min_price: value.min_price ?? ("" as unknown as undefined),
      max_price: value.max_price ?? ("" as unknown as undefined),
    },
    mode: "onChange",
  });

  // react-hook-form 的 watch() 与 React Compiler 不兼容（跳过编译，不影响运行）
  // eslint-disable-next-line react-hooks/incompatible-library
  const category = form.watch("category");

  const apply = (patch: Partial<SchemaOutput>) => {
    const cur = form.getValues() as SchemaOutput;
    const next: SchemaOutput = { ...cur, ...patch };
    form.reset(next, { keepDefaultValues: true });
    onChange(toValue(next));
  };

  const submit = form.handleSubmit(async (vals) => {
    onChange(toValue(vals));
  });

  function toValue(next: z.infer<typeof Schema>): SubjectLevelFiltersValue {
    return {
      q: next.q || undefined,
      category: next.category as CategoryCode | "all",
      min_price: typeof next.min_price === "number" ? next.min_price : undefined,
      max_price: typeof next.max_price === "number" ? next.max_price : undefined,
    };
  }

  const resultCountHint = useMemo(() => {
    if (category !== "all") {
      return CATEGORY_OPTIONS.find((s) => s.code === category)?.name ?? category;
    }
    return "全部分类";
  }, [category]);

  return (
    <Form {...form}>
      <form onSubmit={submit} className="space-y-5 rounded-xl border border-border bg-card p-5 shadow-card">
        {showSearch && (
          <FormField
            control={form.control}
            name="q"
            render={({ field }) => (
              <FormItem>
                <FormLabel>搜索课程</FormLabel>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <FormControl>
                      <Input
                        className="pl-9"
                        placeholder="输入关键词，如：Python、微积分、考研"
                        {...field}
                      />
                    </FormControl>
                  </div>
                  <Button type="submit">搜索</Button>
                </div>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <div className="space-y-1.5">
          <Label>分类</Label>
          <div className="flex flex-wrap gap-2">
            <CategoryTag
              active={category === "all"}
              onClick={() => apply({ category: "all" })}
              label="全部"
            />
            {CATEGORY_OPTIONS.map((s) => (
              <CategoryTag
                key={s.code}
                active={category === s.code}
                onClick={() => apply({ category: s.code })}
                label={s.name}
              />
            ))}
          </div>
        </div>

        {showPrice && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_1fr] md:items-end">
            <FormField
              control={form.control}
              name="min_price"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>最低价格（元）</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={0}
                      placeholder="0"
                      {...field}
                      value={(field.value as unknown as number | "") ?? ""}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="hidden pb-2 text-muted-foreground md:block">—</div>
            <FormField
              control={form.control}
              name="max_price"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>最高价格（元）</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={0}
                      placeholder="9999"
                      {...field}
                      value={(field.value as unknown as number | "") ?? ""}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        )}

        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">当前筛选：{resultCountHint}</span>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() =>
                onChange({
                  q: undefined,
                  category: "all",
                  min_price: undefined,
                  max_price: undefined,
                })
              }
            >
              重置
            </Button>
            <Button type="submit" size="sm">
              应用
            </Button>
          </div>
        </div>
      </form>
    </Form>
  );
}

function CategoryTag({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "group inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-all " +
        (active
          ? "border-primary-border bg-primary text-primary-foreground shadow-sm"
          : "border-border bg-background text-foreground hover:border-primary-border")
      }
    >
      <span
        className={
          "h-2 w-2 rounded-full " + (active ? "bg-white/80" : "bg-muted-foreground/50")
        }
      />
      {label}
    </button>
  );
}
