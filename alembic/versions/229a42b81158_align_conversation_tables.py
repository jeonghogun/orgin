"""Align conversation-related tables with new schema expectations

Revision ID: 229a42b81158
Revises: f1b2c3d4e5f6
Create Date: 2025-01-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "229a42b81158"
down_revision = "f1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # conversation_threads table adjustments
    with op.batch_alter_table("conversation_threads", schema=None) as batch:
        batch.alter_column("thread_id", new_column_name="id")
        batch.alter_column("room_id", new_column_name="sub_room_id")
        batch.alter_column("is_pinned", new_column_name="pinned")
        batch.alter_column("is_archived", new_column_name="archived")

    op.execute("ALTER TABLE conversation_threads ALTER COLUMN created_at TYPE TIMESTAMPTZ USING to_timestamp(created_at)")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING to_timestamp(updated_at)")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN updated_at SET DEFAULT now()")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN pinned SET DEFAULT false")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN archived SET DEFAULT false")

    op.execute("DROP INDEX IF EXISTS idx_conversation_threads_room_id")
    op.execute("DROP INDEX IF EXISTS idx_conversation_threads_created_at")
    op.execute("DROP INDEX IF EXISTS idx_conversation_threads_pinned_archived")
    op.create_index("ix_conversation_threads_sub_room_id", "conversation_threads", ["sub_room_id"], unique=False)
    op.create_index("ix_conversation_threads_created_at", "conversation_threads", ["created_at"], unique=False)
    op.create_index("ix_conversation_threads_pinned_archived", "conversation_threads", ["pinned", "archived"], unique=False)

    # conversation_messages table adjustments
    with op.batch_alter_table("conversation_messages", schema=None) as batch:
        batch.alter_column("message_id", new_column_name="id")
        batch.alter_column("timestamp", new_column_name="created_at")
        batch.drop_column("content_searchable")
        batch.drop_column("embedding")
        batch.drop_column("ts")
        batch.drop_column("user_id")
        batch.add_column(sa.Column("model", sa.String(), nullable=True))
        batch.add_column(sa.Column("status", sa.String(), nullable=False, server_default="draft"))

    op.execute(
        "ALTER TABLE conversation_messages ALTER COLUMN created_at TYPE TIMESTAMPTZ USING to_timestamp(created_at)"
    )
    op.execute(
        "ALTER TABLE conversation_messages ALTER COLUMN content TYPE TEXT "
        "USING CASE WHEN pg_typeof(content) = 'bytea'::regtype "
        "THEN convert_from(content, 'utf8') ELSE content::text END"
    )
    op.execute(
        "ALTER TABLE conversation_messages ALTER COLUMN meta TYPE JSONB "
        "USING CASE WHEN meta IS NULL OR meta = '' THEN NULL ELSE meta::jsonb END"
    )
    op.execute("ALTER TABLE conversation_messages ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE conversation_messages ALTER COLUMN status SET DEFAULT 'draft'")
    op.execute("UPDATE conversation_messages SET status = 'draft' WHERE status IS NULL")

    op.execute("DROP INDEX IF EXISTS idx_conversation_messages_thread_id")
    op.execute("DROP INDEX IF EXISTS idx_conversation_messages_ts")
    op.create_index("ix_conversation_messages_thread_id", "conversation_messages", ["thread_id"], unique=False)
    op.create_index("ix_conversation_messages_created_at", "conversation_messages", ["created_at"], unique=False)

    # attachments table adjustments
    op.execute("DROP INDEX IF EXISTS idx_attachments_thread_id")
    with op.batch_alter_table("attachments", schema=None) as batch:
        batch.alter_column("attachment_id", new_column_name="id")
        batch.drop_column("thread_id")
        batch.alter_column("filename", new_column_name="name")
        batch.alter_column("content_type", new_column_name="mime")
        batch.alter_column("file_size", new_column_name="size")
        batch.alter_column("file_path", new_column_name="url")

    op.execute("ALTER TABLE attachments ALTER COLUMN created_at TYPE TIMESTAMPTZ USING to_timestamp(created_at)")
    op.execute("ALTER TABLE attachments ALTER COLUMN created_at SET DEFAULT now()")

    # export_jobs alignment
    with op.batch_alter_table("export_jobs", schema=None) as batch:
        batch.alter_column("job_id", new_column_name="id")

    op.execute("ALTER TABLE export_jobs ALTER COLUMN created_at TYPE TIMESTAMPTZ USING to_timestamp(created_at)")
    op.execute("ALTER TABLE export_jobs ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING to_timestamp(updated_at)")
    op.execute("ALTER TABLE export_jobs ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE export_jobs ALTER COLUMN updated_at SET DEFAULT now()")
    op.execute("ALTER TABLE export_jobs ALTER COLUMN status SET DEFAULT 'queued'")
    op.execute("UPDATE export_jobs SET status = 'queued' WHERE status IS NULL")

    op.execute("DROP INDEX IF EXISTS idx_export_jobs_thread_id")
    op.execute("DROP INDEX IF EXISTS idx_export_jobs_user_id")
    op.create_index("ix_export_jobs_thread_id", "export_jobs", ["thread_id"], unique=False)
    op.create_index("ix_export_jobs_user_id", "export_jobs", ["user_id"], unique=False)


def downgrade() -> None:
    # export_jobs revert
    op.execute("DROP INDEX IF EXISTS ix_export_jobs_user_id")
    op.execute("DROP INDEX IF EXISTS ix_export_jobs_thread_id")
    op.execute("ALTER TABLE export_jobs ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE export_jobs ALTER COLUMN updated_at DROP DEFAULT")
    op.execute("ALTER TABLE export_jobs ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE export_jobs ALTER COLUMN updated_at TYPE BIGINT USING EXTRACT(EPOCH FROM updated_at)")
    op.execute("ALTER TABLE export_jobs ALTER COLUMN created_at TYPE BIGINT USING EXTRACT(EPOCH FROM created_at)")
    with op.batch_alter_table("export_jobs", schema=None) as batch:
        batch.alter_column("id", new_column_name="job_id")

    # attachments revert
    op.execute("ALTER TABLE attachments ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE attachments ALTER COLUMN created_at TYPE BIGINT USING EXTRACT(EPOCH FROM created_at)")
    with op.batch_alter_table("attachments", schema=None) as batch:
        batch.alter_column("id", new_column_name="attachment_id")
        batch.alter_column("name", new_column_name="filename")
        batch.alter_column("mime", new_column_name="content_type")
        batch.alter_column("size", new_column_name="file_size")
        batch.alter_column("url", new_column_name="file_path")
        batch.add_column(sa.Column("thread_id", sa.String(), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS idx_attachments_thread_id ON attachments(thread_id)")

    # conversation_messages revert
    op.execute("DROP INDEX IF EXISTS ix_conversation_messages_created_at")
    op.execute("DROP INDEX IF EXISTS ix_conversation_messages_thread_id")
    op.execute("ALTER TABLE conversation_messages ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TABLE conversation_messages ALTER COLUMN created_at DROP DEFAULT")
    op.execute(
        "ALTER TABLE conversation_messages ALTER COLUMN meta TYPE TEXT USING CASE WHEN meta IS NULL THEN NULL ELSE meta::text END"
    )
    op.execute("ALTER TABLE conversation_messages ALTER COLUMN content TYPE BYTEA USING convert_to(content, 'utf8')")
    op.execute("ALTER TABLE conversation_messages ALTER COLUMN created_at TYPE BIGINT USING EXTRACT(EPOCH FROM created_at)")
    with op.batch_alter_table("conversation_messages", schema=None) as batch:
        batch.drop_column("status")
        batch.drop_column("model")
        batch.add_column(sa.Column("user_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("content_searchable", sa.Text(), nullable=True))
        batch.add_column(sa.Column("embedding", sa.Text(), nullable=True))
        batch.add_column(sa.Column("ts", sa.Text(), nullable=True))
        batch.alter_column("created_at", new_column_name="timestamp")
        batch.alter_column("id", new_column_name="message_id")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversation_messages_thread_id ON conversation_messages(thread_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversation_messages_ts ON conversation_messages USING gin(ts)")

    # conversation_threads revert
    op.execute("DROP INDEX IF EXISTS ix_conversation_threads_pinned_archived")
    op.execute("DROP INDEX IF EXISTS ix_conversation_threads_created_at")
    op.execute("DROP INDEX IF EXISTS ix_conversation_threads_sub_room_id")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN archived DROP DEFAULT")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN pinned DROP DEFAULT")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN updated_at DROP DEFAULT")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN updated_at TYPE BIGINT USING EXTRACT(EPOCH FROM updated_at)")
    op.execute("ALTER TABLE conversation_threads ALTER COLUMN created_at TYPE BIGINT USING EXTRACT(EPOCH FROM created_at)")
    with op.batch_alter_table("conversation_threads", schema=None) as batch:
        batch.alter_column("id", new_column_name="thread_id")
        batch.alter_column("sub_room_id", new_column_name="room_id")
        batch.alter_column("pinned", new_column_name="is_pinned")
        batch.alter_column("archived", new_column_name="is_archived")

    op.execute("CREATE INDEX IF NOT EXISTS idx_conversation_threads_room_id ON conversation_threads(room_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversation_threads_created_at ON conversation_threads(created_at DESC)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_threads_pinned_archived ON conversation_threads(is_pinned, is_archived)"
    )
