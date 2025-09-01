"""Merge admin_settings and report_tables branches

Revision ID: 7cfc6c70d573
Revises: 9b9d8d759b09, b1a2c3d4e5f6
Create Date: 2025-08-31 01:53:31.426453

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7cfc6c70d573'
down_revision: Union[str, Sequence[str], None] = ('9b9d8d759b09', 'b1a2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
