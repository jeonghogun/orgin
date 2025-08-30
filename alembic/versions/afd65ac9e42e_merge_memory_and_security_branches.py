"""Merge memory and security branches

Revision ID: afd65ac9e42e
Revises: 00dbc3f6a941, 47cc50ae130a
Create Date: 2025-08-29 22:40:46.685861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'afd65ac9e42e'
down_revision: Union[str, Sequence[str], None] = ('00dbc3f6a941', '47cc50ae130a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
