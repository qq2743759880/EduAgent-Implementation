# -*- coding: utf-8 -*-
"""P5 math 互动练习 schemas：占位分步检查 + explain。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PracticeQuestion(BaseModel):
    id: str = Field(..., max_length=64)
    title: str = Field(..., max_length=2000, description="可用 LaTeX: $...$ 行内，$$...$$ 块")
    subject_code: str = "math"
    level_code: str = "L2"
    topic: str | None = None
    options: list[dict] = Field(default_factory=list, description="选择/填空可选")
    steps_hint: list[str] = Field(default_factory=list, description="建议解题步骤（占位）")
    answer: str | dict | list | None = Field(default=None, description="标准答案")


class StepCheckIn(BaseModel):
    """某一步的用户输入。step_index 0..N"""
    question_id: str = Field(..., max_length=64)
    step_index: int = Field(..., ge=0, le=20)
    input_text: str = Field(..., max_length=500, description="当前步骤输入，如算式或推导文字")


class StepCheckOut(BaseModel):
    question_id: str
    step_index: int
    passed: bool
    score: float = Field(0.0, ge=0)
    score_max: float = Field(100.0, ge=0)
    feedback: str = Field(..., max_length=1000)
    next_hint: str | None = None


class ExplainIn(BaseModel):
    question_id: str = Field(..., max_length=64)
    wrong_answer: str | None = Field(default=None, max_length=500)


class ExplainOut(BaseModel):
    question_id: str
    solution_steps: list[str]
    final_answer: str
    kp_citations: list[str] = Field(default_factory=list, description="图谱 knowledge codes 对齐 P4")
    llm_provider: str = Field("LOCAL_RULE", description="打靶用本地规则；真实环境可切换 LLM RAG")
