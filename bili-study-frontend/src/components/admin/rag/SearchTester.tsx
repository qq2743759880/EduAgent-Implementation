/**
 * SearchTester — RAG 高级检索测试面板（task04）
 *  - 输入 query + 可选 preset / top_k / final_max_k，POST /api/admin/rag/search
 *  - 结果区：docs 列表（content/source_file/score）+ degraded_reason 提示
 *  - 写操作（检索）失败抛 → 全局 MutationCache → toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { FileText, Loader2, Search, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { NativeSelect } from "@/components/admin/controls";
import {
  ragAdminSearch,
  type RagPreset,
  type RagSearchResult,
} from "@/lib/api/admin/rag";

export function SearchTester({ presets }: { presets: RagPreset[] }) {
  const [query, setQuery] = useState("");
  const [presetId, setPresetId] = useState("");
  const [topK, setTopK] = useState(20);
  const [finalMaxK, setFinalMaxK] = useState(8);
  const [result, setResult] = useState<RagSearchResult | null>(null);

  const searchMutation = useMutation({
    mutationFn: () =>
      ragAdminSearch({
        query,
        preset_id: presetId === "" ? undefined : Number(presetId),
        top_k: topK,
        final_max_k: finalMaxK,
      }),
    onSuccess: (res) => setResult(res),
    // 失败：全局 MutationCache onError → toast（R-7）
  });

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-0 flex-1">
            <label htmlFor="search-query" className="mb-1 block text-xs text-slate-600">检索问题（跨租户全库）</label>
            <Textarea
              id="search-query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="输入要检索的问题，如：勾股定理的推导过程"
              rows={2}
              data-testid="search-query"
            />
          </div>
          <div className="w-full sm:w-48">
            <label htmlFor="search-preset" className="mb-1 block text-xs text-slate-600">参数预设（可选）</label>
            <NativeSelect id="search-preset" value={presetId} onChange={(e) => setPresetId(e.target.value)} data-testid="search-preset">
              <option value="">不使用预设（手动参数）</option>
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.preset_name}{p.is_default ? "（默认）" : ""}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="w-full sm-24">
            <label htmlFor="search-top-k" className="mb-1 block text-xs text-slate-600">top_k</label>
            <Input
              id="search-top-k"
              type="number"
              min={1}
              max={200}
              value={topK}
              disabled={presetId !== ""}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="h-8"
            />
          </div>
          <div className="w-full sm-24">
            <label htmlFor="search-final-max-k" className="mb-1 block text-xs text-slate-600">final_max_k</label>
            <Input
              id="search-final-max-k"
              type="number"
              min={1}
              max={30}
              value={finalMaxK}
              disabled={presetId !== ""}
              onChange={(e) => setFinalMaxK(Number(e.target.value))}
              className="h-8"
            />
          </div>
          <Button
            disabled={searchMutation.isPending || !query.trim()}
            onClick={() => searchMutation.mutate()}
            data-testid="search-run"
          >
            {searchMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" aria-hidden="true" /> : <Search className="mr-1 h-4 w-4" aria-hidden="true" />}
            检索测试
          </Button>
        </div>
      </div>

      {result && (
        <div className="space-y-3" role="status" aria-live="polite">
          {/* 元信息 */}
          <div className="flex flex-wrap items-center gap-2 text-[13px] text-slate-600">
            <span className="rounded-lg bg-slate-100 px-2.5 py-1">
              召回 <b>{result.retrieved_count}</b> · 最终 <b>{result.final_count}</b>
            </span>
            {result.applied_preset_name && (
              <span className="rounded-lg bg-indigo-50 px-2.5 py-1 text-indigo-700">
                预设：{result.applied_preset_name}
              </span>
            )}
            {result.rewrite_query && (
              <span className="rounded-lg bg-slate-50 px-2.5 py-1">
                rewrite：<span className="font-mono text-slate-600">{result.rewrite_query}</span>
              </span>
            )}
          </div>

          {/* 降级提示 */}
          {result.degraded_reason && (
            <div
              className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-[13px] text-amber-800"
              data-testid="search-degraded"
            >
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>降级提示：{result.degraded_reason}</span>
            </div>
          )}

          {/* docs 列表 */}
          {result.docs.length === 0 ? (
            <div className="rounded-xl border border-dashed p-6 text-center text-sm text-slate-600">
              无检索结果{result.degraded_reason ? "（后端已降级）" : ""}
            </div>
          ) : (
            <div className="space-y-2" data-testid="search-docs">
              {result.docs.map((doc, i) => (
                <div
                  key={`${doc.doc_id}-${i}`}
                  className="rounded-xl border border-slate-200 bg-white p-3"
                  data-testid="search-doc"
                >
                  <div className="flex items-center gap-2 text-[13px]">
                    <FileText className="h-4 w-4 shrink-0 text-indigo-500" aria-hidden="true" />
                    <span className="font-mono text-[12px] text-slate-600">{doc.source_file ?? "未知来源"}</span>
                    <span className="ml-auto shrink-0 rounded-full bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600">
                      {doc.score.toFixed(4)}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-3 whitespace-pre-wrap text-[13px] leading-relaxed text-slate-700">
                    {doc.content}
                  </p>
                  {doc.content_type && (
                    <span className="mt-1 inline-block rounded bg-indigo-50 px-1.5 py-0.5 text-[11px] text-indigo-600">
                      {doc.content_type}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
