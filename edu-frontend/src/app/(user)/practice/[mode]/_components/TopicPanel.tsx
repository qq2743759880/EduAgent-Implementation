/**
 * TopicPanel — 专项练习（task49，candy-playful frozen）
 * 按题型（dim_question_type ⇋ QuestionMode）过滤取题，与错题进度隔离。
 * 点题型卡 → QuizSession 定向刷题；契约⑤ interactive/quiz 未就绪时逐题会走 ErrorState 兜底。
 */
"use client";

import { FileQuestion, ListChecks, PenLine, ToggleRight } from "lucide-react";
import type { QuestionMode } from "@/lib/api/learning";

interface TopicDef {
  qmode: QuestionMode;
  title: string;
  desc: string;
  icon: React.ReactNode;
  accent: "green" | "blue" | "purple" | "orange";
}

const TOPICS: TopicDef[] = [
  {
    qmode: "SINGLE",
    title: "单选题",
    desc: "从给定选项中选出唯一正确答案，覆盖概念/原理判断。",
    icon: <ListChecks className="h-6 w-6" aria-hidden="true" />,
    accent: "blue",
  },
  {
    qmode: "MULTIPLE",
    title: "多选题",
    desc: "选出全部正确项，训练知识点的完整性判断。",
    icon: <FileQuestion className="h-6 w-6" aria-hidden="true" />,
    accent: "purple",
  },
  {
    qmode: "FILL",
    title: "填空题",
    desc: "根据提示补全关键结论、代码或术语。",
    icon: <PenLine className="h-6 w-6" aria-hidden="true" />,
    accent: "orange",
  },
  {
    qmode: "JUDGE",
    title: "判断题",
    desc: "对陈述作真/假判定，检验边界理解。",
    icon: <ToggleRight className="h-6 w-6" aria-hidden="true" />,
    accent: "green",
  },
];

export function TopicPanel({
  onStart,
}: {
  onStart: (qmode: QuestionMode) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="text-sm font-extrabold">
        选择题型
        <span className="ml-2 rounded-full border-2 border-foreground bg-candy-purple-soft px-2.5 py-0.5 text-3xs font-extrabold text-candy-purple">
          按 dim_question_type 过滤
        </span>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {TOPICS.map((t) => (
          <div
            key={t.qmode}
            className="flex flex-col rounded-[1.5rem] border-[3px] border-foreground bg-white p-5 shadow-[0_5px_0_rgba(31,31,31,0.14)] transition-transform hover:-translate-y-1"
          >
            <span
              className={`mb-3 grid h-12 w-12 place-items-center rounded-xl border-2 border-foreground text-white ${
                t.accent === "blue"
                  ? "bg-candy-blue"
                  : t.accent === "purple"
                    ? "bg-candy-purple"
                    : t.accent === "orange"
                      ? "bg-candy-orange"
                      : "bg-candy-green"
              }`}
            >
              {t.icon}
            </span>
            <div className="text-base font-extrabold">{t.title}</div>
            <p className="mt-1 flex-1 text-3xs font-medium leading-relaxed text-muted-foreground">
              {t.desc}
            </p>
            <button
              type="button"
              onClick={() => onStart(t.qmode)}
              className={`mt-4 inline-flex w-full items-center justify-center rounded-xl border-[3px] border-foreground py-2 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.18)] transition-transform hover:-translate-y-px active:translate-y-px active:shadow-none ${
                t.accent === "blue"
                  ? "bg-candy-blue"
                  : t.accent === "purple"
                    ? "bg-candy-purple"
                    : t.accent === "orange"
                      ? "bg-candy-orange"
                      : "bg-candy-green"
              }`}
            >
              去刷题 →
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}