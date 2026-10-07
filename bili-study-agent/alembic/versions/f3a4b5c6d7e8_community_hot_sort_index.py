"""add composite index for community HOT sort

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-08-15

依据：数据库体检报告 F4 项。
community_post 列表默认 HOT 排序：
  ORDER BY is_pinned DESC, hot_score DESC, created_at DESC
原 idx_board_created(board_code, created_at) 无法满足 → Using filesort。

新增 (board_code, is_pinned, hot_score, created_at)：
- 全 DESC 排序可由反向索引扫描（backward index scan）满足，消除 filesort。
- 只覆盖 HOT（默认）路径；NEW/LIKE 排序含 like_count 仍需 filesort——77 行量级可接受，
  模式上"索引跟着最高频查询走"。
- 代价：每次点赞/收藏更新 hot_score 时多维护一个索引页（写放大），
  这是"读多写少才适合排序索引"的典型取舍。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE `community_post` ADD INDEX `idx_board_pin_hot_created` "
        "(`board_code`, `is_pinned`, `hot_score`, `created_at`)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE `community_post` DROP INDEX `idx_board_pin_hot_created`"
    )
