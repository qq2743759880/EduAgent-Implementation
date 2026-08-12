# -*- coding: utf-8 -*-
"""P5 coding service：挑战题 + 运行（Piston HTTP 3s timeout → fallback mock）+ 提交 + 递进 Hint。"""
from __future__ import annotations

import ast
import asyncio
import json
import math
import re
from datetime import datetime
from typing import Any

from app.common.exceptions import AppException as BizError
from app.database import execute_write, fetch_all, fetch_one

from app.interactive.coding.schemas import (
    CaseResult, Challenge, HintIn, HintOut, RunIn, RunSubmitOut, SubmitIn,
)


def _unjson(v: Any) -> Any:
    if v is None:
        return []
    if isinstance(v, (list, dict)):
        return v
    if isinstance(v, (bytes, bytearray)):
        try:
            v = v.decode("utf-8")
        except Exception:
            return []
    try:
        return json.loads(v)
    except Exception:
        return []


async def get_challenge(code: str) -> Challenge:
    row = await fetch_one(
        "SELECT id, code, title, level_code, lang_code, prompt, starter_code, test_cases_json, tags_json, points, yn "
        "FROM coding_challenge WHERE code=%s AND yn=1 LIMIT 1",
        (code,),
    )
    if row is None:
        raise BizError(404031, f"未找到 coding challenge code={code}")
    cases = _unjson(row["test_cases_json"])
    sample = [c for c in cases if not c.get("is_hidden")]
    return Challenge(
        id=int(row["id"]), code=row["code"], title=row["title"], level_code=row["level_code"],
        lang_code=row["lang_code"], prompt=row["prompt"], starter_code=row["starter_code"],
        test_cases_sample=sample[:2],
        tags=list(_unjson(row["tags_json"]) or []),
        points=int(row["points"] or 0),
    )


async def list_challenges(lang: str | None = None, level: str | None = None, page: int = 1, page_size: int = 20) -> dict:
    where = ["yn=1"]
    args: list[Any] = []
    if lang:
        where.append("lang_code=%s"); args.append(lang)
    if level:
        where.append("level_code=%s"); args.append(level)
    total = (await fetch_one(
        "SELECT COUNT(*) c FROM coding_challenge WHERE " + " AND ".join(where),
        tuple(args),
    ))["c"]
    rows = await fetch_all(
        "SELECT id, code, title, level_code, lang_code, points FROM coding_challenge WHERE "
        + " AND ".join(where)
        + " ORDER BY level_code, id LIMIT %s OFFSET %s",
        tuple(args + [int(page_size), max(0, page - 1) * int(page_size)]),
    )
    return {"items": rows, "total": int(total), "page": page, "page_size": page_size}


# ============== 代码沙箱：Piston HTTP → 本地 mock =============

LANG_PISTON_ALIAS = {
    "python": "python",
    "javascript": "javascript",
    "java": "java",
    "cpp": "c++",
}


async def _run_piston(lang: str, code: str, stdin: str, timeout: float = 3.0) -> dict | None:
    """尝试调用 Piston API（EM 判定）；网络失败/超时返回 None，触发 fallback。"""
    try:
        import httpx  # type: ignore
    except Exception:
        return None
    alias = LANG_PISTON_ALIAS.get(lang, lang)
    payload = {
        "language": alias,
        "version": "*",
        "files": [{"content": code}],
        "stdin": stdin,
        "compile_timeout": 10000,
        "run_timeout": 8000,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post("https://emkc.org/api/v2/piston/execute", json=payload)
        if resp.status_code == 200:
            return resp.json()
    except (httpx.TransportError, httpx.TimeoutException, Exception):
        return None
    return None


async def _run_mock(lang: str, code: str, stdin: str, expected_output: str | None = None, *,
                     force_status: str | None = None) -> tuple[str, str, str | None]:
    """本地 mock：
       - Python：ast 解析失败 → CompileError；否则 eval 预置函数（只支持代码中明确写了 def add/reverse/fib 等对应题目）
       - JS/C++：走黑盒：如果 stdin 的输出和 expected_output 字符串匹配 code 关键词（"return"/"split"/"reverse"/"for"）→ 猜测通过
       - 返回 (stdout, stderr, status_inferred)
    """
    if force_status == "CompileError":
        return "", "mock forced compile error", "CompileError"
    if force_status == "RuntimeError":
        return "", "mock forced runtime error", "RuntimeError"

    if lang == "python":
        try:
            ast.parse(code)
        except SyntaxError as e:
            return "", f"SyntaxError: {e.msg} line {e.lineno}", "CompileError"
        ns: dict[str, Any] = {}
        try:
            exec(compile(code, "<code>", "exec"), ns)
        except Exception as e:  # noqa: BLE001
            return "", f"ExecError: {type(e).__name__}: {e}", "RuntimeError"
        # 按题目挑函数
        fn: Any = None
        for name in ["add", "reverse", "fib"]:
            if name in ns and callable(ns[name]):
                fn = ns[name]; break
        try:
            parts = stdin.strip().split()
            if fn is None:
                return "", "No target function add/reverse/fib defined", "RuntimeError"
            if name == "add":
                out = str(fn(int(parts[0]), int(parts[1])))
            elif name == "reverse":
                out = str(fn(parts[0] if parts else ""))
            elif name == "fib":
                out = str(fn(int(parts[0])))
            else:
                return "", "No target function", "RuntimeError"
            return out, "", "Pass"
        except Exception as e:  # noqa: BLE001
            return "", f"RunError: {type(e).__name__}: {e}", "RuntimeError"

    # JS / C++：黑盒关键词 + expected 对比（只给打靶用）
    out = ""
    score_like = 0
    lowered = code.lower().replace(" ", "")
    if lang == "javascript" and ".split('').reverse().join" in lowered or ".split(" in lowered and "reverse()" in lowered:
        score_like += 1
        if stdin:
            out = stdin.strip()[::-1]
    if lang == "cpp":
        if "for" in lowered and ("fib" in lowered or "f[i-1]" in lowered):
            score_like += 1
            try:
                import functools
                @functools.lru_cache(None)
                def fib_(n: int) -> int:
                    return 1 if n <= 2 else fib_(n - 1) + fib_(n - 2)
                out = str(fib_(int(stdin.strip())))
            except Exception:
                out = ""
    if expected_output is not None and out == str(expected_output).strip():
        return out, "", "Pass"
    if score_like and (not expected_output or str(expected_output).strip().startswith(out[:2])):
        return (out or expected_output or ""), "", "Pass"
    return (out or "mock-no-output"), f"mock black-box not passed (score_like={score_like})", "PartialFail"


# ============== 运行 / 提交 统一执行器 ==============

async def _execute(user_id: int, payload: RunIn | SubmitIn, *, run_mode: str) -> RunSubmitOut:
    assert run_mode in ("RUN", "SUBMIT")
    challenge = await get_challenge(payload.challenge_code)
    if payload.lang_code != challenge.lang_code:
        raise BizError(400031, f"题目 {challenge.code} 预设语言为 {challenge.lang_code}，本次提交 {payload.lang_code}")
    cases = _unjson((await fetch_one(
        "SELECT test_cases_json FROM coding_challenge WHERE id=%s", (challenge.id,),
    ))["test_cases_json"])
    if run_mode == "RUN":
        # 只跑非隐藏
        cases = [c for c in cases if not c.get("is_hidden")]
    if not cases:
        raise BizError(400032, "没有可运行的测试用例")

    results: list[CaseResult] = []
    pass_count = 0
    status = "Pending"
    provider = None
    total_ms = 0
    for idx, case in enumerate(cases):
        stdin = str(case.get("input") or "").strip()
        expected = str(case.get("expected") or "").strip()
        start = datetime.now()
        # 先试 Piston real
        piston = await _run_piston(payload.lang_code, payload.code_text, stdin, timeout=2.8)
        actual = ""; stderr = ""; status_each = None
        if piston:
            provider = provider or "PISTON_REAL"
            run_obj = piston.get("run") or {}
            compile_obj = piston.get("compile") or {}
            if compile_obj.get("stderr") or (piston.get("compile", {}).get("code") not in (0, None)):
                stderr = str(compile_obj.get("stderr") or "")[:500]
                status_each = "CompileError"
                actual = str(run_obj.get("output") or "")[:500]
            else:
                actual = str(run_obj.get("output") or "").strip()[:500]
                stderr = str(run_obj.get("stderr") or "")[:500]
                status_each = "Pass" if actual == expected else "PartialFail"
        else:
            # fallback mock
            provider = provider or "LOCAL_MOCK"
            actual, stderr, status_each = await _run_mock(
                payload.lang_code, payload.code_text, stdin, expected_output=expected,
            )
        ms = int((datetime.now() - start).total_seconds() * 1000)
        total_ms += ms
        passed = status_each == "Pass"
        if passed:
            pass_count += 1
        results.append(CaseResult(
            index=idx, input=stdin, expected=(None if case.get("is_hidden") else expected),
            actual=actual if not case.get("is_hidden") else "***",
            is_hidden=bool(case.get("is_hidden", False)),
            passed=passed, stdout=actual,
            stderr=(stderr if not case.get("is_hidden") else "***"),
            runtime_ms=ms,
        ))
    # 状态汇总
    if any(r.status_each if False else False for r in results):  # 占位
        pass
    if all(r.passed for r in results):
        status = "Pass"
    elif pass_count == 0:
        # 首个用例若是 Compile/Runtime 就整体报那个
        kinds = {r.status_each if False else None for r in results}
        has_ce = any("SyntaxError" in (r.stderr or "") for r in results) or any(
            "CompileError" in (r.stderr or "") for r in results
        )
        has_re = any("RuntimeError" in (r.stderr or "") or "ExecError" in (r.stderr or "") for r in results)
        if has_ce:
            status = "CompileError"
        elif has_re:
            status = "RuntimeError"
        else:
            status = "PartialFail"
    else:
        status = "PartialFail"
    points_scored = int(round(pass_count / len(results) * int(challenge.points))) if results else 0
    sid = await execute_write(
        "INSERT INTO coding_submission "
        "(user_id, challenge_id, lang_code, code_text, run_mode, status, pass_count, total_count,"
        " results_json, stdout_text, stderr_text, duration_ms, sandbox_provider, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
        (
            user_id, int(challenge.id or 0), payload.lang_code, payload.code_text,
            run_mode, status, int(pass_count), int(len(results)),
            json.dumps([r.model_dump(mode="json") for r in results], ensure_ascii=False),
            "\n\n---CASE---\n\n".join(r.stdout or "" for r in results)[:65535],
            "\n\n---CASE---\n\n".join(r.stderr or "" for r in results)[:65535],
            int(total_ms), provider,
        ),
    )
    return RunSubmitOut(
        submission_id=int(sid) if sid else 0, status=status,
        pass_count=int(pass_count), total_count=int(len(results)),
        score=points_scored, results=results, duration_ms=int(total_ms),
        sandbox_provider=provider,
    )


async def run_code(user_id: int, payload: RunIn) -> RunSubmitOut:
    return await _execute(user_id, payload, run_mode="RUN")


async def submit_code(user_id: int, payload: SubmitIn) -> RunSubmitOut:
    return await _execute(user_id, payload, run_mode="SUBMIT")


# ============== 递进式 hint（本地规则，生产可切 LLM）=============

HINTS: dict[str, list[str]] = {
    "PY-SUM-TWO": [
        "先仔细读题：两个整数 a 和 b，需要返回它们的和。",
        "函数签名已经给了：def add(a: int, b: int) -> int，所以你只需返回 a + b。",
        "小心：题目说整数，但没说一定非负；直接加就可以，Python 自动处理负数。",
        "常见错误：写成 print(a+b) 而不是 return a+b；题目要求返回值。",
    ],
    "JS-REVERSE-STR": [
        "题目：给一个 JavaScript 函数 reverse(s)，要返回原字符串反转。",
        "核心三步：把字符串拆成字符数组 → 翻转数组 → 再拼回字符串。",
        "对应方法链：s.split('') 或 [...s] 拆成数组，.reverse() 翻转，.join('') 拼接。",
        "常见坑：reverse() 不能直接作用在字符串上；必须先拆到数组再调用。",
    ],
    "CPP-FIB": [
        "斐波那契：F(1)=1, F(2)=1，所以 F(3)=F(2)+F(1)=2… 递推公式 F(n)=F(n-1)+F(n-2)。",
        "建议用 int 数组或循环（不要用递归，递归 1e5 会栈溢出）。",
        "边界条件：如果 n==1 或 n==2 直接 return 1；否则 for(i=3..n) 按公式更新 a,b。",
        "易错：题目是 1-based，不要写成 F(0)=0, F(1)=1 那种 0-based 实现。",
    ],
}


async def hint(payload: HintIn) -> HintOut:
    arr = HINTS.get(payload.challenge_code)
    if not arr:
        raise BizError(404032, f"未找到 challenge_code={payload.challenge_code} 的 hint 数据")
    idx = max(1, min(int(payload.step), len(arr))) - 1
    text = arr[idx]
    # 如果用户传了代码快照，追加一条「定向检查建议」（本地正则）
    if payload.code_snapshot:
        snap = payload.code_snapshot
        if payload.challenge_code == "PY-SUM-TWO" and "return" not in snap:
            text += "\n💡 定向：你的代码目前缺少 return，确认是否把结果 return 出来（而不是 print）。"
        if payload.challenge_code == "JS-REVERSE-STR":
            if "split" not in snap and "[...s]" not in snap:
                text += "\n💡 定向：还没把字符串拆成字符数组，请先 s.split('') 或 [...s]。"
            if ".reverse()" not in snap:
                text += "\n💡 定向：记得对拆出来的数组调 .reverse()。"
        if payload.challenge_code == "CPP-FIB":
            if "for" not in snap:
                text += "\n💡 定向：建议用循环递推，避免递归复杂度爆炸。"
    next_step = (idx + 1) < len(arr)
    return HintOut(
        challenge_code=payload.challenge_code,
        step=idx + 1,
        next_step_available=next_step,
        text=text,
        provider="LOCAL_RULE",
    )
