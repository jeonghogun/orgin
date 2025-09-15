"""
Create initial tables from schema.sql - REFACTORED

This migration has been refactored to be dialect-agnostic, using Alembic
operations instead of raw PostgreSQL. This ensures compatibility with both
PostgreSQL and SQLite for easier local development and testing.

Revision ID: 37ecae34152b
Revises:
Create Date: 2025-08-29 03:36:16.716381
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '37ecae34152b'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # --- Tables ---

    op.create_table('rooms',
        sa.Column('room_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('owner_id', sa.String(255), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('parent_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.Column('message_count', sa.Integer(), nullable=True, server_default='0'),
        sa.ForeignKeyConstraint(['parent_id'], ['rooms.room_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('room_id')
    )

    op.create_table('messages',
        sa.Column('message_id', sa.String(255), nullable=False),
        sa.Column('room_id', sa.String(255), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.BigInteger(), nullable=False),
        sa.Column('embedding', postgresql.VECTOR(1536), nullable=True) if is_postgres else sa.Column('embedding', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.room_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('message_id')
    )

    op.create_table('reviews',
        sa.Column('review_id', sa.String(255), nullable=False),
        sa.Column('room_id', sa.String(255), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('instruction', sa.Text(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('total_rounds', sa.Integer(), nullable=False),
        sa.Column('current_round', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('completed_at', sa.BigInteger(), nullable=True),
        sa.Column('final_report', postgresql.JSONB, nullable=True) if is_postgres else sa.Column('final_report', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.room_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('review_id')
    )

    op.create_table('review_events',
        sa.Column('event_id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('review_id', sa.String(255), nullable=False),
        sa.Column('ts', sa.BigInteger(), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('round', sa.Integer(), nullable=True),
        sa.Column('actor', sa.String(255), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.review_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('event_id')
    )

    op.create_table('memories',
        sa.Column('memory_id', sa.String(255), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('room_id', sa.String(255), nullable=False),
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('embedding', postgresql.VECTOR(1536), nullable=True) if is_postgres else sa.Column('embedding', sa.Text(), nullable=True),
        sa.Column('importance', sa.Float(), nullable=True, server_default='1.0'),
        sa.Column('expires_at', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.room_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('memory_id')
    )

    op.create_table('review_metrics',
        sa.Column('review_id', sa.String(255), nullable=False),
        sa.Column('total_duration_seconds', sa.Float(), nullable=False),
        sa.Column('total_tokens_used', sa.Integer(), nullable=False),
        sa.Column('total_cost_usd', sa.Float(), nullable=False),
        sa.Column('round_metrics', postgresql.JSONB, nullable=True) if is_postgres else sa.Column('round_metrics', sa.Text(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.review_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('review_id')
    )

    op.create_table('user_profiles',
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), nullable=False, server_default='user'),
        sa.Column('name', sa.LargeBinary(), nullable=True),
        sa.Column('preferences', sa.LargeBinary(), nullable=True),
        sa.Column('conversation_style', sa.String(255), nullable=True, server_default='casual'),
        sa.Column('interests', postgresql.ARRAY(sa.Text), nullable=True) if is_postgres else sa.Column('interests', sa.Text(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('user_id')
    )

    op.create_table('conversation_contexts',
        sa.Column('context_id', sa.String(255), nullable=False),
        sa.Column('room_id', sa.String(255), nullable=False),
        sa.Column('user_id', sa.String(255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('key_topics', postgresql.ARRAY(sa.Text), nullable=True) if is_postgres else sa.Column('key_topics', sa.Text(), nullable=True),
        sa.Column('sentiment', sa.String(50), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.room_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('context_id'),
        sa.UniqueConstraint('room_id', 'user_id')
    )

    # --- Indexes ---
    op.create_index(op.f('ix_rooms_owner_id'), 'rooms', ['owner_id'], unique=False)
    op.create_index(op.f('ix_user_profiles_user_id'), 'user_profiles', ['user_id'], unique=False)
    op.create_index(op.f('ix_messages_room_id'), 'messages', ['room_id'], unique=False)
    op.create_index(op.f('ix_reviews_room_id'), 'reviews', ['room_id'], unique=False)
    op.create_index(op.f('ix_review_events_review_id'), 'review_events', ['review_id'], unique=False)
    op.create_index(op.f('ix_messages_room_id_timestamp'), 'messages', ['room_id', 'timestamp'], unique=False)
    op.create_index(op.f('ix_review_events_review_id_ts'), 'review_events', ['review_id', 'ts'], unique=False)

    if is_postgres:
        op.execute("""
            CREATE INDEX idx_messages_embedding ON messages USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);
        """)
        op.execute("""
            CREATE INDEX idx_memories_embedding ON memories USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);
        """)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_memories_embedding;")
        op.execute("DROP INDEX IF EXISTS idx_messages_embedding;")

    op.drop_index(op.f('ix_review_events_review_id_ts'), table_name='review_events')
    op.drop_index(op.f('ix_messages_room_id_timestamp'), table_name='messages')
    op.drop_index(op.f('ix_review_events_review_id'), table_name='review_events')
    op.drop_index(op.f('ix_reviews_room_id'), table_name='reviews')
    op.drop_index(op.f('ix_messages_room_id'), table_name='messages')
    op.drop_index(op.f('ix_user_profiles_user_id'), table_name='user_profiles')
    op.drop_index(op.f('ix_rooms_owner_id'), table_name='rooms')

    op.drop_table('conversation_contexts')
    op.drop_table('user_profiles')
    op.drop_table('review_metrics')
    op.drop_table('memories')
    op.drop_table('review_events')
    op.drop_table('reviews')
    op.drop_table('messages')
    op.drop_table('rooms')

    if is_postgres:
        op.execute("DROP EXTENSION IF EXISTS pgcrypto;")
        op.execute("DROP EXTENSION IF EXISTS vector;")
