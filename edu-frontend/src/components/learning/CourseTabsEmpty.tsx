/**
 * CourseTabsEmpty — 我的课程页三个 Tabs 各自的空态 CTA
 */
"use client";

import Link from "next/link";
import { BookMarked, GraduationCap, Heart } from "lucide-react";
import { Button } from "@/components/ui/button";

type TabKind = "in_progress" | "completed" | "favorited";

export function CourseTabsEmpty({ kind }: { kind: TabKind }) {
  if (kind === "in_progress") {
    return (
      <EmptyFrame
        Icon={GraduationCap}
        accentClass="bg-sky-500"
        title="还没有正在学习的课程"
        desc="从分级课程商城挑一门，立刻开启学习路径。"
        primary={{ href: "/courses", label: "去课程首页", Icon: undefined }}
        secondary={{ href: "/courses/search", label: "用条件搜索" }}
      />
    );
  }
  if (kind === "completed") {
    return (
      <EmptyFrame
        Icon={BookMarked}
        accentClass="bg-emerald-500"
        title="还没有完成的课程"
        desc="完成课程会自动归类到这里，并给你一枚学习徽章。"
        primary={{ href: "/my-courses?tab=in_progress", label: "继续已报名课程" }}
        secondary={{ href: "/dashboard", label: "去仪表盘看进度" }}
      />
    );
  }
  return (
    <EmptyFrame
      Icon={Heart}
      accentClass="bg-rose-500"
      title="还没有收藏的课程"
      desc="在课程卡片右上角点击 ⭐ 可以把感兴趣的课程收藏起来。"
      primary={{ href: "/courses", label: "浏览课程" }}
      secondary={{ href: "/courses/search", label: "按条件找课" }}
    />
  );
}

function EmptyFrame({
  Icon,
  accentClass,
  title,
  desc,
  primary,
  secondary,
}: {
  Icon: React.ComponentType<{ className?: string }>;
  accentClass: string;
  title: string;
  desc: string;
  primary: { href: string; label: string; Icon?: React.ComponentType<{ className?: string }> };
  secondary?: { href: string; label: string };
}) {
  return (
    <div className="rounded-3xl border border-dashed p-10 text-center">
      <div
        className={
          "mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl text-white shadow-sm " +
          accentClass
        }
      >
        <Icon className="h-7 w-7" />
      </div>
      <div className="text-lg font-semibold">{title}</div>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{desc}</p>
      <div className="mt-5 flex items-center justify-center gap-2">
        <Button asChild>
          <Link href={primary.href}>
            {primary.Icon ? <primary.Icon className="mr-1.5 h-4 w-4" /> : null}
            {primary.label}
          </Link>
        </Button>
        {secondary && (
          <Button asChild variant="outline">
            <Link href={secondary.href}>{secondary.label}</Link>
          </Button>
        )}
      </div>
    </div>
  );
}
