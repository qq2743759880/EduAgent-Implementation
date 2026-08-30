/**
 * ModuleTree — 系列详情四级 CRUD 面板（task57）
 *
 * 数据结构（task12 契约③，禁 MOCK）：
 *   series → cohorts（GET /series/{id}/cohorts，裸数组）
 *           → 选中 cohort → modules（GET /cohorts/{cohort_id}/modules）
 *           → 展开 module → sessions（GET /modules/{module_id}/sessions）
 * 归属：Module.cohort_id；Session.series_cohort_course_id（= module 物理 ID）；Cohort 创建必填 institution_id + head_teacher_id。
 *
 * 视频：每课次 resource 四入口（视频开 VideoChunkedUpload 分片上传+转码轮询；课件/作业/考试为契约缺口 → toast 指引）。
 * 软删：cohort/module/session 均 DELETE → ConfirmDialog 二次确认（提示 yn=0 级联语义）。
 * 唯一约束冲突：mutation onError 按后端业务码 40901~40907 分支提示（uniqueConflictTip）。
 *
 * 风格 candy-playful：色全走语义 token + candy 系，禁 slate。
 */
"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen, Calendar, ChevronDown, ChevronRight, FileText, ListChecks, PencilLine,
  Plus, Trash2, Video, Layers,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ErrorState, EmptyState, LoadingState, NativeSelect, FieldRow } from "@/components/admin/controls";
import { VideoChunkedUpload } from "@/components/admin/VideoChunkedUpload";
import {
  listAdminCohorts, createAdminCohort, updateAdminCohort, deleteAdminCohort,
  listAdminModules, createAdminModule, updateAdminModule, deleteAdminModule,
  listAdminSessions, createAdminSession, updateAdminSession, deleteAdminSession,
  TECHING_STATUS_OPTIONS,
  uniqueConflictTip,
  type AdminSeries, type AdminCohort, type AdminModule, type AdminSession,
  type TeachingStatusCode,
  type CohortCreateInput, type ModuleCreateInput, type SessionCreateInput,
} from "@/lib/api/admin/courses";
import { cn } from "@/lib/utils";

export function ModuleTree({ series }: { series: AdminSeries }) {
  const qc = useQueryClient();
  const [rawCohortId, setRawCohortId] = useState<number | null>(null);
  const [expandedModules, setExpandedModules] = useState<Set<number>>(new Set());

  const cohortsQ = useQuery({
    queryKey: ["admin", "series", series.id, "cohorts"] as const,
    queryFn: () => listAdminCohorts(series.id),
    staleTime: 15_000,
  });

  const activeCohortId = rawCohortId ?? (cohortsQ.data && cohortsQ.data.length > 0 ? cohortsQ.data[0].id : null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["admin", "series", series.id, "cohorts"] });
    if (activeCohortId) qc.invalidateQueries({ queryKey: ["admin", "series", series.id, "cohort", activeCohortId, "modules"] });
  };

  const activeCohort = cohortsQ.data?.find((c) => c.id === activeCohortId) ?? null;

  /* ---------- Cohorts CRUD ---------- */
  const createCohort = useMutation({
    mutationFn: (input: CohortCreateInput) => createAdminCohort(input),
    onSuccess: () => { toast.success("班次已创建"); invalidate(); },
    onError: (e) => toast.error(uniqueConflictTip(e, "创建班次失败")),
  });
  const updateCohort = useMutation({
    mutationFn: (v: { id: number; input: Partial<CohortCreateInput> }) => updateAdminCohort(v.id, v.input),
    onSuccess: () => { toast.success("班次已更新"); invalidate(); },
    onError: (e) => toast.error(uniqueConflictTip(e, "更新班次失败")),
  });
  const deleteCohort = useMutation({
    mutationFn: (id: number) => deleteAdminCohort(id),
    onSuccess: (__d, id) => {
      toast.success("班次已删除（软删 yn=0）");
      if (activeCohortId === id) { setRawCohortId(null); setExpandedModules(new Set()); }
      invalidate();
    },
    onError: (e) => toast.error(uniqueConflictTip(e, "删除班次失败")),
  });

  /* ---------- Module/Session 快捷失效 ---------- */
  const invalidateModules = (cid: number) => {
    qc.invalidateQueries({ queryKey: ["admin", "series", series.id, "cohort", cid, "modules"] });
  };
  const invalidateSessions = (mid: number) => {
    qc.invalidateQueries({ queryKey: ["admin", "series", series.id, "module", mid, "sessions"] });
  };

  const createModule = useMutation({
    mutationFn: (input: ModuleCreateInput) => createAdminModule(input),
    onSuccess: () => { toast.success("模块已创建"); invalidateModules(activeCohortId!); },
    onError: (e) => toast.error(uniqueConflictTip(e, "创建模块失败")),
  });
  const updateModule = useMutation({
    mutationFn: (v: { id: number; input: Partial<ModuleCreateInput> }) => updateAdminModule(v.id, v.input),
    onSuccess: () => { toast.success("模块已更新"); invalidateModules(activeCohortId!); },
    onError: (e) => toast.error(uniqueConflictTip(e, "更新模块失败")),
  });
  const deleteModule = useMutation({
    mutationFn: (id: number) => deleteAdminModule(id),
    onSuccess: () => { toast.success("模块已删除（软删 yn=0）"); invalidateModules(activeCohortId!); },
    onError: (e) => toast.error(uniqueConflictTip(e, "删除模块失败")),
  });

  const createSession = useMutation({
    mutationFn: (input: SessionCreateInput) => createAdminSession(input),
    onSuccess: (__d, v) => { toast.success("课次已创建"); invalidateSessions(v.series_cohort_course_id); },
    onError: (e) => toast.error(uniqueConflictTip(e, "创建课次失败")),
  });
  const updateSession = useMutation({
    mutationFn: (v: { id: number; input: Partial<SessionCreateInput> }) => updateAdminSession(v.id, v.input),
    onSuccess: (__d, v) => { toast.success("课次已更新"); invalidateSessions(v.input.series_cohort_course_id ?? 0); },
    onError: (e) => toast.error(uniqueConflictTip(e, "更新课次失败")),
  });
  const deleteSession = useMutation({
    mutationFn: (id: number) => deleteAdminSession(id),
    onSuccess: () => { toast.success("课次已删除（软删 yn=0）"); },
    onError: (e) => toast.error(uniqueConflictTip(e, "删除课次失败")),
  });

  /* ---------- Dialog 状态 ---------- */
  const [cohortForm, setCohortForm] = useState<{ mode: "create" } | { mode: "edit"; cohort: AdminCohort } | null>(null);
  const [moduleForm, setModuleForm] = useState<{ mode: "create"; cohortId: number } | { mode: "edit"; module: AdminModule } | null>(null);
  const [sessionForm, setSessionForm] = useState<{ mode: "create"; module: AdminModule } | { mode: "edit"; session: AdminSession } | null>(null);
  const [videoSession, setVideoSession] = useState<AdminSession | null>(null);

  const [delCohort, setDelCohort] = useState<AdminCohort | null>(null);
  const [delModule, setDelModule] = useState<AdminModule | null>(null);
  const [delSession, setDelSession] = useState<AdminSession | null>(null);

  if (cohortsQ.isLoading) return <LoadingState label="加载班次…" />;
  if (cohortsQ.isError || !cohortsQ.data) {
    return <ErrorState message={cohortsQ.error instanceof Error ? cohortsQ.error.message : "班次加载失败"} onRetry={() => cohortsQ.refetch()} />;
  }
  const cohorts = cohortsQ.data;

  return (
    <div className="space-y-4">
      {/* ===== 班次 DataTable ===== */}
      <CohortTable
        cohorts={cohorts}
        activeCohortId={activeCohortId}
        onSelect={setRawCohortId}
        onCreate={() => setCohortForm({ mode: "create" })}
        onEdit={(c) => setCohortForm({ mode: "edit", cohort: c })}
        onDelete={(c) => setDelCohort(c)}
      />

      {/* ===== 选中班次 → 模块/课次 ===== */}
      {activeCohort ? (
        <ModuleSection
          key={activeCohort.id}
          seriesId={series.id}
          cohort={activeCohort}
          expandedModules={expandedModules}
          onToggleModule={(mid) => {
            setExpandedModules((prev) => {
              const next = new Set(prev);
              if (next.has(mid)) next.delete(mid); else next.add(mid);
              return next;
            });
          }}
          onCreateModule={() => setModuleForm({ mode: "create", cohortId: activeCohort.id })}
          onEditModule={(m) => setModuleForm({ mode: "edit", module: m })}
          onDeleteModule={(m) => setDelModule(m)}
          onCreateSession={(m) => setSessionForm({ mode: "create", module: m })}
          onEditSession={(s) => setSessionForm({ mode: "edit", session: s })}
          onDeleteSession={(s) => setDelSession(s)}
          onOpenVideo={(s) => setVideoSession(s)}
        />
      ) : (
        <EmptyState message="请先选择班次" hint="系列下暂无班次，可点击「新增班次」开始搭建" />
      )}

      {/* ===== Dialogs ===== */}
      {cohortForm && (
        <CohortFormDialog
          key={cohortForm.mode === "create" ? "cohort-new" : `cohort-${cohortForm.cohort.id}`}
          series={series}
          cohort={cohortForm.mode === "edit" ? cohortForm.cohort : undefined}
          open={!!cohortForm}
          onOpenChange={(o) => !o && setCohortForm(null)}
          onSubmit={cohortForm.mode === "create"
            ? (v) => { createCohort.mutate(v as CohortCreateInput); setCohortForm(null); }
            : (v) => { updateCohort.mutate({ id: cohortForm.cohort.id, input: v }); setCohortForm(null); }}
        />
      )}
      {moduleForm && (
        <ModuleFormDialog
          key={moduleForm.mode === "create" ? "module-new" : `module-${moduleForm.module.id}`}
          cohortId={moduleForm.mode === "create" ? moduleForm.cohortId : moduleForm.module.cohort_id}
          module={moduleForm.mode === "edit" ? moduleForm.module : undefined}
          open={!!moduleForm}
          onOpenChange={(o) => !o && setModuleForm(null)}
          onSubmit={moduleForm.mode === "create"
            ? (v) => { createModule.mutate(v as ModuleCreateInput); setModuleForm(null); }
            : (v) => { updateModule.mutate({ id: moduleForm.module.id, input: v }); setModuleForm(null); }}
        />
      )}
      {sessionForm && (
        <SessionFormDialog
          key={sessionForm.mode === "create" ? "session-new" : `session-${sessionForm.session.id}`}
          module={sessionForm.mode === "create" ? sessionForm.module : undefined}
          session={sessionForm.mode === "edit" ? sessionForm.session : undefined}
          open={!!sessionForm}
          onOpenChange={(o) => !o && setSessionForm(null)}
          onSubmit={sessionForm.mode === "create"
            ? (v) => { createSession.mutate(v as SessionCreateInput); setSessionForm(null); }
            : (v) => { updateSession.mutate({ id: sessionForm.session.id, input: v }); setSessionForm(null); }}
        />
      )}

      {videoSession && (
        <VideoChunkedUpload
          open={!!videoSession}
          onOpenChange={(o) => !o && setVideoSession(null)}
          session={videoSession}
          onBound={() => invalidateSessions(videoSession.series_cohort_course_id)}
        />
      )}

      <ConfirmDialog
        open={!!delCohort}
        onOpenChange={(o) => !o && setDelCohort(null)}
        title="删除班次"
        description={delCohort ? `确定删除班次「${delCohort.cohort_name}」吗？软删（yn=0），将级联其下模块/课次不可见，数据保留。` : ""}
        confirmLabel="确认删除（软删）"
        onConfirm={() => { if (delCohort) { deleteCohort.mutate(delCohort.id); setDelCohort(null); } }}
      />
      <ConfirmDialog
        open={!!delModule}
        onOpenChange={(o) => !o && setDelModule(null)}
        title="删除模块"
        description={delModule ? `确定删除模块「${delModule.module_name}」吗？软删（yn=0），将级联其下 ${delModule.lesson_count} 个课次并解绑关联视频。` : ""}
        confirmLabel="确认删除（软删）"
        onConfirm={() => { if (delModule) { deleteModule.mutate(delModule.id); setDelModule(null); } }}
      />
      <ConfirmDialog
        open={!!delSession}
        onOpenChange={(o) => !o && setDelSession(null)}
        title="删除课次"
        description={delSession ? `确定删除课次「${delSession.session_title}」吗？软删（yn=0），关联视频自动解绑。` : ""}
        confirmLabel="确认删除（软删）"
        onConfirm={() => { if (delSession) { deleteSession.mutate(delSession.id); setDelSession(null); } }}
      />
    </div>
  );
}

/* ============================================================
 * 班次表格
 * ============================================================ */
function CohortTable({
  cohorts, activeCohortId, onSelect, onCreate, onEdit, onDelete,
}: {
  cohorts: AdminCohort[];
  activeCohortId: number | null;
  onSelect: (id: number) => void;
  onCreate: () => void;
  onEdit: (c: AdminCohort) => void;
  onDelete: (c: AdminCohort) => void;
}) {
  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Layers className="h-4 w-4 text-primary" /> 班次
          <span className="text-xs font-normal text-muted-foreground">共 {cohorts.length} 个</span>
        </h3>
        <Button size="sm" onClick={onCreate} data-testid="cohort-create">
          <Plus className="mr-1" /> 新增班次
        </Button>
      </div>
      {cohorts.length === 0 ? (
        <EmptyState compact message="暂无班次" hint="点击「新增班次」开始搭建" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] border-collapse text-sm" data-testid="cohort-table">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-3 font-medium">班次</th>
                <th className="px-4 py-3 font-medium">售价</th>
                <th className="px-4 py-3 font-medium">容量（已报）</th>
                <th className="hidden px-4 py-3 font-medium md:table-cell">起止</th>
                <th className="px-4 py-3 pr-5 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {cohorts.map((c) => {
                const active = c.id === activeCohortId;
                return (
                  <tr
                    key={c.id}
                    onClick={() => { onSelect(c.id); onEdit(c); }}
                    className={cn("cursor-pointer border-b border-border last:border-0", active && "bg-primary-soft/60")}
                    data-selected={active || undefined}
                    data-testid={`cohort-row-${c.id}`}
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{c.cohort_name}</div>
                      <code className="font-mono text-xs text-muted-foreground">{c.cohort_code}</code>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">¥{c.sale_price}</td>
                    <td className="px-4 py-3 text-muted-foreground"><b className="text-foreground">{c.current_student_count}</b>/{c.max_student_count}</td>
                    <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">
                      {c.start_date ? c.start_date.slice(0, 10) : "—"} ~ {c.end_date ? c.end_date.slice(0, 10) : "—"}
                    </td>
                    <td className="px-4 py-3 pr-5 text-right">
                      <div className="inline-flex gap-1">
                        <Button variant="ghost" size="sm" data-testid={`cohort-edit-${c.id}`} onClick={(e) => { e.stopPropagation(); onEdit(c); }}>
                          <PencilLine className="h-3.5 w-3.5" /> 编辑
                        </Button>
                        <Button variant="ghost" size="sm" className="text-destructive" data-testid={`cohort-del-${c.id}`} onClick={(e) => { e.stopPropagation(); onDelete(c); }}>
                          <Trash2 className="h-3.5 w-3.5" /> 删除
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ============================================================
 * 模块 + 课次 section（选中班次）
 * ============================================================ */
function ModuleSection({
  seriesId, cohort, expandedModules, onToggleModule,
  onCreateModule, onEditModule, onDeleteModule, onCreateSession, onEditSession, onDeleteSession, onOpenVideo,
}: {
  seriesId: number;
  cohort: AdminCohort;
  expandedModules: Set<number>;
  onToggleModule: (id: number) => void;
  onCreateModule: () => void;
  onEditModule: (m: AdminModule) => void;
  onDeleteModule: (m: AdminModule) => void;
  onCreateSession: (m: AdminModule) => void;
  onEditSession: (s: AdminSession) => void;
  onDeleteSession: (s: AdminSession) => void;
  onOpenVideo: (s: AdminSession) => void;
}) {
  const modulesQ = useQuery({
    queryKey: ["admin", "series", seriesId, "cohort", cohort.id, "modules"] as const,
    queryFn: () => listAdminModules(cohort.id),
    staleTime: 15_000,
  });

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-foreground">
          模块与课次 · 绑班次「{cohort.cohort_name}」
          {modulesQ.data && <span className="ml-1 text-xs font-normal text-muted-foreground">共 {modulesQ.data.length} 模块</span>}
        </h3>
        <Button size="sm" onClick={onCreateModule} data-testid="module-create">
          <Plus className="mr-1" /> 新增模块
        </Button>
      </div>

      {modulesQ.isLoading ? <LoadingState label="加载模块…" />
        : modulesQ.isError ? <ErrorState message="模块加载失败" onRetry={() => modulesQ.refetch()} />
        : modulesQ.data && modulesQ.data.length === 0 ? <EmptyState compact message="暂无模块" hint="点击「新增模块」开始搭建" />
        : (
          <div className="space-y-2 p-3">
            {modulesQ.data!.map((m) => {
              const expanded = expandedModules.has(m.id);
              return (
                <ModulePanel
                  key={m.id}
                  module={m}
                  expanded={expanded}
                  onToggle={() => onToggleModule(m.id)}
                  onEdit={() => onEditModule(m)}
                  onDelete={() => onDeleteModule(m)}
                  onCreateSession={() => onCreateSession(m)}
                  onEditSession={onEditSession}
                  onDeleteSession={onDeleteSession}
                  onOpenVideo={onOpenVideo}
                />
              );
            })}
          </div>
        )}
    </div>
  );
}

/* ---------- 单个模块面板 ---------- */
function ModulePanel({
  module, expanded, onToggle,
  onEdit, onDelete, onCreateSession, onEditSession, onDeleteSession, onOpenVideo,
}: {
  module: AdminModule;
  expanded: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onCreateSession: () => void;
  onEditSession: (s: AdminSession) => void;
  onDeleteSession: (s: AdminSession) => void;
  onOpenVideo: (s: AdminSession) => void;
}) {
  const sessionsQ = useQuery({
    queryKey: ["admin", "series", "module", module.id, "sessions"] as const,
    queryFn: () => listAdminSessions(module.id),
    enabled: expanded,
    staleTime: 15_000,
  });

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 bg-muted/40 px-3 py-2.5">
        <button type="button" onClick={onToggle} aria-expanded={expanded} className="flex min-w-0 flex-1 items-center gap-2 text-left">
          {expanded ? <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />}
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-candy-blue/10 text-candy-blue"><BookOpen className="h-3.5 w-3.5" /></span>
          <span className="truncate text-sm font-semibold text-foreground">{module.module_name}</span>
          <Badge className="border-transparent bg-muted text-muted-foreground">stage {module.stage_no}</Badge>
          <span className="hidden text-xs text-muted-foreground sm:inline">{module.lesson_count} 课次 · {module.total_hours} 学时</span>
        </button>
        <div className="flex shrink-0 gap-1">
          <Button variant="ghost" size="sm" onClick={onCreateSession} data-testid={`session-create-${module.id}`}>
            <Plus className="h-3.5 w-3.5" /> 新增课次
          </Button>
          <Button variant="ghost" size="icon" aria-label="编辑模块" onClick={onEdit}><PencilLine className="h-4 w-4" /></Button>
          <Button variant="ghost" size="icon" aria-label="删除模块" className="text-destructive" onClick={onDelete}><Trash2 className="h-4 w-4" /></Button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border">
          {sessionsQ.isLoading ? <LoadingState label="加载课次…" />
            : sessionsQ.isError ? <ErrorState message="课次加载失败" onRetry={() => sessionsQ.refetch()} />
            : sessionsQ.data && sessionsQ.data.length === 0 ? <EmptyState compact message="暂无课次" hint="点击「新增课次」添加" />
            : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-sm" data-testid="session-table">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="px-3 py-2 font-medium">序号</th>
                      <th className="px-3 py-2 font-medium">标题</th>
                      <th className="px-3 py-2 font-medium">日期</th>
                      <th className="px-3 py-2 font-medium">状态</th>
                      <th className="px-3 py-2 font-medium">资源</th>
                      <th className="px-3 py-2 pr-4 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessionsQ.data!.map((s) => (
                      <tr key={s.id} className="border-b border-border last:border-0" data-testid={`session-row-${s.id}`}>
                        <td className="px-3 py-2.5 font-mono text-xs text-muted-foreground">#{s.session_no}</td>
                        <td className="px-3 py-2.5 font-medium text-foreground">{s.session_title}</td>
                        <td className="px-3 py-2.5 text-muted-foreground">
                          <span className="inline-flex items-center gap-1"><Calendar className="h-3 w-3" />{s.teaching_date ? s.teaching_date.slice(0, 10) : "—"}</span>
                        </td>
                        <td className="px-3 py-2.5"><SessionStatusBadge status={s.teaching_status} /></td>
                        <td className="px-3 py-2.5">
                          <div className="flex gap-1.5">
                            <ResourceChip icon={<Video className="h-3.5 w-3.5" />} label="视频" active onClick={() => onOpenVideo(s)} />
                            <ResourceChip icon={<FileText className="h-3.5 w-3.5" />} label="课件" />
                            <ResourceChip icon={<ListChecks className="h-3.5 w-3.5" />} label="作业" />
                            <ResourceChip icon={<ClipboardIcon />} label="考试" />
                          </div>
                        </td>
                        <td className="px-3 py-2.5 pr-4 text-right">
                          <div className="inline-flex gap-1">
                            <Button variant="ghost" size="icon" aria-label="编辑课次" onClick={() => onEditSession(s)}><PencilLine className="h-4 w-4" /></Button>
                            <Button variant="ghost" size="icon" aria-label="删除课次" className="text-destructive" onClick={() => onDeleteSession(s)}><Trash2 className="h-4 w-4" /></Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </div>
      )}
    </div>
  );
}

function ClipboardIcon() {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    </svg>
  );
}

function ResourceChip({ icon, label, active, onClick }: { icon: React.ReactNode; label: string; active?: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!active && !onClick}
      title={active ? `打开${label}上传` : `${label}：契约缺口，后端无活跃端点`}
      className={cn(
        "inline-flex items-center gap-1 rounded-lg border border-border px-2 py-1 text-xs font-medium transition-colors",
        active ? "bg-primary-soft text-primary-soft-foreground hover:bg-primary/10 cursor-pointer" : "bg-muted text-muted-foreground cursor-not-allowed",
      )}
    >
      {icon}{label}
    </button>
  );
}

function SessionStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    scheduled: "border-transparent bg-muted text-muted-foreground",
    in_progress: "border-transparent bg-primary/10 text-primary",
    completed: "border-transparent bg-candy-green-soft text-candy-green",
    cancelled: "border-transparent bg-destructive/10 text-destructive",
  };
  const label = TECHING_STATUS_OPTIONS.find((t) => t.value === status)?.label ?? status;
  return <Badge className={map[status] ?? "border-transparent bg-muted text-muted-foreground"}>{label}</Badge>;
}

/* ============================================================
 * 表单对话框
 * ============================================================ */
function CohortFormDialog({
  series, cohort, open, onOpenChange, onSubmit,
}: {
  series: AdminSeries;
  cohort?: AdminCohort;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSubmit: (input: CohortCreateInput | Partial<CohortCreateInput>) => void;
}) {
  const [headTeacher, setHeadTeacher] = useState(String(cohort?.head_teacher_id ?? ""));
  const [code, setCode] = useState(cohort?.cohort_code ?? "");
  const [name, setName] = useState(cohort?.cohort_name ?? "");
  const [price, setPrice] = useState(String(cohort?.sale_price ?? ""));
  const [cap, setCap] = useState(String(cohort?.max_student_count ?? ""));
  const [start, setStart] = useState(cohort?.start_date?.slice(0, 10) ?? "");
  const [end, setEnd] = useState(cohort?.end_date?.slice(0, 10) ?? "");

  const submit = () => {
    if (cohort) {
      onSubmit({ head_teacher_id: Number(headTeacher) || undefined, cohort_name: name, sale_price: Number(price) || 0, max_student_count: Number(cap) || 1, start_date: start, end_date: end || undefined });
    } else {
      onSubmit({ institution_id: series.institution_id, series_id: series.id, head_teacher_id: Number(headTeacher), cohort_code: code, cohort_name: name, sale_price: Number(price) || 0, max_student_count: Number(cap) || 1, start_date: start, end_date: end || undefined });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{cohort ? "编辑班次" : "新增班次"}</DialogTitle>
          <DialogDescription>{cohort ? `编辑「${cohort.cohort_name}」` : "创建班次必填 institution_id + head_teacher_id；班次编码创建后不可改"}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FieldRow id="ch-code" label="班次编码" required={!cohort}>
            <Input value={code} onChange={(e) => setCode(e.target.value)} disabled={!!cohort} placeholder="如 COH-2026A" />
          </FieldRow>
          <FieldRow id="ch-name" label="班次名称" required>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 2026 暑期 A 班" />
          </FieldRow>
          <FieldRow id="ch-teacher" label="负责人 head_teacher_id" required={!cohort}>
            <Input type="number" value={headTeacher} onChange={(e) => setHeadTeacher(e.target.value)} />
          </FieldRow>
          <FieldRow id="ch-price" label="售价（元）" hint="冲突报 40902">
            <Input type="number" min={0} value={price} onChange={(e) => setPrice(e.target.value)} />
          </FieldRow>
          <FieldRow id="ch-cap" label="容量 max_student_count">
            <Input type="number" min={1} value={cap} onChange={(e) => setCap(e.target.value)} />
          </FieldRow>
          <FieldRow id="ch-start" label="开课日期"><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></FieldRow>
          <FieldRow id="ch-end" label="结课日期"><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></FieldRow>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={submit} disabled={!name.trim()}>{cohort ? "保存修改" : "创建班次"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ModuleFormDialog({
  cohortId, module, open, onOpenChange, onSubmit,
}: {
  cohortId: number;
  module?: AdminModule;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSubmit: (input: ModuleCreateInput | Partial<ModuleCreateInput>) => void;
}) {
  const [code, setCode] = useState(module?.module_code ?? "");
  const [name, setName] = useState(module?.module_name ?? "");
  const [stage, setStage] = useState(String(module?.stage_no ?? ""));
  const [lessons, setLessons] = useState(String(module?.lesson_count ?? ""));
  const [hours, setHours] = useState(String(module?.total_hours ?? ""));
  const [start, setStart] = useState(module?.start_date?.slice(0, 10) ?? "");
  const [end, setEnd] = useState(module?.end_date?.slice(0, 10) ?? "");

  const submit = () => {
    if (module) {
      onSubmit({ module_name: name, stage_no: Number(stage) || 1, lesson_count: Number(lessons) || 1, total_hours: Number(hours) || 0, start_date: start, end_date: end });
    } else {
      onSubmit({ cohort_id: cohortId, module_code: code, module_name: name, stage_no: Number(stage) || 1, lesson_count: Number(lessons) || 1, total_hours: Number(hours) || 0, start_date: start, end_date: end });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{module ? "编辑模块" : "新增模块"}</DialogTitle>
          <DialogDescription>模块归属 cohort_id #{cohortId}；阶段号 stage_no 需唯一（冲突报 40903）</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FieldRow id="mo-code" label="模块编码" required={!module}><Input value={code} onChange={(e) => setCode(e.target.value)} disabled={!!module} placeholder="如 MOD-01" /></FieldRow>
          <FieldRow id="mo-name" label="模块名称" required><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 Python 基础语法" /></FieldRow>
          <FieldRow id="mo-stage" label="阶段 stage_no"><Input type="number" min={1} value={stage} onChange={(e) => setStage(e.target.value)} /></FieldRow>
          <FieldRow id="mo-lessons" label="课次数 lesson_count"><Input type="number" min={1} value={lessons} onChange={(e) => setLessons(e.target.value)} /></FieldRow>
          <FieldRow id="mo-hours" label="总学时 total_hours"><Input type="number" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} /></FieldRow>
          <FieldRow id="mo-start" label="开始日期"><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></FieldRow>
          <FieldRow id="mo-end" label="结束日期"><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></FieldRow>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={submit} disabled={!name.trim() && !module}>{}&ensp;{module ? "保存修改" : "创建模块"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SessionFormDialog({
  module, session, open, onOpenChange, onSubmit,
}: {
  module?: AdminModule;
  session?: AdminSession;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSubmit: (input: SessionCreateInput | Partial<SessionCreateInput>) => void;
}) {
  const mid = module?.id ?? session?.series_cohort_course_id ?? 0;
  const [no, setNo] = useState(String(session?.session_no ?? ""));
  const [title, setTitle] = useState(session?.session_title ?? "");
  const [status, setStatus] = useState(session?.teaching_status ?? "scheduled");
  const [checkin, setCheckin] = useState(String(session?.checkin_required ?? 0));
  const [date, setDate] = useState(session?.teaching_date?.slice(0, 10) ?? "");
  const [st, setSt] = useState(session?.start_time?.slice(0, 5) ?? "");
  const [et, setEt] = useState(session?.end_time?.slice(0, 5) ?? "");

  const submit = () => {
    const base = { session_title: title, teaching_status: status as SessionCreateInput["teaching_status"], checkin_required: Number(checkin) || 0, teaching_date: date, start_time: st ? `${st}:00` : undefined, end_time: et ? `${et}:00` : undefined };
    if (session) {
      onSubmit({ ...base });
    } else {
      onSubmit({ series_cohort_course_id: mid, session_no: Number(no) || 1, ...base });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{session ? "编辑课次" : "新增课次"}</DialogTitle>
          <DialogDescription>课次归属 series_cohort_course_id（模块物理 ID）#{mid}；课次编号 session_no 需唯一（冲突报 40904）</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FieldRow id="se-no" label="课次序号 session_no" required={!session}><Input type="number" min={1} value={no} onChange={(e) => setNo(e.target.value)} disabled={!!session} /></FieldRow>
          <FieldRow id="se-title" label="课次标题" required><Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="如 第 3 讲 函数入门" /></FieldRow>
          <FieldRow id="se-status" label="教学状态">
            <NativeSelect value={status} onChange={(e) => setStatus(e.target.value as TeachingStatusCode)}>{TECHING_STATUS_OPTIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</NativeSelect>
          </FieldRow>
          <FieldRow id="se-checkin" label="考勤必设 checkin_required">
            <NativeSelect value={checkin} onChange={(e) => setCheckin(e.target.value)}><option value="0">0（无需签到）</option><option value="1">1（必签）</option></NativeSelect>
          </FieldRow>
          <FieldRow id="se-date" label="授课日期"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></FieldRow>
          <FieldRow id="se-start" label="开始时间"><Input type="time" value={st} onChange={(e) => setSt(e.target.value)} /></FieldRow>
          <FieldRow id="se-end" label="结束时间"><Input type="time" value={et} onChange={(e) => setEt(e.target.value)} /></FieldRow>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={submit} disabled={!title.trim() && !session}>{session ? "保存修改" : "创建课次"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ============================================================
 * 删除确认（软删）
 * ============================================================ */
function ConfirmDialog({
  open, onOpenChange, title, description, confirmLabel, onConfirm,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button variant="destructive" onClick={onConfirm}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}