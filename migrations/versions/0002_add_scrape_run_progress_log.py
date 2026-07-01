"""Add progress_log to scrape_runs

Revision ID: 0002_progress_log
Revises: 0001_baseline
Create Date: 2026-03-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_progress_log"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scrape_runs",
        sa.Column("progress_log", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scrape_runs", "progress_log")
