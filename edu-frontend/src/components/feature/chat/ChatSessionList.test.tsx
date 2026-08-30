/**
 * ChatSessionList 单测（task50-fix）：渲染/高亮/点选/删除/新建/空态/loading/键盘。
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ChatSessionList, type ChatSessionListProps } from "./ChatSessionList";
import type { ChatSession } from "@/lib/api/chat";

const DAY = 86_400_000;

function sess(id: string, over: Partial<ChatSession> = {}): ChatSession {
  const now = new Date();
  const updated = new Date(now.getTime() - 2 * DAY).toISOString();
  return {
    session_id: id,
    user_id: 1,
    title: `会话 ${id}`,
    visibility: "private",
    message_count: 3,
    last_message_at: null,
    created_at: updated,
    updated_at: updated,
    yn: 1,
    ...over,
  };
}

function setup(over: Partial<ChatSessionListProps> = {}) {
  const props: ChatSessionListProps = {
    sessions: [sess("s1"), sess("s2"), sess("s3")],
    activeId: "s2",
    loading: false,
    onSelect: vi.fn(),
    onNew: vi.fn(),
    onDelete: vi.fn(),
    ...over,
  };
  return { props, ...render(<ChatSessionList {...props} />) };
}

describe("ChatSessionList", () => {
  it("渲染会话标题与时间，且仅当前会话带 data-active 高亮", () => {
    const { props, container } = setup({ sessions: [sess("s1"), sess("s2"), sess("s3")], activeId: "s2" });
    expect(container.querySelectorAll('[data-slot="chat-session-row"]').length).toBe(3);
    const rows = Array.from(container.querySelectorAll('[data-slot="chat-session-row"]'));
    const active = rows.filter((r) => r.getAttribute("data-active") !== null);
    expect(active.length).toBe(1);
    expect(active[0]?.textContent).toContain(props.sessions[1].title);
    expect(screen.getByText("会话 s1")).toBeInTheDocument();
  });

  it("点选行触发 onSelect(sessionId)", () => {
    const { props } = setup();
    fireEvent.click(screen.getByText("会话 s3"));
    expect(props.onSelect).toHaveBeenCalledExactlyOnceWith("s3");
  });

  it("键盘 Enter 同样触发 onSelect", () => {
    const { props } = setup();
    fireEvent.keyDown(screen.getByText("会话 s3"), { key: "Enter" });
    expect(props.onSelect).toHaveBeenCalledExactlyOnceWith("s3");
  });

  it("点删除触发 onDelete 且不再触发 onSelect（stopPropagation）", () => {
    const { props, container } = setup();
    const del = container.querySelector('[data-slot="chat-session-delete"]') as HTMLElement;
    fireEvent.click(del);
    expect(props.onDelete).toHaveBeenCalledExactlyOnceWith("s1");
    expect(props.onSelect).not.toHaveBeenCalled();
  });

  it("「＋ 新建」触发 onNew", () => {
    const { props } = setup();
    fireEvent.click(screen.getByText("＋ 新建"));
    expect(props.onNew).toHaveBeenCalledOnce();
  });

  it("空列表渲染引导文案", () => {
    setup({ sessions: [] });
    expect(screen.getByText(/还没有会话/)).toBeInTheDocument();
  });

  it("loading 渲染骨架占位", () => {
    const { container } = setup({ loading: true });
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("临时会话（tmp_ 前缀）降透明度标记", () => {
    const { container } = setup({ sessions: [sess("tmp_123")], activeId: "tmp_123" });
    const row = container.querySelector('[data-slot="chat-session-row"]') as HTMLElement;
    expect(row.className).toContain("opacity-70");
  });
});