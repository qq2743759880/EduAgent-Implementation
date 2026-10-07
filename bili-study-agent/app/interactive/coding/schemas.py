# -*- coding: utf-8 -*-
"""P5 coding schemas：挑战题 / 运行 / 提交 / Hint。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Challenge(BaseModel):
    id: int | None = None
    code: str = Field(..., max_length=64)
    title: str
    level_code: str = "L2"
    lang_code: str = Field(..., pattern=r"^(python|javascript|java|cpp)$")
    prompt: str
    starter_code: str | None = None
    test_cases_sample: list[dict] = Field(
        default_factory=list, description="对外暴露的非隐藏用例（含 expected），打靶默认前 2 个",
    )
    tags: list[str] = Field(default_factory=list)
    points: int = Field(default=100, ge=0)


class RunIn(BaseModel):
    """运行（只跑 sample 非隐藏用例）。"""
    challenge_code: str = Field(..., max_length=64)
    lang_code: str
    code_text: str = Field(..., min_length=1)


class SubmitIn(BaseModel):
    """提交（跑全量含隐藏）。"""
    challenge_code: str = Field(..., max_length=64)
    lang_code: str
    code_text: str = Field(..., min_length=1)


class CaseResult(BaseModel):
    index: int
    input: str
    expected: str | None = None
    actual: str | None = None
    is_hidden: bool = False
    passed: bool
    stdout: str | None = None
    stderr: str | None = None
    runtime_ms: int | None = None


class RunSubmitOut(BaseModel):
    submission_id: int
    status: str = Field(..., description="Pending/Running/Pass/PartialFail/CompileError/RuntimeError/SandboxError")
    pass_count: int
    total_count: int
    score: int = Field(0, ge=0, description="pass_count / total_count × points 四舍五入")
    results: list[CaseResult]
    duration_ms: int | None = None
    sandbox_provider: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class HintIn(BaseModel):
    challenge_code: str
    step: int = Field(default=1, ge=1, le=5, description="第几条 hint，步长递进 不直接给答案")
    code_snapshot: str | None = Field(default=None, description="当前用户代码片段，用于 LLM 定向提示")


class HintOut(BaseModel):
    challenge_code: str
    step: int
    next_step_available: bool
    text: str = Field(..., max_length=2000, description="递进式提示：step 1 读题思路 → step 2 伪代码 → step 3 易错点；step 5 前不允许直接给完整代码")
    provider: str = Field("LOCAL_RULE", description="打靶默认本地规则；生产可换 LLM")
