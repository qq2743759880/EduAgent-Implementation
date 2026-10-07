/**
 * lib/api/admin/questions.ts 单测（task03）
 * 验证：题型枚举（后端权威：single_choice/multi_choice/...）与中文 label 映射。
 *
 * W-NEXT-FEBE-SCAN-002（2026-09-18）：题目集合真实路由是 /api/admin/questions/questions
 * （OpenAPI 实测对账）；旧断言的 /api/admin/questions(/{id}) 后端从未注册（404 断点）。
 *
 * W-NEXT-QUESTIONFORM-FIX-001（2026-09-18）：legacy QuestionForm + 死封装
 * createQuestion/updateQuestion 已整体删除（全仓库 grep 零挂载零活 import），
 * 对应的 body 契约测试同步删除；题目写操作唯一入口 = question-bank.ts
 * （见 question-bank.test.ts）。
 */
import { describe, expect, it } from "vitest";
import { QUESTION_TYPE_OPTIONS, questionTypeLabel } from "./questions";

describe("题型枚举（后端契约，非 design-guide 摘要）", () => {
  it("5 个后端枚举值", () => {
    expect(QUESTION_TYPE_OPTIONS.map((t) => t.value)).toEqual([
      "single_choice",
      "multi_choice",
      "true_false",
      "fill_blank",
      "short_answer",
    ]);
  });

  it("questionTypeLabel 映射中文", () => {
    expect(questionTypeLabel("single_choice")).toBe("单选题");
    expect(questionTypeLabel("true_false")).toBe("判断题");
    expect(questionTypeLabel("unknown")).toBe("unknown");
  });
});
