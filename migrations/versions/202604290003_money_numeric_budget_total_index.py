"""use numeric money values and unique total budgets

Revision ID: 202604290003
Revises: 202604290002
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa


revision = "202604290003"
down_revision = "202604290002"
branch_labels = None
depends_on = None


MONEY_TABLES = ("expenses", "incomes", "budgets", "fixed_expenses")


def upgrade() -> None:
    for table_name in MONEY_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "amount",
                existing_type=sa.Float(),
                type_=sa.Numeric(12, 2),
                existing_nullable=False,
            )

    op.execute(
        """
        DELETE FROM budgets
        WHERE category IS NULL
          AND id NOT IN (
              SELECT MIN(id)
              FROM budgets
              WHERE category IS NULL
              GROUP BY user_id, month
          )
        """
    )
    op.create_index(
        "uq_budgets_user_month_total",
        "budgets",
        ["user_id", "month"],
        unique=True,
        sqlite_where=sa.text("category IS NULL"),
        postgresql_where=sa.text("category IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_budgets_user_month_total", table_name="budgets")
    for table_name in MONEY_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "amount",
                existing_type=sa.Numeric(12, 2),
                type_=sa.Float(),
                existing_nullable=False,
            )
