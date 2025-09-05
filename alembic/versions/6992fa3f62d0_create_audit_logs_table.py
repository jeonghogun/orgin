"""Create audit logs table

Revision ID: 6992fa3f62d0
Revises: 4f2a569fdcc5
Create Date: 2025-08-29 08:33:30.370046

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6992fa3f62d0'
down_revision: Union[str, None] = '4f2a569fdcc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_logs',
        sa.Column('log_id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('timestamp', sa.BIGINT(), nullable=False),
        sa.Column('admin_user_id', sa.String(length=255), nullable=False),
        sa.Column('action', sa.String(length=255), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
    )
    op.create_index(op.f('ix_audit_logs_admin_user_id'), 'audit_logs', ['admin_user_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_logs_timestamp'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_admin_user_id'), table_name='audit_logs')
    op.drop_table('audit_logs')
