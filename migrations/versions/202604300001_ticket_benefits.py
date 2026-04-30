"""add ticket benefits

Revision ID: 202604300001
Revises: 202604290004
Create Date: 2026-04-30 20:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "202604300001"
down_revision: str | None = "202604290004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("expenses", sa.Column("payment_source", sa.String(length=30), nullable=False, server_default="money"))

    op.create_table(
        "ticket_benefits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("benefit_type", sa.String(length=30), nullable=False),
        sa.Column("configured_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("cycle_start", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "benefit_type", name="uq_ticket_benefit_user_type"),
    )
    op.create_index(op.f("ix_ticket_benefits_id"), "ticket_benefits", ["id"], unique=False)
    op.create_index(op.f("ix_ticket_benefits_telegram_user_id"), "ticket_benefits", ["telegram_user_id"], unique=False)
    op.create_index(op.f("ix_ticket_benefits_user_id"), "ticket_benefits", ["user_id"], unique=False)
    op.create_index("ix_ticket_benefits_user_type", "ticket_benefits", ["user_id", "benefit_type"], unique=False)

    op.alter_column("users", "onboarding_completed", server_default=None)
    op.alter_column("expenses", "payment_source", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_ticket_benefits_user_type", table_name="ticket_benefits")
    op.drop_index(op.f("ix_ticket_benefits_user_id"), table_name="ticket_benefits")
    op.drop_index(op.f("ix_ticket_benefits_telegram_user_id"), table_name="ticket_benefits")
    op.drop_index(op.f("ix_ticket_benefits_id"), table_name="ticket_benefits")
    op.drop_table("ticket_benefits")
    op.drop_column("expenses", "payment_source")
    op.drop_column("users", "onboarding_completed")
