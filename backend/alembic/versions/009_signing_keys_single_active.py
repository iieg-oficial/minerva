"""Signing keys: a lo sumo una clave `active` y una `pending`

La rotación en dos fases asume ese invariante: `get_active()` firma con UNA clave y
`stage_key()`/`promote_key()` operan sobre UNA pendiente. Hasta ahora solo lo garantizaba
el código (UPDATE condicional en `promote`), así que un INSERT directo, una restauración
de backup a medias o un proceso viejo podían dejar dos activas y volver no determinista
con qué clave se firma.

Los índices únicos parciales lo vuelven un invariante de datos: PostgreSQL rechaza la
segunda fila `active` (o `pending`) sin depender de que la aplicación se porte bien.

Antes de crearlos hay que reparar los estados inválidos que ya existan, o el índice no
se puede construir:
- Varias `active`: se conserva la más reciente (es con la que se ha estado firmando) y
  las demás pasan a `retired`, para que sus tokens vigentes sigan verificando.
- Varias `pending`: se conserva la más reciente y las otras se **borran**. Una pendiente
  nunca firmó nada, así que borrarla no invalida ningún token.

Revision ID: 009_signing_keys_single_active
Revises: 008_signing_keys_timestamptz
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "009_signing_keys_single_active"
down_revision: Union[str, None] = "008_signing_keys_timestamptz"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Repara duplicados preexistentes: conserva la más reciente de cada estado.
    op.execute(
        """
        UPDATE signing_keys SET status = 'retired', rotated_at = COALESCE(rotated_at, now())
        WHERE status = 'active'
          AND id <> (SELECT id FROM signing_keys WHERE status = 'active' ORDER BY created_at DESC LIMIT 1)
        """
    )
    op.execute(
        """
        DELETE FROM signing_keys
        WHERE status = 'pending'
          AND id <> (SELECT id FROM signing_keys WHERE status = 'pending' ORDER BY created_at DESC LIMIT 1)
        """
    )

    op.create_index(
        "ux_signing_keys_single_active",
        "signing_keys",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ux_signing_keys_single_pending",
        "signing_keys",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ux_signing_keys_single_pending", table_name="signing_keys")
    op.drop_index("ux_signing_keys_single_active", table_name="signing_keys")
