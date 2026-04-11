"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "disabled", name="user_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_index(op.f("ix_users_telegram_user_id"), "users", ["telegram_user_id"], unique=False)

    op.create_table(
        "vpn_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("inbound_id", sa.Integer(), nullable=False),
        sa.Column("panel_client_email", sa.String(length=512), nullable=False),
        sa.Column("panel_client_uuid", sa.String(length=128), nullable=True),
        sa.Column("panel_remark", sa.String(length=512), nullable=True),
        sa.Column("panel_sub_id", sa.String(length=256), nullable=True),
        sa.Column("key_slot_number", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            sa.Enum("imported", "issued_by_bot", name="vpn_key_source", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", "imported_unbound", name="vpn_key_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "uq_vpn_keys_user_slot_active",
        "vpn_keys",
        ["user_id", "key_slot_number"],
        unique=True,
        postgresql_where=sa.text("status = 'active' AND user_id IS NOT NULL"),
    )

    op.create_table(
        "second_key_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="second_key_request_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "regeneration_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("old_key_id", sa.Integer(), nullable=False),
        sa.Column("new_key_id", sa.Integer(), nullable=False),
        sa.Column(
            "initiator",
            sa.Enum("user", "admin", "system", name="regeneration_initiator", native_enum=False),
            nullable=False,
        ),
        sa.Column("initiator_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["new_key_id"], ["vpn_keys.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["old_key_id"], ["vpn_keys.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "import_bindings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vpn_key_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["vpn_key_id"], ["vpn_keys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action_type", sa.String(length=128), nullable=False),
        sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "pending_user_notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pending_user_notifications_telegram_user_id"),
        "pending_user_notifications",
        ["telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pending_user_notifications_telegram_user_id"), table_name="pending_user_notifications")
    op.drop_table("pending_user_notifications")
    op.drop_table("audit_log")
    op.drop_table("admin_actions")
    op.drop_table("import_bindings")
    op.drop_table("regeneration_history")
    op.drop_table("second_key_requests")
    op.drop_index("uq_vpn_keys_user_slot_active", table_name="vpn_keys")
    op.drop_table("vpn_keys")
    op.drop_index(op.f("ix_users_telegram_user_id"), table_name="users")
    op.drop_table("users")
