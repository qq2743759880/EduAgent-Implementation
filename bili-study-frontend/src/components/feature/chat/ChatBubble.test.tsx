/**
 * ChatBubble 单测（task50）：三角色气泡 + 流式光标 + 引用计数 + 时间戳元信息。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatBubble } from "./ChatBubble";

describe("ChatBubble", () => {
  it("user 消息右对齐、角色标记 user，正文原样渲染", () => {
    const { container } = render(
      <ChatBubble role="user" content="帮我讲一下反向传播。" time="2026-08-21T10:04:00Z" />,
    );
    const slot = container.querySelector('[data-slot="chat-bubble"]');
    expect(slot?.getAttribute("data-role")).toBe("user");
    expect(slot).toHaveClass("self-end");
    expect(screen.getByText("帮我讲一下反向传播。")).toBeInTheDocument();
  });

  it("assistant 消息左对齐，内容以 Markdown 渲染（加粗生效），meta 含 🤖 与时间", () => {
    const { container } = render(
      <ChatBubble role="assistant" content="**反向传播**是核心。" time="2026-08-21T10:04:00Z" />,
    );
    const slot = container.querySelector('[data-slot="chat-bubble"]');
    expect(slot?.getAttribute("data-role")).toBe("assistant");
    expect(slot).toHaveClass("self-start");
    expect(screen.getByText("反向传播", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("🤖")).toBeInTheDocument();
    expect(screen.getAllByText(/\d{2}:\d{2}/).length).toBeGreaterThan(0);
  });

  it("引用计数 >0 时展示「🔎 N 篇引用」", () => {
    render(
      <ChatBubble role="assistant" content="回答" retrievedCount={5} time="2026-08-21T10:04:00Z" />,
    );
    expect(screen.getByText("🔎 5 篇引用")).toBeInTheDocument();
  });

  it("引用计数为 0/缺失时不显示引用", () => {
    const { queryByText } = render(
      <ChatBubble role="assistant" content="回答" retrievedCount={0} time="2026-08-21T10:04:00Z" />,
    );
    expect(queryByText(/篇引用/)).toBeNull();
  });

  it("流式态：AI 消息末尾渲染闪烁光标（bg-candy-green）", () => {
    const { container } = render(
      <ChatBubble role="assistant" content="正在" streaming />,
    );
    const cursor = container.querySelector("span.animate-pulse.bg-candy-green");
    expect(cursor).not.toBeNull();
  });

  it("system 角色渲染居中提示条（data-slot=chat-bubble-system）", () => {
    const { container } = render(<ChatBubble role="system" content="会话创建失败" />);
    expect(container.querySelector('[data-slot="chat-bubble-system"]')).not.toBeNull();
    expect(screen.getByText("会话创建失败")).toBeInTheDocument();
  });
});