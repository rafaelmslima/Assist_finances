"""initial schema

Revision ID: 202604280001
Revises: 
Create Date: 2026-04-28
"""

from alembic import op
import sqlalchemy as sa


revision = "202604280001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", sa.Integer(), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=True),
        sa.Column("username", sa.String(length=120), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_telegram_chat_id", "users", ["telegram_chat_id"])
    op.create_index("ix_users_telegram_user_id", "users", ["telegram_user_id"], unique=True)

    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expenses_category", "expenses", ["category"])
    op.create_index("ix_expenses_id", "expenses", ["id"])
    op.create_index("ix_expenses_telegram_user_id", "expenses", ["telegram_user_id"])
    op.create_index("ix_expenses_user_created_at", "expenses", ["user_id", "created_at"])
    op.create_index("ix_expenses_user_id", "expenses", ["user_id"])

    op.create_table(
        "incomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incomes_id", "incomes", ["id"])
    op.create_index("ix_incomes_telegram_user_id", "incomes", ["telegram_user_id"])
    op.create_index("ix_incomes_user_created_at", "incomes", ["user_id", "created_at"])
    op.create_index("ix_incomes_user_id", "incomes", ["user_id"])

    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "month", "category", name="uq_budget_user_month_category"),
    )
    op.create_index("ix_budgets_id", "budgets", ["id"])
    op.create_index("ix_budgets_telegram_user_id", "budgets", ["telegram_user_id"])
    op.create_index("ix_budgets_user_id", "budgets", ["user_id"])
    op.create_index("ix_budgets_user_month", "budgets", ["user_id", "month"])

    op.create_table(
        "fixed_expenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fixed_expenses_category", "fixed_expenses", ["category"])
    op.create_index("ix_fixed_expenses_id", "fixed_expenses", ["id"])
    op.create_index("ix_fixed_expenses_telegram_user_id", "fixed_expenses", ["telegram_user_id"])
    op.create_index("ix_fixed_expenses_user", "fixed_expenses", ["user_id"])
    op.create_index("ix_fixed_expenses_user_id", "fixed_expenses", ["user_id"])

    op.create_table(
        "daily_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.Integer(), nullable=True),
        sa.Column("sent_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sent_on", name="uq_daily_notification_user_date"),
    )
    op.create_index("ix_daily_notifications_id", "daily_notifications", ["id"])
    op.create_index("ix_daily_notifications_telegram_user_id", "daily_notifications", ["telegram_user_id"])
    op.create_index("ix_daily_notifications_user_id", "daily_notifications", ["user_id"])


def downgrade() -> None:
    op.drop_table("daily_notifications")
    op.drop_table("fixed_expenses")
    op.drop_table("budgets")
    op.drop_table("incomes")
    op.drop_table("expenses")
    op.drop_table("users")
