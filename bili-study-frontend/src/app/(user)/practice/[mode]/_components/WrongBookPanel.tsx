/**
 * WrongBookPanel — 错题本列表（task49，candy-playful frozen）
 * 数据：listWrongBook(only_not_mastered)（契约⑤ wrong-book，question 表出题源 task13/裙④）。
 * 交互：[开始复习] 或 行内[重做] → 进入 QuizSession 逐题复盘。
 * 分页复用 ui/pagination；无题出 EmptyState；拉取失败出 ErrorState（重试），不伪装成功。
 */
"use client";

import { useMemo, useState } from "react";
import { BookOpenCheck, Loader2, RefreshCw, ScrollText } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { listWrongBook, type QuestionMode } from "@/lib/api/learning";
import { Pagination } from "@/components/ui/pagination";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 10;

const MODE_META: Record<QuestionMode, { label: string; chip: string }> = {
  SINGLE: { label: "单选", chip: "bg-candy-blue/15 text-candy-blue" },
  MULTIPLE: { label: "多选", chip: "bg-candy-purple-soft text-candy-purple" },
  FILL: { label: "填空", chip: "bg-candy-orange-soft text-candy-orange" },
  JUDGE: { label: "判断", chip: "bg-candy-green-soft text-candy-green" },
  DRAG: { label: "拖拽", chip: "bg-candy-purple-soft text-candy-purple" },
  MATCH: { label: "匹配", chip: "bg-candy-blue/15 text-candy-blue" },
};

function ellipse(stem: string, max = 60): string {
  if (!stem) return "";
  return stem.length > max ? `${stem.slice(0, max)}…` : stem;
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

interface WrongBookPanelProps {
  version: number;
  onStart: () => void;
}

export function WrongBookPanel({ version, onStart }: WrongBookPanelProps) {
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["practice_wrong_book", page, version] as const,
    queryFn: () => listWrongBook({ page, page_size: PAGE_SIZE, only_not_mastered: true }),
    staleTime: 30_000,
    retry: false,
  });

  const rows = useMemo(() => q.data?.items ?? [], [q.data]);
  const total = q.data?.total ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-extrabold">
          <ScrollText className="h-4 w-4 text-candy-green" />
          错题本
          <span className="rounded-full border-2 border-foreground bg-candy-green-soft px-2.5 py-0.5 text-3xs font-extrabold text-candy-green">
            共 {total > 0 ? total : "--"} 题未掌握
          </span>
        </div>
        <button
          type="button"
          onClick={onStart}
          disabled={total === 0}
          className="inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-candy-green px-4 py-2 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.18)] transition-transform hover:-translate-y-px active:translate-y-px active:shadow-none disabled:cursor-not-allowed disabled:opacity-50 disabled:active:translate-y-0"
        >
          <BookOpenCheck className="h-4 w-4" aria-hidden="true" />
          开始复习
        </button>
      </div>

      {q.isLoading ? (
        <div className="grid place-items-center rounded-3xl border-[3px] border-foreground bg-white py-16 shadow-[0_5px_0_rgba(31,31,31,0.14)]">
          <Loader2 className="h-6 w-6 animate-spin text-candy-purple" aria-hidden="true" />
          <span className="mt-2 text-3xs font-semibold text-muted-foreground">加载错题本…</span>
        </div>
      ) : q.isError ? (
        <ErrorCard onRetry={() => q.refetch()} />
      ) : rows.length === 0 ? (
        <div className="rounded-3xl border-[3px] border-dashed border-foreground bg-white px-6 py-16 text-center">
          <div className="text-3xl" aria-hidden="true">
            🎉
          </div>
          <div className="mt-2 text-base font-extrabold text-foreground">暂无待复习错题</div>
          <p className="mx-auto mt-1 max-w-sm text-3xs font-medium text-muted-foreground">
            全部掌握！去课程里多刷几题，答错的会自动加入本列表。
          </p>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-3xl border-[3px] border-foreground bg-white shadow-[0_5px_0_rgba(31,31,31,0.14)]">
            <ul className="divide-y divide-foreground/10">
              {rows.map((it) => {
                const meta = MODE_META[it.mode ?? "SINGLE"] ?? MODE_META.SINGLE;
                return (
                  <li
                    key={it.id}
                    className="flex flex-wrap items-center gap-3 px-5 py-3.5 transition-colors hover:bg-candy-bg"
                  >
                    <span
                      className={cn(
                        "inline-flex items-center rounded-full border-2 border-foreground px-2.5 py-0.5 text-3xs font-extrabold",
                        meta.chip,
                      )}
                    >
                      {meta.label}
                    </span>
                    <span className="min-w-0 flex-1 text-sm font-semibold text-foreground">
                      {ellipse(it.stem)}
                    </span>
                    <span className="text-3xs font-bold text-candy-red">
                      {fmtDate(it.last_mistake_at)}
                    </span>
                    <span className="text-3xs font-semibold text-muted-foreground">
                      错 {(it.mistake_count ?? 1)} 次
                    </span>
                    <button
                      type="button"
                      onClick={onStart}
                      className="rounded-lg border-2 border-foreground bg-white px-3 py-1.5 text-3xs font-extrabold shadow-[0_2px_0_rgba(31,31,31,0.15)] transition hover:-translate-y-px active:translate-y-px active:shadow-none"
                    >
                      重做
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="border-t-[3px] border-foreground/10 px-4 py-2.5">
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={total}
                onPageChange={setPage}
                disabled={q.isRefetching}
              />
            </div>
          </div>
          <p className="text-3xs font-medium text-muted-foreground" aria-live="polite">
            逐题作答 → 即时判分 → 展示 explain_content 解析（Markdown 预览，与 task59 管理端一致）。
          </p>
        </>
      )}
    </div>
  );
}

function ErrorCard({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-3xl border-[3px] border-dashed border-candy-red/60 bg-white px-6 py-14 text-center">
      <div className="text-3xl" aria-hidden="true">
        ⚠️
      </div>
      <div className="mt-2 text-base font-extrabold text-foreground">错题本加载失败</div>
      <p className="mx-auto mt-1 max-w-sm text-3xs font-medium text-muted-foreground">
        契约⑤ interactive/quiz 后端未就绪或暂不可用，请稍后重试。
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mx-auto mt-4 inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-candy-purple px-4 py-2 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.18)] active:translate-y-px active:shadow-none"
      >
        <RefreshCw className="h-4 w-4" aria-hidden="true" />
        重试
      </button>
    </div>
  );
}