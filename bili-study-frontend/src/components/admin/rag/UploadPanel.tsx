/**
 * UploadPanel — RAG 文件上传 + 导入任务跟踪（render 批3 · task 管理端 RAG 对齐）
 *
 * 消费契约⑥（task36 冻结，app/knowledge/routers/upload.py）真实端点：
 *  - POST   /api/knowledge/admin/upload  管理端公共库上传（uploadKnowledgeFiles）
 *  - POST   /api/knowledge/upload        学员私有库上传（uploadMyKnowledgeFiles）
 *  - GET    /api/knowledge/status/{task_id}（getKnowledgeTaskStatus）
 *  - GET    /api/knowledge/tasks         分页倒序任务列表（listKnowledgeTasks）
 *
 * 设计（对齐 public/admin-rag-upload.html 审核稿 + FE-M1 无 MOCK）：
 *  - 前端即时校验（扩展名白名单 .md/.txt/.markdown/.pdf/.docx + 单文件 ≤200MB + 数量 ≤50）
 *  - 目标范围切换：公共知识（_default，全部登录用户可见）/ 我的私有知识（user_{id}）
 *  - 上传用 useMutation（L3），失败全局 MutationCache onError → toast（R-7）
 *  - 任务列表 useQuery 5s 轮询，无活跃任务（pending/running）自动停止
 *  - 上传成功 → invalidate 集合与任务 query，行数快照自动刷新闭环
 */
"use client";

import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Loader2, UploadCloud, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { NativeSelect, EmptyState, ErrorState } from "@/components/admin/controls";
import {
  getKnowledgeTaskStatus,
  listKnowledgeTasks,
  uploadKnowledgeFiles,
  uploadMyKnowledgeFiles,
  type KnowledgeTaskDetail,
  type KnowledgeTaskRecord,
} from "@/lib/api/admin/rag";
import { cn } from "@/lib/utils";

/** 允许的扩展名（后端 upload.py _ALLOWED_SUFFIXES） */
const ALLOWED_EXT = ["md", "txt", "markdown", "pdf", "docx"] as const;
const ALLOW_RE = new RegExp(`\\.(${ALLOWED_EXT.join("|")})$`, "i");
const MAX_FILE_BYTES = 200 * 1024 * 1024; // 单文件 ≤200MB
const MAX_FILES = 50; // 单次 ≤50（admin/upload 上限）
const ACCEPT = ".md,.txt,.markdown,.pdf,.docx";

type UploadScope = "public" | "private";

interface PickedFile {
  file: File;
  /** 本地校验失败原因（空 = 通过） */
  reason: string;
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return (bytes / (1024 * 1024 * 1024)).toFixed(2) + "GB";
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + "MB";
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + "KB";
  return bytes + "B";
}

function validateFile(f: File): string {
  if (!ALLOW_RE.test(f.name)) return `非法扩展名（仅 ${ALLOWED_EXT.map((e) => "." + e).join("/")}）`;
  if (f.size > MAX_FILE_BYTES) return "超过单文件 200MB 上限";
  if (f.size <= 0) return "文件为空";
  return "";
}

function taskTypeName(t: string): string {
  return { system_init: "系统导入", user_upload: "用户上传" }[t] ?? t ?? "—";
}

/** 单条导入任务的状态徽章（列表用 succeeded 词汇） */
function TaskStatusBadge({ status }: { status: string }) {
  const tone: Record<string, { label: string; cls: string }> = {
    pending: { label: "排队中", cls: "border-amber-200 bg-amber-50 text-amber-700" },
    running: { label: "导入中", cls: "border-indigo-200 bg-indigo-50 text-indigo-700" },
    succeeded: { label: "完成", cls: "border-emerald-200 bg-emerald-50 text-emerald-700" },
    failed: { label: "失败", cls: "border-rose-200 bg-rose-50 text-rose-700" },
  };
  const t = tone[status] ?? { label: status ?? "—", cls: "border-slate-200 bg-slate-50 text-slate-600" };
  return (
    <Badge variant="outline" className={cn("gap-1", t.cls)}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {t.label}
    </Badge>
  );
}

export function UploadPanel() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [scope, setScope] = useState<UploadScope>("public");
  const [picked, setPicked] = useState<PickedFile[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [detail, setDetail] = useState<{ taskId: string; data: KnowledgeTaskDetail } | null>(null);

  const validFiles = useMemo(() => picked.filter((p) => !p.reason).map((p) => p.file), [picked]);

  /* ---------- 任务列表（5s 轮询，无活跃任务自动停） ---------- */
  const tasksQuery = useQuery({
    queryKey: ["rag", "tasks"] as const,
    queryFn: () => listKnowledgeTasks({ page: 1, page_size: 10 }),
    staleTime: 5_000,
    refetchInterval: (q) => {
      const items = q.state.data?.items;
      const active =
        Array.isArray(items) &&
        items.some((t) => t.status === "pending" || t.status === "running");
      return active ? 5_000 : false;
    },
  });

  /* ---------- 上传（写操作，失败全局 toast） ---------- */
  const uploadMutation = useMutation({
    mutationFn: () =>
      scope === "public"
        ? uploadKnowledgeFiles(validFiles)
        : uploadMyKnowledgeFiles(validFiles),
    onSuccess: (res) => {
      toast.success(`已创建导入任务 ${res.task_id}`);
      setPicked([]);
      // 上传完成 → 行数快照闭环（task61 FR-RAG-02）
      queryClient.invalidateQueries({ queryKey: ["admin", "rag"] });
      queryClient.invalidateQueries({ queryKey: ["rag", "tasks"] });
    },
    // 失败：全局 MutationCache onError → toast（R-7）
  });

  /* ---------- 单任务状态查询（getKnowledgeTaskStatus） ---------- */
  const detailMutation = useMutation({
    mutationFn: (taskId: string) => getKnowledgeTaskStatus(taskId),
    onSuccess: (data, taskId) => setDetail({ taskId, data }),
    // 失败：全局 MutationCache onError → toast（R-7）
  });

  const addFiles = (incoming: File[]) => {
    const next = [...picked];
    let overflow = 0;
    for (const f of incoming) {
      if (next.length >= MAX_FILES) {
        overflow += 1;
        continue;
      }
      next.push({ file: f, reason: validateFile(f) });
    }
    if (overflow > 0) toast.warning(`超过 ${MAX_FILES} 个文件上限，超出 ${overflow} 个已忽略`);
    setPicked(next);
  };

  const removeAt = (index: number) => {
    setPicked((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-4">
      {/* ① 上传面板 */}
      <section className="rounded-xl border border-slate-200 bg-white p-4" data-testid="upload-panel">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-700">上传文件</h3>
          <div className="flex items-center gap-2 text-[12px] text-slate-500">
            目标范围：
            <NativeSelect
              id="upload-scope"
              className="h-8 w-56"
              value={scope}
              onChange={(e) => setScope(e.target.value as UploadScope)}
              data-testid="upload-scope"
            >
              <option value="public">公共知识（_default · 全部登录用户可见）</option>
              <option value="private">我的私有知识（user_{"{id}"} 分区）</option>
            </NativeSelect>
          </div>
        </div>

        {/* 拖拽 / 点击选择 */}
        <label
          htmlFor="upload-files"
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            addFiles(Array.from(e.dataTransfer.files ?? []));
          }}
          className={cn(
            "mt-3 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
            dragOver ? "border-indigo-500 bg-indigo-50" : "border-slate-300 hover:border-indigo-400",
          )}
        >
          <UploadCloud className="h-8 w-8 text-indigo-500" aria-hidden="true" />
          <span className="text-sm font-medium text-slate-700">
            拖拽文件到此处，或点击选择
          </span>
          <span className="text-[12px] text-slate-500">
            支持多选；前端校验：扩展名白名单 + 单文件 ≤200MB + 总数 ≤50
          </span>
          <span className="flex flex-wrap justify-center gap-1.5">
            {ALLOWED_EXT.map((e) => (
              <code key={e} className="rounded-md bg-indigo-50 px-1.5 py-0.5 text-[11px] text-indigo-700">
                .{e}
              </code>
            ))}
          </span>
        </label>
        <input
          ref={inputRef}
          id="upload-files"
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          onChange={(e) => {
            addFiles(Array.from(e.target.files ?? []));
            // 允许重复选择同一文件
            if (inputRef.current) inputRef.current.value = "";
          }}
        />

        {/* 已选文件列表 */}
        {picked.length === 0 ? (
          <p className="mt-3 text-[12px] text-slate-500">
            尚未选择文件 — 最多 {MAX_FILES} 个，前端即时校验拦截
          </p>
        ) : (
          <ul className="mt-3 space-y-2" data-testid="upload-file-list">
            {picked.map((p, i) => (
              <li
                key={`${p.file.name}-${i}`}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-3 py-2",
                  p.reason ? "border-rose-200 bg-rose-50/40" : "border-slate-200 bg-white",
                )}
              >
                <FileText className="h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-slate-800">
                  {p.file.name}
                </span>
                <span className="shrink-0 text-[12px] text-slate-500">{formatSize(p.file.size)}</span>
                {p.reason ? (
                  <span className="shrink-0 text-[12px] text-rose-700" data-testid="file-reason">{p.reason}</span>
                ) : (
                  <span className="shrink-0 text-[12px] text-emerald-600">✓ 通过</span>
                )}
                <button
                  type="button"
                  onClick={() => removeAt(i)}
                  aria-label={`移除 ${p.file.name}`}
                  className="shrink-0 rounded-md p-1 text-slate-500 transition-colors hover:bg-slate-100 hover:text-rose-600"
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-3 flex items-center justify-end">
          <Button
            disabled={validFiles.length === 0 || uploadMutation.isPending}
            onClick={() => uploadMutation.mutate()}
            data-testid="upload-submit"
          >
            {uploadMutation.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <UploadCloud className="mr-1.5 h-4 w-4" aria-hidden="true" />
            )}
            {uploadMutation.isPending
              ? "上传中…"
              : `开始上传（${validFiles.length} 个合法文件）`}
          </Button>
        </div>
      </section>

      {/* ② 导入任务列表 */}
      <section data-testid="upload-tasks">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700">导入任务</h3>
          {tasksQuery.isFetching && (
            <span className="flex items-center gap-1.5 text-[11px] text-indigo-600">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500" aria-hidden="true" />
              5s 轮询 · 无活跃任务自动停止
            </span>
          )}
        </div>

        {tasksQuery.isLoading && !tasksQuery.data ? (
          <EmptyState message="加载任务中…（GET /api/knowledge/tasks）" compact />
        ) : tasksQuery.isError ? (
          <ErrorState
            message={tasksQuery.error instanceof Error ? tasksQuery.error.message : "任务列表加载失败"}
            onRetry={() => tasksQuery.refetch()}
          />
        ) : !tasksQuery.data || tasksQuery.data.items.length === 0 ? (
          <EmptyState message="暂无导入任务" hint="在上方上传知识文件后，此处会跟踪导入进度" compact />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full min-w-[720px] text-sm" data-testid="upload-task-table">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70 text-left text-xs text-slate-500">
                  <th scope="col" className="px-3 py-2.5 font-medium">任务 ID</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">类型</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">文件数</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">分块进度</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">状态</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">错误明细</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">创建时间</th>
                  <th scope="col" className="px-3 py-2.5 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {tasksQuery.data.items.map((t: KnowledgeTaskRecord) => (
                  <tr key={t.task_id} className="hover:bg-slate-50/60" data-testid="upload-task-row">
                    <td className="px-3 py-2.5 font-mono text-[12px] text-slate-600">{t.task_id}</td>
                    <td className="px-3 py-2.5 text-[13px] text-slate-700">{taskTypeName(t.task_type)}</td>
                    <td className="px-3 py-2.5 text-[13px] text-slate-600">
                      {t.source_files?.length ?? 0}
                    </td>
                    <td className="px-3 py-2.5">
                      <ChunkProgress imported={t.imported_chunks} total={t.total_chunks} />
                    </td>
                    <td className="px-3 py-2.5">
                      <TaskStatusBadge status={t.status} />
                    </td>
                    <td className="px-3 py-2.5">
                      {t.error ? (
                        <span className="block max-w-[220px] truncate text-[12px] text-rose-700" title={t.error}>
                          {t.error}
                        </span>
                      ) : (
                        <span className="text-[12px] text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-[12px] text-slate-500">
                      {t.created_at ? String(t.created_at).slice(0, 19).replace("T", " ") : "—"}
                    </td>
                    <td className="px-3 py-2.5">
                      <button
                        type="button"
                        disabled={detailMutation.isPending}
                        onClick={() => detailMutation.mutate(t.task_id)}
                        className="rounded-md px-2 py-1 text-[12px] font-semibold text-indigo-600 transition-colors hover:bg-indigo-50 disabled:opacity-50"
                        data-testid="task-detail-btn"
                      >
                        {detailMutation.isPending && detailMutation.variables === t.task_id
                          ? "查询中…"
                          : "刷新详情"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 单任务详情（GET /api/knowledge/status/{task_id}） */}
        {detail && (
          <div
            className="mt-3 rounded-xl border border-indigo-200 bg-indigo-50/60 p-3 text-[13px] text-slate-700"
            data-testid="upload-task-detail"
            role="status"
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-[12px] text-indigo-700">{detail.taskId}</span>
              <TaskStatusBadge status={detail.data.status} />
            </div>
            <div className="mt-1.5 grid gap-1 text-[12px] text-slate-600 sm:grid-cols-3">
              <span>分块：{detail.data.imported_chunks} / {detail.data.total_chunks}</span>
              <span>开始：{detail.data.started_at ? String(detail.data.started_at).slice(0, 19).replace("T", " ") : "—"}</span>
              <span>结束：{detail.data.finished_at ? String(detail.data.finished_at).slice(0, 19).replace("T", " ") : "—"}</span>
            </div>
            {detail.data.error && (
              <p className="mt-1.5 break-words text-[12px] text-rose-700">{detail.data.error}</p>
            )}
            {Array.isArray(detail.data.source_files) && detail.data.source_files.length > 0 && (
              <p className="mt-1.5 truncate text-[12px] text-slate-500" title={detail.data.source_files.join(", ")}>
                源文件：{detail.data.source_files.join(", ")}
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

/** 分块导入进度条（imported/total + 百分比） */
function ChunkProgress({ imported, total }: { imported: number; total: number }) {
  const pct = total > 0 ? Math.min(100, Math.round((imported / total) * 100)) : 0;
  return (
    <div className="flex min-w-[150px] flex-col gap-1">
      <div className="flex justify-between text-[11px] text-slate-500">
        <span>{imported} / {total} 分块</span>
        {total > 0 && <span>{pct}%</span>}
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-indigo-500 transition-[width] duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}