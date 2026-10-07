/**
 * QuizSession — 复习会话（task49 核心，candy-playful frozen）
 * 流程（对齐 practice.html 复习会话演示 + 契约⑤）：
 *   取题 getNextQuestion → 作答（单选/判断/多选/填空）→ 提交 submitAnswer
 *   → 即时判分横幅（✓/✗）→ correct_answer → explain_content 解析（MarkdownView 渲染，与 task59 管理端一致）
 * 状态机：fetching → answering → result / empty（无题）/ error（拉题失败）。
 * 契约⑤ interactive/quiz 未就绪时：拉题失败出 ErrorState 重试，提交失败在卡内 toast 提示，均不 MOCK。
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Loader2,
  RefreshCw,
  X,
} from "lucide-react";
import {
  getNextQuestion,
  submitAnswer,
  type NextQuestionParams,
  type QuestionMode,
  type QuestionOut,
  type SubmitAnswerOut,
} from "@/lib/api/learning";
import { Textarea } from "@/components/ui/textarea";
import { MarkdownView } from "@/components/community/MarkdownView";
import { cn } from "@/lib/utils";

export type ReviewSession =
  | { source: "wrong-book" }
  | { source: "topic"; qmode: QuestionMode };

interface QuizSessionProps {
  session: ReviewSession;
  onBack: () => void;
}

export function buildParams(session: ReviewSession): NextQuestionParams {
  if (session.source === "wrong-book") {
    return { from_wrong_book: true, prefer_wrong_book_ratio: 1, only_not_mastered: true };
  }
  return { mode: session.qmode, from_wrong_book: false };
}

type Phase = "fetching" | "answering" | "result" | "empty" | "error";

export function QuizSession({ session, onBack }: QuizSessionProps) {
  const [idx, setIdx] = useState(1);
  const [phase, setPhase] = useState<Phase>("fetching");
  const [question, setQuestion] = useState<QuestionOut | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [fillText, setFillText] = useState("");
  const [result, setResult] = useState<SubmitAnswerOut | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [submitMesg, setSubmitMesg] = useState<string | null>(null);
  const submittingRef = useRef(false);
  const mountedRef = useRef(true);

  const loadNext = useCallback(
    async (syncPhase = true) => {
      if (syncPhase) {
        setPhase("fetching");
        setLoadError(false);
      }
      setResult(null);
      setSelected([]);
      setFillText("");
      try {
        const q = await getNextQuestion(buildParams(session));
        if (!mountedRef.current) return;
        if (q == null) {
          setPhase("empty");
          return;
        }
        startedAtRef.current = Date.now();
        setQuestion(q);
        setPhase("answering");
      } catch {
        if (!mountedRef.current) return;
        setPhase("error");
        setLoadError(true);
      }
    },
    [session],
  );

  useEffect(() => {
    mountedRef.current = true;
    // 错峰到微任务：避免 effect 体内同步 setState（React hooks lint）
    const init = async () => {
      await Promise.resolve();
      loadNext(false);
    };
    void init();
    return () => {
      mountedRef.current = false;
    };
  }, [loadNext]);

  const mode = question?.mode ?? "SINGLE";
  /* JUDGE 后端可能不返回 options → 提供「对/错」标准选项（真实判断语义，非假数据） */
  const options =
    mode === "JUDGE" && !(question?.options?.length)
      ? [
          { key: "true", text: "正确" },
          { key: "false", text: "错误" },
        ]
      : (question?.options ?? []);

  /* ----- 作答交互 ----- */
  const toggleSingle = (key: string) => setSelected((prev) => (prev[0] === key ? [] : [key]));
  const toggleMultiple = (key: string) =>
    setSelected((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  const canSubmit =
    mode === "FILL" ? fillText.trim().length > 0 : selected.length > 0;

  /* 作答耗时真实计时：start 已在每次 loadNext 出题成功时写入，这里只读计算 */
  const startedAtRef = useRef<number>(0);
  const submitAnswered = useCallback(() => {
    if (startedAtRef.current <= 0) return 0;
    return Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000));
  }, []);

  const onSubmit = async () => {
    if (!question || !canSubmit || submittingRef.current) return;
    submittingRef.current = true;
    setSubmitMesg(null);
    try {
      const answer =
        mode === "FILL"
          ? fillText
              .split(/\r?\n/)
              .map((s) => s.trim())
              .filter(Boolean)
          : mode === "MULTIPLE"
            ? selected
            : selected[0];
      const out = await submitAnswer({
        question_id: question.question_id,
        answer,
        time_spent_seconds: submitAnswered(),
      });
      if (!mountedRef.current) return;
      setResult(out);
      setPhase("result");
    } catch (e) {
      if (!mountedRef.current) return;
      setSubmitMesg(e instanceof Error ? e.message : "提交失败，请重试");
    } finally {
      submittingRef.current = false;
    }
  };

  const nextQuestion = () => {
    setIdx((i) => i + 1);
    loadNext();
  };

  const title = session.source === "wrong-book" ? "错题复盘" : `专项练习 · ${modeLabel(mode)}`;

  return (
    <div className="mx-auto w-full max-w-4xl">
      {/* 会话顶栏 */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1 rounded-lg border-2 border-foreground bg-white px-3 py-1.5 text-3xs font-extrabold shadow-[0_2px_0_rgba(31,31,31,0.15)] active:translate-y-px active:shadow-none"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" /> 退出复习
        </button>
        <span className="text-sm font-extrabold">
          {title} · 第 {idx} 题
        </span>
        <span className="ml-auto rounded-full border-2 border-foreground bg-candy-yellow px-3 py-0.5 text-3xs font-extrabold">
          {wrapperHint(session)}
        </span>
      </div>

      <div className="overflow-hidden rounded-[1.75rem] border-[3px] border-foreground bg-white shadow-[0_5px_0_rgba(31,31,31,0.14)]">
        {phase === "fetching" ? (
          <div className="grid place-items-center py-24">
            <Loader2 className="h-7 w-7 animate-spin text-candy-purple" aria-hidden="true" />
            <span className="mt-3 text-3xs font-semibold text-muted-foreground">正在出题…</span>
          </div>
        ) : phase === "error" ? (
          <div className="px-6 py-20 text-center">
            <CircleHelp className="mx-auto h-8 w-8 text-candy-red" aria-hidden="true" />
            <div className="mt-2 text-base font-extrabold text-foreground">出题失败</div>
            <p className="mx-auto mt-1 max-w-sm text-3xs font-medium text-muted-foreground">
              {loadError ? "契约⑤ interactive/quiz 后端未就绪或暂不可用，请稍后重试。" : ""}
            </p>
            <div className="mt-4 flex items-center justify-center gap-2">
              <button
                type="button"
                onClick={() => void loadNext()}
                className="inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-candy-purple px-4 py-2 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.18)] active:translate-y-px active:shadow-none"
              >
                <RefreshCw className="h-4 w-4" aria-hidden="true" /> 重试
              </button>
              <button
                type="button"
                onClick={onBack}
                className="inline-flex items-center rounded-xl border-[3px] border-foreground bg-white px-4 py-2 text-sm font-extrabold shadow-[0_4px_0_rgba(31,31,31,0.16)] active:translate-y-px active:shadow-none"
              >
                返回列表
              </button>
            </div>
          </div>
        ) : phase === "empty" ? (
          <div className="px-6 py-20 text-center">
            <div className="text-4xl" aria-hidden="true">
              🌟
            </div>
            <div className="mt-2 text-lg font-extrabold text-foreground">
              {session.source === "wrong-book" ? "错题已全部复盘完成" : "该题型的题目已刷完"}
            </div>
            <p className="mx-auto mt-1 max-w-sm text-3xs font-medium text-muted-foreground">
              本批次没有更多题目，返回列表看看其它复习模式吧。
            </p>
            <button
              type="button"
              onClick={onBack}
              className="mt-5 inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-candy-green px-5 py-2.5 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.18)] active:translate-y-px active:shadow-none"
            >
              完成 · 返回复习中心
            </button>
          </div>
        ) : (
          <div className="p-6 md:p-8">
            {/* 题干 */}
            <div className="mb-3 flex flex-wrap items-center gap-2 text-3xs font-bold text-muted-foreground">
              <span className="rounded-full border-2 border-foreground px-2.5 py-0.5 font-extrabold text-foreground">
                {modeLabel(mode)}
              </span>
              {session.source === "wrong-book" && (
                <span className="rounded-full bg-candy-red px-2.5 py-0.5 font-extrabold text-white">
                  错题
                </span>
              )}
              {question?.difficulty && <span>{difficultyLabel(question.difficulty)}</span>}
            </div>
            <h2 className="mb-5 text-base font-extrabold leading-relaxed md:text-lg">
              {question?.stem}
            </h2>

            {/* 作答区 */}
            {mode === "FILL" ? (
              <Textarea
                value={fillText}
                onChange={(e) => setFillText(e.target.value)}
                placeholder="在此填写答案；多空可换行填写…"
                className="min-h-28 border-2 border-foreground text-sm"
                aria-label="答案填写"
              />
            ) : (
              <div
                className="flex flex-col gap-2.5"
                role={mode === "MULTIPLE" ? "group" : "radiogroup"}
                aria-label={mode === "MULTIPLE" ? "多选，可多选" : "选项，单选"}
              >
                {options.map((opt) => {
                  const checked =
                    mode === "MULTIPLE" ? selected.includes(opt.key) : selected[0] === opt.key;
                  return (
                    <label
                      key={opt.key}
                      className={cn(
                        "flex cursor-pointer items-center gap-3 rounded-2xl border-[3px] border-foreground bg-white px-4 py-3 text-sm font-semibold shadow-[0_3px_0_rgba(31,31,31,0.13)] transition active:translate-y-px active:shadow-none",
                        checked &&
                          (mode === "MULTIPLE"
                            ? "border-candy-purple bg-candy-purple-soft"
                            : "border-candy-blue bg-candy-blue/15"),
                      )}
                    >
                      {mode === "MULTIPLE" ? (
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleMultiple(opt.key)}
                          aria-label={`选项 ${opt.key}`}
                          className="h-4 w-4 accent-candy-purple"
                        />
                      ) : (
                        <input
                          type="radio"
                          name="choice"
                          checked={checked}
                          onChange={() => toggleSingle(opt.key)}
                          className="h-4 w-4 accent-candy-blue"
                          value={opt.key}
                        />
                      )}
                      <span className="font-extrabold text-muted-foreground">{opt.key}</span>
                      <span>{opt.text}</span>
                    </label>
                  );
                })}
              </div>
            )}

            {/* 提交 / 提交失败提示 */}
            {phase === "answering" && (
              <div className="mt-5 flex items-center gap-3">
                <button
                  type="button"
                  onClick={onSubmit}
                  disabled={!canSubmit}
                  className="inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-candy-green px-6 py-2.5 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.18)] transition active:translate-y-px active:shadow-none disabled:cursor-not-allowed disabled:opacity-50 disabled:active:translate-y-0"
                >
                  提交答案
                </button>
                {submitMesg && (
                  <span className="text-3xs font-bold text-candy-red" role="alert">
                    {submitMesg}
                  </span>
                )}
              </div>
            )}

            {/* 判分 */}
            {phase === "result" && result && (
              <div className="mt-5 space-y-4" aria-live="polite">
                <div
                  className={cn(
                    "flex items-center gap-3 rounded-2xl border-[3px] border-foreground px-5 py-4",
                    result.is_correct
                      ? "border-candy-green bg-candy-green-soft"
                      : "border-candy-red bg-candy-red/10",
                  )}
                >
                  <span
                    className={cn(
                      "grid h-10 w-10 shrink-0 place-items-center rounded-full text-xl text-white",
                      result.is_correct ? "bg-candy-green" : "bg-candy-red",
                    )}
                    aria-hidden="true"
                  >
                    {result.is_correct ? "✓" : "✗"}
                  </span>
                  <div>
                    <div
                      className={cn(
                        "text-base font-extrabold",
                        result.is_correct ? "text-candy-green" : "text-candy-red",
                      )}
                    >
                      {result.is_correct
                        ? "回答正确！"
                        : "回答错误，看解析补上这个知识点"}
                      {typeof result.score === "number" && ` · 得分 ${result.score}`}
                    </div>
                    {!result.is_correct && (
                      <div className="mt-0.5 text-3xs font-medium text-muted-foreground">
                        正确答案：{answerToString(result.correct_answer)}
                      </div>
                    )}
                  </div>
                </div>

                {result.explain_content ? (
                  <div className="rounded-2xl border-[3px] border-dashed border-candy-purple p-4">
                    <div className="mb-2 flex items-center gap-2 text-sm font-extrabold text-candy-purple">
                      ✦ 本题解析 · analysis_text
                      <span className="rounded-full bg-candy-purple-soft px-2 py-0.5 text-3xs font-extrabold text-candy-purple">
                        Markdown 预览，与 task59 管理端一致
                      </span>
                    </div>
                    <MarkdownView content={result.explain_content} />
                  </div>
                ) : (
                  <p className="text-3xs font-medium text-muted-foreground">
                    本题暂无解析文本（explain_content 为空）。
                  </p>
                )}

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={nextQuestion}
                    className="inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-candy-blue px-5 py-2.5 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.18)] active:translate-y-px active:shadow-none"
                  >
                    下一题 <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={onBack}
                    className="inline-flex items-center gap-1 rounded-xl border-[3px] border-foreground bg-white px-4 py-2.5 text-sm font-extrabold shadow-[0_4px_0_rgba(31,31,31,0.16)] active:translate-y-px active:shadow-none"
                  >
                    <ChevronLeft className="h-4 w-4" aria-hidden="true" /> 结束本轮
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function wrapperHint(s: ReviewSession): string {
  return s.source === "wrong-book" ? "错题本 · 闭环" : "专项 · 题型过滤";
}

export function modeLabel(m: QuestionMode): string {
  const map: Record<QuestionMode, string> = {
    SINGLE: "单选",
    MULTIPLE: "多选",
    FILL: "填空",
    JUDGE: "判断",
    DRAG: "拖拽",
    MATCH: "匹配",
  };
  return map[m] ?? m;
}

function difficultyLabel(d: string): string {
  const map: Record<string, string> = { EASY: "简单", NORMAL: "中等", HARD: "困难" };
  return map[d] ?? d;
}

export function answerToString(a: unknown): string {
  if (Array.isArray(a)) return a.join("、");
  if (a === true) return "对";
  if (a === false) return "错";
  if (a == null || a === "") return "—";
  return String(a);
}