"""users and audit events

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():

    op.create_table(
        "users",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "username",
            sa.String(120),
            nullable=False,
        ),

        sa.Column(
            "full_name",
            sa.String(160),
            nullable=False,
        ),

        sa.Column(
            "password_hash",
            sa.String(255),
            nullable=False,
        ),

        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default="sales",
        ),

        sa.Column(
            "max_discount_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.Column(
            "last_login_at",
            sa.DateTime(),
            nullable=True,
        ),

        sa.UniqueConstraint("username"),
    )

    op.create_index(
        "ix_users_username",
        "users",
        ["username"],
        unique=True,
    )

    op.create_index(
        "ix_users_role",
        "users",
        ["role"],
    )

    op.create_index(
        "ix_users_active",
        "users",
        ["active"],
    )


    op.create_table(
        "audit_events",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),

        sa.Column(
            "prospect_id",
            sa.Integer(),
            sa.ForeignKey(
                "prospects.id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),

        sa.Column(
            "event_type",
            sa.String(60),
            nullable=False,
        ),

        sa.Column(
            "happened_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.Column(
            "details_json",
            sa.Text(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_audit_events_user_id",
        "audit_events",
        ["user_id"],
    )

    op.create_index(
        "ix_audit_events_prospect_id",
        "audit_events",
        ["prospect_id"],
    )

    op.create_index(
        "ix_audit_events_event_type",
        "audit_events",
        ["event_type"],
    )

    op.create_index(
        "ix_audit_events_happened_at",
        "audit_events",
        ["happened_at"],
    )


def downgrade():

    op.drop_table("audit_events")
    op.drop_table("users")
