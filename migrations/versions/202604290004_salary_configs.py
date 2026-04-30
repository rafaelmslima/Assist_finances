"""add salary configs

Revision ID: 202604290004
Revises: 202604290003
Create Date: 2026-04-29 22:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "202604290004"
down_revision: str | None = "202604290003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "salary_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("schedule_type", sa.String(length=20), nullable=False),
        sa.Column("pay_day", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("current_cycle_start", sa.Date(), nullable=True),
        sa.Column("last_auto_salary_on", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_salary_config_user"),
    )
    op.create_index(op.f("ix_salary_configs_id"), "salary_configs", ["id"], unique=False)
    op.create_index("ix_salary_configs_active", "salary_configs", ["is_active"], unique=False)
    op.create_index(op.f("ix_salary_configs_telegram_user_id"), "salary_configs", ["telegram_user_id"], unique=False)
    op.create_index(op.f("ix_salary_configs_user_id"), "salary_configs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_salary_configs_user_id"), table_name="salary_configs")
    op.drop_index(op.f("ix_salary_configs_telegram_user_id"), table_name="salary_configs")
    op.drop_index("ix_salary_configs_active", table_name="salary_configs")
    op.drop_index(op.f("ix_salary_configs_id"), table_name="salary_configs")
    op.drop_table("salary_configs")
