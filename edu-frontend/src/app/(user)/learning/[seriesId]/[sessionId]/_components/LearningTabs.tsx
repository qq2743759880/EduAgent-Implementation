/**
 * LearningTabs — 「视频 / 作业 / 考试」糖果标签页（task48，对齐 learning.html）
 *
 * 交互层：Base UI Tabs（roving tabindex + 方向键 + 读写 aria-*）。
 * 视觉：角色图标（视频=播放 / 作业=文件 / 考试=警告三角）+ 待办数右上角绿色角标；
 *       选中=橙框橙字（candy-orange）+ 白底，未选中置灰（语义由 aria-selected 承载，不靠颜色）。
 */
"use client";

import { BookOpen, CheckCircle2, FileText, Play, TriangleAlert } from "lucide-react";
import { Tabs as TabsPrimitive } from "@base-ui/react/tabs";
import { cn } from "@/lib/utils";
import { HomeworkPanel, type HomeworkJudge } from "./HomeworkPanel";
import { ExamPanel } from "./ExamPanel";

export interface LearningTabsProps {
  seriesId: number;
  sessionId: number;
  /** 考试时长（分钟） */
  durationMinutes?: number | null;
  /** 本课视频观看比例（0..1），用于判定标签与角标 */
  watchRatio?: number | null;
  homeworkDone?: boolean | null;
  examDone?: boolean | null;
  existingJudge?: HomeworkJudge | null;
}

export function LearningTabs({
  seriesId,
  sessionId,
  durationMinutes,
  watchRatio,
  homeworkDone,
  examDone,
  existingJudge,
}: LearningTabsProps) {
  const videoDone = (watchRatio ?? 0) >= 0.9 || homeworkDone;
  const hwBadge = videoDone || homeworkDone ? undefined : "1";
  const examBadge = videoDone || examDone ? undefined : "1";

  return (
    <TabsPrimitive.Root defaultValue="video" className="w-full">
      <TabsPrimitive.List className="flex w-full gap-2 border-b-[3px] border-foreground/15 bg-transparent">
        <CandyTab value="video" icon={<Play className="h-4 w-4 fill-current" />} label="视频" />
        <CandyTab value="homework" icon={<FileText className="h-4 w-4" />} label="作业" badge={hwBadge} />
        <CandyTab value="exam" icon={<TriangleAlert className="h-4 w-4" />} label="考试" badge={examBadge} />
      </TabsPrimitive.List>

      {/* 视频 → 课程简介 */}
      <TabsPrimitive.Panel value="video" className="pt-4">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-extrabold text-foreground">
          <BookOpen className="h-4 w-4 text-candy-blue" aria-hidden="true" /> 课程简介
        </h3>
        <p className="text-sm-table leading-relaxed text-muted-foreground">
          本节课带你先建立整体认知：部件的命名、连接方式与四步排查法。完成视频后将解锁作业，
          作业通过可进入考试，全部完成即结课（观看 ≥90% 或提交作业即判定完成）。
        </p>
        {videoDone && (
          <p className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-success-foreground">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> 本课已达成完成条件
          </p>
        )}
      </TabsPrimitive.Panel>

      <TabsPrimitive.Panel value="homework" className="pt-4">
        <HomeworkPanel seriesId={seriesId} sessionId={sessionId} existingJudge={existingJudge} />
      </TabsPrimitive.Panel>

      <TabsPrimitive.Panel value="exam" className="pt-4">
        <ExamPanel seriesId={seriesId} sessionId={sessionId} durationMinutes={durationMinutes} />
      </TabsPrimitive.Panel>
    </TabsPrimitive.Root>
  );
}

function CandyTab({
  value,
  icon,
  label,
  badge,
}: {
  value: string;
  icon: React.ReactNode;
  label: string;
  badge?: string;
}) {
  return (
    <TabsPrimitive.Tab
      value={value}
      className={cn(
        "relative inline-flex items-center gap-2 rounded-t-xl border-[3px] border-transparent border-b-0 bg-transparent px-4 py-2.5 text-sm font-bold outline-none",
        "text-muted-foreground data-selected:border-candy-orange data-selected:bg-white data-selected:text-candy-orange",
        "hover:bg-white/60 focus-visible:ring-[3px] focus-visible:ring-candy-blue/50",
      )}
    >
      <span className="data-selected:text-candy-orange [&_svg]:shrink-0">{icon}</span>
      {label}
      {badge ? (
        <span
          className="absolute -right-1.5 -top-1.5 inline-grid min-w-5 place-items-center rounded-full border-2 border-candy-bg bg-candy-green px-1 text-3xs font-extrabold text-white shadow-[0_2px_0_rgba(31,31,31,0.25)]"
          aria-hidden="true"
        >
          {badge}
        </span>
      ) : null}
    </TabsPrimitive.Tab>
  );
}