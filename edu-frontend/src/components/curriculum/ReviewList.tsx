/**
 * ReviewList — 课程详情页「学员评价」Tab
 * 契约② 无评价端点：无 MOCK，默认空态占位；后端评价 API 到位后传 reviews 即可。
 */
"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Star } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export interface ReviewItem {
  id: number | string;
  user_name: string;
  rating: number; // 1..5
  subject_tag?: string;
  published_at?: string;
  content: string;
  helpful?: number;
}

export function ReviewList({
  reviews = [],
  emptyText = "暂无评价，报名后再来分享吧～",
}: {
  reviews?: ReviewItem[];
  emptyText?: string;
}) {
  const stats = (() => {
    if (!reviews.length) return { avg: 0, count: 0, distribution: [0, 0, 0, 0, 0] };
    const dist = [0, 0, 0, 0, 0];
    let total = 0;
    for (const r of reviews) {
      total += r.rating;
      const bucket = Math.max(0, Math.min(4, Math.round(r.rating) - 1));
      dist[bucket] += 1;
    }
    return {
      avg: total / reviews.length,
      count: reviews.length,
      distribution: dist,
    };
  })();

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="text-lg">学员评价</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            共 {stats.count} 条评价，平均分
            {/* 星级豁免（design-options §2.3）：均分数字 warning-foreground（amber-700，a11y 修复） */}
            <span className="ml-1 font-semibold text-warning-foreground">
              {stats.avg.toFixed(1)}
            </span>
            <span className="ml-2">/ 5.0</span>
          </p>
        </div>
        <div className="hidden w-72 space-y-1.5 md:block">
          {[5, 4, 3, 2, 1].map((stars) => {
            const n = stats.distribution[stars - 1] ?? 0;
            const ratio = stats.count ? n / stats.count : 0;
            return (
              <div key={stars} className="flex items-center gap-2 text-xs">
                <span className="w-5 tabular-nums text-muted-foreground">{stars}</span>
                <Star className="h-3.5 w-3.5 fill-warning-foreground text-warning-foreground" />
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-warning-foreground"
                    style={{ width: `${Math.round(ratio * 100)}%` }}
                  />
                </div>
                <span className="w-8 text-right tabular-nums text-muted-foreground">
                  {n}
                </span>
              </div>
            );
          })}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {reviews.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            {emptyText}
          </div>
        ) : (
          reviews.map((r, i) => (
            <article key={r.id ?? `rv-${i}`} className="rounded-xl border border-border bg-card p-4">
              <header className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Avatar className="h-9 w-9">
                    <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">
                      {r.user_name.slice(0, 1)}
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-medium text-foreground">{r.user_name}</span>
                      {r.subject_tag && (
                        <Badge variant="secondary" className="text-xs">
                          {r.subject_tag}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {r.published_at || ""}
                    </div>
                  </div>
                </div>
                <RatingStars rating={r.rating} />
              </header>
              <p className="mt-3 text-sm leading-6 text-foreground/90">{r.content}</p>
              {typeof r.helpful === "number" && (
                <div className="mt-2 text-xs text-muted-foreground">
                  {r.helpful} 人觉得这条评价有用
                </div>
              )}
            </article>
          ))
        )}
      </CardContent>
    </Card>
  );
}

function RatingStars({ rating }: { rating: number }) {
  const full = Math.round(rating);
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={
            "h-4 w-4 " +
            // 星级豁免：填充 warning-foreground；未点亮 fill-muted
            (i <= full
              ? "fill-warning-foreground text-warning-foreground"
              : "fill-muted text-muted")
          }
        />
      ))}
    </div>
  );
}
