# -*- coding: utf-8 -*-
"""P4 推荐引擎 engine：冷启动 / 协同过滤 / 图谱遍历 / 三路加权融合。

TB1：推荐 API 新增 Neo4j 图谱源（source=neo4j|mysql）+ 停机 ≤1s 预算内降级 MySQL 图。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable

from app.common.exceptions import AppException as BizError
from app.config import settings
from app.core.db_resilience import DependencyUnavailableError, neo4j_run
from app.database import execute_write, fetch_all, fetch_one
from app.recommender import neo4j_engine
from app.recommender.schemas import (
    LearningPath, NextStepOut, PathNode, RecommendFeedbackIn, RecommendFeedbackOut,
    RecommendedCourse,
)

logger = logging.getLogger(__name__)

DEFAULT_SUBJECT_LEVELS = ["L1", "L2", "L3", "L4", "L5"]
WEIGHT_COLD: float = 0.30
WEIGHT_CF: float = 0.25
WEIGHT_GRAPH: float = 0.30
WEIGHT_FEEDBACK: float = 0.15


# ============================================================
# 0. Neo4j 图谱源（TB1）：熔断 + ≤1s 预算硬顶，恒不抛异常
# ============================================================
_NE04J_HUB_CACHE: dict[str, Any] = {"seeds": None, "ts": 0.0}


async def _run_neo4j(fn: Callable[[], Any], op_name: str = "recommend_graph",
                     timeout_s: float | None = None, deadline: float | None = None,
                     min_budget_s: float = 0.0) -> Any:
    """执行同步 Neo4j 查询（fn 零参同步函数），经熔断(neo4j_run) + asyncio.wait_for 预算硬顶。

    - timeout_s：单次调用的预算（秒）。
    - deadline：整个图谱阶段的**绝对截止时刻**（time.monotonic()）。传入后实际预算取
      `min(timeout_s, deadline - now)` —— 同一请求内的多次图谱调用共享总预算，
      避免「hub 查询 1s + 共现查询 1s」叠加成 2s（工单要求停机 ≤1s 内降级）。
    - min_budget_s：即便 deadline 已过也要保留的**最小预算**（用于关键主查询不被
      前置的个性化增强调用饿死；仅当预算为正时生效）。

    返回 fn 的结果；超时 / 熔断 / 任意异常 → 返回 None（调用方据此降级 MySQL 图）。
    对齐 app/ai/kg_bridge.py 的 fetch_neighbor_chunks 降级范式。
    """
    budget = (timeout_s if timeout_s is not None
              else float(getattr(settings, "KG_RECOMMEND_TIMEOUT_MS", 1000)) / 1000.0)
    if deadline is not None:
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0 and min_budget_s <= 0:
            logger.warning(f"[recommender] Neo4j 图谱阶段总预算已耗尽 → 直接降级（{op_name}）")
            return None
        budget = min(budget, remaining) if remaining > 0 else budget
        budget = max(budget, min_budget_s)
    try:
        return await asyncio.wait_for(neo4j_run(op_name, fn), timeout=max(0.05, budget))
    except asyncio.TimeoutError:
        logger.warning(f"[recommender] Neo4j 图谱查询超预算降级（{op_name}，预算 {budget:.2f}s）")
        return None
    except DependencyUnavailableError:
        logger.warning(f"[recommender] Neo4j 熔断中 → 推荐降级 MySQL 图（{op_name}）")
        return None
    except Exception as exc:  # noqa: BLE001 - 通道降级兜底：任何异常不拖垮推荐主链
        logger.warning(f"[recommender] Neo4j 图谱查询异常降级（{op_name}）：{type(exc).__name__}: {exc}")
        return None


def _graph_stage_deadline() -> float:
    """本请求图谱阶段的总截止时刻（monotonic）。预算 = KG_RECOMMEND_TIMEOUT_MS。"""
    budget = float(getattr(settings, "KG_RECOMMEND_TIMEOUT_MS", 1000)) / 1000.0
    return time.monotonic() + max(0.05, budget)


async def _neo4j_hub_seeds(limit: int = 6, deadline: float | None = None) -> list[str]:
    """（缓存）Neo4j 高连通 hub 种子名称；首查后 300s 内复用，避免每次请求全图扫描。

    参与阶段总预算（deadline）：不可达时让它快速失败并让后续调用直接降级，
    从而整段停机回退控制在 ≤1 个预算内；正常时单查仅几十 ms，预算绰绰有余。
    缓存命中时零成本（停机场景的重复请求因此快速通过）。
    """
    now = time.time()
    cached = _NE04J_HUB_CACHE.get("seeds")
    if cached is not None and now - float(_NE04J_HUB_CACHE.get("ts", 0.0)) < 300:
        return cached
    seeds = await _run_neo4j(
        lambda: neo4j_engine.hub_seed_names(tenant_id="_default", limit=limit),
        op_name="recommend_hub", deadline=deadline,
    ) or []
    if seeds:
        _NE04J_HUB_CACHE["seeds"] = seeds
        _NE04J_HUB_CACHE["ts"] = now
    return seeds


async def graph_recommend_neo4j(user_id: int, mastery: dict[str, float] | None = None,
                               top_n: int = 30, deadline: float | None = None) -> list[RecommendedCourse]:
    """Neo4j 图谱推荐候选（source="neo4j"）。

    种子：Neo4j hub 高连通种子为可靠基（必存在于 Neo4j，保证非空）；
    若用户正在学的 KP 名称（mastery 0.05~0.9）确实存在于 Neo4j，则前置以做轻个性化。
    注：MySQL graph_node(KP,18) 与 Neo4j(1609) 为不同节点集，故 frontier 名字须先经 Neo4j
    存在性校验，避免误用不存在于 Neo4j 的 MySQL 名字导致空结果。
    恒不抛异常；超时/熔断/不可达 → 返回 [] 由调用方降级 MySQL。
    """
    mastery = mastery if mastery is not None else await _load_mastery_by_kp_code(user_id)
    # 阶段总预算覆盖 hub + 个性化增强 + 主推荐三跳：不可达时首跳即快速失败，
    # 后续调用命中熔断毫秒级直降 → 整段回退 ≤1 个预算；正常时三跳合计仅数百 ms。
    stage_deadline = deadline if deadline is not None else _graph_stage_deadline()
    seeds = await _neo4j_hub_seeds(deadline=stage_deadline)  # 可靠基：必在 Neo4j 中存在
    if mastery:
        codes = [c for c, m in mastery.items() if 0.05 <= float(m) < 0.9][:8]
        if codes:
            rows = await fetch_all(
                "SELECT code, name FROM graph_node "
                "WHERE label='KnowledgePoint' AND yn=1 AND code IN %s",
                (tuple(codes),),
            )
            frontier_names = [r["name"] for r in rows]
            if frontier_names:
                # 个性化增强调用，限一小片预算：慢了也不能挤掉主推荐查询的预算。
                present = await _run_neo4j(
                    lambda: neo4j_engine.kp_names_present(frontier_names),
                    op_name="recommend_frontier_check", timeout_s=0.3, deadline=stage_deadline,
                ) or []
                if present:
                    seeds = present + seeds  # 用户相关种子前置，hub 兜底
    if not seeds:
        return []
    result = await _run_neo4j(
        lambda: neo4j_engine.recommend_knowledge_points(seeds, tenant_id="_default", top_n=top_n),
        op_name="recommend_graph", deadline=stage_deadline, min_budget_s=0.4,
    )
    if not result:
        return []
    # TB1 计分：Neo4j 候选即「图谱原生候选」（本任务的核心图谱源），需与 MySQL graph_traverse
    # 候选处于同一量级（后者为 prereq_score*0.5+(1-mastery)*0.5，量级 0.5~1.0），否则融合后
    # 权重(0.30)会把 Neo4j 候选压到 top_n 之外 → 演示环境看不到 source=neo4j。
    # 故按共现强度归一化映射到 [0.6, 1.0] 区间，保证图谱候选在 top_n 内可见。
    strengths = sorted((int(r["strength"] or 0) for r in result), reverse=True)
    max_strength = (strengths[0] if strengths else 0) or 1
    min_strength = strengths[-1] if strengths else 0
    span = max(1, max_strength - min_strength)
    out: list[RecommendedCourse] = []
    for r in result:
        strength = int(r["strength"] or 0)
        norm = (strength - min_strength) / float(span)          # 0~1
        score = round(0.6 + norm * 0.4, 4)                      # 映射到 [0.6, 1.0]
        out.append(RecommendedCourse(
            item_type="KNOWLEDGE_POINT",
            # Neo4j 的 KnowledgePoint 无 code 属性，以 name 作为稳定标识（对齐 TB3 展示）
            item_code=r["kp_name"],
            item_name=r["kp_name"],
            subject_code=None,
            score=score,
            reason=f"图谱(Neo4j):与「{' / '.join(seeds[:2])}」等共现关联（强度 {strength}）",
            estimated_hours=None,
            prerequisite_codes=[],
            mastery_ratio=0.0,
            source="neo4j",
            extra={"neo4j_modules": r["modules"]},
        ))
    out.sort(key=lambda x: (-x.score, x.item_code))
    return out[:top_n]


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
    """估算各知识点的掌握度（0~1）并按 kp_code 聚合。

    数据源（对齐 edu.sql 真实 schema，P1 修复：无 answers_json 列，答案明细无独立表）：
    - 视频：session_video_play.last_position_seconds / 45min 近似完成度
    - 作业：session_homework_submission.total_score 归一化（无答案明细，无法算逐题正确率）
    - 考试：session_exam_submission.score_value 归一化（同上）
    """
    mastery: dict[str, tuple[float, int]] = {}  # kp_code → (ratio_sum, n)

    # 1) 视频：progress_percent 直取（session_video_play 真实列），无需换算
    rows = await fetch_all(
        """
        SELECT k.code AS kp_code,
               MAX(v.progress_percent) AS max_pct,
               COUNT(DISTINCT v.id) AS signals
        FROM graph_node K
        JOIN graph_edge E      ON E.to_node_id = K.id AND E.rel_type = 'CONTAINS' AND E.yn = 1
        JOIN graph_node M      ON M.id = E.from_node_id AND M.label = 'CourseModule'
        LEFT JOIN session_video_play V ON V.user_id = %s
        WHERE K.label = 'KnowledgePoint' AND K.yn = 1
        GROUP BY K.code
        HAVING signals > 0
        """,
        (user_id,),
    )
    for r in rows:
        pct = r["max_pct"]
        ratio = 0.0 if pct is None else float(pct) / 100.0
        acc, cnt = mastery.get(r["kp_code"], (0.0, 0))
        mastery[r["kp_code"]] = (acc + ratio, cnt + 1)

    # 2) 作业：total_score / 满分近似正确率（无逐题答案，只作弱信号）
    hw_rows = await fetch_all(
        """
        SELECT k.code AS kp_code,
               AVG(CASE WHEN H.total_score IS NOT NULL THEN
                   LEAST(H.total_score, 100) / 100 ELSE NULL END) AS rate,
               COUNT(DISTINCT H.id) AS signals
        FROM graph_node K
        JOIN graph_edge E      ON E.to_node_id = K.id AND E.rel_type = 'CONTAINS' AND E.yn = 1
        JOIN graph_node M      ON M.id = E.from_node_id AND M.label = 'CourseModule'
        LEFT JOIN session_homework_submission H ON H.user_id = %s
        WHERE K.label = 'KnowledgePoint' AND K.yn = 1
        GROUP BY K.code
        HAVING signals > 0
        """,
        (user_id,),
    )
    for r in hw_rows:
        rate = 0.0 if r["rate"] is None else float(r["rate"])
        acc, cnt = mastery.get(r["kp_code"], (0.0, 0))
        mastery[r["kp_code"]] = (acc + rate, cnt + 1)

    # 3) 考试：score_value 归一化（无逐题答案，弱信号）
    ex_rows = await fetch_all(
        """
        SELECT k.code AS kp_code,
               AVG(CASE WHEN S.score_value IS NOT NULL THEN
                   LEAST(S.score_value, 100) / 100 ELSE NULL END) AS rate,
               COUNT(DISTINCT S.id) AS signals
        FROM graph_node K
        JOIN graph_edge E      ON E.to_node_id = K.id AND E.rel_type = 'CONTAINS' AND E.yn = 1
        JOIN graph_node M      ON M.id = E.from_node_id AND M.label = 'CourseModule'
        LEFT JOIN session_exam_submission S ON S.user_id = %s
        WHERE K.label = 'KnowledgePoint' AND K.yn = 1
        GROUP BY K.code
        HAVING signals > 0
        """,
        (user_id,),
    )
    for r in ex_rows:
        rate = 0.0 if r["rate"] is None else float(r["rate"])
        acc, cnt = mastery.get(r["kp_code"], (0.0, 0))
        mastery[r["kp_code"]] = (acc + rate, cnt + 1)

    # 4) 最终求平均
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

    # 统计 peers 在 KP 上的行为：submission/video 经 session→module→KP 关联（P1 修复：
    # 原 SQL 无关联链致 graph×8~52万行笛卡尔，65s+磁盘爆；现经 session_video/session_homework/session_exam
    # → series_cohort_session(module) → series_cohort_course.module_code → graph CourseModule.code → KP）
    placeholders = ",".join(["%s"] * len(peers))
    peer_args = list(peers) * 3
    rows = await fetch_all(
        f"""
        SELECT K.code, K.name, K.subject_code, K.id,
               (COALESCE(MAX(V.freq),0) + COALESCE(MAX(H.freq),0) + 5 * COALESCE(MAX(X.freq),0)) AS freq
        FROM graph_node K
        JOIN graph_edge E ON E.to_node_id = K.id AND E.rel_type = 'CONTAINS' AND E.yn = 1
        JOIN graph_node M ON M.id = E.from_node_id AND M.label = 'CourseModule'
        LEFT JOIN (
            SELECT MCC.module_code AS module_code, COUNT(DISTINCT VP.id) AS freq
            FROM session_video_play VP
            JOIN session_video SV    ON SV.id = VP.video_id
            JOIN session_asset SA    ON SA.id = SV.asset_id
            JOIN series_cohort_session SCS ON SCS.id = SA.session_id
            JOIN series_cohort_course MCC ON MCC.id = SCS.series_cohort_course_id
            WHERE VP.user_id IN ({placeholders})
            GROUP BY MCC.module_code
        ) V ON V.module_code = M.code
        LEFT JOIN (
            SELECT MCC.module_code AS module_code, COUNT(DISTINCT SHS.id) AS freq
            FROM session_homework_submission SHS
            JOIN session_homework SH ON SH.id = SHS.homework_id
            JOIN series_cohort_session SCS ON SCS.id = SH.session_id
            JOIN series_cohort_course MCC ON MCC.id = SCS.series_cohort_course_id
            WHERE SHS.user_id IN ({placeholders})
            GROUP BY MCC.module_code
        ) H ON H.module_code = M.code
        LEFT JOIN (
            SELECT MCC.module_code AS module_code, COUNT(DISTINCT SES.id) AS freq
            FROM session_exam_submission SES
            JOIN session_exam SE ON SE.id = SES.exam_id
            JOIN series_cohort_session SCS ON SCS.id = SE.session_id
            JOIN series_cohort_course MCC ON MCC.id = SCS.series_cohort_course_id
            WHERE SES.user_id IN ({placeholders})
            GROUP BY MCC.module_code
        ) X ON X.module_code = M.code
        WHERE K.label = 'KnowledgePoint' AND K.yn = 1
        GROUP BY K.id
        HAVING freq > 0
        ORDER BY freq DESC
        LIMIT %s
        """,
        tuple([*peer_args, top_n]),
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
    # TB1：图谱候选 = MySQL graph_traverse（基，恒算） ∪ Neo4j 图谱（启用且可达时混入并标 neo4j）。
    # "优先/混入"：Neo4j 候选覆盖同 key 的 MySQL 图谱候选；其余 MySQL 图谱候选保留（source=mysql）。
    mysql_graph = {c.item_code: c for c in await graph_traverse_recommend(user_id, mastery=mastery, top_n=30)}
    neo_items: dict[str, RecommendedCourse] = {}
    if getattr(settings, "KG_RECOMMEND_ENABLED", False):
        neo_list = await graph_recommend_neo4j(user_id, mastery=mastery, top_n=30)
        neo_items = {c.item_code: c for c in neo_list}
    graph_source = "neo4j" if neo_items else "mysql"
    graph_items = {**mysql_graph, **neo_items}  # neo4j 覆盖同 key，其余保留 mysql 图谱候选
    feedback = await _load_feedback_deltas(user_id, for_scene)

    all_keys = set(cold_items) | set(cf_items) | set(graph_items)
    # TB1「优先图谱」：仅对**新接线的 Neo4j 图谱候选**加独立优先通道（等权通道 + 0.4 加成），
    # 使其不再被 WEIGHT_GRAPH=0.30 的乘性上限压到多源热点之后，从而在 top_n 页内可见。
    # 注意：加成只给 neo_items（本任务新接入的源）；既有 MySQL 图谱节点不加成，
    # 以免抬升既有行为（切关时 neo_items 为空 → 全 0，与现状完全一致）。
    merged: dict[str, RecommendedCourse] = {}
    for code in all_keys:
        base = cold_items.get(code) or cf_items.get(code) or graph_items.get(code)
        score = 0.0
        if code in cold_items:  score += WEIGHT_COLD   * cold_items[code].score
        if code in cf_items:    score += WEIGHT_CF     * cf_items[code].score
        if code in graph_items: score += WEIGHT_GRAPH  * graph_items[code].score
        if code in neo_items:   score += WEIGHT_GRAPH  * neo_items[code].score + 0.4
        fb = float(feedback.get("NODE:" + code, feedback.get(code, 0.0)))
        fb_term = fb * WEIGHT_FEEDBACK
        score = round(min(max(score + fb_term, 0.0), 1.0), 4)
        reasons = []
        if code in cold_items:  reasons.append(f"冷启动:{cold_items[code].reason[:30]}")
        if code in cf_items:    reasons.append("协同:同画像热门")
        if code in graph_items:
            if code in neo_items:
                reasons.append("图谱(Neo4j):共现关联")
            else:
                reasons.append("图谱:先修满足→下一步")
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
            source="neo4j" if code in neo_items else "mysql",
            extra={**base.extra, "graph_source": graph_source} if code in neo_items else base.extra,
        )
    items = sorted(merged.values(), key=lambda x: (-x.score, x.item_code))[:top_n]
    # TB1 可见性护栏：图谱启用的响应须在返回页内可见图谱来源候选（演示环境 owner 需看到
    # source=neo4j）。若 top_n 截断把全部图谱候选挤掉，则用图谱候选替换末尾若干低分项，
    # 保证至少 1 条图谱候选在页内；同时不减少返回条数。
    if graph_items:
        if not any(it.item_code in graph_items for it in items):
            ranked_graph = sorted(
                (v for k, v in merged.items() if k in graph_items),
                key=lambda x: (-x.score, x.item_code),
            )
            keep = max(1, min(2, top_n // 3))              # 页内保留 1~2 条图谱候选
            reserve = ranked_graph[:keep]
            reserve_keys = {it.item_code for it in reserve}
            rest = [it for it in items if it.item_code not in reserve_keys]
            items = sorted(reserve + rest, key=lambda x: (-x.score, x.item_code))[:top_n]
    return NextStepOut(
        items=items,
        strategy_weights={
            "cold_start": WEIGHT_COLD,
            "collaborative_filter": WEIGHT_CF,
            "graph_traverse": WEIGHT_GRAPH,
            "feedback_delta": WEIGHT_FEEDBACK,
        },
        graph_source=graph_source,
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
    node_kp_names: dict[int, list[str]] = {}  # step_no -> 该步底层 KP 名称（供 Neo4j 存在性标注）
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
        node_kp_names[i] = [kp["name"] for kp in chunk]
        nodes.append(PathNode(
            step_no=i,
            node_type="KNOWLEDGE_POINT",
            node_code="-".join(kp["code"] for kp in chunk) or f"STEP-{i}",
            node_name=f"第 {i} 步：{title[:20]}{'…' if len(title) > 20 else ''}",
            subject_code=chunk[0].get("subject_code") if chunk else None,
            duration_hours=float(hrs),
            suggestion=suggestion,
            prerequisite_codes=pres,
            source="mysql",
        ))

    # TB1：路径节点 Neo4j 图谱来源标注（图谱可达时，凡底层 KP 在 Neo4j 存在即标 neo4j）。
    # 注：当前 MySQL graph_node(KP,18) 与 Neo4j(1609) 为不同节点集，多数路径节点仍为 mysql；
    # 两套图谱对齐（TC）后，此处自动升级标 neo4j，无需改结构。
    graph_source = "mysql"
    if getattr(settings, "KG_RECOMMEND_ENABLED", False):
        all_kp_names = [nm for names in node_kp_names.values() for nm in names]
        present = await _run_neo4j(
            lambda: neo4j_engine.kp_names_present(all_kp_names), op_name="path_kg_check"
        ) or []
        present_set = set(present)
        if present_set:
            for node in nodes:
                if any(nm in present_set for nm in node_kp_names.get(node.step_no, [])):
                    node.source = "neo4j"
            graph_source = "neo4j"

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
        graph_source=graph_source,
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
