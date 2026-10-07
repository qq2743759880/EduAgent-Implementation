"use client";

import { Award, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useAuthStore, type UserInfo } from "@/lib/auth-client";
import { SUBJECT_LABELS, type SubjectKey } from "@/lib/validators/profile-schemas";
import { cn } from "@/lib/utils";

function firstChar(str: string): string {
  if (!str) return "U";
  const trimmed = str.trim();
  if (!trimmed) return "U";
  return trimmed.slice(0, 1).toUpperCase();
}

interface ProfileLayoutProps {
  children: ReactNode;
  className?: string;
  /** 积分，未接入时不传 */
  points?: number | null;
  /** 学科偏好（用户已勾选的键），未设置时传空数组 */
  subjectPreferences?: SubjectKey[];
}

export function ProfileLayout({
  children,
  className,
  points = null,
  subjectPreferences = [],
}: ProfileLayoutProps) {
  const me: UserInfo | null = useAuthStore((s) => s.me);

  const displayName = me?.nickname || "同学";
  const email = me?.email || "";
  const avatarUrl = me?.avatar || undefined;

  return (
    <div
      className={cn(
        // fe-task07：装饰渐变页面底 → bg-background（中性页面基底）
        "min-h-[calc(100vh-4rem)] w-full bg-background px-4 py-8 sm:px-6 lg:px-10",
        className,
      )}
    >
      <div className="mx-auto w-full max-w-6xl grid grid-cols-1 md:grid-cols-[240px_1fr] gap-6">
        {/* 左：用户简卡 */}
        <aside>
          <Card className="shadow-card border-border sticky top-6">
            <CardContent className="pt-8 pb-6 flex flex-col items-center text-center space-y-4">
              <div className="relative">
                <Avatar className="h-20 w-20 border-4 border-card shadow">
                  {avatarUrl ? <AvatarImage src={avatarUrl} alt={displayName} /> : null}
                  <AvatarFallback className="bg-gradient-to-br from-primary-deep to-primary text-primary-foreground text-2xl font-semibold">
                    {firstChar(displayName)}
                  </AvatarFallback>
                </Avatar>
                {/* fe-task07：编辑徽章 amber-400 → bg-warning-foreground（amber-700 档，a11y 修复） */}
                <span className="absolute -bottom-1 -right-1 inline-flex items-center justify-center h-7 w-7 rounded-full bg-warning-foreground text-white shadow ring-2 ring-card">
                  <Sparkles className="h-3.5 w-3.5" />
                </span>
              </div>
              <div className="space-y-1">
                <h2 className="text-lg font-semibold text-foreground">{displayName}</h2>
                <p className="text-xs text-muted-foreground break-all px-2">{email || "尚未设置邮箱"}</p>
              </div>
              <Separator />
              <div className="w-full space-y-4 pt-1">
                <div className="flex items-center justify-between px-1 text-sm">
                  <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                    <Award className="h-4 w-4 text-warning-foreground" />
                    当前积分
                  </span>
                  <span className="font-semibold text-foreground tabular-nums">
                    {points == null ? "—" : points.toLocaleString()}
                  </span>
                </div>
                <div className="space-y-2 text-left">
                  <div className="text-xs text-muted-foreground px-1">学科偏好</div>
                  <div className="flex flex-wrap gap-1.5 min-h-[2rem] px-1">
                    {subjectPreferences.length === 0 ? (
                      <span className="text-xs text-muted-foreground">暂未设置，去「偏好设置」添加</span>
                    ) : (
                      subjectPreferences.map((k) => (
                        <Badge key={k} variant="secondary" className="bg-primary-soft text-primary hover:bg-primary-soft border border-primary-border">
                          {SUBJECT_LABELS[k]}
                        </Badge>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </aside>

        {/* 右：内容插槽（个人中心 Tabs 由页面拼装） */}
        <section className="min-w-0">{children}</section>
      </div>
    </div>
  );
}

export default ProfileLayout;
