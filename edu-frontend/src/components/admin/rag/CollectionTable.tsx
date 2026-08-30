/**
 * CollectionTable — RAG 知识库集合表格（task04）
 *  - 展示 rag_collection_meta 列表：集合名/分区/行数快照（Milvus）/状态/更新时间
 *  - 每行「重建索引」→ RebuildDialog（POST /collections/rebuild → 202 + job_id）
 *  - 状态徽章：ready=绿 / rebuilding=琥珀（含转圈）/ error=红
 */
"use client";

import { useState } from "react";
import { Database, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RebuildDialog } from "@/components/admin/rag/RebuildDialog";
import {
  ragCollectionStatusLabel,
  type RagCollection,
} from "@/lib/api/admin/rag";
import { cn } from "@/lib/utils";

export function CollectionTable({ collections }: { collections: RagCollection[] }) {
  const [rebuildTarget, setRebuildTarget] = useState<RagCollection | null>(null);

  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[760px] text-sm" data-testid="rag-collection-table">
          <caption className="sr-only">RAG 知识库集合列表（行数快照 / 状态 / 重建操作）</caption>
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/70 text-left text-xs text-slate-500">
              <th scope="col" className="px-3 py-2.5 font-medium">知识库 / 分区</th>
              <th scope="col" className="px-3 py-2.5 font-medium">行数快照</th>
              <th scope="col" className="px-3 py-2.5 font-medium">来源数</th>
              <th scope="col" className="px-3 py-2.5 font-medium">状态</th>
              <th scope="col" className="px-3 py-2.5 font-medium">快照时间</th>
              <th scope="col" className="px-3 py-2.5 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {collections.map((c) => (
              <tr key={c.id} className="hover:bg-slate-50/60" data-testid="rag-collection-row">
                <td className="px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <Database className="h-4 w-4 shrink-0 text-indigo-500" aria-hidden="true" />
                    <div>
                      <div className="font-medium text-slate-800">{c.display_name || c.collection_name}</div>
                      <div className="text-[11px] text-slate-600 font-mono">
                        {c.collection_name} / {c.partition_name}
                        {c.tenant_id ? ` · ${c.tenant_id}` : ""}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2.5">
                  <span className="font-mono text-[13px] font-medium text-slate-700">
                    {c.row_count.toLocaleString()}
                  </span>
                  <span className="ml-1 text-[11px] text-slate-600">chunks</span>
                </td>
                <td className="px-3 py-2.5 text-[13px] text-slate-500">{c.source_count}</td>
                <td className="px-3 py-2.5">
                  <span role="status" aria-live="polite">
                    <StatusBadge status={c.status} />
                  </span>
                  {c.status_message && (
                    <div className="mt-0.5 max-w-[220px] truncate text-[11px] text-slate-600" title={c.status_message}>
                      {c.status_message}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2.5 text-[13px] text-slate-500">
                  {c.last_snapshot_at ? new Date(c.last_snapshot_at).toLocaleString() : "—"}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex items-center justify-end">
                    <Button
                      variant="outline"
                      size="sm"
                      data-testid={`rebuild-${c.id}`}
                      onClick={() => setRebuildTarget(c)}
                    >
                      <RotateCcw className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                      重建索引
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <RebuildDialog
        collection={rebuildTarget}
        open={Boolean(rebuildTarget)}
        onOpenChange={(o) => !o && setRebuildTarget(null)}
      />
    </>
  );
}

export function StatusBadge({ status }: { status: RagCollection["status"] }) {
  const tone = {
    ready: "bg-emerald-100 text-emerald-700",
    rebuilding: "bg-amber-100 text-amber-800",
    error: "bg-rose-100 text-rose-700",
  }[status] ?? "bg-slate-100 text-slate-600";

  return (
    <Badge variant="outline" className={cn("gap-1 border-transparent", tone)} data-testid="collection-status">
      {status === "rebuilding" && (
        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-600 ring-1 ring-amber-800/40" />
      )}
      {ragCollectionStatusLabel(status)}
    </Badge>
  );
}
