"""Elimina users.provider_subject y users.auth_provider

Ambas columnas solo tenían sentido con el login federado externo: `provider_subject`
guardaba el identificador del sujeto en el proveedor y `auth_provider` distinguía el
origen de la cuenta. Sin ese flujo nadie las lee para decidir nada, así que dejan de
existir.

Revision ID: 010_drop_provider_subject
Revises: 009_signing_keys_single_active
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "010_drop_provider_subject"
down_revision: Union[str, None] = "009_signing_keys_single_active"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "provider_subject")
    op.drop_column("users", "auth_provider")


def downgrade() -> None:
    op.add_column(
        "users", sa.Column("auth_provider", sa.String(length=20), nullable=False, server_default="local")
    )
    op.add_column("users", sa.Column("provider_subject", sa.String(length=255), nullable=True))
