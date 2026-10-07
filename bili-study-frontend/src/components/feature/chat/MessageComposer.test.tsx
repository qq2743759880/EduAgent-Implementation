/**
 * MessageComposer 单测（task50）：发送/停止切换、Enter 发送、禁用、上下文徽标、排队/降级提示。
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MessageComposer } from "./MessageComposer";

function setup(onSend = vi.fn(), overrides: Partial<React.ComponentProps<typeof MessageComposer>> = {}) {
  return render(
    <MessageComposer onSend={onSend} onStop={vi.fn()} streaming={false} {...overrides} />,
  );
}

describe("MessageComposer", () => {
  it("输入后 Enter 发送去空白文本并清空输入框", () => {
    const onSend = vi.fn();
    setup(onSend);
    const ta = screen.getByRole("textbox");
    fireEvent.change(ta, { target: { value: "  什么是反向传播？  " } });
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("什么是反向传播？");
    expect(ta).toHaveValue("");
  });

  it("Shift+Enter 仅在输入框中换行、不发送", () => {
    const onSend = vi.fn();
    setup(onSend);
    const ta = screen.getByRole("textbox");
    fireEvent.change(ta, { target: { value: "第一行" } });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("中文输入法组合（isComposing）回车不误发", () => {
    const onSend = vi.fn();
    setup(onSend);
    const ta = screen.getByRole("textbox");
    fireEvent.change(ta, { target: { value: "反向传播" } });
    // KeyboardEvent 构造器支持 isComposing init 成员（中文候选选字回车）
    fireEvent(ta, new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, isComposing: true }));
    expect(onSend).not.toHaveBeenCalled();
  });

  it("空/纯空白输入不发送", () => {
    const onSend = vi.fn();
    setup(onSend);
    const ta = screen.getByRole("textbox");
    fireEvent.change(ta, { target: { value: "   " } });
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("点击发送按钮触发 onSend 并清空", () => {
    const onSend = vi.fn();
    setup(onSend);
    const ta = screen.getByRole("textbox");
    fireEvent.change(ta, { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(onSend).toHaveBeenCalledWith("你好");
    expect(ta).toHaveValue("");
  });

  it("流式中显示「停止生成」按钮，点击触发 onStop 且无「发送」按钮", () => {
    const onStop = vi.fn();
    setup(vi.fn(), { streaming: true, onStop });
    expect(screen.queryByRole("button", { name: "发送" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "停止生成" }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("disabled 锁定输入框", () => {
    setup(vi.fn(), { disabled: true });
    expect(screen.getByRole("textbox")).toBeDisabled();
    // 输入框锁定后占位文案提示不可发送
    expect(screen.getByPlaceholderText("历史加载失败，无法发送")).toBeInTheDocument();
  });

  it("渲染上下文徽标与排队提示 pill", () => {
    setup(vi.fn(), { contextTag: "来自 · 通用编程入门班 第3讲", queueing: true });
    expect(screen.getByText("📎 来自 · 通用编程入门班 第3讲")).toBeInTheDocument();
    expect(screen.getByText("AI 正在思考…")).toBeInTheDocument();
  });

  it("渲染降级 banner（degrade.error）", () => {
    setup(vi.fn(), {
      degrade: { title: "排队人数较多，已为你降级回答：", detail: "当前咨询人数较多" },
    });
    expect(screen.getByText("排队人数较多，已为你降级回答：")).toBeInTheDocument();
    expect(screen.getByText("当前咨询人数较多")).toBeInTheDocument();
  });
});