"""Add performance indexes for messages and reviews

Revision ID: e5a9b8f7c6d0
Revises: 7cfc6c70d573
Create Date: 2025-09-02 13:17:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a9b8f7c6d0'
down_revision: Union[str, None] = '7cfc6c70d573'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('idx_messages_user_id', 'messages', ['user_id'], unique=False)
    op.create_index('idx_reviews_status', 'reviews', ['status'], unique=False)
    op.create_index('idx_reviews_room_created', 'reviews', ['room_id', 'created_at'], unique=False)
    op.create_index(
        'idx_reviews_active',
        'reviews',
        ['room_id'],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'in_progress')")
    )


def downgrade() -> None:
    op.drop_index('idx_reviews_active', table_name='reviews')
    op.drop_index('idx_reviews_room_created', table_name='reviews')
    op.drop_index('idx_reviews_status', table_name='reviews')
    op.drop_index('idx_messages_user_id', table_name='messages')
