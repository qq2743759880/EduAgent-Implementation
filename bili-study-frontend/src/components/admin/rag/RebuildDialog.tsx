/**
 * RebuildDialog — 重建 RAG 索引弹窗（task04）
 *  - 选择重建模式（incremental/full），提交 POST /collections/rebuild
 *  - 成功 → 202 {job_id}，toast + 显示 job_id + 后端 message
 *  - 写操作 useMutation（L3）；失败全局 MutationCache → toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldRow, NativeSelect } from "@/components/admin/controls";
import {
  rebuildRagCollection,
  type RagCollection,
  type RagRebuildResult,
} from "@/lib/api/admin/rag";

export interface RebuildDialogProps {
  collection: RagCollection | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const MODE_OPTIONS = [
  { value: "incremental", label: "增量（只补缺失 chunk，推荐）" },
  { value: "full", label: "全量（清空后重建整库，更慢更干净）" },
] as const;

export function RebuildDialog({ collection, open, onOpenChange }: RebuildDialogProps) {
  return (
    <RebuildDialogBody
      key={open ? `rebuild-${collection?.id ?? "none"}` : "closed"}
      collection={collection}
      open={open}
      onOpenChange={onOpenChange}
    />
  );
}

function RebuildDialogBody({ collection, open, onOpenChange }: RebuildDialogProps) {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"incremental" | "full">("incremental");
  const [result, setResult] = useState<RagRebuildResult | null>(null);

  const rebuildMutation = useMutation({
    mutationFn: () =>
      rebuildRagCollection({
        collection_name: collection?.collection_name ?? "knowledge_chunk_v1",
        partition_name: collection?.partition_name ?? "_default",
        mode,
      }),
    onSuccess: (res) => {
      setResult(res);
      toast.success(`重建任务已接受 · job_id=${res.job_id}`);
      queryClient.invalidateQueries({ queryKey: ["admin", "rag"] });
    },
    // 失败：全局 MutationCache onError → toast（R-7）
  });

  if (!collection) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>重建索引 · {collection.partition_name}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg bg-slate-50 px-3 py-2.5 text-[13px] text-slate-600">
            <div><span className="text-slate-600">集合：</span><span className="font-mono">{collection.collection_name}</span></div>
            <div><span className="text-slate-600">分区：</span><span className="font-mono">{collection.partition_name}</span></div>
            <div><span className="text-slate-600">当前行数：</span>{collection.row_count.toLocaleString()} chunks</div>
          </div>

          <FieldRow label="重建模式">
            <NativeSelect
              id="rebuild-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as "incremental" | "full")}
              data-testid="rebuild-mode"
            >
              {MODE_OPTIONS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </NativeSelect>
          </FieldRow>

          {result && (
            <div
              className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-[13px] text-emerald-800"
              data-testid="rebuild-result"
              role="status"
              aria-live="polite"
            >
              <div className="font-medium">
                job_id：<span className="font-mono" data-testid="rebuild-job-id">{result.job_id}</span>
              </div>
              <p className="mt-1 leading-relaxed text-emerald-700">{result.message}</p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            关闭
          </Button>
          <Button
            type="button"
            disabled={rebuildMutation.isPending}
            data-testid="rebuild-submit"
            onClick={() => rebuildMutation.mutate()}
          >
            {rebuildMutation.isPending ? "提交中…" : "确认重建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
