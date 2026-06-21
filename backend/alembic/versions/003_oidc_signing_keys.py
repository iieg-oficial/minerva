"""OIDC signing keys table (RS256 / JWKS)

Revision ID: 003_oidc_signing_keys
Revises: 002_manifest_imports
Create Date: 2026-06-21
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "003_oidc_signing_keys"
down_revision: Union[str, None] = "002_manifest_imports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signing_keys",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kid", sa.String(), nullable=False),
        sa.Column("algorithm", sa.String(), nullable=False, server_default="RS256"),
        sa.Column("private_key_pem", sa.String(), nullable=False),  # cifrado en reposo
        sa.Column("public_key_pem", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signing_keys_kid", "signing_keys", ["kid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_signing_keys_kid", table_name="signing_keys")
    op.drop_table("signing_keys")
