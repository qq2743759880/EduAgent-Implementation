# -*- coding: utf-8 -*-
"""P4 推荐引擎 engine：冷启动 / 协同过滤 / 图谱遍历 / 三路加权融合。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from app.common.exceptions import AppException as BizError
from app.database import execute_write, fetch_all, fetch_one
from app.recommender.schemas import (
    LearningPath, NextStepOut, PathNode, RecommendFeedbackIn, RecommendFeedbackOut,
    RecommendedCourse,
)

DEFAULT_SUBJECT_LEVELS = ["L1", "L2", "L3", "L4", "L5"]
WEIGHT_COLD: float = 0.30
WEIGHT_CF: float = 0.25
WEIGHT_GRAPH: float = 0.30
WEIGHT_FEEDBACK: float = 0.15


# ============================================================
# 1. 画像/数据获取辅助
# ============================================================

def _unjson(v: Any) -> Any:
    """user_profile（P0-P 用户画像表）中 JSON 列可能是 str / bytes / 内存 dict；统一解析。"""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, (bytes, bytearray)):
        try:
            v = v.decode("utf-8")
        except Exception:
            return None
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return None


async def _load_profile(user_id: int) -> dict[str, Any]:
    """读取 P0-P 用户画像（user_profile），返回规范化 dict。"""
    row = await fetch_one(
        "SELECT nickname, study_style, weekly_available_hours, target_qualification, grade_code,"
        " learning_goals, subject_preferences, level_assessments, interest_tags "
        "FROM user_profile WHERE user_id = %s LIMIT 1",
        (user_id,),
    )
    if row is None:
        return {}
    return {
        "weekly_available_hours": int(row["weekly_available_hours"] or 0),
        "study_style": row["study_style"] or "mixed",
        "target_qualification": row["target_qualification"],
        "grade_code": row["grade_code"],
        "learning_goals": _unjson(row["learning_goals"]) or [],
        "subject_preferences": _unjson(row["subject_preferences"]) or [],   # list[{subject_code, preference_score 1-5}]
        "level_assessments": _unjson(row["level_assessments"]) or [],       # list[{subject_code, level_code L1-L5, assessed_at}]
        "interest_tags": _unjson(row["interest_tags"]) or [],
    }


async def _load_feedback_deltas(user_id: int, scene_code: str) -> dict[str, float]:
    """加载该用户在某场景下的反馈分修正（累加 HELP/NOT_INT 后得到 delta per target）。"""
    rows = await fetch_all(
        "SELECT target_id, SUM(score_delta) AS s FROM recommend_feedback "
        "WHERE user_id=%s AND scene_code=%s GROUP BY target_id HAVING s IS NOT NULL",
        (user_id, scene_code),
    )
    return {r["target_id"]: float(r["s"] or 0) for r in rows}


async def _load_mastery_by_kp_code(user_id: int) -> dict[str, float]:
    """从 P3 数据（video 进度 / homework 正确率 / exam 正确率 × 条目标签关联）估算 mastery_ratio 并按 KP code 聚合。"""
    mastery: dict[str, tuple[float, int]] = {}  # kp_code → (ratio_sum, n)

    # 1) 视频 / 作业：找到所有 session → module → graph KP，映射 session 的完成率
    rows = await fetch_all(
        """
        SELECT k.code AS kp_code,
               MAX(v.position_seconds) AS maxpos,
               IFNULL(CS.duration_minutes, 45) AS dur_min,
               AVG(CASE WHEN H.answers_json IS NOT NULL THEN
                 JSON_LENGTH(JSON_SEARCH(H.answers_json, 'one', true, NULL, '$[*].is_correct')) /
                 NULLIF(JSON_LENGTH(H.answers_json), 0) ELSE NULL END) AS hw_rate,
               COUNT(DISTINCT v.id) + COUNT(DISTINCT H.id) AS signals
        FROM graph_node K
        JOIN graph_edge E      ON E.to_node_id = K.id AND E.rel_type = 'CONTAINS' AND E.yn = 1
        JOIN graph_node M      ON M.id = E.from_node_id AND M.label = 'CourseModule'
        LEFT JOIN curriculum_module CM ON CM.module_code = M.code AND CM.yn = 1  -- 对齐真实 curriculum，没 curriculum 就按默认 45min；软删模块不计
        LEFT JOIN curriculum_session CS ON CS.module_id = CM.id AND CS.yn = 1
        LEFT JOIN session_video_play_event V ON V.session_id = CS.id AND V.user_id = %s
        LEFT JOIN session_homework_submission H ON H.session_id = CS.id AND H.user_id = %s AND H.answers_json IS NOT NULL
        WHERE K.label = 'KnowledgePoint' AND K.yn = 1
        GROUP BY K.code, CS.duration_minutes
        HAVING signals > 0
        """,
        (user_id, user_id),
    )
    for r in rows:
        dur = int(r["dur_min"] or 45) * 60
        ratio_v = 0.0
        if r["maxpos"] is not None and dur > 0:
            ratio_v = min(float(r["maxpos"]) / float(dur), 1.0)
        hw = r["hw_rate"]
        rates = [x for x in (ratio_v, float(0 if hw is None else hw)) if x >= 0]
        if rates:
            acc, cnt = mastery.get(r["kp_code"], (0.0, 0))
            mastery[r["kp_code"]] = (acc + sum(rates) / len(rates), cnt + 1)

    # 2) 考试：试卷条目 → 知识点（通过 question_id → TESTS 边）估算掌握度
    ex_rows = await fetch_all(
        """
        SELECT K.code AS kp_code,
               AVG(CASE WHEN g_correct = true THEN 1 ELSE 0 END) AS rate
        FROM session_exam_submission S
        JOIN JSON_TABLE(S.answers_json, '$[*]' COLUMNS (
            question_id BIGINT PATH '$.question_id',
            g_correct   TINYINT PATH '$.is_correct'
        )) J
        JOIN graph_edge E     ON E.rel_type = 'TESTS' AND E.yn = 1
        JOIN graph_node Q     ON Q.id = E.to_node_id AND Q.label = 'QuestionTag'
        JOIN admin_exam_paper_item PI ON PI.question_id = J.question_id
        JOIN graph_edge E2    ON E2.rel_type = 'TESTS' AND E2.yn = 1
        JOIN graph_node K     ON K.id = E2.from_node_id AND K.label = 'KnowledgePoint'
        WHERE S.user_id = %s AND S.answers_json IS NOT NULL
        GROUP BY K.code
        """,
        (user_id,),
    )
    for r in ex_rows:
        rate = 0.0 if r["rate"] is None else float(r["rate"])
        acc, cnt = mastery.get(r["kp_code"], (0.0, 0))
        mastery[r["kp_code"]] = (acc + rate, cnt + 1)

    # 3) 最终求平均
    out: dict[str, float] = {}
    for k, (s, c) in mastery.items():
        if c > 0:
            out[k] = min(max(s / float(c), 0.0), 1.0)
    return out


# ============================================================
# 2. 策略一：冷启动（画像偏好 × 学科等级 直接打分）
# ============================================================

async def cold_start_recommend(user_id: int, profile: dict[str, Any] | None = None,
                               top_n: int = 15) -> list[RecommendedCourse]:
    """新用户/无历史行为：subject_preferences × level_assessments × curriculum 匹配。"""
    profile = profile or await _load_profile(user_id)
    pref_map: dict[str, int] = {}
    for p in profile.get("subject_preferences", []):
        if isinstance(p, dict):
            pref_map[(p.get("subject_code") or "").lower()] = int(p.get("preference_score") or 3)
    level_map: dict[str, str] = {}
    for a in profile.get("level_assessments", []):
        if isinstance(a, dict):
            level_map[(a.get("subject_code") or "").lower()] = a.get("level_code") or "L2"
    weekly_hours = int(profile.get("weekly_available_hours") or 5)
    if not pref_map:
        # 完全无偏好：默认 english L2
        pref_map = {"english": 3, "programming": 4, "math": 3}

    # 打所有 graph node SERIES/MODULE/KP 分：subject 匹配 pref + 按默认 level 难度给分
    rows = await fetch_all(
        "SELECT id, label, code, name, subject_code, sort_no, properties_json "
        "FROM graph_node WHERE yn=1 AND label IN ('CourseSeries','CourseModule','KnowledgePoint') "
        "ORDER BY subject_code, sort_no, id LIMIT 200",
    )
    results: list[RecommendedCourse] = []
    for r in rows:
        subj = (r["subject_code"] or "").lower()
        score_pref = float(pref_map.get(subj, 1)) / 5.0  # 0.2-1.0
        # 根据学习时间越多，给 KP/MOD 越高「适合学习」打分
        time_bonus = min(weekly_hours / 10.0, 1.5)
        score = round(score_pref * 0.6 + (0.2 if r["label"] != "KnowledgePoint" else 0.15) * time_bonus + 0.1, 4)
        reason_bits = [f"学科偏好：{subj or '通用'} ×{pref_map.get(subj,1)}"]
        if subj in level_map:
            reason_bits.append(f"历史定级：{level_map[subj]}")
        # 前置关系
        pres = await fetch_all(
            "SELECT p.code FROM graph_edge e JOIN graph_node p ON p.id=e.from_node_id "
            "WHERE e.to_node_id=%s AND e.rel_type='PREREQUISITE' AND e.yn=1",
            (r["id"],),
        )
        pre_codes = [p["code"] for p in pres]
        results.append(RecommendedCourse(
            item_type={"CourseSeries": "SERIES", "CourseModule": "MODULE", "KnowledgePoint": "KNOWLEDGE_POINT"}[r["label"]],
            item_code=r["code"],
            item_name=r["name"],
            subject_code=r["subject_code"],
            level_code=level_map.get(subj),
            score=float(score),
            reason="；".join(reason_bits) or "冷启动默认推荐",
            estimated_hours=(weekly_hours / 5.0 if r["label"] == "CourseSeries" else None),
            prerequisite_codes=pre_codes,
        ))
    results.sort(key=lambda x: (-x.score, x.item_code))
    return results[:top_n]


# ============================================================
# 3. 策略二：协同过滤（同画像用户的热门学习路径 → 给当前用户推荐）
# ============================================================

async def collaborative_filter(user_id: int, profile: dict[str, Any] | None = None,
                                top_n: int = 15) -> list[RecommendedCourse]:
    """同画像 (同学习风格 / 同年级 / 同等级) 用户的 P3 行为热门 TOP-N。

    规则：先找画像相似 TOP 50 他人；再统计他们的 P3 学习次数 (video ticks+hw+exam 合并)；归并为得分。
    """
    profile = profile or await _load_profile(user_id)
    style = profile.get("study_style") or "mixed"
    grade = profile.get("grade_code") or ""
    subj_level: list[tuple[str, str]] = []
    for a in profile.get("level_assessments", []):
        if isinstance(a, dict):
            subj_level.append(((a.get("subject_code") or "").lower(), a.get("level_code") or "L2"))
    subj_level = subj_level[:3] or [("english", "L2")]
    # 相似用户 TOP 50（user_profile 字段 同 style / grade 的其他 user）
    similar_sql = (
        "SELECT SP.user_id FROM user_profile SP "
        "WHERE SP.user_id != %s AND SP.study_style = %s "
    )
    args: list[Any] = [user_id, style]
    if grade:
        similar_sql += " AND SP.grade_code = %s "
        args.append(grade)
    similar_sql += " ORDER BY SP.user_id DESC LIMIT 50"
    similar_rows = await fetch_all(similar_sql, tuple(args))
    peers = [int(r["user_id"]) for r in similar_rows]
    if not peers:
        return []

    # 统计 peers 在 KP 上的行为（session→module→KP）
    placeholders = ",".join(["%s"] * len(peers))
    rows = await fetch_all(
        f"""
        SELECT K.code, K.name, K.subject_code, K.id,
               (COUNT(DISTINCT V.id) + COUNT(DISTINCT H.id) + 5 * COUNT(DISTINCT X.id)) AS freq
        FROM graph_node K
        JOIN graph_edge E ON E.to_node_id = K.id AND E.rel_type = 'CONTAINS' AND E.yn = 1
        JOIN graph_node M ON M.id = E.from_node_id AND M.label = 'CourseModule'
        LEFT JOIN curriculum_module CM ON CM.module_code = M.code AND CM.yn = 1
        LEFT JOIN curriculum_session CS ON CS.module_id = CM.id AND CS.yn = 1
        LEFT JOIN session_video_play_event V ON V.session_id = CS.id AND V.user_id IN ({placeholders})
        LEFT JOIN session_homework_submission H ON H.session_id = CS.id AND H.user_id IN ({placeholders})
        LEFT JOIN session_exam_submission X ON X.user_id IN ({placeholders}) AND JSON_LENGTH(X.answers_json) > 0
        WHERE K.label = 'KnowledgePoint' AND K.yn = 1
        GROUP BY K.id
        HAVING freq > 0
        ORDER BY freq DESC
        LIMIT %s
        """,
        tuple([*peers, *peers, *peers, top_n]),
    )
    if not rows:
        return []
    max_freq = max(int(r["freq"] or 1) for r in rows) or 1
    out: list[RecommendedCourse] = []
    for r in rows:
        score = round(float(r["freq"] or 0) / float(max_freq) * 0.9 + 0.05, 4)
        out.append(RecommendedCourse(
            item_type="KNOWLEDGE_POINT",
            item_code=r["code"],
            item_name=r["name"],
            subject_code=r["subject_code"],
            score=score,
            reason=f"同画像 {len(peers)} 位同学热门：热度 {int(r['freq'] or 0)}",
        ))
    return out


# ============================================================
# 4. 策略三：图谱遍历（找「所有先修都已掌握或不缺」→ 最可走的下一步节点）
# ============================================================

async def graph_traverse_recommend(user_id: int, mastery: dict[str, float] | None = None,
                                    top_n: int = 15) -> list[RecommendedCourse]:
    """从所有 KP 出发，挑满足 prereq≥threshold 的候选，按 (1-mastery)×权重推荐。"""
    mastery = mastery if mastery is not None else await _load_mastery_by_kp_code(user_id)
    # 取所有 KP + 它们的前置（可能没有，那 prereq 必满足）
    all_kp = await fetch_all(
        "SELECT K.id, K.code, K.name, K.subject_code, K.sort_no, K.properties_json "
        "FROM graph_node K WHERE K.label = 'KnowledgePoint' AND K.yn = 1",
    )
    prereqs = await fetch_all(
        "SELECT E.to_node_id AS kp_id, P.code AS pre_code "
        "FROM graph_edge E JOIN graph_node P ON P.id = E.from_node_id "
        "WHERE E.rel_type = 'PREREQUISITE' AND E.yn = 1 AND P.label = 'KnowledgePoint'",
    )
    by_kp: dict[int, list[str]] = {}
    for p in prereqs:
        by_kp.setdefault(int(p["kp_id"]), []).append(p["pre_code"])

    candidates: list[RecommendedCourse] = []
    for kp in all_kp:
        pres = by_kp.get(int(kp["id"]), [])
        if not pres:
            prereq_score = 1.0
        else:
            pres_mastery = [mastery.get(c, 0.0) for c in pres]
            prereq_score = float(sum(pres_mastery)) / float(len(pres))
        current_mastery = mastery.get(kp["code"], 0.0)
        # 只推荐尚未掌握（mastery < 0.9）且先修掌握 ≥ 0.6 的
        if current_mastery >= 0.9:
            continue
        if prereq_score < 0.6 and pres:
            # 先修不足也可作为「提醒先学的前置节点」，但打低分
            score = round(prereq_score * 0.3 + max(0.0, 0.5 - current_mastery) * 0.2, 4)
            reason = f"先修掌握不足（{prereq_score:.0%}），建议先补前置：{', '.join(pres[:3])}"
        else:
            score = round(prereq_score * 0.5 + (1 - current_mastery) * 0.5, 4)
            reason = (f"先修满足 {prereq_score:.0%}；当前掌握 {current_mastery:.0%} → 适合下一步学习"
                      if pres else "无前置要求，可直接开始")
        candidates.append(RecommendedCourse(
            item_type="KNOWLEDGE_POINT",
            item_code=kp["code"],
            item_name=kp["name"],
            subject_code=kp["subject_code"],
            score=float(score),
            reason=reason,
            prerequisite_codes=pres,
            mastery_ratio=current_mastery,
        ))
    candidates.sort(key=lambda x: (-x.score, x.item_code))
    return candidates[:top_n]


# ============================================================
# 5. hybrid_rank 三路融合 + 反馈分数偏移
# ============================================================

async def hybrid_rank(user_id: int, *, top_n: int = 8, for_scene: str = "NEXT") -> NextStepOut:
    profile = await _load_profile(user_id)
    mastery = await _load_mastery_by_kp_code(user_id)
    cold_items = {c.item_code: c for c in await cold_start_recommend(user_id, profile=profile, top_n=30)}
    cf_items = {c.item_code: c for c in await collaborative_filter(user_id, profile=profile, top_n=30)}
    graph_items = {c.item_code: c for c in await graph_traverse_recommend(user_id, mastery=mastery, top_n=30)}
    feedback = await _load_feedback_deltas(user_id, for_scene)

    all_keys = set(cold_items) | set(cf_items) | set(graph_items)
    merged: dict[str, RecommendedCourse] = {}
    for code in all_keys:
        base = cold_items.get(code) or cf_items.get(code) or graph_items.get(code)
        score = 0.0
        if code in cold_items:  score += WEIGHT_COLD   * cold_items[code].score
        if code in cf_items:    score += WEIGHT_CF     * cf_items[code].score
        if code in graph_items: score += WEIGHT_GRAPH  * graph_items[code].score
        fb = float(feedback.get("NODE:" + code, feedback.get(code, 0.0)))
        fb_term = fb * WEIGHT_FEEDBACK
        score = round(min(max(score + fb_term, 0.0), 1.0), 4)
        reasons = []
        if code in cold_items:  reasons.append(f"冷启动:{cold_items[code].reason[:30]}")
        if code in cf_items:    reasons.append("协同:同画像热门")
        if code in graph_items: reasons.append("图谱:先修满足→下一步")
        assert base is not None
        merged[code] = RecommendedCourse(
            item_type=base.item_type,
            item_code=base.item_code,
            item_name=base.item_name,
            subject_code=base.subject_code,
            level_code=base.level_code,
            score=score,
            reason=" | ".join(reasons) or base.reason,
            estimated_hours=base.estimated_hours,
            prerequisite_codes=graph_items[code].prerequisite_codes if code in graph_items else base.prerequisite_codes,
            mastery_ratio=mastery.get(code, 0.0),
        )
    items = sorted(merged.values(), key=lambda x: (-x.score, x.item_code))[:top_n]
    return NextStepOut(
        items=items,
        strategy_weights={
            "cold_start": WEIGHT_COLD,
            "collaborative_filter": WEIGHT_CF,
            "graph_traverse": WEIGHT_GRAPH,
            "feedback_delta": WEIGHT_FEEDBACK,
        },
    )


# ============================================================
# 6. 生成完整学习路径（GET /api/recommend/path）
# ============================================================

async def build_learning_path(user_id: int, subject_code: str | None = None,
                               target_level: str | None = None, *, save: bool = True) -> LearningPath:
    """针对某学科按先修链构建有序学习路径。步骤：
       ① 按 subject_code 过滤 KP → 拓扑排序（按 PREREQUISITE 边）得到线性顺序；
       ② 按 KP 聚合成 MODULE 级 6-10 个 step 的 PathNode；
       ③ 若 save 则 INSERT learning_path_instance（含 nodes_json 快照）。"""
    # 1) 选学科 & 目标等级
    profile = await _load_profile(user_id)
    subj = (subject_code or "").lower()
    if not subj:
        # 冷启动：subject_preferences 里 score 最高的学科
        best = max(profile.get("subject_preferences", []) or [],
                   key=lambda p: int(p.get("preference_score") or 0) if isinstance(p, dict) else 0, default=None)
        subj = (best.get("subject_code") or "english").lower() if isinstance(best, dict) else "english"
    if not target_level:
        for a in profile.get("level_assessments", []):
            if isinstance(a, dict) and (a.get("subject_code") or "").lower() == subj:
                # 目标等级 = 当前 +1
                curr_lv = a.get("level_code") or "L1"
                try:
                    idx = max(DEFAULT_SUBJECT_LEVELS.index(curr_lv), 0)
                except ValueError:
                    idx = 1
                target_level = DEFAULT_SUBJECT_LEVELS[min(idx + 1, len(DEFAULT_SUBJECT_LEVELS) - 1)]
                break
        target_level = target_level or "L3"
    weekly_hours = int(profile.get("weekly_available_hours") or 5)

    # 2) 拓扑排序：subject/subject_code 下 KP 按 PREREQUISITE 从左到右
    kp_rows = await fetch_all(
        "SELECT K.id, K.code, K.name, K.subject_code, K.sort_no FROM graph_node K "
        "WHERE K.label='KnowledgePoint' AND K.yn=1 AND (LOWER(K.subject_code) = %s OR 1=1) ORDER BY K.sort_no",
        (subj,),  # OR 1=1 fallback：任意学科都可用（打靶时 subject 可能混）
    )
    # 过滤同 subject 优先，若无同 subject 就全量 KP
    filtered = [k for k in kp_rows if (k["subject_code"] or "").lower() == subj] or kp_rows
    id_map = {int(k["id"]): k for k in filtered}
    # prerequisite in edges（from → to；from 必须先于 to）→ 对每个 target 累加 indegree
    edges = await fetch_all(
        "SELECT from_node_id AS fid, to_node_id AS tid FROM graph_edge "
        "WHERE rel_type='PREREQUISITE' AND yn=1 AND from_node_id IN (%s) AND to_node_id IN (%s)" % (
            ",".join(str(k["id"]) for k in filtered) or "NULL",
            ",".join(str(k["id"]) for k in filtered) or "NULL",
        ),
    )
    indeg: dict[int, int] = {int(k["id"]): 0 for k in filtered}
    children: dict[int, list[int]] = {int(k["id"]): [] for k in filtered}
    for e in edges:
        f, t = int(e["fid"]), int(e["tid"])
        if f in indeg and t in indeg:
            indeg[t] += 1
            children[f].append(t)
    # Kahn 拓扑；同层按 sort_no
    import heapq
    heap: list[tuple[int, int]] = []  # (sort_no, id)
    for kpid, deg in indeg.items():
        if deg == 0:
            heapq.heappush(heap, (int(id_map[kpid]["sort_no"]), kpid))
    order_ids: list[int] = []
    while heap:
        _, nid = heapq.heappop(heap)
        order_ids.append(nid)
        for ch in sorted(children[nid], key=lambda x: int(id_map[x]["sort_no"])):
            indeg[ch] -= 1
            if indeg[ch] == 0:
                heapq.heappush(heap, (int(id_map[ch]["sort_no"]), ch))
    order_ids = order_ids or [int(k["id"]) for k in filtered]

    # 3) 把 KP 序列分 step：每块 2-4 KP = 一个 PathNode
    ordered_kp = [id_map[i] for i in order_ids]
    CHUNK = max(2, min(4, max(1, len(ordered_kp) // 6))) if ordered_kp else 2
    chunks: list[list[dict]] = []
    for i in range(0, len(ordered_kp), CHUNK):
        chunks.append(ordered_kp[i:i + CHUNK])
    if not chunks:
        # 兜底：给一个默认块
        chunks = [[{"id": 0, "code": "KP-DEFAULT-" + subj, "name": f"{subj} 学科入门", "sort_no": 0}]]

    total_hrs = 0.0
    nodes: list[PathNode] = []
    for i, chunk in enumerate(chunks, start=1):
        hrs = round(float(weekly_hours) * (2.0 / 5.0) * max(1, len(chunk) / 2.0), 1)
        hrs = max(1.0, hrs)
        total_hrs += hrs
        pres: list[str] = []
        for kp in chunk:
            pre_rows = await fetch_all(
                "SELECT P.code FROM graph_edge E JOIN graph_node P ON P.id=E.from_node_id "
                "WHERE E.to_node_id=%s AND E.rel_type='PREREQUISITE' AND E.yn=1",
                (kp["id"],),
            )
            for p in pre_rows:
                if p["code"] not in pres:
                    pres.append(p["code"])
        title = " → ".join(kp["name"] for kp in chunk) or f"第 {i} 步"
        suggestion = (f"建议本周花 {hrs:.1f}h：先看对应课次视频，再完成 {len(chunk)} 个知识点的课后练习；"
                      f"完成后提交相关试卷以评估掌握度。")
        nodes.append(PathNode(
            step_no=i,
            node_type="KNOWLEDGE_POINT",
            node_code="-".join(kp["code"] for kp in chunk) or f"STEP-{i}",
            node_name=f"第 {i} 步：{title[:20]}{'…' if len(title) > 20 else ''}",
            subject_code=chunk[0].get("subject_code") if chunk else None,
            duration_hours=float(hrs),
            suggestion=suggestion,
            prerequisite_codes=pres,
        ))

    title = f"{subj.upper()} {target_level} 学习路径（{len(nodes)} 步，约 {total_hrs:.1f}h）"
    rationale = (f"基于画像：学科偏好/目标等级={subj}/{target_level}；每周可投入 {weekly_hours}h；"
                 f"按图谱 PREREQUISITE 拓扑排 {len(ordered_kp)} 个知识点 → {len(nodes)} 步。")

    path_code = "LP-" + hashlib.sha1(
        f"{user_id}:{subj}:{target_level}:{datetime.now().strftime('%Y%m%d%H%M%S')}".encode("utf-8"),
    ).hexdigest()[:12].upper()

    saved_instance_id: int | None = None
    if save:
        ins_id = await execute_write(
            "INSERT INTO learning_path_instance "
            "(user_id, path_code, title, subject_code, total_sessions, total_hours, nodes_json, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())",
            (
                user_id, path_code, title, subj, sum(1 for n in nodes),
                float(round(total_hrs, 2)),
                json.dumps([n.model_dump(mode="json") for n in nodes], ensure_ascii=False),
            ),
        )
        saved_instance_id = int(ins_id) if ins_id else None

    return LearningPath(
        path_code=path_code,
        title=title,
        subject_code=subj,
        target_level=target_level,
        total_sessions=len(nodes),
        total_hours=float(round(total_hrs, 2)),
        rationale=rationale,
        nodes=nodes,
        saved_instance_id=saved_instance_id,
    )


# ============================================================
# 7. 反馈（POST /api/recommend/feedback）
# ============================================================

FEEDBACK_DELTA = {
    "HELPFUL": +0.5,
    "NOT_INTERESTED": -1.0,
    "ALREADY_LEARNED": -0.7,
    "TOO_HARD": -0.4,
}


async def submit_feedback(user_id: int, payload: RecommendFeedbackIn) -> RecommendFeedbackOut:
    delta = FEEDBACK_DELTA.get(payload.feedback_type, 0.0)
    try:
        await execute_write(
            "INSERT INTO recommend_feedback "
            "(user_id, scene_code, target_id, feedback_type, score_delta, extra_json, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,NOW()) "
            "ON DUPLICATE KEY UPDATE score_delta=VALUES(score_delta), extra_json=VALUES(extra_json)",
            (
                user_id, payload.scene_code, payload.target_id, payload.feedback_type,
                float(delta),
                json.dumps({"note": payload.note}, ensure_ascii=False) if payload.note else None,
            ),
        )
    except Exception as e:  # pragma: no cover
        raise BizError(500001, f"反馈写入失败：{e}") from e
    return RecommendFeedbackOut(
        scene_code=payload.scene_code,
        target_id=payload.target_id,
        feedback_type=payload.feedback_type,
        score_delta=float(delta),
    )
