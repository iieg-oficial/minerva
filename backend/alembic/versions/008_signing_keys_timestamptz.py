"""Signing keys: created_at / rotated_at con timezone

El código compara estas columnas con `datetime.now(timezone.utc)` (ventana de
propagación de la clave pendiente y purga de las retiradas). Con la columna naive,
PostgreSQL resuelve la comparación usando el `TimeZone` de la sesión y al leer
devuelve datetimes naive que pueden mezclarse con aware en Python. `timestamptz`
elimina las dos ambigüedades.

Los valores existentes ya están en UTC (el modelo siempre usó
`datetime.now(timezone.utc)`), así que el USING los reinterpreta sin desplazarlos.

Revision ID: 008_signing_keys_timestamptz
Revises: 007_role_permissions_cross_app
Create Date: 2026-07-20
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "008_signing_keys_timestamptz"
down_revision: Union[str, None] = "007_role_permissions_cross_app"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "signing_keys",
        "created_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "signing_keys",
        "rotated_at",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=True,
        postgresql_using="rotated_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "signing_keys",
        "rotated_at",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using="rotated_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "signing_keys",
        "created_at",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
