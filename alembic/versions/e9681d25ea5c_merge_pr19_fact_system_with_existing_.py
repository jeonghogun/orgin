"""merge pr19 fact system with existing migrations

Revision ID: e9681d25ea5c
Revises: c5e8f7a6b3d2, e5a9b8f7c6d0
Create Date: 2025-09-06 04:36:29.730683

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9681d25ea5c'
down_revision: Union[str, Sequence[str], None] = ('c5e8f7a6b3d2', 'e5a9b8f7c6d0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
