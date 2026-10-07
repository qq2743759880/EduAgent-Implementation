/**
 * Accordion(C13) 单测：
 *  - trigger 展开/折叠（aria-expanded 切换 + 内容显隐）
 *  - 受控 value / onValueChange 回传
 *  a11y：trigger role=button + aria-expanded
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Accordion, AccordionItem, AccordionPanel, AccordionTrigger } from "../accordion";

describe("C13 Accordion", () => {
  it("初始折叠：trigger aria-expanded=false，面板内容不挂载", () => {
    render(
      <Accordion>
        <AccordionItem value="1">
          <AccordionTrigger>第一章</AccordionTrigger>
          <AccordionPanel>Python 基础</AccordionPanel>
        </AccordionItem>
      </Accordion>,
    );
    expect(screen.getByText("第一章")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "第一章" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Python 基础")).not.toBeInTheDocument();
  });

  it("点击展开：aria-expanded=true 且内容挂载", async () => {
    const user = userEvent.setup();
    render(
      <Accordion>
        <AccordionItem value="1">
          <AccordionTrigger>第一章</AccordionTrigger>
          <AccordionPanel>Python 基础</AccordionPanel>
        </AccordionItem>
      </Accordion>,
    );
    const trigger = screen.getByRole("button", { name: "第一章" });
    await user.click(trigger);
    expect(screen.getByText("Python 基础")).toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "true");
  });

  it("受控 value + onValueChange 回传展开值", async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    render(
      <Accordion value={[]} onValueChange={onValueChange}>
        <AccordionItem value="a">
          <AccordionTrigger>模块 A</AccordionTrigger>
          <AccordionPanel>内容 A</AccordionPanel>
        </AccordionItem>
        <AccordionItem value="b">
          <AccordionTrigger>模块 B</AccordionTrigger>
          <AccordionPanel>内容 B</AccordionPanel>
        </AccordionItem>
      </Accordion>,
    );
    await user.click(screen.getByRole("button", { name: "模块 B" }));
    expect(onValueChange).toHaveBeenCalledWith(expect.arrayContaining(["b"]), expect.anything());
  });
});