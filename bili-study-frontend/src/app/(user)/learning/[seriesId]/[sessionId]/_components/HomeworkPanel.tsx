/**
 * HomeworkPanel — 本节作业提交与判分（task48 糖果色）
 *
 * 真实接口（契约⑤，task14 已上线）：
 *   POST /api/progress/homework/submit → session_homework_submission 落库 + session_homework_ratio 回读。
 * 判分结果（GWT③）：后端提交响应含 score_* / analysis_text 时展示；非本契约返回字段则渲染
 * 「判分结果待后端返回」待联调位（绝不伪造判分数据）。作业题目内容随 task21 契约⑪ 落地后接入。
 */
"use client";

import { useState } from "react";
import { BookOpen, Send, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { submitHomework } from "@/lib/api/learning";
import { cn } from "@/lib/utils";

export interface HomeworkJudge {
  score_earned?: number | null;
  score_total?: number | null;
  score_percent?: number | null;
  analysis_text?: string | null;
  passed?: boolean | null;
}

export interface HomeworkPanelProps {
  seriesId: number;
  sessionId: number;
  /** 该课次已存在的判分（task21 落地后由 session 详情 / 提交响应提供；缺省则不渲染固定判分） */
  existingJudge?: HomeworkJudge | null;
}

function JudgeResult({ judge }: { judge: HomeworkJudge }) {
  const pct =
    judge.score_percent ??
    (judge.score_earned != null && judge.score_total
      ? Math.round((judge.score_earned / judge.score_total) * 100)
      : null);
  const passed = judge.passed ?? (pct != null ? pct >= 60 : null);
  return (
    <div
      role="status"
      className="rounded-[1.5rem] border-[3px] border-candy-green bg-candy-green-soft p-4"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-2xl font-extrabold text-success-foreground">
          {pct != null ? `${pct} 分` : "已判分"}
        </span>
        {passed != null && (
          <span
            className={cn(
              "rounded-full px-3 py-1 text-xs font-extrabold",
              passed ? "bg-candy-green text-white" : "bg-candy-red text-white",
            )}
          >
            {passed ? "已通过" : "未通过"}
          </span>
        )}
      </div>
      {judge.analysis_text ? (
        <p className="mt-2 text-sm leading-relaxed text-foreground">
          {judge.analysis_text}
        </p>
      ) : null}
    </div>
  );
}

export function HomeworkPanel({ seriesId, sessionId, existingJudge }: HomeworkPanelProps) {
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const onSubmit = async () => {
    if (!answer.trim()) {
      toast.error("请先填写作业作答内容");
      return;
    }
    setSubmitting(true);
    try {
      const r = await submitHomework({
        series_id: seriesId,
        session_id: sessionId,
        homework_title: null,
        detail_payload: { text: answer.trim() },
      });
      setDone(true);
      toast.success(
        r.saved
          ? "作业已提交，session_homework_submission 已落库"
          : "作业已处理（保存状态待确认）",
      );
    } catch (e) {
      toast.error(`作业提交失败：${e instanceof Error ? e.message : "未知错误"}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-[1.5rem] border-[3px] border-foreground bg-white p-5 shadow-[0_5px_0_rgba(31,31,31,0.14)]">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-candy-purple-soft">
            <BookOpen className="h-5 w-5 text-candy-purple" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <div className="text-sm font-extrabold">本节作业</div>
            <div className="text-3xs text-muted-foreground">
              作答提交后落库判分 · 观看 ≥90% 或交作业即可完成本课
            </div>
          </div>
          <span className="ml-auto rounded-full border-2 border-foreground bg-candy-purple-soft px-3 py-1 text-3xs font-extrabold text-candy-purple">
            {done ? "已提交" : "待提交"}
          </span>
        </div>

        {/* 作业题目内容：task21 契约⑪ 落地后替换为真实题目 */}
        <p className="mb-1 text-sm font-bold text-foreground">作业题目（待契约⑪提供题目库）</p>
        <p className="mb-3 text-sm-table text-muted-foreground">
          请口述 / 输入你对本课「输入设备」辨析的理解，提交后将由后端判分。
        </p>
        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          rows={4}
          aria-label="作业作答内容"
          placeholder="在这里输入你的作答…"
          className="w-full resize-y rounded-xl border-2 border-foreground/20 bg-white p-3 text-sm text-foreground outline-none transition-colors focus:border-candy-purple focus:ring-[3px] focus:ring-candy-purple/30"
        />
        <div className="mt-3 flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-3xs text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5 text-candy-purple" aria-hidden="true" />
            判分由后端完成，前端不伪造结果
          </span>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting || done}
            className="inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-candy-green px-4 py-2 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.25)] transition-transform hover:-translate-y-px active:translate-y-px disabled:opacity-50"
          >
            <Send className="h-4 w-4" aria-hidden="true" />
            {submitting ? "提交中…" : done ? "已提交" : "提交判断"}
          </button>
        </div>
      </div>

      {existingJudge ? (
        <JudgeResult judge={existingJudge} />
      ) : done ? (
        <div
          role="status"
          className="rounded-[1.5rem] border-2 border-dashed border-foreground/20 bg-white p-4 text-sm text-muted-foreground"
        >
          已提交。判分结果将由 session_homework_submission 返回（task21 契约⑪ 落地后此处展示
          score / analysis_text）。
        </div>
      ) : null}
    </div>
  );
}