/**
 * Uploader(C5) 单测：
 *  - 点击/选择文件 → 校验（accept 由浏览器 + maxSize JS 校验）→ onFiles / onReject
 *  - 上传项明细渲染（progress/error）+ 移除 onRemove
 *  a11y：上传区 role=button + aria-label；文件列表带 aria-label
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Uploader, type UploadItem } from "../uploader";

function makeFile(name = "syllabus.pdf", size = 1024, type = "application/pdf") {
  return new File([new Uint8Array(size)], name, { type });
}

describe("C5 Uploader · 校验与回调", () => {
  it("选择文件 → onFiles 回调（校验通过）", async () => {
    const user = userEvent.setup();
    const onFiles = vi.fn();
    const { container } = render(<Uploader onFiles={onFiles} />);
    const input = container.querySelector<HTMLInputElement>("input[type='file']");
    expect(input).not.toBeNull();
    await user.upload(input!, [makeFile()]);
    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0]).toHaveLength(1);
  });

  it("超过 maxSize → onReject reason=size（不吞错）", async () => {
    const user = userEvent.setup();
    const onFiles = vi.fn();
    const onReject = vi.fn();
    const { container } = render(
      <Uploader maxSize={512} onFiles={onFiles} onReject={onReject} />,
    );
    const input = container.querySelector<HTMLInputElement>("input[type='file']");
    await user.upload(input!, [makeFile("big.docx", 2048)]);
    expect(onFiles).not.toHaveBeenCalled();
    expect(onReject).toHaveBeenCalledWith([
      expect.objectContaining({ reason: "size" }),
    ]);
  });

  it("超 maxFiles → onReject reason=count", async () => {
    const user = userEvent.setup();
    const onReject = vi.fn();
    const onFiles = vi.fn();
    const { container } = render(
      <Uploader maxFiles={1} multiple onFiles={onFiles} onReject={onReject} />,
    );
    const input = container.querySelector<HTMLInputElement>("input[type='file']");
    await user.upload(input!, [makeFile("a.txt", 10, "text/plain"), makeFile("b.txt", 10, "text/plain")]);
    expect(onFiles).not.toHaveBeenCalled();
    expect(onReject).toHaveBeenCalled();
    expect(onReject.mock.calls[0][0].every((r: { reason: string }) => r.reason === "count")).toBe(true);
  });
});

describe("C5 Uploader · 明细与 a11y", () => {
  it("上传区 role=button 带 aria-label", () => {
    render(<Uploader label="上传视频" />);
    expect(screen.getByRole("button", { name: "上传视频" })).toBeInTheDocument();
  });

  it("渲染上传项（uploading 进度 / error 明细）", () => {
    const items: UploadItem[] = [
      { name: "a.mp4", size: 2048 * 1024, status: "uploading", percent: 45 },
      { name: "b.mp4", size: 1024, status: "error", error: "分片校验失败" },
      { name: "c.mp4", size: 1024, status: "done" },
    ];
    render(<Uploader value={items} />);
    expect(screen.getByText("a.mp4")).toBeInTheDocument();
    expect(screen.getByText("45%")).toBeInTheDocument();
    expect(screen.getByText("分片校验失败")).toBeInTheDocument();
    expect(screen.getByText("b.mp4")).toBeInTheDocument();
    expect(screen.getByText("已就绪")).toBeInTheDocument();
  });

  it("移除按钮回调 onRemove(item,index)", async () => {
    const user = userEvent.setup();
    const onRemove = vi.fn();
    const items: UploadItem[] = [{ name: "a.mp4", size: 1024 }];
    render(<Uploader value={items} onRemove={onRemove} />);
    await user.click(screen.getByRole("button", { name: "移除 a.mp4" }));
    expect(onRemove).toHaveBeenCalledWith(items[0], 0);
  });

  it("禁用态：上传区 aria-disabled 且不可交互", async () => {
    const user = userEvent.setup();
    const onFiles = vi.fn();
    render(<Uploader onFiles={onFiles} disabled />);
    const zone = screen.getByRole("button", { name: "点击选择或拖拽文件到此处" });
    expect(zone).toHaveAttribute("aria-disabled", "true");
    await user.click(zone);
    expect(onFiles).not.toHaveBeenCalled();
  });
});