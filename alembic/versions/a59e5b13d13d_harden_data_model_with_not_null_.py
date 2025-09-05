"""Harden data model with NOT NULL constraints and new indexes

Revision ID: a59e5b13d13d
Revises: 37ecae34152b
Create Date: 2025-08-29 05:24:09.736451

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a59e5b13d13d'
down_revision: Union[str, None] = '37ecae34152b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add NOT NULL constraints to columns that should not be empty
    op.execute("ALTER TABLE rooms ALTER COLUMN message_count SET NOT NULL")
    op.execute("ALTER TABLE memories ALTER COLUMN embedding SET NOT NULL")
    op.execute("ALTER TABLE user_profiles ALTER COLUMN interests SET NOT NULL")
    op.execute("ALTER TABLE user_profiles ALTER COLUMN interests SET DEFAULT '{}'")

    # Add indexes to frequently queried foreign key columns
    op.create_index(op.f('idx_rooms_parent_id'), 'rooms', ['parent_id'], unique=False)
    op.create_index(op.f('idx_memories_user_id'), 'memories', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop the added indexes
    op.drop_index(op.f('idx_memories_user_id'), table_name='memories')
    op.drop_index(op.f('idx_rooms_parent_id'), table_name='rooms')

    # Revert NOT NULL constraints
    # Note: Reverting a NOT NULL constraint simply makes it nullable again.
    op.execute("ALTER TABLE user_profiles ALTER COLUMN interests DROP NOT NULL")
    op.execute("ALTER TABLE user_profiles ALTER COLUMN interests DROP DEFAULT")
    op.execute("ALTER TABLE memories ALTER COLUMN embedding DROP NOT NULL")
    op.execute("ALTER TABLE rooms ALTER COLUMN message_count DROP NOT NULL")
