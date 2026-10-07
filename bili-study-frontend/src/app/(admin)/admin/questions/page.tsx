/**
 * 管理端 · 题库（/admin/questions，task58，contract④ 两级管理 + 批量导入）
 *  - 两级：题库 Tab（question_bank 列表 CRUD）→ 题目 Tab（选题库后 /banks/{bank_id}/questions）
 *  - 检索：题库按 bank_name/code；题目按 keyword（stem + analysis_text + question_code 全文检索，替代已废除标签筛选）
 *  - 批量导入：BankImportDialog 四步（上传→预览→进度→结果，失败行定位）
 *  - 删除：题库/题目均 ConfirmDialog 二次确认（软删不可恢复）
 *  - 编辑/解析：跳 task59 详情路由 /admin/questions/{id}（J24）
 *  - contract④ 唯一冲突码 40921（题库）/40922（题目）在表单行内提示
 */
"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  ArrowRightLeft,
  FileUp,
  Library,
  MoreHorizontal,
  PencilLine,
  Plus,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PaginationBar } from "@/components/curriculum/PaginationBar";
import { BankFormDialog } from "@/components/admin/BankFormDialog";
import { BankImportDialog } from "@/components/admin/BankImportDialog";
import { ErrorState, EmptyState, LoadingState, NativeSelect } from "@/components/admin/controls";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";
import {
  deleteBank,
  deleteQuestion,
  listBankQuestions,
  listBanks,
  listQuestionTypes,
  type QuestionBank,
  type QuestionListItem,
} from "@/lib/api/admin/question-bank";

const PAGE_SIZE = 10;

export default function AdminQuestionsPage() {
  const queryClient = useQueryClient();

  /* 两级导航 + 选中题库 */
  const [tab, setTab] = useState<"banks" | "questions">("banks");
  const [selected, setSelected] = useState<QuestionBank | null>(null);

  /* 题库检索/分页 */
  const [bankKeyword, setBankKeyword] = useState("");
  const [bankPage, setBankPage] = useState(1);
  const appliedBankKeyword = useDebouncedValue(bankKeyword, 300);

  /* 题目检索/分页 */
  const [qKeyword, setQKeyword] = useState("");
  const [qType, setQType] = useState("");
  const [qPage, setQPage] = useState(1);
  const appliedQKeyword = useDebouncedValue(qKeyword, 300);

  /* 弹窗状态 */
  const [bankFormOpen, setBankFormOpen] = useState(false);
  const [editingBank, setEditingBank] = useState<QuestionBank | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [deleteBankTarget, setDeleteBankTarget] = useState<QuestionBank | null>(null);
  const [deleteQTarget, setDeleteQTarget] = useState<QuestionListItem | null>(null);

  /* 题库列表 */
  const banksQ = useQuery({
    queryKey: ["admin", "question-banks", { keyword: appliedBankKeyword || undefined, page: bankPage }] as const,
    async queryFn() {
      return listBanks({ keyword: appliedBankKeyword || undefined, page: bankPage, page_size: PAGE_SIZE });
    },
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  });

  /* 题型维表（题目 Tab 过滤） */
  const typesQ = useQuery({
    queryKey: ["admin", "question-types"] as const,
    queryFn: () => listQuestionTypes(),
    staleTime: 60_000,
  });

  /* 选中题库下的题目列表 */
  const questionsQ = useQuery({
    queryKey: ["admin", "bank-questions", selected?.id, { keyword: appliedQKeyword || undefined, qtype: qType || undefined, page: qPage }] as const,
    queryFn: () =>
      listBankQuestions(selected!.id, {
        keyword: appliedQKeyword || undefined,
        question_type_id: qType ? Number(qType) : undefined,
        page: qPage,
        page_size: PAGE_SIZE,
        yn: 1,
      }),
    enabled: Boolean(selected),
    placeholderData: (prev) => prev,
    staleTime: 15_000,
  });

  /* 删除题库（软删 yn=0） */
  const delBank = useMutation({
    mutationFn: (id: number) => deleteBank(id),
    onSuccess: () => {
      toast.success("题库已删除（软删）");
      queryClient.invalidateQueries({ queryKey: ["admin", "question-banks"] });
      setDeleteBankTarget(null);
      if (selected) {
        setSelected(null);
        setTab("banks");
      }
    },
  });
  /* 删除题目（软删 yn=0） */
  const delQuestion = useMutation({
    mutationFn: (id: number) => deleteQuestion(id),
    onSuccess: () => {
      toast.success("题目已删除（软删）");
      queryClient.invalidateQueries({ queryKey: ["admin", "bank-questions"] });
      setDeleteQTarget(null);
    },
  });

  function selectBank(bank: QuestionBank) {
    setSelected(bank);
    setQKeyword("");
    setQType("");
    setQPage(1);
    setTab("questions");
  }

  const bankTotal = Math.max(1, Math.ceil((banksQ.data?.total ?? 0) / PAGE_SIZE));
  const qTotal = Math.max(1, Math.ceil((questionsQ.data?.total ?? 0) / PAGE_SIZE));
  const types = typesQ.data ?? [];

  return (
    <div className="space-y-5">
      {/* 头部 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-foreground">题库管理</h1>
          <p className="text-sm text-muted-foreground">
            两级管理：题库 → 题目；编辑/解析在题目详情（task59）完成
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={!selected}
            onClick={() => setImportOpen(true)}
            title={selected ? undefined : "请先在题库 Tab 选择一个题库"}
          >
            <FileUp className="mr-1.5 h-4 w-4" /> 批量导入
          </Button>
          <Button
            onClick={() => {
              setEditingBank(null);
              setBankFormOpen(true);
            }}
          >
            <Plus className="mr-1.5 h-4 w-4" /> 新建题库
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v === "questions" ? "questions" : "banks")}>
        <TabsList variant="line" className="gap-1">
          <TabsTrigger value="banks" className="gap-2">
            <Library className="h-4 w-4" /> 题库
            <Badge variant="secondary" className="h-5 px-1.5 py-0 text-4xs">{banksQ.data?.total ?? "—"}</Badge>
          </TabsTrigger>
          <TabsTrigger value="questions" className="gap-2">
            <Sparkles className="h-4 w-4" /> 题目
            <Badge variant="secondary" className="h-5 px-1.5 py-0 text-4xs">{selected ? (questionsQ.data?.total ?? "—") : 0}</Badge>
          </TabsTrigger>
        </TabsList>

        {/* ============ Tab 1：题库 ============ */}
        <TabsContent value="banks" className="space-y-4">
          {/* 检索 */}
          <div className="flex flex-wrap items-end gap-2 rounded-xl border border-border bg-background p-3">
            <div className="min-w-0 flex-1">
              <label htmlFor="filter-bank-keyword" className="mb-1 block text-xs text-muted-foreground">题库检索</label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="filter-bank-keyword"
                  className="pl-8"
                  value={bankKeyword}
                  placeholder="题库名称 / 编码"
                  onChange={(e) => { setBankKeyword(e.target.value); setBankPage(1); }}
                />
              </div>
            </div>
            <Button
              variant="outline"
              onClick={() => { setBankKeyword(""); setBankPage(1); }}
              disabled={!bankKeyword}
            >
              重置
            </Button>
          </div>

          {/* 列表三态 */}
          {banksQ.isLoading && !banksQ.data ? (
            <LoadingState label="加载题库…" />
          ) : banksQ.isError ? (
            <ErrorState message={banksQ.error instanceof Error ? banksQ.error.message : "题库加载失败"} onRetry={() => banksQ.refetch()} />
          ) : (banksQ.data?.items?.length ?? 0) === 0 ? (
            <EmptyState message="暂无题库" hint="可点击「新建题库」建立第一个题库，或用批量导入灌题" />
          ) : (
            <>
              <div className="space-y-2" data-testid="bank-list">
                {banksQ.data!.items.map((b) => (
                  <div
                    key={b.id}
                    data-testid="bank-row"
                    data-selected={selected?.id === b.id || undefined}
                    className={[
                      "group flex items-center justify-between gap-3 rounded-xl border bg-background px-4 py-3 transition-colors",
                      selected?.id === b.id ? "border-primary-border bg-primary-soft" : "border-border hover:border-primary-border",
                    ].join(" ")}
                  >
                    <button
                      type="button"
                      onClick={() => selectBank(b)}
                      className="min-w-0 flex-1 text-left"
                      data-testid={`select-bank-${b.id}`}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-medium text-foreground">{b.bank_name}</span>
                        <Badge variant="outline">{b.bank_code}</Badge>
                        {b.category_name ? <Badge variant="secondary">{b.category_name}</Badge> : null}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span>共 <b className="text-foreground">{b.question_count ?? 0}</b> 题</span>
                        <span className="inline-flex items-center gap-0.5">
                          <ArrowRightLeft className="h-3 w-3" /> 点击查看题目
                        </span>
                      </div>
                    </button>

                    <div className="flex shrink-0 items-center gap-1" data-testid={`bank-actions-${b.id}`}>
                      <Button variant="outline" size="sm" onClick={() => selectBank(b)}>
                        查看题目
                      </Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={<Button variant="ghost" size="icon" className="data-[active]:bg-muted" aria-label={`题库 ${b.bank_name} 更多操作`} />}
                        >
                          <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuItem onClick={() => { setEditingBank(b); setBankFormOpen(true); }}>
                            <PencilLine className="mr-2 h-4 w-4" /> 编辑题库
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            destructive
                            onClick={() => setDeleteBankTarget(b)}
                          >
                            <Trash2 className="mr-2 h-4 w-4" /> 删除题库
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                ))}
              </div>
              {bankTotal > 1 && <PaginationBar page={bankPage} total_pages={bankTotal} onChange={setBankPage} />}
            </>
          )}
        </TabsContent>

        {/* ============ Tab 2：题目 ============ */}
        <TabsContent value="questions" className="space-y-4">
          {!selected ? (
            <EmptyState
              message="尚未选择题库"
              hint="请先在「题库」Tab 选择一个题库，查看其下属题目"
            />
          ) : (
            <>
              {/* 当前题库头 + 检索 */}
              <div className="flex flex-col gap-3 rounded-xl border border-primary-border bg-primary-soft p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm">
                    <span className="font-medium text-foreground">{selected.bank_name}</span>
                    <span className="ml-2 text-muted-foreground">bank_id = {selected.id}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={() => setTab("banks")}>
                      切换题库
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                      <FileUp className="mr-1 h-3.5 w-3.5" /> 批量导入
                    </Button>
                  </div>
                </div>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="w-full sm:w-32">
                    <label htmlFor="filter-q-type" className="mb-1 block text-xs text-muted-foreground">题型</label>
                    <NativeSelect id="filter-q-type" value={qType} onChange={(e) => { setQType(e.target.value); setQPage(1); }}>
                      <option value="">全部题型</option>
                      {types.map((t) => (
                        <option key={t.id} value={String(t.id)}>{t.type_name}</option>
                      ))}
                    </NativeSelect>
                  </div>
                  <div className="min-w-0 flex-1">
                    <label htmlFor="filter-q-keyword" className="mb-1 block text-xs text-muted-foreground">全文检索</label>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        id="filter-q-keyword"
                        className="pl-8"
                        value={qKeyword}
                        placeholder="题干 / 解析 / 题目编码（LIKE 全文检索）"
                        onChange={(e) => { setQKeyword(e.target.value); setQPage(1); }}
                      />
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => { setQKeyword(""); setQType(""); setQPage(1); }}
                    disabled={!qKeyword && !qType}
                  >
                    重置
                  </Button>
                </div>
              </div>

              {/* 题目列表三态 */}
              {questionsQ.isLoading && !questionsQ.data ? (
                <LoadingState label="加载题目…" />
              ) : questionsQ.isError ? (
                <ErrorState message={questionsQ.error instanceof Error ? questionsQ.error.message : "题目加载失败"} onRetry={() => questionsQ.refetch()} />
              ) : (questionsQ.data?.items?.length ?? 0) === 0 ? (
                <EmptyState message="该题库暂无题目" hint="可通过「批量导入」一键灌入题单" />
              ) : (
                <>
                  <div className="space-y-2" data-testid="question-list">
                    {questionsQ.data!.items.map((q) => (
                      <div
                        key={q.id}
                        data-testid="question-row"
                        className="flex items-center justify-between gap-3 rounded-xl border border-border bg-background px-4 py-3 hover:border-primary-border"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="truncate text-sm font-medium text-foreground">{q.stem}</span>
                            <Badge variant="outline">{q.question_type_name ?? "—"}</Badge>
                            <Badge variant="secondary">{q.objective_flag ? "客观题" : "主观题"}</Badge>
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <code className="font-mono">{q.question_code}</code>
                            <span>题号 #{q.id}</span>
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          <Button variant="ghost" size="sm" asChild>
                            <Link href={`/admin/questions/${q.id}`} data-testid={`edit-${q.id}`}>
                              <PencilLine className="mr-1 h-3.5 w-3.5" /> 编辑/解析
                            </Link>
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label={`删除题目 ${q.question_code}`}
                            data-testid={`del-${q.id}`}
                            disabled={delQuestion.isPending && delQuestion.variables === q.id}
                            onClick={() => setDeleteQTarget(q)}
                          >
                            <Trash2 className="h-3.5 w-3.5 text-destructive-foreground" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                  {qTotal > 1 && <PaginationBar page={qPage} total_pages={qTotal} onChange={setQPage} />}
                </>
              )}
            </>
          )}
        </TabsContent>
      </Tabs>

      {/* 弹窗：remount-key 保证每次打开/切换编辑对象都重新初始化表单（对齐 SeriesForm 技法） */}
      <BankFormDialog
        key={bankFormOpen ? `bank-form-${editingBank?.id ?? "new"}` : "bank-form-closed"}
        open={bankFormOpen}
        onOpenChange={setBankFormOpen}
        bank={editingBank}
        onSaved={() => {
          setBankFormOpen(false);
          setEditingBank(null);
        }}
      />

      {selected && (
        <BankImportDialog
          open={importOpen}
          onOpenChange={setImportOpen}
          bankId={selected.id}
          bankName={selected.bank_name}
        />
      )}

      {/* 删除题库确认（题量警示） */}
      <ConfirmDialog
        open={Boolean(deleteBankTarget)}
        onOpenChange={(o) => !o && setDeleteBankTarget(null)}
        title="删除题库？"
        description={
          deleteBankTarget
            ? `确定删除「${deleteBankTarget.bank_name}」吗？该题库下共有 ${deleteBankTarget.question_count ?? 0} 题，删除后不可恢复。`
            : "确定删除该题库吗？删除后不可恢复。"
        }
        confirmText={delBank.isPending ? "删除中…" : "确认删除"}
        loading={delBank.isPending}
        onConfirm={() => deleteBankTarget && delBank.mutate(deleteBankTarget.id)}
      />

      {/* 删除题目确认 */}
      <ConfirmDialog
        open={Boolean(deleteQTarget)}
        onOpenChange={(o) => !o && setDeleteQTarget(null)}
        title="删除题目？"
        description={deleteQTarget ? `确定删除题目「${deleteQTarget.question_code}」吗？删除后不可恢复。` : "确定删除该题目吗？删除后不可恢复。"}
        confirmText={delQuestion.isPending ? "删除中…" : "确认删除"}
        loading={delQuestion.isPending}
        onConfirm={() => deleteQTarget && delQuestion.mutate(deleteQTarget.id)}
      />
    </div>
  );
}