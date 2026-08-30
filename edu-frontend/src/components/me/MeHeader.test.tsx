/**
 * MeHeader 单测：昵称/学习目标/偏好标签渲染；接口失败显示错误态而非空兜底。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MeHeader } from "./MeHeader";
import { getMe, type MeHead } from "@/lib/api/me";

vi.mock("@/lib/api/me", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/me")>("@/lib/api/me");
  return { ...actual, getMe: vi.fn() };
});

const mockGetMe = vi.mocked(getMe);

function makeHead(): MeHead {
  return {
    id: 1,
    nickname: "慕剑知",
    learningGoal: "编程入门",
    subjectPreferences: ["programming", "math"],
  };
}

function renderHeader() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MeHeader />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("MeHeader", () => {
  it("渲染昵称、学习目标与偏好标签（code→中文）", async () => {
    mockGetMe.mockResolvedValue(makeHead());
    renderHeader();
    expect(await screen.findByText("慕剑知")).toBeInTheDocument();
    expect(screen.getByText(/学习目标：/)).toBeInTheDocument();
    expect(screen.getByText("编程入门")).toBeInTheDocument();
    expect(screen.getByText("编程")).toBeInTheDocument();
    expect(screen.getByText("数学")).toBeInTheDocument();
  });

  it("接口失败显示错误态而非空头像/空昵称兜底", async () => {
    mockGetMe.mockRejectedValue(new Error("500"));
    renderHeader();
    expect(await screen.findByText(/个人资料加载失败/)).toBeInTheDocument();
    expect(screen.queryByText("慕剑知")).not.toBeInTheDocument();
  });
});