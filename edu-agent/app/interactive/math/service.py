# -*- coding: utf-8 -*-
"""P5 math 占位 service：3 道内置题 + 分步校验（规则） + 讲解（本地规则 + 可选 LLM 回退）。"""
from __future__ import annotations

import re
from fractions import Fraction

from app.common.exceptions import AppException as BizError
from app.interactive.math.schemas import (
    ExplainIn, ExplainOut, PracticeQuestion, StepCheckIn, StepCheckOut,
)


_QUESTIONS: dict[str, PracticeQuestion] = {
    "M-GAUSS-SUM100": PracticeQuestion(
        id="M-GAUSS-SUM100", subject_code="math", level_code="L2",
        topic="高斯求和",
        title="计算：$S = 1 + 2 + 3 + \\cdots + 99 + 100$",
        steps_hint=[
            "步骤 1：发现首项 $a_1 = 1$、末项 $a_n = 100$、项数 $n = 100$。",
            "步骤 2：运用公式 $S = \\dfrac{(a_1 + a_n) \\times n}{2}$。",
            "步骤 3：代入数值得到结果。",
        ],
        answer="5050",
    ),
    "M-QUAD-EQ-X2-5X-6": PracticeQuestion(
        id="M-QUAD-EQ-X2-5X-6", subject_code="math", level_code="L3",
        topic="一元二次方程",
        title="解方程：$x^2 - 5x + 6 = 0$，按从小到大给出 $x_1, x_2$。",
        steps_hint=[
            "步骤 1：因式分解 $x^2-5x+6 \\to (x-a)(x-b)$；$a+b=5$，$ab=6$。",
            "步骤 2：由零乘积定理，分别令 $(x-a)=0$ 与 $(x-b)=0$。",
            "步骤 3：排序 $x_1 \\le x_2$，输出两个解。",
        ],
        answer="x1=2, x2=3",
    ),
    "M-ARITH-MIXED": PracticeQuestion(
        id="M-ARITH-MIXED", subject_code="math", level_code="L1",
        topic="四则混合运算",
        title="计算：$(3 + 4) \\times 2 - 6 \\div 2 = ?$",
        steps_hint=[
            "步骤 1：先算括号：$(3+4)=7$。",
            "步骤 2：算乘除：$7 \\times 2 = 14$，$6 \\div 2 = 3$。",
            "步骤 3：最后加减：$14 - 3$。",
        ],
        answer="11",
    ),
}


def _parse_number(s: str):
    s = (s or "").strip()
    if not s:
        return None
    # 先尝试整串解析（小数 / 分数）
    s_norm = s.replace(",", "").replace(" ", "")
    try:
        return Fraction(s_norm)
    except Exception:
        pass
    # 若混合文本（"答案是 5050"），抓第一次出现的数字
    m = re.search(r"-?\d+(?:\.\d+)?/?\d*", s)
    if m:
        try:
            return Fraction(m.group(0))
        except Exception:
            pass
    # 去除所有非数字/负号/./,/ 字符后再解析
    digits = re.sub(r"[^\d\-./]", "", s)
    if digits:
        try:
            return Fraction(digits)
        except Exception:
            return None
    return None


async def practice(subject_code: str | None = None, level_code: str | None = None,
                   topic: str | None = None, page: int = 1, page_size: int = 10) -> dict:
    items = list(_QUESTIONS.values())
    if level_code:
        items = [q for q in items if q.level_code == level_code]
    if topic:
        items = [q for q in items if q.topic and topic.lower() in q.topic.lower()]
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": [q.model_dump(mode="json") for q in items[start:start + page_size]],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def step_check(payload: StepCheckIn) -> StepCheckOut:
    q = _QUESTIONS.get(payload.question_id)
    if q is None:
        raise BizError(404011, f"未知 question_id={payload.question_id}")
    ans_num = _parse_number(str(payload.input_text))

    # 每一题的分步判定逻辑（占位）
    if payload.question_id == "M-GAUSS-SUM100":
        if payload.step_index == 0:  # 数项数
            ok = any(tok in payload.input_text for tok in ["100", "项数 100", "n=100", "n = 100"])
            score = 100 / 3 if ok else 0
            return StepCheckOut(question_id=q.id, step_index=0, passed=ok,
                                score=score, score_max=100/3,
                                feedback="识别项数=100 ✅" if ok else "项数应该是 100（从 1 到 100 共 100 项）。",
                                next_hint="下一步：代入 S=(首项+末项)*项数/2")
        if payload.step_index == 1:  # 公式应用
            ok = "101" in payload.input_text or "100/2" in payload.input_text
            return StepCheckOut(question_id=q.id, step_index=1, passed=ok,
                                score=(100/3 if ok else 0), score_max=100/3,
                                feedback="(1+100)=101，×100÷2 思路正确 ✅" if ok else "套公式：S=(1+100)*100/2")
        if payload.step_index >= 2:  # 最终答案
            correct = ans_num is not None and ans_num == 5050
            score = 100 / 3 if correct else 0
            return StepCheckOut(question_id=q.id, step_index=payload.step_index,
                                passed=correct, score=score, score_max=100/3,
                                feedback="最终结果 5050 ✅" if correct else "最终答案应为 5050。",
                                next_hint=None)

    if payload.question_id == "M-QUAD-EQ-X2-5X-6":
        if payload.step_index == 0:  # 分解
            ok = "(x-2)" in payload.input_text.replace(" ", "") and "(x-3)" in payload.input_text.replace(" ", "")
            return StepCheckOut(question_id=q.id, step_index=0, passed=ok,
                                score=(33 if ok else 0), score_max=33,
                                feedback="因式分解 (x-2)(x-3) 正确 ✅" if ok else "提示：6 可拆为 2×3，2+3=5；注意符号。")
        if payload.step_index == 1:  # 各自为 0
            ok = "x=2" in payload.input_text.lower().replace(" ", "") or "x=3" in payload.input_text.lower().replace(" ", "")
            return StepCheckOut(question_id=q.id, step_index=1, passed=ok,
                                score=(33 if ok else 0), score_max=33,
                                feedback="分别令因子为 0 得到解 ✅" if ok else "由零乘积定理：x-2=0 → x=2；x-3=0 → x=3。")
        if payload.step_index >= 2:
            ok = all(tok in payload.input_text for tok in ("2", "3")) and (
                "x1" in payload.input_text.lower() or payload.input_text.count(",") >= 1
            )
            return StepCheckOut(question_id=q.id, step_index=payload.step_index,
                                passed=ok, score=(34 if ok else 0), score_max=34,
                                feedback="排序解 x1=2, x2=3 ✅" if ok else "最后两解按序输出：x1=2, x2=3")

    if payload.question_id == "M-ARITH-MIXED":
        if payload.step_index == 0:
            ok = ans_num is not None and ans_num == 7 or "(7)" in payload.input_text or "=7" in payload.input_text
            return StepCheckOut(question_id=q.id, step_index=0, passed=ok,
                                score=(33 if ok else 0), score_max=33,
                                feedback="括号结果 7 ✅" if ok else "先括号：3+4=7。")
        if payload.step_index == 1:
            ok = "14" in payload.input_text and "3" in payload.input_text
            return StepCheckOut(question_id=q.id, step_index=1, passed=ok,
                                score=(33 if ok else 0), score_max=33,
                                feedback="7×2=14, 6÷2=3 ✅" if ok else "乘除 7×2=14 与 6÷2=3 分别计算。")
        if payload.step_index >= 2:
            ok = ans_num is not None and ans_num == 11
            return StepCheckOut(question_id=q.id, step_index=payload.step_index, passed=ok,
                                score=(34 if ok else 0), score_max=34,
                                feedback="14-3=11，最终正确 ✅" if ok else "最后 14-3 = 11。")

    raise BizError(400011, f"未知 question_id/step_index={payload.question_id}/{payload.step_index}")


async def explain(payload: ExplainIn) -> ExplainOut:
    q = _QUESTIONS.get(payload.question_id)
    if q is None:
        raise BizError(404012, f"未知 question_id={payload.question_id}")
    citations: list[str] = []
    if q.id == "M-GAUSS-SUM100":
        citations = ["KP-MATH-ARITH-GAUSS"]
        steps = [
            "首项 a₁ = 1，末项 aₙ = 100，项数 n = 100。",
            "套用高斯求和公式 S = (a₁ + aₙ) × n ÷ 2 = (1+100)×100÷2。",
            "(1+100)=101；101×100=10100；10100÷2=5050。",
            "答：S = 5050。",
        ]
    elif q.id == "M-QUAD-EQ-X2-5X-6":
        citations = ["KP-MATH-EQ-QUAD-FACTOR"]
        steps = [
            "x²-5x+6 十字相乘：6=(-2)×(-3)，(-2)+(-3)=-5 ⇒ (x-2)(x-3)。",
            "由零乘积定理：x-2=0 或 x-3=0 ⇒ x=2 或 x=3。",
            "按序：x₁=2, x₂=3。",
        ]
    else:
        citations = ["KP-MATH-ARITH-OPORDER"]
        steps = [
            "括号优先：(3+4)=7。",
            "乘除：7×2=14；6÷2=3。",
            "加减：14-3=11。",
        ]
    if payload.wrong_answer:
        steps.insert(0, f"检测到你的作答：{payload.wrong_answer} —— 请对照步骤检查，常见错误是「忽略括号优先」或「乘除顺序反了」。")
    return ExplainOut(
        question_id=q.id,
        solution_steps=steps,
        final_answer=str(q.answer),
        kp_citations=citations,
        llm_provider="LOCAL_RULE",
    )
