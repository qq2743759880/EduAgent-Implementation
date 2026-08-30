/** task59 管理端题目编辑表单（contract④ question 域）。题型联动选项控件、analysis_text 必修、Markdown 预览、objective 派生徽章。已填选项按 label 归位，切题型不丢。 */
"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookMarked } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownView } from "@/components/community/MarkdownView";
import type { ReactNode } from "react";
import {
  updateQuestion,
  type QuestionDetail,
  type QuestionTypeOption,
  type QuestionUpdateInput,
} from "@/lib/api/admin/question-bank";

const LABELS = ["A", "B", "C", "D", "E", "F", "G", "H"];

type OptionRow = { key: string; text: string };

interface Props {
  questionId: number;
  bankName?: string | null;
  detail: QuestionDetail;
  types: QuestionTypeOption[];
}

function chosenLabels(answerText: string, typeCode: string | undefined): Set<string> {
  const set = new Set<string>();
  if (typeCode === "true_false") {
    if (/对|正确|true/i.test(answerText)) set.add("T");
    if (/错|错误|false/i.test(answerText)) set.add("F");
    return set;
  }
  if (typeCode !== "single_choice" && typeCode !== "multi_choice") return set;
  for (const up of [...answerText.toUpperCase()]) {
    if (LABELS.includes(up)) set.add(up);
  }
  return set;
}

function typeCodeToId(types: QuestionTypeOption[], code: string): number {
  return types.find((t) => t.type_code === code)?.id ?? 1;
}
function idToMeta(types: QuestionTypeOption[], id: number): QuestionTypeOption | undefined {
  return types.find((t) => t.id === id);
}

export function QuestionDetailEditor({ questionId, bankName, detail, types }: Props) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const initialCode = idToMeta(types, detail.question_type_id)?.type_code ?? "single_choice";
  const initialOptions: OptionRow[] =
    detail.options_json && detail.options_json.length
      ? detail.options_json.map((o) => ({ key: o.key ?? "", text: o.text ?? "" }))
      : LABELS.slice(0, 4).map((k) => ({ key: k, text: "" }));

  const [typeCode, setTypeCode] = useState(initialCode);
  const [stem, setStem] = useState(detail.stem ?? "");
  const [answerText, setAnswerText] = useState(detail.answer_text ?? "");
  const [analysis, setAnalysis] = useState(detail.analysis_text ?? "");
  const [options, setOptions] = useState<OptionRow[]>(initialOptions);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const curMeta = idToMeta(types, typeCodeToId(types, typeCode));
  const typeName = curMeta?.type_name ?? typeCode;
  const objective = curMeta?.objective_flag === 1;
  const isChoice = typeCode === "single_choice" || typeCode === "multi_choice";
  const chosen = useMemo(() => chosenLabels(answerText, typeCode), [answerText, typeCode]);

  function patchOption(key: string, text: string) {
    setOptions((prev) =>
      prev.some((o) => o.key === key)
        ? prev.map((o) => (o.key === key ? { ...o, text } : o))
        : [...prev, { key, text }],
    );
  }
  function setAnswerFromLabels(set: Set<string>) {
    setAnswerText(Array.from(set).sort((a, b) => LABELS.indexOf(a) - LABELS.indexOf(b)).join(""));
  }
  function toggleChoice(key: string) {
    if (typeCode === "single_choice") setAnswerFromLabels(chosen.has(key) ? new Set() : new Set([key]));
    else {
      const next = new Set(chosen);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      setAnswerFromLabels(next);
    }
  }
  function toggleTf(which: "T" | "F") {
    setAnswerText(which === "T" ? "正确" : "错误");
  }
  function addOption() {
    setOptions((prev) => {
      const used = new Set(prev.map((o) => o.key));
      const nextKey = LABELS.find((k) => !used.has(k));
      return nextKey ? [...prev, { key: nextKey, text: "" }] : prev;
    });
  }
  function removeOption(key: string) {
    setOptions((prev) => prev.filter((o) => o.key !== key));
  }

  function submitPayload(): QuestionUpdateInput {
    return {
      question_type_id: typeCodeToId(types, typeCode),
      stem: stem.trim(),
      answer_text: answerText.trim(),
      analysis_text: analysis.trim() || null,
      options_json: isChoice
        ? options.filter((o) => (o.text ?? "").trim()).map((o) => ({ key: o.key, text: (o.text ?? "").trim() }))
        : null,
    };
  }

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!stem.trim()) errs.stem = "题干为必填";
    if (!answerText.trim()) errs.answer = "答案为必填";
    if (!analysis.trim()) errs.analysis = "解析（analysis_text）为必填，请填写本题解析";
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  const save = useMutation({
    mutationFn: (andContinue: boolean) => updateQuestion(questionId, submitPayload()).then(() => andContinue),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "questions", questionId] });
      queryClient.invalidateQueries({ queryKey: ["admin", "bank-questions"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "question-banks"] });
    },
    onError: (err: unknown) => {
      setFieldErrors((prev) => ({ ...prev, submit: messageOf(err) }));
    },
  });

  function handleSave(andContinue: boolean) {
    if (!validate()) return;
    save.mutate(andContinue, { onSuccess: () => (!andContinue ? router.push("/admin/questions") : undefined) });
  }

  return (
    <div className="space-y-5">
      <Link href="/admin/questions" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary">
        <ArrowLeft className="h-4 w-4" /> 返回题库列表
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-border bg-card p-5">
        <div className="flex min-w-0 items-start gap-3">
          <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-candy-purple text-primary-foreground">
            <BookMarked className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-foreground">题目编辑</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>所属题库</span>
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">{bankName ?? detail.bank_id}</code>
              <span>题号</span>
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">{detail.question_code}</code>
              <ObjBadge objective={objective} typeName={typeName} />
            </div>
          </div>
        </div>
      </div>

      <Tabs defaultValue="edit">
        <TabsList>
          <TabsTrigger value="edit">编辑</TabsTrigger>
          <TabsTrigger value="preview">预览 · 与用户端 QuizPanel 一致</TabsTrigger>
        </TabsList>

        <TabsContent value="edit">
          <div className="space-y-4 rounded-xl border border-border bg-card p-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>题型</Label>
                <select
                  value={typeCode}
                  onChange={(e) => setTypeCode(e.target.value)}
                  aria-label="题型"
                  className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                >
                  {types.map((t) => (
                    <option key={t.id} value={t.type_code}>
                      {t.type_name}（{t.type_code}）
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label>
                  客观性<span className="ml-1 text-xs font-normal text-muted-foreground">派生 · 只读</span>
                </Label>
                <ObjBadge objective={objective} typeName={typeName} />
                <p className="text-xs text-muted-foreground">
                  objective_flag 派生自 dim_question_type，非 question 字段（PATCH 不提交）
                </p>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>
                题干 <span className="text-destructive">*</span>
                <span className="ml-2 text-xs font-normal text-muted-foreground">支持 Markdown / LaTeX</span>
              </Label>
              <Textarea value={stem} onChange={(e) => setStem(e.target.value)} rows={6} placeholder="请输入题干…" />
              <FieldError msg={fieldErrors.stem} />
            </div>

            <div className="space-y-1.5">
              <Label>选项 options_json</Label>
              {isChoice && (
                <ChoiceList
                  mode={typeCode === "single_choice" ? "single" : "multi"}
                  options={options}
                  chosen={chosen}
                  onToggle={toggleChoice}
                  onPatch={patchOption}
                  onAdd={addOption}
                  onRemove={removeOption}
                />
              )}
              {typeCode === "true_false" && (
                <div className="flex flex-wrap gap-3">
                  {(["正确", "错误"] as const).map((t, i) => {
                    const k = i === 0 ? "T" : "F";
                    return (
                      <button
                        key={t}
                        type="button"
                        onClick={() => toggleTf(k)}
                        className={
                          "rounded-xl border border-border bg-background px-4 py-2.5 text-sm transition-colors " +
                          (chosen.has(k) ? "border-primary bg-primary/10 text-primary" : "")
                        }
                      >
                        {k === "T" ? "√" : "×"} {t}（{k === "T" ? "True" : "False"}）
                      </button>
                    );
                  })}
                </div>
              )}
              {(typeCode === "fill_blank" || typeCode === "short_answer") && (
                <div className="rounded-xl border border-dashed border-border bg-muted/40 p-6 text-center text-sm text-muted-foreground">
                  该题型不提供选项编辑器。填空题请在题干中使用 <code className="rounded bg-muted px-1 font-mono">____</code> 占位；简答题直接在「答案」填写参考答案要点。
                </div>
              )}
              <FieldError msg={fieldErrors.options} />
            </div>

            <div className="space-y-1.5">
              <Label>
                答案 <span className="text-destructive">*</span>
              </Label>
              <Textarea value={answerText} onChange={(e) => setAnswerText(e.target.value)} rows={2} placeholder={answerHint(typeCode)} />
              <p className="text-xs text-muted-foreground">{answerHint(typeCode)}</p>
              <FieldError msg={fieldErrors.answer} />
            </div>

            <div className="space-y-1.5">
              <Label className="text-foreground">
                <span className="mr-1 font-bold text-destructive">★</span>解析 analysis_text
                <span className="ml-2 text-xs font-normal text-muted-foreground">必修 · 保存前校验非空 · Markdown 预览</span>
              </Label>
              <Textarea value={analysis} onChange={(e) => setAnalysis(e.target.value)} rows={5} placeholder="编写本题解析（Markdown）…" />
              <div className="rounded-xl border border-border bg-muted/30 p-3">
                <p className="mb-1.5 text-xs font-semibold text-muted-foreground">Markdown 实时预览（与用户端 QuizPanel 一致）</p>
                <div className="text-sm">{analysis.trim() ? <MarkdownView content={analysis} /> : <p className="text-sm text-muted-foreground">暂无内容</p>}</div>
              </div>
              <FieldError msg={fieldErrors.analysis} />
            </div>

            {fieldErrors.submit && <p className="text-sm text-destructive">{fieldErrors.submit}</p>}
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
            <Button type="button" variant="outline" asChild>
              <Link href="/admin/questions">返回列表</Link>
            </Button>
            <span className="flex-1" />
            <Button type="button" variant="outline" disabled={save.isPending} onClick={() => handleSave(true)}>
              保存并继续
            </Button>
            <Button type="button" disabled={save.isPending} onClick={() => handleSave(false)}>
              {save.isPending ? "保存中…" : "保存"}
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="preview">
          <div className="space-y-4 rounded-xl border border-border bg-card p-5">
            <PreviewBlock title="题干 stem">
              {stem.trim() ? <MarkdownView content={stem} /> : <p className="py-2 text-sm text-muted-foreground">暂无内容</p>}
            </PreviewBlock>

            {isChoice && options.filter((o) => (o.text ?? "").trim()).length > 0 && (
              <div className="flex flex-col gap-2">
                {options
                  .filter((o) => (o.text ?? "").trim())
                  .map((o) => (
                    <div
                      key={o.key}
                      className={
                        "flex items-start gap-2 rounded-xl border border-border bg-background p-3 " +
                        (chosen.has(o.key) ? "border-primary bg-primary/10" : "")
                      }
                    >
                      <span className="font-mono text-sm font-bold text-primary">{o.key}</span>
                      <span className="text-sm text-foreground">{o.text}</span>
                    </div>
                  ))}
              </div>
            )}
            {typeCode === "true_false" && (
              <div className="flex flex-col gap-2">
                {(["正确", "错误"] as const).map((t, i) => (
                  <div
                    key={t}
                    className={
                      "flex items-start gap-2 rounded-xl border border-border bg-background p-3 " +
                      (i === 0 && chosen.has("T") ? "border-primary bg-primary/10" : "")
                    }
                  >
                    <span className="font-mono text-sm font-bold text-primary">{i === 0 ? "√" : "×"}</span>
                    <span className="text-sm text-foreground">{t}</span>
                  </div>
                ))}
              </div>
            )}

            <PreviewBlock title="解析 · 作答后折叠展示">
              {analysis.trim() ? <MarkdownView content={analysis} /> : <p className="py-2 text-sm text-muted-foreground">暂无内容</p>}
            </PreviewBlock>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ChoiceList({
  mode,
  options,
  chosen,
  onToggle,
  onPatch,
  onAdd,
  onRemove,
}: {
  mode: "single" | "multi";
  options: OptionRow[];
  chosen: Set<string>;
  onToggle: (key: string) => void;
  onPatch: (key: string, text: string) => void;
  onAdd: () => void;
  onRemove: (key: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-muted/30">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5 text-xs text-muted-foreground">
        <span className="font-semibold text-foreground">
          {mode === "single" ? "单选题选项（RadioGroup · 唯一答案）" : "多选题选项（Checkbox · 可多选）"}
        </span>
        <span>options_json 数组</span>
      </div>
      <div className="flex flex-col gap-2 p-3">
        {options.map((o) => (
          <div key={o.key} className="flex items-start gap-2.5">
            <label className="flex shrink-0 cursor-pointer items-center gap-2 pt-2">
              <input
                type={mode === "single" ? "radio" : "checkbox"}
                name={mode === "single" ? "q-option" : undefined}
                checked={chosen.has(o.key)}
                onChange={() => onToggle(o.key)}
                className="h-4 w-4 accent-primary"
              />
              <span className="font-mono text-xs font-semibold text-muted-foreground">{o.key}</span>
            </label>
            <input
              value={o.text}
              onChange={(e) => onPatch(o.key, e.target.value)}
              placeholder={`选项 ${o.key} 文本…`}
              className="h-9 w-full rounded-lg border border-border bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            <button
              type="button"
              onClick={() => onRemove(o.key)}
              className="h-8 w-8 shrink-0 rounded-lg border border-border text-sm text-destructive hover:bg-destructive/10"
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={onAdd}
        className="m-1.5 rounded-lg border border-dashed border-border px-3 py-1.5 text-xs text-muted-foreground hover:border-primary hover:text-primary"
      >
        + 添加选项
      </button>
    </div>
  );
}

function ObjBadge({ objective, typeName }: { objective: boolean; typeName: string }) {
  return objective ? (
    <Badge className="border-transparent bg-candy-green-soft text-candy-green">客观 · 自动判题（{typeName}）</Badge>
  ) : (
    <Badge className="border-transparent bg-candy-purple/10 text-candy-purple">主观 · 人工批改（{typeName}）</Badge>
  );
}

function PreviewBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-muted/30 p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</p>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null;
  return <p className="text-sm text-destructive">{msg}</p>;
}

function answerHint(typeCode: string): string {
  if (typeCode === "fill_blank") return "填空：填答案文本";
  if (typeCode === "short_answer") return "简答：填参考答案要点";
  return typeCode === "true_false" ? "单选/多选/判断：答案填选项标号（如 对 / 错）" : "单选/多选/判断：答案填选项标号（如 B / AB）";
}

function messageOf(err: unknown): string {
  if (err && typeof err === "object" && "message" in err) return String((err as { message: string }).message);
  return "保存失败，请重试";
}