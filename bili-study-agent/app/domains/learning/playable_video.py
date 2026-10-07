"""Canonical lesson video selection, shared by playback and learning context.

Queries use the aliases ``sv`` (session_video) and ``sa`` (session_asset).
Authorization remains a separate check after this stable selection.
"""

PLAYABLE_VIDEO_PREDICATE = "sv.transcode_status='completed' AND sv.duration_seconds > 0"
PLAYABLE_VIDEO_ORDER = "sa.sort_no, sv.id"
