/**
 * 管理端 · 题库列表（/admin/questions，task03）
 *  - 题目列表：GET /api/admin/questions（subject/type/difficulty/keyword/tag 过滤 + 分页）
 *  - 新建题目：QuestionForm（dialog）
 *  - 批量导入：BatchImportDialog（body 为 list[dict] → imported/skipped/failed + messages）
 *  - 自动组卷：ComposePaperDialog
 *  - 创建标签：POST /tags（供题目选择 tag_ids）
 *  - 删除题目：DELETE /questions/{id}（软删 yn=0）
 *  - 写操作 useMutation + invalidateQueries（L3）；失败全局 toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileUp, ListChecks, Plus, Search, Tags, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { QuestionForm } from "@/components/admin/QuestionForm";
import { BatchImportDialog } from "@/components/admin/BatchImportDialog";
import { ComposePaperDialog } from "@/components/admin/ComposePaperDialog";
import { ErrorState, EmptyState, LoadingState, NativeSelect, FieldRow } from "@/components/admin/controls";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";
import {
  QUESTION_DIFFICULTY_OPTIONS,
  QUESTION_SUBJECT_OPTIONS,
  QUESTION_TYPE_OPTIONS,
  createQuestionTag,
  deleteQuestion,
  listQuestionTags,
  listQuestions,
  questionDifficultyLabel,
  questionSubjectLabel,
  questionTypeLabel,
} from "@/lib/api/admin/questions";

const PAGE_SIZE = 10;

export default function AdminQuestionsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [subject, setSubject] = useState("");
  const [qtype, setQtype] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [keyword, setKeyword] = useState("");
  const [tagId, setTagId] = useState<string>("");
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [tagDialog, setTagDialog] = useState(false);

  // perf F1：关键词 300ms 防抖后进 queryKey（applied 快照），空串归一 undefined 减少无效 key 变体
  const appliedKeyword = useDebouncedValue(keyword, 300);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["admin", "questions", { subject, qtype, difficulty, keyword: appliedKeyword || undefined, tagId, page }] as const,
    async queryFn() {
      return listQuestions({
        subject_code: subject,
        question_type: qtype,
        difficulty_level: difficulty,
        keyword: appliedKeyword || undefined,
        tag_id: tagId ? Number(tagId) : undefined,
        page,
        page_size: PAGE_SIZE,
      });
    },
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  });

  const tagsQ = useQuery({
    queryKey: ["admin", "questions", "tags"] as const,
    queryFn: () => listQuestionTags(),
    staleTime: 60_000,
  });

  const delMutation = useMutation({
    mutationFn: (id: number) => deleteQuestion(id),
    onSuccess: () => {
      toast.success("题目已删除（软删）");
      queryClient.invalidateQueries({ queryKey: ["admin", "questions"] });
    },
  });

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE));
  const tags = tagsQ.data ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">题库管理</h1>
          <p className="text-sm text-slate-500">
            共 {data?.total ?? "—"} 题 · 5 题型（单选/多选/判断/填空/简答）
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setTagDialog(true)}>
            <Tags className="mr-1.5 h-4 w-4" /> 新建标签
          </Button>
          <Button variant="outline" onClick={() => setImportOpen(true)}>
            <FileUp className="mr-1.5 h-4 w-4" /> 批量导入
          </Button>
          <Button variant="outline" onClick={() => setComposeOpen(true)}>
            <ListChecks className="mr-1.5 h-4 w-4" /> 自动组卷
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1.5 h-4 w-4" /> 新建题目
          </Button>
        </div>
      </div>

      {/* 过滤栏 */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <div className="w-full sm:w-36">
          <label htmlFor="filter-q-subject" className="mb-1 block text-xs text-slate-500">学科</label>
          <NativeSelect id="filter-q-subject" value={subject} onChange={(e) => { setSubject(e.target.value); setPage(1); }}>
            <option value="">全部</option>
            {QUESTION_SUBJECT_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-36">
          <label htmlFor="filter-q-type" className="mb-1 block text-xs text-slate-500">题型</label>
          <NativeSelect id="filter-q-type" value={qtype} onChange={(e) => { setQtype(e.target.value); setPage(1); }}>
            <option value="">全部</option>
            {QUESTION_TYPE_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-32">
          <label htmlFor="filter-q-difficulty" className="mb-1 block text-xs text-slate-500">难度</label>
          <NativeSelect id="filter-q-difficulty" value={difficulty} onChange={(e) => { setDifficulty(e.target.value); setPage(1); }}>
            <option value="">全部</option>
            {QUESTION_DIFFICULTY_OPTIONS.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-40">
          <label htmlFor="filter-q-tag" className="mb-1 block text-xs text-slate-500">标签</label>
          <NativeSelect id="filter-q-tag" value={tagId} onChange={(e) => { setTagId(e.target.value); setPage(1); }}>
            <option value="">全部</option>
            {tags.map((t) => (
              <option key={t.id} value={String(t.id)}>{t.tag_name}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="min-w-0 flex-1">
          <label htmlFor="filter-q-keyword" className="mb-1 block text-xs text-slate-500">关键词</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              id="filter-q-keyword"
              className="pl-8"
              value={keyword}
              placeholder="题干 / 题目编码"
              onChange={(e) => { setKeyword(e.target.value); setPage(1); }}
            />
          </div>
        </div>
        <Button
          variant="outline"
          onClick={() => { setSubject(""); setQtype(""); setDifficulty(""); setKeyword(""); setTagId(""); setPage(1); }}
        >
          重置
        </Button>
      </div>

      {/* 列表三态 */}
      {isLoading && !data ? (
        <LoadingState label="加载题目…" />
      ) : isError ? (
        <ErrorState message={error instanceof Error ? error.message : "题目加载失败"} onRetry={() => refetch()} />
      ) : (data?.items?.length ?? 0) === 0 ? (
        <EmptyState message="暂无题目" hint="可点击「新建题目」或「批量导入」录入题库" />
      ) : (
        <>
          <div className="space-y-2" data-testid="question-list">
            {data!.items.map((q) => (
              <div
                key={q.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 hover:border-indigo-200"
                data-testid="question-row"
              >
                <Link href={`/admin/questions/${q.id}`} className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-medium text-slate-800">{q.stem_preview}</span>
                    <Badge variant="outline">{questionTypeLabel(q.question_type)}</Badge>
                    <Badge variant="secondary">{questionSubjectLabel(q.subject_code)}</Badge>
                    <Badge variant="secondary">{questionDifficultyLabel(q.difficulty_level)}</Badge>
                    <span className="text-xs text-slate-600">{q.default_score} 分</span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                    <code className="font-mono">{q.question_code}</code>
                    {q.tags.map((t) => (
                      <span key={t.id} className="rounded-full bg-indigo-50 px-1.5 py-px text-indigo-600">
                        #{t.tag_name}
                      </span>
                    ))}
                  </div>
                </Link>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`删除题目 ${q.question_code}`}
                    data-testid={`del-${q.id}`}
                    disabled={delMutation.isPending && delMutation.variables === q.id}
                    onClick={() => {
                      // 对抗 #9：删除操作二次确认（软删后不可恢复，防误点）
                      if (window.confirm(`确定删除题目「${q.question_code}」吗？删除后不可恢复。`)) {
                        delMutation.mutate(q.id);
                      }
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-rose-500" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
          {totalPages > 1 && <PaginationBar page={page} total_pages={totalPages} onChange={setPage} />}
        </>
      )}

      {/* 弹窗 */}
      <QuestionForm
        open={createOpen}
        onOpenChange={setCreateOpen}
        defaultSubject={subject || undefined}
        onCreated={(id) => router.push(`/admin/questions/${id}`)}
      />
      <BatchImportDialog open={importOpen} onOpenChange={setImportOpen} />
      <ComposePaperDialog open={composeOpen} onOpenChange={setComposeOpen} defaultSubject={subject || undefined} />
      <CreateTagDialog open={tagDialog} onOpenChange={setTagDialog} />
    </div>
  );
}

/* ---------------- 新建标签 ---------------- */
function CreateTagDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ tag_code: "", tag_name: "", tag_type: "knowledge_point", subject_code: "", description: "" });
  const create = useMutation({
    mutationFn: () =>
      createQuestionTag({
        tag_type: form.tag_type,
        tag_code: form.tag_code.trim(),
        tag_name: form.tag_name.trim(),
        subject_code: form.subject_code || undefined,
        description: form.description || undefined,
      }),
    onSuccess: () => {
      toast.success("标签已创建");
      queryClient.invalidateQueries({ queryKey: ["admin", "questions", "tags"] });
      onOpenChange(false);
      setForm({ tag_code: "", tag_name: "", tag_type: "knowledge_point", subject_code: "", description: "" });
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>新建标签</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="tag-code" label="标签编码" required>
              <Input value={form.tag_code} onChange={(e) => setForm((f) => ({ ...f, tag_code: e.target.value }))} placeholder="如：TAG-KP-01" />
            </FieldRow>
            <FieldRow id="tag-name" label="标签名称" required>
              <Input value={form.tag_name} onChange={(e) => setForm((f) => ({ ...f, tag_name: e.target.value }))} placeholder="如：定语从句" />
            </FieldRow>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="tag-type" label="标签类型">
              <NativeSelect value={form.tag_type} onChange={(e) => setForm((f) => ({ ...f, tag_type: e.target.value }))}>
                <option value="knowledge_point">知识点</option>
                <option value="exam_source">考试来源</option>
                <option value="custom">自定义</option>
              </NativeSelect>
            </FieldRow>
            <FieldRow id="tag-subject" label="学科（可不限）">
              <NativeSelect value={form.subject_code} onChange={(e) => setForm((f) => ({ ...f, subject_code: e.target.value }))}>
                <option value="">不限学科</option>
                {QUESTION_SUBJECT_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </NativeSelect>
            </FieldRow>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button
            onClick={() => form.tag_name.trim() && form.tag_code.trim() && create.mutate()}
            disabled={create.isPending || !form.tag_name.trim() || !form.tag_code.trim()}
          >
            {create.isPending ? "创建中…" : "创建标签"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
