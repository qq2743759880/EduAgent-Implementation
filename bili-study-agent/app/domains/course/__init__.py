"""课程域（task11 契约冻结②）：curriculum→series 改造。

层级语义（对齐 edu.sql 权威表）：
    series（系列）
      └── series_cohort（班次）
            └── series_cohort_course（模块，挂 cohort 而非 series —— 修复旧 P3 问题）
                  └── series_cohort_session（课次）
                        └── session_video（视频）
"""
