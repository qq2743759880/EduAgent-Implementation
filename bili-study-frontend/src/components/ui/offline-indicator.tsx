"use client";

/**
 * OfflineIndicator — 离线状态提示（Phase 4 用户体验）
 *
 * 面试考点：
 * - 监听 navigator.onLine + online/offline 事件
 * - PWA 离线可用时显示"离线模式"而非"无法连接"
 * - 非侵入式设计：顶部横幅 + 自动消失，不打断用户操作
 */
import { useEffect, useState } from "react";

export function OfflineIndicator() {
  const [isOffline, setIsOffline] = useState(false);
  const [wasOffline, setWasOffline] = useState(false);

  useEffect(() => {
    const handleOnline = () => {
      setIsOffline(false);
      // 恢复在线时显示 3 秒提示后自动消失
      if (wasOffline) {
        setTimeout(() => setWasOffline(false), 3000);
      }
    };
    const handleOffline = () => {
      setIsOffline(true);
      setWasOffline(true);
    };

    // 初始化状态
    if (typeof navigator !== "undefined") {
      setIsOffline(!navigator.onLine);
    }

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [wasOffline]);

  if (!isOffline && !wasOffline) return null;

  return (
    <div
      className={`fixed top-0 left-0 right-0 z-[100] transition-all duration-300 ${
        isOffline
          ? "translate-y-0 bg-red-600"
          : wasOffline
            ? "translate-y-0 bg-green-600"
            : "-translate-y-full"
      }`}
    >
      <div className="flex items-center justify-center gap-2 px-4 py-2 text-sm text-white">
        {isOffline ? (
          <>
            <span className="inline-block h-2 w-2 rounded-full bg-red-300 animate-pulse" />
            <span>网络连接已断开，部分功能不可用</span>
          </>
        ) : (
          <>
            <span className="inline-block h-2 w-2 rounded-full bg-green-300" />
            <span>网络已恢复</span>
          </>
        )}
      </div>
    </div>
  );
}