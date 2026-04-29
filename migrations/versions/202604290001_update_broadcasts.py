"""add update broadcast notifications

Revision ID: 202604290001
Revises: 202604280001
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa


revision = "202604290001"
down_revision = "202604280001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "receive_updates_notifications",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )

    op.create_table(
        "update_broadcasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(length=4096), nullable=False),
        sa.Column("total_users", sa.Integer(), nullable=False),
        sa.Column("sent_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_update_broadcasts_id", "update_broadcasts", ["id"])
    op.create_index("ix_update_broadcasts_admin_user_id", "update_broadcasts", ["admin_user_id"])

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("receive_updates_notifications", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_update_broadcasts_admin_user_id", table_name="update_broadcasts")
    op.drop_index("ix_update_broadcasts_id", table_name="update_broadcasts")
    op.drop_table("update_broadcasts")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("receive_updates_notifications")
