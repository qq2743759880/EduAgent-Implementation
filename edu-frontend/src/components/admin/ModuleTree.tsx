/**
 * ModuleTree — 系列详情：模块/课次/班次管理（task03）
 *  - 模块 → 课次 嵌套展示（来自 GET /series/{id}/tree）
 *  - 模块 CRUD：POST/PATCH/DELETE /api/admin/courses/modules
 *  - 课次 CRUD：POST/PATCH/DELETE /api/admin/courses/sessions
 *  - 每课次「上传视频」→ VideoUploadFlow（Init→Finalize→Bind）
 *  - 课件上传指引：GET /materials/redirect-upload（P1 管道 307 语义，提示不实现真实上传）
 *  - 班次列表 + 新建班次（POST /cohorts）
 *  - 所有写操作 useMutation + invalidateQueries（L3）；失败全局 toast（R-7）
 */
"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronDown, ChevronRight, FileUp, Layers, Plus, Trash2, Video } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  createAdminCohort,
  createAdminModule,
  createAdminSession,
  deleteAdminCohort,
  deleteAdminModule,
  deleteAdminSession,
  getAdminSeriesTree,
  getMaterialRedirectInfo,
  type AdminCohort,
  type AdminModule,
  type AdminSeriesItem,
  type AdminSession,
  type AdminSeriesTree,
} from "@/lib/api/admin/courses";
import { FieldRow, LoadingState, NativeSelect, ErrorState, EmptyState } from "@/components/admin/controls";
import { VideoUploadFlow } from "@/components/admin/VideoUploadFlow";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export function ModuleTree({ series }: { series: AdminSeriesItem }) {
  const queryClient = useQueryClient();
  const seriesId = series.id;

  const treeQ = useQuery({
    queryKey: ["admin", "series", seriesId, "tree"] as const,
    async queryFn() {
      return getAdminSeriesTree(seriesId);
    },
    staleTime: 15_000,
  });

  const materialQ = useQuery({
    queryKey: ["admin", "materials-redirect"] as const,
    async queryFn() {
      return getMaterialRedirectInfo();
    },
    staleTime: 5 * 60 * 1000,
  });

  const [moduleDlg, setModuleDlg] = useState<{ mode: "create" } | null>(null);
  const [sessionDlg, setSessionDlg] = useState<{ mode: "create"; moduleId: number } | null>(null);
  const [cohortDlg, setCohortDlg] = useState(false);
  const [videoSession, setVideoSession] = useState<AdminSession | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "series", seriesId, "tree"] });
    queryClient.invalidateQueries({ queryKey: ["admin", "series"] });
  };

  const delModule = useMutation({
    mutationFn: (id: number) => deleteAdminModule(id),
    onSuccess: () => {
      toast.success("模块已删除");
      invalidate();
    },
  });

  const delSession = useMutation({
    mutationFn: (id: number) => deleteAdminSession(id),
    onSuccess: () => {
      toast.success("课次已删除");
      invalidate();
    },
  });

  const delCohort = useMutation({
    mutationFn: (id: number) => deleteAdminCohort(id),
    onSuccess: () => {
      toast.success("班次已删除");
      invalidate();
    },
  });

  // 删除类操作统一 window.confirm 二次确认（对抗 #9：误删不可恢复，尤其删模块=级联删全部课次）
  const confirmDeleteModule = (m: AdminModule) => {
    const tip = m.sessions.length > 0
      ? `将级联删除其下 ${m.sessions.length} 个课次并解绑关联视频，此操作不可恢复。`
      : "此操作不可恢复。";
    if (window.confirm(`确定删除模块「${m.module_name}」吗？${tip}`)) {
      delModule.mutate(m.id);
    }
  };

  const confirmDeleteSession = (s: AdminSession) => {
    if (window.confirm(`确定删除课次「${s.session_title}」吗？关联视频将自动解绑，此操作不可恢复。`)) {
      delSession.mutate(s.id);
    }
  };

  const confirmDeleteCohort = (c: AdminCohort) => {
    if (window.confirm(`确定删除班次「${c.cohort_name}」（${c.cohort_code}）吗？此操作不可恢复。`)) {
      delCohort.mutate(c.id);
    }
  };

  if (treeQ.isLoading) return <LoadingState label="加载课程树…" />;
  if (treeQ.isError) {
    return (
      <ErrorState
        message={treeQ.error instanceof Error ? treeQ.error.message : "课程树加载失败"}
        onRetry={() => treeQ.refetch()}
      />
    );
  }

  const tree: AdminSeriesTree | undefined = treeQ.data;
  const modules = tree?.modules ?? [];
  const cohorts = tree?.cohorts ?? [];

  return (
    <div className="space-y-6">
      {/* ===== 概要 ===== */}
      {tree && (
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-slate-500">
          <Badge variant="secondary">共 {modules.length} 个模块</Badge>
          <Badge variant="secondary">共 {tree.summary_total_sessions} 个课次</Badge>
          <Badge variant="secondary">共 {cohorts.length} 个班次</Badge>
        </div>
      )}

      {/* ===== 模块列表 ===== */}
      <section aria-label="模块与课次">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-1.5 text-base font-semibold text-slate-800">
            <Layers className="h-4 w-4 text-indigo-600" /> 模块与课次
          </h2>
          <Button size="sm" onClick={() => setModuleDlg({ mode: "create" })}>
            <Plus className="mr-1 h-3.5 w-3.5" /> 新增模块
          </Button>
        </div>

        {modules.length === 0 ? (
          <EmptyState message="还没有模块" hint="点击「新增模块」建立课程结构" />
        ) : (
          <div className="space-y-3">
            {modules.map((m) => (
              <ModuleCard
                key={m.id}
                module={m}
                onAddSession={() => setSessionDlg({ mode: "create", moduleId: m.id })}
                onDeleteModule={() => confirmDeleteModule(m)}
                onDeleteSession={(sid) => {
                  const s = m.sessions.find((x) => x.id === sid);
                  if (s) confirmDeleteSession(s);
                }}
                onUploadVideo={(s) => setVideoSession(s)}
                deleting={delModule.isPending && delModule.variables === m.id}
              />
            ))}
          </div>
        )}
      </section>

      {/* ===== 班次 ===== */}
      <section aria-label="班次管理">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-800">班次</h2>
          <Button size="sm" variant="outline" onClick={() => setCohortDlg(true)}>
            <Plus className="mr-1 h-3.5 w-3.5" /> 新增班次
          </Button>
        </div>
        {cohorts.length === 0 ? (
          <EmptyState message="暂无班次" />
        ) : (
          <div className="grid gap-2 sm:grid-cols-2">
            {cohorts.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm"
              >
                <div className="min-w-0">
                  <div className="font-medium text-slate-800">{c.cohort_name}</div>
                  <div className="text-xs text-slate-600">
                    {c.cohort_code} · 已报名 {c.current_student_count}/{c.max_student_count}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`删除班次 ${c.cohort_name}`}
                  onClick={() => confirmDeleteCohort(c)}
                >
                  <Trash2 className="h-3.5 w-3.5 text-rose-500" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ===== 课件上传提示（P1 管道重定向） ===== */}
      {materialQ.data && (
        <section
          aria-label="课件上传指引"
          className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 text-[13px] text-amber-800"
        >
          <div className="flex items-start gap-2.5">
            <FileUp className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="space-y-1">
              <div className="font-medium">课件上传走 P1 知识库管道</div>
              <p>
                {materialQ.data.tip}
              </p>
              <p className="font-mono text-xs">
                {materialQ.data.method} {materialQ.data.redirect_endpoint}
                {materialQ.data.auth_header_required ? "（需携带鉴权头）" : ""}
              </p>
            </div>
          </div>
        </section>
      )}

      {/* ===== 弹窗 ===== */}
      {moduleDlg && (
        <ModuleDialog
          seriesId={seriesId}
          stageNo={modules.length + 1}
          onClose={() => setModuleDlg(null)}
          onSaved={() => {
            setModuleDlg(null);
            invalidate();
          }}
        />
      )}
      {sessionDlg && (
        <SessionDialog
          moduleId={sessionDlg.moduleId}
          onClose={() => setSessionDlg(null)}
          onSaved={() => {
            setSessionDlg(null);
            invalidate();
          }}
        />
      )}
      {cohortDlg && (
        <CohortDialog
          seriesId={seriesId}
          onClose={() => setCohortDlg(false)}
          onSaved={() => {
            setCohortDlg(false);
            invalidate();
          }}
        />
      )}
      {videoSession && (
        <VideoUploadFlow
          open={Boolean(videoSession)}
          onOpenChange={(open) => !open && setVideoSession(null)}
          session={videoSession}
          onBound={() => invalidate()}
        />
      )}
    </div>
  );
}

/* ---------------- 子组件/工具 ---------------- */

function teachingBadgeCls(status: string): string {
  switch (status) {
    case "completed":
      return "bg-emerald-50 text-emerald-700";
    case "in_progress":
      // D-05：sky 为基准外色 → 进行中=中性强调 indigo（与 VideoUploadFlow 过程块 indigo 语义一致）
      return "bg-indigo-50 text-indigo-600";
    case "cancelled":
      return "bg-rose-50 text-rose-700";
    default:
      return "bg-slate-100 text-slate-500";
  }
}

/* ---------------- 模块卡片 ---------------- */
function ModuleCard({
  module,
  onAddSession,
  onDeleteModule,
  onDeleteSession,
  onUploadVideo,
  deleting,
}: {
  module: AdminModule;
  onAddSession: () => void;
  onDeleteModule: () => void;
  onDeleteSession: (sessionId: number) => void;
  onUploadVideo: (session: AdminSession) => void;
  deleting?: boolean;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50/60 px-3 py-2.5">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          {open ? <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />}
          <BookOpen className="h-4 w-4 shrink-0 text-indigo-600" />
          <span className="truncate font-medium text-slate-800">{module.module_name}</span>
          <Badge variant="outline" className="shrink-0">{module.stage_no} 阶段</Badge>
          <span className="shrink-0 text-xs text-slate-600">{module.sessions.length} 课次</span>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <Button size="sm" variant="ghost" onClick={onAddSession}>
            <Plus className="mr-1 h-3.5 w-3.5" /> 课次
          </Button>
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label={`删除模块 ${module.module_name}`}
            disabled={deleting}
            onClick={onDeleteModule}
          >
            <Trash2 className="h-3.5 w-3.5 text-rose-500" />
          </Button>
        </div>
      </div>

      {open && (
        <ul className="divide-y divide-slate-100 px-3">
          {module.sessions.length === 0 && (
            // D-14：课次空态与模块/班次空态同用 EmptyState（嵌套层级用 compact 形态）
            <li className="px-3 py-3">
              <EmptyState compact message="该模块还没有课次" />
            </li>
          )}
          {module.sessions.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-2 py-2.5">
              <div className="min-w-0">
                <div className="truncate text-sm text-slate-700">
                  <span className="mr-1.5 font-mono text-xs text-slate-600">#{s.session_no}</span>
                  {s.session_title}
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-slate-600">
                  <span>{s.duration_minutes} 分钟</span>
                  <span className={cn("rounded-full px-1.5 py-px", teachingBadgeCls(s.teaching_status))}>
                    {s.teaching_status}
                  </span>
                  {s.video_url ? (
                    // D-19：已绑/未绑视频由裸文字改为 chip/badge 形态（emerald/amber 语义保留）
                    <span className="rounded-full bg-emerald-50 px-1.5 py-px text-emerald-700">已绑视频</span>
                  ) : (
                    <span className="rounded-full bg-amber-50 px-1.5 py-px text-amber-700">未绑视频</span>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  size="sm"
                  variant={s.video_url ? "outline" : "default"}
                  onClick={() => onUploadVideo(s)}
                >
                  <Video className="mr-1 h-3.5 w-3.5" />
                  {s.video_url ? "更换视频" : "上传视频"}
                </Button>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`删除课次 ${s.session_title}`}
                  onClick={() => onDeleteSession(s.id)}
                >
                  <Trash2 className="h-3.5 w-3.5 text-rose-500" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ---------------- 新建模块 ---------------- */
function ModuleDialog({
  seriesId,
  stageNo,
  onClose,
  onSaved,
}: {
  seriesId: number;
  stageNo: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({ module_code: "", module_name: "", stage_no: stageNo, lesson_count: 0, total_hours: 0, description: "" });
  const create = useMutation({
    mutationFn: () =>
      createAdminModule({
        series_id: seriesId,
        module_code: form.module_code.trim(),
        module_name: form.module_name.trim(),
        stage_no: Number(form.stage_no),
        lesson_count: Number(form.lesson_count || 0),
        total_hours: Number(form.total_hours || 0),
        description: form.description || undefined,
      }),
    onSuccess: () => {
      toast.success("模块已创建");
      onSaved();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>新增模块</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <FieldRow id="module-name" label="模块名称" required>
            <Input value={form.module_name} onChange={(e) => setForm((f) => ({ ...f, module_name: e.target.value }))} placeholder="如：词汇基础" />
          </FieldRow>
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="module-code" label="模块编码" required>
              <Input value={form.module_code} onChange={(e) => setForm((f) => ({ ...f, module_code: e.target.value }))} placeholder="如：MOD-01" />
            </FieldRow>
            <FieldRow id="module-stage-no" label="阶段序号">
              <Input type="number" min={1} value={form.stage_no} onChange={(e) => setForm((f) => ({ ...f, stage_no: Number(e.target.value) }))} />
            </FieldRow>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="module-lesson-count" label="课次数量">
              <Input type="number" min={0} value={form.lesson_count} onChange={(e) => setForm((f) => ({ ...f, lesson_count: Number(e.target.value) }))} />
            </FieldRow>
            <FieldRow id="module-total-hours" label="总课时（小时）">
              <Input type="number" min={0} step="0.5" value={form.total_hours} onChange={(e) => setForm((f) => ({ ...f, total_hours: Number(e.target.value) }))} />
            </FieldRow>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button
            onClick={() => form.module_name.trim() && form.module_code.trim() && create.mutate()}
            disabled={create.isPending || !form.module_name.trim() || !form.module_code.trim()}
          >
            {create.isPending ? "创建中…" : "创建模块"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------- 新建课次 ---------------- */
function SessionDialog({
  moduleId,
  onClose,
  onSaved,
}: {
  moduleId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({ session_no: 1, session_title: "", duration_minutes: 45, teaching_status: "scheduled", teaching_date: "" });
  const create = useMutation({
    mutationFn: () =>
      createAdminSession({
        module_id: moduleId,
        session_no: Number(form.session_no),
        session_title: form.session_title.trim(),
        duration_minutes: Number(form.duration_minutes || 45),
        teaching_status: form.teaching_status,
        teaching_date: form.teaching_date || undefined,
      }),
    onSuccess: () => {
      toast.success("课次已创建");
      onSaved();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>新增课次</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <FieldRow id="session-title" label="课次标题" required>
            <Input value={form.session_title} onChange={(e) => setForm((f) => ({ ...f, session_title: e.target.value }))} placeholder="如：第 1 讲 词汇导学" />
          </FieldRow>
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="session-no" label="课次序号">
              <Input type="number" min={1} value={form.session_no} onChange={(e) => setForm((f) => ({ ...f, session_no: Number(e.target.value) }))} />
            </FieldRow>
            <FieldRow id="session-duration" label="时长（分钟）">
              <Input type="number" min={1} value={form.duration_minutes} onChange={(e) => setForm((f) => ({ ...f, duration_minutes: Number(e.target.value) }))} />
            </FieldRow>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="session-status" label="教学状态">
              <NativeSelect value={form.teaching_status} onChange={(e) => setForm((f) => ({ ...f, teaching_status: e.target.value }))}>
                {["scheduled", "in_progress", "completed", "cancelled"].map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </NativeSelect>
            </FieldRow>
            <FieldRow id="session-date" label="授课日期">
              <Input type="date" value={form.teaching_date} onChange={(e) => setForm((f) => ({ ...f, teaching_date: e.target.value }))} />
            </FieldRow>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button
            onClick={() => form.session_title.trim() && create.mutate()}
            disabled={create.isPending || !form.session_title.trim()}
          >
            {create.isPending ? "创建中…" : "创建课次"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------- 新建班次 ---------------- */
function CohortDialog({
  seriesId,
  onClose,
  onSaved,
}: {
  seriesId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({ cohort_code: "", cohort_name: "", max_student_count: 200, sale_price: 0, start_date: "", end_date: "" });
  const create = useMutation({
    mutationFn: () =>
      createAdminCohort({
        series_id: seriesId,
        cohort_code: form.cohort_code.trim(),
        cohort_name: form.cohort_name.trim(),
        max_student_count: Number(form.max_student_count || 200),
        sale_price: Number(form.sale_price || 0),
        start_date: form.start_date || undefined,
        end_date: form.end_date || undefined,
      }),
    onSuccess: () => {
      toast.success("班次已创建");
      onSaved();
    },
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>新增班次</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="cohort-code" label="班次编码" required>
              <Input value={form.cohort_code} onChange={(e) => setForm((f) => ({ ...f, cohort_code: e.target.value }))} placeholder="如：COH-2026A" />
            </FieldRow>
            <FieldRow id="cohort-name" label="班次名称" required>
              <Input value={form.cohort_name} onChange={(e) => setForm((f) => ({ ...f, cohort_name: e.target.value }))} placeholder="如：2026 春 A 班" />
            </FieldRow>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="cohort-capacity" label="容量">
              <Input type="number" min={1} value={form.max_student_count} onChange={(e) => setForm((f) => ({ ...f, max_student_count: Number(e.target.value) }))} />
            </FieldRow>
            <FieldRow id="cohort-price" label="售价（元）">
              <Input type="number" min={0} step="0.01" value={form.sale_price} onChange={(e) => setForm((f) => ({ ...f, sale_price: Number(e.target.value) }))} />
            </FieldRow>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id="cohort-start" label="开课日期">
              <Input type="date" value={form.start_date} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} />
            </FieldRow>
            <FieldRow id="cohort-end" label="结课日期">
              <Input type="date" value={form.end_date} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))} />
            </FieldRow>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button
            onClick={() => form.cohort_name.trim() && form.cohort_code.trim() && create.mutate()}
            disabled={create.isPending || !form.cohort_name.trim() || !form.cohort_code.trim()}
          >
            {create.isPending ? "创建中…" : "创建班次"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
