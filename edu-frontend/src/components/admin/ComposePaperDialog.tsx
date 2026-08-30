/**
 * ComposePaperDialog — 自动组卷（task03）
 *  - POST /api/admin/questions/papers/compose
 *    body: { spec: {subject_code, difficulty_level?, tag_ids[], per_question_score, total_score, duration_minutes, pass_score},
 *            paper_code, paper_title, expected_question_count }
 *  - 结果展示 draft_paper_id / selected_count / total_score（后端已生成草稿试卷）
 *  - 写操作 useMutation + 失败全局 toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileCheck2, ListChecks } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  QUESTION_DIFFICULTY_OPTIONS,
  QUESTION_SUBJECT_OPTIONS,
  composePaper,
  listQuestionTags,
  type PaperComposeResult,
} from "@/lib/api/admin/questions";
import { FieldRow, NativeSelect, NO_TAG_HINT, TagChip } from "@/components/admin/controls";

export interface ComposePaperDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultSubject?: string;
}

interface ComposeForm {
  subject_code: string;
  difficulty_level: string;
  tag_ids: number[];
  per_question_score: number;
  question_count: number;
  paper_code: string;
  paper_title: string;
  total_score: number;
  duration_minutes: number;
  pass_score: number;
}

export function ComposePaperDialog({ open, onOpenChange, defaultSubject }: ComposePaperDialogProps) {
  const [form, setForm] = useState<ComposeForm>(() => initialComposeForm(defaultSubject));
  const [result, setResult] = useState<PaperComposeResult | null>(null);

  const tagsQ = useQuery({
    queryKey: ["admin", "questions", "tags"] as const,
    queryFn: () => listQuestionTags(),
    staleTime: 60_000,
  });

  const composeMutation = useMutation({
    mutationFn: () =>
      composePaper({
        spec: {
          subject_code: form.subject_code,
          difficulty_level: form.difficulty_level || null,
          tag_ids: form.tag_ids,
          per_question_score: form.per_question_score,
          total_score: form.total_score,
          duration_minutes: form.duration_minutes,
          pass_score: form.pass_score,
        },
        paper_code: form.paper_code.trim(),
        paper_title: form.paper_title.trim(),
        expected_question_count: form.question_count,
      }),
    onSuccess: (resp) => {
      setResult(resp);
      toast.success(`组卷成功：选中 ${resp.selected_count} 题，共 ${resp.total_score} 分`);
    },
    // 失败 → 全局 MutationCache onError toast（R-7）
  });

  function toggleTag(tagId: number) {
    setForm((prev) => ({
      ...prev,
      tag_ids: prev.tag_ids.includes(tagId)
        ? prev.tag_ids.filter((t) => t !== tagId)
        : [...prev.tag_ids, tagId],
    }));
  }

  function handleOpenChange(next: boolean) {
    if (!next) {
      setForm(initialComposeForm(defaultSubject));
      setResult(null);
    }
    onOpenChange(next);
  }

  const tags = tagsQ.data ?? [];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ListChecks className="h-4 w-4 text-indigo-600" /> 自动组卷
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="compose-paper-code" label="试卷编码" required>
              <Input
                value={form.paper_code}
                onChange={(e) => setForm((f) => ({ ...f, paper_code: e.target.value }))}
                placeholder="如：PAPER-MATH-001"
              />
            </FieldRow>
            <FieldRow id="compose-paper-title" label="试卷标题" required>
              <Input
                value={form.paper_title}
                onChange={(e) => setForm((f) => ({ ...f, paper_title: e.target.value }))}
                placeholder="如：数学月考卷"
              />
            </FieldRow>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <FieldRow id="compose-subject" label="学科" required>
              <NativeSelect value={form.subject_code} onChange={(e) => setForm((f) => ({ ...f, subject_code: e.target.value }))}>
                <option value="" disabled>选择学科</option>
                {QUESTION_SUBJECT_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </NativeSelect>
            </FieldRow>
            <FieldRow id="compose-difficulty" label="难度（可不限）">
              <NativeSelect value={form.difficulty_level} onChange={(e) => setForm((f) => ({ ...f, difficulty_level: e.target.value }))}>
                <option value="">不限</option>
                {QUESTION_DIFFICULTY_OPTIONS.map((d) => (
                  <option key={d.value} value={d.value}>{d.label}</option>
                ))}
              </NativeSelect>
            </FieldRow>
            <FieldRow id="compose-question-count" label="题量" required>
              <Input
                type="number"
                min={1}
                max={200}
                value={form.question_count}
                onChange={(e) => setForm((f) => ({ ...f, question_count: Number(e.target.value) }))}
              />
            </FieldRow>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <FieldRow id="compose-per-question-score" label="每题分值" required>
              <Input
                type="number"
                min={1}
                value={form.per_question_score}
                onChange={(e) => setForm((f) => ({ ...f, per_question_score: Number(e.target.value) }))}
              />
            </FieldRow>
            <FieldRow id="compose-total-score" label="总分">
              <Input
                type="number"
                min={0}
                value={form.total_score}
                onChange={(e) => setForm((f) => ({ ...f, total_score: Number(e.target.value) }))}
              />
            </FieldRow>
            <FieldRow id="compose-duration" label="时长（分钟）">
              <Input
                type="number"
                min={1}
                value={form.duration_minutes}
                onChange={(e) => setForm((f) => ({ ...f, duration_minutes: Number(e.target.value) }))}
              />
            </FieldRow>
          </div>

          <FieldRow id="compose-tags" label="限定标签（可不选）" hint={tagsQ.isLoading ? "标签加载中…" : undefined}>
            {tags.length === 0 && !tagsQ.isLoading ? (
              <p className="text-[12px] text-slate-500">{NO_TAG_HINT}</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {tags.map((t) => (
                  <TagChip
                    key={t.id}
                    selected={form.tag_ids.includes(t.id)}
                    onClick={() => toggleTag(t.id)}
                  >
                    {t.tag_name}
                  </TagChip>
                ))}
              </div>
            )}
          </FieldRow>

          {result && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 text-sm space-y-1">
              <div className="flex items-center gap-2 font-medium text-emerald-800">
                <FileCheck2 className="h-4 w-4" /> 草稿已生成
              </div>
              <p className="text-emerald-700">
                试卷编号 <code className="font-mono text-xs">{result.paper_code}</code> · 选中{" "}
                <b>{result.selected_count}</b> 题 · 共 <b>{result.total_score}</b> 分
              </p>
              <p className="text-[12px] text-emerald-700">{result.message}</p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>关闭</Button>
          <Button
            onClick={() => composeMutation.mutate()}
            disabled={!form.paper_code.trim() || !form.paper_title.trim() || !form.subject_code || composeMutation.isPending}
          >
            {composeMutation.isPending ? "组卷中…" : "生成草稿试卷"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function initialComposeForm(defaultSubject?: string): ComposeForm {
  return {
    subject_code: defaultSubject ?? "",
    difficulty_level: "",
    tag_ids: [],
    per_question_score: 5,
    question_count: 20,
    paper_code: "",
    paper_title: "",
    total_score: 100,
    duration_minutes: 120,
    pass_score: 60,
  };
}
