"""Add message_versions table

Revision ID: f1b2c3d4e5f6
Revises: e9681d25ea5c
Create Date: 2025-09-15 08:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1b2c3d4e5f6'
down_revision: Union[str, None] = 'e9681d25ea5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('message_versions',
        sa.Column('version_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('message_id', sa.String(255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['messages.message_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('version_id')
    )
    op.create_index(op.f('ix_message_versions_message_id'), 'message_versions', ['message_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_message_versions_message_id'), table_name='message_versions')
    op.drop_table('message_versions')
