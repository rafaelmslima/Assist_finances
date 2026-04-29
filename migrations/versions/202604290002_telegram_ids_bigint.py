"""use bigint for telegram identifiers

Revision ID: 202604290002
Revises: 202604290001
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa


revision = "202604290002"
down_revision = "202604290001"
branch_labels = None
depends_on = None


TELEGRAM_USER_ID_TABLES = (
    "users",
    "expenses",
    "incomes",
    "budgets",
    "fixed_expenses",
    "daily_notifications",
)


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "telegram_chat_id",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )

    for table_name in TELEGRAM_USER_ID_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "telegram_user_id",
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                existing_nullable=table_name != "users",
            )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "telegram_chat_id",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )

    for table_name in TELEGRAM_USER_ID_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "telegram_user_id",
                existing_type=sa.BigInteger(),
                type_=sa.Integer(),
                existing_nullable=table_name != "users",
            )
