/**
 * CourseSearchInput 单测（task44，防抖 400ms）：
 *  - 输入停止 400ms 后回调（trim 后提交）
 *  - 400ms 内不触发（防抖重置）
 *  - 清空按钮立即回调空串 + 清空输入框
 * 用 fireEvent.change（同步）+ fake timers，避免 userEvent 内部定时器与防抖定时器互相挂起。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { CourseSearchInput } from "./CourseSearchInput";

afterEach(() => {
  vi.useRealTimers();
});

describe("CourseSearchInput · 防抖 400ms", () => {
  it("输入停止 400ms 后回调 trim 值；400ms 内不触发", () => {
    vi.useFakeTimers();
    const onDebouncedChange = vi.fn();
    render(<CourseSearchInput value="" onDebouncedChange={onDebouncedChange} />);

    const input = screen.getByRole("textbox", { name: "搜索课程" });
    fireEvent.change(input, { target: { value: "  python  " } });

    // 输入后 <400ms 不触发
    vi.advanceTimersByTime(200);
    expect(onDebouncedChange).not.toHaveBeenCalled();

    // 满 400ms 后触发一次（trim）
    vi.advanceTimersByTime(200);
    expect(onDebouncedChange).toHaveBeenCalledTimes(1);
    expect(onDebouncedChange).toHaveBeenCalledWith("python");
  });

  it("连续输入重置防抖：最后一次输入后 400ms 才回调", () => {
    vi.useFakeTimers();
    const onDebouncedChange = vi.fn();
    render(<CourseSearchInput value="" onDebouncedChange={onDebouncedChange} />);

    const input = screen.getByRole("textbox", { name: "搜索课程" });
    fireEvent.change(input, { target: { value: "py" } });
    vi.advanceTimersByTime(300); // 接近但未到 400ms
    fireEvent.change(input, { target: { value: "python" } });
    vi.advanceTimersByTime(300); // 距最后一次输入 300ms
    expect(onDebouncedChange).not.toHaveBeenCalled();
    vi.advanceTimersByTime(100); // 满 400ms
    expect(onDebouncedChange).toHaveBeenCalledTimes(1);
    expect(onDebouncedChange).toHaveBeenCalledWith("python");
  });

  it("清空按钮：立即回调空串并清空输入框", () => {
    vi.useFakeTimers();
    const onDebouncedChange = vi.fn();
    render(<CourseSearchInput value="" onDebouncedChange={onDebouncedChange} />);

    const input = screen.getByRole("textbox", { name: "搜索课程" });
    fireEvent.change(input, { target: { value: "abc" } });
    vi.advanceTimersByTime(400);
    expect(onDebouncedChange).toHaveBeenLastCalledWith("abc");

    fireEvent.click(screen.getByRole("button", { name: "清空搜索" }));
    expect(onDebouncedChange).toHaveBeenLastCalledWith("");
    expect(input).toHaveValue("");
  });
});
