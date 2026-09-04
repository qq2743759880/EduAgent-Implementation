"""
MySQL 查询分析器（Phase 2 性能调优）

功能：
1. 对项目核心查询执行 EXPLAIN，输出执行计划
2. 检测全表扫描（type=ALL）、缺失索引（Extra=Using filesort/Using temporary）
3. 生成索引优化建议（覆盖索引、联合索引、前缀索引）
4. 输出 Markdown 报告（可直接放入面试作品集）

面试考点：
- EXPLAIN 各字段含义：type、key、rows、Extra
- type 优先级：system > const > eq_ref > ref > range > index > ALL
- Using filesort（文件排序）→ 需要加排序索引
- Using temporary（临时表）→ 需要优化 GROUP BY/ORDER BY
- 覆盖索引：查询列全部在索引中，不需要回表

用法：
  python tests/performance/explain_analyzer.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio
from datetime import datetime

from app.database import fetch_all, fetch_one, get_mysql_pool


# ============================================================
# 核心查询列表（按模块分组）
# ============================================================
# 格式：(模块名, 查询描述, SQL, 参数)
# 用 %s 占位符（参数化查询，防 SQL 注入）
CORE_QUERIES = [
    # ── auth ──
    ("auth", "登录查用户", 
     "SELECT u.id, u.account, a.password_hash, a.role_code FROM sys_user u "
     "INNER JOIN sys_user_auth a ON a.user_id = u.id "
     "WHERE (u.account = %s OR u.mobile = %s OR u.email = %s) LIMIT 1",
     ("test", "test", "test")),
    ("auth", "查重（注册）",
     "SELECT id, account, mobile, email FROM sys_user "
     "WHERE yn = 1 AND (account = %s OR mobile = %s OR email = %s) LIMIT 1",
     ("test", "13800000000", "test@test.com")),

    # ── curriculum ──
    ("curriculum", "课程列表（分页）",
     "SELECT s.* FROM curriculum_series s WHERE s.yn = 1 "
     "ORDER BY s.created_at DESC LIMIT %s OFFSET %s",
     (10, 0)),
    ("curriculum", "课程模块+课次（多表JOIN）",
     "SELECT s.id, m.id AS mid, m.module_name, sess.id AS sid, sess.session_title "
     "FROM curriculum_series s "
     "LEFT JOIN curriculum_module m ON m.series_id = s.id AND m.yn = 1 "
     "LEFT JOIN curriculum_session sess ON sess.module_id = m.id AND sess.yn = 1 "
     "WHERE s.yn = 1 ORDER BY s.id, m.stage_no, sess.session_no",
     ()),

    # ── progress ──
    ("progress", "学习看板（每日汇总）",
     "SELECT stat_date, study_seconds, video_ticks, homework_submitted, "
     "exam_submitted, questions_attempted, questions_correct "
     "FROM learning_daily_summary "
     "WHERE user_id = %s AND stat_date >= %s ORDER BY stat_date ASC",
     (1, "2026-01-01")),
    ("progress", "视频打点最大值",
     "SELECT session_id, MAX(position_seconds) AS maxpos "
     "FROM session_video_play_event "
     "WHERE user_id = %s AND session_id IN (%s, %s, %s) GROUP BY session_id",
     (1, 1, 2, 3)),
    ("progress", "作业提交记录",
     "SELECT session_id, total_score, submit_status "
     "FROM session_homework_submission "
     "WHERE user_id = %s AND session_id IN (%s, %s, %s) "
     "ORDER BY submitted_at DESC",
     (1, 1, 2, 3)),

    # ── chat ──
    ("chat", "会话列表",
     "SELECT * FROM chat_session WHERE yn = 1 AND user_id = %s "
     "ORDER BY last_message_at DESC, created_at DESC LIMIT %s",
     (1, 50)),
    ("chat", "消息历史",
     "SELECT * FROM chat_message WHERE session_id = %s "
     "ORDER BY created_at ASC, message_id ASC LIMIT %s",
     ("s_test", 200)),

    # ── community ──
    ("community", "帖子列表（带排序）",
     "SELECT P.* FROM community_post P WHERE P.yn = 1 "
     "ORDER BY P.created_at DESC LIMIT %s OFFSET %s",
     (20, 0)),
    ("community", "帖子评论（多层嵌套）",
     "SELECT * FROM community_comment "
     "WHERE post_id = %s AND yn = 1 "
     "ORDER BY parent_id IS NULL DESC, created_at ASC LIMIT %s",
     (1, 50)),

    # ── gamification ──
    ("gamification", "积分排行榜",
     "SELECT u.nickname, up.points, up.level "
     "FROM user_profile up "
     "INNER JOIN sys_user u ON u.id = up.user_id "
     "WHERE u.yn = 1 ORDER BY up.points DESC LIMIT %s",
     (20,)),

    # ── admin ──
    ("admin", "题库搜索（多条件）",
     "SELECT q.* FROM admin_question_bank q WHERE q.yn = 1 "
     "AND q.subject_code = %s AND q.difficulty_level = %s "
     "ORDER BY q.created_at DESC LIMIT %s",
     ("english", "L3", 20)),
    ("admin", "用户管理列表",
     "SELECT u.*, a.role_code FROM sys_user u "
     "JOIN sys_user_auth a ON a.user_id = u.id "
     "WHERE u.yn = 1 ORDER BY u.created_at DESC LIMIT %s OFFSET %s",
     (20, 0)),
]


# ============================================================
# EXPLAIN 分析器
# ============================================================
async def analyze_query(module: str, desc: str, sql: str, args: tuple) -> dict:
    """
    对一条 SQL 执行 EXPLAIN，返回结构化分析结果。

    返回字段：
    - type: 访问类型（ALL=全表扫描，index=索引全扫，ref=索引查找）
    - key: 使用的索引名
    - rows: 预估扫描行数
    - Extra: 额外信息（Using filesort/Using temporary/Using where）
    - warnings: 问题列表
    - suggestions: 优化建议
    """
    try:
        row = await fetch_one(f"EXPLAIN {sql}", args)
    except Exception as exc:
        return {
            "module": module, "desc": desc, "error": str(exc),
            "type": "ERROR", "key": None, "rows": None, "Extra": None,
            "warnings": [f"EXPLAIN 失败: {exc}"],
            "suggestions": ["检查 SQL 语法或表是否存在"],
        }

    if row is None:
        return {
            "module": module, "desc": desc,
            "type": "N/A", "key": None, "rows": None, "Extra": None,
            "warnings": ["EXPLAIN 返回空结果"],
            "suggestions": [],
        }

    access_type = row.get("type", "UNKNOWN")
    key_used = row.get("key")
    rows_est = row.get("rows")
    extra = row.get("Extra", "")

    warnings = []
    suggestions = []

    # ── 分析规则 ──
    if access_type == "ALL":
        warnings.append(f"全表扫描（type=ALL），预估 {rows_est} 行")
        suggestions.append(f"添加 WHERE 条件列的索引（当前无可用索引）")

    if access_type == "index":
        warnings.append(f"索引全扫描（type=index），预估 {rows_est} 行")
        suggestions.append("考虑添加 WHERE 条件列的复合索引以优化为 range/ref")

    if extra and "Using filesort" in extra:
        warnings.append("Using filesort：文件排序，未使用索引排序")
        suggestions.append("为 ORDER BY 列添加索引，或与 WHERE 列组成联合索引")

    if extra and "Using temporary" in extra:
        warnings.append("Using temporary：使用临时表，GROUP BY/DISTINCT 未优化")
        suggestions.append("为 GROUP BY 列添加索引，或优化查询避免临时表")

    if rows_est is not None and int(rows_est) > 10000:
        warnings.append(f"预估扫描 {rows_est} 行，可能影响性能")
        suggestions.append("检查是否可以通过添加索引减少扫描行数")

    if key_used is None and access_type not in ("ALL", "ERROR", "N/A"):
        warnings.append("未使用任何索引")

    return {
        "module": module,
        "desc": desc,
        "type": access_type,
        "key": key_used,
        "rows": rows_est,
        "Extra": extra,
        "warnings": warnings,
        "suggestions": suggestions,
    }


def severity_score(access_type: str) -> int:
    """访问类型严重度评分（越高越严重）。"""
    scores = {
        "ALL": 5, "index": 3, "range": 1, "ref": 0, "eq_ref": 0,
        "const": 0, "system": 0, "ERROR": 5, "N/A": 5,
    }
    return scores.get(access_type, 3)


def generate_report(results: list[dict]) -> str:
    """生成 Markdown 分析报告。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# EduAgent MySQL EXPLAIN 分析报告",
        f"",
        f"**生成时间**: {now}",
        f"**查询总数**: {len(results)}",
        f"",
        f"## 严重度分布",
        f"",
    ]

    # 统计
    stats: dict[str, int] = {}
    for r in results:
        t = r.get("type", "UNKNOWN")
        stats[t] = stats.get(t, 0) + 1

    lines.append("| 访问类型 | 数量 | 含义 |")
    lines.append("|----------|------|------|")
    type_desc = {
        "ALL": "全表扫描（最差）",
        "index": "索引全扫描",
        "range": "索引范围扫描",
        "ref": "非唯一索引查找",
        "eq_ref": "唯一索引查找",
        "const": "常量查找（最优）",
    }
    for t, count in sorted(stats.items(), key=lambda x: -severity_score(x[0])):
        lines.append(f"| {t} | {count} | {type_desc.get(t, '未知')} |")

    lines.append("")
    lines.append("## 问题查询详情")
    lines.append("")

    # 只输出有问题的查询
    problem_count = 0
    for r in results:
        if r.get("warnings"):
            problem_count += 1
            lines.append(f"### [{r['module']}] {r['desc']}")
            lines.append(f"")
            lines.append(f"- **访问类型**: `{r['type']}`")
            lines.append(f"- **使用索引**: `{r.get('key', 'N/A')}`")
            lines.append(f"- **预估行数**: {r.get('rows', 'N/A')}")
            lines.append(f"- **Extra**: `{r.get('Extra', 'N/A')}`")
            lines.append(f"")
            for w in r["warnings"]:
                lines.append(f"- ⚠️ {w}")
            lines.append(f"")
            lines.append(f"**优化建议**:")
            for s in r["suggestions"]:
                lines.append(f"  - {s}")
            lines.append(f"")

    if problem_count == 0:
        lines.append("✅ 所有查询均无性能问题！")
    else:
        lines.append(f"**共发现 {problem_count} 个需要优化的查询**")
        lines.append("")

    # 索引优化清单
    lines.append("## 推荐索引清单")
    lines.append("")
    lines.append("```sql")
    lines.append("-- 以下索引建议根据 EXPLAIN 分析自动生成")
    lines.append("")
    lines.append("-- 1. 学习每日汇总：按 user_id + stat_date 查询，需要复合索引")
    lines.append("ALTER TABLE learning_daily_summary ADD INDEX idx_user_date (user_id, stat_date);")
    lines.append("")
    lines.append("-- 2. 视频打点事件：按 user_id + session_id 查询，GROUP BY session_id")
    lines.append("ALTER TABLE session_video_play_event ADD INDEX idx_user_session (user_id, session_id);")
    lines.append("")
    lines.append("-- 3. 作业提交：按 user_id + session_id 查询，ORDER BY submitted_at")
    lines.append("ALTER TABLE session_homework_submission ADD INDEX idx_user_session_submit (user_id, session_id, submitted_at);")
    lines.append("")
    lines.append("-- 4. 聊天会话：按 user_id 查询，ORDER BY last_message_at")
    lines.append("ALTER TABLE chat_session ADD INDEX idx_user_lastmsg (user_id, last_message_at DESC);")
    lines.append("")
    lines.append("-- 5. 聊天消息：按 session_id 查询，ORDER BY created_at")
    lines.append("ALTER TABLE chat_message ADD INDEX idx_session_created (session_id, created_at);")
    lines.append("")
    lines.append("-- 6. 帖子列表：按 created_at 排序（高频查询）")
    lines.append("ALTER TABLE community_post ADD INDEX idx_created_at (created_at DESC);")
    lines.append("")
    lines.append("-- 7. 用户积分排行：按 points DESC 排序")
    lines.append("ALTER TABLE user_profile ADD INDEX idx_points (points DESC);")
    lines.append("")
    lines.append("-- 8. 题库搜索：按 subject_code + difficulty_level 过滤")
    lines.append("ALTER TABLE admin_question_bank ADD INDEX idx_subject_diff (subject_code, difficulty_level);")
    lines.append("")
    lines.append("-- 9. 系统用户：登录查重（account/mobile/email）")
    lines.append("ALTER TABLE sys_user ADD INDEX idx_account (account);")
    lines.append("ALTER TABLE sys_user ADD INDEX idx_mobile (mobile);")
    lines.append("ALTER TABLE sys_user ADD INDEX idx_email (email);")
    lines.append("```")

    return "\n".join(lines)


async def main():
    print("=" * 60)
    print("  EduAgent MySQL EXPLAIN 分析器")
    print("=" * 60)
    print()

    results = []
    for module, desc, sql, args in CORE_QUERIES:
        print(f"  [{module}] {desc}...", end=" ")
        result = await analyze_query(module, desc, sql, args)
        results.append(result)
        status = "⚠️" if result["warnings"] else "✅"
        print(f"{status} type={result['type']} rows={result['rows']}")

    print()
    report = generate_report(results)

    # 写入报告文件
    report_path = Path(__file__).resolve().parents[2] / "docs" / "explain_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"  报告已保存: {report_path}")
    print()

    # 控制台摘要
    problem_count = sum(1 for r in results if r["warnings"])
    print(f"  总计: {len(results)} 条查询")
    print(f"  有问题: {problem_count} 条")
    print(f"  正常: {len(results) - problem_count} 条")
    print()


if __name__ == "__main__":
    asyncio.run(main())