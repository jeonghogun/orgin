"""add auto_fact_extraction_flag

Revision ID: c5e8f7a6b3d2
Revises: b9bb7fcd1ce6
Create Date: 2025-09-05 01:14:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5e8f7a6b3d2'
down_revision: Union[str, None] = 'b9bb7fcd1ce6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_profiles', sa.Column('auto_fact_extraction_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False))


def downgrade() -> None:
    op.drop_column('user_profiles', 'auto_fact_extraction_enabled')
