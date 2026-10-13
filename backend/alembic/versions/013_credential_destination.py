"""Destino de los enlaces de credencial

`credential_tokens.application_id` guarda la aplicación a la que se manda a la persona
después de fijar su contraseña. Es opcional: sin destino, el enlace termina en el login
de Minerva como hasta ahora.

Revision ID: 013_credential_destination
Revises: 012_credential_lifecycle
Create Date: 2026-10-13
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "013_credential_destination"
down_revision: Union[str, None] = "012_credential_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credential_tokens",
        sa.Column("application_id", sa.String(), sa.ForeignKey("applications.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credential_tokens", "application_id")
