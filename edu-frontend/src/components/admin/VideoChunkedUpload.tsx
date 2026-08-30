/**
 * VideoChunkedUpload — 视频分片上传 + 转码状态轮询（task57 关键链路）
 *
 * 契约（domains/course_admin，task12 契约③，端点参数走 query string）：
 *   1. POST /videos/init-chunked     {session_id, file_name, file_size, chunk_count} → {upload_id, chunk_size, upload_urls, strategy}
 *   2. 分片上传（local_fallback 占位：后端不真实收分片 → 前端模拟进度；若 upload_urls 非空可扩展为并发 PUT，本站未启用）
 *   3. POST /videos/finalize-chunked {upload_id} → {upload_id, asset_id, video_id, transcode_status}
 *   4. POST /videos/bind-session      {session_id, video_id, sort_no} → {bound}
 *   5. GET  /videos/{video_id}/transcode-status → {video_id, transcode_status, review_status}（3s 轮询，终态停）
 *
 * 转码徽章 tone：pending→warning / in_progress→primary / completed→success / failed→destructive（transcodeBadgeTone）。
 * 章节管理：schema（session_video_chapter，start_second/end_second）已冻结但路由未注册 → 契约缺口，
 *           UI 脚手架显示起止秒输入 + 新增/保存/删除按钮（disabled），实披露不 MOCK。
 *
 * 失败处理（R-7）：写操作 useMutation onError → 全局 toast；可从失败步骤重试当前步。
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Film, Loader2, UploadCloud, XCircle } from "lucide-react";
import { toast } from "sonner";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  bindSessionVideo,
  finalizeChunkedUpload,
  getTranscodeStatus,
  initChunkedUpload,
  transcodeBadgeTone,
  transcodeStatusLabel,
  reviewBadgeTone,
  reviewStatusLabel,
  formatFileSize,
  fmtSeconds,
  type AdminSession,
} from "@/lib/api/admin/courses";
import { FieldRow } from "@/components/admin/controls";
import { cn } from "@/lib/utils";

export interface VideoChunkedUploadProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 目标课次（上传后绑定到该课次） */
  session: AdminSession;
  /** 绑定成功回调（父级用于展示该课次已绑视频与转码状态） */
  onBound?: (videoId: number) => void;
}

type Stage = "select" | "upload" | "finalize" | "bind" | "poll";

const STEPS: Array<{ key: Stage | "done"; label: string }> = [
  { key: "select", label: "init-chunked" },
  { key: "upload", label: "分片上传" },
  { key: "finalize", label: "finalize" },
  { key: "bind", label: "bind-session" },
  { key: "poll", label: "转码轮询" },
];

const CHUNK_SIZE = 8 * 1024 * 1024; // 8MB / 分片

export function VideoChunkedUpload({ open, onOpenChange, session, onBound }: VideoChunkedUploadProps) {
  const [stage, setStage] = useState<Stage>("select");
  const [fileName, setFileName] = useState("");
  const [fileSize, setFileSize] = useState(0);
  const [progress, setProgress] = useState(0);
  const [videoId, setVideoId] = useState<number | null>(null);
  const [assetId, setAssetId] = useState<number | null>(null);
  const [bound, setBound] = useState(false);
  const uploadIdRef = useRef<string | null>(null);
  const videoIdRef = useRef<number | null>(null);
  const progressTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (progressTimer.current) clearInterval(progressTimer.current); }, []);

  function clearTimer() {
    if (progressTimer.current) { clearInterval(progressTimer.current); progressTimer.current = null; }
  }

  /* ---------- 1. init ---------- */
  const init = useMutation({
    mutationFn: () => {
      const chunkCount = Math.max(1, Math.ceil(fileSize / CHUNK_SIZE));
      return initChunkedUpload(session.id, { file_name: fileName, file_size: fileSize, chunk_count: chunkCount });
    },
    onSuccess: (resp) => {
      uploadIdRef.current = resp.upload_id;
      setStage("upload");
      setProgress(0);
      startSimulated(resp.strategy);
    },
    onError: () => setStage("select"),
  });

  function startSimulated(strategy: string) {
    clearTimer();
    // chunked（upload_urls 非空）可并发 PUT，本站未启用 → 占位式进度；local_fallback 同上
    void strategy;
    progressTimer.current = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearTimer();
          finish.mutate(uploadIdRef.current ?? undefined);
          return 100;
        }
        const delta = prev < 80 ? 7 : 3;
        return Math.min(100, prev + delta);
      });
    }, 150);
  }

  /* ---------- 3. finalize ---------- */
  const finish = useMutation({
    mutationFn: (id?: string) => {
      if (!id) throw new Error("缺少 upload_id，请重新发起上传");
      return finalizeChunkedUpload(id);
    },
    onSuccess: (resp) => {
      clearTimer();
      setProgress(100);
      setVideoId(resp.video_id);
      videoIdRef.current = resp.video_id;
      setAssetId(resp.asset_id);
      setStage("bind");
    },
    onError: () => { clearTimer(); setStage("finalize"); },
  });

  /* ---------- 4. bind ---------- */
  const bind = useMutation({
    mutationFn: () => {
      const vid = videoIdRef.current;
      if (!vid) throw new Error("缺少 video_id");
      return bindSessionVideo(session.id, vid, 0);
    },
    onSuccess: () => {
      setBound(true);
      setStage("poll");
      toast.success("视频已绑定课次");
      onBound?.(videoIdRef.current ?? 0);
    },
  });

  /* ---------- 5. 转码状态轮询（3s，终态停） ---------- */
  const pollEnabled = open && stage === "poll" && videoId != null;
  const transcodeQ = useQuery({
    queryKey: ["admin", "series", "video", videoId, "transcode"] as const,
    queryFn: () => getTranscodeStatus(videoId!),
    enabled: pollEnabled,
    refetchInterval: (query) => {
      const s = query.state.data?.transcode_status;
      if (!s) return false;
      return s === "completed" || s === "failed" ? false : 3000;
    },
  });

  const transcode = transcodeQ.data?.transcode_status ?? (stage === "poll" ? "pending" : undefined);
  const review = transcodeQ.data?.review_status;
  const isTerminal = transcode === "completed" || transcode === "failed";

  function handleStart() {
    if (!fileName.trim()) { toast.warning("请先选择视频文件"); return; }
    init.mutate();
  }
  function handleClose() {
    clearTimer();
    onOpenChange(false);
  }

  const busy = init.isPending || finish.isPending || bind.isPending;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Film className="h-4 w-4 text-primary" />
            视频上传 · {session.session_title}
          </DialogTitle>
          <DialogDescription>init-chunked → 分片上传 → finalize → bind-session → 转码轮询</DialogDescription>
        </DialogHeader>

        <Stepper stage={stage} transcode={transcode} />

        <div className="space-y-4">
          {/* 1. 选文件 */}
          {stage === "select" && (
            <>
              <FieldRow id="video-file" label="视频文件" required hint="支持 .mp4 / .mov；分片默认 8MB，占位式上传不真实接收分片">
                <input
                  ref={fileInputRef}
                  id="video-file"
                  type="file"
                  accept=".mp4,.mov"
                  className="block w-full cursor-pointer rounded-lg border border-input text-sm text-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-primary-soft file:px-3 file:py-2 file:text-sm file:font-medium file:text-primary-soft-foreground hover:file:bg-primary/10"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) { setFileName(f.name); setFileSize(f.size); }
                    else { setFileName(""); setFileSize(0); }
                  }}
                />
              </FieldRow>
              {fileSize > 0 && (
                <p className="text-xs text-muted-foreground">
                  {fileName} · {formatFileSize(fileSize)} · {Math.max(1, Math.ceil(fileSize / CHUNK_SIZE))} 分片
                </p>
              )}
            </>
          )}

          {/* 2. 分片上传中（占位进度） */}
          {stage === "upload" && (
            <div className="rounded-xl border border-primary-border bg-primary-soft/40 p-4">
              <div className="mb-2 flex items-center justify-between text-sm text-primary-strong">
                <span className="inline-flex items-center gap-1.5"><Loader2 className="h-3.5 w-3.5 animate-spin" /> 分片上传中（local_fallback 占位）</span>
                <span className="font-mono text-xs">{progress}%</span>
              </div>
              <Progress value={progress} aria-label="上传进度" />
            </div>
          )}

          {/* 3. finalize */}
          {stage === "finalize" && (
            <div className="rounded-xl border border-primary-border bg-primary-soft/40 p-4 text-sm text-primary-strong">
              <span className="inline-flex items-center gap-1.5"><Loader2 className="h-3.5 w-3.5 animate-spin" /> 正在 finalize（注册资产与视频记录）…</span>
            </div>
          )}

          {/* 4. bind 确认 */}
          {stage === "bind" && (
            <div className="rounded-xl border border-border bg-card p-4 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">资产 asset_id</span>
                <span className="font-mono text-xs text-foreground">#{assetId}</span>
              </div>
              <div className="mt-2 flex items-center justify-between">
                <span className="text-muted-foreground">视频 video_id</span>
                <span className="font-mono text-xs text-foreground">#{videoId}</span>
              </div>
            </div>
          )}

          {/* 5. 转码轮询 + Timeline + 章节 */}
          {stage === "poll" && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm text-muted-foreground">转码状态</span>
                <Badge className={transcodeBadgeTone(transcode ?? "pending")} data-testid="transcode-badge">
                  {transcodeStatusLabel(transcode ?? "pending")}
                </Badge>
                {review && (
                  <Badge className={reviewBadgeTone(review)} data-testid="review-badge">{reviewStatusLabel(review)}</Badge>
                )}
                {!isTerminal && (
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" /> 3s 轮询中（终态停）
                  </span>
                )}
              </div>

              <Timeline bound={bound} terminal={isTerminal} failed={transcode === "failed"} />

              {transcode === "completed" && <ChapterManager disabled videoId={videoId ?? 0} />}
            </>
          )}

          {/* 资产/转码结果网格（completed 简示） */}
          {stage === "poll" && isTerminal && (
            <div className="rounded-xl border border-border bg-muted/30 p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-muted-foreground">video_id</span>
                <code className="font-mono text-xs text-foreground">#{videoId}</code>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="flex-wrap gap-2">
          {stage === "select" && (
            <>
              <Button variant="outline" onClick={handleClose}>取消</Button>
              <Button onClick={handleStart} disabled={init.isPending || !fileName.trim()}>
                {init.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <UploadCloud className="mr-1.5 h-4 w-4" />}
                发起分片上传
              </Button>
            </>
          )}
          {stage === "finalize" && (
            <>
              <Button variant="outline" onClick={() => finish.mutate(uploadIdRef.current ?? undefined)} disabled={finish.isPending}>
                {finish.isPending ? "finalize 中…" : "重试 finalize"}
              </Button>
              <Button variant="outline" onClick={handleClose}>取消</Button>
            </>
          )}
          {stage === "bind" && (
            <>
              <Button variant="outline" onClick={handleClose}>取消</Button>
              <Button onClick={() => bind.mutate()} disabled={bind.isPending}>
                {bind.isPending ? "绑定中…" : "绑定到本课次"}
              </Button>
            </>
          )}
          {stage === "poll" && (
            <Button variant="outline" onClick={handleClose}>关闭</Button>
          )}
          {busy && stage === "upload" && <span className="text-xs text-muted-foreground">请勿关闭弹窗</span>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------- Stepper ---------------- */
function Stepper({ stage, transcode }: { stage: Stage; transcode?: string }) {
  const order: Array<{ key: Stage | "done"; label: string }> = STEPS;
  const idxMap: Record<string, number> = { select: 0, upload: 1, finalize: 2, bind: 3, poll: 4 };
  const currentIdx = idxMap[stage];
  // 轮询终态视为「完成」
  const done = transcode === "completed" || transcode === "failed";
  return (
    <ol className="flex flex-wrap items-center gap-1" aria-label="上传步骤">
      {order.map((s, i) => {
        const reached = i < currentIdx || (i === 4 && (stage === "poll" || done)) || (i < idxMap[stage]);
        const cur = i === currentIdx;
        const failed = transcode === "failed" && i === 4;
        return (
          <li key={s.key} className="flex items-center gap-1" aria-current={cur ? "step" : undefined}>
            {i > 0 && <span className="h-px w-4 bg-muted sm:w-6" />}
            <span
              className={cn(
                "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-medium",
                done || i < currentIdx || (i === 4 && stage === "poll" && done)
                  ? "bg-candy-green text-white"
                  : failed ? "bg-destructive text-destructive-foreground"
                  : cur ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {i === 4 && done ? <CheckCircle2 className="h-3 w-3" /> : i === 4 && failed ? <XCircle className="h-3 w-3" /> : reached ? <CheckCircle2 className="h-3 w-3" /> : i + 1}
            </span>
            <span className={cn("text-xs", (cur || (i === 4 && (done || failed))) ? "text-foreground" : "text-muted-foreground")}>
              {transcode === "failed" && i === 4 ? "失败" : done && i === 4 ? "已完成" : s.label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/* ---------------- Timeline 轨迹 ---------------- */
function Timeline({ bound, terminal, failed }: { bound: boolean; terminal: boolean; failed: boolean }) {
  const items: Array<{ label: string; detail: string; state: "ok" | "cur" }> = [
    { label: "分片上传", detail: "占位式 local_fallback 上传", state: "ok" },
    { label: "finalize", detail: "资产注册 → video_id", state: "ok" },
    { label: "bind-session", detail: bound ? "已绑定到课次" : "待确认", state: bound ? "ok" : "cur" },
    { label: failed ? "转码失败" : terminal ? "转码完成" : "转码中", detail: failed ? "请重新上传或联系运维" : terminal ? "播放就绪，等待审核" : "in_progress 轮询中…", state: failed ? "ok" : terminal ? "ok" : "cur" },
  ];
  return (
    <ol className="ml-1.5 border-l border-border pl-4 text-sm">
      {items.map((it) => (
        <li key={it.label} className="relative py-1.5">
          <span className={cn(
            "absolute -left-[21px] top-2.5 h-2.5 w-2.5 rounded-full border-2",
            it.state === "ok" ? "border-candy-green bg-candy-green" : "border-primary bg-primary",
          )} />
          <span className="font-medium text-foreground">{it.label}</span>
          <span className="ml-2 text-xs text-muted-foreground">{it.detail}</span>
        </li>
      ))}
    </ol>
  );
}

/* ---------------- 章节管理（契约缺口占位：路由未注册，输入禁用） ---------------- */
function ChapterManager({ disabled, videoId }: { disabled: boolean; videoId: number }) {
  // 无真实章节数据源（无 CRUD/列表端点）；脚手架展示 start_second/end_second GUI，button 全部禁用 → 待后端接线
  return (
    <div className="rounded-xl border border-dashed border-border p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-foreground">章节管理（session_video_chapter）</span>
        <Badge className="border-transparent bg-warning/10 text-warning">契约缺口：后端章节端点未注册，保存/新增待接线</Badge>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        章节字段 chapter_no / chapter_title / start_second / end_second（起止秒）已冻结；当前 video #{videoId} 存量章节不可用。
      </p>
      <ChapterRow disabled={disabled} title="开篇 · 环境安装" start={0} end={128} />
      <div className="mt-2 flex items-center justify-end gap-2">
        <Button variant="outline" size="sm" disabled>＋ 新增章节</Button>
        <Button size="sm" disabled>保存章节</Button>
      </div>
    </div>
  );
}

function ChapterRow({ disabled, title, start, end }: { disabled: boolean; title: string; start: number; end: number }) {
  const [s, setS] = React.useState<number>(start);
  const [e, setE] = React.useState<number>(end);
  return (
    <div className="mb-1 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm">
      <span className="font-mono text-xs text-muted-foreground">CH</span>
      <span className="min-w-0 flex-1 text-foreground">{title}</span>
      <span className="inline-flex items-center gap-1.5 text-xs">
        <span className="text-muted-foreground">开始</span>
        <input
          type="number"
          min={0}
          value={s}
          disabled={disabled}
          aria-label="起始秒"
          onChange={(ev) => setS(Number(ev.target.value) || 0)}
          className="w-16 rounded-md border border-input px-2 py-1 text-right text-xs"
        />
        <span className="font-mono text-xs text-muted-foreground">{fmtSeconds(s)}</span>
        <span className="text-muted-foreground">结束</span>
        <input
          type="number"
          min={1}
          value={e}
          disabled={disabled}
          aria-label="结束秒"
          onChange={(ev) => setE(Number(ev.target.value) || 0)}
          className="w-16 rounded-md border border-input px-2 py-1 text-right text-xs"
        />
        <span className="font-mono text-xs text-muted-foreground">{fmtSeconds(e)}</span>
      </span>
      <Button variant="ghost" size="icon" disabled aria-label="删除章节"><XCircle className="h-4 w-4" /></Button>
    </div>
  );
}