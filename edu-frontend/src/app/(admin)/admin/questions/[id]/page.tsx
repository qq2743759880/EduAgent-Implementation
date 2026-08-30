/** task59 /admin/questions/[id] 管理端题目编辑（契约④：详情 GET /questions/{id}，题型 GET /types，保存 PATCH /questions/{id}）。重写清理 task03/v0.2.0 text-slate-500 灰系与旧 QuestionForm/tag_ids 契约。 */
"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";

import { QuestionDetailEditor } from "@/components/admin/QuestionDetailEditor";
import { ErrorState, LoadingState } from "@/components/admin/controls";
import { getBank, getQuestion, listQuestionTypes } from "@/lib/api/admin/question-bank";

export default function AdminQuestionEditPage({ params }: { params: Promise<{ id: string }> }) {
  const resolved = use(params);
  const questionId = Number(resolved.id);
  const valid = Number.isFinite(questionId) && questionId > 0;

  const typesQ = useQuery({
    queryKey: ["admin", "question-types"] as const,
    queryFn: () => listQuestionTypes(),
    enabled: valid,
    staleTime: 30_000,
  });

  const detailQ = useQuery({
    queryKey: ["admin", "questions", questionId, "detail"] as const,
    queryFn: () => getQuestion(questionId),
    enabled: valid,
    staleTime: 20_000,
  });

  const bankQ = useQuery({
    queryKey: ["admin", "question-banks", detailQ.data?.bank_id] as const,
    queryFn: () => (detailQ.data ? getBank(detailQ.data.bank_id) : Promise.reject(new Error("no detail"))),
    enabled: valid && Boolean(detailQ.data?.bank_id),
    staleTime: 60_000,
    retry: false,
  });

  if (!valid) return <ErrorState message="无效的题目 ID" />;
  if (typesQ.isLoading || detailQ.isLoading) return <LoadingState label="加载题目…" />;
  if (typesQ.isError || !typesQ.data?.length || detailQ.isError || !detailQ.data) {
    return (
      <ErrorState
        message={
          typesQ.isError || !typesQ.data?.length
            ? "题型枚举加载失败"
            : detailQ.error instanceof Error
              ? detailQ.error.message
              : "题目加载失败"
        }
        onRetry={() => {
          typesQ.refetch();
          detailQ.refetch();
        }}
      />
    );
  }

  return <QuestionDetailEditor questionId={questionId} bankName={bankQ.data?.bank_name ?? null} detail={detailQ.data} types={typesQ.data} />;
}