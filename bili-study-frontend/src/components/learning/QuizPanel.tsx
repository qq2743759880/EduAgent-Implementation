/**
 * QuizPanel — P5 互动习题题面板
 * 支持：
 *   - SINGLE 单选 / MULTIPLE 多选 / JUDGE 对错 / FILL 填空
 *   - DRAG / MATCH 两种后端高端形态：前端只显示正确答案提示 + "在 AI 练习中心打开" CTA
 *   - 提交时计算 time_spent_seconds（从加载题目开始计时）；提交后展示 correct/incorrect + explain_content + mastery_changed
 */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  HelpCircle,
  Loader2,
  RotateCcw,
  Sparkles,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
  getNextQuestion,
  submitAnswer,
  type NextQuestionParams,
  type QuestionMode,
  type QuestionOut,
  type SubmitAnswerOut,
} from "@/lib/api/learning";
import { cn } from "@/lib/utils";

export type AnswerShape =
  | { type: "SINGLE"; value: string }
  | { type: "MULTIPLE"; values: Set<string> }
  | { type: "JUDGE"; value: "T" | "F" }
  | { type: "FILL"; values: string[] }
  | { type: "UNSUPPORTED" };

export interface QuizPanelProps extends NextQuestionParams {
  /** true 时会优先把 session_id 范围内的题塞进 P5 的 quiz/next */
  prefer_from_session?: boolean;
  /** 提交成功后、刷新下一题前触发（可用于更新「做题数」等状态） */
  onAfterSubmit?: (payload: {
    question: QuestionOut;
    correct: boolean;
    result: SubmitAnswerOut;
  }) => void;
}

export function QuizPanel(props: QuizPanelProps) {
  const params: NextQuestionParams = {
    subject_code: props.subject_code,
    series_id: props.series_id,
    session_id: props.session_id,
    mode: props.mode,
    difficulty: props.difficulty,
    from_wrong_book: props.from_wrong_book,
    prefer_wrong_book_ratio: props.prefer_wrong_book_ratio ?? props.from_wrong_book ? 1 : 0.35,
    only_not_mastered: props.only_not_mastered,
  };

  const q = useQuery({
    queryKey: ["quiz_next", params] as const,
    async queryFn(): Promise<QuestionOut | null> {
      const res = await getNextQuestion(params);
      loadedAtRef.current = Date.now();
      return res;
    },
    staleTime: 0,
  });

  const submit = useMutation({
    async mutationFn(input: { question: QuestionOut; answer: unknown; seconds: number }) {
      return submitAnswer({
        question_id: input.question.question_id,
        subject_code: input.question.subject_code ?? params.subject_code,
        answer: input.answer,
        time_spent_seconds: input.seconds,
        session_id: params.session_id,
      });
    },
  });

  const loadedAtRef = useRef<number>(0);
  const question = q.data ?? null;
  const initialAnswer = useInitialAnswer(question);
  const [answer, setAnswer] = useState<AnswerShape>(initialAnswer);
  const [userAnalysis, setUserAnalysis] = useState<string>("");
  const [usedHint, setUsedHint] = useState(false);
  const [submitted, setSubmitted] = useState<SubmitAnswerOut | null>(null);
  // 当前题目已用时（秒）——state 驱动，避免渲染期调 Date.now()/读 ref（React Compiler 规则）
  const [elapsedSec, setElapsedSec] = useState<number>(1);

  // 切换题目时重置作答状态（用纯函数计算初始答案，避免在 effect 里调 Hook —— P3-A lint 修复）
  // 依赖 question?.question_id 而非 question 对象：question 每次渲染可能是新引用（Query 缓存），
  // 加整个对象会导致每次渲染重置作答，破坏用户输入。
  useEffect(() => {
    setAnswer(buildInitialAnswer(question));
    setUserAnalysis("");
    setUsedHint(false);
    setSubmitted(null);
    loadedAtRef.current = Date.now();
    setElapsedSec(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question?.question_id]);

  // 每秒刷新已用时
  useEffect(() => {
    const id = window.setInterval(() => {
      setElapsedSec(Math.max(1, Math.floor((Date.now() - loadedAtRef.current) / 1000)));
    }, 1000);
    return () => window.clearInterval(id);
  }, [question?.question_id]);

  const handleNext = useCallback(() => {
    void q.refetch();
  }, [q]);

  const handleSubmit = useCallback(async () => {
    if (!question) return;
    const payload = normalizeAnswerForSubmit(answer);
    if (!payload.ready) {
      toast.warning("请先作答再提交");
      return;
    }
    const seconds = Math.max(1, Math.floor((Date.now() - loadedAtRef.current) / 1000));
    try {
      const res = await submit.mutateAsync({
        question,
        answer: payload.answer,
        seconds,
      });
      setSubmitted(res);
      props.onAfterSubmit?.({
        question,
        correct: !!res.is_correct,
        result: res,
      });
    } catch (e) {
      toast.error("提交失败，请重试", {
        description: e instanceof Error ? e.message : undefined,
      });
    }
  }, [question, answer, submit, props]);

  const modeLabel = modeLabelOf(question?.mode);
  const diffLabel = difficultyBadge(question?.difficulty);

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center gap-2">
        {q.isLoading && !question ? (
          <Badge variant="secondary" className="gap-1 text-xs">
            <Loader2 className="h-3 w-3 animate-spin" /> 出题中…
          </Badge>
        ) : null}
        {q.isError ? (
          <Badge variant="destructive" className="text-xs text-destructive-foreground">出题接口异常（稍后重试）</Badge>
        ) : null}
        {question?.is_from_wrong_book ? (
          <Badge className="bg-destructive/10 text-destructive-foreground hover:bg-destructive/10 text-xs">
            来源：错题本
          </Badge>
        ) : null}
        {question?.mode ? (
          <Badge variant="secondary" className="text-xs">{modeLabel}</Badge>
        ) : null}
        {diffLabel ? (
          <Badge variant="outline" className="text-xs">
            难度：{diffLabel}
          </Badge>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setUsedHint(true)}
            disabled={usedHint}
          >
            <Sparkles className="mr-1 h-3.5 w-3.5" />
            {usedHint ? "已使用提示" : "给我一点提示"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => handleNext()}
            disabled={q.isFetching}
          >
            <RotateCcw className="mr-1 h-3.5 w-3.5" />
            换一题
          </Button>
        </div>
      </header>

      {q.isLoading && !question ? <Skeleton /> : null}
      {!question && !q.isLoading ? <EmptyState onRetry={handleNext} /> : null}

      {question && isUnsupportedMode(question.mode) ? (
        <UnsupportedPanel question={question} />
      ) : null}

      {question && !isUnsupportedMode(question.mode) ? (
        <Card>
          <CardContent className="space-y-5 p-5">
            <StemBlock
              stem={question.stem}
              hint={usedHint ? `建议先回忆「${modeLabelOf(question.mode)}」作答步骤，再提交。` : null}
            />

            <AnswerBlock
              question={question}
              answer={answer}
              submitted={submitted}
              onChange={setAnswer}
              disabled={!!submitted || q.isFetching || submit.isPending}
            />

            {!submitted && (
              <div className="space-y-3">
                <div>
                  <Label className="text-xs text-muted-foreground">自己的思路（可选）</Label>
                  <Textarea
                    className="mt-1.5 text-sm"
                    rows={3}
                    placeholder="写下你的思路，做错时可以和 AI 解析做对比…"
                    value={userAnalysis}
                    onChange={(e) => setUserAnalysis(e.target.value)}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <div className="text-xs text-muted-foreground">
                    当前用时 {elapsedSec} 秒
                  </div>
                  <Button
                    onClick={handleSubmit}
                    disabled={submit.isPending}
                  >
                    {submit.isPending ? (
                      <>
                        <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                        提交中…
                      </>
                    ) : (
                      <>
                        提交答案
                        <ArrowRight className="ml-1.5 h-4 w-4" />
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {submitted && <SubmitResultBlock result={submitted} onNext={handleNext} analysis={userAnalysis} />}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

/* ---------- 子组件 ---------- */

function StemBlock({ stem, hint }: { stem: string; hint: string | null }) {
  return (
    <div className="space-y-3">
      {/* sizeExceptions 例外③/④：15px → text-base（题目正文，非 arbitrary） */}
      <div className="text-base leading-7 whitespace-pre-wrap">{stem}</div>
      {hint && (
        <div className="rounded-xl border border-warning/40 bg-warning/10 p-3 text-sm text-warning-foreground">
          <Sparkles className="mr-1.5 inline h-4 w-4 align-text-bottom" />
          {hint}
        </div>
      )}
    </div>
  );
}

function AnswerBlock({
  question,
  answer,
  submitted,
  onChange,
  disabled,
}: {
  question: QuestionOut;
  answer: AnswerShape;
  submitted: SubmitAnswerOut | null;
  onChange: (n: AnswerShape) => void;
  disabled?: boolean;
}) {
  switch (question.mode) {
    case "SINGLE": {
      const value = answer.type === "SINGLE" ? answer.value : "";
      const correct = submitted ? normalizeScalar(submitted.correct_answer) : undefined;
      return (
        <RadioGroup
          disabled={disabled}
          value={value}
          onValueChange={(v) => onChange({ type: "SINGLE", value: String(v) })}
          className="space-y-2"
        >
          {(question.options ?? []).map((o, i) => {
            const isRight = submitted && correct != null && o.key === correct;
            const isPick = submitted && value === o.key;
            return (
              <label
                key={o.key ?? `opt-${i}`}
                className={cn(
                  "flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-all",
                  disabled && "cursor-default opacity-90",
                  isPick && !submitted && "border-primary bg-primary/5",
                  isPick && submitted && (submitted.is_correct ? "border-success/40 bg-success/10" : "border-destructive/30 bg-destructive/10"),
                  isRight && !isPick && submitted && "border-success/30 bg-success/5",
                )}
              >
                <RadioGroupItem value={o.key} id={`q-single-${o.key}`} className="mt-0.5" />
                <div className="flex-1">
                  <div className="text-sm">
                    <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-muted text-xs font-semibold text-secondary-foreground">
                      {o.key.toUpperCase()}
                    </span>
                    {o.text}
                  </div>
                </div>
              </label>
            );
          })}
        </RadioGroup>
      );
    }
    case "MULTIPLE": {
      const values = answer.type === "MULTIPLE" ? answer.values : new Set<string>();
      const correctArr = normalizeArr(submitted?.correct_answer);
      const toggle = (k: string) => {
        const ns = new Set(values);
        if (ns.has(k)) ns.delete(k);
        else ns.add(k);
        onChange({ type: "MULTIPLE", values: ns });
      };
      return (
        <div className="space-y-2">
          {(question.options ?? []).map((o, i) => {
            const checked = values.has(o.key);
            const isRight = submitted && correctArr.includes(o.key);
            return (
              <div
                key={o.key ?? `mopt-${i}`}
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-3 transition-all",
                  checked && !submitted && "border-primary bg-primary/5",
                  submitted && checked && (
                    correctArr.includes(o.key)
                      ? "border-success/40 bg-success/10"
                      : "border-destructive/30 bg-destructive/10"
                  ),
                  submitted && !checked && isRight && "border-success/30 bg-success/5",
                )}
              >
                <Checkbox
                  disabled={disabled}
                  checked={checked}
                  onCheckedChange={() => !disabled && toggle(o.key)}
                  className="mt-0.5"
                  id={`q-multi-${o.key}`}
                />
                <Label
                  htmlFor={`q-multi-${o.key}`}
                  className={cn("flex-1 text-sm", disabled && "cursor-default")}
                >
                  <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-muted text-xs font-semibold text-secondary-foreground">
                    {o.key.toUpperCase()}
                  </span>
                  {o.text}
                </Label>
              </div>
            );
          })}
        </div>
      );
    }
    case "JUDGE": {
      const v = answer.type === "JUDGE" ? answer.value : undefined;
      const correctRaw = normalizeScalar(submitted?.correct_answer);
      const correct = correctRaw === "T" || correctRaw === "true" || correctRaw === "1" ? "T" : "F";
      const Pair = [
        { key: "T", label: "正确 ✓" },
        { key: "F", label: "错误 ✗" },
      ] as const;
      return (
        <RadioGroup
          disabled={disabled}
          value={v ?? ""}
          onValueChange={(val) => onChange({ type: "JUDGE", value: String(val) as "T" | "F" })}
          className="grid grid-cols-2 gap-3"
        >
          {Pair.map((p) => {
            const selected = v === p.key;
            const right = submitted && correct === p.key;
            return (
              <label
                key={p.key}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-xl border p-4 text-center transition-all",
                  disabled && "cursor-default opacity-90",
                  selected && !submitted && "border-primary bg-primary/5",
                  selected && submitted &&
                    (submitted.is_correct ? "border-success/40 bg-success/10" : "border-destructive/30 bg-destructive/10"),
                  right && !selected && submitted && "border-success/30 bg-success/5",
                )}
              >
                <RadioGroupItem value={p.key} id={`q-judge-${p.key}`} />
                <div className="flex-1 text-sm font-medium">{p.label}</div>
              </label>
            );
          })}
        </RadioGroup>
      );
    }
    case "FILL": {
      const vals = answer.type === "FILL" ? answer.values : [];
      const hints = question.blanks_hint?.length ? question.blanks_hint : undefined;
      const slots =
        hints?.length ??
        (question.stem.match(/_{2,}/g)?.length) ??
        Math.max(1, vals.length, 1);
      const correctArr = normalizeArr(submitted?.correct_answer);
      while (vals.length < slots) vals.push("");
      return (
        <div className="space-y-2.5">
          {Array.from({ length: slots }).map((_, i) => (
            <div key={i} className="space-y-1">
              <Label className="text-xs text-muted-foreground">
                第 {i + 1} 空 {hints?.[i] ? `（提示：${hints[i]}）` : ""}
                {submitted && correctArr[i] != null ? (
                  <span className="ml-2 text-success-foreground">参考答案：{String(correctArr[i])}</span>
                ) : null}
              </Label>
              <Input
                disabled={disabled}
                value={vals[i]}
                placeholder="输入答案…"
                onChange={(e) => {
                  const nv = vals.slice();
                  nv[i] = e.target.value;
                  onChange({ type: "FILL", values: nv });
                }}
              />
            </div>
          ))}
        </div>
      );
    }
    default:
      return null;
  }
}

function SubmitResultBlock({
  result,
  onNext,
  analysis,
}: {
  result: SubmitAnswerOut;
  onNext: () => void;
  analysis?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border p-4",
        result.is_correct ? "border-success/40 bg-success/10" : "border-destructive/30 bg-destructive/10",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {result.is_correct ? (
            <>
              <CheckCircle2 className="h-5 w-5 text-success" />
              <div className="font-semibold text-success-foreground">回答正确 🎉</div>
            </>
          ) : (
            <>
              <XCircle className="h-5 w-5 text-destructive" />
              <div className="font-semibold text-destructive-foreground">回答错误</div>
            </>
          )}
          {typeof result.score === "number" && (
            <Badge variant="secondary" className="text-xs">得分 {result.score}</Badge>
          )}
          {typeof result.mastery_changed === "number" && (
            <Badge variant="outline" className="text-xs">
              掌握度 {result.mastery_changed > 0 ? "↑" : ""}
              {result.mastery_changed.toFixed(2)}
            </Badge>
          )}
        </div>
        <Button size="sm" onClick={onNext}>
          下一题
          <ArrowRight className="ml-1.5 h-4 w-4" />
        </Button>
      </div>

      {analysis && (
        <div className="mt-3 rounded-lg bg-muted/60 p-3 text-xs text-secondary-foreground">
          <div className="font-semibold text-secondary-foreground">我的思路：</div>
          <div className="mt-1 whitespace-pre-wrap">{analysis}</div>
        </div>
      )}

      {result.explain_content && (
        <div className="mt-3 rounded-lg bg-muted/60 p-3 text-sm leading-6">
          <div className="mb-1 text-xs font-semibold text-secondary-foreground">AI 解析：</div>
          <div className="whitespace-pre-wrap">{result.explain_content}</div>
        </div>
      )}
    </div>
  );
}

function UnsupportedPanel({ question }: { question: QuestionOut }) {
  return (
    <Card>
      <CardContent className="grid gap-4 p-5 md:grid-cols-[auto_minmax(0,1fr)] md:items-start">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary md:mx-0">
          <HelpCircle className="h-6 w-6" />
        </div>
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-base font-semibold">不支持的题型（{question.mode}）</div>
            <Badge variant="secondary" className="text-xs">DRAG / MATCH → 下一阶段在 Playground 支持</Badge>
            {question.is_from_wrong_book && (
              <Badge className="bg-destructive/10 text-destructive-foreground hover:bg-destructive/10 text-xs">来自错题本</Badge>
            )}
          </div>
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">{question.stem}</p>
          <Separator />
          <p className="text-sm">
            拖拽 / 拖拽匹配类题型将在后续 AI Playground 模块上线。当前可以先在复习中心打开常规习题训练。
          </p>
          <div className="flex flex-wrap gap-2">
            <Button asChild size="sm">
              <Link href="/practice/wrong-book">
                <BookOpen className="mr-1.5 h-4 w-4" /> 复习中心：错题本
              </Link>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-10 text-center">
      <HelpCircle className="mx-auto mb-2 h-8 w-8 text-muted-foreground/70" />
      <div className="text-base font-semibold text-foreground">暂时没有可用的习题</div>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        该学科 / 课程题库可能还没生成，也可能你已经完成了所有未掌握的题目。可以稍后再试。
      </p>
      <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
        <RotateCcw className="mr-1.5 h-4 w-4" />
        再试一次
      </Button>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-3 rounded-xl border border-border p-5">
      <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
      <div className="h-4 w-full animate-pulse rounded bg-muted" />
      <div className="h-4 w-4/5 animate-pulse rounded bg-muted" />
      <div className="mt-4 space-y-2">
        <div className="h-11 w-full animate-pulse rounded-xl border border-border bg-muted" />
        <div className="h-11 w-full animate-pulse rounded-xl border border-border bg-muted" />
        <div className="h-11 w-1/2 animate-pulse rounded-xl border border-border bg-muted" />
      </div>
    </div>
  );
}

/* ---------- helpers ---------- */

function buildInitialAnswer(q: QuestionOut | null): AnswerShape {
  if (!q) return { type: "UNSUPPORTED" };
  switch (q.mode) {
    case "SINGLE":
      return { type: "SINGLE", value: "" };
    case "MULTIPLE":
      return { type: "MULTIPLE", values: new Set() };
    case "JUDGE":
      return { type: "JUDGE", value: "T" };
    case "FILL":
      return { type: "FILL", values: [] };
    default:
      return { type: "UNSUPPORTED" };
  }
}

function useInitialAnswer(q: QuestionOut | null): AnswerShape {
  // 依赖 q?.question_id + mode 而非整个 q（q 引用变化不应重算初始答案）
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo<AnswerShape>(() => buildInitialAnswer(q), [q?.question_id, q?.mode]);
}

function normalizeAnswerForSubmit(answer: AnswerShape):
  | { ready: false }
  | { ready: true; answer: unknown } {
  switch (answer.type) {
    case "SINGLE":
      return answer.value ? { ready: true, answer: answer.value } : { ready: false };
    case "MULTIPLE":
      return answer.values.size > 0
        ? { ready: true, answer: Array.from(answer.values) }
        : { ready: false };
    case "JUDGE":
      return { ready: true, answer: answer.value };
    case "FILL":
      return answer.values.length > 0 && answer.values.some((v) => v.trim())
        ? { ready: true, answer: answer.values.map((v) => v.trim()) }
        : { ready: false };
    default:
      return { ready: false };
  }
}

function modeLabelOf(m?: QuestionMode): string {
  switch (m) {
    case "SINGLE":
      return "单选题";
    case "MULTIPLE":
      return "多选题";
    case "JUDGE":
      return "判断题";
    case "FILL":
      return "填空题";
    case "DRAG":
      return "拖拽题";
    case "MATCH":
      return "匹配题";
    default:
      return "互动题";
  }
}

function difficultyBadge(d?: string | null): string {
  switch (d) {
    case "EASY":
      return "简单";
    case "NORMAL":
      return "中等";
    case "HARD":
      return "困难";
    default:
      return d ? String(d) : "";
  }
}

function isUnsupportedMode(m?: QuestionMode): boolean {
  return m === "DRAG" || m === "MATCH";
}

function normalizeScalar(v: unknown): string | undefined {
  if (v == null) return undefined;
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (Array.isArray(v)) return v[0] != null ? String(v[0]) : undefined;
  if (typeof v === "object") {
    const kv = v as Record<string, unknown>;
    if ("key" in kv) return normalizeScalar(kv.key);
  }
  return undefined;
}
function normalizeArr(v: unknown): string[] {
  if (v == null) return [];
  if (Array.isArray(v)) return v.map((x) => (x == null ? "" : String(x)));
  if (typeof v === "string") {
    try {
      const j = JSON.parse(v);
      if (Array.isArray(j)) return j.map((x) => String(x));
    } catch {
      /* ignore */
    }
    return [v];
  }
  return [String(v)];
}
