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


from sqlalchemy.dialects import postgresql

def upgrade() -> None:
    # Add NOT NULL constraints to columns that should not be empty
    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.alter_column('message_count',
               existing_type=sa.Integer(),
               nullable=False,
               existing_server_default=sa.text('0'))

    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.alter_column('embedding',
               existing_type=postgresql.VECTOR(1536),
               nullable=False)

    with op.batch_alter_table('user_profiles', schema=None) as batch_op:
        batch_op.alter_column('interests',
               existing_type=postgresql.ARRAY(sa.Text()),
               nullable=False,
               server_default='{}')

    # Add indexes to frequently queried foreign key columns
    op.create_index(op.f('idx_rooms_parent_id'), 'rooms', ['parent_id'], unique=False)
    op.create_index(op.f('idx_memories_user_id'), 'memories', ['user_id'], unique=False)


def downgrade() -> None:
    # Drop the added indexes
    op.drop_index(op.f('idx_memories_user_id'), table_name='memories')
    op.drop_index(op.f('idx_rooms_parent_id'), table_name='rooms')

    # Revert NOT NULL constraints
    with op.batch_alter_table('user_profiles', schema=None) as batch_op:
        batch_op.alter_column('interests',
               existing_type=postgresql.ARRAY(sa.Text()),
               nullable=True,
               server_default=None)

    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.alter_column('embedding',
               existing_type=postgresql.VECTOR(1536),
               nullable=True)

    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.alter_column('message_count',
               existing_type=sa.Integer(),
               nullable=True,
               existing_server_default=sa.text('0'))
