/**
 * CandyVideoPlayer — task48 糖果版播放区（STYLE: candy-playful frozen）
 *
 * 对齐 learning.html 播放器：16:9 深色舞台 + 糖果橙播放按钮 + 糖果黄播放进度 + 章节徽标。
 * 打点复用 useVideoTicks（15s flush + 30 条 / visibilitychange / beforeunload 兜底）。
 *
 * 转码占位（GWT④，不白屏）：
 *   - transcodeStatus 'processing'  →「转码中」spinner 覆盖
 *   - 'failed'/'missing'           →「不可播」覆盖（文字作业/考试仍可用）
 *   - 'completed' / 无视频源        → 播放态（无源走模拟推进，进度照常上报）
 *
 * 契约注：session_video.transcode_status 为 task21/23 落地后字段；后端未就绪时缺省
 * 按「有 videoSrc → completed、无 videoSrc → 播放占位」处理，联调后以真实字段为准。
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Pause, Play, Volume2 } from "lucide-react";
import { useVideoTicks } from "@/components/learning/hooks/useVideoTicks";
import { cn } from "@/lib/utils";

export interface VideoChapter {
  /** 章节序（1-based，展示用） */
  no: number;
  title: string;
}

export interface CandyVideoPlayerProps {
  seriesId: number;
  sessionId: number;
  /** 视频源；为空则进入模拟推进态（进度照常打点） */
  videoSrc?: string | null;
  /** 总秒数（可选，<video> loadedmetadata 会覆盖） */
  totalSeconds?: number | null;
  /** 转码状态：processing | failed | missing | completed */
  transcodeStatus?: string | null;
  /** 封面标题（无源时展示） */
  title?: string | null;
  /** 章节列表（session_video_chapter，当前章节高亮） */
  chapters?: VideoChapter[];
  /** 实时进度回调（用于大纲/标签联动） */
  onLiveWatch?: (p: { currentSec: number; totalSec: number | null; ratio: number }) => void;
}

function fmtClock(s: number): string {
  const sec = Math.max(0, Math.floor(s || 0));
  const m = Math.floor(sec / 60);
  const ss = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

export function CandyVideoPlayer({
  seriesId,
  sessionId,
  videoSrc,
  totalSeconds,
  transcodeStatus,
  title,
  chapters,
  onLiveWatch,
}: CandyVideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [currentSec, setCurrentSec] = useState(0);
  const [totalSec, setTotalSec] = useState<number | null>(totalSeconds ?? null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [curChapter, setCurChapter] = useState(1);
  const simRef = useRef<number | null>(null);
  const hasRealVideo = !!videoSrc;

  const ticks = useVideoTicks({
    seriesId,
    sessionId,
    totalSeconds: totalSeconds ?? null,
    enabled: true,
  });

  const tcStatus = (transcodeStatus ?? (hasRealVideo ? "completed" : "standby")) as string;
  const processing = tcStatus === "processing";
  const notPlayable = tcStatus === "failed" || tcStatus === "missing";

  /* 播放进度通知 + 章节联动 */
  const publish = useCallback(
    (sec: number, tsec: number | null) => {
      const ratio = !tsec || tsec <= 0 ? 0 : Math.min(1, sec / tsec);
      onLiveWatch?.({ currentSec: sec, totalSec: tsec, ratio });
      const total = tsec ?? 0;
      if (chapters?.length) {
        const seg = total / chapters.length;
        const idx =
          seg > 0 ? Math.min(chapters.length, 1 + Math.floor(sec / seg)) : 1;
        setCurChapter(idx);
      }
    },
    [chapters, onLiveWatch],
  );

  /* 真实视频：attach + 事件同步 */
  useEffect(() => {
    if (!hasRealVideo || processing || notPlayable) return;
    const el = videoRef.current;
    if (!el) return;
    ticks.attachVideo(el);
    const onTime = () => {
      setCurrentSec(el.currentTime);
      if (Number.isFinite(el.duration)) {
        setTotalSec(el.duration);
        ticks.setTotalSeconds(el.duration);
      }
      publish(el.currentTime, Number.isFinite(el.duration) ? el.duration : totalSec);
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
  }, [hasRealVideo, processing, notPlayable, ticks, totalSec, publish]);

  /* 主播放/暂停 */
  const togglePlay = useCallback(() => {
    if (processing || notPlayable) return;
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
    // 无源模拟：每秒 +1s，进度照常打点
    if (isPlaying) {
      if (simRef.current != null) {
        clearInterval(simRef.current);
        simRef.current = null;
      }
      setIsPlaying(false);
      return;
    }
    simRef.current = window.setInterval(() => {
      setCurrentSec((s) => {
        const tsec = totalSec ?? null;
        const next = tsec != null && tsec > 0 ? Math.min(tsec, s + 1) : s + 1;
        ticks.recordTick(next, tsec);
        publish(next, tsec);
        if (tsec != null && next >= tsec) {
          if (simRef.current != null) clearInterval(simRef.current);
          setIsPlaying(false);
        }
        return next;
      });
    }, 1000);
    setIsPlaying(true);
  }, [hasRealVideo, processing, notPlayable, isPlaying, totalSec, ticks, publish]);

  /* 清理模拟 interval */
  useEffect(
    () => () => {
      if (simRef.current != null) clearInterval(simRef.current);
    },
    [],
  );

  const ratio = !totalSec || totalSec <= 0 ? 0 : Math.min(1, currentSec / totalSec);
  const chapter =
    chapters?.find((c) => c.no === curChapter) ??
    chapters?.find((c) => c.no === Math.min(curChapter, chapters.length)) ??
    null;

  return (
    <div className="overflow-hidden rounded-[1.75rem] border-[3px] border-foreground bg-foreground shadow-[0_5px_0_rgba(31,31,31,0.14)]">
      {/* ===== 16:9 舞台 ===== */}
      <div className="relative aspect-video w-full bg-black">
        {/* 章节徽标 */}
        {!processing && !notPlayable && (
          <span
            className="absolute left-3 top-3 z-[2] inline-flex items-center gap-2 rounded-full border-2 border-white/40 bg-black/55 px-3 py-1 text-xs font-bold text-white backdrop-blur-sm"
            aria-hidden="true"
          >
            {(chapter?.no ?? curChapter) < 10 ? `0${chapter?.no ?? curChapter}` : chapter?.no} /{" "}
            {chapters ? String(chapters.length).padStart(2, "0") : "--"}
            <span className="text-candy-yellow">
              {chapter?.title ?? (hasRealVideo ? "播放中" : "学习指南")}
            </span>
          </span>
        )}

        {/* 真实视频 */}
        {hasRealVideo && !processing && !notPlayable ? (
          <video
            ref={videoRef}
            className="h-full w-full"
            controls
            playsInline
            preload="metadata"
            src={videoSrc ?? undefined}
          >
            你的浏览器不支持 HTML5 video 标签。
          </video>
        ) : (
          <>
            {/* 垫底渐变（不依赖网络图，防白屏） */}
            <div
              className="absolute inset-0 bg-gradient-to-br from-black via-neutral-800 to-neutral-600"
              aria-hidden="true"
            />
            <div className="absolute inset-0 bg-black/40" aria-hidden="true" />

            {/* 转码占位 / 不可播（GWT④，不白屏） */}
            {(processing || notPlayable) && (
              <div
                role="status"
                aria-live="polite"
                className="absolute inset-0 z-[3] flex flex-col items-center justify-center gap-3 bg-black/80 px-6 text-center text-white backdrop-blur-md"
              >
                <div
                  className={cn(
                    "grid h-16 w-16 place-items-center rounded-2xl text-3xl",
                    processing ? "bg-candy-purple-soft" : "bg-candy-orange-soft",
                  )}
                >
                  {processing ? "🎬" : "📵"}
                </div>
                <p className="text-lg font-extrabold">
                  {processing ? "转码中，请稍候" : "暂不可播"}
                </p>
                <p className="max-w-xs text-xs leading-relaxed text-white/80">
                  {processing
                    ? "高清版正在生成，预计 1~3 分钟完成。可先学习大纲中的其它课时或下方的文字作业。"
                    : "该课次视频处理失败或已下架，请联系助教。下方文字作业与考试仍可正常进行。"}
                </p>
                {processing && (
                  <Loader2 className="h-5 w-5 animate-spin text-white" aria-hidden="true" />
                )}
              </div>
            )}
          </>
        )}

        {/* 播放按钮（无源模拟态） */}
        {!hasRealVideo && !processing && !notPlayable && (
          <button
            type="button"
            onClick={togglePlay}
            aria-label={isPlaying ? "暂停" : "播放"}
            className={cn(
              "relative z-[2] grid h-20 w-20 place-items-center rounded-full border-[3px] border-white bg-candy-orange text-white shadow-[0_6px_0_rgba(199,64,0,0.9),0_0_0_6px_rgba(255,255,255,0.18)] transition-transform hover:scale-105 active:scale-95",
            )}
          >
            {isPlaying ? (
              <Pause className="ml-0 h-7 w-7 fill-current" />
            ) : (
              <Play className="ml-1 h-7 w-7 fill-current" />
            )}
          </button>
        )}

        {/* 控制条（深色底部，糖果黄进度） */}
        {!processing && !notPlayable && (
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-4 pb-2.5 pt-6 text-white">
            <div
              className="relative h-4 overflow-hidden rounded-full bg-white/25"
              role="progressbar"
              aria-label="视频观看进度"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(ratio * 100)}
            >
              <div className="absolute inset-y-0 left-0 w-[62%] bg-white/40" aria-hidden="true" />
              <div
                className="absolute inset-y-0 left-0 bg-candy-yellow"
                style={{ width: `${ratio * 100}%` }}
                aria-hidden="true"
              />
              <div
                className="absolute top-[-3px] h-[22px] w-[22px] rounded-full border-[3px] border-foreground bg-white shadow-[0_2px_0_rgba(0,0,0,0.3)]"
                style={{ left: `calc(${ratio * 100}% - 11px)` }}
                aria-hidden="true"
              />
            </div>
            <div className="mt-1.5 flex items-center gap-3 text-xs font-bold tabular-nums">
              <span className="shrink-0">
                {fmtClock(currentSec)} / {totalSec != null ? fmtClock(totalSec) : "--:--"}
              </span>
              {hasRealVideo ? (
                <span className="rounded bg-white/20 px-2 py-0.5 text-3xs">1.0×</span>
              ) : (
                <span className="rounded bg-white/20 px-2 py-0.5 text-3xs">模拟 · 正在打点</span>
              )}
              <span className="ml-auto inline-flex items-center gap-2 text-white/70">
                {ticks.hasBufferedTicks() ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    打点同步中…
                  </>
                ) : (
                  <>
                    <Volume2 className="h-3.5 w-3.5" />
                    15s 打点学习中
                  </>
                )}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ===== 播放下方信息行 + 判定标签 ===== */}
      <div className="bg-white px-5 py-4">
        {title && <h2 className="mb-2 text-lg font-extrabold leading-snug">{title}</h2>}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <span className="inline-flex items-center gap-2 text-xs font-extrabold text-success-foreground">
            <span className="h-2 w-2 animate-pulse rounded-full bg-candy-green" aria-hidden="true" />
            15s 打点学习中
          </span>
          <span className="text-xs text-muted-foreground">
            已观看 {fmtClock(currentSec)}
            {totalSec != null ? ` / ${Math.round(ratio * 100)}%` : ""}
          </span>
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-full border-2 border-candy-green/40 bg-candy-green-soft px-3 py-1 text-xs font-extrabold text-success-foreground">
            🎉 判定：观看 ≥90% 或作业提交
          </span>
        </div>
      </div>
    </div>
  );
}