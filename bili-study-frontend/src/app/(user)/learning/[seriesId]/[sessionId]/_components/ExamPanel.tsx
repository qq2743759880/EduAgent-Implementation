/**
 * ExamPanel — 本节考试提交（task48 糖果色）
 *
 * 真实接口（契约⑤，task14 已上线）：POST /api/progress/exam/submit → session_exam_submission 落库。
 * 考试题目内容随 task21 契约⑪ 落地后接入；当前为提交通道（不伪造题库）。
 * 倒计时：若后端给出 duration_minutes 则客户端计时展示；因子组件无题库故默认折叠为等级展示。
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, RotateCcw, Send, TimerReset } from "lucide-react";
import { toast } from "sonner";
import { submitExam } from "@/lib/api/learning";

export interface ExamPanelProps {
  seriesId: number;
  sessionId: number;
  /** 考试时长（分钟），task21 契约⑪ 落地后由 session 详情提供；缺省则不计时 */
  durationMinutes?: number | null;
  /** 交卷结果回执（可选，落库后由 parent 提升展示） */
  onSubmitted?: (r: { saved: boolean }) => void;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

export function ExamPanel({ seriesId, sessionId, durationMinutes, onSubmitted }: ExamPanelProps) {
  const initialLeftSec =
    typeof durationMinutes === "number" && durationMinutes > 0 ? durationMinutes * 60 : null;
  const [leftSec, setLeftSec] = useState<number | null>(initialLeftSec);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const timerRef = useRef<number | null>(null);

  /* 渲染期同步：durationMinutes 为查询结果可能后置到达，prop 变更时重置倒计时起点 */
  const [prevMinutes, setPrevMinutes] = useState<number | null>(initialLeftSec);
  if (initialLeftSec !== prevMinutes) {
    setPrevMinutes(initialLeftSec);
    setLeftSec(initialLeftSec);
  }

  /* 计时器（仅当存在时长时，effect 内不再同步 setState/引用 leftSec） */
  const hasTimed = initialLeftSec != null && initialLeftSec > 0;
  useEffect(() => {
    if (!hasTimed) return;
    timerRef.current = window.setInterval(() => {
      setLeftSec((s) => {
        if (s == null) return s;
        const next = s - 1;
        if (next <= 0 && timerRef.current != null) clearInterval(timerRef.current);
        return Math.max(0, next);
      });
    }, 1000);
    return () => {
      if (timerRef.current != null) clearInterval(timerRef.current);
    };
  }, [hasTimed]);

  const onRetry = () => {
    setSubmitted(false);
  };

  const onSubmit = async () => {
    setSubmitting(true);
    try {
      const r = await submitExam({
        series_id: seriesId,
        session_id: sessionId,
        exam_title: null,
        detail_payload: {},
      });
      setSubmitted(true);
      onSubmitted?.({ saved: r.saved });
      toast.success(r.saved ? "考试已交卷，session_exam_submission 已落库" : "考试已交卷（状态待确认）");
    } catch (e) {
      toast.error(`交卷失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setSubmitting(false);
    }
  };

  const minutes = leftSec != null ? Math.floor(leftSec / 60) : null;
  const seconds = leftSec != null ? leftSec % 60 : null;

  return (
    <div className="rounded-[1.5rem] border-[3px] border-foreground bg-white p-5 shadow-[0_5px_0_rgba(31,31,31,0.14)]">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-candy-orange-soft">
          <TimerReset className="h-5 w-5 text-candy-orange" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <div className="text-sm font-extrabold">本节考试</div>
          <div className="text-3xs text-muted-foreground">
            {leftSec != null ? "剩余时间计时中，交卷后落库判分" : "交卷通道 · 题目待契约⑪接入"}
          </div>
        </div>
        <span className="ml-auto rounded-full border-2 border-foreground bg-candy-orange-soft px-3 py-1 text-3xs font-extrabold text-candy-orange">
          {submitted ? "已交卷" : "进行中"}
        </span>
      </div>

      {/* 倒计时条（GWT③ 考试计时器） */}
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border-2 border-dashed border-candy-orange/40 bg-candy-orange-soft px-4 py-3">
        <span className="inline-flex items-center gap-2 text-md font-extrabold tabular-nums text-candy-orange">
          <span className="text-xs font-bold text-foreground">剩余时间</span>
          {leftSec != null ? (
            <>
              {pad(minutes ?? 0)}:{pad(seconds ?? 0)}
            </>
          ) : (
            <span className="text-xs font-medium text-muted-foreground">未设时限</span>
          )}
        </span>
      </div>

      {/* 题目占位：task21 契约⑪ 落地后在此渲染真实题目组；当前为交卷通道，绝不伪造题目 */}
      <div
        role="status"
        className="mb-4 rounded-xl border border-dashed border-foreground/20 bg-muted/40 p-5 text-center text-sm text-muted-foreground"
      >
        考试题目待后端 study 域（契约⑪）提供后接入。当前可先完成视频观看与文字作业。
      </div>

      <div className="flex items-center justify-between gap-2">
        {submitted ? (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-white px-4 py-2 text-sm font-extrabold text-foreground shadow-[0_4px_0_rgba(31,31,31,0.16)] transition-transform hover:-translate-y-px active:translate-y-px"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            返回考试
          </button>
        ) : (
          <span className="text-3xs text-muted-foreground">
            完成全部作答后点击交卷，判分结果落库展示
          </span>
        )}
        <button
          type="button"
          onClick={onSubmit}
          disabled={submitting || submitted}
          className="inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-candy-orange px-5 py-2 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.28)] transition-transform hover:-translate-y-px active:translate-y-px disabled:opacity-50"
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Send className="h-4 w-4" aria-hidden="true" />
          )}
          {submitting ? "交卷中…" : submitted ? "已交卷" : "交卷"}
        </button>
      </div>
    </div>
  );
}