"""Create kpi_snapshots table

Revision ID: 31074482757e
Revises: 6992fa3f62d0
Create Date: 2025-08-29 09:01:39.813456

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31074482757e'
down_revision: Union[str, None] = '6992fa3f62d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kpi_snapshots',
        sa.Column('snapshot_id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.UniqueConstraint('snapshot_date', 'metric_name', name='uq_kpi_snapshot_date_metric')
    )
    op.create_index(op.f('ix_kpi_snapshots_date_metric'), 'kpi_snapshots', ['snapshot_date', 'metric_name'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_kpi_snapshots_date_metric'), table_name='kpi_snapshots')
    op.drop_table('kpi_snapshots')
