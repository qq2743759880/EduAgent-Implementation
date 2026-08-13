/**
 * PracticeCenterClient — 复习中心客户端
 *   - 未登录 → /login?redirect=
 *   - wrong-book：WrongBookList + VocabProgressCard 简化 CTA 去单词
 *   - vocab：VocabProgressCard（顶部 12 列全宽）+ VocabDailyPanel（主复习交互）+ WrongBookList 入口
 */
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ArrowLeft, BookMarked, CircleHelp, GraduationCap, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuthStore } from "@/lib/auth-client";
import { WrongBookList } from "@/components/learning/WrongBookList";
import { VocabDailyPanel } from "@/components/learning/VocabDailyPanel";
import { VocabProgressCard } from "@/components/learning/VocabProgressCard";
import { Card, CardContent } from "@/components/ui/card";

export interface PracticeCenterClientProps {
  mode: "wrong-book" | "vocab" | null;
  rawMode: string;
}

export default function PracticeCenterClient({ mode, rawMode }: PracticeCenterClientProps) {
  const router = useRouter();
  const authed = useAuthStore((s) => s.isAuthenticated());

  useEffect(() => {
    if (authed) return;
    const redirect = encodeURIComponent(window.location.pathname + (window.location.search ?? ""));
    router.replace(`/login?redirect=${redirect}`);
  }, [authed, router]);

  if (!authed) {
    return (
      <div className="rounded-xl border border-dashed border-border p-10 text-center">
        <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-primary" />
        <div className="text-base font-semibold text-foreground">请先登录再进入复习中心</div>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          复习中心包含你的错题本与单词计划，需要登录后才能查看个人数据。
        </p>
      </div>
    );
  }

  if (!mode) {
    return <UnsupportedMode rawMode={rawMode} />;
  }

  const tabsValue = mode;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <div className="inline-flex items-center gap-1.5 rounded-full border bg-primary/5 px-3 py-1 text-xs font-medium text-primary">
            <Sparkles className="h-3.5 w-3.5" />
            Review Center
          </div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">复习中心</h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            重做错题，复习单词；持续坚持，知识图谱会逐步被你「染绿」。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild size="sm" variant="ghost">
            <Link href="/my-courses">
              <ArrowLeft className="mr-1.5 h-4 w-4" /> 返回我的课程
            </Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/dashboard">
              <GraduationCap className="mr-1.5 h-4 w-4" />
              去仪表盘
            </Link>
          </Button>
        </div>
      </header>

      <Tabs
        value={tabsValue}
        onValueChange={(v) => router.replace(`/practice/${v}`, { scroll: true })}
      >
        <TabsList>
          <TabsTrigger value="wrong-book" className="gap-2">
            <CircleHelp className="h-4 w-4" /> 错题本
          </TabsTrigger>
          <TabsTrigger value="vocab" className="gap-2">
            <BookMarked className="h-4 w-4" /> 单词本
          </TabsTrigger>
        </TabsList>

        <div className="mt-5">
          <TabsContent value="wrong-book">
            <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
              <WrongBookList onlyNotMastered />
              <div className="space-y-5 xl:sticky xl:top-24 xl:self-start">
                <VocabProgressCard compact />
                <Card>
                  <CardContent className="space-y-3 p-4">
                    <div className="flex items-center gap-2 text-sm font-semibold">
                      <Sparkles className="h-4 w-4 text-primary" />
                      想复习单词？
                    </div>
                    <p className="text-xs text-muted-foreground">
                      每日 20 张单词卡，只需 5–8 分钟即可完成 SM-2 召回流程。
                    </p>
                    <Button
                      size="sm"
                      onClick={() => router.replace("/practice/vocab", { scroll: true })}
                    >
                      去单词本页面 <ArrowRightInline />
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="vocab">
            <div className="space-y-5">
              <VocabProgressCard />
              <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
                <VocabDailyPanel subject_code="english" plan_count={20} />
                <div className="xl:sticky xl:top-24 xl:self-start">
                  <Card>
                    <CardContent className="space-y-3 p-4">
                      <div className="flex items-center gap-2 text-sm font-semibold">
                        {/* fe-task07：重做错题 rose → destructive（保留语义，纠错=危险） */}
                        <CircleHelp className="h-4 w-4 text-destructive" /> 重做错题
                      </div>
                      <p className="text-xs text-muted-foreground">
                        随堂练习答错的题会自动进入错题本，点这里一次性巩固。
                      </p>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          router.replace("/practice/wrong-book", { scroll: true })
                        }
                      >
                        打开错题本
                      </Button>
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}

function UnsupportedMode({ rawMode }: { rawMode: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-10 text-center">
      <CircleHelp className="mx-auto mb-2 h-7 w-7 text-muted-foreground/70" />
      <div className="text-base font-semibold text-foreground">不存在的复习模式</div>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        当前路径 <code className="rounded bg-muted px-1">/practice/{rawMode || ""}</code>{" "}
        不在支持的范围内。可选模式为：
        <code className="mx-1 rounded bg-muted px-1">wrong-book</code>
        与
        <code className="mx-1 rounded bg-muted px-1">vocab</code>
      </p>
      <div className="mt-4 flex items-center justify-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href="/practice/wrong-book">错题本</Link>
        </Button>
        <Button asChild size="sm">
          <Link href="/practice/vocab">单词本</Link>
        </Button>
        <Button asChild size="sm" variant="ghost">
          <Link href="/dashboard">去仪表盘</Link>
        </Button>
      </div>
    </div>
  );
}

function ArrowRightInline() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="ml-1.5 inline h-4 w-4"
    >
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </svg>
  );
}
