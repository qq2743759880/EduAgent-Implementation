/**
 * SeriesForm — 系列创建/编辑弹窗（task03）
 *  - create：POST /api/admin/courses/series（系列编码必填，创建后不可改）
 *  - edit：PATCH /api/admin/courses/series/{id}（仅提交非空字段）
 *  - 写操作走 useMutation（L3），失败由全局 MutationCache → toast，不静默吞错（R-7）
 */
"use client";

import type { FormEvent } from "react";
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  ADMIN_LEVEL_OPTIONS,
  ADMIN_SUBJECT_OPTIONS,
  SALE_STATUS_OPTIONS,
  createAdminSeries,
  updateAdminSeries,
  type AdminSeriesItem,
  type SeriesCreateInput,
} from "@/lib/api/admin/courses";
import { FieldRow, NativeSelect, focusFirstFieldError } from "@/components/admin/controls";

export interface SeriesFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 传入 series 为编辑模式；不传为创建模式 */
  series?: AdminSeriesItem | null;
  onSaved?: () => void;
}

const LEVEL_NAME_PRESETS: Array<{ code: string; name: string }> = [
  { code: "L1", name: "入门" },
  { code: "L2", name: "基础" },
  { code: "L3", name: "进阶" },
  { code: "L4", name: "高级" },
  { code: "L5", name: "专家" },
];

/** 校验失败后焦点定位：字段 key → 控件选择器（与下方 FieldRow id 对应） */
const FIELD_SELECTORS: Record<string, string> = {
  series_code: "#series-code",
  series_name: "#series-name",
  subject_code: "#series-subject",
  level_code: "#series-level",
  level_name: "#series-level-name",
};

export function SeriesForm({ open, onOpenChange, series, onSaved }: SeriesFormProps) {
  // key 切换触发重挂载：每次弹窗打开（open→true）重置表单（编辑回填 / 创建置空）
  return (
    <SeriesFormBody
      key={open ? `open-${series?.id ?? "new"}` : "closed"}
      open={open}
      onOpenChange={onOpenChange}
      series={series}
      onSaved={onSaved}
    />
  );
}

function SeriesFormBody({ open, onOpenChange, series, onSaved }: SeriesFormProps) {
  const isEdit = Boolean(series);
  const queryClient = useQueryClient();

  const [form, setForm] = useState<SeriesCreateInput>(() => initialForm(series));
  const [errors, setErrors] = useState<Record<string, string>>({});

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (isEdit && series) {
        const patch = buildEditPayload(form);
        await updateAdminSeries(series.id, patch);
        return;
      }
      await createAdminSeries(form);
    },
    onSuccess: () => {
      toast.success(isEdit ? "系列已更新" : "系列已创建");
      queryClient.invalidateQueries({ queryKey: ["admin", "series"] });
      onOpenChange(false);
      onSaved?.();
    },
    // 失败：全局 MutationCache onError 已 toast + console.error（R-7）
  });

  const levelName = useMemo(
    () => LEVEL_NAME_PRESETS.find((l) => l.code === form.level_code)?.name ?? "",
    [form.level_code],
  );

  function patch<K extends keyof SeriesCreateInput>(key: K, value: SeriesCreateInput[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: "" }));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const next = validate(form);
    setErrors(next);
    if (Object.keys(next).length > 0) {
      // a11y 3.3.1：焦点移到第一个错误字段（提供到达错误的路径）
      focusFirstFieldError(next, FIELD_SELECTORS);
      return;
    }
    saveMutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? `编辑系列 · ${series?.series_code}` : "创建系列"}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <FieldRow id="series-code" label="系列编码" required error={errors.series_code}
            hint={isEdit ? "编码创建后不可修改" : "唯一编码，如 ES-EN-BASIC-01"}>
            <Input
              value={form.series_code ?? ""}
              onChange={(e) => patch("series_code", e.target.value)}
              disabled={isEdit}
              placeholder="2-64 字符"
            />
          </FieldRow>

          <FieldRow id="series-name" label="系列名称" required error={errors.series_name}>
            <Input
              value={form.series_name ?? ""}
              onChange={(e) => patch("series_name", e.target.value)}
              placeholder="如：雅思基础入门系列"
            />
          </FieldRow>

          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="series-subject" label="学科" required error={errors.subject_code}>
              <NativeSelect
                value={form.subject_code ?? ""}
                onChange={(e) => patch("subject_code", e.target.value)}
              >
                <option value="" disabled>选择学科</option>
                {ADMIN_SUBJECT_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </NativeSelect>
            </FieldRow>
            <FieldRow id="series-level" label="难度分级" required error={errors.level_code}>
              <NativeSelect
                value={form.level_code ?? ""}
                onChange={(e) => patch("level_code", e.target.value)}
              >
                <option value="" disabled>选择分级</option>
                {ADMIN_LEVEL_OPTIONS.map((l) => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </NativeSelect>
            </FieldRow>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* 多子元素（Input + 预填按钮）：FieldRow 不会自动注入 aria，控件手动关联 */}
            <FieldRow id="series-level-name" label="分级名称" required error={errors.level_name}>
              <Input
                id="series-level-name"
                aria-invalid={errors.level_name ? true : undefined}
                aria-describedby={errors.level_name ? "series-level-name-error" : undefined}
                value={form.level_name ?? ""}
                onChange={(e) => patch("level_name", e.target.value)}
                placeholder="如：入门"
              />
              {levelName && (
                <button
                  type="button"
                  className="mt-1 text-[12px] text-indigo-600 hover:underline"
                  onClick={() => patch("level_name", levelName)}
                >
                  按分级预填「{levelName}」
                </button>
              )}
            </FieldRow>
            <FieldRow id="series-target-hours" label="目标课时（小时）">
              <Input
                type="number"
                min={0}
                step="0.5"
                value={form.target_hours ?? 0}
                onChange={(e) => patch("target_hours", e.target.value === "" ? 0 : Number(e.target.value))}
              />
            </FieldRow>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="series-sale-status" label="销售状态">
              <NativeSelect
                value={form.sale_status ?? "on_sale"}
                onChange={(e) => patch("sale_status", e.target.value)}
              >
                {SALE_STATUS_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </NativeSelect>
            </FieldRow>
            <FieldRow id="series-sort-no" label="排序号">
              <Input
                type="number"
                value={form.sort_no ?? 0}
                onChange={(e) => patch("sort_no", e.target.value === "" ? 0 : Number(e.target.value))}
              />
            </FieldRow>
          </div>

          <FieldRow id="series-description" label="简介">
            <Textarea
              value={form.description ?? ""}
              onChange={(e) => patch("description", e.target.value)}
              placeholder="系列简介（选填）"
              rows={3}
            />
          </FieldRow>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "保存中…" : isEdit ? "保存修改" : "创建系列"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------- 纯函数（可单测） ---------------- */

export function initialForm(series?: AdminSeriesItem | null): SeriesCreateInput {
  if (series) {
    return {
      series_code: series.series_code,
      series_name: series.series_name,
      subject_code: series.subject_code,
      level_code: series.level_code,
      level_name: series.level_name,
      description: series.description ?? "",
      cover_url: series.cover_url ?? "",
      target_hours: Number(series.target_hours ?? 0),
      sale_status: series.sale_status,
      sort_no: series.sort_no ?? 0,
    };
  }
  return {
    series_code: "",
    series_name: "",
    subject_code: "",
    level_code: "",
    level_name: "",
    description: "",
    cover_url: "",
    target_hours: 0,
    sale_status: "on_sale",
    sort_no: 0,
  };
}

/** 编辑模式只提交非空字段（对齐后端 SeriesAdminUpdate 全 Optional） */
export function buildEditPayload(form: SeriesCreateInput): Partial<SeriesCreateInput> {
  const patch: Partial<SeriesCreateInput> = {};
  if (form.series_name.trim()) patch.series_name = form.series_name.trim();
  if (form.subject_code) patch.subject_code = form.subject_code;
  if (form.level_code) patch.level_code = form.level_code;
  if (form.level_name.trim()) patch.level_name = form.level_name.trim();
  if (form.description) patch.description = form.description;
  if (form.cover_url) patch.cover_url = form.cover_url;
  if (typeof form.target_hours === "number") patch.target_hours = form.target_hours;
  if (form.sale_status) patch.sale_status = form.sale_status;
  if (typeof form.sort_no === "number") patch.sort_no = form.sort_no;
  return patch;
}

export function validate(form: SeriesCreateInput): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.series_code.trim()) errors.series_code = "请输入系列编码";
  else if (form.series_code.trim().length < 2) errors.series_code = "编码至少 2 个字符";
  if (!form.series_name.trim()) errors.series_name = "请输入系列名称";
  if (!form.subject_code) errors.subject_code = "请选择学科";
  if (!form.level_code) errors.level_code = "请选择难度分级";
  if (!form.level_name.trim()) errors.level_name = "请输入分级名称";
  return errors;
}
