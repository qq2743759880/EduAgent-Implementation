/**
 * InteractiveTabs — 播放页互动习题/单词/数学/编程 Tab 容器
 * 四个子面板按需渲染：
 *   - Quiz（P5 互动习题）——默认激活，直接显示 QuizPanel
 *   - Word（P5 单词本）—— 直接调用 VocabDailyPanel
 *   - Math（P5 互动数学）—— Minimal 入口占位（后续替换成 P5 /api/math/practice 渲染）
 *   - Coding（P5 编程练习）—— Minimal 入口占位
 */
"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertCircle, Binary, Calculator, BookText, HelpCircle, Layers } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { QuizPanel } from "./QuizPanel";
import { VocabDailyPanel } from "./VocabDailyPanel";

export interface InteractiveTabsProps {
  subjectCode?: string | null;
  seriesId?: number;
  sessionId?: number;
}

export function InteractiveTabs({ subjectCode, seriesId, sessionId }: InteractiveTabsProps) {
  return (
    <Card className="overflow-hidden">
      <Tabs defaultValue="quiz" className="w-full">
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-3 border-b bg-slate-50/40">
          <div className="flex-1">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Layers className="h-5 w-5 text-primary" />
              课次互动练习
            </CardTitle>
            <CardDescription>
              视频看完后，在这里做随堂题、背单词，学习路径自动上色。
            </CardDescription>
          </div>
          <TabsList className="grid grid-cols-4 bg-background shadow-sm">
            <TabsTrigger value="quiz" className="gap-1.5">
              <HelpCircle className="h-3.5 w-3.5" /> 习题
            </TabsTrigger>
            <TabsTrigger value="word" className="gap-1.5">
              <BookText className="h-3.5 w-3.5" /> 单词
            </TabsTrigger>
            <TabsTrigger value="math" className="gap-1.5">
              <Calculator className="h-3.5 w-3.5" /> 数学
            </TabsTrigger>
            <TabsTrigger value="coding" className="gap-1.5">
              <Binary className="h-3.5 w-3.5" /> 编程
            </TabsTrigger>
          </TabsList>
        </CardHeader>

        <CardContent className="p-4 md:p-6">
          <TabsContent value="quiz">
            <QuizPanel
              subject_code={subjectCode ?? undefined}
              series_id={seriesId}
              session_id={sessionId}
              prefer_from_session
            />
          </TabsContent>

          <TabsContent value="word">
            {subjectCode === "english" ? (
              <VocabDailyPanel subject_code="english" compact />
            ) : (
              <PlaceholderPanel
                Icon={BookText}
                title="单词本仅英语学科可用"
                desc="当前课程不属于英语学科，暂无可记忆的单词卡。切换到英语课程可查看今日计划与 SM-2 召回流程。"
                cta={[
                  { label: "去英语课列表", href: "/courses?subject=english" },
                  { label: "打开复习中心·单词", href: "/practice/vocab" },
                ]}
              />
            )}
          </TabsContent>

          <TabsContent value="math">
            {subjectCode === "math" ? (
              <PlaceholderPanel
                Icon={Calculator}
                title="数学互动练习：后续阶段上线"
                desc="P5 的 /api/math/practice 与 step-check 接口已就绪，P9 播放页集成将在下个阶段（Step4 完成后）补齐。"
                cta={[
                  { label: "打开复习中心·错题", href: "/practice/wrong-book" },
                ]}
                badge="P9-Step4 Phase 2"
              />
            ) : (
              <PlaceholderPanel
                Icon={Calculator}
                title="数学练习非本学科"
                desc="当前学科无数学练习，切换到数学课程即可看到分步骤互动解题。"
                cta={[{ label: "去数学课列表", href: "/courses?subject=math" }]}
              />
            )}
          </TabsContent>

          <TabsContent value="coding">
            {subjectCode === "programming" ? (
              <PlaceholderPanel
                Icon={Binary}
                title="编程挑战：后续阶段上线"
                desc="P5 的 coding/practice 接口已就绪，会在独立 Playground 模式与 AI 代码助手完成后集成。"
                cta={[{ label: "打开复习中心·错题", href: "/practice/wrong-book" }]}
                badge="P10（AI Playground）"
              />
            ) : (
              <PlaceholderPanel
                Icon={Binary}
                title="编程练习非本学科"
                desc="当前学科无编程题。切换到编程（Programming）课程可以获得互动 IDE 练习。"
                cta={[{ label: "去编程课列表", href: "/courses?subject=programming" }]}
              />
            )}
          </TabsContent>
        </CardContent>
      </Tabs>
    </Card>
  );
}

function PlaceholderPanel({
  Icon,
  title,
  desc,
  cta,
  badge,
}: {
  Icon: React.ComponentType<{ className?: string }>;
  title: string;
  desc: string;
  cta?: Array<{ href: string; label: string }>;
  badge?: string;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-[auto_minmax(0,1fr)] md:items-start">
      <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-primary/10 text-primary md:mx-0">
        <Icon className="h-7 w-7" />
      </div>
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base font-semibold">{title}</h3>
          {badge && <Badge variant="secondary" className="text-xs">{badge}</Badge>}
        </div>
        <p className="mt-2 text-sm text-muted-foreground">{desc}</p>
        {cta && cta.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {cta.map((c, i) => (
              <Button key={i} asChild size="sm" variant={i === 0 ? "default" : "outline"}>
                <Link href={c.href}>{c.label}</Link>
              </Button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

// 避免 lint 警告（保留 AlertCircle 做后续错误态）
export const __unused_alert = AlertCircle;
