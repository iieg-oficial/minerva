"""Refresh tokens (rotación + detección de reúso)

Revision ID: 005_refresh_tokens
Revises: 004_auth_codes_pkce
Create Date: 2026-06-21
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "005_refresh_tokens"
down_revision: Union[str, None] = "004_auth_codes_pkce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("family_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("applications.client_id"), nullable=False),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("access_jti", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
