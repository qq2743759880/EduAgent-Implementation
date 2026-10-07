/**
 * task48 学习播放页组件单测：
 *  - HomeworkPanel：空作答拦截（toast.error）→ 提交调用 submitHomework(detail_payload)；已判分渲染
 *  - ExamPanel：durationMinutes 倒计时展示；交卷调用 submitExam
 *  - LearningTabs：视频/作业/考试三 Tab + 默认展开视频（课程简介）
 *  - SyllabusPanel：空大纲占位；模块/课次渲染 + 当前课 aria-current=page + 完成计数
 *  - LearningToolbar：AI 提问 → /chat?context=session:{id}；错题本 → /practice?from_session={id}
 * API 全部 vi.mock，sonner toast 隔离。
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { toast } from "sonner";
import { submitHomework, submitExam } from "@/lib/api/learning";
import { HomeworkPanel } from "./HomeworkPanel";
import { ExamPanel } from "./ExamPanel";
import { LearningTabs } from "./LearningTabs";
import { SyllabusPanel } from "./SyllabusPanel";
import { LearningToolbar } from "./LearningToolbar";
import type { StudyOutline } from "@/lib/api/study";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/lib/api/learning", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/learning")>();
  return { ...actual, submitHomework: vi.fn(), submitExam: vi.fn() };
});

const submitHomeworkMock = vi.mocked(submitHomework);
const submitExamMock = vi.mocked(submitExam);

beforeEach(() => {
  vi.clearAllMocks();
});

/* ---------- HomeworkPanel ---------- */
describe("HomeworkPanel", () => {
  it("空作答：拦截提交并 toast.error，不调用 submitHomework", async () => {
    const user = userEvent.setup();
    render(<HomeworkPanel seriesId={1001} sessionId={55} />);
    await user.click(screen.getByRole("button", { name: /提交判断/ }));
    expect(toast.error).toHaveBeenCalledWith("请先填写作业作答内容");
    expect(submitHomeworkMock).not.toHaveBeenCalled();
  });

  it("填写后提交：调用 submitHomework({series_id, session_id, title:null, detail_payload}) 并展示已提交", async () => {
    const user = userEvent.setup();
    submitHomeworkMock.mockResolvedValue({ saved: true });
    render(<HomeworkPanel seriesId={1001} sessionId={55} />);
    await user.type(screen.getByRole("textbox", { name: "作业作答内容" }), "我的作答");
    await user.click(screen.getByRole("button", { name: /提交判断/ }));
    expect((await screen.findAllByText("已提交")).length).toBeGreaterThanOrEqual(1);
    expect(submitHomeworkMock).toHaveBeenCalledTimes(1);
    const arg = submitHomeworkMock.mock.calls[0][0];
    expect(arg.series_id).toBe(1001);
    expect(arg.session_id).toBe(55);
    expect(arg.homework_title).toBeNull();
    expect(arg.detail_payload).toEqual({ text: "我的作答" });
  });

  it("existingJudge 渲染判分（占比 + 通过态）", () => {
    render(
      <HomeworkPanel
        seriesId={1001}
        sessionId={55}
        existingJudge={{ score_earned: 8, score_total: 10, passed: true }}
      />,
    );
    expect(screen.getByText("80 分")).toBeInTheDocument();
    expect(screen.getByText("已通过")).toBeInTheDocument();
  });
});

/* ---------- ExamPanel ---------- */
describe("ExamPanel", () => {
  it("交卷：调用 submitExam({series_id, session_id}) 并展示已交卷", async () => {
    const user = userEvent.setup();
    submitExamMock.mockResolvedValue({ saved: true });
    render(<ExamPanel seriesId={1001} sessionId={55} />);
    await user.click(screen.getByRole("button", { name: /交卷/ }));
    expect((await screen.findAllByText("已交卷")).length).toBeGreaterThanOrEqual(1);
    expect(submitExamMock).toHaveBeenCalledTimes(1);
    const arg = submitExamMock.mock.calls[0][0];
    expect(arg.series_id).toBe(1001);
    expect(arg.session_id).toBe(55);
  });

  it("durationMinutes 存在时展示剩余时间倒计时", () => {
    render(<ExamPanel seriesId={1001} sessionId={55} durationMinutes={1} />);
    expect(screen.getByText(/01:00/)).toBeInTheDocument();
  });
});

/* ---------- LearningTabs ---------- */
describe("LearningTabs", () => {
  it("渲染 视频/作业/考试 三 Tab，默认选中视频（课程简介）", () => {
    render(<LearningTabs seriesId={1001} sessionId={55} />);
    expect(screen.getByRole("tab", { name: /视频/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /作业/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /考试/ })).toBeInTheDocument();
    expect(screen.getByText("课程简介")).toBeInTheDocument();
  });
});

/* ---------- SyllabusPanel ---------- */
describe("SyllabusPanel", () => {
  const outline: StudyOutline = {
    series_id: 1001,
    series_title: "通用编程入门班",
    overall_ratio: 0.5,
    total_sessions: 2,
    completed_sessions: 1,
    modules: [
      {
        module_id: 21,
        module_title: "语法基础",
        module_no: 1,
        overall_ratio: 0.5,
        sessions: [
          {
            session_id: 55,
            session_title: "变量与类型",
            session_no: 1,
            duration_minutes: 90,
            video_url: null,
            watch_ratio: 1,
            homework_done: true,
          },
          {
            session_id: 56,
            session_title: "条件分支",
            session_no: 2,
            duration_minutes: 90,
            video_url: null,
            watch_ratio: 0,
            homework_done: false,
          },
        ],
      },
    ],
  };

  it("空大纲渲染占位", () => {
    render(<SyllabusPanel seriesId={1001} currentSessionId={56} outline={null} />);
    expect(screen.getByText(/大纲待后端生成/)).toBeInTheDocument();
  });

  it("渲染模块/课次，当前课 aria-current=page，完成计数=1/2", () => {
    render(<SyllabusPanel seriesId={1001} currentSessionId={56} outline={outline} />);
    expect(screen.getByText("语法基础")).toBeInTheDocument();
    expect(screen.getByText(/01 变量与类型/)).toBeInTheDocument();
    expect(screen.getByText(/02 条件分支/)).toBeInTheDocument();
    const current = screen.getByRole("link", { name: /02 条件分支/ });
    expect(current).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("1/2")).toBeInTheDocument();
  });
});

/* ---------- LearningToolbar ---------- */
describe("LearningToolbar", () => {
  it("AI 提问 → /chat?context=session:{id}；错题本 → /practice?from_session={id}", () => {
    render(<LearningToolbar seriesId={1001} sessionId={55} />);
    expect(screen.getByRole("link", { name: /AI 提问/ })).toHaveAttribute(
      "href",
      "/chat?context=session:55",
    );
    expect(screen.getByRole("link", { name: /错题本/ })).toHaveAttribute(
      "href",
      "/practice?from_session=55",
    );
  });
});