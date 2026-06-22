"""Auth codes: PKCE + nonce + auth_time (OIDC)

Revision ID: 004_auth_codes_pkce
Revises: 003_oidc_signing_keys
Create Date: 2026-06-21
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "004_auth_codes_pkce"
down_revision: Union[str, None] = "003_oidc_signing_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("auth_codes", sa.Column("code_challenge", sa.String(), nullable=True))
    op.add_column("auth_codes", sa.Column("code_challenge_method", sa.String(), nullable=True))
    op.add_column("auth_codes", sa.Column("nonce", sa.String(), nullable=True))
    op.add_column("auth_codes", sa.Column("auth_time", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_codes", "auth_time")
    op.drop_column("auth_codes", "nonce")
    op.drop_column("auth_codes", "code_challenge_method")
    op.drop_column("auth_codes", "code_challenge")
