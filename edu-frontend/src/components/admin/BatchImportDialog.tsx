/**
 * BatchImportDialog — 题目批量导入（task03）
 *  - 粘贴 JSON 数组（list[dict]，对齐后端 /batch-import 契约）
 *  - 结果展示 imported / skipped / failed 计数 + messages（≤20 条）
 *  - 提供样例 JSON 一键填充（方便打靶：含 1 条重复编码 + 1 条非法 schema）
 *  - 写操作 useMutation + 失败全局 toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileUp, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { batchImportQuestions, type QuestionBatchImportResult } from "@/lib/api/admin/questions";
import { FieldRow } from "@/components/admin/controls";
import { cn } from "@/lib/utils";

export interface BatchImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported?: (result: QuestionBatchImportResult) => void;
}

export const BATCH_IMPORT_SAMPLE = `[
  {
    "question_code": "Q-BATCH-001",
    "subject_code": "math",
    "question_type": "single_choice",
    "difficulty_level": "L1",
    "stem_html": "1 + 1 = ?",
    "options_json": [{ "label": "A", "content": "1" }, { "label": "B", "content": "2" }, { "label": "C", "content": "3" }],
    "correct_answer": "B",
    "default_score": 5
  },
  {
    "question_code": "Q-BATCH-002",
    "subject_code": "english",
    "question_type": "fill_blank",
    "difficulty_level": "L2",
    "stem_html": "The capital of France is ____.",
    "correct_answer": "Paris",
    "default_score": 5
  },
  {
    "question_code": "Q-BATCH-002",
    "subject_code": "math",
    "question_type": "true_false",
    "difficulty_level": "L1",
    "stem_html": "重复编码（应被跳过 skipped）",
    "correct_answer": "对",
    "default_score": 5
  },
  {
    "question_code": "Q-BATCH-BAD",
    "subject_code": "english",
    "question_type": "unknown_type",
    "difficulty_level": "L1",
    "stem_html": "非法 schema（应失败 failed）",
    "correct_answer": "X"
  }
]`;

/**
 * D-21：messages 逐条语义色下钻（与计数三色一致）。
 * 对齐后端 batch_import_questions（question_admin/service.py:298-325）消息格式：
 *  - skip 编码重复 → amber（跳过）
 *  - fail: / schema invalid → rose（失败）
 *  - 其余（导入成功不产生 message，兜底中性）
 */
function messageToneCls(m: string): string {
  if (m.includes("skip") || m.includes("编码重复")) return "text-amber-700";
  if (m.includes("fail") || m.includes("schema invalid")) return "text-rose-700";
  return "text-slate-600";
}

export function BatchImportDialog({ open, onOpenChange, onImported }: BatchImportDialogProps) {
  const queryClient = useQueryClient();
  const [raw, setRaw] = useState("");
  const [result, setResult] = useState<QuestionBatchImportResult | null>(null);

  const importMutation = useMutation({
    mutationFn: async () => {
      let items: unknown;
      try {
        items = JSON.parse(raw);
      } catch {
        throw new Error("JSON 解析失败，请检查格式");
      }
      if (!Array.isArray(items)) {
        throw new Error("批量导入 body 必须是 JSON 数组");
      }
      return batchImportQuestions(items as never[]);
    },
    onSuccess: (resp) => {
      setResult(resp);
      toast.success(`导入完成：成功 ${resp.imported} / 跳过 ${resp.skipped} / 失败 ${resp.failed}`);
      queryClient.invalidateQueries({ queryKey: ["admin", "questions"] });
      onImported?.(resp);
    },
    // 失败（含 JSON 解析错误）→ 全局 MutationCache onError toast（R-7）
  });

  function handleOpenChange(next: boolean) {
    if (!next) {
      setRaw("");
      setResult(null);
    }
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileUp className="h-4 w-4 text-indigo-600" /> 批量导入题目
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <FieldRow
            id="batch-import-json"
            label="题目 JSON 数组"
            required
            hint="body 为 list[dict]，字段对齐 QuestionAdminCreate；重复编码 → skipped，schema 非法 → failed"
          >
            <Textarea
              value={raw}
              onChange={(e) => setRaw(e.target.value)}
              placeholder='[{"question_code":"Q-001","subject_code":"math",...}]'
              rows={12}
              className="font-mono text-xs"
            />
          </FieldRow>
          <Button type="button" variant="outline" size="sm" onClick={() => setRaw(BATCH_IMPORT_SAMPLE)}>
            填充样例（含重复 + 非法各 1 条）
          </Button>

          {result && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2">
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <span className="inline-flex items-center gap-1 text-slate-500">
                  共 <b className="text-slate-800">{result.total}</b> 条
                </span>
                <span className="inline-flex items-center gap-1 text-emerald-700">
                  <CheckCircle2 className="h-4 w-4" /> 导入 {result.imported}
                </span>
                <span className="inline-flex items-center gap-1 text-amber-700">
                  <AlertTriangle className="h-4 w-4" /> 跳过 {result.skipped}
                </span>
                <span className="inline-flex items-center gap-1 text-rose-700">
                  <XCircle className="h-4 w-4" /> 失败 {result.failed}
                </span>
              </div>
              {result.messages.length > 0 && (
                <ul className="max-h-40 space-y-1 overflow-y-auto rounded-lg bg-white p-2 text-[12px] font-mono">
                  {result.messages.map((m, i) => (
                    <li key={i} className={cn("truncate", messageToneCls(m))} title={m}>{m}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            关闭
          </Button>
          <Button onClick={() => importMutation.mutate()} disabled={!raw.trim() || importMutation.isPending}>
            {importMutation.isPending ? "导入中…" : "开始导入"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
