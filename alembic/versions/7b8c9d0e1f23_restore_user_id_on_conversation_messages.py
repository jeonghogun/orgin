"""Restore conversation_messages.user_id column and backfill data

Revision ID: 7b8c9d0e1f23
Revises: 229a42b81158
Create Date: 2024-06-05 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "7b8c9d0e1f23"
down_revision = "229a42b81158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the user_id column back and populate it for existing rows."""
    # Add the column as nullable so we can backfill existing rows first
    op.add_column("conversation_messages", sa.Column("user_id", sa.String(), nullable=True))

    # Prefer explicit user ids stored in the JSON meta payload when present
    op.execute(
        """
        UPDATE conversation_messages
        SET user_id = meta->>'userId'
        WHERE user_id IS NULL AND meta IS NOT NULL AND meta ? 'userId'
        """
    )

    # Fall back to the owning thread's user for user-authored messages
    op.execute(
        """
        UPDATE conversation_messages AS cm
        SET user_id = ct.user_id
        FROM conversation_threads AS ct
        WHERE cm.user_id IS NULL
          AND cm.thread_id = ct.id
          AND cm.role = 'user'
        """
    )

    # System authored messages default to 'system'
    op.execute(
        """
        UPDATE conversation_messages
        SET user_id = 'system'
        WHERE user_id IS NULL
        """
    )

    # Make the column required going forward and align with ORM expectations
    op.alter_column("conversation_messages", "user_id", existing_type=sa.String(), nullable=False)

    # Mirror other indexes created by earlier migrations
    op.create_index(
        "ix_conversation_messages_user_id",
        "conversation_messages",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the user_id column and supporting index."""
    op.drop_index("ix_conversation_messages_user_id", table_name="conversation_messages")
    op.drop_column("conversation_messages", "user_id")
