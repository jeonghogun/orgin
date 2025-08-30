"""Add hybrid memory and fact store tables

Revision ID: 00dbc3f6a941
Revises: 4f2a569fdcc5
Create Date: 2025-08-29 11:30:57.441123

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '00dbc3f6a941'
down_revision: Union[str, None] = '4f2a569fdcc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add BM25 FTS columns to messages table
    op.execute("""
        ALTER TABLE messages ADD COLUMN IF NOT EXISTS ts tsvector
        GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages USING GIN (ts);
    """)

    # Create new user_facts table
    op.create_table(
        'user_facts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('value_json', postgresql.JSONB(astext_for_arra=False), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('updated_at', postgresql.TIMESTAMPTZ(), nullable=False, server_default=sa.text("now()"))
    )
    op.create_index(op.f('idx_user_facts_user_kind_key'), 'user_facts', ['user_id', 'kind', 'key'], unique=True)

    # Create new summary_notes table
    op.create_table(
        'summary_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column('room_id', sa.Text(), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('tokens_saved_estimate', sa.Integer(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMPTZ(), nullable=False, server_default=sa.text("now()"))
    )
    op.create_index(op.f('idx_summary_notes_room_week'), 'summary_notes', ['room_id', 'week_start'], unique=False)

    # Ensure pgvector index exists on messages.embedding
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_embedding ON messages USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
    """)


def downgrade() -> None:
    op.drop_index(op.f('idx_summary_notes_room_week'), table_name='summary_notes')
    op.drop_table('summary_notes')

    op.drop_index(op.f('idx_user_facts_user_kind_key'), table_name='user_facts')
    op.drop_table('user_facts')

    op.drop_index('idx_messages_ts', table_name='messages', if_exists=True)
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS ts;")

    # The vector index might have been created by the initial migration, so we only drop if it exists.
    op.drop_index('idx_messages_embedding', table_name='messages', if_exists=True)
