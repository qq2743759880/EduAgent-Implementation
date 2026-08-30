/**
 * app/(user)/chat/page —— AI 问答页（task50 糖果单栏）
 *  - 客户端交互在 ChatCandyClient（受 Suspense 保护，因为用到 useSearchParams）
 *  - 路由：/chat[?context=session:{id}]（学习页「AI 提问」携带上下文）
 *  - metadata：SEO 标题 + desc 用于分享卡
 */
import type { Metadata } from "next";
import { Suspense } from "react";
import ChatCandyClient from "./_components/ChatCandyClient";

export const metadata: Metadata = {
  title: "AI 学习助手 · EduAgent",
  description:
    "EduAgent AI 问答助手：学科知识讲解、错题分析、学习规划、结合课程进度与学习数据，调用 MCP 工具检索课程与资料。",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default function ChatPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen w-full flex items-center justify-center bg-background text-muted-foreground">
        <div className="animate-pulse text-sm">正在加载 AI 助手…</div>
      </div>
    }>
      <ChatCandyClient />
    </Suspense>
  );
}
