"""Write completion report to proper location."""
import os
content = """# task14-fix 完工报告 — answers_json P0 系统缺陷修复

> **日期**：2026-08-20 | **状态**：✅ 等待编排者复验
> **前置**：task14 原始完成 + 技术批判（P0 dashboard 500：answers_json 列不存在）

## 修复清单

| 编号 | 级别 | 修改点 | 目标文件 |
|------|------|--------|---------|
| A | **P0** | dashboard 3 处 answers_json 聚合移除 | progress/service.py |
| B | **P0** | submit_homework / submit_exam INSERT 去 answers_json 列 | progress/service.py |
| C | P1 | 作业平均分用 AVG(COALESCE(total_score,0)) | progress/service.py |

## 验收证据（5/5）

1. GET /api/progress/dashboard → **200**（不再 500，真实聚合视频/作业/考试数）
2. POST /api/progress/homework/submit → **200** 落库（无 answers_json）
3. POST /api/progress/exam/submit → **200** 落库（无 answers_json）
4. GET /api/users/me/learning-summary → **200**（5 字段回归）
5. grep answers_json in progress/service.py = 0 行 SQL（仅注释）

## 契约⑤ 字段说明

DashboardOut：total_questions_attempted=0, total_questions_correct=0, overall_correct_rate=None
（edu.sql 无作答明细载体，前端 dashboard 不展示正确率/答题数）
"""

with open(r"e:\stu\project\stu\EduAgent实施手册\edu-agent\test-reports\task14-fix-completion-report.md", "w", encoding="utf-8") as f:
    f.write(content)
print("Written OK")