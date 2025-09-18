"""merge conversation and export branches

Revision ID: 57f8c41a6674
Revises: 229a42b81158, c3d4e5f6a7b8
Create Date: 2025-09-19 03:15:31.528689

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '57f8c41a6674'
down_revision: Union[str, Sequence[str], None] = ('229a42b81158', 'c3d4e5f6a7b8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
