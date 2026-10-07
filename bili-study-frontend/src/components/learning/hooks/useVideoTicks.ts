/**
 * useVideoTicks — 视频学习进度打点
 * 设计：
 *   - 调用方把 <video> 当前时间与总时长定期喂进 recordTick(currentSec, totalSec?)
 *     或直接传 HTMLVideoElement ref（attachVideo）。
 *   - 内部以 sessionId 去重（当前秒数 ≤ 已打点最大秒则跳过），积攒到：
 *       a) 15s 定时 flush
 *       b) buffer 满 30 条
 *       c) visibilitychange=hidden / beforeunload / router 路由切换
 *   - 提交失败：重试 3 次（指数退避），仍失败则塞回 buffer 下次继续。
 */
"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { submitVideoTicks, type VideoTickInput } from "@/lib/api/learning";
import { API_BASE } from "@/lib/api-client";

export interface UseVideoTicksOptions {
  seriesId: number;
  sessionId: number;
  /** 总视频秒数（可在 attachVideo 后由 DOM 补上或 setTotalSeconds 手动改） */
  totalSeconds?: number | null;
  /** 启用/暂停（比如暂停按钮时不记录） */
  enabled?: boolean;
  /** 定时间隔（毫秒），默认 15_000 */
  flushIntervalMs?: number;
  /** 最大缓冲条数，默认 30 */
  maxBufferedTicks?: number;
  /** 成功提交时回调，用于页面内更新「已观看进度」 */
  onFlushed?: (payload: { saved_count: number; watch_ratio_synced?: number | null }) => void;
  /** 错误回调（UI 可以用它弹 toast，但 hook 内部不会自己弹） */
  onError?: (err: unknown) => void;
}

export interface VideoTicksHandle {
  /** 手动记录当前播放时间（0..totalSeconds） */
  recordTick: (currentSeconds: number, totalSecondsOverride?: number | null) => void;
  /** 接入原生 video 元素：监听 timeupdate / play / pause 来自动打点 */
  attachVideo: (el: HTMLVideoElement | null | undefined) => void;
  /** 外部设置总时长（当 attachVideo 失败时使用） */
  setTotalSeconds: (sec: number | null) => void;
  /** 立即把当前 buffer 发到后端 */
  flushNow: () => Promise<void>;
  /** 仅获取：是否有未上报的 tick */
  hasBufferedTicks: () => boolean;
}

export function useVideoTicks(opts: UseVideoTicksOptions): VideoTicksHandle {
  const {
    seriesId,
    sessionId,
    totalSeconds: initialTotal,
    enabled = true,
    flushIntervalMs = 15_000,
    maxBufferedTicks = 30,
    onFlushed,
    onError,
  } = opts;

  const bufferRef = useRef<VideoTickInput[]>([]);
  const lastTickSecRef = useRef<number>(-1);
  const totalRef = useRef<number | null>(initialTotal ?? null);
  const videoElRef = useRef<WeakRef<HTMLVideoElement> | null>(null);
  const flushLockRef = useRef<boolean>(false);
  const playSessionIdRef = useRef<string | null>(null);

  const flush = useCallback(async () => {
    if (flushLockRef.current) return;
    const pending = bufferRef.current.slice();
    if (!pending.length) return;
    flushLockRef.current = true;
    let attempt = 0;
    let delay = 800;
    while (attempt < 3) {
      try {
        const playSessionId = playSessionIdRef.current ??=
          (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
            ? `ps-${seriesId}-${crypto.randomUUID().slice(0, 8)}`
            : `ps-${seriesId}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`);
        const result = await submitVideoTicks(seriesId, pending, { play_session_id: playSessionId });
        // 成功：把已经送出去的部分（如果之前追加了新的，保留尾部）从 buffer 去掉
        bufferRef.current = bufferRef.current.slice(pending.length);
        onFlushed?.(result);
        flushLockRef.current = false;
        return;
      } catch (e) {
        attempt += 1;
        if (attempt < 3) {
          await sleep(delay);
          delay = Math.min(delay * 2, 6400);
          continue;
        }
        onError?.(e);
        // 失败：把这批 tick 放回 buffer 最前，下轮继续
        bufferRef.current = pending.concat(bufferRef.current.slice(pending.length));
        flushLockRef.current = false;
        return;
      }
    }
  }, [seriesId, onFlushed, onError]);

  const enqueueTick = useCallback(
    (currentSec: number, totalOverride?: number | null) => {
      if (!enabled) return;
      const t = Math.max(0, Math.floor(Number(currentSec) || 0));
      if (t <= lastTickSecRef.current) return;
      if (typeof totalOverride === "number" && totalOverride > 0) {
        totalRef.current = totalOverride;
      }
      lastTickSecRef.current = t;
      bufferRef.current.push({
        session_id: sessionId,
        tick_second: t,
        total_seconds: totalRef.current ?? null,
      });
      if (bufferRef.current.length >= maxBufferedTicks) {
        void flush();
      }
    },
    [enabled, sessionId, maxBufferedTicks, flush],
  );

  /* 15s 定时器 */
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => {
      void flush();
    }, flushIntervalMs);
    return () => window.clearInterval(id);
  }, [enabled, flushIntervalMs, flush]);

  /* 页面隐藏 / 关闭：立即 flush */
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onHide = () => {
      if (document.visibilityState === "hidden") void flush();
    };
    const onBeforeUnload = () => {
      /* 不 await，浏览器同步路径里放弃 Promise 等待，但尽量把请求发出去 */
      try {
        // 取个局部快照避免 flush 重入
        const pending = bufferRef.current.slice();
        if (!pending.length) return;
        // 用 navigator.sendBeacon 当兜底（body=JSON 也 OK，但后端要求 Content-Type: application/json，
        // Beacon 会发送 text/plain；这里仍用 XHR 同步方式，兼容性最好）
        const playSessionId = playSessionIdRef.current ??
          `ps-${seriesId}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
        playSessionIdRef.current = playSessionId;
        syncFlushXHR(seriesId, pending, playSessionId);
        bufferRef.current = bufferRef.current.slice(pending.length);
      } catch {
        /* 忽略 */
      }
    };
    document.addEventListener("visibilitychange", onHide);
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => {
      document.removeEventListener("visibilitychange", onHide);
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
  }, [seriesId, flush]);

  /* 切换课次时立刻 flush 一次上一课 */
  useEffect(() => {
    return () => {
      void flush();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const attachVideo = useCallback(
    (el: HTMLVideoElement | null | undefined) => {
      if (!el) return;
      videoElRef.current = new WeakRef(el);
      if (el.duration && Number.isFinite(el.duration)) {
        totalRef.current = el.duration;
      }
      const onTime = () => {
        if (!enabled) return;
        enqueueTick(el.currentTime, el.duration);
      };
      const onMeta = () => {
        if (Number.isFinite(el.duration)) totalRef.current = el.duration;
      };
      el.addEventListener("timeupdate", onTime);
      el.addEventListener("loadedmetadata", onMeta);
      el.addEventListener("durationchange", onMeta);
    },
    [enabled, enqueueTick],
  );

  const setTotalSeconds = useCallback((sec: number | null) => {
    totalRef.current = sec;
  }, []);

  const hasBufferedTicks = useCallback(() => bufferRef.current.length > 0, []);

  return useMemo(
    () => ({
      recordTick: enqueueTick,
      attachVideo,
      setTotalSeconds,
      flushNow: async () => flush(),
      hasBufferedTicks,
    }),
    [enqueueTick, attachVideo, setTotalSeconds, flush, hasBufferedTicks],
  );
}

/* ---------- 辅助：同步 XHR flush，仅用于 beforeunload ---------- */
function syncFlushXHR(seriesId: number, ticks: VideoTickInput[], playSessionId: string) {
  if (typeof XMLHttpRequest === "undefined") return;
  const token = getJWTFromStorage();
  const xhr = new XMLHttpRequest();
  try {
    /*
     * 关键：后端 API 不在 Next.js 同源端口（3000），而在独立的 API_BASE（默认 8000）。
     * 之前写成相对路径 "/api/progress/video/tick-batch" 会把 tick 打到 3000，
     * Next 没有对应的 route handler，直接 404，beforeunload 下静默丢失进度。
     * 这里改走跟 chatStream 一样的 API_BASE（来自 api-client.ts 的环境变量）。
     */
    const url = `${API_BASE}/api/progress/video/tick-batch`;
    xhr.open("POST", url, /* async */ false);
    xhr.setRequestHeader("Content-Type", "application/json");
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.send(JSON.stringify({
      play_session_id: playSessionId,
      series_id: seriesId,
      ticks,
    }));
  } catch {
    /* beforeunload 里不抛错 */
  }
}

function getJWTFromStorage(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const t = window.localStorage.getItem("edu:auth:token");
    if (!t) return null;
    if (t.startsWith('"') && t.endsWith('"')) return t.slice(1, -1);
    return t;
  } catch {
    return null;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms));
}
