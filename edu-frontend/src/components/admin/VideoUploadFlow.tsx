/**
 * VideoUploadFlow — 视频上传四步流（task03 关键链路）
 *
 * 后端「占位式上传」契约（app/admin/course_admin/service.py）：
 *   1. POST /videos/upload/init     {origin_file_name, file_size, duration_seconds?, bind_session_id?}
 *      → {asset_id, upload_url, form_fields, transcode_status_tip, expires_at}
 *   2. （占位模式无真实分片）→ 前端本地模拟进度条（1s ~ 100%）
 *   3. POST /videos/upload/finalize {asset_id, ...} → VideoAsset（transcode_status: pending→ready + 播放地址）
 *   4. POST /videos/bind-session    {asset_id, session_id} → VideoAsset（同步写 curriculum_session.video_url）
 *
 * 失败处理（R-7）：写操作 useMutation + 全局 MutationCache onError → toast + console.error。
 * 步骤失败后允许「重新尝试当前步骤」（不重置已获取的 asset_id）。
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Film, Loader2, UploadCloud } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  bindVideoToSession,
  finalizeVideoUpload,
  initVideoUpload,
  type AdminSession,
  type AdminVideoAsset,
} from "@/lib/api/admin/courses";
import { FieldRow } from "@/components/admin/controls";
import { cn } from "@/lib/utils";

export interface VideoUploadFlowProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 目标课次（上传成功后绑定到该课次） */
  session: AdminSession;
  onBound?: (asset: AdminVideoAsset) => void;
}

type Step = "init" | "upload" | "finalize" | "bind" | "done";

const STEP_LABELS: Record<Step, string> = {
  init: "发起上传",
  upload: "上传中",
  finalize: "转码处理",
  bind: "绑定课次",
  done: "完成",
};

export function VideoUploadFlow({ open, onOpenChange, session, onBound }: VideoUploadFlowProps) {
  // key 切换触发重挂载：每次弹窗打开（open→true）重置整个流程状态
  return (
    <VideoUploadFlowBody
      key={open ? `open-${session.id}` : "closed"}
      open={open}
      onOpenChange={onOpenChange}
      session={session}
      onBound={onBound}
    />
  );
}

function VideoUploadFlowBody({
  open,
  onOpenChange,
  session,
  onBound,
}: VideoUploadFlowProps) {
  const [fileName, setFileName] = useState("");
  const [fileSize, setFileSize] = useState(0);
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [step, setStep] = useState<Step>("init");
  const [progress, setProgress] = useState(0);
  const [assetId, setAssetId] = useState<string | null>(null);
  const assetIdRef = useRef<string | null>(null);
  const [asset, setAsset] = useState<AdminVideoAsset | null>(null);
  const progressTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // 卸载/关闭时清理模拟进度定时器（仅 cleanup，不 setState，避免级联渲染）
  useEffect(() => {
    return () => {
      if (progressTimer.current) {
        clearInterval(progressTimer.current);
        progressTimer.current = null;
      }
    };
  }, []);

  function clearProgressTimer() {
    if (progressTimer.current) {
      clearInterval(progressTimer.current);
      progressTimer.current = null;
    }
  }

  /* ---------- Step1: Init ---------- */
  const initMutation = useMutation({
    mutationFn: async () => {
      const resp = await initVideoUpload({
        origin_file_name: fileName.trim(),
        file_size: fileSize,
        duration_seconds: durationSeconds,
        asset_title: `${session.session_title} - ${fileName.trim()}`,
        bind_session_id: session.id,
      });
      return resp;
    },
    onSuccess: (resp) => {
      setAssetId(resp.asset_id);
      assetIdRef.current = resp.asset_id;
      setStep("upload");
      setProgress(0);
      startSimulatedProgress();
    },
    onError: () => {
      // 全局 MutationCache onError 已 toast；保持在 init 步可重试
      setStep("init");
    },
  });

  function startSimulatedProgress() {
    clearProgressTimer();
    progressTimer.current = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          clearProgressTimer();
          // 模拟上传完成 → 进入 Finalize（assetId 从 ref 读，避免闭包陈旧值）
          finalizeMutation.mutate(assetIdRef.current ?? undefined);
          return 100;
        }
        // 前 90% 较快，后 10% 放慢，模拟分片上传
        const delta = prev < 80 ? 8 : 3;
        return Math.min(100, prev + delta);
      });
    }, 150);
  }

  /* ---------- Step3: Finalize ---------- */
  const finalizeMutation = useMutation({
    mutationFn: async (id?: string) => {
      if (!id) throw new Error("缺少 asset_id，请重新发起上传");
      return finalizeVideoUpload({ asset_id: id });
    },
    onSuccess: (video) => {
      clearProgressTimer();
      setProgress(100);
      setAsset(video);
      if (video.transcode_status === "ready") {
        setStep("bind");
      } else {
        setStep("finalize");
        toast.error(video.transcode_message || `转码失败（${video.transcode_status}）`);
      }
    },
    onError: () => {
      clearProgressTimer();
      setStep("finalize");
    },
  });

  /* ---------- Step4: Bind ---------- */
  const bindMutation = useMutation({
    mutationFn: async () => {
      if (!assetId) throw new Error("缺少 asset_id");
      return bindVideoToSession(assetId, session.id);
    },
    onSuccess: (video) => {
      setAsset(video);
      setStep("done");
      toast.success("视频已绑定课次，播放地址已同步");
      onBound?.(video);
    },
    // onError → 全局 toast，留在 bind 步可重试
  });

  function handleStart() {
    if (!fileName.trim()) {
      toast.warning("请先填写视频文件名");
      return;
    }
    initMutation.mutate();
  }

  function handleClose() {
    clearProgressTimer();
    onOpenChange(false);
  }

  const busy =
    initMutation.isPending || finalizeMutation.isPending || bindMutation.isPending || step === "upload";

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Film className="h-4 w-4 text-indigo-600" />
            上传视频 · {session.session_title}
          </DialogTitle>
        </DialogHeader>

        {/* 步骤条 */}
        <Stepper current={step} />

        <div className="space-y-4">
          {step === "init" && (
            <>
              <FieldRow id="video-file-name" label="视频文件名" required hint="占位式上传：后端不真实接收分片，直接发起即可">
                <Input
                  value={fileName}
                  onChange={(e) => setFileName(e.target.value)}
                  placeholder="如：lesson-01-intro.mp4"
                />
              </FieldRow>
              <div className="grid grid-cols-2 gap-3">
                <FieldRow id="video-file-size" label="文件大小（字节）">
                  <Input
                    type="number"
                    min={0}
                    value={fileSize || ""}
                    onChange={(e) => setFileSize(Number(e.target.value) || 0)}
                    placeholder="0"
                  />
                </FieldRow>
                <FieldRow id="video-duration" label="时长（秒）">
                  <Input
                    type="number"
                    min={0}
                    value={durationSeconds || ""}
                    onChange={(e) => setDurationSeconds(Number(e.target.value) || 0)}
                    placeholder="0"
                  />
                </FieldRow>
              </div>
            </>
          )}

          {step === "upload" && (
            <UploadingBlock label="模拟上传中（占位模式无真实分片）" percent={progress} />
          )}

          {step === "finalize" && !asset?.transcode_status && (
            <UploadingBlock label="等待转码结果…" percent={100} />
          )}

          {asset && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">资产 ID</span>
                <code className="font-mono text-xs">{asset.asset_id}</code>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500">转码状态</span>
                <StatusBadge status={asset.transcode_status} />
              </div>
              {asset.play_720_url && (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-500 shrink-0">720P 播放地址</span>
                  <code className="min-w-0 truncate font-mono text-[11px] text-slate-700" title={asset.play_720_url}>
                    {asset.play_720_url}
                  </code>
                </div>
              )}
              {asset.play_1080_url && (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-500 shrink-0">1080P 播放地址</span>
                  <code className="min-w-0 truncate font-mono text-[11px] text-slate-700" title={asset.play_1080_url}>
                    {asset.play_1080_url}
                  </code>
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          {step === "init" && (
            <>
              <Button variant="outline" onClick={handleClose}>取消</Button>
              <Button onClick={handleStart} disabled={initMutation.isPending}>
                {initMutation.isPending ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <UploadCloud className="mr-1 h-4 w-4" />
                )}
                发起上传
              </Button>
            </>
          )}

          {step === "finalize" && (
            <Button
              variant="outline"
              onClick={() => finalizeMutation.mutate(assetIdRef.current ?? undefined)}
              disabled={finalizeMutation.isPending}
            >
              {finalizeMutation.isPending ? "转码中…" : "重试转码"}
            </Button>
          )}

          {step === "bind" && (
            <Button onClick={() => bindMutation.mutate()} disabled={bindMutation.isPending}>
              {bindMutation.isPending ? "绑定中…" : "绑定到本课次"}
            </Button>
          )}

          {step === "done" && (
            <Button onClick={handleClose} className="gap-1.5">
              <CheckCircle2 className="h-4 w-4" /> 完成
            </Button>
          )}

          {busy && step === "upload" && (
            <span className="text-[12px] text-slate-500">请勿关闭弹窗</span>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ---------------- 子组件 ---------------- */

function Stepper({ current }: { current: Step }) {
  const order: Step[] = ["init", "upload", "finalize", "bind", "done"];
  const currentIdx = order.indexOf(current);
  return (
    <ol className="flex items-center gap-1" aria-label="上传步骤">
      {order.map((s, i) => {
        const reached = i <= currentIdx;
        return (
          <li key={s} className="flex flex-1 items-center gap-1" aria-current={i === currentIdx ? "step" : undefined}>
            <span
              className={cn(
                "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-medium",
                reached ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-600",
              )}
            >
              {reached ? <CheckCircle2 className="h-3 w-3" /> : i + 1}
            </span>
            <span className={cn("text-[11px]", reached ? "text-indigo-700" : "text-slate-500")}>
              {STEP_LABELS[s]}
            </span>
            {i < order.length - 1 && <span className="h-px flex-1 bg-slate-200" />}
          </li>
        );
      })}
    </ol>
  );
}

function UploadingBlock({ label, percent }: { label: string; percent: number }) {
  return (
    <div className="space-y-2 rounded-xl border border-indigo-100 bg-indigo-50/50 p-4">
      <div className="flex items-center justify-between text-[13px] text-indigo-700">
        <span className="inline-flex items-center gap-1.5">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> {label}
        </span>
        <span className="font-mono text-xs">{percent}%</span>
      </div>
      <Progress value={percent} aria-label="上传进度" />
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    pending: { label: "转码中", cls: "bg-amber-50 text-amber-700" },
    ready: { label: "已就绪", cls: "bg-emerald-50 text-emerald-700" },
    failed: { label: "失败", cls: "bg-rose-50 text-rose-700" },
  };
  const s = map[status] ?? { label: status, cls: "bg-slate-100 text-slate-600" };
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", s.cls)}>{s.label}</span>
  );
}
