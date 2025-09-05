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

# Load .env file to ensure environment variables are available
load_dotenv()


# revision identifiers, used by Alembic.
revision: str = '4f2a569fdcc5'
down_revision: Union[str, None] = 'a59e5b13d13d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    encryption_key = os.getenv("DB_ENCRYPTION_KEY")
    if not encryption_key:
        raise ValueError("DB_ENCRYPTION_KEY must be set in environment for this migration.")

    # Add encrypted content column
    op.add_column('messages', sa.Column('content_encrypted', sa.LargeBinary(), nullable=True))
    
    # Add searchable content column (for full-text search)
    op.add_column('messages', sa.Column('content_searchable', sa.Text(), nullable=True))

    # Encrypt the content and copy to searchable column
    stmt = sa.text("UPDATE messages SET content_encrypted = pgp_sym_encrypt(content, :key), content_searchable = content")
    stmt = stmt.bindparams(sa.bindparam('key', encryption_key))
    op.execute(stmt)

    # Drop original content column
    op.drop_column('messages', 'content')
    
    # Rename encrypted column to content (for backward compatibility)
    op.alter_column('messages', 'content_encrypted', new_column_name='content')
    op.alter_column('messages', 'content', nullable=False)
    op.alter_column('messages', 'content_searchable', nullable=False)


def downgrade() -> None:
    encryption_key = os.getenv("DB_ENCRYPTION_KEY")
    if not encryption_key:
        raise ValueError("DB_ENCRYPTION_KEY must be set in environment for this migration.")

    op.add_column('messages', sa.Column('content_decrypted', sa.Text(), nullable=True))

    stmt = sa.text("UPDATE messages SET content_decrypted = pgp_sym_decrypt(content, :key)")
    stmt = stmt.bindparams(sa.bindparam('key', encryption_key))
    op.execute(stmt)

    op.drop_column('messages', 'content')
    op.alter_column('messages', 'content_decrypted', new_column_name='content')
    op.alter_column('messages', 'content', nullable=False)
