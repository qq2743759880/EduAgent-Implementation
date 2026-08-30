/**
 * PracticeCenterClient — 复习中心客户端（task49 重构，candy-playful frozen）
 * 结构（对齐 practice.html 效果图）：
 *   - 顶部：面包屑 + 糖果头 + 三入口卡（错题本/单词本/专项练习，Grid lg:3）+ 统计行
 *   - 内容区两层：
 *       list  → 按 mode 渲染 WrongBookPanel / TopicPanel / VocabDailyPanel
 *       quiz  → QuizSession（复习会话：取题→作答→判分→explain_content 解析）
 * 守卫：未登录 → /login?redirect=；mode 非法 → UnsupportedMode（糖果态）
 * 契约：复用了 task40 契约⑤（interactive/quiz|vocab）；错题出题源已切 question 表（task13/裙④）。
 */
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  BookMarked,
  CircleHelp,
  GraduationCap,
  Loader2,
  ScrollText,
  Swords,
  Target,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/auth-client";
import { getVocabProgress, listWrongBook } from "@/lib/api/learning";
import { VocabDailyPanel } from "@/components/learning/VocabDailyPanel";
import { VocabProgressCard } from "@/components/learning/VocabProgressCard";
import { CandyStatRow } from "./CandyStatRow";
import { WrongBookPanel } from "./WrongBookPanel";
import { TopicPanel } from "./TopicPanel";
import { QuizSession, type ReviewSession } from "./QuizSession";
import { cn } from "@/lib/utils";

export interface PracticeCenterClientProps {
  mode: "wrong-book" | "topic" | "vocab" | null;
  rawMode: string;
}

export default function PracticeCenterClient({ mode, rawMode }: PracticeCenterClientProps) {
  const router = useRouter();
  const authed = useAuthStore((s) => s.ready && !!s.token);
  const [session, setSession] = useState<ReviewSession | null>(null);
  const [listVersion, setListVersion] = useState(0);

  useEffect(() => {
    if (authed) return;
    const redirect = encodeURIComponent(window.location.pathname + (window.location.search ?? ""));
    router.replace(`/login?redirect=${redirect}`);
  }, [authed, router]);

  /* 入口卡数量徽标（与 CandyStatRow 同 key，命中同一查询缓存） */
  const wrongQ = useQuery({
    queryKey: ["practice_stat_wrong"] as const,
    queryFn: () => listWrongBook({ page: 1, page_size: 1, only_not_mastered: true }),
    staleTime: 2 * 60_000,
    retry: false,
  });
  const vocabQ = useQuery({
    queryKey: ["practice_stat_vocab"] as const,
    queryFn: () => getVocabProgress({ window_days: 30 }),
    staleTime: 2 * 60_000,
    retry: false,
  });

  if (!authed) {
    return (
      <div className="rounded-3xl border-[3px] border-dashed border-foreground bg-white p-10 text-center">
        <Loader2 className="mx-auto mb-2 h-6 w-6 animate-spin text-candy-purple" />
        <div className="text-base font-bold text-foreground">请先登录再进入复习中心</div>
        <p className="mx-auto mt-1 max-w-md text-3xs font-medium text-muted-foreground">
          复习中心包含你的错题本、专项练习与单词计划，需要登录后才能查看个人数据。
        </p>
      </div>
    );
  }

  if (!mode) {
    return <UnsupportedMode rawMode={rawMode} />;
  }

  /* 复习会话进行中 → 覆盖内容区 */
  if (session) {
    return (
      <QuizSession
        session={session}
        onBack={() => {
          setSession(null);
          setListVersion((v) => v + 1);
        }}
      />
    );
  }

  const wrongTotal = wrongQ.data?.total;
  const dueToday = vocabQ.data?.due_today ?? null;

  return (
    <div className="space-y-5">
      {/* 头 + 三入口卡 */}
      <header>
        <nav className="mb-3 flex flex-wrap items-center gap-1.5 text-3xs font-semibold text-muted-foreground">
          <Link href="/my-courses" className="font-bold text-candy-blue hover:underline">
            我的课程
          </Link>
          <span aria-hidden="true">/</span>
          <span className="font-bold text-foreground">复习中心</span>
        </nav>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight md:text-3xl">复习中心</h1>
            <p className="mt-1 max-w-xl text-3xs font-medium text-muted-foreground">
              错题复盘 · 专项突破 · 单词回忆 —— 糖果色 · candy-playful
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild size="sm" variant="ghost">
              <Link href="/my-courses">
                <ArrowLeft className="mr-1.5 h-4 w-4" /> 我的课程
              </Link>
            </Button>
            <Button asChild size="sm">
              <Link href="/dashboard">
                <GraduationCap className="mr-1.5 h-4 w-4" />
                仪表盘
              </Link>
            </Button>
          </div>
        </div>
      </header>

      {/* 统计行（增强信息，数据缺失显示占位） */}
      <CandyStatRow />

      {/* 三入口卡 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3" aria-label="三种复习模式">
        <EntryCard
          href="/practice/wrong-book"
          accent="green"
          icon={<ScrollText className="h-6 w-6" />}
          title="错题本"
          badge={wrongTotal != null ? `${wrongTotal} 题待复习` : "待统计"}
          desc="历史答错题目入库（question 表出题），逐题重做 + 查看 explain_content 解析。"
          cta="开始复习 →"
          active={mode === "wrong-book"}
        />
        <EntryCard
          href="/practice/vocab"
          accent="blue"
          icon={<BookMarked className="h-6 w-6" />}
          title="单词本"
          badge={dueToday != null ? `${dueToday} 词待回忆` : "待统计"}
          desc="SM-2 间隔回忆，按遗忘曲线安排复习节点（既有词卡，本次不改动）。"
          cta="开始回忆 →"
          active={mode === "vocab"}
        />
        <EntryCard
          href="/practice/topic"
          accent="purple"
          icon={<Target className="h-6 w-6" />}
          title="专项练习"
          badge="按题型选择"
          desc="按题型（单选/多选/填空/判断）定向刷题，与错题进度隔离。"
          cta="去练习 →"
          active={mode === "topic"}
        />
      </div>

      {/* 内容区 */}
      <div>{renderPanel()}</div>
    </div>
  );

  function renderPanel() {
    if (mode === "wrong-book") {
      return <WrongBookPanel version={listVersion} onStart={() => setSession({ source: "wrong-book" })} />;
    }
    if (mode === "topic") {
      return <TopicPanel onStart={(qmode) => setSession({ source: "topic", qmode })} />;
    }
    // vocab：SM-2 词卡（范围外，复用不动）
    return (
      <div className="space-y-5">
        <VocabProgressCard />
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <VocabDailyPanel subject_code="english" plan_count={20} />
          <div className="xl:sticky xl:top-24 xl:self-start">
            <div className="rounded-3xl border-[3px] border-foreground bg-white p-5 shadow-[0_5px_0_rgba(31,31,31,0.14)]">
              <div className="flex items-center gap-2 text-sm font-extrabold">
                <Swords className="h-4 w-4 text-candy-red" /> 被记入错题？
              </div>
              <p className="mt-1 text-3xs font-medium text-muted-foreground">
                随堂练习答错的题会自动进入错题本，点这里一次性巩固。
              </p>
              <Button
                className="mt-3"
                size="sm"
                variant="outline"
                onClick={() => router.replace("/practice/wrong-book", { scroll: true })}
              >
                打开错题本
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}

function EntryCard(props: {
  href: string;
  accent: "green" | "blue" | "purple";
  icon: React.ReactNode;
  title: string;
  badge: string;
  desc: string;
  cta: string;
  active: boolean;
}) {
  const { href, accent, icon, title, badge, desc, cta, active } = props;
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-[1.75rem] border-[3px] border-foreground bg-white shadow-[0_5px_0_rgba(31,31,31,0.14)]",
        active && "ring-2 ring-candy-purple/40",
      )}
    >
      <div
        className={cn(
          "absolute inset-x-0 top-0 h-2",
          accent === "green" && "bg-candy-green",
          accent === "blue" && "bg-candy-blue",
          accent === "purple" && "bg-candy-purple",
        )}
      />
      <div className="flex flex-col p-5 pt-5">
        <span
          className={cn(
            "mb-3 grid h-12 w-12 place-items-center rounded-xl border-2 border-foreground text-white",
            accent === "green" && "bg-candy-green",
            accent === "blue" && "bg-candy-blue",
            accent === "purple" && "bg-candy-purple",
          )}
        >
          {icon}
        </span>
        <div className="flex items-center gap-2 text-base font-extrabold">
          {title}
          <span
            className={cn(
              "rounded-full border-2 border-foreground px-2.5 py-0.5 text-3xs font-extrabold",
              accent === "green" && "bg-candy-green-soft text-candy-green",
              accent === "blue" && "bg-candy-blue/15 text-candy-blue",
              accent === "purple" && "bg-candy-purple-soft text-candy-purple",
            )}
          >
            {badge}
          </span>
        </div>
        <p className="mt-2 flex-1 text-3xs font-medium leading-relaxed text-muted-foreground">
          {desc}
        </p>
        <Link
          href={href}
          className={cn(
            "mt-4 inline-flex w-full items-center justify-center rounded-xl border-[3px] border-foreground py-2.5 text-sm font-extrabold text-white shadow-[0_4px_0_rgba(31,31,31,0.18)] transition-transform hover:-translate-y-px active:translate-y-px active:shadow-none",
            accent === "green" && "bg-candy-green",
            accent === "blue" && "bg-candy-blue",
            accent === "purple" && "bg-candy-purple",
          )}
        >
          {cta}
        </Link>
      </div>
    </div>
  );
}

function UnsupportedMode({ rawMode }: { rawMode: string }) {
  return (
    <div className="rounded-3xl border-[3px] border-dashed border-foreground bg-white p-10 text-center">
      <CircleHelp className="mx-auto mb-2 h-7 w-7 text-muted-foreground/70" />
      <div className="text-base font-extrabold text-foreground">不存在的复习模式</div>
      <p className="mx-auto mt-1 max-w-md text-3xs font-medium text-muted-foreground">
        当前路径 <code className="rounded bg-muted px-1">/practice/{rawMode || ""}</code>{" "}
        不在支持范围。可选模式：
        <code className="mx-1 rounded bg-muted px-1">wrong-book</code>、
        <code className="mx-1 rounded bg-muted px-1">topic</code>、
        <code className="mx-1 rounded bg-muted px-1">vocab</code>
      </p>
      <div className="mt-4 flex items-center justify-center gap-2">
        <Button asChild size="sm" variant="outline">
          <Link href="/practice/wrong-book">错题本</Link>
        </Button>
        <Button asChild size="sm">
          <Link href="/practice/topic">专项练习</Link>
        </Button>
        <Button asChild size="sm" variant="ghost">
          <Link href="/dashboard">去仪表盘</Link>
        </Button>
      </div>
    </div>
  );
}