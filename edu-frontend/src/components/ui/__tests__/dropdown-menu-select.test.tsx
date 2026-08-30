/**
 * DropdownMenu(C11) / Select(C12) 单测。
 *  popup 在 jsdom 无真实布局（measurement 受限），故冒烟聚焦：trigger 语义与受控展开基础，
 *  完整定位/焦点测试交由 fe-tester 在真实浏览器端验证。
 *  a11y：trigger role + aria-haspopup / aria-expanded；select error role=alert。
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../dropdown-menu";
import { Select } from "../select";
import { Button } from "../button";

describe("C11 DropdownMenu", () => {
  it("trigger 渲染 + aria-haspopup（行操作入口语义）", () => {
    render(
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="outline" size="sm" />}>操作</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onClick={() => {}}>编辑</DropdownMenuItem>
          <DropdownMenuItem destructive onClick={() => {}}>删除</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    const trigger = screen.getByRole("button", { name: "操作" });
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    // 初始关闭：菜单项不在可访问树（jsdom 不展开定位，留浏览器端验证展开）
    expect(screen.queryByText("编辑")).not.toBeInTheDocument();
  });
});

const OPTIONS = [
  { value: "online_live", label: "在线直播" },
  { value: "online_recorded", label: "在线录播" },
  { value: "offline_face_to_face", label: "线下面授" },
];

describe("C12 Select", () => {
  it("渲染 label + placeholder（受控 value 为空）", () => {
    render(<Select label="交付模式" options={OPTIONS} value={null} onValueChange={() => {}} />);
    expect(screen.getByText("交付模式")).toBeInTheDocument();
    expect(screen.getByText("请选择")).toBeInTheDocument();
  });

  it("受控 value 展示选中项 label 且 trigger 带 aria-expanded", () => {
    render(<Select label="交付模式" options={OPTIONS} value="online_live" onValueChange={() => {}} />);
    // Base UI Select trigger 语义角色为 combobox；选中值渲染进 trigger
    const trigger = screen.getByRole("combobox", { name: /交付模式/ });
    expect(within(trigger).getByText("在线直播")).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("disabled 时 trigger 禁用", () => {
    render(<Select label="交付模式" options={OPTIONS} value={null} disabled onValueChange={() => {}} />);
    expect(screen.getByRole("combobox", { name: /交付模式/ })).toBeDisabled();
  });

  it("error 展示错误信息（role=alert，不吞错）", () => {
    render(
      <Select
        label="交付模式"
        options={OPTIONS}
        value={null}
        error="请选择交付模式"
        onValueChange={() => {}}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("请选择交付模式");
    // aria-invalid 打到 trigger
    expect(screen.getByRole("combobox", { name: /交付模式/ })).toHaveAttribute("aria-invalid", "true");
  });

  it("必填项 label 带 * 标记", () => {
    render(<Select label="交付模式" options={OPTIONS} value={null} required onValueChange={() => {}} />);
    expect(screen.getByText("*")).toBeInTheDocument();
  });
});