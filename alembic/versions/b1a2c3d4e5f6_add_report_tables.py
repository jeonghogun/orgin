"""add_report_tables

Revision ID: b1a2c3d4e5f6
Revises: afd65ac9e42e
Create Date: 2025-08-30 10:03:47.110583

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1a2c3d4e5f6'
down_revision = 'afd65ac9e42e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE panel_reports (
        id SERIAL PRIMARY KEY,
        review_id VARCHAR(255) NOT NULL,
        round_num INTEGER NOT NULL,
        persona VARCHAR(255) NOT NULL,
        report_data JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_review
            FOREIGN KEY(review_id)
	        REFERENCES reviews(review_id)
	        ON DELETE CASCADE,
        UNIQUE (review_id, round_num, persona)
    );
    """)
    op.execute("""
    CREATE TABLE consolidated_reports (
        id SERIAL PRIMARY KEY,
        review_id VARCHAR(255) NOT NULL,
        round_num INTEGER NOT NULL,
        report_data JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_review
            FOREIGN KEY(review_id)
	        REFERENCES reviews(review_id)
	        ON DELETE CASCADE,
        UNIQUE (review_id, round_num)
    );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE consolidated_reports;")
    op.execute("DROP TABLE panel_reports;")
