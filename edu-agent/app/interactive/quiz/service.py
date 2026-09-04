# -*- coding: utf-8 -*-
"""P5 互动习题 quiz service：6 题型判分 + 错题本 + 即时解析（模板 + RAG 占位）。"""
from __future__ import annotations

import json
import random
from typing import Any

from app.common.exceptions import AppException as BizError
from app.database import execute_write, fetch_all, fetch_one
from app.interactive.quiz.schemas import (
    FILL, JUDGE, MATCH, MULTI, Question, SubmitAnswer, SubmitResult,
    WrongBookEntry, WrongBookList, Choice, MatchPair, DRAG_SORT, SINGLE,
)


# ========== 内置 mock 题库 10 题（6 题型都有，打靶可直接用） ==========

_MOCK_BANK: list[dict[str, Any]] = [
    dict(
        code="Q-EN-SINGLE-THE", subject_code="english", type=SINGLE,
        title="Fill in the blank: ___ sun rises in the east.", score_max=5,
        choices=[Choice(key="A", text="A"), Choice(key="B", text="An"),
                 Choice(key="C", text="The"), Choice(key="D", text="/")],
        correct="C",
        explain_template="世界上独一无二的事物前需用定冠词 **the**，如 the sun / the moon / the earth。",
        knowledge_codes=["KP-EN-GRAM-ARTICLE"],
    ),
    dict(
        code="Q-EN-MULTI-COLORS", subject_code="english", type=MULTI,
        title="Which of the following are colors? (multiple answers)", score_max=5,
        choices=[Choice(key="A", text="red"), Choice(key="B", text="happy"),
                 Choice(key="C", text="blue"), Choice(key="D", text="run")],
        correct=["A", "C"],
        explain_template="red(红色) 和 blue(蓝色) 是颜色；happy(开心) 是情绪；run(跑) 是动作。",
        knowledge_codes=["KP-EN-VOC-COLOR"],
    ),
    dict(
        code="Q-EN-JUDGE-GO", subject_code="english", type=JUDGE,
        title="判断正误：'I goed to school yesterday.' 语法正确。",
        correct=False, score_max=5,
        explain_template="go 的过去式是 went，不是 goed。不规则动词需记忆：go→went，do→did，see→saw。",
        knowledge_codes=["KP-EN-GRAM-PASTTENSE"],
    ),
    dict(
        code="Q-EN-FILL-BIGGER", subject_code="english", type=FILL,
        title="比较级：The elephant is ___ (big) than the mouse.", score_max=5,
        correct=["bigger"],
        explain_template="重读闭音节（辅音+元音+辅音结尾）单音节形容词：双写末尾辅音字母 + er → bigger。",
        knowledge_codes=["KP-EN-GRAM-COMPARATIVE"],
    ),
    dict(
        code="Q-MATH-DRAG-OP", subject_code="math", type=DRAG_SORT,
        title="把运算优先级 从高到低 排序（拖拽排列）：加减乘除括号",
        score_max=5,
        items=[
            {"item_id": "A", "label": "加减（+/-）"},
            {"item_id": "B", "label": "乘除（×/÷）"},
            {"item_id": "C", "label": "括号（( )）"},
        ],
        correct=["C", "B", "A"],
        explain_template="运算优先级口诀：先括号 → 后乘除 → 最后加减。同级运算从左到右。",
        knowledge_codes=["KP-MATH-ARITH-OPORDER"],
    ),
    dict(
        code="Q-EN-MATCH-ANTONYM", subject_code="english", type=MATCH,
        title="将下列反义词用线连起来：",
        score_max=5,
        pairs=[
            MatchPair(left_id="L1", left_text="big",    right_id="R1", right_text="small"),
            MatchPair(left_id="L2", left_text="happy",  right_id="R2", right_text="sad"),
            MatchPair(left_id="L3", left_text="hot",    right_id="R3", right_text="cold"),
        ],
        correct=[("L1", "R1"), ("L2", "R2"), ("L3", "R3")],
        explain_template="big↔small（大↔小）；happy↔sad（快乐↔悲伤）；hot↔cold（热↔冷）都是典型反义配对。",
        knowledge_codes=["KP-EN-VOC-ANTONYM"],
    ),
    dict(
        code="Q-PY-SINGLE-KEY", subject_code="programming", type=SINGLE,
        title="Python 中用于获取字典所有 key 的方法是？",
        score_max=5,
        choices=[Choice(key="A", text="dict.keys()"), Choice(key="B", text="dict.values()"),
                 Choice(key="C", text="dict.items()"), Choice(key="D", text="dict.all()")],
        correct="A",
        explain_template="dict.keys() 返回键视图；values() 返回值；items() 返回 (k,v) 对；dict 没有 all()。",
        knowledge_codes=["KP-PY-DICT"],
    ),
    dict(
        code="Q-MATH-SINGLE-SUM100", subject_code="math", type=SINGLE,
        title="1+2+3+…+99+100 = ?",
        score_max=5,
        choices=[Choice(key="A", text="5000"), Choice(key="B", text="5050"),
                 Choice(key="C", text="4950"), Choice(key="D", text="5100")],
        correct="B",
        explain_template="高斯求和：和 = (首项+末项)×项数÷2 = (1+100)×100÷2 = 5050。",
        knowledge_codes=["KP-MATH-ARITH-GAUSS"],
    ),
    dict(
        code="Q-MATH-JUDGE-SQRT", subject_code="math", type=JUDGE,
        title="√2 是有理数。", correct=False, score_max=5,
        explain_template="√2 是无理数，不能表示为两个整数之比（欧几里得已用反证法证明）。",
        knowledge_codes=["KP-MATH-NUM-RATIONAL"],
    ),
    dict(
        code="Q-PY-MULTI-IMMUTABLE", subject_code="programming", type=MULTI,
        title="以下 Python 类型属于「不可变」(immutable) 的有哪些？",
        score_max=5,
        choices=[Choice(key="A", text="tuple"), Choice(key="B", text="list"),
                 Choice(key="C", text="str"),   Choice(key="D", text="int")],
        correct=["A", "C", "D"],
        explain_template="tuple/str/int 都是不可变；list 可变（append 等方法就地修改）。",
        knowledge_codes=["KP-PY-IMMUTABLE"],
    ),
]


def _mock_question_map() -> dict[str, dict[str, Any]]:
    return {q["code"]: q for q in _MOCK_BANK}


# ========== 1. 生成「下一道」给用户 ==========

async def next_question(user_id: int, subject_code: str | None = None,
                        question_type: str | None = None,
                        ensure_type: bool = False) -> Question:
    """按学科/题型过滤：优先从错题本 next_review_at<=now 抽一道；否则从内置 mock 或 admin_question 抽。"""
    # A) 错题本优先
    wb_sql = ("SELECT WB.question_id, WB.custom_question_code, WB.subject_code "
              "FROM quiz_wrong_book WB "
              "WHERE WB.user_id=%s AND WB.status='ACTIVE' AND (WB.next_review_at IS NULL OR WB.next_review_at<=NOW()) ")
    args: list[Any] = [user_id]
    if subject_code:
        wb_sql += " AND WB.subject_code=%s "
        args.append(subject_code)
    wb_sql += " ORDER BY WB.wrong_count DESC, WB.next_review_at ASC LIMIT 1"
    wb = await fetch_one(wb_sql, tuple(args))
    if wb is not None and wb.get("custom_question_code"):
        q = await _load_by_code_or_id(code=wb["custom_question_code"], qid=wb.get("question_id"))
        if q is not None:
            return q

    # B) 过滤 mock + admin
    bank = list(_MOCK_BANK)
    if subject_code:
        bank = [q for q in bank if q["subject_code"].lower() == subject_code.lower()]
    if question_type:
        if ensure_type:
            bank = [q for q in bank if q["type"] == question_type]
        else:
            bank = [q for q in bank if q["type"] == question_type] or bank

    # C) 结合 P3 学习记录：用户薄弱 KP 优先（mastery<0.5 的题概率加权 2 倍）
    mastery: dict[str, float] = {}
    try:
        from app.recommender.engine import _load_mastery_by_kp_code
        mastery = await _load_mastery_by_kp_code(user_id)
    except Exception:
        mastery = {}
    weak_kp = {k for k, v in mastery.items() if v < 0.5}
    weights: list[int] = []
    for q in bank:
        kps = set(q.get("knowledge_codes") or [])
        weights.append(3 if (kps & weak_kp) else 1)
    if not bank:
        raise BizError(404001, "题库中暂无可出的题目，请先指定其他学科或题型。")
    chosen = random.choices(bank, weights=weights, k=1)[0]
    return _dict_to_question(chosen)


async def _load_by_code_or_id(*, code: str | None = None, qid: int | None = None) -> Question | None:
    if code and code in _mock_question_map():
        return _dict_to_question(_mock_question_map()[code])
    # question 表真实题（task13 出题源切换：旧 admin_question → edu.sql question 表）
    if qid:
        try:
            row = await fetch_one(
                "SELECT q.id, q.question_code, q.question_type_id, q.stem, q.options_json, "
                "q.answer_text, q.analysis_text, qt.type_code "
                "FROM `question` q "
                "LEFT JOIN dim_question_type qt ON qt.id = q.question_type_id "
                "WHERE q.id = %s AND q.yn = 1",
                (qid,),
            )
        except Exception as e:
            msg = str(e).lower()
            if ("doesn't exist" in msg or "1146" in msg or "no such table" in msg):
                row = None
            else:
                raise
        if row:
            type_code = (row.get("type_code") or "single_choice").upper()
            # 映射 dim_question_type.type_code → quiz 6 题型
            TYPE_MAP = {
                "SINGLE_CHOICE": SINGLE,
                "MULTI_CHOICE": MULTI,
                "TRUE_FALSE": JUDGE,
                "FILL_BLANK": FILL,
                "DRAG_SORT": DRAG_SORT,
                "MATCH": MATCH,
            }
            qtype = TYPE_MAP.get(type_code, SINGLE)
            opt = _unjson(row.get("options_json")) or []
            return Question(
                question_id=int(row["id"]),
                custom_code=f"Q-{row['question_code']}",
                subject_code="general",
                question_type=qtype,
                title=row["stem"] or "",
                score_max=5.0,
                choices=[Choice(**x) for x in opt if isinstance(x, dict)],
                correct=_unjson(row.get("answer_text")),
                explain_template=row.get("analysis_text"),
                knowledge_codes=[],
            )
    return None


def _unjson(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, (bytes, bytearray)):
        try:
            v = v.decode("utf-8")
        except Exception:
            return None
    try:
        return json.loads(v)
    except Exception:
        return None


def _dict_to_question(d: dict[str, Any]) -> Question:
    q = Question(
        custom_code=d["code"], subject_code=d["subject_code"], question_type=d["type"],
        title=d["title"], score_max=d.get("score_max", 5.0),
        correct=d["correct"], hint=d.get("hint"),
        explain_template=d.get("explain_template"),
        knowledge_codes=d.get("knowledge_codes", []),
    )
    if d["type"] in (SINGLE, MULTI):
        q.choices = d.get("choices", [])
    if d["type"] == DRAG_SORT:
        q.items = d.get("items", [])
    if d["type"] == MATCH:
        q.pairs = d.get("pairs", [])
    return q


# ========== 2. 判分引擎（6 题型） ==========

def _grade(qt: Question, answer: Any) -> tuple[bool, float, str]:
    """返回 (是否正确，得分 0..score_max，判分说明)。"""
    def ratio(got: bool) -> float:
        return qt.score_max if got else 0.0

    if qt.question_type == SINGLE:
        got = answer == qt.correct
        return got, ratio(got), "作答正确" if got else f"正确答案是 {qt.correct}。"
    if qt.question_type == MULTI:
        try:
            ans = sorted([str(x).strip() for x in answer])
        except Exception:
            return False, 0.0, "多选作答格式不对"
        keys = sorted([str(x).strip() for x in (qt.correct or [])])
        if ans == keys:
            return True, ratio(True), "完全正确"
        set_a, set_c = set(ans), set(keys)
        if set_a <= set_c and set_a:
            # 选少了，给一半分
            return False, ratio(False) + ratio(True) * 0.5 * (len(set_a) / max(1, len(set_c))), f"部分正确，漏选 {set_c - set_a}"
        return False, 0.0, f"正确选项 {keys}；错选 {set_a - set_c}"
    if qt.question_type == JUDGE:
        try:
            got = bool(answer)
        except Exception:
            return False, 0.0, "判断题需要 true/false"
        corr = bool(qt.correct)
        return got == corr, ratio(got == corr), "正确" if got == corr else f"正确答案是 {corr}"
    if qt.question_type == FILL:
        corr_list = qt.correct if isinstance(qt.correct, list) else [qt.correct]
        ans_list = answer if isinstance(answer, list) else [answer]
        if len(corr_list) != len(ans_list):
            return False, 0.0, f"空位数不匹配：应有 {len(corr_list)} 空，提交 {len(ans_list)} 空"
        matched = 0
        details = []
        for i, (a, c) in enumerate(zip(ans_list, corr_list), start=1):
            ok = str(a).strip().lower() == str(c).strip().lower()
            matched += int(ok)
            details.append(f"第{i}空 {'✅' if ok else '❌ 正确答案=' + str(c)}")
        all_ok = matched == len(corr_list)
        return all_ok, qt.score_max * matched / len(corr_list), "；".join(details)
    if qt.question_type == DRAG_SORT:
        try:
            order = list(answer)
        except Exception:
            return False, 0.0, "拖拽排序答案应该是 id 数组"
        correct = list(qt.correct or [])
        if len(order) != len(correct):
            return False, 0.0, "拖拽顺序数组长度不对"
        # 如果相邻对，给线性分（完全匹配 100%；错位置按位置匹配数/总）
        pos_match = sum(1 for i in range(len(order)) if order[i] == correct[i])
        ratio_ = pos_match / len(correct)
        return ratio_ >= 0.999, qt.score_max * ratio_, f"顺序匹配 {pos_match}/{len(correct)}"
    if qt.question_type == MATCH:
        try:
            matches = [(m["left_id"], m["right_id"]) for m in answer]
        except Exception:
            return False, 0.0, "MATCH 需要 [{left_id,right_id}] 格式"
        correct_pairs = set(tuple(x) for x in (qt.correct or []))
        ok = sum(1 for m in matches if tuple(m) in correct_pairs)
        ratio_ = ok / max(1, len(correct_pairs))
        return ratio_ >= 0.999, qt.score_max * ratio_, f"配对正确 {ok}/{len(correct_pairs)}"
    return False, 0.0, f"未知题型 {qt.question_type}"


# ========== 3. 提交作答：写 session + 错题本联动 + 返回解析 ==========

async def submit(user_id: int, payload: SubmitAnswer) -> SubmitResult:
    # 找题目
    q = await _load_by_code_or_id(code=payload.custom_code, qid=payload.question_id)
    if q is None:
        raise BizError(404002, f"找不到题目：{payload.custom_code}")
    if q.question_type != payload.question_type:
        raise BizError(400001, f"题目题型 {q.question_type} 与 payload {payload.question_type} 不一致")

    is_correct, score, detail = _grade(q, payload.answer)
    score = round(score, 2)
    # 解析文本：模板 + 判分 detail
    explain = (q.explain_template or "")
    if detail:
        explain = (explain + ("\n\n判分说明：" if explain else "") + detail).strip()

    # 写 quiz_answer_session
    sid = await execute_write(
        "INSERT INTO quiz_answer_session "
        "(user_id, question_id, custom_question_code, subject_code, question_type,"
        " prompt_json, user_answer_json, is_correct, score, time_spent_sec, explain_text, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())",
        (
            user_id, q.question_id, q.custom_code, q.subject_code, q.question_type,
            json.dumps(q.model_dump(mode="json", include={"title", "choices", "items", "pairs"}), ensure_ascii=False),
            json.dumps(payload.answer, ensure_ascii=False),
            1 if is_correct else 0, float(score), int(payload.time_spent_sec), explain,
        ),
    )

    # 错题本更新：做错 或 复习模式做对
    added_to_wrong_book = False
    if not is_correct:
        _sid = sid or 0
        await execute_write(
            "INSERT INTO quiz_wrong_book (user_id, question_id, custom_question_code, subject_code,"
            " question_type, wrong_count, correct_count, master_threshold, status, next_review_at,"
            " last_wrong_answer_json, created_at, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,1,0,3,'ACTIVE',DATE_ADD(NOW(), INTERVAL 6 HOUR),%s,NOW(),NOW()) "
            "ON DUPLICATE KEY UPDATE wrong_count=wrong_count+1, correct_count=GREATEST(0,correct_count-1),"
            " status='ACTIVE', next_review_at=DATE_ADD(NOW(), INTERVAL 6 HOUR),"
            " last_wrong_answer_json=VALUES(last_wrong_answer_json), updated_at=NOW()",
            (
                user_id, q.question_id, q.custom_code, q.subject_code, q.question_type,
                json.dumps(payload.answer, ensure_ascii=False),
            ),
        )
        added_to_wrong_book = True
    else:
        # 做对：若错题本里有，则 correct_count +1；连续达到 master_threshold 就标记 MASTERED
        cur = await fetch_one(
            "SELECT id, correct_count, master_threshold FROM quiz_wrong_book "
            "WHERE user_id=%s AND (custom_question_code=%s OR question_id<=>%s) LIMIT 1",
            (user_id, q.custom_code, q.question_id),
        )
        if cur is not None:
            new_correct_count = int(cur["correct_count"]) + 1
            status = "MASTERED" if new_correct_count >= int(cur["master_threshold"]) else "ACTIVE"
            next_review = "DATE_ADD(NOW(), INTERVAL 3 DAY)" if status == "ACTIVE" else "NULL"
            await execute_write(
                f"UPDATE quiz_wrong_book SET correct_count=%s, status=%s, "
                f"next_review_at={next_review}, updated_at=NOW() WHERE id=%s",
                (new_correct_count, status, int(cur["id"])),
            )
            if status == "MASTERED":
                added_to_wrong_book = False

    mastery_change: dict[str, float] = {}
    return SubmitResult(
        session_id=int(sid) if sid else 0,
        is_correct=is_correct,
        score=float(score),
        score_max=float(q.score_max),
        explain_text=explain,
        added_to_wrong_book=added_to_wrong_book,
        mastery_change=mastery_change,
    )


# ========== 4. 错题本列表（支持复习模式） ==========

async def wrong_book_list(user_id: int, *, status: str = "ACTIVE", page: int = 1,
                          page_size: int = 20, subject_code: str | None = None,
                          only_due: bool = False) -> WrongBookList:
    sql = (
        "SELECT id, question_id, custom_question_code, subject_code, question_type, wrong_count,"
        " correct_count, status, next_review_at, last_wrong_answer_json "
        "FROM quiz_wrong_book WHERE user_id=%s "
    )
    args: list[Any] = [user_id]
    if status and status != "ALL":
        sql += " AND status=%s "
        args.append(status)
    if subject_code:
        sql += " AND subject_code=%s "
        args.append(subject_code)
    if only_due:
        sql += " AND (next_review_at IS NULL OR next_review_at <= NOW()) "
    total = (await fetch_one(
        "SELECT COUNT(*) c FROM (" + sql + ") T",
        tuple(args),
    ))["c"]
    sql += " ORDER BY wrong_count DESC, next_review_at DESC LIMIT %s OFFSET %s"
    args.extend([int(page_size), int(max(0, page - 1)) * int(page_size)])
    rows = await fetch_all(sql, tuple(args))
    items: list[WrongBookEntry] = []
    for r in rows:
        items.append(WrongBookEntry(
            id=int(r["id"]),
            question_id=r["question_id"],
            custom_code=r["custom_question_code"],
            subject_code=r["subject_code"],
            question_type=r["question_type"],
            wrong_count=int(r["wrong_count"]),
            correct_count=int(r["correct_count"]),
            status=r["status"],
            next_review_at=r["next_review_at"],
            last_wrong_answer=_unjson(r["last_wrong_answer_json"]),
        ))
    return WrongBookList(items=items, total=int(total), page=int(page), page_size=int(page_size),
                         filter_status=status or "ALL")


# ========== 5. 「复习模式」抽一道错题 ==========

async def pick_wrong(user_id: int, *, subject_code: str | None = None) -> Question:
    lst = await wrong_book_list(user_id, status="ACTIVE", page=1, page_size=1, only_due=True,
                                subject_code=subject_code)
    if not lst.items:
        raise BizError(404003, "当前没有到期的错题可复习，先去做点新题目吧！")
    entry = lst.items[0]
    q = await _load_by_code_or_id(code=entry.custom_code, qid=entry.question_id)
    if q is None:
        raise BizError(404004, f"错题已关联的题目 {entry.custom_code} 不存在")
    return q
