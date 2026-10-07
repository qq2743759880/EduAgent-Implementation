/**
 * SeriesForm — 系列创建/编辑弹窗（task56 重构，对齐 domains.course_admin）
 *  - create：POST /api/admin/courses/series（institution_id + delivery_mode + code + name + sale_status 必填）
 *  - edit：PATCH /api/admin/courses/series/{id}（仅提交 Update 允许字段；series_code/institution_id 创建后不可改）
 *  - 写操作走 useMutation（L3），失败由全局 MutationCache → toast + console.error，不静默吞错（R-7）
 */
"use client";

import type { FormEvent } from "react";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DELIVERY_MODE_OPTIONS,
  SALE_STATUS_OPTIONS,
  createAdminSeries,
  updateAdminSeries,
  type AdminSeriesListItem,
  type SeriesCreateInput,
} from "@/lib/api/admin/courses";
import { FieldRow, NativeSelect, focusFirstFieldError } from "@/components/admin/controls";

export interface SeriesFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 传入 series 为编辑模式；不传为创建模式 */
  series?: AdminSeriesListItem | null;
  onSaved?: () => void;
}

/** 校验失败后焦点定位：字段 key → 控件选择器（与下方 FieldRow id 对应） */
const FIELD_SELECTORS: Record<string, string> = {
  series_code: "#series-code",
  series_name: "#series-name",
  institution_id: "#series-institution",
  delivery_mode: "#series-delivery",
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
      queryClient.invalidateQueries({ queryKey: ["admin", "courses", "series"] });
      onOpenChange(false);
      onSaved?.();
    },
    // 失败：全局 MutationCache onError 已 toast + console.error（R-7）
  });

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
          <DialogTitle>{isEdit ? `编辑系列 · ${series?.series_code}` : "新建系列"}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="series-code" label="系列编码" required error={errors.series_code}
              hint={isEdit ? "编码创建后不可修改" : "唯一编码，如 PY001"}>
              <Input
                id="series-code"
                value={form.series_code ?? ""}
                onChange={(e) => patch("series_code", e.target.value)}
                disabled={isEdit}
                placeholder="2-64 字符"
              />
            </FieldRow>
            <FieldRow id="series-institution" label="机构 ID" required error={errors.institution_id}>
              <Input
                id="series-institution"
                type="number"
                min={1}
                value={form.institution_id || ""}
                onChange={(e) => patch("institution_id", e.target.value === "" ? 0 : Number(e.target.value))}
                disabled={isEdit}
                placeholder="如 1"
              />
            </FieldRow>
          </div>

          <FieldRow id="series-name" label="系列名称" required error={errors.series_name}>
            <Input
              id="series-name"
              value={form.series_name ?? ""}
              onChange={(e) => patch("series_name", e.target.value)}
              placeholder="如：零基础 Python 入门营"
            />
          </FieldRow>

          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="series-delivery" label="交付模式" required error={errors.delivery_mode}>
              <NativeSelect
                id="series-delivery"
                value={form.delivery_mode ?? ""}
                onChange={(e) => patch("delivery_mode", e.target.value as SeriesCreateInput["delivery_mode"])}
              >
                <option value="" disabled>选择交付模式</option>
                {DELIVERY_MODE_OPTIONS.map((d) => (
                  <option key={d.value} value={d.value}>{d.label}</option>
                ))}
              </NativeSelect>
            </FieldRow>
            <FieldRow id="series-sale-status" label="上下架状态">
              <NativeSelect
                value={form.sale_status ?? "draft"}
                onChange={(e) => patch("sale_status", e.target.value as SeriesCreateInput["sale_status"])}
              >
                {SALE_STATUS_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </NativeSelect>
            </FieldRow>
          </div>

          <FieldRow id="series-cover" label="封面 URL">
            <Input
              value={form.cover_url ?? ""}
              onChange={(e) => patch("cover_url", e.target.value)}
              placeholder="https://…（选填）"
            />
          </FieldRow>

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

export function initialForm(series?: AdminSeriesListItem | null): SeriesCreateInput {
  if (series) {
    return {
      institution_id: Number(series.institution_id),
      delivery_mode: series.delivery_mode,
      series_code: series.series_code,
      series_name: series.series_name,
      description: series.description ?? "",
      cover_url: series.cover_url ?? "",
      sale_status: series.sale_status,
    };
  }
  return {
    institution_id: 0,
    delivery_mode: "online_live",
    series_code: "",
    series_name: "",
    description: "",
    cover_url: "",
    sale_status: "draft",
  };
}

/** 编辑模式只提交 Update 允许字段（series_code/institution_id 不可改，Delta 算法） */
export function buildEditPayload(form: SeriesCreateInput): Partial<SeriesCreateInput> {
  const patch: Partial<SeriesCreateInput> = {};
  if (form.delivery_mode) patch.delivery_mode = form.delivery_mode;
  if (form.series_name.trim()) patch.series_name = form.series_name.trim();
  if (form.description) patch.description = form.description;
  if (form.cover_url) patch.cover_url = form.cover_url;
  if (form.sale_status) patch.sale_status = form.sale_status;
  return patch;
}

export function validate(form: SeriesCreateInput): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.series_code.trim()) errors.series_code = "请输入系列编码";
  else if (form.series_code.trim().length < 2) errors.series_code = "编码至少 2 个字符";
  if (!form.series_name.trim()) errors.series_name = "请输入系列名称";
  if (!form.institution_id || form.institution_id <= 0) errors.institution_id = "请输入机构 ID";
  if (!form.delivery_mode) errors.delivery_mode = "请选择交付模式";
  return errors;
}