/**
 * 管理端 · 题目编辑（/admin/questions/[id]，task03）
 *  - 加载：GET /api/admin/questions/{id}（QuestionBankDetail 全字段）
 *  - 编辑：QuestionForm embedded 模式（PATCH /questions/{id}，options_json/tag_ids 一并提交）
 */
"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { QuestionForm } from "@/components/admin/QuestionForm";
import { ErrorState, LoadingState } from "@/components/admin/controls";
import { getQuestion } from "@/lib/api/admin/questions";

export default function AdminQuestionEditPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const resolved = use(params);
  const questionId = Number(resolved.id);
  const valid = Number.isFinite(questionId) && questionId > 0;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "questions", questionId] as const,
    queryFn: () => getQuestion(questionId),
    enabled: valid,
    staleTime: 60_000,
  });

  if (!valid) return <ErrorState message="无效的题目 ID" />;
  if (isLoading) return <LoadingState label="加载题目…" />;
  if (isError || !data) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : "题目加载失败"}
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Link
        href="/admin/questions"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600"
      >
        <ArrowLeft className="h-4 w-4" /> 返回题库列表
      </Link>

      <QuestionForm
        open
        onOpenChange={() => undefined}
        question={data}
        embedded
      />
    </div>
  );
}
