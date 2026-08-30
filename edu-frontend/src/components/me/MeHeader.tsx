/**
 * 个人中心头卡（task54 me）：头像渐变圆 + 昵称/编辑资料 + 学习目标 + 学科偏好标签。
 * 数据源：GET /api/users/me（MeHead，agent 合并视图）；错误走 ErrorState（R-7），绝不空兜底。
 */
"use client";
import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { getMe } from "@/lib/api/me";
import { ErrorState } from "@/components/ui/error-state";

export function MeHeader() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["me", "head"] as const,
    queryFn: getMe,
    staleTime: 60_000,
  });

  if (isLoading && !data) return <MeHeaderSkeleton />;
  if (isError && !data) {
    return (
      <ErrorState
        title="个人资料加载失败"
        message="网络开小差了，请稍后重试。"
        retry={refetch}
        retryLabel="重试"
      />
    );
  }
  if (!data) return null;

  const avatarUrl = data.avatar?.trim() || null;
  return (
    <div className="flex items-center gap-4 rounded-2xl border-[3px] border-foreground bg-white p-5 shadow-[0_4px_0_rgba(31,31,31,0.14)]">
      {avatarUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={avatarUrl}
          alt={`${data.nickname} 的头像`}
          className="h-20 w-20 shrink-0 rounded-full border-[3px] border-foreground object-cover"
        />
      ) : (
        <div
          aria-hidden="true"
          className="grid h-20 w-20 shrink-0 place-items-center rounded-full border-[3px] border-foreground bg-gradient-to-br from-candy-purple via-candy-blue to-candy-green text-3xl font-black text-white"
        >
          {data.nickname?.charAt(0)?.toUpperCase() ?? "🐻"}
        </div>
      )}

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-black tracking-tight text-foreground">{data.nickname}</h1>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-full border-[2px] border-foreground bg-candy-purple px-3 py-1 text-xs font-extrabold text-white shadow-[0_2px_0_rgba(31,31,31,0.25)]"
          >
            ✏️ 编辑资料
          </button>
        </div>
        {data.learningGoal ? (
          <div className="mt-2 text-sm font-semibold text-muted-foreground">
            学习目标：<b className="text-foreground">{data.learningGoal}</b>
          </div>
        ) : null}
        {Array.isArray(data.subjectPreferences) && data.subjectPreferences.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {data.subjectPreferences.map((code) => (
              <span
                key={code}
                className="inline-flex items-center gap-1 rounded-full border-[1.5px] border-border bg-candy-purple-soft px-2.5 py-0.5 text-xs font-bold text-primary"
              >
                <Sparkles className="h-3 w-3" aria-hidden="true" />
                {subjectLabel(code)}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function subjectLabel(code: string): string {
  const map: Record<string, string> = {
    english: "英语",
    programming: "编程",
    coding: "编程",
    math: "数学",
    chinese: "语文",
    physics: "物理",
  };
  return map[code] ?? code;
}

function MeHeaderSkeleton() {
  return (
    <div
      className="flex items-center gap-4 rounded-2xl border-[3px] border-border bg-white p-5"
      role="status"
      aria-label="正在加载个人资料…"
    >
      <div className="h-20 w-20 shrink-0 animate-pulse rounded-full bg-candy-bg" />
      <div className="flex-1 space-y-2">
        <div className="h-5 w-40 animate-pulse rounded-md bg-candy-bg" />
        <div className="h-3 w-56 animate-pulse rounded-md bg-candy-bg" />
        <div className="h-3 w-32 animate-pulse rounded-md bg-candy-bg" />
      </div>
    </div>
  );
}