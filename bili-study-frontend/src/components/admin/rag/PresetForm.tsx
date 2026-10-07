/**
 * PresetForm — 新建 RAG 参数预设弹窗（task04）
 *  - 字段对齐 ParamPresetCreate：preset_name / is_default / top_k / final_max_k /
 *    cutoff_drop_ratio / rrf_k / use_hyde / enable_graph / llm_model_pref / description
 *  - is_default=true 提交 → 后端事务把旧 default 置 0（唯一默认项）
 *  - 写操作 useMutation（L3）；失败全局 MutationCache → toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldRow, NativeSelect } from "@/components/admin/controls";
import {
  RAG_MODEL_OPTIONS,
  createRagPreset,
  type RagPresetInput,
} from "@/lib/api/admin/rag";

export interface PresetFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export interface PresetFormState {
  preset_name: string;
  is_default: boolean;
  description: string;
  top_k: number;
  final_max_k: number;
  cutoff_drop_ratio: number;
  rrf_k: number;
  use_hyde: boolean;
  enable_graph: boolean;
  llm_model_pref: string;
}

export function initialPresetForm(): PresetFormState {
  return {
    preset_name: "",
    is_default: false,
    description: "",
    top_k: 20,
    final_max_k: 6,
    cutoff_drop_ratio: 0.4,
    rrf_k: 60,
    use_hyde: true,
    enable_graph: true,
    llm_model_pref: "fast",
  };
}

export function PresetForm({ open, onOpenChange }: PresetFormProps) {
  return (
    <PresetFormBody
      key={open ? "open" : "closed"}
      open={open}
      onOpenChange={onOpenChange}
    />
  );
}

function PresetFormBody({ open, onOpenChange }: PresetFormProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<PresetFormState>(initialPresetForm);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const saveMutation = useMutation({
    mutationFn: () => createRagPreset(buildPresetPayload(form)),
    onSuccess: () => {
      toast.success(form.is_default ? "预设已创建并设为默认" : "预设已创建");
      queryClient.invalidateQueries({ queryKey: ["admin", "rag", "presets"] });
      onOpenChange(false);
    },
    // 失败：全局 MutationCache onError → toast（R-7）
  });

  function patch<K extends keyof PresetFormState>(key: K, value: PresetFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: "" }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next = validatePresetForm(form);
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    saveMutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>新建参数预设</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <FieldRow label="预设名称" required error={errors.preset_name}>
            <Input
              id="preset-name"
              value={form.preset_name}
              onChange={(e) => patch("preset_name", e.target.value)}
              placeholder="如：高召回-考试场景（2-64 字符）"
              aria-invalid={Boolean(errors.preset_name)}
              aria-describedby={errors.preset_name ? "preset-name-error-desc" : undefined}
              data-testid="preset-name"
            />
            {errors.preset_name && (
              <span id="preset-name-error-desc" className="sr-only">{errors.preset_name}</span>
            )}
          </FieldRow>

          <label htmlFor="preset-is-default" className="flex items-center gap-2 text-[13px] text-slate-700">
            <Checkbox
              id="preset-is-default"
              checked={form.is_default}
              onCheckedChange={(v) => patch("is_default", v === true)}
              aria-label="设为默认预设（旧默认将自动取消）"
              data-testid="preset-is-default"
            />
            设为默认预设（旧默认将自动取消）
          </label>

          <div className="grid grid-cols-2 gap-3">
            <FieldRow label="召回 top_k">
              <Input
                id="preset-top-k"
                type="number"
                min={1}
                max={200}
                value={form.top_k}
                onChange={(e) => patch("top_k", e.target.value === "" ? 20 : Number(e.target.value))}
                aria-invalid={Boolean(errors.top_k)}
                aria-describedby={errors.top_k ? "preset-top-k-error-desc" : undefined}
              />
              {errors.top_k && (
                <span id="preset-top-k-error-desc" className="sr-only">{errors.top_k}</span>
              )}
            </FieldRow>
            <FieldRow label="最终 final_max_k">
              <Input
                id="preset-final-max-k"
                type="number"
                min={1}
                max={30}
                value={form.final_max_k}
                onChange={(e) => patch("final_max_k", e.target.value === "" ? 6 : Number(e.target.value))}
                aria-invalid={Boolean(errors.final_max_k)}
                aria-describedby={errors.final_max_k ? "preset-final-max-k-error-desc" : undefined}
              />
              {errors.final_max_k && (
                <span id="preset-final-max-k-error-desc" className="sr-only">{errors.final_max_k}</span>
              )}
            </FieldRow>
            <FieldRow label="断崖阈值 cutoff_drop_ratio">
              <Input
                id="preset-cutoff"
                type="number"
                min={0.05}
                max={0.9}
                step={0.05}
                value={form.cutoff_drop_ratio}
                onChange={(e) => patch("cutoff_drop_ratio", e.target.value === "" ? 0.4 : Number(e.target.value))}
                aria-invalid={Boolean(errors.cutoff_drop_ratio)}
                aria-describedby={errors.cutoff_drop_ratio ? "preset-cutoff-error-desc" : undefined}
              />
              {errors.cutoff_drop_ratio && (
                <span id="preset-cutoff-error-desc" className="sr-only">{errors.cutoff_drop_ratio}</span>
              )}
            </FieldRow>
            <FieldRow label="RRF k">
              <Input
                id="preset-rrf-k"
                type="number"
                min={5}
                max={500}
                value={form.rrf_k}
                onChange={(e) => patch("rrf_k", e.target.value === "" ? 60 : Number(e.target.value))}
                aria-invalid={Boolean(errors.rrf_k)}
                aria-describedby={errors.rrf_k ? "preset-rrf-k-error-desc" : undefined}
              />
              {errors.rrf_k && (
                <span id="preset-rrf-k-error-desc" className="sr-only">{errors.rrf_k}</span>
              )}
            </FieldRow>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <FieldRow label="LLM 模型偏好">
              <NativeSelect
                id="preset-llm-model"
                value={form.llm_model_pref}
                onChange={(e) => patch("llm_model_pref", e.target.value)}
              >
                {RAG_MODEL_OPTIONS.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </NativeSelect>
            </FieldRow>
            <div className="flex items-end gap-4 pb-1">
              <label htmlFor="preset-use-hyde" className="flex items-center gap-2 text-[13px] text-slate-700">
                <Checkbox
                  id="preset-use-hyde"
                  checked={form.use_hyde}
                  onCheckedChange={(v) => patch("use_hyde", v === true)}
                  aria-label="HyDE"
                  data-testid="preset-use-hyde"
                />
                HyDE
              </label>
              <label htmlFor="preset-enable-graph" className="flex items-center gap-2 text-[13px] text-slate-700">
                <Checkbox
                  id="preset-enable-graph"
                  checked={form.enable_graph}
                  onCheckedChange={(v) => patch("enable_graph", v === true)}
                  aria-label="图谱"
                  data-testid="preset-enable-graph"
                />
                图谱
              </label>
            </div>
          </div>

          <FieldRow label="描述">
            <Textarea
              id="preset-description"
              value={form.description}
              onChange={(e) => patch("description", e.target.value)}
              placeholder="预设用途说明（选填）"
              rows={2}
            />
          </FieldRow>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type="submit" disabled={saveMutation.isPending} data-testid="preset-submit">
              {saveMutation.isPending ? "创建中…" : "创建预设"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------- 纯函数（可单测） ---------------- */

export function buildPresetPayload(form: PresetFormState): RagPresetInput {
  return {
    preset_name: form.preset_name.trim(),
    is_default: form.is_default,
    description: form.description.trim() || null,
    top_k: form.top_k,
    final_max_k: form.final_max_k,
    cutoff_drop_ratio: form.cutoff_drop_ratio,
    rrf_k: form.rrf_k,
    use_hyde: form.use_hyde,
    enable_graph: form.enable_graph,
    llm_model_pref: form.llm_model_pref,
  };
}

export function validatePresetForm(form: PresetFormState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.preset_name.trim()) errors.preset_name = "请输入预设名称";
  else if (form.preset_name.trim().length < 2) errors.preset_name = "预设名称至少 2 个字符";
  else if (form.preset_name.trim().length > 64) errors.preset_name = "预设名称最多 64 字符";
  if (!Number.isFinite(form.top_k) || form.top_k < 1 || form.top_k > 200) errors.top_k = "top_k 范围 1-200";
  if (!Number.isFinite(form.final_max_k) || form.final_max_k < 1 || form.final_max_k > 30) errors.final_max_k = "final_max_k 范围 1-30";
  if (!Number.isFinite(form.cutoff_drop_ratio) || form.cutoff_drop_ratio < 0.05 || form.cutoff_drop_ratio > 0.9) errors.cutoff_drop_ratio = "范围 0.05-0.9";
  if (!Number.isFinite(form.rrf_k) || form.rrf_k < 5 || form.rrf_k > 500) errors.rrf_k = "rrf_k 范围 5-500";
  return errors;
}
