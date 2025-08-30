"""Create two-tier memory schema

Revision ID: 47cc50ae130a
Revises: 31074482757e
Create Date: 2025-08-29 18:19:59.475663

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47cc50ae130a'
down_revision: Union[str, Sequence[str], None] = '31074482757e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
