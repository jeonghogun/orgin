"""add user fact fields v2

Revision ID: b9bb7fcd1ce6
Revises: 00dbc3f6a941
Create Date: 2025-09-05 01:13:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b9bb7fcd1ce6'
down_revision: Union[str, None] = '00dbc3f6a941'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename 'key' column to 'fact_type' to be more descriptive
    op.alter_column('user_facts', 'key', new_column_name='fact_type')

    # Add new columns for the V2 fact system
    op.add_column('user_facts', sa.Column('normalized_value', sa.Text(), nullable=True))
    op.add_column('user_facts', sa.Column('source_message_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('user_facts', sa.Column('pending_review', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('user_facts', sa.Column('latest', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('user_facts', sa.Column('sensitivity', sa.String(length=50), server_default="'low'", nullable=False))

    # Make confidence non-nullable
    op.alter_column('user_facts', 'confidence',
               existing_type=sa.FLOAT(),
               nullable=False,
               server_default=sa.text('1.0'))

    # --- Data Migration for backfilling normalized_value ---
    op.execute("""
        UPDATE user_facts
        SET normalized_value = lower(value_json::text)
        WHERE normalized_value IS NULL AND value_json IS NOT NULL;
    """)
    op.execute("""
        UPDATE user_facts
        SET normalized_value = ''
        WHERE normalized_value IS NULL;
    """)

    # Make normalized_value non-nullable after backfill
    op.alter_column('user_facts', 'normalized_value',
               existing_type=sa.Text(),
               nullable=False)

    # Create new indexes on the correct columns
    op.create_index(op.f('ix_user_facts_user_id_fact_type_latest'), 'user_facts', ['user_id', 'fact_type', 'latest'], unique=False)
    op.create_index(op.f('ix_user_facts_user_id_fact_type_normalized_value'), 'user_facts', ['user_id', 'fact_type', 'normalized_value'], unique=False)

    # Add foreign key constraint
    op.create_foreign_key(
        'fk_user_facts_source_message_id',
        'user_facts', 'messages',
        ['source_message_id'], ['message_id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_user_facts_source_message_id', 'user_facts', type_='foreignkey')
    op.drop_index(op.f('ix_user_facts_user_id_fact_type_normalized_value'), table_name='user_facts')
    op.drop_index(op.f('ix_user_facts_user_id_fact_type_latest'), table_name='user_facts')

    op.alter_column('user_facts', 'fact_type', new_column_name='key')

    op.alter_column('user_facts', 'confidence',
               existing_type=sa.FLOAT(),
               nullable=True,
               server_default=None)

    op.drop_column('user_facts', 'latest')
    op.drop_column('user_facts', 'pending_review')
    op.drop_column('user_facts', 'source_message_id')
    op.drop_column('user_facts', 'sensitivity')
    op.drop_column('user_facts', 'normalized_value')
