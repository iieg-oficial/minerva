"""Elimina users.provider_subject

La columna solo la poblaba el login federado (identificador del sujeto en el proveedor
externo); sin ese flujo nadie la escribe ni la lee, así que deja de existir.

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


def downgrade() -> None:
    op.add_column("users", sa.Column("provider_subject", sa.String(length=255), nullable=True))
