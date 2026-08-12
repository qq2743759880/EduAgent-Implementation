/**
 * WrongBookList — 错题本列表（分页）
 * 每行包含：题干摘要 / 错误次数 / 上次错误 / 掌握状态 / 「再做一次」按钮
 * 「再做一次」按钮：用 `getNextQuestion(from_wrong_book=true, wrong_book_id=id)` 取此题的互动练习视图，
 * 直接弹窗（Dialog）渲染 QuizPanel，答对后可刷新列表。
 */
"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BookMarked,
  CircleHelp,
  Loader2,
  Pencil,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { Progress } from "@/components/ui/progress";
import {
  listWrongBook,
  type WrongBookItem,
  type QuestionMode,
} from "@/lib/api/learning";
import { QuizPanel } from "./QuizPanel";
import { toast } from "sonner";

export interface WrongBookListProps {
  subjectCode?: string;
  defaultPageSize?: number;
  onlyNotMastered?: boolean;
}

export function WrongBookList({
  subjectCode,
  defaultPageSize = 10,
  onlyNotMastered = false,
}: WrongBookListProps) {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(defaultPageSize);
  const [openWbId, setOpenWbId] = useState<number | null>(null);

  const q = useQuery({
    queryKey: ["wrong_book", page, pageSize, subjectCode, onlyNotMastered] as const,
    async queryFn() {
      return listWrongBook({
        subject_code: subjectCode,
        page,
        page_size: pageSize,
        only_not_mastered: onlyNotMastered,
      });
    },
    staleTime: 60_000,
  });

  const qc = useQueryClient();
  const invalidate = useCallback(() => {
    return qc.invalidateQueries({ queryKey: ["wrong_book"] });
  }, [qc]);

  const openingItem = useMemo<WrongBookItem | null>(() => {
    if (openWbId == null) return null;
    return q.data?.items.find((x) => x.id === openWbId) ?? null;
  }, [openWbId, q.data]);

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-lg">
            <XCircle className="h-5 w-5 text-rose-500" />
            错题本
          </CardTitle>
          <CardDescription>
            共 {q.data?.total ?? 0} 条，当前第 {q.data?.page ?? page} /{" "}
            {Math.max(1, Math.ceil((q.data?.total ?? 0) / (q.data?.page_size ?? pageSize)))} 页
            {onlyNotMastered && <> · 仅显示未掌握</>}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => q.refetch()}
            disabled={q.isFetching}
          >
            <RotateCcw className={"mr-1.5 h-4 w-4 " + (q.isFetching ? "animate-spin" : "")} />
            刷新
          </Button>
          <Button asChild size="sm">
            <Link href="/my-courses">
              <BookMarked className="mr-1.5 h-4 w-4" />
              回到我的课程
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {q.isLoading && !q.data ? <SkeletonList /> : null}
        {!q.isLoading && q.isError ? <ErrorState msg={q.error instanceof Error ? q.error.message : "加载错题本失败"} onRetry={() => q.refetch()} /> : null}
        {!q.isLoading && !q.isError && (q.data?.items.length ?? 0) === 0 ? (
          <EmptyState />
        ) : null}

        {q.data?.items.length ? (
          <ul className="divide-y divide-slate-100 rounded-2xl border">
            {q.data.items.map((item, i) => (
              <Row
                key={item.id ?? `wb-${i}`}
                item={item}
                onRetake={() => setOpenWbId(item.id)}
              />
            ))}
          </ul>
        ) : null}

        {q.data && q.data.total > (q.data.page_size ?? pageSize) ? (
          <PaginationBar
            page={q.data.page}
            total_pages={Math.max(1, Math.ceil(q.data.total / (q.data.page_size ?? pageSize)))}
            onChange={setPage}
          />
        ) : null}
      </CardContent>

      {/* 错题重做弹窗：利用 QuizPanel 的 from_wrong_book + wrong_book_id 语义（由 P5 后端做偏好） */}
      <Dialog
        open={openWbId != null}
        onOpenChange={(open) => !open && setOpenWbId(null)}
      >
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Pencil className="h-5 w-5 text-primary" />
              重做错题
              <Badge variant="secondary" className="ml-2 text-xs">
                #{openWbId ?? ""}
              </Badge>
            </DialogTitle>
            <DialogDescription>
              {openingItem
                ? `原题：${truncate(openingItem.stem, 60)}`
                : "正在从 P5 题库中抽取这道错题…"}
            </DialogDescription>
          </DialogHeader>
          {openingItem ? (
            <QuizPanel
              subject_code={subjectCode}
              from_wrong_book
              only_not_mastered={false}
              session_id={openingItem.source_session_id ?? undefined}
              onAfterSubmit={async ({ correct }) => {
                if (correct) toast.success("答对啦：该错题掌握度会被 P5 更新");
                await invalidate();
              }}
            />
          ) : (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在请求 P5 /interactive/quiz/next
            </div>
          )}
          <div className="flex justify-end pt-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setOpenWbId(null)}
            >
              关闭
              <ArrowRight className="ml-1.5 h-4 w-4 -rotate-45" />
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Row({ item, onRetake }: { item: WrongBookItem; onRetake: () => void }) {
  const mastered = !!item.mastered_at;
  const modeLabel = modeTag(item.mode);
  const pct = Math.min(1, (item.mistake_count ?? 0) / 5);
  return (
    <li className="grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="text-xs">
            {modeLabel}
          </Badge>
          <Badge variant="outline" className="text-xs">
            错 {item.mistake_count ?? 1} 次
          </Badge>
          {mastered ? (
            <Badge className="bg-emerald-500 text-white text-xs">已掌握 · {item.mastered_at?.slice(0, 10)}</Badge>
          ) : (
            <Badge className="bg-rose-500 text-white text-xs">未掌握</Badge>
          )}
          {item.last_mistake_at && (
            <Badge variant="outline" className="text-xs">
              上次犯错：{item.last_mistake_at.slice(0, 10)}
            </Badge>
          )}
        </div>
        <div className="text-sm leading-7 whitespace-pre-wrap line-clamp-3">
          {item.stem}
        </div>
        {!mastered && (item.mistake_count ?? 0) >= 2 ? (
          <div className="max-w-sm">
            <div className="mb-1 text-[11px] text-muted-foreground">
              错误频次越高，在复习中心会被越多召回
            </div>
            <Progress value={pct * 100} />
          </div>
        ) : null}
      </div>
      <div className="flex items-center justify-start md:justify-end">
        <Button size="sm" onClick={onRetake} variant="default">
          <Pencil className="mr-1.5 h-4 w-4" />
          再做一次
        </Button>
      </div>
    </li>
  );
}

function SkeletonList() {
  return (
    <ul className="divide-y divide-slate-100 rounded-2xl border">
      {Array.from({ length: 3 }).map((_, i) => (
        <li key={i} className="space-y-2 p-4">
          <div className="h-4 w-1/3 animate-pulse rounded bg-slate-100" />
          <div className="h-4 w-full animate-pulse rounded bg-slate-100" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-slate-100" />
        </li>
      ))}
    </ul>
  );
}

function ErrorState({ msg, onRetry }: { msg: string; onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-rose-200 bg-rose-50/40 p-5">
      <div className="flex items-center gap-2 text-rose-700">
        <XCircle className="h-5 w-5" />
        <span className="font-semibold">加载失败</span>
      </div>
      <p className="mt-1 text-sm text-rose-600">{msg}</p>
      <Button variant="outline" size="sm" className="mt-3 border-rose-300 text-rose-700" onClick={onRetry}>
        <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> 重试
      </Button>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl border border-dashed p-8 text-center">
      <CircleHelp className="mx-auto mb-2 h-7 w-7 text-muted-foreground/60" />
      <div className="text-base font-semibold">错题本是空的 👍</div>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        说明你最近题目正确率都很高！可以去课程播放页找随堂练习继续巩固。
      </p>
      <div className="mt-4 flex items-center justify-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href="/courses">去课程首页</Link>
        </Button>
      </div>
    </div>
  );
}

function modeTag(m?: QuestionMode | null): string {
  switch (m) {
    case "SINGLE":
      return "单选";
    case "MULTIPLE":
      return "多选";
    case "JUDGE":
      return "判断";
    case "FILL":
      return "填空";
    case "DRAG":
      return "拖拽";
    case "MATCH":
      return "匹配";
    default:
      return "互动题";
  }
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n) + "…";
}
