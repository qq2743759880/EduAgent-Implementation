/**
 * CourseCard — 课程列表卡片（首页/搜索页复用）
 * 展示：封面 / 学科标签 / 级别标签 / 标题 / 简介 / 价格（原价划线）/ 课时数 / 评分 / 学生数
 * 点击整张卡片跳详情页。
 */
"use client";

import Link from "next/link";
import { Clock, Star, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { LEVEL_OPTIONS, SUBJECT_OPTIONS, SeriesSummary } from "@/lib/api/curriculum";

export function CourseCard({ data }: { data: SeriesSummary }) {
  const subject = SUBJECT_OPTIONS.find((s) => s.code === data.subject_code);
  const level = LEVEL_OPTIONS.find((l) => l.code === data.level_code);
  const priceNow = data.price_current ?? 0;
  const priceOrigin = data.price_original ?? priceNow;
  const hours = typeof data.total_hours === "number" ? data.total_hours : 0;
  const sessions = data.session_count ?? 0;
  const rating = typeof data.rating === "number" ? data.rating : 4.5;
  const students = data.student_count ?? 0;

  return (
    <Link href={`/courses/${data.id}`} className="group block">
      <Card className="h-full overflow-hidden transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
        <div className={"relative h-40 w-full overflow-hidden bg-gradient-to-br " + subjectColorGradient(data.subject_code)}>
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.25),transparent_60%)]" />
          <div className="absolute left-3 top-3 flex gap-1.5">
            {subject && (
              <Badge className={"text-white shadow-sm " + subject?.color}>{subject.name}</Badge>
            )}
            {level && (
              <Badge variant="secondary" className="bg-white/85 backdrop-blur-sm">
                {level.short}
              </Badge>
            )}
          </div>
          <div className="absolute bottom-3 left-4 right-4 flex items-end justify-between text-white">
            <div className="truncate text-lg font-semibold drop-shadow-sm">
              {data.series_title}
            </div>
          </div>
        </div>

        <CardContent className="p-4">
          <div className="line-clamp-2 min-h-[2.5rem] text-sm text-muted-foreground">
            {data.subtitle || data.description || "系统分级课程，配学习路径与互动习题。"}
          </div>

          <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {hours > 0 ? `${hours} 学时` : `${sessions} 课次`}
            </span>
            <span className="inline-flex items-center gap-1">
              <Users className="h-3.5 w-3.5" />
              {students.toLocaleString()} 人已报
            </span>
            <span className="inline-flex items-center gap-1 text-amber-600">
              <Star className="h-3.5 w-3.5 fill-current" />
              {rating.toFixed(1)}
            </span>
          </div>

          <div className="mt-3 flex items-end justify-between">
            <div>
              <div className="flex items-baseline gap-2">
                <span className="text-xl font-bold text-rose-600">
                  ¥{priceNow.toFixed(0)}
                </span>
                {priceOrigin > priceNow ? (
                  <span className="text-xs text-muted-foreground line-through">
                    ¥{priceOrigin.toFixed(0)}
                  </span>
                ) : null}
              </div>
            </div>
            <span className="text-xs text-emerald-600 opacity-0 transition-opacity group-hover:opacity-100">
              查看详情 →
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function subjectColorGradient(code: string | null | undefined): string {
  switch (code) {
    case "english":
      return "from-sky-500 via-sky-400 to-cyan-400";
    case "programming":
      return "from-violet-500 via-purple-500 to-indigo-500";
    case "math":
      return "from-emerald-500 via-teal-500 to-green-500";
    case "chinese":
      return "from-amber-500 via-orange-400 to-yellow-400";
    case "physics":
      return "from-rose-500 via-pink-500 to-red-500";
    default:
      return "from-slate-500 via-slate-400 to-slate-600";
  }
}
