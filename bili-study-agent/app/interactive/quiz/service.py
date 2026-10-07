# -*- coding: utf-8 -*-
"""P5 互动习题 quiz service：6 题型判分 + 错题本 + 即时解析（模板 + RAG 占位）。"""
from __future__ import annotations

import json
import random
import unicodedata
from typing import Any

from app.common.exceptions import AppException as BizError
from app.database import execute_write, fetch_all, fetch_one, transaction
from app.config import settings
from app.domains.analytics.event_stream import emit_learning_event
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

# quiz 6 题型 → dim_question_type.type_code（真实题库按维度表映射，与 _load_by_code_or_id 的 TYPE_MAP 反向）
_QTYPE_TO_DIM = {
    SINGLE: "single_choice", MULTI: "multi_choice", JUDGE: "true_false",
    FILL: "fill_blank", DRAG_SORT: "drag_sort", MATCH: "match",
}

# One publication authority for public bank practice and enrolled course practice.
_PUBLISHED_FROM = (
    "FROM `question` q JOIN question_bank qb ON qb.id=q.bank_id AND qb.yn=1 "
    "JOIN dim_question_type qt ON qt.id=q.question_type_id "
    "JOIN quiz_question_publication qp ON qp.question_id=q.id "
    "WHERE q.yn=1 AND qp.review_status='PUBLISHED' AND qp.subject_code<>'' "
    "AND qp.question_version<>'' AND qp.source<>'' "
    "AND (qp.course_id IS NULL OR EXISTS (SELECT 1 FROM quiz_question_kp k "
    "WHERE k.question_id=q.id AND k.knowledge_code<>'')) "
    "AND (qp.source<>'video_generated' OR EXISTS (SELECT 1 FROM video_learning_exercise ve "
    "JOIN video_learning_publication vp ON vp.video_id=ve.video_id "
    "AND vp.artifact_id=ve.generation AND vp.artifact_sha256=ve.artifact_sha256 "
    "WHERE ve.bank_id=q.bank_id AND ve.package_sha256=qp.question_version AND vp.rag_status='ready' AND NOT EXISTS ("
    "SELECT 1 FROM video_learning_publication newer WHERE newer.video_id=vp.video_id "
    "AND newer.rag_status='ready' AND newer.id>vp.id))) "
)
_LEARNER_SCOPE = (
    "AND (qp.course_id IS NULL OR EXISTS (SELECT 1 FROM student_cohort_rel scr "
    "JOIN series_cohort_course ccc ON ccc.cohort_id=scr.cohort_id "
    "WHERE scr.user_id=%s AND scr.enroll_status='active' AND ccc.id=qp.course_id)) "
)


async def available_banks(user_id: int) -> dict:
    rows = await fetch_all("SELECT qb.id AS bank_id,qb.bank_name,COUNT(DISTINCT q.id) AS question_count, "
        "GROUP_CONCAT(DISTINCT qt.type_code) AS type_codes " + _PUBLISHED_FROM + _LEARNER_SCOPE +
        "GROUP BY qb.id,qb.bank_name ORDER BY qb.id DESC", (int(user_id),))
    inverse = {value: key for key, value in _QTYPE_TO_DIM.items()}
    for row in rows:
        row["question_types"] = [inverse[t] for t in (row.pop("type_codes") or "").split(",") if t in inverse]
    return {"items": rows, "total": len(rows)}

async def next_question(user_id: int, subject_code: str | None = None,
                        question_type: str | None = None, course_id: int | None = None,
                        bank_id: int | None = None, learning_loop_id: str | None = None) -> Question:
    """按学科/题型过滤：优先从错题本 next_review_at<=now 抽一道；否则从内置 mock 或真实题库抽。

    [FEAT-WIRE-V2 #7 修复] 专项练习选题型曾完全失效，两处根因：
    ① 错题本优先分支不按 question_type 过滤——用户有一道到期 SINGLE 错题时，
      选任何题型都返回这道单选题；
    ② mock 过滤的 `or bank` 兜底把题型过滤静默吞掉（无该题型 mock 时回退全库）。
    修复：错题优先同样按题型过滤；mock 无该题型时查真实题库（question 表按
    dim_question_type.type_code 映射），仍无则诚实抛 404001，不再静默忽略过滤。"""
    ordinary_only = False
    if learning_loop_id:
        loop = await fetch_one("SELECT course_id,session_id FROM learning_loop WHERE id=%s AND user_id=%s "
            "AND status='ACTIVE' AND activated_at>=DATE_SUB(NOW(6), INTERVAL 24 HOUR)", (str(learning_loop_id),int(user_id)))
        if not loop or (course_id is not None and int(loop['course_id'])!=course_id):
            raise BizError(40330,"学习轮次已失效或不属于当前课程")
        from app.domains.learning.study_context import _load_authorized_context
        from app.domains.video_learning.exercises import ready_exercises
        context=await _load_authorized_context(int(loop['session_id']),int(user_id))
        course_id=int(context['module_id'])
        video=context.get('video')
        exercise=await ready_exercises(int(video['video_id'])) if video else None
        if exercise:
            if bank_id is not None and bank_id!=int(exercise['bank_id']):raise BizError(40330,'题库不属于本课正式视频版本')
            bank_id=int(exercise['bank_id'])
        else:
            if bank_id is not None:raise BizError(40330,'本课视频习题尚未生成')
            ordinary_only=True  # Keep legitimate legacy course questions, never another video's bank.
    # A) 错题本优先（显式选题型时，错题也只在该题型内优先）
    wb_sql = ("SELECT WB.question_id, WB.custom_question_code, WB.subject_code "
              "FROM quiz_wrong_book WB ")
    if course_id is not None:
        wb_sql += "JOIN quiz_question_publication WQP ON WQP.question_id=WB.question_id "
    wb_sql += ("WHERE WB.user_id=%s AND WB.status='ACTIVE' "
               "AND (WB.next_review_at IS NULL OR WB.next_review_at<=NOW()) ")
    args: list[Any] = [user_id]
    if course_id is not None:
        wb_sql += " AND WQP.course_id=%s "
        args.append(int(course_id))
    if subject_code:
        wb_sql += " AND WB.subject_code=%s "
        args.append(subject_code)
    if question_type:
        wb_sql += " AND WB.question_type=%s "
        args.append(question_type)
    wb_sql += " ORDER BY WB.wrong_count DESC, WB.next_review_at ASC LIMIT 1"
    wb = await fetch_one(wb_sql, tuple(args))
    if bank_id is None and wb is not None and wb.get("custom_question_code"):
        q = await _load_by_code_or_id(code=wb["custom_question_code"], qid=wb.get("question_id"))
        if q is not None and (not ordinary_only or q.source != 'video_generated') and (course_id is None or q.course_id == course_id) and await _can_access_question(user_id, q):
            return q

    # B) 演示题仅允许通过显式 QUIZ_DEMO_MODE 开启；正式路径永不混入 mock。
    bank = list(_MOCK_BANK) if settings.QUIZ_DEMO_MODE and course_id is None else []
    if subject_code:
        bank = [q for q in bank if q["subject_code"].lower() == subject_code.lower()]
    if question_type:
        bank = [q for q in bank if q["type"] == question_type]
    if not bank:
        # mock 无该（学科×题型）组合 → 查真实题库；仍无 → 诚实空态
        q = await _random_real_question(user_id=user_id, question_type=question_type,
                                        subject_code=subject_code, course_id=course_id, bank_id=bank_id,
                                        **({'ordinary_only': True} if ordinary_only else {}))
        if q is not None:
            return q
        raise BizError(404001, "题库中暂无该题型的题目，请先选择其他题型。")

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


async def _random_real_question(*, user_id: int, question_type: str | None = None,
                                subject_code: str | None = None,
                                course_id: int | None = None, bank_id: int | None = None,
                                ordinary_only: bool = False) -> Question | None:
    """[FEAT-WIRE-V2 #7] 按题型从真实题库（question 表）随机抽一题。

    题型经 dim_question_type.type_code 映射；表不存在/无匹配题时返回 None（由调用方诚实空态）。"""
    if not question_type:
        dim_code = None
    else:
        dim_code = _QTYPE_TO_DIM.get(question_type)
        if dim_code is None:
            return None
    # publication / question_kp 是迁移后由题目管理端维护的正式发布元数据。
    # 缺表时 fail closed：不能把没有课程/KP/version 的存量题伪装成正式题。
    sql = "SELECT q.id " + _PUBLISHED_FROM + _LEARNER_SCOPE
    args: list[Any] = [int(user_id)]
    if ordinary_only: sql += " AND qp.source<>'video_generated'"
    if course_id is not None:
        sql += " AND qp.course_id=%s"
        args.append(int(course_id))
    if bank_id is not None:
        sql += " AND q.bank_id=%s"
        args.append(int(bank_id))
    if dim_code:
        sql += " AND qt.type_code = %s"
        args.append(dim_code)
    if subject_code:
        sql += " AND qp.subject_code = %s"
        args.append(subject_code)
    sql += " ORDER BY RAND() LIMIT 1"
    try:
        row = await fetch_one(sql, tuple(args))
    except Exception as e:
        msg = str(e).lower()
        if ("doesn't exist" in msg or "1146" in msg or "no such table" in msg
                or "quiz_question_publication" in msg or "quiz_question_kp" in msg):
            return None
        raise
    if not row:
        return None
    question = await _load_by_code_or_id(code=None, qid=row["id"])
    if course_id is not None and question is not None and question.course_id != course_id:
        return None  # Publication changed between selection and load.
    return question


async def _load_by_code_or_id(*, code: str | None = None, qid: int | None = None) -> Question | None:
    if settings.QUIZ_DEMO_MODE and code and code in _mock_question_map():
        return _dict_to_question(_mock_question_map()[code])
    # question 表真实题（task13 出题源切换：旧 admin_question → edu.sql question 表）
    if qid:
        try:
            row = await fetch_one(
                "SELECT q.id, q.bank_id, q.question_code, q.question_type_id, q.stem, q.options_json, "
                "q.answer_text, q.analysis_text, qt.type_code, qp.question_version, "
                "qp.course_id, qp.subject_code, qp.difficulty, qp.source, qp.review_status "
                + _PUBLISHED_FROM + "AND q.id=%s",
                (qid,),
            )
        except Exception as e:
            msg = str(e).lower()
            if ("doesn't exist" in msg or "1146" in msg or "no such table" in msg
                    or "quiz_question_publication" in msg or "quiz_question_kp" in msg):
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
            video_evidence = None
            if row.get('source') == 'video_generated':
                from app.domains.video_learning.exercises import question_evidence
                video_evidence = await question_evidence(int(row['bank_id']), row['question_code'])
                if video_evidence is None: return None
            return Question(
                question_id=int(row["id"]),
                bank_id=row.get("bank_id"),
                video_evidence=video_evidence,
                custom_code=f"Q-{row['question_code']}",
                question_version=str(row["question_version"]),
                course_id=int(row["course_id"]) if row["course_id"] is not None else None,
                subject_code=row["subject_code"],
                difficulty=row["difficulty"],
                source=row["source"],
                review_status=row["review_status"],
                question_type=qtype,
                title=row["stem"] or "",
                score_max=5.0,
                choices=[Choice(key=str(x.get("key", x.get("label", ""))), text=str(x.get("text", x.get("content", "")))) for x in opt if isinstance(x, dict)],
                correct=_unjson(row.get("answer_text")) if _unjson(row.get("answer_text")) is not None else row.get("answer_text"),
                explain_template=row.get("analysis_text"),
                knowledge_codes=await _question_knowledge_codes(int(row["id"])),
            )
    return None


async def _question_knowledge_codes(question_id: int) -> list[str]:
    rows = await fetch_all(
        "SELECT knowledge_code FROM quiz_question_kp WHERE question_id=%s ORDER BY knowledge_code",
        (question_id,),
    )
    return [str(r["knowledge_code"]) for r in rows if r.get("knowledge_code")]


async def _can_access_question(user_id: int, question: Question) -> bool:
    if question.course_id is None:
        return bool((question.question_id is not None and question.review_status == "PUBLISHED")
                    or (settings.QUIZ_DEMO_MODE and question.review_status == "DEMO"))
    return bool(await fetch_one(
        "SELECT 1 AS allowed FROM student_cohort_rel scr "
        "JOIN series_cohort_course ccc ON ccc.cohort_id=scr.cohort_id "
        "WHERE scr.user_id=%s AND scr.enroll_status='active' AND ccc.id=%s LIMIT 1",
        (int(user_id), int(question.course_id)),
    ))


async def question_for_user(user_id: int, *, code: str | None = None,
                            qid: int | None = None) -> Question | None:
    if qid is None and code and not (settings.QUIZ_DEMO_MODE and code in _mock_question_map()):
        question_code = code[2:] if code.startswith("Q-") else code
        # Restrict resolution to this learner's active course before reading the question.
        try:
            found = await fetch_one(
                "SELECT q.id " + _PUBLISHED_FROM + _LEARNER_SCOPE + "AND q.question_code=%s LIMIT 1",
                (int(user_id), question_code),
            )
        except Exception as exc:
            msg = str(exc).lower()
            if ("doesn't exist" in msg or "1146" in msg or "no such table" in msg
                    or "quiz_question_publication" in msg or "quiz_question_kp" in msg):
                return None
            raise
        if not found:
            return None
        qid = int(found["id"])
        code = None
    question = await _load_by_code_or_id(code=code, qid=qid)
    if code and question is not None and question.custom_code != code:
        return None
    if question is None or not await _can_access_question(user_id, question):
        return None
    return question


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
        question_version=str(d.get("question_version", "demo-v1")),
        course_id=d.get("course_id"), difficulty=d.get("difficulty", "demo"),
        source="demo", review_status="DEMO",
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
            if not isinstance(answer, list):
                raise TypeError
            ans_raw = [str(x).strip() for x in answer]
            if len(ans_raw) != len(set(ans_raw)):
                return False, 0.0, "多选答案包含重复选项"
            ans = sorted(ans_raw)
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
        got = _normalize_judge(answer)
        if got is None:
            return False, 0.0, "判断题需要 true/false"
        corr = _normalize_judge(qt.correct)
        if corr is None:
            return False, 0.0, "题目正确答案格式无效"
        return got == corr, ratio(got == corr), "正确" if got == corr else f"正确答案是 {corr}"
    if qt.question_type == FILL:
        corr_list = qt.correct if isinstance(qt.correct, list) else [qt.correct]
        ans_list = answer if isinstance(answer, list) else [answer]
        if len(corr_list) != len(ans_list):
            return False, 0.0, f"空位数不匹配：应有 {len(corr_list)} 空，提交 {len(ans_list)} 空"
        matched = 0
        details = []
        for i, (a, c) in enumerate(zip(ans_list, corr_list), start=1):
            ok = _normalize_fill_v1(a) == _normalize_fill_v1(c)
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
        if len(matches) != len(set(matches)):
            return False, 0.0, "MATCH 提交包含重复配对"
        if len({left for left, _ in matches}) != len(matches) or len({right for _, right in matches}) != len(matches):
            return False, 0.0, "MATCH 每个左右项只能使用一次"
        ok = sum(1 for m in matches if tuple(m) in correct_pairs)
        ratio_ = ok / max(1, len(correct_pairs))
        return ratio_ >= 0.999, min(qt.score_max, qt.score_max * ratio_), f"配对正确 {ok}/{len(correct_pairs)}"
    return False, 0.0, f"未知题型 {qt.question_type}"


def _normalize_judge(value: Any) -> bool | None:
    """Judge schema v1: bool 或大小写不敏感 true/false 字符串；其它值无效。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


def _normalize_fill_v1(value: Any) -> str:
    """Fill normalization v1: Unicode NFKC、首尾裁剪、casefold、连续空白折叠。"""
    normalized = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    return " ".join(normalized.split())


# ========== 3. 提交作答：写 session + 错题本联动 + 返回解析 ==========

async def submit(user_id: int, payload: SubmitAnswer) -> SubmitResult:
    attempt_id = str(payload.attempt_id)
    request_hash = _submit_request_hash(payload)
    existing = await fetch_one(
        "SELECT id,request_hash,response_json FROM quiz_answer_session "
        "WHERE user_id=%s AND attempt_id=%s LIMIT 1",
        (int(user_id), attempt_id),
    )
    if existing:
        return _replay_or_reject(existing, request_hash)

    q = await question_for_user(user_id, code=payload.custom_code, qid=payload.question_id)
    if q is None:
        raise BizError(404002, f"找不到当前课程可访问的正式题目：{payload.custom_code}")
    if q.question_type != payload.question_type:
        raise BizError(400001, f"题目题型 {q.question_type} 与 payload {payload.question_type} 不一致")

    is_correct, score, detail = _grade(q, payload.answer)
    score = round(score, 2)
    explain = (q.explain_template or "")
    if detail:
        explain = (explain + ("\n\n判分说明：" if explain else "") + detail).strip()
    prompt_json = json.dumps(q.model_dump(mode="json", include={
        "title", "choices", "items", "pairs", "question_version", "course_id",
        "subject_code", "knowledge_codes", "difficulty", "source",
    }), ensure_ascii=False, sort_keys=True)
    answer_json = json.dumps(payload.answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    added_to_wrong_book = not is_correct
    loop_id = str(payload.learning_loop_id) if payload.learning_loop_id else None
    try:
        async with transaction() as (_conn, cur):
            if loop_id:
                await cur.execute(
                    "SELECT ll.course_id,ll.session_id FROM learning_loop ll "
                    "JOIN series_cohort_session s ON s.id=ll.session_id "
                    "JOIN series_cohort_course ccc ON ccc.id=s.series_cohort_course_id "
                    "AND ccc.id=ll.course_id "
                    "JOIN student_cohort_rel scr ON scr.cohort_id=ccc.cohort_id "
                    "AND scr.user_id=ll.user_id AND scr.enroll_status='active' "
                    "WHERE ll.id=%s AND ll.user_id=%s AND ll.status='ACTIVE' "
                    "AND ll.activated_at>=DATE_SUB(NOW(6), INTERVAL 24 HOUR) FOR UPDATE",
                    (loop_id, int(user_id)),
                )
                authorized_loop = await cur.fetchone()
                if not authorized_loop or q.course_id != int(authorized_loop[0]):
                    raise BizError(40330, "学习轮次已失效或题目不属于当前课程")
                if q.video_evidence and q.video_evidence.session_id != int(authorized_loop[1]):
                    raise BizError(40330,"视频习题不属于当前课次")
            if payload.redo_of_attempt_id:
                await cur.execute(
                    "SELECT id FROM quiz_answer_session WHERE user_id=%s AND attempt_id=%s "
                    "AND question_id<=>%s AND custom_question_code=%s AND is_correct=0 FOR UPDATE",
                    (int(user_id), str(payload.redo_of_attempt_id), q.question_id, q.custom_code),
                )
                if await cur.fetchone() is None:
                    raise BizError(400001, "重做来源必须是本人此前答错的同一道题")
            await cur.execute(
                "INSERT INTO quiz_answer_session "
                "(user_id,question_id,custom_question_code,subject_code,course_id,question_type,"
                "question_version,knowledge_codes_snapshot,hint_used,redo_of_attempt_id,attempt_id,learning_loop_id,"
                "request_hash,response_json,prompt_json,user_answer_json,is_correct,score,time_spent_sec,"
                "explain_text,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,NOW())",
                (int(user_id), q.question_id, q.custom_code, q.subject_code, q.course_id,
                 q.question_type, q.question_version,
                 json.dumps(q.knowledge_codes, ensure_ascii=False),
                 str(payload.redo_of_attempt_id) if payload.redo_of_attempt_id else None,
                 attempt_id, loop_id, request_hash, prompt_json, answer_json, 1 if is_correct else 0,
                 float(score), int(payload.time_spent_sec), explain),
            )
            sid = int(cur.lastrowid)
            if not is_correct:
                await cur.execute(
                    "INSERT INTO quiz_wrong_book (user_id,question_id,custom_question_code,subject_code,"
                    "question_type,wrong_count,correct_count,master_threshold,status,next_review_at,"
                    "last_wrong_answer_json,created_at,updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,1,0,3,'ACTIVE',DATE_ADD(NOW(), INTERVAL 6 HOUR),%s,NOW(),NOW()) "
                    "ON DUPLICATE KEY UPDATE wrong_count=wrong_count+1,"
                    "correct_count=IF(correct_count>0,correct_count-1,0),status='ACTIVE',"
                    "next_review_at=DATE_ADD(NOW(), INTERVAL 6 HOUR),"
                    "last_wrong_answer_json=VALUES(last_wrong_answer_json),updated_at=NOW()",
                    (int(user_id), q.question_id, q.custom_code, q.subject_code, q.question_type, answer_json),
                )
            else:
                await cur.execute(
                    "SELECT id,correct_count,master_threshold FROM quiz_wrong_book "
                    "WHERE user_id=%s AND custom_question_code=%s AND question_id<=>%s LIMIT 1 FOR UPDATE",
                    (int(user_id), q.custom_code, q.question_id),
                )
                old_wrong = await cur.fetchone()
                if old_wrong:
                    new_count = int(old_wrong[1]) + 1
                    status = "MASTERED" if new_count >= int(old_wrong[2]) else "ACTIVE"
                    if status == "MASTERED":
                        await cur.execute(
                            "UPDATE quiz_wrong_book SET correct_count=%s,status=%s,next_review_at=NULL,updated_at=NOW() WHERE id=%s",
                            (new_count, status, int(old_wrong[0])),
                        )
                        added_to_wrong_book = False
                    else:
                        await cur.execute(
                            "UPDATE quiz_wrong_book SET correct_count=%s,status=%s,"
                            "next_review_at=DATE_ADD(NOW(), INTERVAL 3 DAY),updated_at=NOW() WHERE id=%s",
                            (new_count, status, int(old_wrong[0])),
                        )
            mastery_change: dict[str, float] = {}
            states = {}
            if q.course_id is not None and q.knowledge_codes:
                from app.domains.learning.mastery_repository import recompute_quiz_mastery_in_transaction

                states = await recompute_quiz_mastery_in_transaction(
                    cur, int(user_id), int(q.course_id)
                )
                mastery_change = {code: float(state.confidence) for code, state in states.items()}
            next_action = None
            if loop_id:
                if is_correct:
                    due_candidates = [s.next_review_at for s in states.values() if s.next_review_at]
                    due_at = min(due_candidates) if due_candidates else None
                    kind = "REVIEW_KP"
                else:
                    await cur.execute(
                        "SELECT next_review_at FROM quiz_wrong_book "
                        "WHERE user_id=%s AND question_id<=>%s AND custom_question_code=%s "
                        "LIMIT 1 FOR UPDATE",
                        (int(user_id), q.question_id, q.custom_code),
                    )
                    wrong_row = await cur.fetchone()
                    due_at = wrong_row[0] if wrong_row else None
                    kind = "REVIEW_QUESTION"
                if due_at is None:
                    raise BizError(500001, "复习安排未能持久化")
                await cur.execute(
                    "INSERT INTO learning_next_action "
                    "(learning_loop_id,user_id,quiz_answer_session_id,kind,status,due_at,created_at) "
                    "VALUES (%s,%s,%s,%s,'SCHEDULED',%s,NOW(6))",
                    (loop_id, int(user_id), sid, kind, due_at),
                )
                next_action = {"action_id": int(cur.lastrowid), "kind": kind,
                               "status": "SCHEDULED", "due_at": due_at.isoformat()}
            if payload.redo_of_attempt_id:
                await cur.execute(
                    "UPDATE learning_next_action a JOIN quiz_answer_session old "
                    "ON old.id=a.quiz_answer_session_id "
                    "SET a.status='EXECUTED',a.executed_at=NOW(6) "
                    "WHERE old.user_id=%s AND old.attempt_id=%s "
                    "AND a.kind='REVIEW_QUESTION' AND a.status='SCHEDULED'",
                    (int(user_id), str(payload.redo_of_attempt_id)),
                )
            result = SubmitResult(session_id=sid, is_correct=is_correct, score=float(score),
                                  score_max=float(q.score_max), explain_text=explain,
                                  added_to_wrong_book=added_to_wrong_book,
                                  mastery_change=mastery_change,
                                  learning_loop_id=payload.learning_loop_id,
                                  next_action=next_action)
            await cur.execute(
                "UPDATE quiz_answer_session SET response_json=%s WHERE id=%s",
                (result.model_dump_json(), sid),
            )
    except Exception as exc:
        if _is_duplicate_key_error(exc):
            duplicate = await fetch_one(
                "SELECT id,request_hash,response_json FROM quiz_answer_session "
                "WHERE user_id=%s AND attempt_id=%s LIMIT 1",
                (int(user_id), attempt_id),
            )
            if duplicate:
                return _replay_or_reject(duplicate, request_hash)
        raise

    emit_learning_event("quiz_submit", user_id=user_id, payload={
        "question_id": q.question_id, "custom_code": q.custom_code,
        "subject_code": q.subject_code, "question_type": q.question_type,
        "is_correct": bool(is_correct), "score": float(score),
        "quiz_answer_session_id": sid,
    })
    return result


def _submit_request_hash(payload: SubmitAnswer) -> str:
    import hashlib
    body = {"question_id": payload.question_id, "custom_code": payload.custom_code,
            "question_type": payload.question_type, "answer": payload.answer,
            "time_spent_sec": payload.time_spent_sec,
            "learning_loop_id": str(payload.learning_loop_id) if payload.learning_loop_id else None,
            "redo_of_attempt_id": str(payload.redo_of_attempt_id) if payload.redo_of_attempt_id else None}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _replay_or_reject(existing: dict, request_hash: str) -> SubmitResult:
    if existing.get("request_hash") != request_hash:
        raise BizError(409001, "attempt_id 已被不同作答内容使用")
    response = _unjson(existing.get("response_json"))
    if not isinstance(response, dict):
        raise BizError(503001, "该 attempt 已记录但响应快照缺失，需运维对账")
    return SubmitResult.model_validate(response)


def _is_duplicate_key_error(exc: Exception) -> bool:
    return any(str(item) == "1062" or "duplicate entry" in str(item).lower()
               for item in getattr(exc, "args", ()))


# ========== 4. 错题本列表（支持复习模式） ==========

async def wrong_book_list(user_id: int, *, status: str = "ACTIVE", page: int = 1,
                          page_size: int = 20, subject_code: str | None = None,
                          only_due: bool = False) -> WrongBookList:
    sql = (
        "SELECT id, question_id, custom_question_code, subject_code, question_type, wrong_count,"
        " correct_count, status, next_review_at, last_wrong_answer_json, "
        "(SELECT qa.attempt_id FROM quiz_answer_session qa WHERE qa.user_id=quiz_wrong_book.user_id "
        "AND qa.question_id<=>quiz_wrong_book.question_id "
        "AND qa.custom_question_code<=>quiz_wrong_book.custom_question_code AND qa.is_correct=0 "
        "ORDER BY qa.id DESC LIMIT 1) AS last_wrong_attempt_id "
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
    if not settings.QUIZ_DEMO_MODE:
        # Keep historical rows in storage; only offer questions that remain
        # formally published and authorized for this learner.
        sql += " AND EXISTS (SELECT 1 " + _PUBLISHED_FROM + _LEARNER_SCOPE + " AND q.id=quiz_wrong_book.question_id) "
        args.append(int(user_id))
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
            last_wrong_attempt_id=str(r["last_wrong_attempt_id"]) if r.get("last_wrong_attempt_id") else None,
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
    if q is None or not await _can_access_question(user_id, q):
        raise BizError(404004, f"错题已关联的题目 {entry.custom_code} 不存在")
    return q
