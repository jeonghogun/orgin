"""Encrypt message content

Revision ID: 4f2a569fdcc5
Revises: a59e5b13d13d
Create Date: 2025-08-29 07:26:16.711123

"""
import os
from typing import Sequence, Union
from dotenv import load_dotenv

from alembic import op
import sqlalchemy as sa

# Load .env file to ensure environment variables are available in local development
if os.getenv("ENVIRONMENT", "development").lower() in {"development", "dev", "local", "test"}:
    load_dotenv()


# revision identifiers, used by Alembic.
revision: str = '4f2a569fdcc5'
down_revision: Union[str, None] = 'a59e5b13d13d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_encrypted', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('content_searchable', sa.Text(), nullable=True))

    # Data migration only for PostgreSQL
    if bind.dialect.name == 'postgresql':
        encryption_key = os.getenv("DB_ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError("DB_ENCRYPTION_KEY must be set for this migration on PostgreSQL.")

        stmt = sa.text("UPDATE messages SET content_encrypted = pgp_sym_encrypt(content, :key), content_searchable = content")
        stmt = stmt.bindparams(sa.bindparam('key', encryption_key))
        op.execute(stmt)

    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('content')
        batch_op.alter_column('content_encrypted', new_column_name='content', existing_type=sa.LargeBinary(), nullable=False)
        # In SQLite, the column might not have any data, so we can't make it non-nullable
        if bind.dialect.name == 'postgresql':
            batch_op.alter_column('content_searchable', existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_decrypted', sa.Text(), nullable=True))

    # Data migration only for PostgreSQL
    if bind.dialect.name == 'postgresql':
        encryption_key = os.getenv("DB_ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError("DB_ENCRYPTION_KEY must be set for this migration on PostgreSQL.")

        stmt = sa.text("UPDATE messages SET content_decrypted = pgp_sym_decrypt(content, :key)")
        stmt = stmt.bindparams(sa.bindparam('key', encryption_key))
        op.execute(stmt)

    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('content')
        batch_op.alter_column('content_decrypted', new_column_name='content', existing_type=sa.Text(), nullable=False)
