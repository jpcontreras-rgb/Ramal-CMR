"""one order per quote

Revision ID: 0003
Revises: 0002
"""

from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_orders_quote_id",
        "orders",
        ["quote_id"],
    )


def downgrade():
    op.drop_constraint(
        "uq_orders_quote_id",
        "orders",
        type_="unique",
    )
