/**
 * 管理端 · RAG 控制台（/admin/rag，task04）
 *  - 集合列表（Milvus 行数快照 + 重建索引 202+job_id）
 *  - 参数预设列表 + 新建（is_default 唯一）
 *  - 审计日志（user_id/role/created_after 过滤 + 分页）
 *  - 高级检索测试面板（query → docs/degraded）
 *  - 全部数据来自真实 API（无 MOCK）；写操作 useMutation（L3），失败全局 toast（R-7）
 */
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { CollectionTable } from "@/components/admin/rag/CollectionTable";
import { PresetForm } from "@/components/admin/rag/PresetForm";
import { AuditLogTable } from "@/components/admin/rag/AuditLogTable";
import { SearchTester } from "@/components/admin/rag/SearchTester";
import { UploadPanel } from "@/components/admin/rag/UploadPanel";
import { EmptyState, ErrorState, LoadingState } from "@/components/admin/controls";
import { listRagCollections, listRagPresets } from "@/lib/api/admin/rag";

export default function AdminRagPage() {
  const [presetOpen, setPresetOpen] = useState(false);

  const collectionsQuery = useQuery({
    queryKey: ["admin", "rag", "collections"] as const,
    queryFn: listRagCollections,
    staleTime: 15_000,
    // task04 #3：仅当存在 rebuilding 状态的集合时轮询（10s），stuck 回置/完成后自动停止；
    // 后端 list_collections 会对超时 stuck 集合自动回置 error，轮询保证状态流转可见。
    // LOW-08 防御：后端不可达时 data 可能非数组（错误壳），用 Array.isArray 守卫避免 .some 崩溃
    refetchInterval: (query) =>
      Array.isArray(query.state.data) && query.state.data.some((c) => c.status === "rebuilding")
        ? 10_000
        : false,
  });

  const presetsQuery = useQuery({
    queryKey: ["admin", "rag", "presets"] as const,
    queryFn: listRagPresets,
    staleTime: 15_000,
  });

  // LOW-08 防御：presetsQuery.data 在请求失败/未完成时可能为 undefined 或非数组（错误壳），
  // 直接 .find 会抛 TypeError 导致整页崩溃（a11y 报告 LOW-08），此处用 Array.isArray 守卫。
  const presetsData = Array.isArray(presetsQuery.data) ? presetsQuery.data : [];
  const defaultPreset = presetsData.find((p) => p.is_default) ?? null;

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">RAG 控制台</h1>
          <p className="text-sm text-slate-500">
            文件上传 / 知识库集合 / 参数预设 / 审计日志 / 高级检索（仅 admin）
          </p>
        </div>
      </div>

      {/* 文件上传 + 导入任务 */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-700">文件上传</h2>
        <UploadPanel />
      </section>

      {/* 集合列表 + 重建 */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">知识库集合（Milvus 行数快照）</h2>
        </div>
        {collectionsQuery.isLoading && !collectionsQuery.data ? (
          <LoadingState label="加载知识库…" />
        ) : collectionsQuery.isError ? (
          <ErrorState
            message={collectionsQuery.error instanceof Error ? collectionsQuery.error.message : "知识库加载失败"}
            onRetry={() => collectionsQuery.refetch()}
          />
        ) : (collectionsQuery.data?.length ?? 0) === 0 ? (
          <EmptyState message="暂无知识库集合" hint="后端 rag_collection_meta 为空（Milvus 未连接时也会降级返回种子集合）" />
        ) : (
          <CollectionTable collections={collectionsQuery.data!} />
        )}
      </section>

      {/* 参数预设 */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">检索参数预设</h2>
          <Button size="sm" onClick={() => setPresetOpen(true)} data-testid="preset-open">
            <Plus className="mr-1 h-3.5 w-3.5" aria-hidden="true" /> 新建预设
          </Button>
        </div>

        {presetsQuery.isLoading && !presetsQuery.data ? (
          <LoadingState label="加载预设…" />
        ) : presetsQuery.isError ? (
          <ErrorState
            message={presetsQuery.error instanceof Error ? presetsQuery.error.message : "预设加载失败"}
            onRetry={() => presetsQuery.refetch()}
          />
        ) : presetsData.length === 0 ? (
          <EmptyState message="暂无参数预设" hint="点击右上角「新建预设」创建" />
        ) : (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="preset-list">
            {presetsData.map((p) => (
              <div
                key={p.id}
                className="rounded-xl border border-slate-200 bg-white p-3"
                data-testid="preset-card"
              >
                <div className="flex items-center gap-2">
                  <SlidersHorizontal className="h-4 w-4 shrink-0 text-indigo-500" aria-hidden="true" />
                  <span className="truncate text-sm font-medium text-slate-800">{p.preset_name}</span>
                  {p.is_default && (
                    <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700" data-testid="preset-default-badge">
                      默认
                    </Badge>
                  )}
                </div>
                <p className="mt-1 line-clamp-2 text-[12px] text-slate-500">
                  {p.description || "无描述"}
                </p>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-slate-500">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5">top_k={p.top_k}</span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5">final={p.final_max_k}</span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5">rrf={p.rrf_k}</span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5">model={p.llm_model_pref}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 高级检索测试 */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-slate-700">高级检索测试</h2>
        <SearchTester presets={presetsData} />
      </section>

      {/* 审计日志 */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">审计日志</h2>
          {defaultPreset && (
            <span className="text-[12px] text-slate-600">当前默认预设：{defaultPreset.preset_name}</span>
          )}
        </div>
        <AuditLogTable />
      </section>

      <PresetForm open={presetOpen} onOpenChange={setPresetOpen} />
    </div>
  );
}
