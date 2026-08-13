/**
 * VideoPlayer — 播放页主视频容器
 * 逻辑：
 *   - 优先使用传入的 src（真实 mp4/m3u8 URL），<video controls />
 *   - 无 src 时渲染「封面占位 + 进度模拟条」：点击 Play 推进进度百分比，配合 useVideoTicks.recordTick()
 *   - 两种模式都挂载 useVideoTicks（attachVideo 或手动打点）
 *
 * onProgressUpdate 回调用于同步侧边栏「视频观看 xx%」等实时展示。
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Loader2,
  Pause,
  Play,
  Volume2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { useVideoTicks } from "./hooks/useVideoTicks";
import { cn } from "@/lib/utils";
import { SUBJECT_OPTIONS, type SubjectCode } from "@/lib/api/curriculum";

export interface VideoPlayerProps {
  seriesId: number;
  sessionId: number;
  /** 视频源，可缺省（进入封面占位模式） */
  videoSrc?: string | null;
  /** 视频封面（可缺省，内部 fallback 学科渐变封面） */
  posterSrc?: string | null;
  /** 课程学科（决定占位封面颜色） */
  subjectCode?: SubjectCode | string | null;
  /** 标题 */
  title?: string | null;
  /** 预期总秒数（可选，<video> loadedmetadata 会覆盖它） */
  expectedSeconds?: number | null;
  /** 实时观看进度回调 */
  onProgressUpdate?: (payload: {
    currentSec: number;
    totalSec: number | null;
    ratio: number;
    syncedRatio?: number | null;
  }) => void;
  onError?: (err: unknown) => void;
}

export function VideoPlayer({
  seriesId,
  sessionId,
  videoSrc,
  posterSrc,
  subjectCode,
  title,
  expectedSeconds,
  onProgressUpdate,
  onError,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [currentSec, setCurrentSec] = useState<number>(0);
  const [totalSec, setTotalSec] = useState<number | null>(expectedSeconds ?? null);
  const [syncedRatio, setSyncedRatio] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [hasRealVideo] = useState<boolean>(!!videoSrc);

  const ticks = useVideoTicks({
    seriesId,
    sessionId,
    totalSeconds: expectedSeconds ?? null,
    enabled: true,
    onFlushed: (r) => {
      if (typeof r.watch_ratio_synced === "number") setSyncedRatio(r.watch_ratio_synced);
    },
    onError,
  });

  /* 真实视频模式：自动 attach + 同步 currentSec/totalSec 到本地 state（用于滑块展示） */
  useEffect(() => {
    if (!hasRealVideo) return;
    const el = videoRef.current;
    if (!el) return;
    ticks.attachVideo(el);
    const onTime = () => {
      setCurrentSec(el.currentTime);
      if (Number.isFinite(el.duration)) setTotalSec(el.duration);
      onProgressUpdate?.({
        currentSec: el.currentTime,
        totalSec: Number.isFinite(el.duration) ? el.duration : totalSec,
        ratio: calcRatio(el.currentTime, Number.isFinite(el.duration) ? el.duration : totalSec),
        syncedRatio,
      });
    };
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onMeta = () => {
      if (Number.isFinite(el.duration)) {
        setTotalSec(el.duration);
        ticks.setTotalSeconds(el.duration);
      }
    };
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("durationchange", onMeta);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("durationchange", onMeta);
    };
  }, [hasRealVideo, ticks, onProgressUpdate, syncedRatio, totalSec]);

  /* 播放条（模拟 or 真实） */
  const ratio = calcRatio(currentSec, totalSec);
  const displayRatio =
    typeof syncedRatio === "number" && syncedRatio > ratio ? syncedRatio : ratio;

  /* 无 src 模式下：Play 按钮驱动 +5s 推进 */
  const handlePlayClick = useCallback(() => {
    if (hasRealVideo) {
      const el = videoRef.current;
      if (!el) return;
      if (el.paused) void el.play().then(() => setIsPlaying(true)).catch(() => setIsPlaying(false));
      else {
        el.pause();
        setIsPlaying(false);
      }
      return;
    }
    // 模拟模式：每秒 +1s
    setIsPlaying((prevPlaying) => {
      if (prevPlaying) return false;
      if (totalSec && currentSec >= totalSec) return false;
      // 起一个 interval 推进
      let ticks_handle = window.setInterval(() => {
        setCurrentSec((s) => {
          const next = Math.min(totalSec ?? s + 5, s + 1);
          ticks.recordTick(next, totalSec ?? null);
          onProgressUpdate?.({
            currentSec: next,
            totalSec,
            ratio: calcRatio(next, totalSec),
            syncedRatio,
          });
          if (totalSec && next >= totalSec) {
            window.clearInterval(ticks_handle);
            setIsPlaying(false);
          }
          return next;
        });
      }, 1000);
      // 暴露给下一次 pause 用：用一个全局 ref 不方便，改用 cleanup on unmount，这里简单处理
      (window as any).__edu_video_sim_interval__ = ticks_handle;
      return true;
    });
  }, [hasRealVideo, currentSec, totalSec, ticks, onProgressUpdate, syncedRatio]);

  /* 模拟模式 cleanup */
  useEffect(() => {
    return () => {
      if (!(window as any).__edu_video_sim_interval__) return;
      window.clearInterval((window as any).__edu_video_sim_interval__);
      (window as any).__edu_video_sim_interval__ = null;
    };
  }, []);

  const onSeek = (value: number | readonly number[]) => {
    const val = Array.isArray(value) ? value : [value as number];
    const next = val[0];
    setCurrentSec(next);
    if (hasRealVideo && videoRef.current) {
      videoRef.current.currentTime = next;
    } else {
      ticks.recordTick(next, totalSec ?? null);
      onProgressUpdate?.({
        currentSec: next,
        totalSec,
        ratio: calcRatio(next, totalSec),
        syncedRatio,
      });
    }
  };

  const subject = SUBJECT_OPTIONS.find((s) => s.code === subjectCode);

  return (
    <div className="overflow-hidden rounded-xl border border-foreground/20 bg-foreground shadow-card">
      {/* 视频 / 占位 */}
      <div className="relative aspect-video w-full bg-foreground">
        {hasRealVideo ? (
          <video
            ref={videoRef}
            className="h-full w-full"
            controls
            playsInline
            preload="metadata"
            poster={posterSrc ?? undefined}
            src={videoSrc ?? undefined}
          >
            你的浏览器不支持 HTML5 video 标签。
          </video>
        ) : (
          <div
            className={
              "absolute inset-0 flex flex-col items-center justify-center text-white " +
              (posterSrc
                ? "bg-cover bg-center"
                : "bg-gradient-to-br " + placeholderGradient(subjectCode as SubjectCode))
            }
            style={posterSrc ? { backgroundImage: `url(${posterSrc})` } : undefined}
          >
            <div className="absolute inset-0 bg-black/45" />
            <div className="relative z-10 flex flex-col items-center gap-4 px-6 text-center">
              <Badge className="bg-white/20 backdrop-blur text-white">
                {subject?.name ?? "课程"} · 学习视频
              </Badge>
              {title && (
                <h2 className="max-w-2xl text-2xl font-bold tracking-tight drop-shadow-sm">
                  {title}
                </h2>
              )}
              <p className="max-w-xl text-sm text-white/80">
                视频源待后端对接。当前提供模拟播放器，进度会被 watch-tick 记录并回传到
                P3 的 progress/video/tick-batch 接口。
              </p>
              <button
                type="button"
                onClick={handlePlayClick}
                className="grid h-16 w-16 place-items-center rounded-full bg-white/95 text-foreground shadow-lg transition-transform hover:scale-105"
                aria-label={isPlaying ? "暂停" : "播放"}
              >
                {isPlaying ? (
                  <Pause className="h-7 w-7 fill-current" />
                ) : (
                  <Play className="ml-1 h-7 w-7 fill-current" />
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 控制条：播放按钮 + 进度条 + 时间 + 音视频说明（深色视频容器，foreground 系） */}
      <div className="flex flex-col gap-3 bg-foreground p-4 text-white">
        <div className="flex items-center gap-3">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-9 w-9 text-white hover:bg-white/10"
            onClick={handlePlayClick}
            aria-label={isPlaying ? "暂停" : "播放"}
          >
            {isPlaying ? (
              <Pause className="h-4 w-4 fill-current" />
            ) : (
              <Play className="ml-0.5 h-4 w-4 fill-current" />
            )}
          </Button>
          <div className="flex-1">
            <Slider
              disabled={hasRealVideo}
              value={[Math.round(currentSec)]}
              max={Math.max(0, Math.round(totalSec ?? 300))}
              step={1}
              onValueChange={onSeek}
              className={"!py-3.5 [&_[role=slider]]:h-4 [&_[role=slider]]:w-4 " +
                (hasRealVideo ? "opacity-40" : "")}
            />
            {/* 已观看叠加条（fe-task07：进度条渐变 → 纯色 bg-primary） */}
            <div className="-mt-3.5 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${Math.min(100, displayRatio * 100)}%` }}
              />
            </div>
          </div>
          <div className="min-w-[120px] text-right font-mono text-xs text-white/80">
            {fmtClock(currentSec)} / {totalSec ? fmtClock(totalSec) : "--:--"}
          </div>
          <Volume2 className="hidden h-4 w-4 text-white/60 sm:block" />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-white/70">
          {/* fe-task07：Legend 数据分类多色 → 主色系透明度 + 文字区分 */}
          <div className="flex flex-wrap items-center gap-3">
            <LegendDot color="bg-primary" label="当前观看进度" />
            {typeof syncedRatio === "number" && syncedRatio > 0 && (
              <LegendDot color="bg-primary/60" label={`后端已同步 ${(syncedRatio * 100).toFixed(0)}%`} />
            )}
            {hasRealVideo ? (
              <LegendDot color="bg-success/80" label="HTML5 源视频" />
            ) : (
              <LegendDot color="bg-warning/80" label="模拟进度（打点正常上报）" />
            )}
          </div>
          {ticks.hasBufferedTicks() ? (
            <span className="inline-flex items-center gap-1 text-warning-foreground">
              <Loader2 className="h-3 w-3 animate-spin" />
              打点同步中…
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-success-foreground">
              <AlertCircle className="h-3 w-3" />
              本地进度已落盘
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function calcRatio(cur: number, total: number | null): number {
  if (!total || !Number.isFinite(total) || total <= 0) return 0;
  return Math.max(0, Math.min(1, cur / total));
}
function fmtClock(s: number): string {
  const sec = Math.max(0, Math.floor(s || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const ss = sec % 60;
  const pad = (x: number) => String(x).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(ss)}` : `${pad(m)}:${pad(ss)}`;
}
function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("inline-block h-2 w-2 rounded-full", color)} />
      {label}
    </span>
  );
}
function placeholderGradient(code?: SubjectCode | string | null): string {
  // fe-task07：学科 placeholder 渐变 → 主色渐变（学科靠课程名 + 标签补偿）
  void code;
  return "from-primary-deep to-primary";
}
