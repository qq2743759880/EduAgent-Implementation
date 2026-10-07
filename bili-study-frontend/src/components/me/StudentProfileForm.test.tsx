/**
 * StudentProfileForm 单测：加载回显学校；保存调 PUT /me/profile 且 toast 成功；
 * 接口失败显示错误态。契约⑤ 现状：仅 school_name 可写（见 me.ts 注释）。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  StudentProfileForm,
} from "./StudentProfileForm";
import { getStudentProfile, updateProfile, type StudentProfileRow } from "@/lib/api/me";

vi.mock("@/lib/api/me", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/me")>("@/lib/api/me");
  return { ...actual, getStudentProfile: vi.fn(), updateProfile: vi.fn() };
});

const toastSpies = { success: vi.fn(), error: vi.fn() };
vi.mock("sonner", () => ({
  toast: { success: (...a: unknown[]) => (toastSpies.success as unknown as (...x: unknown[]) => void)(...a), error: (...a: unknown[]) => (toastSpies.error as unknown as (...x: unknown[]) => void)(...a) },
}));

const mockGetProf = vi.mocked(getStudentProfile);
const mockUpdate = vi.mocked(updateProfile);

function makeRow(): StudentProfileRow {
  return {
    user_id: 1,
    learner_identity_id: 2,
    school_name: "市第一中学",
    industry_name: "软件与信息技术",
    job_role_name: "前端开发工程师",
    years_of_experience: "1-3 年",
  };
}

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StudentProfileForm />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("StudentProfileForm", () => {
  it("加载后回显学校/行业/岗位/工作年限", async () => {
    mockGetProf.mockResolvedValue(makeRow());
    renderForm();
    expect(await screen.findByDisplayValue("市第一中学")).toBeInTheDocument();
    expect(screen.getByDisplayValue("软件与信息技术")).toBeInTheDocument();
    expect(screen.getByDisplayValue("前端开发工程师")).toBeInTheDocument();
    expect(screen.getByDisplayValue("1-3 年")).toBeInTheDocument();
  });

  it("保存：仅提交 UserProfile 可写字段 school_name 并 toast 成功", async () => {
    const user = userEvent.setup();
    mockGetProf.mockResolvedValue(makeRow());
    mockUpdate.mockResolvedValue({});
    renderForm();
    await screen.findByDisplayValue("市第一中学");
    await user.click(screen.getByRole("button", { name: /保存档案/ }));
    expect(mockUpdate).toHaveBeenCalledWith({ school_name: "市第一中学" });
    expect(toastSpies.success).toHaveBeenCalledWith("档案已保存");
  });

  it("接口失败显示错误态而非空表单", async () => {
    mockGetProf.mockRejectedValue(new Error("500"));
    renderForm();
    expect(await screen.findByText(/档案加载失败/)).toBeInTheDocument();
    expect(screen.queryByText("保存档案")).not.toBeInTheDocument();
  });
});