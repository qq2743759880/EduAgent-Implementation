/**
 * SubjectLevelFilters
 * 学科 Tabs + 分级 Level Tags + 价格区间输入
 * 受控组件：value 与 onChange 由父组件（search params）管理。
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
import { Badge } from "@/components/ui/badge";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { LEVEL_OPTIONS, SUBJECT_OPTIONS, SubjectCode, LevelCode } from "@/lib/api/curriculum";

export interface SubjectLevelFiltersValue {
  q?: string;
  subject: SubjectCode | "all";
  level: LevelCode | "all";
  min_price?: number;
  max_price?: number;
}

const Schema = z
  .object({
    q: z.string().max(64, "关键词最多 64 字符").optional(),
    subject: z.enum(["all", ...SUBJECT_OPTIONS.map((s) => s.code)] as [string, ...string[]]),
    level: z.enum(["all", ...LEVEL_OPTIONS.map((l) => l.code)] as [string, ...string[]]),
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
      subject: value.subject ?? "all",
      level: value.level ?? "all",
      min_price: value.min_price ?? ("" as unknown as undefined),
      max_price: value.max_price ?? ("" as unknown as undefined),
    },
    mode: "onChange",
  });

  const subject = form.watch("subject");
  const level = form.watch("level");

  const apply = (patch: Partial<z.infer<typeof Schema>>) => {
    const cur = form.getValues();
    const next = { ...cur, ...patch };
    form.reset(next, { keepDefaultValues: true });
    onChange({
      q: next.q || undefined,
      subject: next.subject as SubjectCode | "all",
      level: next.level as LevelCode | "all",
      min_price: typeof next.min_price === "number" ? next.min_price : undefined,
      max_price: typeof next.max_price === "number" ? next.max_price : undefined,
    });
  };

  const submit = form.handleSubmit(async (vals) => {
    onChange({
      q: vals.q || undefined,
      subject: vals.subject as SubjectCode | "all",
      level: vals.level as LevelCode | "all",
      min_price: typeof vals.min_price === "number" ? vals.min_price : undefined,
      max_price: typeof vals.max_price === "number" ? vals.max_price : undefined,
    });
  });

  const resultCountHint = useMemo(() => {
    const tokens: string[] = [];
    if (subject !== "all") {
      tokens.push(
        SUBJECT_OPTIONS.find((s) => s.code === subject)?.name ?? subject,
      );
    }
    if (level !== "all") {
      tokens.push(level);
    }
    return tokens.length ? tokens.join(" · ") : "全部学科";
  }, [subject, level]);

  return (
    <Form {...form}>
      <form onSubmit={submit} className="space-y-5 rounded-2xl border bg-white p-5 shadow-sm">
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
                        placeholder="输入关键词，如：雅思、Python、微积分"
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
          <Label>学科</Label>
          <div className="flex flex-wrap gap-2">
            <SubjectTag
              active={subject === "all"}
              onClick={() => apply({ subject: "all" })}
              colorClass="bg-slate-500"
              label="全部"
            />
            {SUBJECT_OPTIONS.map((s) => (
              <SubjectTag
                key={s.code}
                active={subject === s.code}
                onClick={() => apply({ subject: s.code })}
                colorClass={s.color}
                label={s.name}
              />
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>级别</Label>
          <div className="flex flex-wrap gap-2">
            <LevelTag active={level === "all"} onClick={() => apply({ level: "all" })} label="全部" />
            {LEVEL_OPTIONS.map((l) => (
              <LevelTag
                key={l.code}
                active={level === l.code}
                onClick={() => apply({ level: l.code })}
                label={l.short}
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
                  subject: "all",
                  level: "all",
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

function SubjectTag({
  active,
  onClick,
  colorClass,
  label,
}: {
  active: boolean;
  onClick: () => void;
  colorClass: string;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "group inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-all " +
        (active
          ? "border-transparent text-white shadow-sm " + colorClass
          : "border-border bg-background text-foreground hover:border-foreground/30")
      }
    >
      <span
        className={
          "h-2 w-2 rounded-full " + (active ? "bg-white/80" : colorClass)
        }
      />
      {label}
    </button>
  );
}

function LevelTag({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <Badge
      variant={active ? "default" : "outline"}
      className={
        "cursor-pointer select-none px-3 py-1.5 text-sm " +
        (active ? "pointer-events-none" : "")
      }
      onClick={onClick}
    >
      {label}
    </Badge>
  );
}
