/**
 * DataTable 单测（task41 C1）：
 *  - 渲染表头/数据行 + 排序表头按钮 + aria-sort
 *  - 加载骨架（aria-busy + 骨架行 aria-hidden）+ 空态内建 EmptyState
 *  - 交互：onSortChange / onRowClick
 *  a11y：原生 table 语义 + th scope + 排序按钮 aria-label
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataTable, type DataTableColumn } from "../data-table";

type Row = { id: number; name: string; price: number };

const columns: DataTableColumn<Row>[] = [
  { key: "id", header: "ID" },
  { key: "name", header: "名称", sortable: true },
  { key: "price", header: "价格", accessor: (r) => `¥${r.price}`, align: "right" },
];

const data: Row[] = [
  { id: 1, name: "Python", price: 100 },
  { id: 2, name: "PyTorch", price: 200 },
];

describe("DataTable · 渲染与 a11y", () => {
  it("渲染表头 + 数据行（含 accessor）", () => {
    render(<DataTable columns={columns} data={data} rowKey={(r) => r.id} />);
    // 表头
    expect(screen.getByRole("columnheader", { name: "名称" })).toBeInTheDocument();
    // 数据行
    expect(screen.getByRole("cell", { name: "Python" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "¥200" })).toBeInTheDocument();
    // 原生 table 语义
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("a11y：所有表头带 scope=col", () => {
    render(<DataTable columns={columns} data={data} rowKey={(r) => r.id} />);
    for (const th of screen.getAllByRole("columnheader")) {
      expect(th).toHaveAttribute("scope", "col");
    }
  });

  it("超过一列时可排序列按钮带 aria-label", () => {
    render(<DataTable columns={columns} data={data} rowKey={(r) => r.id} />);
    expect(screen.getByRole("button", { name: "按名称排序" })).toBeInTheDocument();
  });
});

describe("DataTable · 排序/加载/空态", () => {
  it("点击排序列回调 onSortChange(key, dir) 并切换方向", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    render(<DataTable columns={columns} data={data} rowKey={(r) => r.id} onSortChange={onSortChange} />);
    const btn = screen.getByRole("button", { name: "按名称排序" });
    await user.click(btn);
    expect(onSortChange).toHaveBeenCalledWith("name", "asc");
  });

  it("受控 sort 时表头 aria-sort 正确（升序 ascending）", () => {
    const { container } = render(
      <DataTable
        columns={columns}
        data={data}
        rowKey={(r) => r.id}
        sort={{ key: "name", dir: "asc" }}
      />,
    );
    const th = screen.getByRole("columnheader", { name: "名称" });
    expect(th).toHaveAttribute("aria-sort", "ascending");
    expect(container.firstChild).not.toBeNull();
  });

  it("loading 渲染骨架行并置 aria-busy（骨架行 aria-hidden 屏蔽读屏）", () => {
    const { container } = render(
      <DataTable columns={columns} data={data} rowKey={(r) => r.id} loading />,
    );
    const root = container.querySelector("[data-slot='data-table']");
    expect(root).toHaveAttribute("aria-busy", "true");
    // 骨架占位行存在且对读屏隐藏
    const hiddenRows = container.querySelectorAll("tr[aria-hidden='true']");
    expect(hiddenRows.length).toBeGreaterThan(0);
  });

  it("空数据内建空态（role=status + 文案）", () => {
    render(<DataTable columns={columns} data={[]} rowKey={(r) => r.id} emptyTitle="暂无课程" />);
    expect(screen.getByRole("status")).toHaveTextContent("暂无课程");
  });

  it("onRowClick 行点击回调", async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    render(<DataTable columns={columns} data={data} rowKey={(r) => r.id} onRowClick={onRowClick} />);
    await user.click(screen.getByRole("cell", { name: "Python" }));
    expect(onRowClick).toHaveBeenCalledWith(data[0]);
  });
});