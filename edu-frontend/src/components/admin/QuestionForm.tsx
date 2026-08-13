/**
 * QuestionForm — 题目创建/编辑（task03）
 *  - 5 题型分发：single_choice / multi_choice / true_false / fill_blank / short_answer
 *    （题型枚举以后端 question_admin.schemas 为准，勿用 design-guide 摘要）
 *  - options_json 为 [{label, content}] 数组；correct_answer：
 *      单选 = 选项 label（如 "A"）；多选 = 逗号分隔 label（如 "A,C"）
 *      判断 = "对"/"错"；填空/简答 = 文本
 *  - tag_ids 多选（标签来自 GET /api/admin/questions/tags）
 *  - embedded=true 时不包 Dialog（题目编辑页整页使用）；否则弹窗（题库列表页新建）
 *  - 写操作 useMutation（L3）+ 失败全局 toast（R-7）
 */
"use client";

import type { FormEvent } from "react";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  QUESTION_DIFFICULTY_OPTIONS,
  QUESTION_SUBJECT_OPTIONS,
  QUESTION_TYPE_OPTIONS,
  TRUE_FALSE_ANSWERS,
  buildOptionLabels,
  createQuestion,
  listQuestionTags,
  updateQuestion,
  type QuestionAdminDetail,
  type QuestionCreateInput,
  type QuestionOption,
} from "@/lib/api/admin/questions";
import { FieldRow, NativeSelect, NO_TAG_HINT, TagChip, focusFirstFieldError } from "@/components/admin/controls";

export interface QuestionFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 传入 question 为编辑模式；不传为创建模式 */
  question?: QuestionAdminDetail | null;
  defaultSubject?: string;
  /** 创建成功后跳转编辑页用（题目列表页） */
  onCreated?: (id: number) => void;
  embedded?: boolean;
}

/** 校验失败后焦点定位：字段 key → 控件选择器（与下方 FieldRow id 对应；correct_answer 按题型动态解析） */
const FIELD_SELECTORS: Record<string, string> = {
  question_code: "#qf-question-code",
  default_score: "#qf-default-score",
  subject_code: "#qf-subject",
  question_type: "#qf-type",
  difficulty_level: "#qf-difficulty",
  stem_html: "#qf-stem",
  correct_answer: "",
};

function correctAnswerFocusSelector(type: string): string {
  if (type === "single_choice" || type === "multi_choice") return '[data-testid="option-correct-A"]';
  if (type === "true_false") return '[data-testid="tf-对"]';
  return "#qf-correct-answer";
}

interface QuestionFormState {
  question_code: string;
  subject_code: string;
  question_type: string;
  difficulty_level: string;
  stem_html: string;
  analysis_html: string;
  options: QuestionOption[];
  correct_answer: string;
  correct_answer_detail: string;
  default_score: number;
  knowledge_points: string;
  tag_ids: number[];
}

export function QuestionForm(props: QuestionFormProps) {
  const { open, embedded } = props;
  // key 切换触发重挂载：弹窗每次打开（open→true）重置表单，编辑页以 question 身份保持
  return (
    <QuestionFormBody
      key={embedded ? `embedded-${props.question?.id ?? "new"}` : open ? "open" : "closed"}
      {...props}
    />
  );
}

function QuestionFormBody({
  open,
  onOpenChange,
  question,
  defaultSubject,
  onCreated,
  embedded = false,
}: QuestionFormProps) {
  const isEdit = Boolean(question);
  const queryClient = useQueryClient();

  const tagsQ = useQuery({
    queryKey: ["admin", "questions", "tags"] as const,
    queryFn: () => listQuestionTags(),
    staleTime: 60_000,
  });

  const [form, setForm] = useState<QuestionFormState>(() => initialForm(question, defaultSubject));
  const [errors, setErrors] = useState<Record<string, string>>({});

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = buildQuestionPayload(form);
      if (isEdit && question) {
        await updateQuestion(question.id, payload);
        return { id: question.id };
      }
      return createQuestion(payload);
    },
    onSuccess: (resp) => {
      toast.success(isEdit ? "题目已更新" : "题目已创建");
      queryClient.invalidateQueries({ queryKey: ["admin", "questions"] });
      if (isEdit) {
        onOpenChange(false);
      } else {
        onOpenChange(false);
        onCreated?.(resp.id);
      }
    },
    // 失败 → 全局 MutationCache onError toast（R-7）
  });

  const tags = tagsQ.data ?? [];

  function patch<K extends keyof QuestionFormState>(key: K, value: QuestionFormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => ({ ...prev, [key]: "" }));
  }

  function toggleTag(tagId: number) {
    setForm((prev) => ({
      ...prev,
      tag_ids: prev.tag_ids.includes(tagId)
        ? prev.tag_ids.filter((t) => t !== tagId)
        : [...prev.tag_ids, tagId],
    }));
  }

  function setOptionContent(idx: number, content: string) {
    setForm((prev) => {
      const options = prev.options.map((o, i) => (i === idx ? { ...o, content } : o));
      return { ...prev, options };
    });
  }

  function addOption() {
    setForm((prev) => {
      const labels = buildOptionLabels(prev.options.length + 1);
      const options = [...prev.options, { label: labels[prev.options.length], content: "" }];
      return { ...prev, options, correct_answer: "" };
    });
  }

  function removeOption(idx: number) {
    setForm((prev) => {
      const options = prev.options.filter((_, i) => i !== idx);
      return { ...prev, options, correct_answer: "" };
    });
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const next = validateForm(form);
    setErrors(next);
    if (Object.keys(next).length > 0) {
      toast.warning("请检查表单必填项");
      // a11y 3.3.1：焦点移到第一个错误字段（提供到达错误的路径）
      focusFirstFieldError(next, { ...FIELD_SELECTORS, correct_answer: correctAnswerFocusSelector(form.question_type) });
      return;
    }
    saveMutation.mutate();
  }

  const isChoice = form.question_type === "single_choice" || form.question_type === "multi_choice";

  const body = (
    <form onSubmit={handleSubmit} className="space-y-4" data-testid="question-form">
      <div className="grid grid-cols-2 gap-3">
        <FieldRow id="qf-question-code" label="题目编码" required error={errors.question_code}
          hint={isEdit ? "编码创建后不可修改" : "唯一编码，如 Q-MATH-SINGLE-001"}>
          <Input
            value={form.question_code}
            onChange={(e) => patch("question_code", e.target.value)}
            disabled={isEdit}
            placeholder="64 字符内唯一"
          />
        </FieldRow>
        <FieldRow id="qf-default-score" label="默认分值" required error={errors.default_score}>
          <Input
            type="number"
            min={0}
            value={form.default_score}
            onChange={(e) => patch("default_score", e.target.value === "" ? 0 : Number(e.target.value))}
          />
        </FieldRow>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <FieldRow id="qf-subject" label="学科" required error={errors.subject_code}>
          <NativeSelect value={form.subject_code} onChange={(e) => patch("subject_code", e.target.value)}>
            <option value="" disabled>选择学科</option>
            {QUESTION_SUBJECT_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </NativeSelect>
        </FieldRow>
        <FieldRow id="qf-type" label="题型" required error={errors.question_type}>
          <NativeSelect
            value={form.question_type}
            onChange={(e) => patch("question_type", e.target.value)}
            data-testid="question-type-select"
          >
            <option value="" disabled>选择题型</option>
            {QUESTION_TYPE_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </NativeSelect>
        </FieldRow>
        <FieldRow id="qf-difficulty" label="难度" required error={errors.difficulty_level}>
          <NativeSelect value={form.difficulty_level} onChange={(e) => patch("difficulty_level", e.target.value)}>
            {QUESTION_DIFFICULTY_OPTIONS.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </NativeSelect>
        </FieldRow>
      </div>

      <FieldRow id="qf-stem" label="题干" required error={errors.stem_html}>
        <Textarea
          value={form.stem_html}
          onChange={(e) => patch("stem_html", e.target.value)}
          placeholder="题干（支持 HTML/Markdown 片段）"
          rows={3}
        />
      </FieldRow>

      {/* 选项编辑（单选/多选） */}
      {isChoice && (
        <ChoiceEditor
          options={form.options}
          type={form.question_type as "single_choice" | "multi_choice"}
          correctAnswer={form.correct_answer}
          error={errors.correct_answer}
          onContentChange={setOptionContent}
          onAdd={addOption}
          onRemove={removeOption}
          onCorrectChange={(answer) => patch("correct_answer", answer)}
        />
      )}

      {/* 判断题 */}
      {form.question_type === "true_false" && (
        <FieldRow id="qf-tf" label="正确答案" required error={errors.correct_answer}>
          <div className="flex gap-2">
            {TRUE_FALSE_ANSWERS.map((a) => (
              <button
                key={a.value}
                type="button"
                data-testid={`tf-${a.value}`}
                aria-pressed={form.correct_answer === a.value}
                aria-describedby={errors.correct_answer ? "qf-tf-error" : undefined}
                onClick={() => patch("correct_answer", a.value)}
                className={
                  form.correct_answer === a.value
                    ? "rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white"
                    : "rounded-lg border border-slate-200 px-4 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
                }
              >
                {a.label}
              </button>
            ))}
          </div>
        </FieldRow>
      )}

      {/* 填空 / 简答 */}
      {(form.question_type === "fill_blank" || form.question_type === "short_answer") && (
        <FieldRow
          id="qf-correct-answer"
          label={form.question_type === "fill_blank" ? "填空答案" : "参考答案"}
          required
          error={errors.correct_answer}
        >
          <Textarea
            value={form.correct_answer}
            onChange={(e) => patch("correct_answer", e.target.value)}
            placeholder={form.question_type === "fill_blank" ? "如：transformation" : "参考答案要点"}
            rows={2}
          />
        </FieldRow>
      )}

      <FieldRow id="qf-analysis" label="答案解析" hint="选填">
        <Textarea
          value={form.analysis_html}
          onChange={(e) => patch("analysis_html", e.target.value)}
          rows={2}
        />
      </FieldRow>

      <FieldRow id="qf-knowledge-points" label="知识点编码" hint="多个用英文逗号分隔，自动序列化为数组">
        <Input
          value={form.knowledge_points}
          onChange={(e) => patch("knowledge_points", e.target.value)}
          placeholder="如：grammar.passive, vocab.ielts"
        />
      </FieldRow>

      <FieldRow id="qf-tags" label="标签" error={errors.tag_ids} hint={tagsQ.isLoading ? "标签加载中…" : undefined}>
        {tags.length === 0 && !tagsQ.isLoading ? (
          <p className="text-[12px] text-slate-500">{NO_TAG_HINT}</p>
        ) : (
          <div className="flex flex-wrap gap-2" data-testid="tag-list">
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

      {!embedded && (
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button type="submit" disabled={saveMutation.isPending}>
            {saveMutation.isPending ? "保存中…" : isEdit ? "保存修改" : "创建题目"}
          </Button>
        </DialogFooter>
      )}

      {embedded && (
        <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
          <span className="mr-auto text-[12px] text-slate-500">
            {isEdit ? `题目 ID ${question?.id}` : "新建题目"}
          </span>
          <Button type="submit" disabled={saveMutation.isPending} data-testid="embedded-save">
            {saveMutation.isPending ? "保存中…" : "保存修改"}
          </Button>
        </div>
      )}
    </form>
  );

  if (embedded) return body;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? `编辑题目 · ${question?.question_code}` : "新建题目"}</DialogTitle>
        </DialogHeader>
        {body}
      </DialogContent>
    </Dialog>
  );
}

/* ---------------- 选项编辑器 ---------------- */
function ChoiceEditor({
  options,
  type,
  correctAnswer,
  error,
  onContentChange,
  onAdd,
  onRemove,
  onCorrectChange,
}: {
  options: QuestionOption[];
  type: "single_choice" | "multi_choice";
  correctAnswer: string;
  error?: string;
  onContentChange: (idx: number, content: string) => void;
  onAdd: () => void;
  onRemove: (idx: number) => void;
  onCorrectChange: (answer: string) => void;
}) {
  const correctSet = useMemo(() => new Set(correctAnswer.split(",").map((s) => s.trim()).filter(Boolean)), [correctAnswer]);
  return (
    <FieldRow
      id="qf-options"
      label={type === "single_choice" ? "选项（单选正确项）" : "选项（多选正确项）"}
      required
      error={error}
    >
      <div className="space-y-2">
        {options.map((opt, idx) => {
          const checked = correctSet.has(opt.label);
          const toggle = () => {
            if (type === "single_choice") {
              onCorrectChange(opt.label);
            } else {
              const next = new Set(correctSet);
              if (next.has(opt.label)) next.delete(opt.label);
              else next.add(opt.label);
              onCorrectChange([...next].sort().join(","));
            }
          };
          return (
            <div key={opt.label} className="flex items-start gap-2">
              <button
                type="button"
                onClick={toggle}
                data-testid={`option-correct-${opt.label}`}
                aria-pressed={checked}
                aria-describedby={error ? "qf-options-error" : undefined}
                className={
                  checked
                    ? "mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[12px] font-semibold text-white"
                    : "mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-slate-300 text-[12px] text-slate-500"
                }
                aria-label={`选项 ${opt.label} 标记为${type === "single_choice" ? "正确答案" : "正确项"}`}
              >
                {opt.label}
              </button>
              <Input
                value={opt.content}
                onChange={(e) => onContentChange(idx, e.target.value)}
                placeholder={`选项 ${opt.label} 内容`}
                className="flex-1"
              />
              {options.length > 2 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`删除选项 ${opt.label}`}
                  onClick={() => onRemove(idx)}
                >
                  <Trash2 className="h-3.5 w-3.5 text-rose-500" />
                </Button>
              )}
            </div>
          );
        })}
        <Button type="button" variant="outline" size="sm" onClick={onAdd}>
          <Plus className="mr-1 h-3.5 w-3.5" /> 添加选项
        </Button>
      </div>
    </FieldRow>
  );
}

/* ---------------- 纯函数（可单测） ---------------- */

export function initialForm(
  question?: QuestionAdminDetail | null,
  defaultSubject?: string,
): QuestionFormState {
  if (question) {
    return {
      question_code: question.question_code,
      subject_code: question.subject_code,
      question_type: question.question_type,
      difficulty_level: question.difficulty_level,
      stem_html: question.stem_html,
      analysis_html: question.analysis_html ?? "",
      options: (question.options_json ?? []).map((o) => ({ label: o.label, content: o.content })),
      correct_answer: question.correct_answer ?? "",
      correct_answer_detail: question.correct_answer_detail ?? "",
      default_score: question.default_score ?? 5,
      knowledge_points: (question.knowledge_point_codes ?? []).join(", "),
      tag_ids: (question.tags ?? []).map((t) => t.id),
    };
  }
  return {
    question_code: "",
    subject_code: defaultSubject ?? "",
    question_type: "",
    difficulty_level: "L2",
    stem_html: "",
    analysis_html: "",
    options: [
      { label: "A", content: "" },
      { label: "B", content: "" },
      { label: "C", content: "" },
      { label: "D", content: "" },
    ],
    correct_answer: "",
    correct_answer_detail: "",
    default_score: 5,
    knowledge_points: "",
    tag_ids: [],
  };
}

/** 表单 → 后端 QuestionCreateInput（knowledge_point_codes 逗号拆分、tag_ids 去重） */
export function buildQuestionPayload(form: QuestionFormState): QuestionCreateInput {
  return {
    question_code: form.question_code.trim(),
    subject_code: form.subject_code,
    question_type: form.question_type,
    difficulty_level: form.difficulty_level,
    stem_html: form.stem_html.trim(),
    analysis_html: form.analysis_html.trim() || undefined,
    options_json: form.options
      .map((o) => ({ label: o.label, content: o.content.trim() }))
      .filter((o) => o.content !== ""),
    correct_answer: form.correct_answer.trim(),
    correct_answer_detail: form.correct_answer_detail.trim() || undefined,
    default_score: Number(form.default_score || 0),
    knowledge_point_codes: [
      ...new Set(
        form.knowledge_points
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      ),
    ],
    tag_ids: [...new Set(form.tag_ids)],
  };
}

export function validateForm(form: QuestionFormState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.question_code.trim()) errors.question_code = "请输入题目编码";
  if (!form.subject_code) errors.subject_code = "请选择学科";
  if (!form.question_type) errors.question_type = "请选择题型";
  if (!form.difficulty_level) errors.difficulty_level = "请选择难度";
  if (!form.stem_html.trim()) errors.stem_html = "请输入题干";
  if (typeof form.default_score !== "number" || Number.isNaN(form.default_score) || form.default_score < 0) {
    errors.default_score = "分值不能为负";
  }

  if (form.question_type === "single_choice" || form.question_type === "multi_choice") {
    const filled = form.options.filter((o) => o.content.trim());
    if (filled.length < 2) errors.correct_answer = "至少需要 2 个有效选项";
    else if (!form.correct_answer.trim()) errors.correct_answer = "请标记正确选项";
  }
  if (form.question_type === "true_false" && !form.correct_answer.trim()) {
    errors.correct_answer = "请选择对/错";
  }
  if (
    (form.question_type === "fill_blank" || form.question_type === "short_answer") &&
    !form.correct_answer.trim()
  ) {
    errors.correct_answer = "请输入答案";
  }
  return errors;
}
